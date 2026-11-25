"""Lease Day v0.4: a policy sandbox on top of the mobility and rent loop.

Rule-only trial with placeholder numbers. No LLM and no real data.
Every policy starts when the new line opens. Budgets are set to be roughly equal across policies.
"""
import random
import statistics as st

ROOMS = {"A": (35, 2000), "B": (40, 1500), "C": (55, 1100)}
MINUTES_BEFORE = {"AA": 15, "BB": 15, "CC": 15, "AB": 40, "BC": 40, "AC": 75}
MINUTES_AFTER = {"AA": 15, "BB": 15, "CC": 15, "AB": 40, "BC": 30, "AC": 45}
FARE = {"AA": 3, "BB": 3, "CC": 3, "AB": 5, "BC": 5, "AC": 8}
JOB_SHARE_A = 0.6
JOB_CHANGE = 0.05
WORKDAYS = 26
N_TENANTS = 120
MONTHS = 60
LINE_OPENS = 24
CHURN = 0.02
LISTINGS_SEEN = 5
MAX_BURDEN = 0.35
LEASE_MONTHS = 12
MOVE_COST = 1000
LOW_INCOME = 5000

POLICIES = {
    "no_line": {"line": False},
    "line_only": {},
    "renewal_cap": {"cap": 0.02},
    "subsidy": {"subsidy": 250, "capture": 0.0},
    "subsidy_captured": {"subsidy": 250, "capture": 0.6},
    "near_job_rooms": {"public_rooms": 20, "public_discount": 0.3},
    "free_fare": {"free_fare": True},
}


def key(a, b):
    return "".join(sorted(a + b))


class Room:
    def __init__(self, zone, rent, public=False):
        self.zone, self.rent, self.public = zone, rent, public
        self.tenant, self.vacant_for, self.loaded = None, 0, 0.0


class Tenant:
    def __init__(self, rng):
        self.income = rng.choice([4000, 5000, 6000, 7000, 8000, 9000])
        self.job = "A" if rng.random() < JOB_SHARE_A else "C"
        self.room, self.expires = None, 0

    @property
    def low(self):
        return self.income <= LOW_INCOME


