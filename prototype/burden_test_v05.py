"""Does the acceptable rent share change Lease Day v0.5? Rule-only, no LLM. Everything else as in v0.5.

The board is still the old A/B/C corridor, so this tests the rule's leverage, not the CBD result.
"""
import random
import statistics as st

import lease_day_v05 as g

SEEDS = 200
MID_TOP = 12000


def group(t):
    return "low" if t.income <= g.LOW_INCOME else "mid" if t.income < MID_TOP else "high"


def share(x):
    return lambda game, t, rent, room: rent <= x * t.income


def by_group(low, mid, high):
    return lambda game, t, rent, room: rent <= {"low": low, "mid": mid, "high": high}[group(t)] * t.income


def individual(lo, hi):
    def rule(game, t, rent, room):
        if not hasattr(t, "limit"):
            t.limit = game.draw.uniform(lo, hi)
        return rent <= t.limit * t.income
    return rule


def residual(floor):
    return lambda game, t, rent, room: rent + 2 * g.WORKDAYS * game.fare(t, room.zone) <= t.income - floor


RULES = {
    "all 25%": share(0.25),
    "all 30%": share(0.30),
    "all 35% (v0.5)": share(0.35),
    "all 45%": share(0.45),
    "all 60%": share(0.60),
    "low 45 mid 35 high 30": by_group(0.45, 0.35, 0.30),
    "low 25 mid 35 high 40": by_group(0.25, 0.35, 0.40),
    "low 25 only": by_group(0.25, 0.35, 0.35),
    "low 60 only": by_group(0.60, 0.35, 0.35),
    "mid 25 only": by_group(0.35, 0.25, 0.35),
    "mid 60 only": by_group(0.35, 0.60, 0.35),
    "high 25 only": by_group(0.35, 0.35, 0.25),
    "high 60 only": by_group(0.35, 0.35, 0.60),
    "individual 20-50%": individual(0.20, 0.50),
    "left over 2000": residual(2000),
    "left over 3000": residual(3000),
}


class Trial(g.Game):
    rule = None

    def __init__(self, policy, landlord, seed):
        super().__init__(policy, landlord, seed)
        self.draw = random.Random(seed + 1)

    def best(self, t, stay_rent=None, see_all=False):
        vacant = [r for r in self.rooms if r.tenant is None and not r.public]
        options = []
        if stay_rent is not None and self.rule(t, self.net(t, stay_rent, t.room), t.room):
            options.append((self.score(t, t.room, stay_rent, False), t.room))
        seen = vacant if see_all else self.rng.sample(vacant, min(g.LISTINGS_SEEN, len(vacant)))
        if t.low:
            seen = seen + [r for r in self.rooms if r.tenant is None and r.public]
        for r in seen:
            rent = r.rent + self.load(t, r)
            if self.rule(t, self.net(t, rent, r), r):
                options.append((self.score(t, r, rent, True), r))
        return min(options, key=lambda o: o[0])[1] if options else None


def play(rule, policy, seed):
    game = Trial(policy, "stayer_discount", seed)
    game.rule = lambda t, rent, room: rule(game, t, rent, room)
    out = game.run()
    for name in ("low", "mid", "high"):
        people = [t for t in game.tenants if group(t) == name]
        out[name + "_low_room"] = st.mean(t.room.tier == "low" for t in people) if people else 0
        out[name + "_burden"] = st.mean(t.room.rent / t.income for t in people) if people else 0
        out[name + "_over_30"] = st.mean(t.room.rent / t.income > 0.30 for t in people) if people else 0
    return out


def mean(rs, k):
    return st.mean(r[k] for r in rs)


def gap(a, b, k):
    d = [x[k] - y[k] for x, y in zip(a, b)]
    return f"{st.mean(d):+7.1f} +-{1.96 * st.stdev(d) / len(d) ** 0.5:5.1f}"


if __name__ == "__main__":
    print(f"{SEEDS} seeds; 120 tenants; stayer_discount landlord; values at the end of the run under line_only unless marked")
    print(f"{'rule':24} {'seated':>6} {'end n':>5} {'left':>4} {'moves':>5} | {'low rm: low mid high':>21} | {'burden: low mid high':>21} | {'over30 low':>10} | {'line on low commute':>16} | {'line on C regular':>16} | {'frozen minus line, commute':>16}")
    for name, rule in RULES.items():
        no = [play(rule, "no_line", s) for s in range(SEEDS)]
        line = [play(rule, "line_only", s) for s in range(SEEDS)]
        frozen = [play(rule, "line_frozen", s) for s in range(SEEDS)]
        print(f"{name:24} {mean(line, 'seated'):6.1f} {mean(line, 'n'):5.1f} {mean(line, 'left'):4.1f} {mean(line, 'moves'):5.1f} | "
              f"{mean(line, 'low_low_room'):7.2f} {mean(line, 'mid_low_room'):6.2f} {mean(line, 'high_low_room'):6.2f} | "
              f"{mean(line, 'low_burden'):7.2f} {mean(line, 'mid_burden'):6.2f} {mean(line, 'high_burden'):6.2f} | "
              f"{mean(line, 'low_over_30'):10.2f} | "
              f"{gap(line, no, 'low_commute')} | {gap(line, no, 'after_C_regular')} | {gap(frozen, line, 'commute')}")
