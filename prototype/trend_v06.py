"""What if rents and wages move over the 60 months? Rule-only, east express against no line, same seeds."""
import math
import multiprocessing as mp
import statistics as st

import lease_day_v06 as g

SEEDS = 30
SCENARIOS = {
    "base, no trend": {},
    "wages back to 2018 level": {"income_scale": 1 / 1.113},
    "rent +5%, wage +5%": {"rent_trend": 0.05, "wage_trend": 0.05},
    "rent +5%, wage 0": {"rent_trend": 0.05},
    "rent +13%, wage +8.8% (2015-18)": {"rent_trend": 0.13, "wage_trend": 0.088},
    "rent +13%, wage +8.8%, low-cost -30%": {"rent_trend": 0.13, "wage_trend": 0.088, "low_cost": 0.7},
}


def play(args):
    policy, seed, shock, v = args
    return g.Game(policy, seed, shock=shock, **v).run()


def premium(a, b, zones):
    d = []
    for x, y in zip(a, b):
        keys = [k for k in x["after"] if k[0] in zones and k in y["after"]]
        d.append(st.mean(math.log(x["after"][k] / y["after"][k]) for k in keys) * 100)
    return st.mean(d), 1.96 * st.stdev(d) / math.sqrt(len(d))


if __name__ == "__main__":
    with mp.Pool(8) as pool:
        for name, v in SCENARIOS.items():
            none = pool.map(play, [("line_only", s, "none", v) for s in range(SEEDS)])
            east = pool.map(play, [("line_only", s, "east_express", v) for s in range(SEEDS)])
            m = lambda k: st.mean(r[k] for r in east)
            n = lambda k: st.mean(r[k] for r in none)
            pr = premium(east, none, {"Z05", "Z11"})
            print(f"{name:38} end n {n('n'):5.0f} vac {n('vacant'):.3f} commute {n('commute'):4.1f} over60 {n('over60'):.2f} burden all/low/mid/high {n('all_burden'):.3f} {n('low_burden'):.3f} {n('mid_burden'):.3f} {n('high_burden'):.3f} low>30 {n('low_over30'):.2f} left {n('left_low'):5.1f}/{n('left_mid'):5.1f}/{n('left_high'):4.1f} blocked {n('blocked_low'):5.0f}/{n('blocked_mid'):4.0f}/{n('blocked_high'):3.0f} moves {n('moves'):4.0f} premium {pr[0]:+.2f} +-{pr[1]:.2f}", flush=True)