class Game:
    def __init__(self, policy, landlord, seed):
        self.p, self.landlord = POLICIES[policy], landlord
        self.rng = random.Random(seed)
        self.minutes = MINUTES_BEFORE
        self.active = False
        self.rooms = [Room(z, rent) for z, (n, rent) in ROOMS.items() for _ in range(n)]
        self.tenants = []

    def fare(self, t, zone):
        if self.active and self.p.get("free_fare") and t.low:
            return 0
        return FARE[key(zone, t.job)]

    def commute(self, t, zone):
        return self.minutes[key(zone, t.job)]

    def commute_cost(self, t, zone):
        hours = 2 * WORKDAYS * self.commute(t, zone) / 60
        return hours * 0.5 * t.income / 260 + 2 * WORKDAYS * self.fare(t, zone)

    def net(self, t, rent, room):
        if self.active and t.low and not room.public:
            return rent - self.p.get("subsidy", 0)
        return rent

    def load(self, t, room):
        if self.active and t.low and not room.public and room.loaded == 0:
            return self.p.get("subsidy", 0) * self.p.get("capture", 0)
        return 0.0

    def private(self, zone):
        return [r for r in self.rooms if r.zone == zone and not r.public]

    def vacancy(self, zone):
        here = self.private(zone)
        return sum(r.tenant is None for r in here) / len(here)

    @staticmethod
    def market_rate(v):
        return 0.06 if v < 0.04 else 0.02 if v < 0.08 else -0.01 if v < 0.12 else -0.04

    def renewal(self, t):
        room = t.room
        if room.public:
            return room.rent
        r = self.market_rate(self.vacancy(room.zone))
        if self.landlord == "stayer_discount":
            r = 0.0 if self.rng.random() < 0.30 else r * 0.5
        if self.active and "cap" in self.p:
            r = min(r, self.p["cap"])
        return room.rent * (1 + r) + self.load(t, room)

    def vacate(self, room):
        room.tenant = None
        room.vacant_for = 0
        if room.public:
            return
        room.rent -= room.loaded
        room.loaded = 0.0
        room.rent *= 1 + self.market_rate(self.vacancy(room.zone))

    def best(self, t, stay_rent=None, see_all=False):
        vacant = [r for r in self.rooms if r.tenant is None and not r.public]
        options = []
        if stay_rent is not None and self.net(t, stay_rent, t.room) <= MAX_BURDEN * t.income:
            options.append((self.net(t, stay_rent, t.room) + self.commute_cost(t, t.room.zone), t.room))
        seen = vacant if see_all else self.rng.sample(vacant, min(LISTINGS_SEEN, len(vacant)))
        if t.low:
            seen = seen + [r for r in self.rooms if r.tenant is None and r.public]
        for r in seen:
            rent = self.net(t, r.rent + self.load(t, r), r)
            if rent <= MAX_BURDEN * t.income:
                options.append((rent + self.commute_cost(t, r.zone) + MOVE_COST / LEASE_MONTHS, r))
        return min(options, key=lambda o: o[0])[1] if options else None

    def place(self, t, room, month):
        extra = self.load(t, room)
        room.rent += extra
        room.loaded += extra
        room.tenant, t.room = t, room
        t.expires = month + LEASE_MONTHS

    def open_line(self):
        if self.p.get("line", True):
            self.minutes = MINUTES_AFTER
        self.active = True
        if self.p.get("public_rooms"):
            base = st.mean(r.rent for r in self.private("A"))
            for _ in range(self.p["public_rooms"]):
                self.rooms.append(Room("A", base * (1 - self.p["public_discount"]), public=True))

    def run(self):
        rng = self.rng
        for t in sorted((Tenant(rng) for _ in range(N_TENANTS)), key=lambda x: x.income):
            r = self.best(t, see_all=True)
            if r is not None:
                self.place(t, r, rng.randrange(LEASE_MONTHS) - LEASE_MONTHS)
                self.tenants.append(t)
        moves = left = 0
        tail = {k: [] for k in ["commute", "low_commute", "low_cost", "low_share", "high_share", "revenue", "public_cost", "subsidy_cost", "fare_cost", "vacant"]}
        for month in range(MONTHS):
            if month == LINE_OPENS:
                self.open_line()
            for r in self.rooms:
                if r.tenant is None and not r.public:
                    r.vacant_for += 1
                    if r.vacant_for > 1:
                        r.rent *= 0.97
            for t in [x for x in self.tenants if rng.random() < CHURN]:
                room = t.room
                self.tenants.remove(t)
                self.vacate(room)
                for _ in range(10):
                    n = Tenant(rng)
                    target = self.best(n)
                    if target is not None:
                        self.place(n, target, month)
                        self.tenants.append(n)
                        break
            for t in self.tenants:
                if rng.random() < JOB_CHANGE:
                    t.job = "C" if t.job == "A" else "A"
            for t in list(self.tenants):
                if t.expires > month:
                    continue
                quote = self.renewal(t)
                target = self.best(t, stay_rent=quote)
                if target is None:
                    old = t.room
                    self.tenants.remove(t)
                    self.vacate(old)
                    left += month >= LINE_OPENS
                elif target is t.room:
                    if not t.room.public:
                        t.room.loaded += self.load(t, t.room)
                    t.room.rent = quote
                    t.expires = month + LEASE_MONTHS
                else:
                    self.vacate(t.room)
                    self.place(t, target, month)
                    moves += month >= LINE_OPENS
            if month >= MONTHS - 12:
                low = [t for t in self.tenants if t.low]
                high = [t for t in self.tenants if t.income >= 8000]
                total = lambda t: self.net(t, t.room.rent, t.room) + self.commute_cost(t, t.room.zone)
                privates = [r for r in self.rooms if not r.public]
                mean_a = st.mean(r.rent for r in self.private("A"))
                tail["commute"].append(st.mean(self.commute(t, t.room.zone) for t in self.tenants))
                tail["low_commute"].append(st.mean(self.commute(t, t.room.zone) for t in low))
                tail["low_cost"].append(st.mean(total(t) for t in low))
                tail["low_share"].append(st.mean(total(t) / t.income for t in low))
                tail["high_share"].append(st.mean(total(t) / t.income for t in high))
                tail["revenue"].append(sum(r.rent for r in privates if r.tenant) / len(privates))
                tail["vacant"].append(sum(r.tenant is None for r in privates) / len(privates))
                tail["public_cost"].append(sum(mean_a - r.rent for r in self.rooms if r.public and r.tenant))
                tail["subsidy_cost"].append(self.p.get("subsidy", 0) * sum(not t.room.public for t in low))
                tail["fare_cost"].append(sum(2 * WORKDAYS * FARE[key(t.room.zone, t.job)] for t in low) if self.p.get("free_fare") else 0)
        out = {k: st.mean(v) for k, v in tail.items()}
        out.update(moves=moves, left=left, budget=out["public_cost"] + out["subsidy_cost"] + out["fare_cost"])
        return out


def batch(policy, landlord, seeds):
    rs = [Game(policy, landlord, s).run() for s in range(seeds)]
    return {k: st.mean(r[k] for r in rs) for k in rs[0]}


if __name__ == "__main__":
    SEEDS = 300
    for landlord in ["stayer_discount", "same"]:
        print(f"\nlandlord = {landlord}")
        print(f"{'policy':18} {'commute':>8} {'lowCmt':>7} {'lowCost':>8} {'lowShare':>9} {'hiShare':>8} {'revenue':>8} {'vacant':>7} {'budget':>7} {'moves':>6} {'left':>5}")
        rows = {}
        for name in POLICIES:
            m = batch(name, landlord, SEEDS)
            rows[name] = m
            print(f"{name:18} {m['commute']:8.1f} {m['low_commute']:7.1f} {m['low_cost']:8.0f} {m['low_share']:9.3f} {m['high_share']:8.3f} {m['revenue']:8.0f} {m['vacant']:7.3f} {m['budget']:7.0f} {m['moves']:6.1f} {m['left']:5.1f}")
        order = sorted((n for n in rows if n != "no_line"), key=lambda n: rows[n]["low_cost"])
        print("  rank by low-income total cost:", " > ".join(order))
