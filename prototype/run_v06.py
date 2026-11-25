"""Run Lease Day v0.6: calibration checks, the policy ledger, and assumption tests. Rule-only."""
import math
import multiprocessing as mp
import statistics as st
import sys
import time

import lease_day_v06 as g

SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
KEYS = ["commute", "low_commute", "low_cash", "low_burden", "revenue", "budget", "left", "moves"]
START = {(z["id"], k): z["rents"][k] for z in g.ZONES for k in g.TYPES}
MIN = {z["id"]: z["options"]["地铁"]["min"] for z in g.ZONES}


def play(args):
    policy, seed, shock, share, v = args
    return g.Game(policy, seed, shock=shock, cbd_share=share, **v).run()


def runs(policy, shock="replay", share=1.0, **v):
    return POOL.map(play, [(policy, s, shock, share, v) for s in range(SEEDS)])


def mean(rs, k):
    return st.mean(r[k] for r in rs)


def gap(a, b, k):
    d = [x[k] - y[k] for x, y in zip(a, b)]
    return st.mean(d), 1.96 * st.stdev(d) / math.sqrt(len(d))


def rent_index(rs, key, zones=None, kinds=g.TYPES):
    out = []
    for r in rs:
        vals = [r[key][k] / START[k] for k in r[key] if k in START and (zones is None or k[0] in zones) and k[1] in kinds]
        out.append(st.mean(vals))
    return st.mean(out)


def gradient(rs):
    """Log whole-unit rent on subway minutes, per 10 minutes; board rent is the 2018 listing."""
    slopes = []
    for r in rs:
        pts = [(MIN[k[0]], math.log(v)) for k, v in r["after"].items() if k[1] == "整租"]
        mx, my = st.mean(p[0] for p in pts), st.mean(p[1] for p in pts)
        slopes.append(sum((x - mx) * (y - my) for x, y in pts) / sum((x - mx) ** 2 for x, _ in pts) * 10)
    return st.mean(slopes)


def zone_premium(a, b, zones):
    d = []
    for x, y in zip(a, b):
        ka = [k for k in x["after"] if k[0] in zones and k in y["after"]]
        d.append(st.mean(math.log(x["after"][k] / y["after"][k]) for k in ka) * 100)
    return st.mean(d), 1.96 * st.stdev(d) / math.sqrt(len(d))


def report_checks(name, rs):
    modes = {}
    for r in rs:
        for k, v in r["modes"].items():
            modes[k] = modes.get(k, 0) + v
    total = {}
    for (grp, m), v in modes.items():
        total[grp] = total.get(grp, 0) + v
    print(f"\n[{name}] seated {mean(rs, 'seated'):.0f} (low {mean(rs, 'seated_low'):.2f}, mid {mean(rs, 'seated_mid'):.2f}, high {mean(rs, 'seated_high'):.2f}); end n {mean(rs, 'n'):.0f}; vacancy {mean(rs, 'vacant'):.3f}")
    print(f"  commute {mean(rs, 'commute'):.1f}, over 60 min {mean(rs, 'over60'):.2f}; burden all {mean(rs, 'all_burden'):.3f}, low {mean(rs, 'low_burden'):.3f}, mid {mean(rs, 'mid_burden'):.3f}, high {mean(rs, 'high_burden'):.3f}; low over 30% {mean(rs, 'low_over30'):.2f}, over 50% {mean(rs, 'low_over50'):.2f}; low within near zones {mean(rs, 'low_near'):.2f}")
    print(f"  rent index before line {rent_index(rs, 'before'):.3f}, end {rent_index(rs, 'after'):.3f}; whole {rent_index(rs, 'after', kinds=['整租']):.3f}, low-cost {rent_index(rs, 'after', kinds=g.TYPES[:2]):.3f}; gradient per 10 min {gradient(rs):+.3f}")
    print(f"  left low/mid/high {mean(rs, 'left_low'):.1f}/{mean(rs, 'left_mid'):.1f}/{mean(rs, 'left_high'):.1f}; blocked arrivals low/mid/high {mean(rs, 'blocked_low'):.1f}/{mean(rs, 'blocked_mid'):.1f}/{mean(rs, 'blocked_high'):.1f}")
    for grp in ("low", "mid", "high"):
        print("  modes", grp, {m: round(v / total[grp], 2) for (gg, m), v in sorted(modes.items(), key=lambda x: -x[1]) if gg == grp})


