"""Pre-registered metrics analyzer & case replay utility for Lease Day v0.7 (§2.3 & §6).

Computes all 5 pre-registered indicators with paired seed CIs and P0-3 methodological safeguards:
1. Net treated-zone rent rise (P-N and S-N) at M24 & M36 separately, plus pre-opening capitalization ratio.
2. Early move-ins (M13-M24): count, income-group share, mean income, mean liquid cash (P vs S vs N).
3. Lock-in renewal rate & renewal rent hikes in treated zones (M13-M24).
4. Benefit incidence: BOTH M12 stayer cohort panel (no composition bias!) AND cross-section by income group.
5. Decision-level treated-zone landlord offers (P vs S, OLS controlling for zone vacancy rate).
6. Full timeline replay of 1 treated landlord and 1 tenant from decisions.jsonl.
7. --validate: pre-registered Axtell & Epstein Level 1-3 checks (VALIDATION_SPEC) + LLM-vs-rule no-shock bias.

Usage:
    python3 -m prototype_v07.analyze_v07 --runs rental_game/runs --group R
    python3 -m prototype_v07.analyze_v07 --runs rental_game/runs_mock --group L --replay
"""
import argparse
import json
import math
from pathlib import Path
import statistics as st
from typing import Any, Dict, List, Optional, Tuple

from .lease_day_v07 import replay_agent


def ci95(vals: List[float]) -> Tuple[float, float]:
    if not vals:
        return 0.0, 0.0
    if len(vals) == 1:
        return vals[0], 0.0
    return st.mean(vals), 1.96 * st.stdev(vals) / math.sqrt(len(vals))


def _load_monthly(run_dir: Path) -> Dict[int, Dict[str, Any]]:
    out = {}
    with (run_dir / "monthly.jsonl").open("r", encoding="utf-8") as fp:
        for line in fp:
            rec = json.loads(line)
            out[rec["month"]] = rec
    return out


