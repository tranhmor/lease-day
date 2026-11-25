"""Vacancy in the east express treated zones against the rest, and market-wide levels, for all four arms. Rule-only, paired seeds."""
import multiprocessing as mp
import statistics as st
import sys

import lease_day_v06 as g

SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 100
ZONES = ("Z05", "Z11")
ARMS = {"A none, respond": ("line_only", "none"), "A0 none, frozen": ("frozen", "none"), "B line, frozen": ("frozen", "east_express"), "C line, respond": ("line_only", "east_express")}
KEYS = ["vac_in", "vac_out", "vacant", "n", "over60", "low_over30"]


class Probe(g.Game):
    def measure(self, tail, modes):
        super().measure(tail, modes)
        share = lambda rs: st.mean(r.tenant is None for r in rs)
        tail.setdefault("vac_in", []).append(share([r for r in self.rooms if r.zone in ZONES]))
        tail.setdefault("vac_out", []).append(share([r for r in self.rooms if r.zone not in ZONES]))


def play(args):
    policy, shock, seed = args
    return {k: v for k, v in Probe(policy, seed, shock=shock, watch=ZONES).run().items() if k in KEYS}


if __name__ == "__main__":
    print(f"east_express: treated zones {list(ZONES)}; {SEEDS} seeds; last 12 months")
    print(f"{'arm':16} " + " ".join(f"{k:>11}" for k in KEYS))
    with mp.Pool(8) as pool:
        for name, (policy, shock) in ARMS.items():
            rs = pool.map(play, [(policy, shock, s) for s in range(SEEDS)])
            print(f"{name:16} " + " ".join(f"{st.mean(r[k] for r in rs):11.4f}" for k in KEYS), flush=True)
