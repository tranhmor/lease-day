"""How much does the move-in payment matter? Rule-only, 30 paired seeds, inquiries on."""
import multiprocessing as mp
import statistics as st

import lease_day_v06 as g

SEEDS = 30
SCENARIOS = {
    "all 押一付三": {"up_front": 4},
    "all 押一付二": {"up_front": 3},
    "all 押一付一": {"up_front": 2},
    "by room type": {},
}


def play(args):
    seed, shock, v = args
    return g.Game("line_only", seed, shock=shock, **v).run()


if __name__ == "__main__":
    with mp.Pool(8) as pool:
        for name, v in SCENARIOS.items():
            rs = pool.map(play, [(s, "none", v) for s in range(SEEDS)])
            m = lambda k: st.mean(r[k] for r in rs)
            print(f"{name:14} seated {m('seated'):5.0f} low/mid/high {m('seated_low'):.2f}/{m('seated_mid'):.2f}/{m('seated_high'):.2f} end n {m('n'):5.0f} vac {m('vacant'):.3f} commute {m('commute'):.1f} over60 {m('over60'):.2f} burden {m('all_burden'):.3f}/{m('low_burden'):.3f}/{m('mid_burden'):.3f}/{m('high_burden'):.3f} low>30 {m('low_over30'):.2f} left {m('left_low'):.1f}/{m('left_mid'):.1f}/{m('left_high'):.1f} blocked {m('blocked_low'):.0f}/{m('blocked_mid'):.0f}/{m('blocked_high'):.0f} moves {m('moves'):.0f}", flush=True)