def _ols_p_vs_s_controlling_vacancy(rows: List[Tuple[float, float, float]]) -> Optional[Dict[str, float]]:
    """Simple 2-regressor OLS: y = b0 + b1*is_P + b2*vacancy (pure stdlib, normal equations)."""
    n = len(rows)
    if n < 6:
        return None
    # Build X'X (3x3) and X'y (3)
    s = [[0.0] * 3 for _ in range(3)]
    b = [0.0] * 3
    for y, is_p, vac in rows:
        x = (1.0, is_p, vac)
        for i in range(3):
            b[i] += x[i] * y
            for j in range(3):
                s[i][j] += x[i] * x[j]
    # Gaussian elimination 3x3
    aug = [s[i] + [b[i]] for i in range(3)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(aug[r][col]))
        if abs(aug[piv][col]) < 1e-12:
            return None
        aug[col], aug[piv] = aug[piv], aug[col]
        div = aug[col][col]
        aug[col] = [v / div for v in aug[col]]
        for r in range(3):
            if r != col:
                f = aug[r][col]
                aug[r] = [aug[r][k] - f * aug[col][k] for k in range(4)]
    beta = [aug[i][3] for i in range(3)]
    # Residual variance & SE of b1
    sse = sum((y - (beta[0] + beta[1] * is_p + beta[2] * vac)) ** 2 for y, is_p, vac in rows)
    sigma2 = sse / max(n - 3, 1)
    # Invert 3x3 s to get Var(b1)
    inv_aug = [s[i] + [1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(inv_aug[r][col]))
        inv_aug[col], inv_aug[piv] = inv_aug[piv], inv_aug[col]
        div = inv_aug[col][col]
        inv_aug[col] = [v / div for v in inv_aug[col]]
        for r in range(3):
            if r != col:
                f = inv_aug[r][col]
                inv_aug[r] = [inv_aug[r][k] - f * inv_aug[col][k] for k in range(6)]
    se_b1 = math.sqrt(max(0.0, sigma2 * inv_aug[1][4]))
    return {
        "n_offers": n,
        "b_P_vs_S_pct": round(beta[1] * 100, 2),
        "ci95_pct": round(1.96 * se_b1 * 100, 2),
        "b_vacancy": round(beta[2], 3),
    }


def analyze_group(runs_dir: Path, group: str) -> Dict[str, Any]:
    # Discover paired seeds present across N, S, P
    seed_sets = {}
    for sc in ("N", "S", "P"):
        found = set()
        for d in runs_dir.glob(f"{group}_{sc}_*"):
            if (d / "summary.json").exists() and (d / "monthly.jsonl").exists():
                try:
                    found.add(int(d.name.split("_")[-1]))
                except ValueError:
                    pass
        seed_sets[sc] = found

    seeds = sorted(seed_sets["N"] & seed_sets["S"] & seed_sets["P"])
    if not seeds:
        raise FileNotFoundError(f"No complete paired (N, S, P) seeds found for group {group} in {runs_dir}")

    # Load all summaries & monthly trajectories
    summaries: Dict[Tuple[str, int], Dict[str, Any]] = {}
    monthlies: Dict[Tuple[str, int], Dict[int, Dict[str, Any]]] = {}
    for sc in ("N", "S", "P"):
        for s in seeds:
            d = runs_dir / f"{group}_{sc}_{s}"
            summaries[(sc, s)] = json.loads((d / "summary.json").read_text(encoding="utf-8"))
            monthlies[(sc, s)] = _load_monthly(d)

    # Indicator 1: Net treated rent rise at M24 & M36 (P-N, S-N, P-S)
    d_m24_pn, d_m36_pn, d_m24_sn, d_m36_sn, d_m24_ps = [], [], [], [], []
    for s in seeds:
        mN, mS, mP = monthlies[("N", s)], monthlies[("S", s)], monthlies[("P", s)]
        last_m = max(mN.keys())
        d_m24_pn.append(mP[24]["rent_index_treated"] - mN[24]["rent_index_treated"])
        d_m36_pn.append(mP[last_m]["rent_index_treated"] - mN[last_m]["rent_index_treated"])
        d_m24_sn.append(mS[24]["rent_index_treated"] - mN[24]["rent_index_treated"])
        d_m36_sn.append(mS[last_m]["rent_index_treated"] - mN[last_m]["rent_index_treated"])
        d_m24_ps.append(mP[24]["rent_index_treated"] - mS[24]["rent_index_treated"])

    mean_m24_pn, ci_m24_pn = ci95(d_m24_pn)
    mean_m36_pn, ci_m36_pn = ci95(d_m36_pn)
    pre_share_pn = round(mean_m24_pn / mean_m36_pn, 3) if abs(mean_m36_pn) >= 1.0 else None

    # Indicator 2 & 3: M13-M24 move-ins (count, income, cash, groups) & lock-in renewals
    ind23: Dict[str, Dict[str, Any]] = {}
    for sc in ("N", "S", "P"):
        mi_cnt, all_inc, all_cash, ren_rates, ren_hikes = [], [], [], [], []
        grp_tot = {"low": 0, "mid": 0, "high": 0}
        for s in seeds:
            m = monthlies[(sc, s)]
            win = [m[k] for k in range(13, 25) if k in m]
            mi_cnt.append(sum(r["treated_move_ins"] for r in win))
            for r in win:
                all_inc.extend(r["treated_move_in_incomes"])
                all_cash.extend(r["treated_move_in_cash"])
                for g in ("low", "mid", "high"):
                    grp_tot[g] += r["treated_move_in_groups"][g]
                ren_hikes.extend(r["treated_renewal_hikes"])
            exp_t = sum(r["treated_expiries"] for r in win)
            ren_t = sum(r["treated_renewals"] for r in win)
            if exp_t > 0:
                ren_rates.append(ren_t / exp_t)
        tot_mi = max(sum(grp_tot.values()), 1)
        ind23[sc] = {
            "move_ins_per_run": round(st.mean(mi_cnt), 2),
            "move_in_mean_income": round(st.mean(all_inc), 1) if all_inc else None,
            "move_in_mean_cash": round(st.mean(all_cash), 1) if all_cash else None,
            "move_in_group_share": {g: round(grp_tot[g] / tot_mi, 3) for g in ("low", "mid", "high")},
            "treated_renewal_rate": round(st.mean(ren_rates), 3) if ren_rates else None,
            "treated_renewal_hike_pct": round(st.mean(ren_hikes) * 100, 2) if ren_hikes else None,
        }

    # Indicator 4: M12 stayer cohort panel (no Simpson's paradox)
    cohort_out: Dict[str, Dict[str, Any]] = {}
    for sc in ("N", "S", "P"):
        cohort_out[sc] = {}
        for g in ("low", "mid", "high"):
            rets = [summaries[(sc, s)]["m12_cohort"][g]["retention_rate"] for s in seeds if summaries[(sc, s)]["m12_cohort"][g]["n_m12"] > 0]
            dcosts = [summaries[(sc, s)]["m12_cohort"][g]["delta_full_cost"] for s in seeds if summaries[(sc, s)]["m12_cohort"][g]["delta_full_cost"] is not None]
            cohort_out[sc][g] = {
                "retention_rate": round(st.mean(rets), 3) if rets else None,
                "delta_full_cost_rmb": round(st.mean(dcosts), 1) if dcosts else None,
            }

    # Indicator 5: Decision-level treated-zone landlord quotes M13-M24 (P vs S controlling vacancy)
    offer_rows: List[Tuple[float, float, float]] = []
    for sc, is_p in (("S", 0.0), ("P", 1.0)):
        for s in seeds:
            dec_f = runs_dir / f"{group}_{sc}_{s}" / "decisions.jsonl"
            if not dec_f.exists():
                continue
            with dec_f.open("r", encoding="utf-8") as fp:
                for line in fp:
                    rec = json.loads(line)
                    if rec["agent_type"] == "landlord" and rec["decision"] in ("renewal_offer", "price_vacant"):
                        if 13 <= rec["month"] <= 24 and rec["inputs"].get("zone") in ("Z05", "Z11"):
                            cur_r = rec["inputs"]["current_rent"]
                            new_r = rec["output"]["rent"]
                            vac = rec["inputs"]["zone_vacancy_smooth"]
                            if cur_r > 0:
                                offer_rows.append(((new_r - cur_r) / cur_r, is_p, vac))

    decision_ols = _ols_p_vs_s_controlling_vacancy(offer_rows)

    return {
        "group": group,
        "n_paired_seeds": len(seeds),
        "indicator_1_rent_index": {
            "P_minus_N_M24": f"{mean_m24_pn:+.2f} ± {ci_m24_pn:.2f}",
            "P_minus_N_M36": f"{mean_m36_pn:+.2f} ± {ci_m36_pn:.2f}",
            "S_minus_N_M24": f"{ci95(d_m24_sn)[0]:+.2f} ± {ci95(d_m24_sn)[1]:.2f}",
            "S_minus_N_M36": f"{ci95(d_m36_sn)[0]:+.2f} ± {ci95(d_m36_sn)[1]:.2f}",
            "P_minus_S_M24": f"{ci95(d_m24_ps)[0]:+.2f} ± {ci95(d_m24_ps)[1]:.2f}",
            "pre_opening_capitalization_share_P_net": pre_share_pn,
        },
        "indicator_2_3_moveins_and_renewals_M13_24": ind23,
        "indicator_4_m12_cohort_panel": cohort_out,
        "indicator_5_decision_level_offers_P_vs_S": decision_ols,
        "diagnostics": {
            "fallback_rate_mean": round(st.mean(summaries[(sc, s)]["fallback_rate"] for sc in ("N", "S", "P") for s in seeds), 4),
            "counters_per_run": round(st.mean(summaries[("P", s)]["counters_total"] for s in seeds), 1),
            "counter_accept_rate_P": round(
                sum(summaries[("P", s)]["counter_accepts_total"] for s in seeds)
                / max(sum(summaries[("P", s)]["counters_total"] for s in seeds), 1),
                3,
            ),
            "multi_app_rooms_per_run_P": round(st.mean(summaries[("P", s)]["multi_app_total"] for s in seeds), 1),
        },
    }


# Pre-registered validation spec (Axtell & Epstein levels). Thresholds are fixed BEFORE looking at L-group results.
# "source" says where each threshold comes from; "internal" = our own tolerance, stated as such in the report.
EMPIRICAL_PREMIUM = {  # analysis/line_rent_results.md, 30-150 m2, 1 km, same-distance control, cell bootstrap 95% CI
    "line14_middle": (2.3, -1.5, 6.7),
    "line16_north": (5.8, -4.8, 13.7),
}
V22_TARGET, V22_TOL = 48.0, 0.10

VALIDATION_SPEC = {
    "V1.1_no_shock_stability": {"level": 1, "rule": "N: |rent_index_all M36 - M12| <= 3.0 and mean vacancy M13-36 in [3%, 12%]", "source": "internal tolerance"},
    # A3 (2026-11-25): scope narrowed to the formal market; the original all-kinds rule is still reported, not gated.
    "V1.2_burden_gradient": {"level": 1, "rule": "N tail, formal market (excl. 低价房), pooled tenant-months: rent/income low > mid > high in >= 80% of seeds; AND within every room kind, groups with >= 30 tenant-months (pooled over seeds) are strictly decreasing", "source": "stylized fact (lower-income renters bear higher burden); scope rationale in Lease_Day_v0.7_理论与实证依据.md §3-4"},
    "V1.3_rent_commute_tradeoff": {"level": 1, "rule": "N tail: Spearman(zone whole-unit rent, subway minutes) < 0", "source": "bid-rent theory; partly an input property of the board, so this checks it is preserved"},
    "V1.4_opening_premium_sign": {"level": 1, "rule": "S - N treated rent index at M36 > 0 (seed mean)", "source": "line_rent_results.md point estimates are positive for Lines 14/16"},
    "V1.5_announcement_effect_sign": {"level": 1, "rule": "P - S treated rent index at M24 > 0 (seed mean)", "source": "literature on anticipation (e.g., McMillen & McDonald 2004; Knaap et al. 2001) - direction only"},
    "V2.1_opening_premium_magnitude": {"level": 2, "rule": "S vs N treated premium (%) at M36 inside Line 14 95% CI [-1.5, 6.7]", "source": "line_rent_results.md"},
    "V2.2_commute_level": {"level": 2, "rule": "N mean one-way commute within 48 min +/-10% [43.2, 52.8] (weakly independent: not a calibration target, but TAU may have been chosen with it in mind); share >60 min reported vs 28-31%, not gated",
                           "source": "CAUPD/Baidu Maps 2022 Annual China Major Cities Commuting Monitoring Report (Beijing 2021: 48 min, >60 min 30%); see analysis/v22_commute_target.md"},
    "V3_micro_behaviour": {"level": 3, "rule": "not testable: no individual landlord/tenant rental panel", "source": "-"},
}


def _spearman(xs: List[float], ys: List[float]) -> Optional[float]:
    def ranks(v: List[float]) -> List[float]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2.0
            i = j + 1
        return r
    if len(xs) < 3:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None


def _paired_seeds(runs_dir: Path, group: str, scenarios=("N", "S", "P")) -> List[int]:
    sets = []
    for sc in scenarios:
        found = set()
        for d in runs_dir.glob(f"{group}_{sc}_*"):
            if (d / "summary.json").exists() and (d / "monthly.jsonl").exists():
                try:
                    found.add(int(d.name.split("_")[-1]))
                except ValueError:
                    pass
        sets.append(found)
    return sorted(set.intersection(*sets)) if sets else []


def validate_group(runs_dir: Path, group: str, baseline_runs: Optional[Path] = None, baseline_group: str = "R") -> Dict[str, Any]:
    """Level 1-3 validation checks (pre-registered in VALIDATION_SPEC). Returns per-check value + verdict."""
    from .board_v07 import ZONES
    seeds = _paired_seeds(runs_dir, group)
    if not seeds:
        raise FileNotFoundError(f"No complete paired (N, S, P) seeds for group {group} in {runs_dir}")
    mon = {(sc, s): _load_monthly(runs_dir / f"{group}_{sc}_{s}") for sc in "NSP" for s in seeds}
    summ = {(sc, s): json.loads((runs_dir / f"{group}_{sc}_{s}" / "summary.json").read_text(encoding="utf-8")) for sc in "NSP" for s in seeds}
    last = max(mon[("N", seeds[0])])
    out: Dict[str, Any] = {"group": group, "seeds": seeds, "checks": {}}

    def put(key: str, value: Any, verdict: str) -> None:
        out["checks"][key] = {**VALIDATION_SPEC[key], "value": value, "verdict": verdict}

    # V1.1 stability of the no-shock market
    drift = [mon[("N", s)][last]["rent_index_all"] - mon[("N", s)][12]["rent_index_all"] for s in seeds]
    vac = [st.mean(mon[("N", s)][m]["vacancy_all"] for m in range(13, last + 1)) for s in seeds]
    d_mean, d_ci = ci95(drift)
    ok = abs(d_mean) <= 3.0 and 0.03 <= st.mean(vac) <= 0.12
    put("V1.1_no_shock_stability", {"rent_index_drift_M12_to_end": f"{d_mean:+.2f} ± {d_ci:.2f}", "vacancy_M13_end": round(st.mean(vac), 4)}, "PASS" if ok else "FAIL")

    # V1.2 burden gradient (A3 scope: formal market + within-kind; original all-kinds rule reported for transparency)
    groups = ("low", "mid", "high")
    hold_all = [summ[("N", s)]["low_burden"] > summ[("N", s)]["mid_burden"] > summ[("N", s)]["high_burden"] for s in seeds]
    means_all = {g: round(st.mean(summ[("N", s)][g + "_burden"] for s in seeds), 3) for g in groups}
    cells = {s: summ[("N", s)].get("burden_cells") for s in seeds}
    if any(c is None for c in cells.values()):
        put("V1.2_burden_gradient", {"all_kinds_mean_burden": means_all, "all_kinds_seeds_holding": f"{sum(hold_all)}/{len(seeds)}"},
            "UNKNOWN (runs predate A3; rerun to get burden_cells)")
    else:
        def pooled(seed_list, kinds):
            acc = {g: [0.0, 0] for g in groups}
            for s in seed_list:
                for key, (mean_b, n) in cells[s].items():
                    kind, g = key.split("|")
                    if kind in kinds:
                        acc[g][0] += mean_b * n
                        acc[g][1] += n
            return {g: (acc[g][0] / acc[g][1] if acc[g][1] else None, acc[g][1]) for g in groups}
        formal = ("便宜单间", "合租单间", "整租")
        hold_formal = []
        for s in seeds:
            b = pooled([s], formal)
            hold_formal.append(all(b[g][0] is not None for g in groups) and b["low"][0] > b["mid"][0] > b["high"][0])
        formal_all = pooled(seeds, formal)
        within, within_ok = {}, True
        for kind in ("低价房",) + formal:
            b = pooled(seeds, (kind,))
            present = [(g, b[g][0]) for g in groups if b[g][1] >= 30]
            ok_k = all(x[1] > y[1] for x, y in zip(present, present[1:]))
            within_ok &= ok_k
            within[kind] = {g: (round(b[g][0], 3) if b[g][0] is not None else None, b[g][1]) for g in groups} | {"decreasing": ok_k}
        ok = sum(hold_formal) >= 0.8 * len(seeds) and within_ok
        put("V1.2_burden_gradient", {
            "formal_market_mean_burden": {g: round(formal_all[g][0], 3) for g in groups},
            "formal_market_seeds_holding": f"{sum(hold_formal)}/{len(seeds)}",
            "within_kind_pooled [burden, tenant-months]": within,
            "all_kinds_mean_burden (original rule, not gated)": means_all,
            "all_kinds_seeds_holding (original rule)": f"{sum(hold_all)}/{len(seeds)}",
            "blocked_M13_end_per_run": {g: round(st.mean(summ[("N", s)]["blocked_" + g] for s in seeds), 1) for g in groups},
        }, "PASS" if ok else "FAIL")

    # V1.3 rent-commute trade-off across zones (whole units)
    minutes = {z["id"]: z["options"]["地铁"]["min"] for z in ZONES}
    rhos = []
    for s in seeds:
        after = summ[("N", s)]["after"]
        pairs = [(minutes[k.split("|")[0]], v) for k, v in after.items() if k.endswith("|整租") and k.split("|")[0] in minutes]
        rho = _spearman([p[0] for p in pairs], [p[1] for p in pairs])
        if rho is not None:
            rhos.append(rho)
    r_mean = st.mean(rhos) if rhos else None
    put("V1.3_rent_commute_tradeoff", {"spearman_mean": round(r_mean, 3) if r_mean is not None else None}, "PASS" if r_mean is not None and r_mean < 0 else "FAIL")

    # V1.4 / V1.5 / V2.1 treated-zone effects
    sn36 = [mon[("S", s)][last]["rent_index_treated"] - mon[("N", s)][last]["rent_index_treated"] for s in seeds]
    ps24 = [mon[("P", s)][24]["rent_index_treated"] - mon[("S", s)][24]["rent_index_treated"] for s in seeds]
    prem = [(mon[("S", s)][last]["rent_index_treated"] / mon[("N", s)][last]["rent_index_treated"] - 1) * 100 for s in seeds]
    m14, ci14 = ci95(sn36)
    put("V1.4_opening_premium_sign", f"{m14:+.2f} ± {ci14:.2f} index pts", "PASS" if m14 > 0 else "FAIL")
    m15, ci15 = ci95(ps24)
    if group == "R":
        put("V1.5_announcement_effect_sign", f"{m15:+.2f} ± {ci15:.2f}", "N/A (rule agents ignore the announcement by design)")
    else:
        put("V1.5_announcement_effect_sign", f"{m15:+.2f} ± {ci15:.2f} index pts", "PASS" if m15 > 0 else "FAIL")
    pm, pci = ci95(prem)
    lo, hi = EMPIRICAL_PREMIUM["line14_middle"][1:]
    inside = lo <= pm <= hi
    overlap = (pm - pci) <= hi and (pm + pci) >= lo
    put("V2.1_opening_premium_magnitude", {
        "model_S_vs_N_pct": f"{pm:+.2f} ± {pci:.2f}",
        "empirical": {k: f"{v[0]:+.1f}% ({v[1]}, {v[2]})" for k, v in EMPIRICAL_PREMIUM.items()},
        "caveats": "model = 12 months after opening, all rooms (contract + asking); data = 1.5-2.5 years after opening, asking rents of 30-150 m2 listings; shock size differs",
    }, "CONSISTENT" if inside else ("OVERLAP" if overlap else "INCONSISTENT"))

    # V2.2 commute level (calibration fit only)
    c_mean, c_ci = ci95([summ[("N", s)]["commute"] for s in seeds])
    o60 = st.mean(summ[("N", s)]["over60"] for s in seeds)
    lo22, hi22 = V22_TARGET * (1 - V22_TOL), V22_TARGET * (1 + V22_TOL)
    put("V2.2_commute_level", {
        "model_N_mean_commute_min": f"{c_mean:.2f} ± {c_ci:.2f}",
        "target_min": V22_TARGET, "band": [round(lo22, 1), round(hi22, 1)],
        "model_share_over60": round(o60, 4), "empirical_share_over60": "0.28-0.31 (reported only)",
        "caveats": "weakly independent; population = CBD renters vs all central-city commuters; model has no peak congestion",
    }, "CONSISTENT" if lo22 <= c_mean <= hi22 else "INCONSISTENT")
    put("V3_micro_behaviour", None, "NOT TESTABLE")

    # LLM systematic-bias check: no-shock L/M market vs rule market on the same seeds
    if baseline_runs is not None and group != baseline_group:
        b_seeds = [s for s in seeds if (baseline_runs / f"{baseline_group}_N_{s}" / "monthly.jsonl").exists()]
        if b_seeds:
            rows = {}
            for key in ("rent_index_all", "rent_index_treated", "vacancy_all", "commute_all"):
                diffs = [mon[("N", s)][last][key] - _load_monthly(baseline_runs / f"{baseline_group}_N_{s}")[last][key] for s in b_seeds]
                m, c = ci95(diffs)
                rows[key] = f"{m:+.3f} ± {c:.3f}"
            out["llm_vs_rule_no_shock_M_end"] = {"seeds": b_seeds, "diff": rows,
                                                 "note": "a non-zero rent gap with no shock = LLM systematic bias; report alongside P-S"}
    out["level_reached"] = (
        "Level 1 " + ("met" if all(out["checks"][k]["verdict"] in ("PASS",) or out["checks"][k]["verdict"].startswith("N/A")
                                    for k in out["checks"] if k.startswith("V1")) else "NOT met")
        + "; Level 2 partial (V2.1 " + out["checks"]["V2.1_opening_premium_magnitude"]["verdict"]
        + ", V2.2 " + out["checks"]["V2.2_commute_level"]["verdict"] + "); Level 3 not testable"
    )
    return out


def print_sample_replay(runs_dir: Path, group: str, scenario: str = "P", seed: int = 0) -> None:
    dec_f = runs_dir / f"{group}_{scenario}_{seed}" / "decisions.jsonl"
    if not dec_f.exists():
        print(f"[replay] {dec_f} not found")
        return
    # Pick first treated-zone landlord & a tenant with >= 2 decisions
    ll_id, t_counts = None, {}
    with dec_f.open("r", encoding="utf-8") as fp:
        for line in fp:
            rec = json.loads(line)
            if ll_id is None and rec["agent_type"] == "landlord" and rec["inputs"].get("zone") in ("Z05", "Z11"):
                ll_id = rec["agent_id"]
            if rec["agent_type"] == "tenant":
                t_counts[rec["agent_id"]] = t_counts.get(rec["agent_id"], 0) + 1
    t_id = max(t_counts, key=lambda k: t_counts[k]) if t_counts else None

    if ll_id is not None:
        evs = replay_agent(str(dec_f), "landlord", ll_id)
        print(f"\n=== Sample Landlord Replay ({group}_{scenario}_{seed}, landlord_id={ll_id}, {len(evs)} events) ===")
        for e in evs[:6]:
            print(f"  M{e['month']:02d} {e['decision']:15s} zone={e['inputs'].get('zone')} out={e['output']} reason={e['reason']}")
    if t_id is not None:
        evs = replay_agent(str(dec_f), "tenant", t_id)
        print(f"\n=== Sample Tenant Replay ({group}_{scenario}_{seed}, tenant_id={t_id}, {len(evs)} events) ===")
        for e in evs[:6]:
            print(f"  M{e['month']:02d} {e['decision']:12s} out={e['output']} reason={e['reason']}")


# Paired-difference table: (label, kind, key, months, scale). kind "m" = monthly.jsonl field averaged over months,
# kind "s" = summary.json scalar. Same rows for R and L so the L table can be read against the R baseline.
PAIRED_ROWS = [
    ("受益区租金指数，第 24 月（点）", "m", "rent_index_treated", (24,), 1.0),
    ("受益区租金指数，第 36 月（点）", "m", "rent_index_treated", (36,), 1.0),
    ("受益区空置率，第 13–24 月（百分点）", "m", "vacancy_treated", tuple(range(13, 25)), 100.0),
    ("受益区空置率，第 25–36 月（百分点）", "m", "vacancy_treated", tuple(range(25, 37)), 100.0),
    ("全市平均通勤，第 25–36 月（分钟）", "m", "commute_all", tuple(range(25, 37)), 1.0),
    ("受益区迁入户数，第 13–24 月", "s", "tr_move_ins_m13_24", None, 1.0),
    ("受益区低收入户占比，第 25–36 月（百分点）", "m", "treated_low_share", tuple(range(25, 37)), 100.0),
    ("低收入户被挡次数，第 13–36 月", "s", "blocked_low", None, 1.0),
]


def paired_table(runs_dir: Path, group: str) -> str:
    """Markdown table of N level and seed-paired S-N, P-N, P-S differences with normal-approx 95% CI."""
    seeds = _paired_seeds(runs_dir, group)
    if not seeds:
        raise FileNotFoundError(f"No complete paired (N, S, P) seeds for group {group} in {runs_dir}")
    mon = {(sc, s): _load_monthly(runs_dir / f"{group}_{sc}_{s}") for sc in "NSP" for s in seeds}
    summ = {(sc, s): json.loads((runs_dir / f"{group}_{sc}_{s}" / "summary.json").read_text(encoding="utf-8")) for sc in "NSP" for s in seeds}

    def val(sc, s, kind, key, months, scale):
        if kind == "m":
            return st.mean(mon[(sc, s)][m][key] for m in months) * scale
        return summ[(sc, s)][key] * scale

    def cell(xs):
        m, h = ci95(xs)
        return f"{m:+.2f} ({m - h:+.2f}, {m + h:+.2f})"

    lines = [f"{group} 组，{len(seeds)} 个配对种子；括号内为 95% 置信区间（均值 ± 1.96 × 标准误）。", "",
             "| 指标 | N 组水平 | S − N | P − N | P − S |", "|---|---|---|---|---|"]
    for label, kind, key, months, scale in PAIRED_ROWS:
        v = {sc: [val(sc, s, kind, key, months, scale) for s in seeds] for sc in "NSP"}
        diff = lambda a, b: [x - y for x, y in zip(v[a], v[b])]
        lines.append(f"| {label} | {st.mean(v['N']):.2f} | {cell(diff('S', 'N'))} | {cell(diff('P', 'N'))} | {cell(diff('P', 'S'))} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------------------
# A5 (2026-11-25): criteria for the L group, written down BEFORE any real-LLM run. Do not edit after L results exist.
# ---------------------------------------------------------------------------------------------------------------
PREREG_L = {
    "H1": "Treated-zone landlord quotes (renewal_offer + price_vacant), M13-M24, y = (new-cur)/cur on [1, is_P, "
          "zone_vacancy_smooth]; seed-clustered SE (CR1), CI uses t(G-1). SUPPORTED if b_P > 0 and the 95% CI excludes 0. "
          "Also reported: per-seed b_P signs (k of G > 0) and P-S treated rent index at M24 (auxiliary, paired over seeds).",
    "H2": "Treated-zone move-ins M13-M24: P-S difference in mean income and in mean pre-move cash, seed bootstrap "
          "(resample seeds, 2,000 draws, fixed RNG). SUPPORTED if both differences > 0 with CIs excluding 0; "
          "DIRECTIONAL if both point estimates > 0 only. Low power (~90 move-ins per scenario over 5 seeds) is stated.",
    "H3": "N scenario, L vs R baseline: (a) share of renewal quotes with no hike (<= +0.05%) when zone vacancy < 4%; "
          "(b) counter-offer accept rate. OVER-CONCESSIVE if (a) or (b) exceeds R by > 20 pp, or (b) > 98%. "
          "Either result is reported.",
    "quality": "Each run: fallback rate < 2%, otherwise the run is void and must be rerun before analysis.",
    "B": "L-N minus R-N, month 36, same seeds: rent_index_all, rent_index_treated, vacancy_all, commute_all. "
         "If |mean rent-index gap| > 3 points, every P-S conclusion carries a bias caveat.",
    "crosscheck": "One paired seed run with a cloud model: H1 b_P sign vs the local model on the SAME seed. "
                  "ROBUST if same sign, MODEL-DEPENDENT if opposite (reported as such); pooled local b_P also shown.",
}
T_CRIT_975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
              10: 2.228, 15: 2.131, 19: 2.093, 20: 2.086, 30: 2.042}


def _t975(df: int) -> float:
    if df in T_CRIT_975:
        return T_CRIT_975[df]
    keys = sorted(T_CRIT_975)
    return T_CRIT_975[max(k for k in keys if k <= df)] if df > 1 else T_CRIT_975[1]


def _solve(a: List[List[float]], b: List[float]) -> Optional[List[float]]:
    n = len(b)
    aug = [list(a[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[piv][col]) < 1e-12:
            return None
        aug[col], aug[piv] = aug[piv], aug[col]
        d = aug[col][col]
        aug[col] = [v / d for v in aug[col]]
        for r in range(n):
            if r != col:
                f = aug[r][col]
                aug[r] = [aug[r][k] - f * aug[col][k] for k in range(n + 1)]
    return [aug[i][n] for i in range(n)]


def ols_cluster(rows: List[Tuple[float, List[float], Any]]) -> Optional[Dict[str, Any]]:
    """OLS with cluster-robust (CR1) covariance. rows = (y, x incl. intercept, cluster id). Returns beta, se, G, n."""
    n = len(rows)
    if n == 0:
        return None
    k = len(rows[0][1])
    xtx = [[sum(x[i] * x[j] for _, x, _ in rows) for j in range(k)] for i in range(k)]
    xty = [sum(x[i] * y for y, x, _ in rows) for i in range(k)]
    beta = _solve(xtx, xty)
    if beta is None:
        return None
    inv = [_solve(xtx, [1.0 if r == c else 0.0 for r in range(k)]) for c in range(k)]  # columns of (X'X)^-1
    inv = [[inv[c][r] for c in range(k)] for r in range(k)]
    clusters: Dict[Any, List[float]] = {}
    for y, x, g in rows:
        e = y - sum(b_ * xi for b_, xi in zip(beta, x))
        u = clusters.setdefault(g, [0.0] * k)
        for i in range(k):
            u[i] += x[i] * e
    G = len(clusters)
    meat = [[sum(u[i] * u[j] for u in clusters.values()) for j in range(k)] for i in range(k)]
    corr = (G / (G - 1)) * ((n - 1) / (n - k)) if G > 1 and n > k else 1.0
    tmp = [[sum(inv[i][m] * meat[m][j] for m in range(k)) for j in range(k)] for i in range(k)]
    cov = [[corr * sum(tmp[i][m] * inv[m][j] for m in range(k)) for j in range(k)] for i in range(k)]
    return {"beta": beta, "se": [math.sqrt(max(cov[i][i], 0.0)) for i in range(k)], "G": G, "n": n}


def _offer_rows(runs_dir: Path, group: str, seeds: List[int]) -> List[Tuple[float, List[float], int]]:
    rows = []
    for sc, is_p in (("S", 0.0), ("P", 1.0)):
        for s in seeds:
            dec_f = runs_dir / f"{group}_{sc}_{s}" / "decisions.jsonl"
            if not dec_f.exists():
                raise FileNotFoundError(f"{dec_f} missing: H1 needs decision logs (do not use --no-decision-log)")
            with dec_f.open("r", encoding="utf-8") as fp:
                for line in fp:
                    rec = json.loads(line)
                    if rec["agent_type"] != "landlord" or rec["decision"] not in ("renewal_offer", "price_vacant"):
                        continue
                    inp = rec["inputs"]
                    if 13 <= rec["month"] <= 24 and inp.get("zone") in ("Z05", "Z11") and inp["current_rent"] > 0:
                        y = (rec["output"]["rent"] - inp["current_rent"]) / inp["current_rent"]
                        rows.append((y, [1.0, is_p, inp["zone_vacancy_smooth"]], s))
    return rows


def persona_exploratory(runs_dir: Path, group: str, seeds: List[int]) -> Dict[str, Any]:
    """EXPLORATORY, not pre-registered (added before any L-group run): landlord persona mix per seed and the
    P - S mean quote change in treated zones (months 13-24) split by persona. P and S share the landlords of a seed."""
    mix = {}
    for s in seeds:
        meta = json.loads((runs_dir / f"{group}_N_{s}" / "summary.json").read_text(encoding="utf-8"))["landlords_meta"]
        tr = [l for l in meta if l.get("treated")]
        mix[s] = {"treated_n": len(tr),
                  "treated_risk_怕空置": sum(1 for l in tr if l["risk"] == "怕空置"),
                  "treated_kind_托管机构": sum(1 for l in tr if l["kind"] == "托管机构"),
                  "all_risk_怕空置": sum(1 for l in meta if l["risk"] == "怕空置"),
                  "all_kind_托管机构": sum(1 for l in meta if l["kind"] == "托管机构"), "all_n": len(meta)}
    cells: Dict[str, Dict[str, List[float]]] = {}
    for sc in ("S", "P"):
        for s in seeds:
            dec_f = runs_dir / f"{group}_{sc}_{s}" / "decisions.jsonl"
            if not dec_f.exists():
                continue
            with dec_f.open("r", encoding="utf-8") as fp:
                for line in fp:
                    rec = json.loads(line)
                    if rec["agent_type"] != "landlord" or rec["decision"] not in ("renewal_offer", "price_vacant"):
                        continue
                    inp = rec["inputs"]
                    if 13 <= rec["month"] <= 24 and inp.get("zone") in ("Z05", "Z11") and inp["current_rent"] > 0:
                        y = (rec["output"]["rent"] - inp["current_rent"]) / inp["current_rent"] * 100
                        for lab in (f"risk={inp['landlord']['risk']}", f"kind={inp['landlord']['kind']}"):
                            cells.setdefault(lab, {"S": [], "P": []})[sc].append(y)
    split = {k: {"P_minus_S_pct": round(st.mean(v["P"]) - st.mean(v["S"]), 3) if v["P"] and v["S"] else None,
                 "n_P": len(v["P"]), "n_S": len(v["S"])} for k, v in sorted(cells.items())}
    return {"label": "EXPLORATORY (not pre-registered)", "persona_mix_by_seed": mix, "treated_quote_change_by_persona": split}


def h1_estimate(runs_dir: Path, group: str, seeds: List[int]) -> Dict[str, Any]:
    rows = _offer_rows(runs_dir, group, seeds)
    fit = ols_cluster(rows)
    per_seed = {}
    for s in seeds:
        f = ols_cluster([r for r in rows if r[2] == s])
        per_seed[s] = round(f["beta"][1] * 100, 3) if f else None
    out: Dict[str, Any] = {"n_offers": len(rows), "per_seed_b_P_pct": per_seed,
                           "seeds_positive": f"{sum(1 for v in per_seed.values() if v is not None and v > 0)}/{len(seeds)}"}
    if fit is None:
        return {**out, "b_P_pct": None}
    b, se, G = fit["beta"][1], fit["se"][1], fit["G"]
    h = _t975(G - 1) * se if G > 1 else float("nan")
    out.update(b_P_pct=round(b * 100, 3), ci95_pct=[round((b - h) * 100, 3), round((b + h) * 100, 3)] if G > 1 else None,
               b_vacancy=round(fit["beta"][2], 4), clusters=G)
    return out


def _seed_bootstrap_diff(per_seed: Dict[str, Dict[int, List[float]]], seeds: List[int], n_boot: int = 2000) -> Dict[str, Any]:
    import random as _r
    rng = _r.Random(20261125)

    def diff(ss):
        p = [v for s in ss for v in per_seed["P"][s]]
        q = [v for s in ss for v in per_seed["S"][s]]
        return st.mean(p) - st.mean(q) if p and q else None
    point = diff(seeds)
    draws = sorted(d for d in (diff([rng.choice(seeds) for _ in seeds]) for _ in range(n_boot)) if d is not None)
    ci = [draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws)) - 1]] if draws else None
    return {"P_minus_S": round(point, 1) if point is not None else None, "ci95": [round(c, 1) for c in ci] if ci else None}


