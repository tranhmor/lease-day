"""Automated acceptance & health test suite for Lease Day v0.7 (§9 Criteria 1-6 + structural checks).

Usage:
    python3 -m prototype_v07.check_v07
"""
import json
import multiprocessing as mp
from pathlib import Path
import statistics as st
import tempfile

from .agents.llm import PROMPTS_DIR, DiskCache, LLMLandlord, LLMTenant, MockLLMBackend, _strip_private
from .agents.rule import RuleLandlord, RuleTenant
from .diagnose import run_diagnostics
from .lease_day_v07 import Config, GameV07, replay_agent


def _run_compat(seed: int):
    cfg = Config(
        scenario="N",
        seed=seed,
        n_rooms=1200,
        months=60,
        line_opens=24,
        compat_v06=True,
        record_decisions=False,
    )
    return GameV07(cfg).run()


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


LINE_KEYS = {"announcement", "contract_months_after_open", "post_open_min", "already_open", "affects_this_zone", "lease_months_after_open"}
FORBIDDEN_KEYS = {"treated", "group", "monthly_equiv_vacancy_loss", "one_month_vacancy_loss", "zone_vacancy_smooth", "floor_rent", "cell_vacancy", "demand_signal"}
ALL_DECISIONS = {"renewal_offer", "price_vacant", "answer_counter", "pick_applicant", "at_expiry", "search"}
# System prompts are sent in every scenario (N/S/P alike), so they must not mention the line, the design or the hypotheses.
TEMPLATE_BANNED = ("公告", "新线", "快线", "开通", "Z05", "Z11", "受益", "提前", "预期", "涨价", "情景", "实验", "假设")


def _check_template_words() -> list:
    issues = []
    for f in sorted(PROMPTS_DIR.glob("*.txt")):
        text = f.read_text(encoding="utf-8")
        hits = [w for w in TEMPLATE_BANNED if w in text]
        if hits:
            issues.append(f"template {f.name}: banned words {hits}")
    return issues


def _line_info_present(payload) -> bool:
    """Key-level: any line-related key at all (even empty/zero) counts as a trace."""
    if "快线" in json.dumps(payload, ensure_ascii=False):
        return True
    return any(k in LINE_KEYS for k, _ in _walk_keys(payload))


def _check_prompt_leakage(seed: int = 0, months: int = 30):
    """N never sees line info; S sees none before opening; S and P get the same post-opening fact; no design labels."""
    issues = []
    with tempfile.TemporaryDirectory() as tmp:
        cache = DiskCache(str(Path(tmp) / "c.sqlite"))
        b = MockLLMBackend()
        ll, tp = LLMLandlord(b, cache=cache), LLMTenant(b, cache=cache)
        # Mock-LLM policies plus rule policies (rule tenants counter more often -> covers answer_counter).
        # The check inspects the logged contexts, which are built by the engine independent of policy.
        games = {}
        for tag, (lp, tpol) in {"mock": (ll, tp), "rule": (RuleLandlord(), RuleTenant())}.items():
            warm = GameV07(Config(scenario="N", seed=seed, months=months), lp, tpol)
            warm.run_until(warm.cfg.announce_month)
            snap = warm.export_snapshot()
            for sc in "NSP":
                games[(sc, tag)] = GameV07.from_snapshot(snap, scenario=sc, landlord_policy=lp, tenant_policy=tpol)
                games[(sc, tag)].run()
        cache.close()
    opens_1idx = Config().line_opens + 1
    post_texts = {}
    seen_post = {"S": set(), "P": set()}
    for (sc, tag), g in games.items():
        for rec in g.decision_records:
            if sc in seen_post and rec["month"] >= opens_1idx:
                seen_post[sc].add(rec["decision"])
            payload = _strip_private(rec["inputs"], rec["decision"])
            where = f"{sc}/{tag} m{rec['month']} {rec['decision']}"
            for k, _ in _walk_keys(payload):
                if k in FORBIDDEN_KEYS:
                    issues.append(f"{where}: design/rule-internal key '{k}'")
            if rec["agent_type"] == "tenant" and any(k in ("affects_this_zone", "expected_time_saving_min") for k, _ in _walk_keys(payload.get("announcement") or {})):
                issues.append(f"{where}: zone-specific announcement field shown to tenant")
            has_line = _line_info_present(payload)
            if sc == "N" and has_line:
                issues.append(f"{where}: line info in no-line scenario")
            if sc == "S" and rec["month"] < opens_1idx and has_line:
                issues.append(f"{where}: line info before opening in S")
            if sc == "P" and rec["month"] <= Config().announce_month and has_line:
                issues.append(f"{where}: line info before announcement in P")
            if sc in "SP" and rec["month"] >= opens_1idx:
                ann = payload.get("announcement")
                if not (ann and ann.get("already_open")):
                    issues.append(f"{where}: missing opened-line fact")
                if ann:
                    post_texts.setdefault(sc, set()).add(ann["text"])
    if post_texts.get("S") != post_texts.get("P"):
        issues.append(f"post-opening text differs S vs P: {post_texts}")
    for sc, seen in seen_post.items():
        if seen != ALL_DECISIONS:
            issues.append(f"{sc}: post-opening coverage incomplete, saw only {sorted(seen)}")
    return issues


