"""How much does the rent response depend on the value of time and the vacancy rule, with inquiries off? Rule-only."""
import math
import multiprocessing as mp
import statistics as st

import lease_day_v06 as g

SEEDS = 30
TREATED = {"east_express": {"Z05", "Z11"}, "replay": {"Z03", "Z21", "Z22", "Z23"}}
VARIANTS = {
    "base": {},
    "value of time 1.0": {"vot": 1.0},
    "smooth vacancy rule": {"smooth": True},
    "smooth, stayers full rate": {"smooth": True, "stayer_share": 1.0},
    "smooth x2": {"smooth": True, "rate_scale": 2},
    "time 1.0, smooth x2": {"vot": 1.0, "smooth": True, "rate_scale": 2},
    "time 1.0, smooth x2, stayers full": {"vot": 1.0, "smooth": True, "rate_scale": 2, "stayer_share": 1.0},
    "time 1.0, smooth x2, stayers full, no floor": {"vot": 1.0, "smooth": True, "rate_scale": 2, "stayer_share": 1.0, "floor": 0.6},
}


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
        runs = lambda policy, shock, v: pool.map(play, [(policy, s, shock, v) for s in range(SEEDS)])
        print(f"{'variant':46} {'east Z05+Z11 rent %':>20} {'replay treated %':>18} {'frozen-resp low cost':>20} {'frozen-resp commute':>20} {'vac':>5} {'moves':>6} {'whole end':>9}")
        for name, v in VARIANTS.items():
            none = runs("line_only", "none", v)
            east = runs("line_only", "east_express", v)
            real = runs("line_only", "replay", v)
            frozen = runs("frozen", "east_express", v)
            start = {(z["id"], k): z["rents"][k] for z in g.ZONES for k in g.TYPES}
            whole = st.mean(st.mean(r["after"][k] / start[k] for k in r["after"] if k[1] == "整租") for r in none)
            e, r = premium(east, none, TREATED["east_express"]), premium(real, none, TREATED["replay"])
            c, t = gap(frozen, east, "low_cash"), gap(frozen, east, "commute")
            print(f"{name:46} {e[0]:+10.2f} +-{e[1]:5.2f} {r[0]:+10.2f} +-{r[1]:4.2f} {c[0]:+12.0f} +-{c[1]:4.0f} {t[0]:+12.2f} +-{t[1]:4.2f} {st.mean(x['vacant'] for x in east):5.3f} {st.mean(x['moves'] for x in east):6.0f} {whole:9.3f}", flush=True)
