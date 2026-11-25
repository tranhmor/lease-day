"""Rule-based Landlord and Tenant policies (both v0.7 calibrated/symmetric and v0.6 compat)."""
import random
from typing import Any, Dict, List, Optional, Tuple

from .base import LandlordPolicy, TenantPolicy, clamp_rent


# ---------------------------------------------------------------------------
# v0.6 Compatibility Rules (for Acceptance Criterion #2: 1,200-room regression)
# ---------------------------------------------------------------------------

class RuleLandlordV06Compat(LandlordPolicy):
    """Exact reproduction of Lease Day v0.6 landlord repricing formulas."""

    def __init__(self, stayer_share: float = 0.5):
        self.stayer_share = stayer_share

    @staticmethod
    def _market_rate(v: float) -> float:
        return 0.06 if v < 0.04 else 0.02 if v < 0.08 else -0.01 if v < 0.12 else -0.04

    def renewal_offer(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        rng: random.Random = ctx["_rng"]
        if rng.random() < 0.30:
            return {"rent": ctx["current_rent"], "reason": "v06_stayer_no_hike"}
        rate = (self._market_rate(ctx["cell_vacancy"]) + ctx["demand_signal"]) * self.stayer_share
        return {"rent": ctx["current_rent"] * (1.0 + rate), "reason": "v06_renewal_formula"}

    def price_vacant(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        floor_r = ctx["floor_rent"]
        if ctx["vacant_for"] == 0:
            rate = self._market_rate(ctx["cell_vacancy"]) + ctx["demand_signal"]
            rent = max(floor_r, ctx["current_rent"] * (1.0 + rate))
            return {"rent": rent, "up_front": ctx["up_front"], "reason": "v06_vacate_reprice"}
        if ctx["vacant_for"] > 1:
            rent = max(floor_r, ctx["current_rent"] * 0.97)
            return {"rent": rent, "up_front": ctx["up_front"], "reason": "v06_vacant_decay"}
        return {"rent": ctx["current_rent"], "up_front": ctx["up_front"], "reason": "v06_hold"}

    def answer_counter(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {"accept": False, "rent": ctx["initial_offer"], "reason": "v06_no_bargain"}

    def pick_applicant(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        apps = ctx["applicants"]
        return {"tenant_id": apps[0]["tenant_id"] if apps else None, "reason": "v06_fcfs"}


class RuleTenantV06Compat(TenantPolicy):
    """Exact reproduction of Lease Day v0.6 tenant scoring (no bargaining, no amenity, no announcement)."""

    def at_expiry(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        best_opt = None  # (score, action, room_id, mode)
        cur = ctx["current_room"]
        if cur["affordable"] and cur["rule_within_stretch"]:
            best_opt = (cur["rule_score"], "renew", cur["room_id"], cur["rule_best_mode"])
        for c in ctx["candidates"]:
            if c["affordable"] and c["rule_within_stretch"]:
                cand = (c["rule_score"], "move", c["room_id"], c["rule_best_mode"])
                if best_opt is None or cand[0] < best_opt[0]:
                    best_opt = cand
        if best_opt is None:
            return {"action": "leave", "mode": None, "rent": None, "if_rejected": None, "apply": [], "reason": "v06_none_feasible"}
        _, act, rid, mode = best_opt
        if act == "renew":
            return {"action": "renew", "mode": mode, "rent": cur["offer_rent"], "if_rejected": None, "apply": [], "reason": "v06_renew"}
        return {"action": "move", "mode": mode, "rent": None, "if_rejected": None, "apply": [{"room_id": rid, "mode": mode}], "reason": "v06_move"}

    def search(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        best_c = None
        for c in ctx["candidates"]:
            if c["affordable"] and c["rule_within_stretch"]:
                if best_c is None or c["rule_score"] < best_c["rule_score"]:
                    best_c = c
        if best_c is None:
            return {"apply": [], "reason": "v06_none_feasible"}
        return {"apply": [{"room_id": best_c["room_id"], "mode": best_c["rule_best_mode"]}], "reason": "v06_best"}


# ---------------------------------------------------------------------------
# v0.7 Calibrated & Symmetric Rule Policies (strictly ignores announcements!)
# ---------------------------------------------------------------------------

class RuleLandlord(LandlordPolicy):
    """v0.7 Rule landlord: smoothed rolling zone vacancy, symmetric bargaining/terms/screening, blind to announcements."""

    def __init__(self, stayer_share: float = 0.5):
        self.stayer_share = stayer_share

    @staticmethod
    def _smooth_rate(v: float) -> float:
        """Continuous pricing curve: v=0% -> +5.5%, v=5% -> +1.3%, v=8% -> -1.2%, v>=12% -> -4.0%."""
        return max(-0.04, min(0.055, 0.055 - (v / 0.12) * 0.095))

    def renewal_offer(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        # Strictly ignores ctx["announcement"] so R-P == R-S identically!
        rng: random.Random = ctx["_rng"]
        ll = ctx["landlord"]
        v = ctx["zone_vacancy_smooth"]
        demand = ctx["demand_signal"]  # 0.0 before LINE_OPENS

        # Risk-averse landlords with good-standing tenants waive hikes more often
        no_hike_prob = 0.35 if (ll["risk"] == "怕空置" and ctx["tenant_good_standing"]) else 0.25
        if rng.random() < no_hike_prob:
            return {"rent": round(ctx["current_rent"], 2), "reason": "rule_keep_good_tenant"}

        rate = (self._smooth_rate(v) + demand) * self.stayer_share
        # Institutional landlords adjust slightly faster; patient landlords push slightly higher when tight
        if ll["kind"] == "托管机构":
            rate *= 1.15
        if ll["risk"] == "愿意等" and v < 0.04:
            rate += 0.005
        if not ctx["tenant_good_standing"]:
            rate += 0.01
        raw_rent = max(ctx["floor_rent"], ctx["current_rent"] * (1.0 + rate))
        rent, _ = clamp_rent(raw_rent, ctx["current_rent"])
        return {"rent": rent, "reason": f"rule_renewal_v={v:.3f}_d={demand:+.3f}"}

    def price_vacant(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        # Strictly ignores ctx["announcement"]!
        ll = ctx["landlord"]
        v = ctx["zone_vacancy_smooth"]
        demand = ctx["demand_signal"]
        floor_r = ctx["floor_rent"]
        up_front = ctx["up_front"]

        if ctx["vacant_for"] == 0:
            rate = self._smooth_rate(v) + demand
            if ll["risk"] == "愿意等" and v < 0.04:
                rate += 0.01
            raw_rent = max(floor_r, ctx["current_rent"] * (1.0 + rate))
            rent, _ = clamp_rent(raw_rent, ctx["current_rent"])
            # Symmetric payment-term adjustment based solely on realized vacancy
            if v < 0.035 and ll["risk"] == "愿意等" and up_front < 4:
                up_front += 1
            elif v > 0.095 and ll["risk"] == "怕空置" and up_front > 2:
                up_front -= 1
            return {"rent": rent, "up_front": up_front, "reason": f"rule_vacate_v={v:.3f}_d={demand:+.3f}"}

        if ctx["vacant_for"] > 1:
            decay = 0.96 if ll["risk"] == "怕空置" else 0.975
            raw_rent = max(floor_r, ctx["current_rent"] * decay)
            rent, _ = clamp_rent(raw_rent, ctx["current_rent"])
            if ctx["vacant_for"] >= 3 and up_front > 2:
                up_front -= 1
            return {"rent": rent, "up_front": up_front, "reason": f"rule_vacant_decay_m={ctx['vacant_for']}"}

        return {"rent": round(ctx["current_rent"], 2), "up_front": up_front, "reason": "rule_vacant_hold"}

    def answer_counter(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        # Strictly ignores ctx["announcement"]!
        ll = ctx["landlord"]
        v = ctx["zone_vacancy_smooth"]
        offer = ctx["initial_offer"]
        counter = ctx["counter_rent"]

        # Reservation floor depends on realized vacancy and landlord risk attitude
        if ll["risk"] == "怕空置" or v >= 0.075:
            min_ratio = 0.95
        elif v < 0.04 and ll["risk"] == "愿意等":
            min_ratio = 0.985
        else:
            min_ratio = 0.97

        if ctx["tenant_good_standing"]:
            min_ratio -= 0.005

        min_accept = max(ctx["floor_rent"], offer * min_ratio)
        if counter >= min_accept:
            return {"accept": True, "rent": round(counter, 2), "reason": "rule_accept_within_margin"}
        return {"accept": False, "rent": round(offer, 2), "reason": "rule_reject_below_floor"}

    def pick_applicant(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        # Ranks applicants by offered rent, payment safety (income-to-rent ratio), and standing
        apps = ctx["applicants"]
        if not apps:
            return {"tenant_id": None, "reason": "no_applicants"}
        ll = ctx["landlord"]

        def _rank(a: Dict[str, Any]) -> Tuple[float, float, int]:
            # Risk-averse landlords weight income safety & good standing slightly higher
            safety_w = 120.0 if ll["risk"] == "怕空置" else 60.0
            stand_bonus = 150.0 if a["good_standing"] else 0.0
            score = a["offered_rent"] + safety_w * min(a["income_to_rent"], 6.0) + stand_bonus
            return (score, a["income_to_rent"], -a["tenant_id"])

        best = max(apps, key=_rank)
        return {"tenant_id": best["tenant_id"], "reason": "rule_highest_rent_and_safety"}


class RuleTenant(TenantPolicy):
    """v0.7 Rule tenant: amenity-aware, couple privacy-aware, symmetric bargaining, blind to announcements."""

    def at_expiry(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        # Strictly ignores ctx["announcement"] and post-opening commute times!
        cur = ctx["current_room"]
        can_renew = cur["affordable"] and cur["rule_within_stretch"]
        renew_score = cur["rule_score"] if can_renew else float("inf")

        feasible_cands = [c for c in ctx["candidates"] if c["affordable"] and c["rule_within_stretch"]]
        feasible_cands.sort(key=lambda c: c["rule_score"])

        best_move_score = feasible_cands[0]["rule_score"] if feasible_cands else float("inf")
        top2 = [{"room_id": c["room_id"], "mode": c["rule_best_mode"]} for c in feasible_cands[:2]]

        if not can_renew and not feasible_cands:
            return {"action": "leave", "mode": None, "rent": None, "if_rejected": None, "apply": [], "reason": "rule_none_feasible"}

        # If renewing is best (or only affordable option)
        if can_renew and renew_score <= best_move_score:
            offer = cur["offer_rent"]
            old = cur["current_rent"]
            # Bargain once if landlord raised rent noticeably (>1.5%)
            if offer > old * 1.015:
                counter = round(old + 0.4 * (offer - old), 2)
                # If a close alternative exists within 150 RMB/mo of renewal, move if rejected; else accept
                if feasible_cands and best_move_score <= renew_score + 150.0:
                    if_rej, fb = "move", top2
                else:
                    if_rej, fb = "accept_offer", []
                return {
                    "action": "counter",
                    "mode": cur["rule_best_mode"],
                    "rent": counter,
                    "if_rejected": if_rej,
                    "apply": fb,
                    "reason": "rule_counter_rent_hike",
                }
            return {
                "action": "renew",
                "mode": cur["rule_best_mode"],
                "rent": offer,
                "if_rejected": None,
                "apply": [],
                "reason": "rule_renew_best",
            }

        # Moving is strictly better (or renewal is unaffordable)
        # If renewal is unaffordable because of a hike, try countering back to stretch limit before moving/leaving
        if not can_renew and cur["modes"] and cur["offer_rent"] > cur["current_rent"] * 1.01:
            stretch_cap = ctx["tenant"]["stretch_ratio"] * ctx["tenant"]["income"]
            counter = round(min(cur["current_rent"] * 1.01, stretch_cap), 2)
            if counter >= cur["current_rent"] * 0.90 and counter <= ctx["tenant"]["income"] - ctx["hard_floor"]:
                if_rej = "move" if top2 else "leave"
                return {
                    "action": "counter",
                    "mode": cur["rule_best_mode"],
                    "rent": counter,
                    "if_rejected": if_rej,
                    "apply": top2 if if_rej == "move" else [],
                    "reason": "rule_counter_to_afford",
                }

        return {
            "action": "move",
            "mode": top2[0]["mode"],
            "rent": None,
            "if_rejected": None,
            "apply": top2,
            "reason": "rule_move_better",
        }

    def search(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        feasible_cands = [c for c in ctx["candidates"] if c["affordable"] and c["rule_within_stretch"]]
        feasible_cands.sort(key=lambda c: c["rule_score"])
        top2 = [{"room_id": c["room_id"], "mode": c["rule_best_mode"]} for c in feasible_cands[:2]]
        if not top2:
            return {"apply": [], "reason": "rule_none_feasible"}
        return {"apply": top2, "reason": "rule_top2_candidates"}