def _check_log_idempotent() -> list:
    """Re-running into the same --out directory (shared warm-up and plain) must not duplicate lines."""
    import subprocess
    import sys
    issues = []
    with tempfile.TemporaryDirectory() as tmp:
        for extra in ([], ["--no-shared-warmup"]):
            out = str(Path(tmp) / ("plain" if extra else "shared"))
            cmd = [sys.executable, "-m", "prototype_v07.run_v07", "--group", "R", "--seeds", "1", "--months", "18", "--out", out] + extra
            sizes = []
            for _ in range(2):
                subprocess.run(cmd, check=True, capture_output=True, cwd=str(Path(__file__).resolve().parent.parent))
                d = Path(out) / "R_P_0"
                sizes.append(tuple(sum(1 for _ in (d / f).open(encoding="utf-8")) for f in ("decisions.jsonl", "monthly.jsonl")))
                months = [json.loads(l)["month"] for l in (d / "monthly.jsonl").open(encoding="utf-8")]
                if len(months) != len(set(months)):
                    issues.append(f"{'plain' if extra else 'shared'}: duplicate months in monthly.jsonl")
            if sizes[0] != sizes[1]:
                issues.append(f"{'plain' if extra else 'shared'}: rerun changed line counts {sizes}")
    # Same object, two run_until() calls into one log_dir: append without re-flushing
    with tempfile.TemporaryDirectory() as tmp:
        g = GameV07(Config(scenario="P", seed=0, months=18, log_dir=tmp))
        g.run_until(12)
        g.run_until(18)
        months = [json.loads(l)["month"] for l in (Path(tmp) / "monthly.jsonl").open(encoding="utf-8")]
        if months != list(range(1, 19)):
            issues.append(f"split run_until: months {months[:3]}..{months[-3:]} (n={len(months)})")
        # Re-running with record_decisions=False must not write or keep decisions.jsonl
        g_nodec = GameV07(Config(scenario="P", seed=0, months=18, log_dir=tmp, record_decisions=False))
        g_nodec.run()
        if (Path(tmp) / "decisions.jsonl").exists():
            issues.append("record_decisions=False unexpectedly created or kept decisions.jsonl")
        if sum(1 for _ in (Path(tmp) / "monthly.jsonl").open(encoding="utf-8")) != 18:
            issues.append("record_decisions=False monthly.jsonl line count != 18")
    return issues


