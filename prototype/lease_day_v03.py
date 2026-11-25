"""Lease Day v0.3: a new line changes travel, travel changes room choice, choice changes rent, rent changes travel.

Rule-only trial with placeholder numbers. No LLM and no real data.
Arms: no line; line with rents frozen; line with rents responding.
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


def key(a, b):
    return "".join(sorted(a + b))


class Room:
    def __init__(self, zone, rent):
        self.zone, self.rent, self.tenant, self.vacant_for = zone, rent, None, 0


class Tenant:
    def __init__(self, rng):
        self.income = rng.choice([4000, 5000, 6000, 7000, 8000, 9000])
        self.job = "A" if rng.random() < JOB_SHARE_A else "C"
        self.room, self.expires = None, 0


class Game:
    def __init__(self, arm, landlord, seed):
        self.arm, self.landlord = arm, landlord
        self.rng = random.Random(seed)
        self.minutes = MINUTES_BEFORE
        self.line_open = False
        self.rooms = [Room(z, rent) for z, (n, rent) in ROOMS.items() for _ in range(n)]
        self.tenants = []

    @property
    def frozen(self):
        return self.arm == "frozen" and self.line_open

    def commute(self, t, zone):
        return self.minutes[key(zone, t.job)]

    def commute_cost(self, t, zone):
        hours = 2 * WORKDAYS * self.commute(t, zone) / 60
        return hours * 0.5 * t.income / 260 + 2 * WORKDAYS * FARE[key(zone, t.job)]

    def vacancy(self, zone):
        here = [r for r in self.rooms if r.zone == zone]
        return sum(r.tenant is None for r in here) / len(here)

    @staticmethod
    def market_rate(v):
        return 0.06 if v < 0.04 else 0.02 if v < 0.08 else -0.01 if v < 0.12 else -0.04

    def renewal(self, room):
        if self.frozen:
            return room.rent
        r = self.market_rate(self.vacancy(room.zone))
        if self.landlord == "stayer_discount":
            if self.rng.random() < 0.30:
                return room.rent
            r *= 0.5
        return room.rent * (1 + r)

    def vacate(self, room):
        room.tenant = None
        room.vacant_for = 0
        if not self.frozen:
            room.rent *= 1 + self.market_rate(self.vacancy(room.zone))

    def best(self, t, stay_rent=None, see_all=False):
        vacant = [r for r in self.rooms if r.tenant is None]
        options = []
        if stay_rent is not None and stay_rent <= MAX_BURDEN * t.income:
            options.append((stay_rent + self.commute_cost(t, t.room.zone), t.room))
        seen = vacant if see_all else self.rng.sample(vacant, min(LISTINGS_SEEN, len(vacant)))
        for r in seen:
            if r.rent <= MAX_BURDEN * t.income:
                options.append((r.rent + self.commute_cost(t, r.zone) + MOVE_COST / LEASE_MONTHS, r))
        return min(options, key=lambda o: o[0])[1] if options else None

    def place(self, t, room, month):
        room.tenant, t.room = t, room
        t.expires = month + LEASE_MONTHS

    def run(self):
        rng = self.rng
        for t in sorted((Tenant(rng) for _ in range(N_TENANTS)), key=lambda x: x.income):
            r = self.best(t, see_all=True)
            if r is not None:
                self.place(t, r, rng.randrange(LEASE_MONTHS) - LEASE_MONTHS)
                self.tenants.append(t)
        moves = left = 0
        tail = {k: [] for k in ["commute", "rent", "long", "burden", "low_commute", "low_burden", "low_in_c", "high_in_c", "low_cost"]}
        zone_rent_before = {}
        zone_rent_after = {z: [] for z in ROOMS}
        for month in range(MONTHS):
            if month == LINE_OPENS and self.arm != "no_line":
                self.minutes = MINUTES_AFTER
                self.line_open = True
            for r in self.rooms:
                if r.tenant is None:
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
                    t.job = "C" if t.job == "A" else "A"
            for t in list(self.tenants):
                if t.expires > month:
                    continue
                quote = self.renewal(t.room)
                target = self.best(t, stay_rent=quote)
                if target is None:
                    old = t.room
                    self.tenants.remove(t)
                    self.vacate(old)
                    left += month >= LINE_OPENS
                elif target is t.room:
                    t.room.rent = quote
                    t.expires = month + LEASE_MONTHS
                else:
                    self.vacate(t.room)
                    self.place(t, target, month)
                    moves += month >= LINE_OPENS
            if month == LINE_OPENS - 1:
                for z in ROOMS:
                    zone_rent_before[z] = st.mean(r.rent for r in self.rooms if r.zone == z)
            if month >= MONTHS - 12:
                low = [t for t in self.tenants if t.income <= 5000]
                high = [t for t in self.tenants if t.income >= 8000]
                tail["commute"].append(st.mean(self.commute(t, t.room.zone) for t in self.tenants))
                tail["rent"].append(st.mean(t.room.rent for t in self.tenants))
                tail["long"].append(st.mean(self.commute(t, t.room.zone) >= 60 for t in self.tenants))
                tail["burden"].append(st.mean(t.room.rent / t.income for t in self.tenants))
                tail["low_commute"].append(st.mean(self.commute(t, t.room.zone) for t in low))
                tail["low_burden"].append(st.mean(t.room.rent / t.income for t in low))
                tail["low_cost"].append(st.mean(t.room.rent + self.commute_cost(t, t.room.zone) for t in low))
                tail["low_in_c"].append(st.mean(t.room.zone == "C" for t in low))
                tail["high_in_c"].append(st.mean(t.room.zone == "C" for t in high))
                for z in ROOMS:
                    zone_rent_after[z].append(st.mean(r.rent for r in self.rooms if r.zone == z))
        out = {k: st.mean(v) for k, v in tail.items()}
        out.update(moves=moves, left=left, n_end=len(self.tenants))
        for z in ROOMS:
            out[f"rent_{z}"] = st.mean(zone_rent_after[z])
            out[f"before_{z}"] = zone_rent_before[z]
        return out


def batch(arm, landlord, seeds):
    rs = [Game(arm, landlord, s).run() for s in range(seeds)]
    keys = rs[0].keys()
    return {k: st.mean(r[k] for r in rs) for k in keys}


if __name__ == "__main__":
    SEEDS = 300
    for landlord in ["stayer_discount", "same"]:
        print(f"\nlandlord = {landlord}")
        print(f"{'arm':8} {'rent':>5} {'commute':>8} {'>=60':>6} {'burden':>7} | {'low:cmt':>8} {'burden':>7} {'cost':>6} {'inC':>6} | {'hi:inC':>7} | {'A':>5} {'B':>5} {'C':>5} | {'moves':>6} {'left':>5} {'n':>6}")
        for arm in ["no_line", "frozen", "full"]:
            m = batch(arm, landlord, SEEDS)
            print(f"{arm:8} {m['rent']:5.0f} {m['commute']:8.1f} {m['long']:6.3f} {m['burden']:7.3f} | {m['low_commute']:8.1f} {m['low_burden']:7.3f} {m['low_cost']:6.0f} {m['low_in_c']:6.3f} | {m['high_in_c']:7.3f} | {m['rent_A']:5.0f} {m['rent_B']:5.0f} {m['rent_C']:5.0f} | {m['moves']:6.1f} {m['left']:5.1f} {m['n_end']:6.1f}")
            print("  rents just before the line:", {z: round(m[f"before_{z}"]) for z in ROOMS})
