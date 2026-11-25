"""Lease Day v0.1: a rule-only trial of the renter and landlord game. No LLM and no real data."""
import random
import statistics as st

ZONES = {"A": {"commute": 20, "fare": 4, "rooms": 40, "rent": 2000},
         "B": {"commute": 45, "fare": 6, "rooms": 50, "rent": 1500},
         "C": {"commute": 80, "fare": 9, "rooms": 60, "rent": 1100}}
ORDER = {"A": 0, "B": 1, "C": 2}
WORKDAYS = 26
N_TENANTS = 120
MONTHS = 36
SHOCK_MONTH = 12
SHOCK_ROOMS = 25
CHURN = 0.02
LISTINGS_SEEN = 5
MAX_BURDEN = 0.5
MOBILITY = {"high": {"months": 6, "move_cost": 500}, "low": {"months": 12, "move_cost": 2500}}


class Room:
    def __init__(self, zone, rent):
        self.zone, self.rent, self.tenant, self.vacant_for = zone, rent, None, 0


class Tenant:
    def __init__(self, rng):
        self.income = rng.choice([4000, 5000, 6000, 7000, 8000, 9000])
        self.room, self.expires, self.first_zone = None, 0, None

    def commute_cost(self, zone):
        z = ZONES[zone]
        hours = 2 * WORKDAYS * z["commute"] / 60
        value_per_hour = 0.5 * self.income / 260
        return hours * value_per_hour + 2 * WORKDAYS * z["fare"]


def zone_vacancy(rooms, zone):
    here = [r for r in rooms if r.zone == zone]
    return sum(r.tenant is None for r in here) / len(here) if here else 0.0


def raise_rate(vacancy):
    if vacancy < 0.05:
        return 0.08
    if vacancy < 0.10:
        return 0.04
    if vacancy < 0.20:
        return 0.01
    return -0.02


def quote(rate, months, landlord_rule):
    # "per_lease": the same percentage at every renewal. "per_year": scaled to the lease length.
    return rate if landlord_rule == "per_lease" else rate * months / 12


def choose(t, rooms, rng, mob, stay_rent=None):
    vacant = [r for r in rooms if r.tenant is None]
    seen = rng.sample(vacant, min(LISTINGS_SEEN, len(vacant)))
    options = []
    if stay_rent is not None and stay_rent <= MAX_BURDEN * t.income:
        options.append((stay_rent + t.commute_cost(t.room.zone), t.room))
    for r in seen:
        if r.rent <= MAX_BURDEN * t.income:
            options.append((r.rent + t.commute_cost(r.zone) + mob["move_cost"] / mob["months"], r))
    return min(options, key=lambda o: o[0])[1] if options else None


def run(mobility, supply, landlord_rule, seed):
    rng = random.Random(seed)
    mob = MOBILITY[mobility]
    rooms = [Room(z, d["rent"]) for z, d in ZONES.items() for _ in range(d["rooms"])]
    tenants = []
    for _ in range(N_TENANTS):
        t = Tenant(rng)
        tenants.append(t)
    for t in sorted(tenants, key=lambda x: -x.income):
        r = choose(t, rooms, rng, mob)
        if r is None:
            continue
        r.tenant, t.room = t, r
        t.first_zone = r.zone
        t.expires = rng.randrange(mob["months"])
    tenants = [t for t in tenants if t.room]
    left, outward, inward, moves = 0, 0, 0, 0
    tail = {"burden": [], "commute": [], "rent": [], "revenue": [], "vacant": []}

    def place(t, target, month):
        nonlocal outward, inward, moves
        old = t.room
        if old is target:
            t.expires = month + mob["months"]
            return
        if old is not None:
            old.tenant = None
            old.vacant_for = 0
            old.rent *= 1 + quote(raise_rate(zone_vacancy(rooms, old.zone)), mob["months"], landlord_rule)
            if month >= SHOCK_MONTH:
                moves += 1
                outward += ORDER[target.zone] > ORDER[old.zone]
                inward += ORDER[target.zone] < ORDER[old.zone]
        target.tenant, t.room = t, target
        t.expires = month + mob["months"]

    for month in range(MONTHS):
        if month == SHOCK_MONTH and supply == "tight":
            removable = sorted((r for r in rooms if r.zone == "A"), key=lambda r: r.rent)[:SHOCK_ROOMS]
            for r in removable:
                rooms.remove(r)
                if r.tenant:
                    t = r.tenant
                    t.room, t.expires = None, month
                    r.tenant = None
                    target = choose(t, rooms, rng, mob)
                    if target is None:
                        tenants.remove(t)
                        left += 1
                    else:
                        target.tenant, t.room = t, target
                        t.expires = month + mob["months"]
                        outward += ORDER[target.zone] > 0
                        moves += 1
        for r in rooms:
            if r.tenant is None:
                r.vacant_for += 1
                if r.vacant_for > 1:
                    r.rent *= 0.97
        for t in [x for x in tenants if rng.random() < CHURN]:
            t.room.tenant = None
            t.room.vacant_for = 0
            tenants.remove(t)
            n = Tenant(rng)
            target = choose(n, rooms, rng, mob)
            if target is not None:
                target.tenant, n.room = n, target
                n.first_zone, n.expires = target.zone, month + mob["months"]
                tenants.append(n)
        for t in list(tenants):
            if t.expires > month:
                continue
            rate = quote(raise_rate(zone_vacancy(rooms, t.room.zone)), mob["months"], landlord_rule)
            new_rent = t.room.rent * (1 + rate)
            target = choose(t, rooms, rng, mob, stay_rent=new_rent)
            if target is None:
                t.room.tenant = None
                t.room.vacant_for = 0
                tenants.remove(t)
                if month >= SHOCK_MONTH:
                    left += 1
                continue
            if target is t.room:
                t.room.rent = new_rent
            place(t, target, month)
        if month >= MONTHS - 12:
            tail["burden"].append(st.mean(t.room.rent / t.income for t in tenants))
            tail["commute"].append(st.mean(ZONES[t.room.zone]["commute"] for t in tenants))
            tail["rent"].append(st.mean(t.room.rent for t in tenants))
            tail["revenue"].append(sum(t.room.rent for t in tenants) / len(rooms))
            tail["vacant"].append(sum(r.tenant is None for r in rooms) / len(rooms))
    return {"burden": st.mean(tail["burden"]), "commute": st.mean(tail["commute"]), "rent": st.mean(tail["rent"]),
            "revenue": st.mean(tail["revenue"]), "vacant": st.mean(tail["vacant"]),
            "outward": outward, "inward": inward, "moves": moves, "left": left}


if __name__ == "__main__":
    SEEDS = 300
    for rule in ["per_lease", "per_year"]:
        print(f"\nlandlord rule = {rule}")
        print(f"{'mobility':8} {'supply':6} {'rent':>6} {'burden':>7} {'commute':>8} {'outward':>8} {'inward':>7} {'moves':>6} {'left':>5} {'vacant':>7} {'revenue':>8}")
        for mobility in ["high", "low"]:
            for supply in ["slack", "tight"]:
                rs = [run(mobility, supply, rule, s) for s in range(SEEDS)]
                m = lambda k: st.mean(r[k] for r in rs)
                print(f"{mobility:8} {supply:6} {m('rent'):6.0f} {m('burden'):7.3f} {m('commute'):8.1f} {m('outward'):8.1f} {m('inward'):7.1f} {m('moves'):6.1f} {m('left'):5.1f} {m('vacant'):7.3f} {m('revenue'):8.0f}")