def evaluate_preregistered(runs_dir: Path, group: str, baseline_runs: Optional[Path] = None, baseline_group: str = "R") -> Dict[str, Any]:
    seeds = _paired_seeds(runs_dir, group)
    if not seeds:
        raise FileNotFoundError(f"No complete paired (N, S, P) seeds for group {group} in {runs_dir}")
    mon = {(sc, s): _load_monthly(runs_dir / f"{group}_{sc}_{s}") for sc in "NSP" for s in seeds}
    summ = {(sc, s): json.loads((runs_dir / f"{group}_{sc}_{s}" / "summary.json").read_text(encoding="utf-8")) for sc in "NSP" for s in seeds}
    out: Dict[str, Any] = {"group": group, "seeds": seeds, "criteria": PREREG_L, "results": {}}
    res = out["results"]

    # quality gate first: void runs make every other verdict provisional
    bad = {f"{sc}_{s}": round(summ[(sc, s)]["fallback_rate"], 4) for sc in "NSP" for s in seeds if summ[(sc, s)]["fallback_rate"] >= 0.02}
    res["quality"] = {"max_fallback_rate": round(max(summ[k]["fallback_rate"] for k in summ), 4), "void_runs": bad,
                      "verdict": "PASS" if not bad else "RERUN NEEDED"}

    # H1
    h1 = h1_estimate(runs_dir, group, seeds)
    aux = [mon[("P", s)][24]["rent_index_treated"] - mon[("S", s)][24]["rent_index_treated"] for s in seeds]
    m, hw = ci95(aux)
    h1["aux_P_minus_S_rent_index_M24"] = f"{m:+.2f} ± {hw:.2f}"
    ci = h1.get("ci95_pct")
    h1["verdict"] = ("SUPPORTED" if ci and h1["b_P_pct"] > 0 and ci[0] > 0 else "NOT SUPPORTED")
    res["H1"] = h1

    # H2
    per = {k: {"P": {}, "S": {}} for k in ("income", "cash")}
    for sc in "PS":
        for s in seeds:
            win = [mon[(sc, s)][k] for k in range(13, 25)]
            per["income"][sc][s] = [v for r in win for v in r["treated_move_in_incomes"]]
            per["cash"][sc][s] = [v for r in win for v in r["treated_move_in_cash"]]
    h2 = {k: _seed_bootstrap_diff(per[k], seeds) for k in per}
    h2["n_move_ins"] = {sc: sum(len(per["income"][sc][s]) for s in seeds) for sc in "PS"}
    pts = [h2[k]["P_minus_S"] for k in ("income", "cash")]
    cis = [h2[k]["ci95"] for k in ("income", "cash")]
    if all(p is not None and p > 0 for p in pts):
        h2["verdict"] = "SUPPORTED" if all(c and c[0] > 0 for c in cis) else "DIRECTIONAL (CI includes 0; low power)"
    else:
        h2["verdict"] = "NOT SUPPORTED"
    res["H2"] = h2

    # H3 and B need the rule baseline
    def h3_rates(sm):
        tr = [sm[s]["tight_renewals"] for s in sm if "tight_renewals" in sm[s]]
        n_t, n_keep = sum(x[0] for x in tr), sum(x[1] for x in tr)
        c, a = sum(sm[s]["counters_total"] for s in sm), sum(sm[s]["counter_accepts_total"] for s in sm)
        return (n_keep / n_t if n_t else None), (a / c if c else None), n_t, c
    l_keep, l_acc, l_nt, l_nc = h3_rates({s: summ[("N", s)] for s in seeds})
    h3: Dict[str, Any] = {"L_no_hike_when_tight": l_keep, "L_counter_accept": l_acc, "n_tight_quotes": l_nt, "n_counters": l_nc}
    if baseline_runs is not None:
        b_seeds = [s for s in seeds if (baseline_runs / f"{baseline_group}_N_{s}" / "summary.json").exists()]
        b_summ = {s: json.loads((baseline_runs / f"{baseline_group}_N_{s}" / "summary.json").read_text(encoding="utf-8")) for s in b_seeds}
        r_keep, r_acc, _, _ = h3_rates(b_summ)
        h3.update(R_no_hike_when_tight=r_keep, R_counter_accept=r_acc, baseline_seeds=b_seeds)
        if l_keep is None or r_keep is None:
            h3["verdict"] = "UNKNOWN (missing tight_renewals)"
        else:
            over_a = l_keep - r_keep > 0.20
            over_b = l_acc is not None and r_acc is not None and ((l_acc - r_acc > 0.20) or l_acc > 0.98)
            h3["verdict"] = "OVER-CONCESSIVE" if (over_a or over_b) else "NOT OVER-CONCESSIVE"
            if l_acc is None:
                h3["verdict"] += " (judged on (a) only: L tenants made no counter-offers)"
        last = max(mon[("N", seeds[0])])
        gaps = {}
        for key in ("rent_index_all", "rent_index_treated", "vacancy_all", "commute_all"):
            d = [mon[("N", s)][last][key] - _load_monthly(baseline_runs / f"{baseline_group}_N_{s}")[last][key] for s in b_seeds]
            mm, hh = ci95(d)
            gaps[key] = [round(mm, 3), round(hh, 3)]
        flag = abs(gaps["rent_index_all"][0]) > 3 or abs(gaps["rent_index_treated"][0]) > 3
        res["B"] = {"diff_mean_ci95": gaps, "verdict": "CAVEAT REQUIRED (rent gap > 3 pts)" if flag else "OK"}
    else:
        h3["verdict"] = "UNKNOWN (pass --baseline-runs)"
        res["B"] = {"verdict": "UNKNOWN (pass --baseline-runs)"}
    for k in ("L_no_hike_when_tight", "L_counter_accept", "R_no_hike_when_tight", "R_counter_accept"):
        if isinstance(h3.get(k), float):
            h3[k] = round(h3[k], 3)
    res["H3"] = h3
    res["exploratory_persona"] = persona_exploratory(runs_dir, group, seeds)
    return out


