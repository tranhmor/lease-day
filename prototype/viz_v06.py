"""Month-by-month record of the core experiment for the results page. Rule-only.

The recorder only watches: it changes no rule and draws no random number, so its totals must equal scenarios_v06.py.
Writes analysis/viz_v06_data.json (all seeds, averaged) and analysis/viz_v06_replay.json (one seed, every room and event).
Usage: python3 viz_v06.py [seeds]; python3 viz_v06.py check
"""
import json
import math
import multiprocessing as mp
import os
import statistics as st
import sys

import lease_day_v06 as g

SHOCK = "east_express"
WATCH = ("Z05", "Z11")
ARMS = {"A": ("line_only", "none"), "A0": ("frozen", "none"), "B": ("frozen", SHOCK), "C": ("line_only", SHOCK)}
REPLAY_SEED = 0
TAIL = 12
ZONE_IDS = [z["id"] for z in g.ZONES]
GROUPS = ("low", "mid", "high")
MODES = list(g.CLASS)
CLASSES = ["subway", "bus", "bike", "walk", "car", "taxi"]


def avg(xs):
    return sum(xs) / len(xs) if xs else 0.0


class Blocked(dict):
    """Game.run adds zero to blocked before the line; every write is still one blocked arrival."""

    def __init__(self, owner, start):
        super().__init__(start)
        self.owner = owner

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.owner.on_blocked(key)


