"""Base policy interfaces and strict code-level output validation / guardrails (v0.7 §4 & §4.3)."""
from typing import Any, Dict, List, Optional, Tuple


class LandlordPolicy:
    """Decision interface for landlords (implemented by RuleLandlord and LLMLandlord)."""

    def renewal_offer(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Return {'rent': float, 'reason': str}."""
        raise NotImplementedError

    def answer_counter(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Return {'accept': bool, 'rent': float, 'reason': str}."""
        raise NotImplementedError

    def price_vacant(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Return {'rent': float, 'up_front': int (2|3|4), 'reason': str}."""
        raise NotImplementedError

    def pick_applicant(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Return {'tenant_id': int | None, 'reason': str}."""
        raise NotImplementedError


class TenantPolicy:
    """Decision interface for tenants (implemented by RuleTenant and LLMTenant)."""

    def at_expiry(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Return:
        {
            'action': 'renew' | 'counter' | 'move' | 'leave',
            'mode': str | None,                      # commute mode for current room (if renew/counter)
            'rent': float | None,                    # counter-offer rent (if action == 'counter')
            'if_rejected': 'accept_offer'|'move'|'leave' | None,  # fallback if counter is rejected
            'apply': [{'room_id': int, 'mode': str}, ...],        # up to 2 targets if move or fallback move
            'reason': str,
        }
        """
        raise NotImplementedError

    def search(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Return {'apply': [{'room_id': int, 'mode': str}, ...], 'reason': str} (up to 2 targets)."""
        raise NotImplementedError


# ---- Hard Guardrails & Schema Validators (§4.3) ----

def clamp_rent(rent: float, ref_rent: float, lo_mult: float = 0.7, hi_mult: float = 1.3) -> Tuple[float, bool]:
    """Clamp rent into [0.7, 1.3] * ref_rent; return (clamped_value, was_clamped)."""
    lo = ref_rent * lo_mult
    hi = ref_rent * hi_mult
    if rent < lo:
        return round(lo, 2), True
    if rent > hi:
        return round(hi, 2), True
    return round(float(rent), 2), False


# Quotes this far from the current rent are almost surely a unit error (a multiplier like 1.03 or a percentage like 3),
# not a price: reject and retry instead of silently clamping to 0.7x. Inside this band, the 0.7-1.3x clamp still applies.
SANE_LO, SANE_HI = 0.5, 2.0


def _nullish(v: Any) -> Any:
    """Small models often write the string "null"/"None"/"" instead of JSON null."""
    if isinstance(v, str) and v.strip().lower() in ("", "null", "none", "无", "nil"):
        return None
    return v


def _to_float(val: Any) -> Optional[float]:
    if isinstance(val, bool) or val is None:
        return None
    try:
        f = float(val)
        return f if f == f and abs(f) < 1e9 else None
    except (TypeError, ValueError):
        return None


def validate_renewal_offer(raw: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    if not isinstance(raw, dict):
        return None, "not_dict"
    rent = _to_float(raw.get("rent"))
    if rent is None or rent <= 0:
        return None, "invalid_rent"
    if not SANE_LO * ctx["current_rent"] <= rent <= SANE_HI * ctx["current_rent"]:
        return None, "rent_out_of_range"
    clamped, was_clamped = clamp_rent(rent, ctx["current_rent"])
    reason = str(raw.get("reason", "")).strip()[:200]
    return {"rent": clamped, "clamped": was_clamped, "reason": reason}, ""


def validate_price_vacant(raw: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    if not isinstance(raw, dict):
        return None, "not_dict"
    rent = _to_float(raw.get("rent"))
    if rent is None or rent <= 0:
        return None, "invalid_rent"
    up_front = raw.get("up_front", ctx.get("up_front", 2))
    if isinstance(up_front, bool) or not isinstance(up_front, int) or up_front not in (2, 3, 4):
        return None, "invalid_up_front"
    if not SANE_LO * ctx["current_rent"] <= rent <= SANE_HI * ctx["current_rent"]:
        return None, "rent_out_of_range"
    clamped, was_clamped = clamp_rent(rent, ctx["current_rent"])
    reason = str(raw.get("reason", "")).strip()[:200]
    return {"rent": clamped, "up_front": up_front, "clamped": was_clamped, "reason": reason}, ""


def validate_answer_counter(raw: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    if not isinstance(raw, dict):
        return None, "not_dict"
    accept = raw.get("accept")
    if not isinstance(accept, bool):
        return None, "invalid_accept"
    if accept:
        agreed = _to_float(raw.get("rent"))
        if agreed is None:
            agreed = ctx["counter_rent"]
        # When accepting, agreed rent must lie within [counter_rent, initial_offer]
        lo = min(ctx["counter_rent"], ctx["initial_offer"])
        hi = max(ctx["counter_rent"], ctx["initial_offer"])
        agreed = max(lo, min(hi, agreed))
        agreed, _ = clamp_rent(agreed, ctx["current_rent"])
    else:
        agreed = ctx["initial_offer"]
    reason = str(raw.get("reason", "")).strip()[:200]
    out = {"accept": accept, "rent": round(float(agreed), 2), "reason": reason}
    if accept and agreed >= ctx["initial_offer"] - 0.5:
        # "Accept" at the original offer is a rejection of the counter: count it as one (H3(b) is a strict rate)
        out.update(accept=False, rent=round(float(ctx["initial_offer"]), 2), repaired="accept_at_offer_to_reject")
    return out, ""


def validate_pick_applicant(raw: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    if not isinstance(raw, dict):
        return None, "not_dict"
    tid = _nullish(raw.get("tenant_id"))
    if isinstance(tid, str) and tid.strip().lstrip("-").isdigit():
        tid = int(tid.strip())
    valid_ids = {a["tenant_id"] for a in ctx["applicants"]}
    if tid is not None and (isinstance(tid, bool) or tid not in valid_ids):
        return None, "invalid_tenant_id"
    reason = str(raw.get("reason", "")).strip()[:200]
    return {"tenant_id": tid, "reason": reason}, ""


def _validate_apply_list(items: Any, cand_map: Dict[int, Dict[str, Any]], max_items: int = 2) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    if items is None:
        return [], ""
    if not isinstance(items, list):
        return None, "apply_not_list"
    cleaned: List[Dict[str, Any]] = []
    seen = set()
    for entry in items[:max_items]:
        if isinstance(entry, dict):
            rid = entry.get("room_id")
            mode = entry.get("mode")
        elif isinstance(entry, int):
            rid = entry
            mode = None
        else:
            return None, "bad_apply_item"
        if rid not in cand_map or rid in seen:
            return None, f"room_not_in_candidates:{rid}"
        c = cand_map[rid]
        valid_modes = [m["mode"] for m in c["modes"] if m.get("feasible", True)]
        if not valid_modes:
            return None, f"no_feasible_mode:{rid}"
        if mode is None:
            mode = valid_modes[0]
        elif mode not in valid_modes:
            return None, f"invalid_mode:{mode}"
        seen.add(rid)
        cleaned.append({"room_id": rid, "mode": mode})
    return cleaned, ""


def validate_at_expiry(raw: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    if not isinstance(raw, dict):
        return None, "not_dict"
    action = raw.get("action")
    action = action.strip().lower() if isinstance(action, str) else action
    if action not in ("renew", "counter", "move", "leave"):
        return None, "invalid_action"

    cand_map = {c["room_id"]: c for c in ctx["candidates"]}
    cur = ctx["current_room"]
    cur_modes = [m["mode"] for m in cur["modes"] if m.get("feasible", True)]
    can_renew = bool(cur.get("affordable", False)) and bool(cur_modes)
    reason = str(raw.get("reason", "")).strip()[:200]

    if action == "leave":
        return {"action": "leave", "mode": None, "rent": None, "if_rejected": None, "apply": [], "reason": reason}, ""

    if action == "renew":
        if not can_renew:
            return None, "renew_not_affordable"
        mode = _nullish(raw.get("mode")) or cur_modes[0]
        if mode not in cur_modes:
            return None, f"invalid_renew_mode:{mode}"
        return {"action": "renew", "mode": mode, "rent": cur["offer_rent"], "if_rejected": None, "apply": [], "reason": reason}, ""

    if action == "move":
        raw_apply = raw.get("apply")
        if raw_apply is None and raw.get("room_id") is not None:
            raw_apply = [{"room_id": raw["room_id"], "mode": raw.get("mode")}]
        cleaned, err = _validate_apply_list(raw_apply, cand_map, max_items=2)
        if err or not cleaned:
            return None, err or "empty_move_apply"
        return {"action": "move", "mode": cleaned[0]["mode"], "rent": None, "if_rejected": None, "apply": cleaned, "reason": reason}, ""

    # action == "counter"
    if not cur_modes:
        return None, "counter_no_mode"
    c_rent = _to_float(raw.get("rent"))
    if c_rent is None or c_rent <= 0 or c_rent > cur["offer_rent"]:
        return None, "invalid_counter_rent"
    c_rent, _ = clamp_rent(c_rent, cur["current_rent"], lo_mult=0.75, hi_mult=1.30)
    if c_rent > cur["offer_rent"]:
        c_rent = cur["offer_rent"]
    # Check affordability at counter rent
    if c_rent > ctx["tenant"]["income"] - ctx["hard_floor"]:
        return None, "counter_unaffordable"
    mode = _nullish(raw.get("mode")) or cur_modes[0]
    if mode not in cur_modes:
        return None, f"invalid_counter_mode:{mode}"

    repaired = None
    raw_rej = _nullish(raw.get("if_rejected"))
    if_rej = raw_rej
    if if_rej not in ("accept_offer", "move", "leave"):
        if_rej = "accept_offer" if can_renew else ("move" if cand_map else "leave")
        repaired = f"if_rejected_{raw_rej}_to_{if_rej}"
    if if_rej == "accept_offer" and not can_renew:
        if_rej = "move" if cand_map else "leave"
        repaired = f"if_rejected_accept_offer_to_{if_rej}"

    cleaned_fb: List[Dict[str, Any]] = []
    if if_rej == "move":
        raw_fb = raw.get("apply") or raw.get("fallback_apply")
        cleaned_fb, err = _validate_apply_list(raw_fb, cand_map, max_items=2)
        if err or not cleaned_fb:
            # Graceful repair: fall back to accept_offer if affordable, else leave (logged, counted in run quality)
            if_rej = "accept_offer" if can_renew else "leave"
            cleaned_fb = []
            repaired = f"if_rejected_move_to_{if_rej}"
    out = {
        "action": "counter",
        "mode": mode,
        "rent": c_rent,
        "if_rejected": if_rej,
        "apply": cleaned_fb,
        "reason": reason,
    }
    if repaired:
        out["repaired"] = repaired
    return out, ""


def validate_search(raw: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    if not isinstance(raw, dict):
        return None, "not_dict"
    cand_map = {c["room_id"]: c for c in ctx["candidates"]}
    cleaned, err = _validate_apply_list(raw.get("apply", []), cand_map, max_items=2)
    if err:
        return None, err
    reason = str(raw.get("reason", "")).strip()[:200]
    return {"apply": cleaned or [], "reason": reason}, ""