def _check_backoff() -> list:
    """Transport errors (429/5xx/timeout/socket/HTTPException) are retried with backoff; 4xx client errors are not."""
    import http.client
    import io
    import socket
    import urllib.error
    from .agents.llm import OpenAICompatBackend
    issues = []
    b = OpenAICompatBackend(api_key="test", base_url="http://localhost", model="m")
    waits = []
    b.sleep = waits.append
    ok = {"choices": [{"message": {"content": "{}"}}]}

    def flaky(errors):
        seq = list(errors)

        def send():
            if seq:
                e = seq.pop(0)
                if isinstance(e, int):
                    raise urllib.error.HTTPError("u", e, "x", {}, io.BytesIO())
                raise e
            return ok
        return send

    try:
        if b._send_with_backoff(flaky([429, 503, TimeoutError()])) != ok or waits != [1.0, 2.0, 4.0]:
            issues.append(f"3 transient errors should recover with waits 1/2/4, got {waits}")
    except RuntimeError as e:
        issues.append(f"3 transient errors should recover, raised {e}")
    waits.clear()
    try:
        if b._send_with_backoff(flaky([socket.timeout("read timeout"), http.client.RemoteDisconnected("closed")])) != ok or waits != [1.0, 2.0]:
            issues.append(f"socket.timeout / RemoteDisconnected should recover with waits 1/2, got {waits}")
    except RuntimeError as e:
        issues.append(f"socket.timeout / RemoteDisconnected should recover, raised {e}")
    waits.clear()
    try:
        b._send_with_backoff(flaky([429, 429, 429, 429]))
        issues.append("4 consecutive 429s should raise")
    except RuntimeError:
        pass
    waits.clear()
    try:
        b._send_with_backoff(flaky([400]))
        issues.append("HTTP 400 should raise")
    except RuntimeError:
        if waits:
            issues.append("HTTP 400 must not be retried")
    return issues