class Recorder(g.Game):
    def __init__(self, policy, seed, shock, detail=False, **variant):
        self.watching = False
        self.detail = detail
        super().__init__(policy, seed, shock=shock, **variant)
        self.blocked = Blocked(self, self.blocked)
        self.series = {}
        self.zone_series = {z: {} for z in ZONE_IDS}
        self.ledger = {}
        self.flow = [[0] * len(ZONE_IDS) for _ in ZONE_IDS]
        self.frames_seen = 0
        self.zone_at = {z: i for i, z in enumerate(ZONE_IDS)}
        self.base = {(z["id"], k): z["rents"][k] for z in g.ZONES for k in g.TYPES}
        self.reset_counts()
        self.searcher = None
        if detail:
            self.room_at = {id(r): i for i, r in enumerate(self.rooms)}
            self.people = {}
            self.events = []
            self.last_state = [None] * len(self.rooms)
            self.deltas = []
            self.renew_log = []
            self.month_events = []

    @property
    def month(self):
        return self._month

    @month.setter
    def month(self, value):
        if self.watching:
            self.close_month(value - 1)
        self._month = value

    def reset_counts(self):
        self.counts = dict(moves=0, arrivals=0, exits=0, left=0, blocked_low=0, blocked_mid=0, blocked_high=0, renewals=0, moves_in=0, moves_out=0, arrive_in=0)
        self.quote_up = []
        self.renewing = False  # the month's random departures come first, then the renewals

    def vid(self, t):
        if not hasattr(t, "vid"):
            t.vid = len(self.people)
            self.people[t.vid] = [GROUPS.index(t.group), round(t.income), round(t.wage), int(t.couple), int(t.car)]
        return t.vid

    def way(self, t, zone):
        w = self.travel(t, zone)
        return MODES.index(w[1]), round(w[2])

    def on_blocked(self, group):
        self.counts["blocked_" + group] += 1
        if self.detail and self.searcher is not None:
            self.month_events.append(["blocked", GROUPS.index(group), round(self.searcher.income)])

    def best(self, t, vacant, stay_rent=None, see_all=False):
        self.searcher = t
        return super().best(t, vacant, stay_rent=stay_rent, see_all=see_all)

    def renewal(self, t):
        self.renewing = True
        paid = t.room.rent
        quote = super().renewal(t)
        t.paid, t.quote = paid, quote
        self.counts["renewals"] += 1
        self.quote_up.append(quote / paid - 1)
        return quote

    def vacate(self, room):
        t = room.tenant
        if t is not None and t not in self.tenants:
            key = "left" if self.renewing else "exits"
            self.counts[key] += 1
            if self.detail:
                self.month_events.append([key, self.vid(t), self.room_at[id(room)], round(t.paid) if self.renewing else round(room.rent), round(t.quote) if self.renewing else 0])
        super().vacate(room)

    def place(self, t, room, month):
        old = t.room
        if self.watching and old is not None:
            self.counts["moves"] += 1
            self.flow[self.zone_at[old.zone]][self.zone_at[room.zone]] += self._month >= g.LINE_OPENS
            self.counts["moves_in"] += old.zone not in WATCH and room.zone in WATCH
            self.counts["moves_out"] += old.zone in WATCH and room.zone not in WATCH
            if self.detail:
                self.month_events.append(["move", self.vid(t), self.room_at[id(old)], self.room_at[id(room)], round(t.paid), round(t.quote), round(room.rent)] + list(self.way(t, old.zone)) + list(self.way(t, room.zone)))
        elif self.watching:
            self.counts["arrivals"] += 1
            self.counts["arrive_in"] += room.zone in WATCH
            if self.detail:
                self.month_events.append(["arrive", self.vid(t), self.room_at[id(room)], round(room.rent)] + list(self.way(t, room.zone)))
        super().place(t, room, month)

    def add(self, key, value):
        self.series.setdefault(key, []).append(value)

    def close_month(self, m):
        rows = [(t, self.travel(t, t.room.zone, self.net(t, t.room.rent, t.room)) or self.travel(t, t.room.zone)) for t in self.tenants]
        inside = [(t, w) for t, w in rows if t.room.zone in WATCH]
        outside = [(t, w) for t, w in rows if t.room.zone not in WATCH]
        burden = lambda t: self.net(t, t.room.rent, t.room) / t.income
        self.add("commute", avg([w[2] for _, w in rows]))
        self.add("over60", avg([w[2] > 60 for _, w in rows]))
        for grp in GROUPS:
            self.add(grp + "_commute", avg([w[2] for t, w in rows if t.group == grp]))
            self.add(grp + "_burden", avg([burden(t) for t, _ in rows if t.group == grp]))
        self.add("watch_commute", avg([w[2] for _, w in inside]))
        self.add("other_commute", avg([w[2] for _, w in outside]))
        self.add("watch_share", len(inside) / len(rows))
        self.add("watch_low", avg([t.low for t, _ in inside]))
        self.add("low_cash", avg([self.net(t, t.room.rent, t.room) + w[3] for t, w in rows if t.low]))
        self.add("low_over30", avg([burden(t) > 0.30 for t, _ in rows if t.low]))
        self.add("all_burden", avg([burden(t) for t, _ in rows]))
        self.add("n", len(rows))
        for cls in CLASSES:
            self.add("mode_in_" + cls, avg([g.CLASS[w[1]] == cls for _, w in inside]))
            self.add("mode_out_" + cls, avg([g.CLASS[w[1]] == cls for _, w in outside]))
        cell = {}
        for r in self.rooms:
            cell.setdefault((r.zone, r.kind), []).append(r)
        index = {k: avg([r.rent for r in rs]) / self.base[k] for k, rs in cell.items()}
        self.add("watch_rent", 100 * avg([v for k, v in index.items() if k[0] in WATCH]))
        self.add("other_rent", 100 * avg([v for k, v in index.items() if k[0] not in WATCH]))
        rooms_in = [r for r in self.rooms if r.zone in WATCH]
        rooms_out = [r for r in self.rooms if r.zone not in WATCH]
        self.add("vac_in", avg([r.tenant is None for r in rooms_in]))
        self.add("vac_out", avg([r.tenant is None for r in rooms_out]))
        self.add("revenue", sum(r.rent for r in self.rooms if r.tenant) / len(self.rooms))
        self.add("rev_in", sum(r.rent for r in rooms_in if r.tenant) / len(rooms_in))
        self.add("rev_out", sum(r.rent for r in rooms_out if r.tenant) / len(rooms_out))
        at = max(m, 0)
        self.add("inq_in", sum(c[at] for k, c in self.inquiries.items() if k[0] in WATCH) / len(rooms_in) if m >= 0 else 0.0)
        self.add("inq_out", sum(c[at] for k, c in self.inquiries.items() if k[0] not in WATCH) / len(rooms_out) if m >= 0 else 0.0)
        for k, v in self.counts.items():
            self.add(k, v if m >= 0 else 0)
        self.add("quote_up", 100 * avg(self.quote_up))
        for z in ZONE_IDS:
            here = [(t, w) for t, w in rows if t.room.zone == z]
            rs = [r for r in self.rooms if r.zone == z]
            zs = self.zone_series[z]
            zs.setdefault("n", []).append(len(here))
            zs.setdefault("low", []).append(sum(t.low for t, _ in here))
            zs.setdefault("vac", []).append(avg([r.tenant is None for r in rs]))
            zs.setdefault("rent", []).append(100 * avg([v for k, v in index.items() if k[0] == z]))
            zs.setdefault("commute", []).append(avg([w[2] for _, w in here]))
        if m >= g.MONTHS - TAIL:
            for grp in GROUPS:
                for where, part in (("in", inside), ("out", outside)):
                    members = [(t, w) for t, w in part if t.group == grp]
                    bucket = self.ledger.setdefault(grp + "_" + where, {"n": [], "commute": [], "rent": [], "fare": [], "burden": []})
                    bucket["n"].append(len(members))
                    bucket["commute"].append(avg([w[2] for _, w in members]))
                    bucket["rent"].append(avg([self.net(t, t.room.rent, t.room) for t, _ in members]))
                    bucket["fare"].append(avg([w[3] for _, w in members]))
                    bucket["burden"].append(avg([burden(t) for t, _ in members]))
        if self.detail:
            self.store_detail(m, rows)
        self.reset_counts()

    def store_detail(self, m, rows):
        delta = []
        way = {id(t.room): (t, w) for t, w in rows}
        for i, r in enumerate(self.rooms):
            got = way.get(id(r))
            state = (self.vid(got[0]), round(r.rent), MODES.index(got[1][1]), round(got[1][2])) if got else (-1, round(r.rent), -1, 0)
            if state != self.last_state[i]:
                delta.append([i, *state])
                self.last_state[i] = state
        self.deltas.append(delta)
        self.events.append(self.month_events if m >= 0 else [])
        self.renew_log.append([self.counts["renewals"], round(100 * avg(self.quote_up), 2)])
        self.month_events = []

    def run(self):
        self.watching = True
        out = super().run()
        self.close_month(g.MONTHS - 1)
        self.watching = False
        return out


