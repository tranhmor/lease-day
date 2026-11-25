"""Core comparison: no line or line, crossed with rents frozen at month 24 or responding. Rule-only, paired seeds."""
import math
import multiprocessing as mp
import statistics as st
import sys

import lease_day_v06 as g

SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 100
DEMAND = float(sys.argv[2]) if len(sys.argv) > 2 else g.DEMAND_K
KEYS = ["commute", "low_commute", "watch_commute", "other_commute", "watch_share", "watch_low", "low_cash", "low_burden", "revenue", "moves", "left", "blocked_low"]
SHOCK_ZONES = {"east_express": {"Z05", "Z11"}, "replay": {"Z03", "Z21", "Z22", "Z23"}}


def play(args):
    policy, seed, shock, v = args
    out = g.Game(policy, seed, shock=shock, **v).run()
    zones = v["watch"]
    start = {(z["id"], k): z["rents"][k] for z in g.ZONES for k in g.TYPES}
    inside = [out["after"][k] / start[k] for k in out["after"] if k[0] in zones]
    other = [out["after"][k] / start[k] for k in out["after"] if k[0] not in zones]
    out["watch_rent"] = st.mean(inside) * 100
    out["other_rent"] = st.mean(other) * 100
    return {k: v2 for k, v2 in out.items() if k not in ("before", "after", "modes")}


def gap(a, b, k):
    d = [x[k] - y[k] for x, y in zip(a, b)]
    return st.mean(d), 1.96 * st.stdev(d) / math.sqrt(len(d))


def twist(a, b, c, d, k):
    v = [(w[k] - x[k]) - (y[k] - z[k]) for w, x, y, z in zip(a, b, c, d)]
    return st.mean(v), 1.96 * st.stdev(v) / math.sqrt(len(v))


if __name__ == "__main__":
    with mp.Pool(8) as pool:
        for shock, zones in SHOCK_ZONES.items():
            v = {"watch": tuple(zones), "demand_k": DEMAND}
            arm = lambda policy, s: pool.map(play, [(policy, i, s, v) for i in range(SEEDS)])
            a, a0, b, c = arm("line_only", "none"), arm("frozen", "none"), arm("frozen", shock), arm("line_only", shock)
            keys = KEYS + ["watch_rent", "other_rent"]
            print(f"\n{shock}: demand_k {DEMAND}; treated zones {sorted(zones)}; {SEEDS} seeds; last 12 months; last two rows are rent index x100 against start")
            print(f"{'metric':15} {'A none, respond':>15} {'A0 none, frozen':>15} {'B line, frozen':>15} {'C line, respond':>15} | {'B-A':>13} {'C-B':>13} {'C-A':>13} {'A0-A':>13} {'B-A0':>13} {'C-A-(B-A0)':>13}")
            for k in keys:
                m = lambda rs: st.mean(r[k] for r in rs)
                f = lambda x: f"{x[0]:+7.2f}±{x[1]:4.2f}"
                print(f"{k:15} {m(a):15.3f} {m(a0):15.3f} {m(b):15.3f} {m(c):15.3f} | {f(gap(b,a,k)):>13} {f(gap(c,b,k)):>13} {f(gap(c,a,k)):>13} {f(gap(a0,a,k)):>13} {f(gap(b,a0,k)):>13} {f(twist(c,a,b,a0,k)):>13}", flush=True)