def main():
    began = time.time()
    print(f"{SEEDS} paired seeds; rule agents; values at the end of the run")
    treated = {"Z03", "Z21", "Z22", "Z23"}
    for share in (1.0, 0.1):
        none = runs("line_only", "none", share)
        real = runs("line_only", "replay", share)
        east = runs("line_only", "east_express", share)
        east_f = runs("frozen", "east_express", share)
        report_checks(f"no new line, cbd share {share}", none)
        report_checks(f"replay, cbd share {share}", real)
        print("  replay vs none, treated zones rent % ", "%+.2f +-%.2f" % zone_premium(real, none, treated), " Z03 %+.2f +-%.2f" % zone_premium(real, none, {"Z03"}), " Z23 %+.2f +-%.2f" % zone_premium(real, none, {"Z23"}))
        print("  east express vs none, Z05+Z11 rent % ", "%+.2f +-%.2f" % zone_premium(east, none, {"Z05", "Z11"}), " commute %+.1f +-%.1f" % gap(east, none, "commute"), " low commute %+.1f +-%.1f" % gap(east, none, "low_commute"), " low cash %+.0f +-%.0f" % gap(east, none, "low_cash"), " left %+.1f +-%.1f" % gap(east, none, "left"))
        print("  frozen minus responding (east express): commute %+.2f +-%.2f, low commute %+.2f +-%.2f, low cash %+.0f +-%.0f, revenue %+.0f +-%.0f" % (*gap(east_f, east, "commute"), *gap(east_f, east, "low_commute"), *gap(east_f, east, "low_cash"), *gap(east_f, east, "revenue")))
        if "policies" not in sys.argv:  # deferred to the extension; pass "policies" to run them
            continue
        print(f"  policy ledger, east express, cbd share {share}: differences against line only")
        print(f"  {'policy':17} " + " ".join(f"{k:>16}" for k in KEYS))
        print(f"  {'line_only level':17} " + " ".join(f"{mean(east, k):16.1f}" for k in KEYS))
        for name in ["renewal_cap", "subsidy", "subsidy_captured", "near_job_rooms", "free_fare"]:
            a = runs(name, "east_express", share)
            print(f"  {name:17} " + " ".join("%+8.1f +-%5.1f " % gap(a, east, k) for k in KEYS))
    print("\nassumption tests, east express, cbd share 1.0: level, difference from base in brackets for low cash")
    base = runs("line_only", "east_express", 1.0)
    base_none = runs("line_only", "none", 1.0)
    variants = {
        "base": {},
        "tau 25": {"tau": 25},
        "tau 60": {"tau": 60},
        "low-cost rooms -30%": {"low_cost": 0.7},
        "low-cost rooms -60%": {"low_cost": 0.4},
        "occupancy 0.99": {"occupancy": 0.99},
        "savings half": {"savings": 0.5},
        "saving x2": {"saving_scale": 2},
        "mid lines 20/30": {"lines": {**g.LINES, "mid": (0.20, 0.30)}},
        "mid lines 30/55": {"lines": {**g.LINES, "mid": (0.30, 0.55)}},
        "low lines 15/30": {"lines": {**g.LINES, "low": (0.15, 0.30)}},
        "low lines 25/55": {"lines": {**g.LINES, "low": (0.25, 0.55)}},
        "outside floor 0.8": {"floor": 0.8},
        "outside floor 1.0": {"floor": 1.0},
    }
    print(f"{'variant':22} {'seated':>6} {'low seat':>8} {'commute':>7} {'over60':>6} {'lowBur':>6} {'lowO30':>6} {'left':>6} {'blockLow':>8} {'blockMid':>8} {'Z05+Z11 rent%':>14} {'lowNear':>7}")
    for name, v in variants.items():
        a = runs("line_only", "east_express", 1.0, **v)
        b = runs("line_only", "none", 1.0, **v)
        pr = zone_premium(a, b, {"Z05", "Z11"})
        print(f"{name:22} {mean(a, 'seated'):6.0f} {mean(a, 'seated_low'):8.2f} {mean(a, 'commute'):7.1f} {mean(a, 'over60'):6.2f} {mean(a, 'low_burden'):6.3f} {mean(a, 'low_over30'):6.2f} {mean(a, 'left'):6.1f} {mean(a, 'blocked_low'):8.1f} {mean(a, 'blocked_mid'):8.1f} {pr[0]:+8.2f} +-{pr[1]:4.2f} {mean(a, 'low_near'):7.2f}")
    print("seconds", round(time.time() - began))


if __name__ == "__main__":
    with mp.Pool(8) as POOL:
        main()