def play(args):
    arm, seed = args
    policy, shock = ARMS[arm]
    detail = seed == REPLAY_SEED
    game = Recorder(policy, seed, shock, detail=detail, watch=WATCH, demand_k=g.DEMAND_K)
    out = game.run()
    start = {(z["id"], k): z["rents"][k] for z in g.ZONES for k in g.TYPES}
    out["watch_rent"] = st.mean(out["after"][k] / start[k] for k in out["after"] if k[0] in WATCH) * 100
    out["other_rent"] = st.mean(out["after"][k] / start[k] for k in out["after"] if k[0] not in WATCH) * 100
    out = {k: v for k, v in out.items() if k not in ("before", "after", "modes")}
    for key, base in (("cum_in", "moves_in"), ("cum_moves", "moves"), ("cum_left", "left"), ("cum_blocked", "blocked_low")):
        total, game.series[key] = 0, []
        for i, v in enumerate(game.series[base]):
            total += v if i > g.LINE_OPENS else 0
            game.series[key].append(total)
    result = dict(arm=arm, seed=seed, out=out, series=game.series, zones=game.zone_series, flow=game.flow, ledger={k: {m: avg(v) for m, v in b.items()} for k, b in game.ledger.items()})
    if detail:
        result["detail"] = dict(rooms=[[game.zone_at[r.zone], g.TYPES.index(r.kind), round(r.start)] for r in game.rooms], people=game.people, deltas=game.deltas, events=game.events, renew=game.renew_log)
    return result


def tail(values):
    return avg(values[-TAIL:])


def half(values):
    return 1.96 * st.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0


def effects(per_arm, pick):
    """Direct B-A0, total C-A, interaction, paired by seed."""
    a, a0, b, c = (per_arm[k] for k in ("A", "A0", "B", "C"))
    rows = {"direct": [], "total": [], "interaction": []}
    for i in range(len(a)):
        rows["direct"].append(pick(b[i]) - pick(a0[i]))
        rows["total"].append(pick(c[i]) - pick(a[i]))
        rows["interaction"].append(rows["total"][-1] - rows["direct"][-1])
    return {k: [round(avg(v), 3), round(half(v), 3)] for k, v in rows.items()}