def crosscheck(local_runs: Path, cloud_runs: Path, group: str = "L") -> Dict[str, Any]:
    c_seeds = _paired_seeds(cloud_runs, group, scenarios=("S", "P"))
    l_seeds = _paired_seeds(local_runs, group, scenarios=("S", "P"))
    common = sorted(set(c_seeds) & set(l_seeds))
    if not common:
        raise FileNotFoundError("cross-check needs at least one seed present (S and P) in both run directories")
    s = common[0]
    cloud = h1_estimate(cloud_runs, group, [s])
    local_same = h1_estimate(local_runs, group, [s])
    local_all = h1_estimate(local_runs, group, l_seeds)
    bc, bl = cloud.get("b_P_pct"), local_same.get("b_P_pct")
    verdict = "UNKNOWN" if bc is None or bl is None else ("ROBUST" if (bc > 0) == (bl > 0) else "MODEL-DEPENDENT")
    return {"seed": s, "cloud_b_P_pct": bc, "local_same_seed_b_P_pct": bl, "local_pooled_b_P_pct": local_all.get("b_P_pct"),
            "local_pooled_ci95_pct": local_all.get("ci95_pct"), "n_offers_cloud": cloud["n_offers"], "verdict": verdict}


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze Lease Day v0.7 simulation outputs")
    ap.add_argument("--runs", type=str, default="rental_game/runs")
    ap.add_argument("--group", choices=["R", "L", "M"], default="R")
    ap.add_argument("--replay", action="store_true", help="Print sample landlord & tenant timeline replay")
    ap.add_argument("--validate", action="store_true", help="Run pre-registered Level 1-3 validation checks")
    ap.add_argument("--baseline-runs", type=str, default=None, help="Dir holding R_N_* runs for the LLM-bias comparison")
    ap.add_argument("--table", action="store_true", help="Print Markdown table of seed-paired differences with 95% CI")
    ap.add_argument("--prereg", action="store_true", help="Evaluate pre-registered H1-H3 / quality / bias criteria (A5)")
    ap.add_argument("--crosscheck", type=str, default=None, help="Cloud-model run dir to compare H1 sign against --runs")
    args = ap.parse_args()

    if args.crosscheck:
        print(json.dumps(crosscheck(Path(args.runs), Path(args.crosscheck), args.group), ensure_ascii=False, indent=2))
        return
    if args.prereg:
        res = evaluate_preregistered(Path(args.runs), args.group, Path(args.baseline_runs) if args.baseline_runs else None)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if args.table:
        print(paired_table(Path(args.runs), args.group))
        return

    if args.validate:
        res = validate_group(Path(args.runs), args.group, Path(args.baseline_runs) if args.baseline_runs else None)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    res = analyze_group(Path(args.runs), args.group)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if args.replay:
        print_sample_replay(Path(args.runs), args.group)


if __name__ == "__main__":
    main()
