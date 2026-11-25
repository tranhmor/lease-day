"""Single-decision LLM behavioral diagnostics (v0.7 §5.4).

Runs controlled synthetic grids BEFORE full simulation:
1. Landlord renewal pricing grid: announcement x vacancy x months_to_open x good_standing (20 distinct instances/cell x 3 wordings)
2. Landlord bargaining concession test: announcement x vacancy x counter_discount (checks H3 sycophancy)
2b. Post-opening re-pricing: already-open line x rent premium over start_rent (0/5/8%) -> double-hike check
3. Tenant expiry grid: announcement x income_group x months_to_open (20 distinct instances/cell x 3 wordings),
   reported both pooled and per (announcement, months_to_open, income group) cell

Usage:
    python3 -m prototype_v07.diagnose --mock
    python3 -m prototype_v07.diagnose --live --samples 20 --cache runs/diag_cache.sqlite
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random
import statistics as st
import sys
import tempfile
import time
from typing import Any, Dict, List

from .agents.base import validate_answer_counter, validate_at_expiry, validate_renewal_offer
from .agents.llm import (
    DiskCache,
    LLMLandlord,
    LLMTenant,
    MockLLMBackend,
    OpenAICompatBackend,
    PROMPTS_DIR,
    _extract_json,
    _strip_private,
    output_format_spec,
    render_user_prompt,
    prompt_hashes,
)
from .agents.rule import RuleLandlord, RuleTenant
from .board_v07 import ZONE_AMENITY_SCORE, zone_label
from .lease_day_v07 import ANNOUNCEMENT_TEXT, FLOOR, LANDLORD_LINE_NOTE, LEASE_MONTHS, OPENED_TEXT, TENANT_LINE_NOTE

# Alternative wordings differ in framing only; the JSON schema block is shared with the frozen template.
TENANT_FORMAT = output_format_spec((PROMPTS_DIR / "tenant_at_expiry.txt").read_text(encoding="utf-8"))


def _between(fname: str, start: str, end: str) -> str:
    t = (PROMPTS_DIR / fname).read_text(encoding="utf-8")
    return t[t.index(start):t.index(end)].strip()


# Round 2: alternative wordings carry the same field descriptions as the default template, so they differ in
# framing only (round 1 compared an informed default against uninformed alternatives).
LANDLORD_FIELDS = _between("landlord_renewal_offer.txt", "字段说明", "输出格式")
TENANT_FACTS = _between("tenant_at_expiry.txt", "事实：", "可选 action")

LANDLORD_WORDINGS = [
    # Wording 0: default frozen template
    None,
    # Wording 1: concise neutral phrasing
    (
        "你是城市租赁市场的房东。请结合下方市场与房源信息，给出续租月租报价（必须在当前租金0.7-1.3倍内）。"
        "请权衡空置损失与租金收益，仅输出JSON：{\"rent\": 数字, \"reason\": \"简短理由\"}\n" + LANDLORD_FIELDS
    ),
    # Wording 2: explicit risk-framing phrasing
    (
        "作为一名理性房东，你需要决定下一年续租报价。如果定价过高租客可能搬离并造成空置损失；"
        "如果定价偏低则会错失市场租金。请依据下方结构化事实决策，仅输出JSON：{\"rent\": 数字, \"reason\": \"简短理由\"}\n" + LANDLORD_FIELDS
    ),
]

TENANT_WORDINGS = [
    None,
    (
        "你是在CBD上班的租客，12个月租约即将到期。结合下方收入、可用现金、续租报价和候选空房，"
        "决定续租(renew)、还价(counter)、搬家(move)或离开(leave)。仅输出规定格式的JSON。\n" + TENANT_FACTS + "\n" + TENANT_FORMAT
    ),
    (
        "请从一名在CBD通勤的理性租客出发，在租金负担、首期现金、通勤时长与搬家成本之间权衡，"
        "合同期为12个月。仅输出规定格式的JSON。\n" + TENANT_FACTS + "\n" + TENANT_FORMAT
    ),
]


def _make_landlord_ctx(
    rng: random.Random,
    announced: bool,
    vac_high: bool,
    m_to_open: int,
    good_standing: bool,
    idx: int,
    opened: bool = False,
    premium: float = 0.0,
) -> Dict[str, Any]:
    """opened=True: line already open (S/P post-opening). premium: rent already above start_rent by this share."""
    # Mixed-radix index -> full factorial kind(3) x zone(2) x risk(2) x landlord kind(2): no two factors share a
    # parity, so zone, risk, room type and landlord type are crossed (balanced when samples per cell is a multiple of 24).
    zone = "Z05" if (idx // 3) % 2 == 0 else "Z11"
    kind = ["便宜单间", "合租单间", "整租"][idx % 3]
    base_map = {"便宜单间": 1300, "合租单间": 1900, "整租": 4000}
    cur_rent = round(base_map[kind] * (1.0 + premium) * rng.uniform(0.98, 1.02), 1) if premium else round(base_map[kind] * rng.uniform(0.92, 1.08), 1)
    v = round(rng.uniform(0.11, 0.16) if vac_high else rng.uniform(0.015, 0.035), 4)
    ll_kind = "个人房东" if (idx // 12) % 2 == 0 else "托管机构"
    ll_risk = "怕空置" if (idx // 6) % 2 == 0 else "愿意等"
    month = 25 + m_to_open if opened else 25 - m_to_open
    ann = None
    if announced or opened:
        ann = {
            "text": OPENED_TEXT if opened else ANNOUNCEMENT_TEXT,
            "opens_at_month": 25,
            "months_to_opening": 0 if opened else m_to_open,
            "already_open": opened,
            "affects_this_zone": True,
            "expected_time_saving_min": 12 if zone == "Z05" else 15,
            "lease_months_after_open": LEASE_MONTHS if opened else max(0, LEASE_MONTHS - m_to_open),
            "note": LANDLORD_LINE_NOTE,
        }
    return {
        "month": month,
        "room_id": 1000 + idx,
        "zone": zone,
        "zone_label": zone_label(zone),
        "amenity_score": ZONE_AMENITY_SCORE[zone],
        "kind": kind,
        "current_rent": cur_rent,
        "start_rent": base_map[kind],
        "floor_rent": round(base_map[kind] * 0.9, 1),
        "up_front": 3 if kind == "合租单间" else (4 if kind == "整租" else 2),
        "vacant_for": 0,
        "last_vacant_months": 2 if vac_high else 0,
        "landlord": {"landlord_id": idx, "kind": ll_kind, "risk": ll_risk, "treated": True, "zones": [zone], "n_rooms": 6},
        "landlord_vacant_rooms": 2 if vac_high else 0,
        "zone_vacancy_smooth": v,
        # Rule-fallback inputs (stripped before the LLM sees them); synthetic cells use zone vacancy for the cell
        "cell_vacancy": v,
        "demand_signal": 0.0,
        "nearby_avg_rent": round(cur_rent * rng.uniform(0.98, 1.04), 1),
        "recent_apps_per_vacant": 0.6 if vac_high else 3.2,
        "tenant_tenure_months": rng.choice([12, 24, 36]),
        "tenant_good_standing": good_standing,
        "announcement": ann,
        "_rng": rng,
    }


def _make_tenant_ctx(rng: random.Random, announced: bool, group: str, m_to_open: int, idx: int) -> Dict[str, Any]:
    inc_ranges = {"low": (4500, 6800), "mid": (8000, 14000), "high": (17000, 28000)}
    income = rng.randrange(*inc_ranges[group], 500)
    cash = round(income * rng.uniform(1.5, 3.0), 1)
    comfort = 0.22 if group == "low" else 0.25
    stretch = 0.40 if group != "high" else 0.35
    cur_kind = "便宜单间" if group == "low" else ("合租单间" if group == "mid" else "整租")
    cur_rent = {"low": 1400, "mid": 2600, "high": 5800}[group]
    offer_rent = round(cur_rent * rng.uniform(1.01, 1.05), 1)
    tr_rent = {"low": 1350, "mid": 2000, "high": 4200}[group]
    months_after = max(0, LEASE_MONTHS - m_to_open) if announced else 0
    ann = None
    if announced:
        ann = {
            "text": ANNOUNCEMENT_TEXT,
            "opens_at_month": 25,
            "months_to_opening": m_to_open,
            "already_open": False,
            "note": TENANT_LINE_NOTE,
        }

    def _mk_card(rid: int, z: str, kind: str, rnt: float, sub_min: int, post_min: int, moving: bool) -> Dict[str, Any]:
        up = 2 if kind == "便宜单间" else (3 if kind == "合租单间" else 4)
        upfront = up * rnt + 500 if moving else 0.0
        m_entry: Dict[str, Any] = {"mode": "地铁", "min": sub_min, "transfers": 0, "month_fare": 260, "monthly_residual": round(income - rnt - 260, 1), "feasible": (income - rnt - 260) >= FLOOR}
        if announced and post_min < sub_min:
            m_entry["post_open_min"] = post_min
        eb_entry = {"mode": "电动车", "min": sub_min + 8, "transfers": 0, "month_fare": 120, "monthly_residual": round(income - rnt - 120, 1), "feasible": (income - rnt - 120) >= FLOOR}
        card = {
            "room_id": rid,
            "zone": z,
            "zone_label": zone_label(z),
            "amenity_score": ZONE_AMENITY_SCORE[z],
            "kind": kind,
            "rent": rnt,
            "current_rent": cur_rent if not moving else rnt,
            "offer_rent": rnt,
            "rent_pct_income": round(rnt / income, 3),
            "up_front": up,
            "upfront_cash_needed": upfront,
            "cash_gap": round(cash + cur_rent - upfront, 1) if moving else cash,
            "station_dist_m": 600,
            "modes": [m_entry, eb_entry],
            "affordable": (income - rnt - 120 >= FLOOR) and ((not moving) or (cash + cur_rent >= upfront)),
            "rule_within_stretch": rnt <= stretch * income,
            "rule_score": rnt + sub_min * 20,
            "rule_best_mode": "地铁",
            "contract_months": LEASE_MONTHS,
        }
        if announced:
            card["contract_months_after_open"] = months_after if z in ("Z05", "Z11") else 0
        return card

    cur_card = _mk_card(1, "Z08", cur_kind, offer_rent, 47, 47, moving=False)
    cands = [
        _mk_card(2, "Z05", cur_kind, tr_rent, 48, 36, moving=True),
        _mk_card(3, "Z11", cur_kind, round(tr_rent * 0.92, 1), 62, 47, moving=True),
        _mk_card(4, "Z09", cur_kind, round(cur_rent * 0.96, 1), 46, 46, moving=True),
    ]
    return {
        "month": 25 - m_to_open,
        "tenant": {
            "tenant_id": idx,
            "income": income,
            "group": group,
            "couple": group != "low" and (idx % 2 == 0),
            "car": False,
            "cash": cash,
            "locked_deposit": cur_rent,
            "available_move_cash": cash + cur_rent,
            "comfort_ratio": comfort,
            "stretch_ratio": stretch,
            "good_standing": True,
            "tenure_months": 12,
        },
        "current_room": cur_card,
        "candidates": cands,
        "hard_floor": FLOOR,
        "announcement": ann,
    }


def run_diagnostics(backend, cache: DiskCache, samples_per_cell: int = 20) -> Dict[str, Any]:
    ll_agent = LLMLandlord(backend, cache=cache)
    t_agent = LLMTenant(backend, cache=cache)
    rule_ll = RuleLandlord()
    rule_t = RuleTenant()

    total_calls = 0
    valid_calls = 0

    # 1. Landlord renewal grid
    ll_by_wording: Dict[int, Dict[str, List[float]]] = {}
    ll_factors: Dict[str, List[float]] = {}
    # Reported only: does the persona move quotes at all, and does it interact with the announcement?
    ll_persona: Dict[str, List[float]] = {}
    for w_idx, w_override in enumerate(LANDLORD_WORDINGS):
        buckets: Dict[str, List[float]] = {"ann_1": [], "ann_0": [], "vac_hi": [], "vac_lo": []}
        rng = random.Random(1000 + w_idx)
        for ann in (False, True):
            for vac_hi in (False, True):
                for m_open in (12, 6, 1):
                    for stand in (True, False):
                        for i in range(samples_per_cell):
                            ctx = _make_landlord_ctx(rng, ann, vac_hi, m_open, stand, i)
                            res = ll_agent._query_and_validate(
                                "landlord_renewal_offer.txt",
                                "renewal_offer",
                                ctx,
                                validate_renewal_offer,
                                rule_ll.renewal_offer,
                                system_override=w_override,
                            )
                            total_calls += 1
                            if not res.get("_meta", {}).get("fallback", False):
                                valid_calls += 1
                            pct = (res["rent"] - ctx["current_rent"]) / ctx["current_rent"]
                            buckets["ann_1" if ann else "ann_0"].append(pct)
                            buckets["vac_hi" if vac_hi else "vac_lo"].append(pct)
                            vac_tag = "vac_hi" if vac_hi else "vac_lo"
                            for fac, lvl in (("zone", ctx["zone"]), ("risk", ctx["landlord"]["risk"]),
                                             ("ll_kind", ctx["landlord"]["kind"]), ("kind", ctx["kind"])):
                                ll_factors.setdefault(f"{fac}={lvl}|{vac_tag}", []).append(pct)
                            ll_persona.setdefault(f"risk={ctx['landlord']['risk']}|{'ann' if ann else 'no_ann'}", []).append(pct)
                            ll_persona.setdefault(f"ll_kind={ctx['landlord']['kind']}|{'ann' if ann else 'no_ann'}", []).append(pct)
        ll_by_wording[w_idx] = {k: round(st.mean(v) * 100, 2) for k, v in buckets.items()}

    # 2. Landlord concession / bargaining test (H3)
    concession_stats: Dict[str, List[int]] = {"vac_lo_5pct": [], "vac_lo_10pct": [], "vac_hi_5pct": [], "ann_lo_5pct": []}
    rng_b = random.Random(2026)
    for label, ann, vac_hi, disc in [
        ("vac_lo_5pct", False, False, 0.05),
        ("vac_lo_10pct", False, False, 0.10),
        ("vac_hi_5pct", False, True, 0.05),
        ("ann_lo_5pct", True, False, 0.05),
    ]:
        for i in range(samples_per_cell):
            ctx = _make_landlord_ctx(rng_b, ann, vac_hi, 6, True, i)
            offer = round(ctx["current_rent"] * 1.04, 1)
            ctx["initial_offer"] = offer
            ctx["counter_rent"] = round(offer * (1.0 - disc), 1)
            res = ll_agent.answer_counter(ctx)
            total_calls += 1
            if not res.get("_meta", {}).get("fallback", False):
                valid_calls += 1
            concession_stats[label].append(1 if res["accept"] else 0)

    # 2b. Post-opening re-pricing: does an already-opened line trigger a second hike on rents already
    # above start_rent (pre-opening capitalization)? Compares premium 0 / 5% / 8%, opened vs not announced.
    reopen: Dict[str, List[float]] = {}
    rng_o = random.Random(2027)
    for premium in (0.0, 0.05, 0.08):
        for opened in (False, True):
            key = f"premium_{int(premium * 100)}pct_{'opened' if opened else 'no_line'}"
            reopen[key] = []
            for vac_hi in (False, True):
                for i in range(samples_per_cell):
                    ctx = _make_landlord_ctx(rng_o, False, vac_hi, 3, True, i, opened=opened, premium=premium)
                    res = ll_agent.renewal_offer(ctx)
                    total_calls += 1
                    if not res.get("_meta", {}).get("fallback", False):
                        valid_calls += 1
                    reopen[key].append((res["rent"] - ctx["current_rent"]) / ctx["current_rent"])

    # 3. Tenant anticipation grid
    t_by_wording: Dict[int, Dict[str, float]] = {}
    t_cells: Dict[str, List[int]] = {}
    # Reported only: before opening, does the tenant's reason describe the line as already open?
    misread_open: List[int] = []
    for w_idx, w_override in enumerate(TENANT_WORDINGS):
        move_tr_ann, move_tr_noann = [], []
        rng_t = random.Random(3000 + w_idx)
        for ann in (False, True):
            for grp in ("low", "mid", "high"):
                for m_open in (12, 6, 1):
                    for i in range(samples_per_cell):
                        ctx = _make_tenant_ctx(rng_t, ann, grp, m_open, i)
                        res = t_agent._query_and_validate(
                            "tenant_at_expiry.txt",
                            "at_expiry",
                            ctx,
                            validate_at_expiry,
                            rule_t.at_expiry,
                            system_override=w_override,
                        )
                        total_calls += 1
                        if not res.get("_meta", {}).get("fallback", False):
                            valid_calls += 1
                        picked_tr = 1 if (res["action"] == "move" and res["apply"] and res["apply"][0]["room_id"] in (2, 3)) else 0
                        (move_tr_ann if ann else move_tr_noann).append(picked_tr)
                        if ann:
                            reason = str(res.get("reason", ""))
                            misread_open.append(1 if any(w in reason for w in OPEN_MISREAD_WORDS) else 0)
                        t_cells.setdefault(f"{'ann' if ann else 'no_ann'}|m_to_open={m_open}|{grp}", []).append(picked_tr)
        t_by_wording[w_idx] = {
            "move_treated_ann_pct": round(st.mean(move_tr_ann) * 100, 1),
            "move_treated_noann_pct": round(st.mean(move_tr_noann) * 100, 1),
        }

    legal_rate = valid_calls / max(total_calls, 1)
    # ann > no-ann is the behaviour under study (H1): reported, never a pass condition (gating on it would select
    # prompts for the hypothesis). vac_hi < vac_lo is a sanity check on unrelated economics and stays a gate.
    dir_ann_ok = all(d["ann_1"] > d["ann_0"] for d in ll_by_wording.values())
    dir_vac_ok = all(d["vac_hi"] < d["vac_lo"] for d in ll_by_wording.values())
    return {
        "model": backend.model,
        "prompt_hashes": prompt_hashes(PROMPTS_DIR),
        "samples_per_cell": samples_per_cell,
        "total_calls": total_calls,
        "legal_output_rate": round(legal_rate, 4),
        "pass_legal_98pct": legal_rate >= 0.98,
        "landlord_direction_vac_ok": dir_vac_ok,
        "pass_gate": legal_rate >= 0.98 and dir_vac_ok,
        "reported_only": {"landlord_ann_hike_gt_noann_all_wordings": dir_ann_ok},
        "landlord_renewal_hike_pct_by_wording": ll_by_wording,
        # Pooled over wordings / announcement / months; each factor crossed with the vacancy state
        "landlord_renewal_hike_pct_by_factor": {k: round(st.mean(v) * 100, 2) for k, v in sorted(ll_factors.items())},
        "landlord_renewal_hike_pct_by_persona_x_ann": {k: round(st.mean(v) * 100, 2) for k, v in sorted(ll_persona.items())},
        "landlord_counter_accept_rate": {k: round(st.mean(v), 3) for k, v in concession_stats.items()},
        "landlord_post_opening_hike_pct": {k: round(st.mean(v) * 100, 2) for k, v in reopen.items()},
        "tenant_move_treated_by_wording": t_by_wording,
        # Pooled over wordings. Lock-in logic predicts ann-uplift rising as m_to_open falls (12 -> 6 -> 1).
        "tenant_move_treated_pct_by_cell": {k: round(st.mean(v) * 100, 1) for k, v in sorted(t_cells.items())},
        "tenant_reason_says_already_open_pct_pre_opening": round(st.mean(misread_open) * 100, 1) if misread_open else None,
    }


OPEN_MISREAD_WORDS = ("已开通", "新开通", "已经开通", "开通后通勤缩短")


class _CollectBackend:
    """Records first-attempt prompts and answers with a valid mock reply. A failing reply would trigger the rule
    fallback, which draws from the shared grid rng and shifts every later grid instance (prompts would then differ
    from the real pass). Run against a throwaway cache so mock replies never reach the real one."""

    def __init__(self, temperature: float):
        self.model, self.temperature = "collect-only", temperature
        self._mock = MockLLMBackend()
        self.prompts: Dict[str, tuple] = {}

    def complete(self, system_prompt: str, user_prompt: str):
        p_hash = hashlib.sha256((system_prompt + "\n---\n" + user_prompt).encode("utf-8")).hexdigest()[:24]
        self.prompts.setdefault(p_hash, (system_prompt, user_prompt))
        return self._mock.complete(system_prompt, user_prompt)


def prefetch(backend, cache: DiskCache, samples_per_cell: int, parallel: int) -> Dict[str, int]:
    """Send all first-attempt prompts concurrently and store the raw replies under the agents' cache keys.
    The real diagnostic pass then reads them from cache; only retries (invalid first outputs) go live."""
    col = _CollectBackend(backend.temperature)
    with tempfile.TemporaryDirectory() as tmp:
        scratch = DiskCache(str(Path(tmp) / "collect.sqlite"))
        try:
            run_diagnostics(col, scratch, samples_per_cell=samples_per_cell)
        finally:
            scratch.close()
    todo = [(h, v) for h, v in col.prompts.items() if cache.get(f"{backend.model}|{backend.temperature}|{h}") is None]
    print(f"prefetch: {len(todo)} uncached prompts, {parallel} concurrent", file=sys.stderr, flush=True)
    done = errors = 0
    t0 = time.time()
    with ThreadPoolExecutor(parallel) as ex:
        futs = {ex.submit(backend.complete, sp, up): h for h, (sp, up) in todo}
        for f in as_completed(futs):
            h = futs[f]
            try:
                raw, toks = f.result()
            except Exception:
                errors += 1
                continue
            cache.put(f"{backend.model}|{backend.temperature}|{h}", backend.model, backend.temperature, h, raw, toks)
            done += 1
            if done % 250 == 0:
                rate = done / (time.time() - t0) * 60
                print(f"  {done}/{len(todo)} ({rate:.0f}/min, eta {(len(todo) - done) / max(rate, 1e-9):.0f} min)", file=sys.stderr, flush=True)
    return {"prefetched": done, "errors": errors, "minutes": round((time.time() - t0) / 60, 1)}


def ping_backend() -> int:
    """Live smoke test: endpoint reachable, thinking disabled, JSON valid, latency per call. No cache."""
    b = OpenAICompatBackend()
    print(f"endpoint={b.base_url} model={b.model} thinking_off={b.thinking_style} max_tokens={b.max_tokens} timeout={b.timeout}s")
    rng = random.Random(0)
    cases = (
        ("landlord_renewal_offer.txt", "renewal_offer", LLMLandlord(b), _make_landlord_ctx(rng, True, False, 6, True, 0), validate_renewal_offer),
        ("tenant_at_expiry.txt", "at_expiry", LLMTenant(b), _make_tenant_ctx(rng, True, "mid", 6, 0), validate_at_expiry),
    )
    bad = 0
    for fname, dname, agent, ctx, validator in cases:
        sys_prompt = agent._get_template(fname)
        user_prompt = render_user_prompt(_strip_private(ctx, dname))
        t0 = time.time()
        try:
            raw, toks = b.complete(sys_prompt, user_prompt)
        except Exception as e:
            print(f"[{dname}] FAIL transport: {e}")
            bad += 1
            continue
        dt = time.time() - t0
        parsed = _extract_json(raw)
        ok, err = validator(parsed, ctx) if parsed is not None else (None, "json_parse_error")
        think = "<think>" in raw or len(raw) > 1500
        print(f"[{dname}] {dt:.1f}s tokens={toks} prompt_chars={len(sys_prompt) + len(user_prompt)} valid={ok is not None} {err}"
              + (" WARNING: output looks like it contains reasoning text" if think else ""))
        print(f"    raw: {raw[:300]}")
        bad += ok is None
    return 1 if bad else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Lease Day v0.7 §5.4 single-decision LLM diagnostics")
    ap.add_argument("--mock", action="store_true", help="Run with offline MockLLMBackend (zero API cost)")
    ap.add_argument("--live", action="store_true", help="Run with live OpenAI-compatible API from .env")
    ap.add_argument("--samples", type=int, default=5, help="Distinct instances per grid cell (20 for final §5.4 run)")
    ap.add_argument("--cache", type=str, default="rental_game/runs/diag_cache.sqlite", help="SQLite prompt cache path")
    ap.add_argument("--out", type=str, default="", help="Optional JSON path to save diagnostic report")
    ap.add_argument("--parallel", type=int, default=1, help="Live only: prefetch first attempts with N concurrent requests")
    ap.add_argument("--ping", action="store_true", help="Send 1 real landlord + 1 real tenant prompt; report latency, tokens, JSON validity")
    args = ap.parse_args()

    if args.ping:
        sys.exit(ping_backend())
    if not args.mock and not args.live:
        args.mock = True
    backend = MockLLMBackend() if args.mock else OpenAICompatBackend()
    cache = DiskCache(args.cache)
    try:
        pre = prefetch(backend, cache, args.samples, args.parallel) if (args.live and args.parallel > 1) else None
        report = run_diagnostics(backend, cache, samples_per_cell=args.samples)
        if pre is not None:
            report["prefetch"] = {**pre, "parallel": args.parallel}
    finally:
        cache.close()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
