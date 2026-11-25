"""Quick baseline check for Lease Day v0.6: market stability and calibration targets, no shock."""
import multiprocessing as mp
import statistics as st
import sys

import lease_day_v06 as g

SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 8


def play(seed):
    return g.Game("line_only", seed, shock="none").run()


if __name__ == "__main__":
    with mp.Pool(8) as pool:
        rs = pool.map(play, range(SEEDS))
    m = lambda k: st.mean(r[k] for r in rs)
    print("seated", round(m("seated")), "low/mid/high", round(m("seated_low"), 2), round(m("seated_mid"), 2), round(m("seated_high"), 2), "end n", round(m("n")), "vacancy", round(m("vacant"), 3))
    print("commute", round(m("commute"), 1), "low", round(m("low_commute"), 1), "over60", round(m("over60"), 2))
    print("burden all", round(m("all_burden"), 3), "low", round(m("low_burden"), 3), "mid", round(m("mid_burden"), 3), "high", round(m("high_burden"), 3), "low over30", round(m("low_over30"), 2), "low near", round(m("low_near"), 2))
    print("left", round(m("left_low"), 1), round(m("left_mid"), 1), round(m("left_high"), 1), "blocked", round(m("blocked_low"), 1), round(m("blocked_mid"), 1), round(m("blocked_high"), 1), "moves", round(m("moves")))
    start = {(z["id"], k): z["rents"][k] for z in g.ZONES for k in g.TYPES}
    for name in ("before", "after"):
        print(name, {k: round(st.mean(st.mean(r[name][x] / start[x] for x in r[name] if x[1] == k) for r in rs), 3) for k in g.TYPES})
    modes, total = {}, {}
    for r in rs:
        for key, v in r["modes"].items():
            modes[key] = modes.get(key, 0) + v
    for (grp, mode), v in modes.items():
        total[grp] = total.get(grp, 0) + v
    for grp in ("low", "mid", "high"):
        print(grp, {mode: round(v / total[grp], 2) for (gg, mode), v in sorted(modes.items(), key=lambda x: -x[1]) if gg == grp})