def check():
    """A plain Game and a Recorder with the same seed must end identically, and the record must match the game's own tail."""
    worst = 0.0
    for arm, (policy, shock) in ARMS.items():
        for seed in (0, 1):
            v = dict(watch=WATCH, demand_k=g.DEMAND_K)
            plain = g.Game(policy, seed, shock=shock, **v).run()
            game = Recorder(policy, seed, shock, detail=seed == 0, **v)
            seen = game.run()
            for k in plain:
                if k in ("before", "after", "modes"):
                    assert plain[k] == seen[k], (arm, seed, k)
                else:
                    assert abs(plain[k] - seen[k]) < 1e-9, (arm, seed, k, plain[k], seen[k])
            mapping = {"commute": "commute", "low_cash": "low_cash", "watch_commute": "watch_commute", "other_commute": "other_commute", "revenue": "revenue"}
            for mine, theirs in mapping.items():
                worst = max(worst, abs(tail(game.series[mine]) - plain[theirs]))
            assert sum(game.series["left"][g.LINE_OPENS + 1:]) == plain["left"], (arm, seed, "left", sum(game.series["left"][g.LINE_OPENS + 1:]), plain["left"])
            assert sum(game.series["moves"][g.LINE_OPENS + 1:]) == plain["moves"], (arm, seed, "moves")
            assert sum(game.series["blocked_low"][g.LINE_OPENS + 1:]) == plain["blocked_low"], (arm, seed, "blocked_low")
            print(arm, seed, "identical to plain game; frames", len(game.series["commute"]), "worst tail gap", f"{worst:.2e}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        check()
        sys.exit()
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    jobs = [(arm, s) for arm in ARMS for s in range(seeds)]
    per_arm = {arm: [None] * seeds for arm in ARMS}
    with mp.Pool(8) as pool:
        for i, r in enumerate(pool.imap_unordered(play, jobs, chunksize=4)):
            per_arm[r["arm"]][r["seed"]] = r
            if i % 40 == 0:
                print("done", i, "of", len(jobs), flush=True)
    series_keys = list(per_arm["A"][0]["series"])
    monthly = {arm: {k: {"m": [round(avg([r["series"][k][i] for r in rs]), 3) for i in range(g.MONTHS + 1)],
                         "h": [round(half([r["series"][k][i] for r in rs]), 3) for i in range(g.MONTHS + 1)]} for k in series_keys}
               for arm, rs in per_arm.items()}
    zones = {arm: {z: {k: [round(avg([r["zones"][z][k][i] for r in rs]), 3) for i in range(g.MONTHS + 1)] for k in ("n", "low", "vac", "rent", "commute")} for z in ZONE_IDS} for arm, rs in per_arm.items()}
    tails = {arm: {k: round(avg([tail(r["series"][k]) for r in rs]), 3) for k in series_keys} for arm, rs in per_arm.items()}
    effect = {k: effects(per_arm, lambda r, key=k: tail(r["series"][key])) for k in series_keys}
    effect_by_month = {k: [effects(per_arm, lambda r, key=k, at=i: r["series"][key][at]) for i in range(g.MONTHS + 1)] for k in ("watch_commute", "watch_rent", "other_rent", "rev_in", "mode_in_subway", "inq_in", "cum_in", "cum_moves", "cum_left", "cum_blocked", "low_cash")}
    zone_effect = {z: {k: effects(per_arm, lambda r, zone=z, key=k: tail(r["zones"][zone][key])) for k in ("n", "vac", "rent", "commute")} for z in ZONE_IDS}
    ledger = {}
    for bucket in per_arm["A"][0]["ledger"]:
        ledger[bucket] = {m: {"level": {arm: round(avg([r["ledger"][bucket][m] for r in rs]), 3) for arm, rs in per_arm.items()},
                              "effect": effects(per_arm, lambda r, b=bucket, key=m: r["ledger"][b][key])} for m in ("n", "commute", "rent", "fare", "burden")}
    flows = {arm: [[round(avg([r["flow"][i][j] for r in rs]), 2) for j in range(len(ZONE_IDS))] for i in range(len(ZONE_IDS))] for arm, rs in per_arm.items()}
    totals = {arm: {k: round(avg([r["out"][k] for r in rs]), 3) for k in ("commute", "low_commute", "watch_commute", "other_commute", "watch_share", "watch_low", "low_cash", "low_burden", "revenue", "moves", "left", "blocked_low", "watch_rent", "other_rent")} for arm, rs in per_arm.items()}
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis")
    json.dump(dict(seeds=seeds, shock=SHOCK, watch=WATCH, months=g.MONTHS, opens=g.LINE_OPENS, tail=TAIL, zone_ids=ZONE_IDS, monthly=monthly, zones=zones, tails=tails, effect=effect, effect_by_month=effect_by_month, zone_effect=zone_effect, ledger=ledger, flows=flows, totals=totals),
              open(os.path.join(here, "viz_v06_data.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    replay = {arm: rs[REPLAY_SEED]["detail"] for arm, rs in per_arm.items()}
    replay = dict(seed=REPLAY_SEED, types=g.TYPES, modes=MODES, classes=[g.CLASS[m] for m in MODES], arms=replay)
    json.dump(replay, open(os.path.join(here, "viz_v06_replay.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("totals")
    for k in totals["A"]:
        print(f"{k:15}", *(f"{totals[a][k]:12.3f}" for a in ("A", "A0", "B", "C")))
    print("seeds", seeds)
