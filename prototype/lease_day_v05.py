"""Lease Day v0.5: the board calibrated to the Changping to Zhongguancun corridor.

Rule-only trial. No LLM.
From data: rent levels and low-rent shares (2020 census table 9-5), occupation mix of renters (table 9-10),
subway fares by distance (authors' code in the Beijing survey capsule).
Assumptions: travel times, the new line's saving, incomes by occupation, job shares, the penalty for low-rent
rooms, landlord rules and policy sizes. Zone B is a blend of A and C.
"""
import random
import statistics as st

ROOMS = {"A": {"low": (9, 700), "regular": (41, 3520)},
         "B": {"low": (10, 700), "regular": (20, 2900)},
         "C": {"low": (21, 700), "regular": (29, 2260)}}
MINUTES_BEFORE = {"AA": 20, "BB": 20, "CC": 20, "AB": 45, "BC": 35, "AC": 70}
MINUTES_AFTER = {"AA": 20, "BB": 20, "CC": 20, "AB": 35, "BC": 35, "AC": 55}
FARE = {"AA": 3, "BB": 3, "CC": 3, "AB": 5, "BC": 5, "AC": 6}
OCCUPATIONS = [(0.14, 4000, 6000), (0.512, 5000, 9000), (0.099, 8000, 14000), (0.216, 12000, 25000), (0.033, 20000, 35000)]
JOB_SHARE_A = 0.75
JOB_CHANGE = 0.05
WORKDAYS = 26
N_TENANTS = 120
MONTHS = 60
LINE_OPENS = 24
CHURN = 0.02
LISTINGS_SEEN = 5
MAX_BURDEN = 0.35
LEASE_MONTHS = 12
MOVE_COST = 1500
LOW_INCOME = 6000

POLICIES = {
    "no_line": {"line": False},
    "line_frozen": {"frozen": True},
    "line_only": {},
    "renewal_cap": {"cap": 0.02},
    "subsidy": {"subsidy": 250, "capture": 0.0},
    "subsidy_captured": {"subsidy": 250, "capture": 0.6},
    "near_job_rooms": {"public_rooms": 6, "public_rent": 1800},
    "free_fare": {"free_fare": True},
}


def key(a, b):
    return "".join(sorted(a + b))


class Room:
    def __init__(self, zone, tier, rent, public=False):
        self.zone, self.tier, self.rent, self.public = zone, tier, rent, public
        self.tenant, self.vacant_for, self.loaded = None, 0, 0.0


class Tenant:
    def __init__(self, rng):
        _, lo, hi = rng.choices(OCCUPATIONS, weights=[o[0] for o in OCCUPATIONS])[0]
        self.income = rng.randrange(lo, hi + 1, 500)
        self.job = "A" if rng.random() < JOB_SHARE_A else "C"
        self.room, self.expires = None, 0

    @property
    def low(self):
        return self.income <= LOW_INCOME

    @property
    def low_room_penalty(self):
        return max(200, 0.35 * self.income - 800)


