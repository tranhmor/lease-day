"""Lease Day v0.2: two job centres and job changes, so moving can shorten a commute. Rule-only, no LLM, no real data."""
import random
import statistics as st

ROOMS = {"A": (40, 2000), "B": (50, 1500), "C": (60, 1100)}
POS = {"A": 0, "B": 1, "C": 2}
MINUTES = {0: 15, 1: 40, 2: 75}
FARE = {0: 3, 1: 5, 2: 8}
JOB_SHARE_A = 0.6
JOB_CHANGE = 0.05
WORKDAYS = 26
N_TENANTS = 120
MONTHS = 36
SHOCK_MONTH = 12
CHURN = 0.02
LISTINGS_SEEN = 5
MAX_BURDEN = 0.35
MOBILITY = {"high": {"months": 6, "move_cost": 500}, "low": {"months": 12, "move_cost": 2500}}


def gap(a, b):
    return abs(POS[a] - POS[b])


class Room:
    def __init__(self, zone, rent):
        self.zone, self.rent, self.tenant, self.vacant_for = zone, rent, None, 0


class Tenant:
    def __init__(self, rng):
        self.income = rng.choice([4000, 5000, 6000, 7000, 8000, 9000])
        self.job = "A" if rng.random() < JOB_SHARE_A else "C"
        self.room, self.expires = None, 0
        self.log = []

    def minutes(self, zone):
        return MINUTES[gap(zone, self.job)]

    def commute_cost(self, zone):
        d = gap(zone, self.job)
        hours = 2 * WORKDAYS * MINUTES[d] / 60
        return hours * 0.5 * self.income / 260 + 2 * WORKDAYS * FARE[d]


def vacancy(rooms, zone):
    here = [r for r in rooms if r.zone == zone]
    return sum(r.tenant is None for r in here) / len(here) if here else 0.0


def rate(v):
    return 0.08 if v < 0.05 else 0.04 if v < 0.10 else 0.01 if v < 0.20 else -0.02


def adj(r, mob, rule):
    return r if rule == "per_lease" else r * mob["months"] / 12


def best(t, rooms, rng, mob, stay_rent=None):
    vacant = [r for r in rooms if r.tenant is None]
    options = []
    if stay_rent is not None and stay_rent <= MAX_BURDEN * t.income:
        options.append((stay_rent + t.commute_cost(t.room.zone), t.room))
    for r in rng.sample(vacant, min(LISTINGS_SEEN, len(vacant))):
        if r.rent <= MAX_BURDEN * t.income:
            options.append((r.rent + t.commute_cost(r.zone) + mob["move_cost"] / mob["months"], r))
    return min(options, key=lambda o: o[0]) if options else (None, None)


