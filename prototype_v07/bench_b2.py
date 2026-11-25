"""B2: live-backend stability and throughput check (run before freezing prompts).

Prompts are real payloads: a rule-policy P run (seed 0) is replayed and its logged contexts are rendered exactly as
the LLM agents would send them, stratified by decision type (always including the longest tenant prompts).

Checks
1. Repeat determinism: each prompt sent `--repeats` times sequentially -> identical raw text / identical decision.
2. Concurrency invariance: the same prompts sent with `--parallel` threads -> same output as sequential.
   (Ollama batches concurrent requests; batched kernels can change floating-point results even at temperature 0.)
3. Truncation: usage.prompt_tokens of the longest prompts vs the server context window (no silent front-cut).
4. Validity: share of first-attempt outputs accepted by the validators (no retry, no fallback).
5. Throughput: wall time at concurrency 1 and `--parallel`; projection for the L-group call volume.

Usage:
    python3 -m prototype_v07.bench_b2 --per-decision 8 --repeats 3 --parallel 4 --out runs_b2/b2_report.json
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics as st
import time
from typing import Any, Dict, List, Tuple
import urllib.request

from .agents.base import (
    validate_answer_counter,
    validate_at_expiry,
    validate_pick_applicant,
    validate_price_vacant,
    validate_renewal_offer,
    validate_search,
)
from .agents.llm import PROMPTS_DIR, THINKING_OFF_FIELDS, OpenAICompatBackend, _extract_json, _strip_private, render_user_prompt
from .lease_day_v07 import Config, GameV07

TEMPLATE = {
    "renewal_offer": ("landlord_renewal_offer.txt", validate_renewal_offer),
    "price_vacant": ("landlord_price_vacant.txt", validate_price_vacant),
    "answer_counter": ("landlord_answer_counter.txt", validate_answer_counter),
    "pick_applicant": ("landlord_pick_applicant.txt", validate_pick_applicant),
    "at_expiry": ("tenant_at_expiry.txt", validate_at_expiry),
    "search": ("tenant_search.txt", validate_search),
}
# Measured L-group volume (5 seeds x N/S/P, see upgrade plan §5.5 / summary): ~24k calls
L_GROUP_CALLS = 24000


def sample_prompts(per_decision: int, seed: int = 0) -> List[Dict[str, Any]]:
    warm = GameV07(Config(scenario="N", seed=seed))
    warm.run_until(12)
    g = GameV07.from_snapshot(warm.export_snapshot(), scenario="P")
    g.run()
    by: Dict[str, List[Dict[str, Any]]] = {}
    for r in g.decision_records:
        if r["month"] >= 13:
            by.setdefault(r["decision"], []).append(r)
    out = []
    for dec, recs in sorted(by.items()):
        # Spread over announcement window and post-opening; for tenants force-include the 2 longest payloads.
        rendered = [(render_user_prompt(_strip_private(r["inputs"], dec)), r) for r in recs]
        picks: List[Tuple[str, Dict[str, Any]]] = []
        if dec in ("at_expiry", "search"):
            picks += sorted(rendered, key=lambda x: -len(x[0]))[:2]
        step = max(1, len(rendered) // max(1, per_decision - len(picks)))
        for x in rendered[::step]:
            if len(picks) >= per_decision:
                break
            if all(x[0] != p[0] for p in picks):
                picks.append(x)
        for up, r in picks:
            ctx = dict(r["inputs"])
            out.append({"decision": dec, "month": r["month"], "user": up, "ctx": ctx})
    return out


def call(b: OpenAICompatBackend, system: str, user: str) -> Dict[str, Any]:
    body = {
        "model": b.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": b.temperature,
        "max_tokens": b.max_tokens,
        "response_format": {"type": "json_object"},
        "stream": False,
        **THINKING_OFF_FIELDS[b.thinking_style],
    }
    req = urllib.request.Request(
        b.base_url + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {b.api_key}"},
    )
    opener = urllib.request.build_opener() if b.use_proxy else urllib.request.build_opener(urllib.request.ProxyHandler({}))
    t0 = time.time()
    data = b._send_with_backoff(lambda: b._open_json(opener, req))
    u = data.get("usage", {})
    return {
        "raw": data["choices"][0]["message"]["content"],
        "finish": data["choices"][0].get("finish_reason"),
        "prompt_tokens": int(u.get("prompt_tokens", 0)),
        "completion_tokens": int(u.get("completion_tokens", 0)),
        "sec": time.time() - t0,
    }


def decision_key(dec: str, parsed: Any, ctx: Dict[str, Any]) -> Any:
    """Validated decision with the free-text reason removed (what the simulation actually uses)."""
    if parsed is None:
        return None
    _, validator = TEMPLATE[dec]
    v, err = validator(parsed, ctx)
    if v is None:
        return f"INVALID:{err}"
    return json.dumps({k: v[k] for k in sorted(v) if k != "reason"}, ensure_ascii=False, sort_keys=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--per-decision", type=int, default=8)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--ctx-window", type=int, default=8192)
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    b = OpenAICompatBackend()
    systems = {d: (PROMPTS_DIR / f).read_text(encoding="utf-8").strip() for d, (f, _) in TEMPLATE.items()}
    items = sample_prompts(args.per_decision)
    for it in items:
        it["ctx"]["_rng"] = None  # validators never use it; rule fallback is not exercised here
    print(f"model={b.model} endpoint={b.base_url} prompts={len(items)} repeats={args.repeats} parallel={args.parallel}", flush=True)

    # warm-up (model load) excluded from timing
    call(b, systems["renewal_offer"], items[0]["user"])

    # 1 + 5a: sequential repeats
    seq: List[List[Dict[str, Any]]] = [[] for _ in items]
    t0 = time.time()
    for r in range(args.repeats):
        for i, it in enumerate(items):
            seq[i].append(call(b, systems[it["decision"]], it["user"]))
        print(f"  sequential pass {r + 1}/{args.repeats} done ({time.time() - t0:.0f}s)", flush=True)
    seq_wall = (time.time() - t0) / args.repeats

    # 2 + 5b: concurrent pass (each prompt once, submitted in a shuffled-by-length order so batches mix sizes)
    order = sorted(range(len(items)), key=lambda i: (i * 7919) % len(items))
    par: Dict[int, Dict[str, Any]] = {}
    t0 = time.time()
    with ThreadPoolExecutor(args.parallel) as ex:
        futs = {i: ex.submit(call, b, systems[items[i]["decision"]], items[i]["user"]) for i in order}
        for i, f in futs.items():
            par[i] = f.result()
    par_wall = time.time() - t0
    print(f"  concurrent pass done ({par_wall:.0f}s)", flush=True)

    rows = []
    for i, it in enumerate(items):
        d = it["decision"]
        raws = [x["raw"] for x in seq[i]]
        keys = [decision_key(d, _extract_json(x), it["ctx"]) for x in raws]
        pkey = decision_key(d, _extract_json(par[i]["raw"]), it["ctx"])
        rows.append({
            "decision": d,
            "month": it["month"],
            "user_chars": len(it["user"]),
            "prompt_tokens": seq[i][0]["prompt_tokens"],
            "completion_tokens": st.mean(x["completion_tokens"] for x in seq[i]),
            "sec_seq": st.mean(x["sec"] for x in seq[i]),
            "finish": seq[i][0]["finish"],
            "raw_identical_repeats": len(set(raws)) == 1,
            "decision_identical_repeats": len(set(keys)) == 1,
            "raw_identical_concurrent": par[i]["raw"] == raws[0],
            "decision_identical_concurrent": pkey == keys[0],
            "valid_first_attempt": not (keys[0] is None or str(keys[0]).startswith("INVALID")),
            "decision_seq": keys[0],
            "decision_par": pkey,
            "reason_sample": (_extract_json(raws[0]) or {}).get("reason"),
        })

    def share(pred, sub=None) -> float:
        sub = rows if sub is None else sub
        return round(sum(1 for r in sub if pred(r)) / max(len(sub), 1), 4)

    per_dec = {}
    for d in TEMPLATE:
        sub = [r for r in rows if r["decision"] == d]
        if not sub:
            continue
        per_dec[d] = {
            "n": len(sub),
            "valid_first_attempt": share(lambda r: r["valid_first_attempt"], sub),
            "decision_identical_repeats": share(lambda r: r["decision_identical_repeats"], sub),
            "decision_identical_concurrent": share(lambda r: r["decision_identical_concurrent"], sub),
            "raw_identical_concurrent": share(lambda r: r["raw_identical_concurrent"], sub),
            "mean_prompt_tokens": round(st.mean(r["prompt_tokens"] for r in sub)),
            "max_prompt_tokens": max(r["prompt_tokens"] for r in sub),
            "mean_completion_tokens": round(st.mean(r["completion_tokens"] for r in sub), 1),
            "mean_sec_sequential": round(st.mean(r["sec_seq"] for r in sub), 2),
        }
    longest = max(rows, key=lambda r: r["prompt_tokens"])
    seq_rate = len(items) / seq_wall
    par_rate = len(items) / par_wall
    report = {
        "model": b.model,
        "endpoint": b.base_url,
        "n_prompts": len(items),
        "repeats": args.repeats,
        "parallel": args.parallel,
        "valid_first_attempt": share(lambda r: r["valid_first_attempt"]),
        "raw_identical_repeats": share(lambda r: r["raw_identical_repeats"]),
        "decision_identical_repeats": share(lambda r: r["decision_identical_repeats"]),
        "raw_identical_concurrent": share(lambda r: r["raw_identical_concurrent"]),
        "decision_identical_concurrent": share(lambda r: r["decision_identical_concurrent"]),
        "finish_not_stop": [r["decision"] for r in rows if r["finish"] != "stop"],
        "truncation": {
            "max_prompt_tokens": longest["prompt_tokens"],
            "max_prompt_chars": longest["user_chars"],
            "ctx_window": args.ctx_window,
            "headroom_tokens": args.ctx_window - longest["prompt_tokens"] - b.max_tokens,
            "chars_per_token_tenant": round(st.mean(r["user_chars"] / max(r["prompt_tokens"], 1) for r in rows if r["decision"] in ("at_expiry", "search")), 2),
        },
        "throughput_calls_per_min": {"sequential": round(seq_rate * 60, 1), f"parallel_{args.parallel}": round(par_rate * 60, 1)},
        "projection_hours_L_group": {
            "calls": L_GROUP_CALLS,
            "sequential": round(L_GROUP_CALLS / seq_rate / 3600, 1),
            f"parallel_{args.parallel}": round(L_GROUP_CALLS / par_rate / 3600, 1),
            "note": "sample is stratified by decision type, while real runs are dominated by tenant prompts; see per-decision timings",
        },
        "per_decision": per_dec,
        "rows": rows,
    }
    txt = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