class Game:
    def __init__(self, policy, landlord, seed):
        self.p, self.landlord = POLICIES[policy], landlord
        self.rng = random.Random(seed)
        self.minutes = MINUTES_BEFORE
        self.active = False
        self.rooms = [Room(z, tier, rent) for z, tiers in ROOMS.items() for tier, (n, rent) in tiers.items() for _ in range(n)]
        self.tenants = []

    @property
    def frozen(self):
        return self.active and self.p.get("frozen", False)

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

    def vacancy(self, room):
        here = [r for r in self.rooms if r.zone == room.zone and r.tier == room.tier and not r.public]
        return sum(r.tenant is None for r in here) / len(here)

    @staticmethod
    def market_rate(v):
        return 0.06 if v < 0.04 else 0.02 if v < 0.08 else -0.01 if v < 0.12 else -0.04

    def renewal(self, t):
        room = t.room
        if room.public or self.frozen:
            return room.rent
        r = self.market_rate(self.vacancy(room))
        if self.landlord == "stayer_discount":
            r = 0.0 if self.rng.random() < 0.30 else r * 0.5
        if self.active and "cap" in self.p:
            r = min(r, self.p["cap"])
        return room.rent * (1 + r) + self.load(t, room)

    def vacate(self, room):
        room.tenant = None
        room.vacant_for = 0
        if room.public or self.frozen:
            return
        room.rent -= room.loaded
        room.loaded = 0.0
        room.rent *= 1 + self.market_rate(self.vacancy(room))

    def score(self, t, room, rent, moving):
        extra = t.low_room_penalty if room.tier == "low" else 0
        return self.net(t, rent, room) + self.commute_cost(t, room.zone) + extra + (MOVE_COST / LEASE_MONTHS if moving else 0)

    def best(self, t, stay_rent=None, see_all=False):
        vacant = [r for r in self.rooms if r.tenant is None and not r.public]
        options = []
        if stay_rent is not None and self.net(t, stay_rent, t.room) <= MAX_BURDEN * t.income:
            options.append((self.score(t, t.room, stay_rent, False), t.room))
        seen = vacant if see_all else self.rng.sample(vacant, min(LISTINGS_SEEN, len(vacant)))
        if t.low:
            seen = seen + [r for r in self.rooms if r.tenant is None and r.public]
        for r in seen:
            rent = r.rent + self.load(t, r)
            if self.net(t, rent, r) <= MAX_BURDEN * t.income:
                options.append((self.score(t, r, rent, True), r))
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
        for _ in range(self.p.get("public_rooms", 0)):
            self.rooms.append(Room("A", "regular", self.p["public_rent"], public=True))

    def zone_rents(self):
        return {f"{z}_{tier}": st.mean(r.rent for r in self.rooms if r.zone == z and r.tier == tier and not r.public)
                for z in ROOMS for tier in ("low", "regular")}

    def run(self):
        rng = self.rng
        for t in sorted((Tenant(rng) for _ in range(N_TENANTS)), key=lambda x: x.income):
            r = self.best(t, see_all=True)
            if r is not None:
                self.place(t, r, rng.randrange(LEASE_MONTHS) - LEASE_MONTHS)
                self.tenants.append(t)
        seated = len(self.tenants)
        moves = left = 0
        before = {}
        tail = {k: [] for k in ["commute", "low_commute", "low_cost", "low_burden", "low_in_c", "high_in_c", "revenue", "vacant", "budget", "n"]}
        after = []
        for month in range(MONTHS):
            if month == LINE_OPENS:
                before = self.zone_rents()
                self.open_line()
            for r in self.rooms:
                if r.tenant is None and not r.public:
                    r.vacant_for += 1
                    if r.vacant_for > 1 and not self.frozen:
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
                    t.job = "A" if rng.random() < JOB_SHARE_A else "C"
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
                high = [t for t in self.tenants if t.income >= 12000]
                privates = [r for r in self.rooms if not r.public]
                total = lambda t: self.net(t, t.room.rent, t.room) + self.commute_cost(t, t.room.zone)
                mean_a = st.mean(r.rent for r in privates if r.zone == "A" and r.tier == "regular")
                public_cost = sum(mean_a - r.rent for r in self.rooms if r.public and r.tenant)
                subsidy_cost = self.p.get("subsidy", 0) * sum(not t.room.public for t in low)
                fare_cost = sum(2 * WORKDAYS * FARE[key(t.room.zone, t.job)] for t in low) if self.p.get("free_fare") else 0
                tail["commute"].append(st.mean(self.commute(t, t.room.zone) for t in self.tenants))
                tail["low_commute"].append(st.mean(self.commute(t, t.room.zone) for t in low))
                tail["low_cost"].append(st.mean(total(t) for t in low))
                tail["low_burden"].append(st.mean(self.net(t, t.room.rent, t.room) / t.income for t in low))
                tail["low_in_c"].append(st.mean(t.room.zone == "C" for t in low))
                tail["high_in_c"].append(st.mean(t.room.zone == "C" for t in high))
                tail["revenue"].append(sum(r.rent for r in privates if r.tenant) / len(privates))
                tail["vacant"].append(sum(r.tenant is None for r in privates) / len(privates))
                tail["budget"].append(public_cost + subsidy_cost + fare_cost)
                tail["n"].append(len(self.tenants))
                after.append(self.zone_rents())
        out = {k: st.mean(v) for k, v in tail.items()}
        out.update(moves=moves, left=left, seated=seated)
        for k in before:
            out["before_" + k] = before[k]
            out["after_" + k] = st.mean(a[k] for a in after)
        return out


def batch(policy, landlord, seeds):
    rs = [Game(policy, landlord, s).run() for s in range(seeds)]
    return {k: st.mean(r[k] for r in rs) for k in rs[0]}


if __name__ == "__main__":
    SEEDS = 300
    for landlord in ["stayer_discount", "same"]:
        print(f"\nlandlord = {landlord}")
        print(f"{'policy':17} {'cmt':>5} {'lowCmt':>6} {'lowCost':>7} {'lowBur':>6} {'lowC':>5} {'hiC':>5} {'rev':>5} {'vac':>5} {'budget':>6} {'moves':>5} {'left':>4} {'n':>5}")
        rows = {}
        for name in POLICIES:
            m = batch(name, landlord, SEEDS)
            rows[name] = m
            print(f"{name:17} {m['commute']:5.1f} {m['low_commute']:6.1f} {m['low_cost']:7.0f} {m['low_burden']:6.3f} {m['low_in_c']:5.2f} {m['high_in_c']:5.2f} {m['revenue']:5.0f} {m['vacant']:5.3f} {m['budget']:6.0f} {m['moves']:5.0f} {m['left']:4.1f} {m['n']:5.1f}")
        keys = [f"{z}_{t}" for z in ROOMS for t in ("low", "regular")]
        print("  seated at start:", round(rows["no_line"]["seated"], 1))
        print("  before line:", {k: round(rows["line_only"]["before_" + k]) for k in keys})
        print("  no line, end:", {k: round(rows["no_line"]["after_" + k]) for k in keys})
        print("  line, end   :", {k: round(rows["line_only"]["after_" + k]) for k in keys})
        order = sorted((n for n in rows if n not in ("no_line", "line_frozen")), key=lambda n: rows[n]["low_cost"])
        print("  rank by low-income cost:", " > ".join(order))
