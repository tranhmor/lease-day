"""Does the monthly floor check depend on using only the tenant's first-choice mode? Rule-only, 30 paired seeds."""
import math
import multiprocessing as mp
import statistics as st

import lease_day_v06 as g

SEEDS = 30


def play(args):
    policy, seed, shock, v = args
    return g.Game(policy, seed, shock=shock, **{"demand_k": 0, **v}).run()


def premium(a, b, zones):
    d = []
    for x, y in zip(a, b):
        keys = [k for k in x["after"] if k[0] in zones and k in y["after"]]
        d.append(st.mean(math.log(x["after"][k] / y["after"][k]) for k in keys) * 100)
    return st.mean(d), 1.96 * st.stdev(d) / math.sqrt(len(d))


def gap(a, b, k):
    d = [x[k] - y[k] for x, y in zip(a, b)]
    return st.mean(d), 1.96 * st.stdev(d) / math.sqrt(len(d))


if __name__ == "__main__":
    with mp.Pool(8) as pool:
        for name, v in {"first-choice mode only": {}, "any mode that fits the budget": {"afford_modes": True}}.items():
            runs = lambda policy, shock, extra=None: pool.map(play, [(policy, s, shock, {**v, **(extra or {})}) for s in range(SEEDS)])
            none, east, real, frozen = runs("line_only", "none"), runs("line_only", "east_express"), runs("line_only", "replay"), runs("frozen", "east_express")
            cut = runs("line_only", "east_express", {"low_cost": 0.4})
            m = lambda rs, k: st.mean(r[k] for r in rs)
            print(name)
            print(f"  seated {m(none,'seated'):.0f} low/mid/high {m(none,'seated_low'):.2f}/{m(none,'seated_mid'):.2f}/{m(none,'seated_high'):.2f} end n {m(none,'n'):.0f} vacancy {m(none,'vacant'):.3f}")
            print(f"  commute {m(none,'commute'):.1f} over60 {m(none,'over60'):.2f} burden all/low/mid/high {m(none,'all_burden'):.3f} {m(none,'low_burden'):.3f} {m(none,'mid_burden'):.3f} {m(none,'high_burden'):.3f} low>30 {m(none,'low_over30'):.2f}")
            print(f"  left {m(none,'left_low'):.1f}/{m(none,'left_mid'):.1f}/{m(none,'left_high'):.1f} blocked {m(none,'blocked_low'):.0f}/{m(none,'blocked_mid'):.0f}/{m(none,'blocked_high'):.0f} moves {m(none,'moves'):.0f}")
            print("  east premium %+.2f +-%.2f, replay treated %+.2f +-%.2f" % (*premium(east, none, {"Z05", "Z11"}), *premium(real, none, {"Z03", "Z21", "Z22", "Z23"})))
            print("  frozen minus responding: commute %+.2f +-%.2f, low cash %+.0f +-%.0f" % (*gap(frozen, east, "commute"), *gap(frozen, east, "low_cash")))
            print(f"  low-cost -60%: seated {m(cut,'seated'):.0f} low>30 {m(cut,'low_over30'):.2f} left total {m(cut,'left'):.1f} blocked low {m(cut,'blocked_low'):.0f}")
            modes, total = {}, {}
            for r in none:
                for key, value in r["modes"].items():
                    modes[key] = modes.get(key, 0) + value
            for (grp, mode), value in modes.items():
                total[grp] = total.get(grp, 0) + value
            print("  car share low/mid/high", *(round(modes.get((grp, "私家车"), 0) / total[grp], 2) for grp in ("low", "mid", "high")), flush=True)
