"""Experiment runner for Lease Day v0.7: Group (R/L/M) x Scenario (N/S/P) x paired seeds.

Supports shared M1-M12 warm-up snapshots so N/S/P start from the exact same Month-12 state per seed,
saving ~33% LLM calls and eliminating pre-announcement variance.

Examples:
    python3 -m prototype_v07.run_v07 --group R --seeds 20 --out rental_game/runs
    python3 -m prototype_v07.run_v07 --group L --mock --seeds 5 --out rental_game/runs_mock
    python3 -m prototype_v07.run_v07 --group M --live --seeds 5 --out rental_game/runs
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import multiprocessing as mp
from pathlib import Path
import time
from typing import Dict, List, Tuple

from .agents.llm import DiskCache, LLMLandlord, LLMTenant, MockLLMBackend, OpenAICompatBackend
from .agents.rule import RuleLandlord, RuleTenant
from .lease_day_v07 import Config, GameV07


def _make_policies(group: str, backend_kind: str, cache_path: str):
    cache = None
    backend = None
    if group in ("L", "M"):
        cache = DiskCache(cache_path)
        backend = MockLLMBackend() if backend_kind == "mock" else OpenAICompatBackend()
    if group == "R":
        return RuleLandlord(), RuleTenant(), None
    if group == "M":
        return LLMLandlord(backend, cache=cache), RuleTenant(), cache
    if group == "L":
        return LLMLandlord(backend, cache=cache), LLMTenant(backend, cache=cache), cache
    raise ValueError(f"Unknown group: {group}")


def _run_branch(snap, group: str, sc: str, seed: int, out_dir: str, backend_kind: str, cache_path: str) -> Dict:
    # Own policies and SQLite connection per thread (sqlite3 connections are not shared across threads)
    ll_pol, t_pol, cache = _make_policies(group, backend_kind, cache_path)
    try:
        g = GameV07.from_snapshot(snap, scenario=sc, landlord_policy=ll_pol, tenant_policy=t_pol,
                                  log_dir=str(Path(out_dir) / f"{group}_{sc}_{seed}"))
        return g.run()
    finally:
        if cache is not None:
            cache.close()


def run_seed_bundle(args: Tuple[str, int, List[str], str, str, str, bool, bool, int, bool]) -> List[Dict]:
    group, seed, scenarios, out_dir, backend_kind, cache_path, shared_warmup, log_decisions, months, par_branches = args
    ll_pol, t_pol, cache = _make_policies(group, backend_kind, cache_path)
    results = []
    try:
        if shared_warmup and len(scenarios) > 1 and par_branches:
            # Non-deterministic backends: S must replay N's cached answers for months 13-24 (identical prompts), so S
            # starts only after N has finished. P's prompts carry the announcement from month 13 and never collide
            # with N's, so N and P run concurrently. Pre-opening S == N then holds by construction via the cache.
            warm_cfg = Config(scenario="N", seed=seed, months=months, log_dir=None, record_decisions=log_decisions)
            warm_game = GameV07(warm_cfg, landlord_policy=ll_pol, tenant_policy=t_pol)
            warm_game.run_until(warm_cfg.announce_month)
            snap = warm_game.export_snapshot()
            by_sc: Dict[str, Dict] = {}
            with ThreadPoolExecutor(2) as ex:
                fut_p = ex.submit(_run_branch, snap, group, "P", seed, out_dir, backend_kind, cache_path) if "P" in scenarios else None
                if "N" in scenarios:
                    by_sc["N"] = _run_branch(snap, group, "N", seed, out_dir, backend_kind, cache_path)
                if "S" in scenarios:
                    by_sc["S"] = _run_branch(snap, group, "S", seed, out_dir, backend_kind, cache_path)
                if fut_p is not None:
                    by_sc["P"] = fut_p.result()
            results = [by_sc[sc] for sc in scenarios]
        elif shared_warmup and len(scenarios) > 1:
            # Run M1-M12 warm-up ONCE (using scenario "N", no announcement, no opening)
            warm_cfg = Config(
                scenario="N",
                seed=seed,
                months=months,
                log_dir=None,
                record_decisions=log_decisions,
            )
            warm_game = GameV07(warm_cfg, landlord_policy=ll_pol, tenant_policy=t_pol)
            warm_game.run_until(warm_cfg.announce_month)
            snap = warm_game.export_snapshot()

            for sc in scenarios:
                run_dir = str(Path(out_dir) / f"{group}_{sc}_{seed}")
                g = GameV07.from_snapshot(snap, scenario=sc, landlord_policy=ll_pol, tenant_policy=t_pol, log_dir=run_dir)
                results.append(g.run())
        else:
            for sc in scenarios:
                run_dir = str(Path(out_dir) / f"{group}_{sc}_{seed}")
                cfg = Config(
                    scenario=sc,
                    seed=seed,
                    months=months,
                    log_dir=run_dir,
                    record_decisions=log_decisions,
                )
                g = GameV07(cfg, landlord_policy=ll_pol, tenant_policy=t_pol)
                results.append(g.run())
    finally:
        if cache is not None:
            cache.close()
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="Run Lease Day v0.7 experiment matrix")
    ap.add_argument("--group", choices=["R", "L", "M"], default="R")
    ap.add_argument("--scenarios", nargs="+", default=["N", "S", "P"], choices=["N", "S", "P"])
    ap.add_argument("--seeds", type=int, default=5, help="Number of paired seeds (0..seeds-1)")
    ap.add_argument("--months", type=int, default=36)
    ap.add_argument("--workers", type=int, default=None, help="Parallel seed processes (default: 1 for --live L/M, else 4)")
    ap.add_argument("--mock", action="store_true", help="Use offline MockLLMBackend for L/M")
    ap.add_argument("--live", action="store_true", help="Use live OpenAI-compatible API from .env")
    ap.add_argument("--no-shared-warmup", action="store_true", help="Disable shared M1-M12 snapshot fork")
    ap.add_argument("--no-decision-log", action="store_true", help="Skip decisions.jsonl to save disk on 100-seed R runs")
    ap.add_argument("--parallel-branches", action="store_true",
                    help="After the shared warm-up run N and P concurrently, then S (S replays N's cache up to opening)")
    ap.add_argument("--out", type=str, default="rental_game/runs")
    ap.add_argument("--cache", type=str, default="rental_game/runs/llm_cache.sqlite")
    args = ap.parse_args()

    backend_kind = "live" if args.live else "mock"
    shared = not args.no_shared_warmup
    log_dec = not args.no_decision_log
    t0 = time.time()

    jobs = [
        (args.group, s, args.scenarios, args.out, backend_kind, args.cache, shared, log_dec, args.months, args.parallel_branches)
        for s in range(args.seeds)
    ]

    if args.group in ("L", "M"):
        # Pre-initialize SQLite WAL cache once before spawning parallel workers
        DiskCache(args.cache).close()

    # Live runs default to 1 worker (shared/rate-limited gateways); pass --workers N explicitly for a local GPU server.
    req_workers = args.workers if args.workers is not None else (1 if (args.group in ("L", "M") and backend_kind == "live") else 4)
    workers = max(1, min(req_workers, len(jobs)))
    if workers > 1:
        with mp.Pool(workers) as pool:
            nested = pool.map(run_seed_bundle, jobs)
    else:
        nested = [run_seed_bundle(j) for j in jobs]

    flat = [r for sub in nested for r in sub]
    print(f"Completed {len(flat)} runs (group={args.group}, scenarios={args.scenarios}, seeds=0..{args.seeds - 1}) in {time.time() - t0:.1f}s")
    for sc in args.scenarios:
        sub = [r for r in flat if r["scenario"] == sc]
        avg_m24 = sum(r["rent_tr_m24"] for r in sub) / len(sub)
        avg_m36 = sum(r["rent_tr_m36"] for r in sub) / len(sub)
        avg_mi = sum(r["tr_move_ins_m13_24"] for r in sub) / len(sub)
        avg_fb = sum(r["fallback_rate"] for r in sub) / len(sub)
        tot_tok = sum(r["total_tokens"] for r in sub)
        print(f"  [{args.group}-{sc}] tr_rent M24={avg_m24:.2f}, M36={avg_m36:.2f} | M13-24 move_ins={avg_mi:.1f} | fallback={avg_fb:.2%} | tokens={tot_tok:,}")


if __name__ == "__main__":
    main()