def run(mobility, shock_rooms, rule, seed, trace=False):
    rng = random.Random(seed)
    mob = MOBILITY[mobility]
    rooms = [Room(z, rent) for z, (n, rent) in ROOMS.items() for _ in range(n)]
    tenants = []
    for t in sorted((Tenant(rng) for _ in range(N_TENANTS)), key=lambda x: -x.income):
        _, r = best(t, rooms, rng, mob)
        if r is not None:
            r.tenant, t.room = t, r
            t.expires = rng.randrange(mob["months"])
            tenants.append(t)
    start = len(tenants)
    left = moves = breaks = 0
    tail = {k: [] for k in ["burden", "commute", "rent", "long", "match", "income_low_commute"]}
    focus = next((t for t in tenants if t.income == 6000 and t.job == "A" and t.room.zone == "A"), None) if trace else None

    def vacate(room, month):
        room.tenant = None
        room.vacant_for = 0
        room.rent *= 1 + adj(rate(vacancy(rooms, room.zone)), mob, rule)

    for month in range(MONTHS):
        if month == SHOCK_MONTH and shock_rooms:
            for r in sorted((x for x in rooms if x.zone == "A"), key=lambda x: x.rent)[:shock_rooms]:
                rooms.remove(r)
                t = r.tenant
                if t is None:
                    continue
                old_zone, old_rent = r.zone, r.rent
                t.room, r.tenant = None, None
                _, target = best(t, rooms, rng, mob)
                if target is None:
                    tenants.remove(t)
                    left += 1
                    if t is focus:
                        t.log.append((month, "demolished, left the city"))
                else:
                    target.tenant, t.room = t, target
                    t.expires = month + mob["months"]
                    moves += 1
                    if t is focus:
                        t.log.append((month, f"room demolished, moved {old_zone} to {target.zone}, rent {old_rent:.0f} to {target.rent:.0f}, commute {t.minutes(target.zone)} min"))
        for r in rooms:
            if r.tenant is None:
                r.vacant_for += 1
                if r.vacant_for > 1:
                    r.rent *= 0.97
        for t in [x for x in tenants if rng.random() < CHURN and x is not focus]:
            room = t.room
            tenants.remove(t)
            vacate(room, month)
            n = Tenant(rng)
            _, target = best(n, rooms, rng, mob)
            if target is not None:
                target.tenant, n.room = n, target
                n.expires = month + mob["months"]
                tenants.append(n)
        for t in list(tenants):
            if rng.random() >= JOB_CHANGE:
                continue
            t.job = "C" if t.job == "A" else "A"
            if t is focus:
                t.log.append((month, f"job moved to {t.job}, commute now {t.minutes(t.room.zone)} min"))
            remaining = max(0, t.expires - month)
            if remaining and gap(t.room.zone, t.job) > 0:
                _, target = best(t, rooms, rng, mob)
                if target is None or target is t.room:
                    continue
                saving = (t.room.rent + t.commute_cost(t.room.zone)) - (target.rent + t.commute_cost(target.zone))
                if saving * remaining > t.room.rent + mob["move_cost"]:
                    old = t.room
                    vacate(old, month)
                    target.tenant, t.room = t, target
                    t.expires = month + mob["months"]
                    moves += 1
                    breaks += 1
                    if t is focus:
                        t.log.append((month, f"broke lease, moved {old.zone} to {target.zone}, rent {target.rent:.0f}, commute {t.minutes(target.zone)} min"))
        for t in list(tenants):
            if t.expires > month:
                continue
            quote = t.room.rent * (1 + adj(rate(vacancy(rooms, t.room.zone)), mob, rule))
            _, target = best(t, rooms, rng, mob, stay_rent=quote)
            if target is None:
                old = t.room
                tenants.remove(t)
                vacate(old, month)
                left += 1
                if t is focus:
                    t.log.append((month, f"quoted {quote:.0f}, nothing affordable, left the city"))
            elif target is t.room:
                if t is focus:
                    t.log.append((month, f"quoted {quote:.0f} (was {t.room.rent:.0f}), stayed in {t.room.zone}"))
                t.room.rent = quote
                t.expires = month + mob["months"]
            else:
                old = t.room
                vacate(old, month)
                target.tenant, t.room = t, target
                t.expires = month + mob["months"]
                moves += 1
                if t is focus:
                    t.log.append((month, f"quoted {quote:.0f}, moved {old.zone} to {target.zone}, rent {target.rent:.0f}, commute {t.minutes(target.zone)} min"))
        if month >= MONTHS - 12:
            tail["burden"].append(st.mean(t.room.rent / t.income for t in tenants))
            tail["commute"].append(st.mean(t.minutes(t.room.zone) for t in tenants))
            tail["rent"].append(st.mean(t.room.rent for t in tenants))
            tail["long"].append(st.mean(t.minutes(t.room.zone) >= 60 for t in tenants))
            tail["match"].append(st.mean(t.room.zone == t.job for t in tenants))
            low = [t.minutes(t.room.zone) for t in tenants if t.income <= 5000]
            tail["income_low_commute"].append(st.mean(low) if low else 0)
    out = {k: st.mean(v) for k, v in tail.items()}
    out.update(left=left, moves=moves, breaks=breaks, n_end=len(tenants), n_start=start)
    if trace:
        out["trace"] = focus.log if focus else []
        out["focus"] = (focus.income, focus.job) if focus else None
    return out


if __name__ == "__main__":
    SEEDS = 300
    for rule in ["per_lease", "per_year"]:
        print(f"\nlandlord rule = {rule}")
        print(f"{'mobility':8} {'shock':>5} {'rent':>6} {'burden':>7} {'commute':>8} {'>=60min':>8} {'match':>6} {'lowinc':>7} {'moves':>6} {'breaks':>7} {'left':>5} {'end_n':>6}")
        for mobility in ["high", "low"]:
            for shock in [0, 25]:
                rs = [run(mobility, shock, rule, s) for s in range(SEEDS)]
                m = lambda k: st.mean(r[k] for r in rs)
                print(f"{mobility:8} {shock:5d} {m('rent'):6.0f} {m('burden'):7.3f} {m('commute'):8.1f} {m('long'):8.3f} {m('match'):6.3f} {m('income_low_commute'):7.1f} {m('moves'):6.1f} {m('breaks'):7.1f} {m('left'):5.1f} {m('n_end'):6.1f}")
    print("\nhigh minus low, by rooms removed (200 seeds)")
    print(f"{'rule':10} {'rooms':>5} {'d_rent':>7} {'d_commute':>10} {'d_left':>7}")
    for rule in ["per_lease", "per_year"]:
        for shock in [0, 10, 20, 25, 28]:
            hi = [run("high", shock, rule, s) for s in range(200)]
            lo = [run("low", shock, rule, s) for s in range(200)]
            d = lambda k: st.mean(r[k] for r in hi) - st.mean(r[k] for r in lo)
            print(f"{rule:10} {shock:5d} {d('rent'):7.0f} {d('commute'):10.1f} {d('left'):7.1f}")
    print("\none tenant's log, high mobility, 25 rooms removed, per_lease")
    for s in range(50):
        r = run("high", 25, "per_lease", s, trace=True)
        if r["focus"] and len(r["trace"]) >= 5 and any("demolished" in e[1] for e in r["trace"]):
            print("seed", s, "income, first job:", r["focus"])
            for e in r["trace"]:
                print(" month", e[0] + 1, e[1])
            break