def _check_thinking_switch() -> list:
    """Hybrid-reasoning models must get the right 'thinking off' fields per serving stack."""
    from .agents.llm import THINKING_OFF_FIELDS, resolve_thinking_style
    issues = []
    cases = {
        ("auto", "http://100.116.15.70:11434/v1", "qwen3.5:9b"): "ollama",
        ("auto", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3.5-flash"): "dashscope",
        ("auto", "https://api.deepseek.com", "deepseek-chat"): "deepseek",
        ("auto", "http://localhost:8000/v1", "Qwen/Qwen3.5-9B"): "none",
        ("vllm", "http://localhost:8000/v1", "Qwen/Qwen3.5-9B"): "vllm",
    }
    for args, want in cases.items():
        got = resolve_thinking_style(*args)
        if got != want:
            issues.append(f"{args} -> {got}, expected {want}")
    if THINKING_OFF_FIELDS["ollama"].get("reasoning_effort") != "none":
        issues.append("ollama must send reasoning_effort=none (its /v1 ignores think=false)")
    try:
        resolve_thinking_style("typo", "http://x", "m")
        issues.append("unknown LLM_THINKING value must raise")
    except ValueError:
        pass
    return issues


def _check_common_external_events(seeds=(0, 1)) -> list:
    """A2: N/S/P forked from one warm-up must see identical newcomers each month, and any tenant present in two
    branches in the same month must get the same churn draw (R and mock-L back ends)."""
    errs = []
    for kind in ("rule", "mock"):
        for seed in seeds:
            b = MockLLMBackend() if kind == "mock" else None
            ll, tp = (LLMLandlord(b), LLMTenant(b)) if b else (None, None)
            warm = GameV07(Config(scenario="N", seed=seed, record_decisions=False), ll, tp)
            warm.run_until(12)
            snap = warm.export_snapshot()
            logs = {}
            for sc in "NSP":
                g = GameV07.from_snapshot(snap, scenario=sc, landlord_policy=ll, tenant_policy=tp)
                g.run()
                logs[sc] = g.external_log
            for sc in "SP":
                if [e["newcomers"] for e in logs[sc]] != [e["newcomers"] for e in logs["N"]]:
                    errs.append(f"{kind} seed={seed}: newcomers differ N vs {sc}")
            for a, c in (("N", "S"), ("N", "P"), ("S", "P")):
                for ea, ec in zip(logs[a], logs[c]):
                    both = set(ea["present"]) & set(ec["present"])
                    if set(ea["leavers"]) & both != set(ec["leavers"]) & both:
                        errs.append(f"{kind} seed={seed} M{ea['month']}: churn differs {a} vs {c} on common tenants")
                        break
    return errs


def _check_prereg_estimators() -> list:
    """A5: cluster-robust OLS reproduces a hand-built case; H1-H3/B pipeline runs end to end on a tiny mock L run."""
    import random as _r
    from .analyze_v07 import PREREG_L, evaluate_preregistered, ols_cluster
    errs = []
    if set(PREREG_L) != {"H1", "H2", "H3", "quality", "B", "crosscheck"}:
        errs.append("PREREG_L keys changed")
    # Exact fit check: y = 1 + 2*P (no noise) -> beta (1, 2, 0), se ~ 0
    rows = [(1.0 + 2.0 * p, [1.0, p, v], g) for g in range(4) for p in (0.0, 1.0) for v in (0.01, 0.05, 0.09)]
    f = ols_cluster(rows)
    if f is None or abs(f["beta"][1] - 2.0) > 1e-9 or f["se"][1] > 1e-9:
        errs.append(f"ols_cluster exact-fit failed: {f}")
    # Cluster shock check: a seed-level shock correlated with P must widen the SE vs naive iid
    rng = _r.Random(3)
    rows = []
    for g in range(5):
        shock = rng.gauss(0, 0.03)
        for _ in range(40):
            p = 1.0 if rng.random() < 0.5 else 0.0
            rows.append((0.02 * p + shock * p + rng.gauss(0, 0.005), [1.0, p, rng.random() * 0.1], g))
    f = ols_cluster(rows)
    f_iid = ols_cluster([(y, x, i) for i, (y, x, _) in enumerate(rows)])
    if not (f and f_iid and f["se"][1] > 2 * f_iid["se"][1]):
        errs.append("cluster SE not wider than iid SE under seed-level shocks")
    with tempfile.TemporaryDirectory() as tmp:
        b = MockLLMBackend()
        ll, tp = LLMLandlord(b), LLMTenant(b)
        for s in (0, 1):
            warm = GameV07(Config(scenario="N", seed=s), ll, tp)
            warm.run_until(12)
            snap = warm.export_snapshot()
            for sc in "NSP":
                GameV07.from_snapshot(snap, scenario=sc, landlord_policy=ll, tenant_policy=tp, log_dir=f"{tmp}/L_{sc}_{s}").run()
                GameV07.from_snapshot(snap, scenario=sc, log_dir=f"{tmp}/base/R_{sc}_{s}").run()
        out = evaluate_preregistered(Path(tmp), "L", Path(tmp) / "base")
        for k in ("quality", "H1", "H2", "H3", "B"):
            v = out["results"].get(k, {}).get("verdict", "")
            if not v or v.startswith("UNKNOWN"):
                errs.append(f"{k} verdict missing/unknown: {v}")
    return errs


def _check_wording_formats() -> list:
    """Every system prompt used anywhere (templates + diagnostic overrides) must state the JSON keys."""
    from .diagnose import LANDLORD_WORDINGS, TENANT_WORDINGS
    from .agents.llm import PROMPTS_DIR
    issues = []
    required = {
        "landlord": ['"rent"', '"reason"'],
        "tenant": ['"action"', '"mode"', '"rent"', '"if_rejected"', '"apply"', '"reason"'],
    }
    for kind, wordings in (("landlord", LANDLORD_WORDINGS), ("tenant", TENANT_WORDINGS)):
        for i, w in enumerate(wordings):
            if w is None:
                continue
            missing = [k for k in required[kind] if k not in w]
            if missing:
                issues.append(f"{kind} wording {i} missing keys {missing}")
    for p in sorted(PROMPTS_DIR.glob("*.txt")):
        if "输出格式" not in p.read_text(encoding="utf-8"):
            issues.append(f"{p.name}: no 输出格式 block")
    return issues


def _run_v07_baseline(seed: int):
    cfg = Config(scenario="N", seed=seed, n_rooms=240, months=36, record_decisions=True)
    g = GameV07(cfg)
    out = g.run()
    # Extra health stats: treated vacancy, renewal vs vacate sign, pool sizes
    tr_rooms = [r for r in g.rooms if r.zone in cfg.treated_zones]
    out["end_vac_tr"] = sum(r.tenant_id is None for r in tr_rooms) / len(tr_rooms)
    ren_hikes, vac_chgs = [], []
    for rec in g.decision_records:
        if 13 <= rec["month"] <= 24 and rec["agent_type"] == "landlord" and rec["inputs"].get("zone") in ("Z05", "Z11"):
            if rec["decision"] == "renewal_offer":
                cur = rec["inputs"]["current_rent"]
                ren_hikes.append((rec["output"]["rent"] - cur) / cur)
            elif rec["decision"] == "price_vacant" and rec["inputs"].get("vacant_for") == 0:
                cur = rec["inputs"]["current_rent"]
                vac_chgs.append((rec["output"]["rent"] - cur) / cur)
    out["tr_ren_chg"] = st.mean(ren_hikes) if ren_hikes else 0.0
    out["tr_vac_chg"] = st.mean(vac_chgs) if vac_chgs else 0.0
    # Candidate pool sizes seen by tenants M13-M24
    pools = {"low": [], "mid": [], "high": []}
    for rec in g.decision_records:
        if 13 <= rec["month"] <= 24 and rec["agent_type"] == "tenant":
            pools[rec["inputs"]["tenant"]["group"]].append(len(rec["inputs"]["candidates"]))
    out["pools"] = {k: (st.mean(v) if v else 0.0) for k, v in pools.items()}
    return out


def main() -> None:
    passed = {}

    # ------------------------------------------------------------------
    # Criterion 1: R group P and S are bit-for-bit identical per seed
    # ------------------------------------------------------------------
    print("=== [Check 1] R group: P == S identically across 5 paired seeds ===")
    c1_ok = True
    for s in range(5):
        warm = GameV07(Config(scenario="N", seed=s, record_decisions=False))
        warm.run_until(12)
        snap = warm.export_snapshot()
        r_s = GameV07.from_snapshot(snap, scenario="S").run()
        r_p = GameV07.from_snapshot(snap, scenario="P").run()
        keys = ("commute", "vacant", "rent_tr_m24", "rent_tr_m36", "moves", "left", "tr_move_ins_m13_24")
        for k in keys:
            if r_s[k] != r_p[k]:
                print(f"  MISMATCH seed={s} key={k}: S={r_s[k]} vs P={r_p[k]}")
                c1_ok = False
    passed["1_R_P_equals_S"] = c1_ok
    print(f"  Result: {'PASS' if c1_ok else 'FAIL'}")

    # ------------------------------------------------------------------
    # Criterion 2: v0.6 compat regression (1,200 rooms, 60 months, 8 seeds)
    # Target from check_v06.py 8: commute 48.2 min, vacancy 0.068 (<1% rel error)
    # ------------------------------------------------------------------
    print("\n=== [Check 2] v0.6 compat regression (1,200 rooms, 60 mo, 8 seeds) ===")
    with mp.Pool(4) as pool:
        compat_rs = pool.map(_run_compat, range(8))
    c_comm = st.mean(r["commute"] for r in compat_rs)
    c_vac = st.mean(r["vacant"] for r in compat_rs)
    c_seated = st.mean(r["seated"] for r in compat_rs)
    comm_err = abs(c_comm - 48.2) / 48.2
    vac_err = abs(c_vac - 0.068) / 0.068
    c2_ok = (comm_err <= 0.01) and (vac_err <= 0.015)
    passed["2_v06_compat_regression"] = c2_ok
    print(f"  seated={c_seated:.0f}, commute={c_comm:.2f} (ref 48.2, err={comm_err:.2%}), vacancy={c_vac:.4f} (ref 0.068, err={vac_err:.2%}) -> {'PASS' if c2_ok else 'FAIL'}")

    # ------------------------------------------------------------------
    # Criterion 3 + Health checks: 240-room v0.7 R-N baseline (20 seeds)
    # ------------------------------------------------------------------
    print("\n=== [Check 3] v0.7 240-room R-N baseline & health checks (20 seeds) ===")
    with mp.Pool(4) as pool:
        v07_rs = pool.map(_run_v07_baseline, range(20))
    comm_240 = st.mean(r["commute"] for r in v07_rs)
    vac_240 = st.mean(r["vacant"] for r in v07_rs)
    vac_tr = st.mean(r["end_vac_tr"] for r in v07_rs)
    tr_vacs = [r["tr_vacates_m13_24"] for r in v07_rs]
    tr_ren = st.mean(r["tr_ren_chg"] for r in v07_rs)
    tr_vac_chg = st.mean(r["tr_vac_chg"] for r in v07_rs)
    multi_app = st.mean(r["multi_app_total"] for r in v07_rs)
    counters = st.mean(r["counters_total"] for r in v07_rs)
    pools_avg = {g: st.mean(r["pools"][g] for r in v07_rs) for g in ("low", "mid", "high")}
    # Verify landlord separation (zero landlords own both treated & control!)
    g0 = GameV07(Config(scenario="N", seed=0))
    cross_ll = sum(
        1 for ll in g0.landlords.values()
        if any(z in ("Z05", "Z11") for z in ll.zones) and any(z not in ("Z05", "Z11") for z in ll.zones)
    )
    c3_ok = (45.0 <= comm_240 <= 52.0) and (0.04 <= vac_240 <= 0.10) and (min(tr_vacs) >= 8) and (cross_ll == 0) and (tr_vac_chg >= 0.0)
    passed["3_v07_240_baseline_and_health"] = c3_ok
    print(f"  commute={comm_240:.2f}m [45-52] | vac_all={vac_240:.2%} [4%-10%] | vac_treated={vac_tr:.2%}")
    print(f"  M13-24 Z05+Z11 vacates: mean={st.mean(tr_vacs):.1f}, min={min(tr_vacs)} (>=8 required)")
    print(f"  Z05+Z11 M13-24 rent change: renewal={tr_ren:+.2%}, vacate={tr_vac_chg:+.2%} (no more -3.11% small-cell crash!)")
    print(f"  40 landlords treated/control overlap: {cross_ll} | counters/run={counters:.1f} | multi_app/run={multi_app:.1f}")
    print(f"  Avg candidate pool seen M13-24 (low/mid/high): {pools_avg['low']:.2f} / {pools_avg['mid']:.2f} / {pools_avg['high']:.2f}")
    print(f"  Result: {'PASS' if c3_ok else 'FAIL'}")

    print("\n=== [Check 3b] Steady state before the announcement (R-N, 20 seeds) ===")
    steady = []
    for s in range(20):
        g = GameV07(Config(scenario="N", seed=s, record_decisions=False))
        g.run()
        m = {r["month"]: r for r in g.monthly_records}
        steady.append((m[1]["occupied"],
                       st.mean(m[k]["vacancy_all"] for k in range(10, 13)),
                       st.mean(m[k]["vacancy_all"] for k in range(25, 37))))
    occ_m1 = st.mean(x[0] for x in steady) / Config().n_rooms
    gap_pp = abs(st.mean(x[1] for x in steady) - st.mean(x[2] for x in steady)) * 100
    c3b_ok = occ_m1 >= 0.90 and gap_pp < 2.0
    passed["3b_steady_state_pre_announcement"] = c3b_ok
    print(f"  M1 occupancy={occ_m1:.1%} (>=90%) | mean vacancy M10-12 vs M25-36 gap={gap_pp:.2f} pp (<2) -> {'PASS' if c3b_ok else 'FAIL'}")

    # ------------------------------------------------------------------
    # Criterion 4, 5, 6: Mock-LLM diagnostics, cache determinism, JSONL replay
    # ------------------------------------------------------------------
    print("\n=== [Check 4-6] Mock-LLM diagnostics, cache reproducibility & JSONL replay ===")
    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        cache = DiskCache(str(tdir / "cache.sqlite"))
        # Criterion 4: diagnostics legal rate >= 98% & directionality
        diag = run_diagnostics(MockLLMBackend(inject_bad_json_rate=0.05), cache, samples_per_cell=3)
        c4_ok = diag["pass_gate"]
        passed["4_mock_diagnostics"] = c4_ok
        print(f"  [Check 4] diag legal_rate={diag['legal_output_rate']:.2%} (with 5% injected bad JSON -> retry recovery), vac_ok={diag['landlord_direction_vac_ok']} | reported only: ann_hike_gt_noann={diag['reported_only']['landlord_ann_hike_gt_noann_all_wordings']} -> {'PASS' if c4_ok else 'FAIL'}")

        # Criterion 5: L group cached replay exact reproducibility + zero new backend calls on rerun
        b1 = MockLLMBackend()
        ll1, t1 = LLMLandlord(b1, cache=cache), LLMTenant(b1, cache=cache)
        out1 = GameV07(Config(scenario="P", seed=0, months=24, log_dir=str(tdir / "run1")), ll1, t1).run()
        calls_first = b1.call_count

        b2 = MockLLMBackend()
        ll2, t2 = LLMLandlord(b2, cache=cache), LLMTenant(b2, cache=cache)
        out2 = GameV07(Config(scenario="P", seed=0, months=24, log_dir=str(tdir / "run2")), ll2, t2).run()
        calls_second = b2.call_count
        cache.close()

        c5_ok = (
            out1["rent_tr_m24"] == out2["rent_tr_m24"]
            and out1["tr_move_ins_m13_24"] == out2["tr_move_ins_m13_24"]
            and calls_second == 0
            and out1["fallback_rate"] < 0.02
        )
        passed["5_cache_reproducibility"] = c5_ok
        print(f"  [Check 5] run1 calls={calls_first}, run2 calls={calls_second} (100% cache hit), M24 tr_rent={out1['rent_tr_m24']:.2f}=={out2['rent_tr_m24']:.2f}, fallback={out1['fallback_rate']:.2%} -> {'PASS' if c5_ok else 'FAIL'}")

        # Criterion 6: Replay any landlord and tenant from decisions.jsonl
        dec_path = str(tdir / "run1" / "decisions.jsonl")
        ll_counts, t_counts = {}, {}
        with open(dec_path, "r", encoding="utf-8") as fp:
            for line in fp:
                r = json.loads(line)
                if r["agent_type"] == "landlord":
                    ll_counts[r["agent_id"]] = ll_counts.get(r["agent_id"], 0) + 1
                else:
                    t_counts[r["agent_id"]] = t_counts.get(r["agent_id"], 0) + 1
        sample_ll = max(ll_counts, key=ll_counts.get)
        sample_t = max(t_counts, key=t_counts.get)
        ll_events = replay_agent(dec_path, "landlord", sample_ll)
        t_events = replay_agent(dec_path, "tenant", sample_t)
        c6_ok = (len(ll_events) >= 2) and (len(t_events) >= 2)
        passed["6_jsonl_replay"] = c6_ok
        print(f"  [Check 6] replay landlord#{sample_ll}: {len(ll_events)} events, tenant#{sample_t}: {len(t_events)} events (unique logged: {len(ll_counts)} landlords, {len(t_counts)} tenants) -> {'PASS' if c6_ok else 'FAIL'}")

    # ------------------------------------------------------------------
    # Criterion 7: prompt-level information hygiene (what the LLM actually sees)
    # ------------------------------------------------------------------
    print("\n=== [Check 7] Prompt leakage: scenario info & design labels in LLM payloads ===")
    c7_issues = _check_template_words() + _check_prompt_leakage()
    passed["7_prompt_leakage"] = not c7_issues
    for msg in c7_issues[:10]:
        print(f"  LEAK: {msg}")
    print(f"  Result: {'PASS' if not c7_issues else 'FAIL'}")

    print("\n=== [Check 8] Engineering: log idempotence, API backoff, wording JSON formats, thinking switch, common external events, pre-registered estimators ===")
    for name, fn in (("8a_log_idempotent", _check_log_idempotent), ("8b_api_backoff", _check_backoff), ("8c_wording_formats", _check_wording_formats), ("8d_thinking_switch", _check_thinking_switch), ("8e_common_external_events", _check_common_external_events), ("8f_prereg_estimators", _check_prereg_estimators)):
        errs = fn()
        passed[name] = not errs
        for msg in errs[:5]:
            print(f"  {name} FAIL: {msg}")
        print(f"  {name}: {'PASS' if not errs else 'FAIL'}")

    print("\n=== SUMMARY ===")
    for k, v in passed.items():
        print(f"  {k:32s}: {'PASS' if v else 'FAIL'}")
    if not all(passed.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
