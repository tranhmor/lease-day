"""Lease Day v0.6: rule agents on the CBD board (analysis/board_cbd_v01.json). No LLM.

Tenants follow tenant_rules_v01.md: hard money checks in code, then comfort and stretch lines. A rule agent treats the
stretch line as a limit; an LLM agent may cross it. All tenants work in the CBD, so job changes become arrivals and leavers.
From data: rents, room types, room stock, job mix, couple shares. Calibrated: mode constants, to the Beijing survey's mode shares
by distance (calibrate_modes.py). Assumptions: travel speeds, incomes within groups, the second earner, savings, room quality
penalties, car access, the gravity decay, landlord rules, policy sizes.
"""
import json
import math
import os
import random
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.join(HERE, "..", "analysis")
BOARD = json.load(open(os.path.join(ANALYSIS, "board_cbd_v01.json"), encoding="utf-8"))
ZONES = BOARD["zones"]
REPLAY = {z: v["replay_2015_2018"] for z, v in json.load(open(os.path.join(ANALYSIS, "zone_shock.json"), encoding="utf-8")).items()}
SHOCKS = {"none": {}, "replay": REPLAY, "east_express": {"Z05": 12, "Z11": 15}}
TYPES = ["低价房", "便宜单间", "合租单间", "整租"]
QUALITY = {"低价房": 1.0, "便宜单间": 0.5, "合租单间": 0.25, "整租": 0.0}
SUBWAY = ("地铁", "骑车接地铁")
PUBLIC_FARE = ("地铁", "公交直达", "公交换乘")

N_ROOMS = 1200
OCCUPANCY = 0.95
MONTHS = 60
LINE_OPENS = 24
CHURN = 0.02
LISTINGS_SEEN = 5
LEASE_MONTHS = 12
WORKDAYS = 26
FLOOR = 2000
MOVE_CASH = 500
MOVE_HASSLE = 1500
# Months paid before moving in: deposit plus first rent. 2 = 押一付一, 3 = 押一付二, 4 = 押一付三, the common form and the cap for
# rental firms (Beijing Housing Rental Regulation, art. 36). The shares by room type are assumptions; no survey was found.
UP_FRONT = {"低价房": ((2, 0.7), (3, 0.1), (4, 0.2)), "便宜单间": ((2, 0.5), (3, 0.2), (4, 0.3)), "合租单间": ((2, 0.3), (3, 0.2), (4, 0.5)), "整租": ((2, 0.1), (3, 0.1), (4, 0.8))}
PUBLIC_UP_FRONT = 2
COMFORT_WEIGHT = 0.5
BACKGROUND_VACANCY = 0.05
OUTSIDE_FLOOR = 0.90  # tenants working elsewhere take a room once its rent is this far below its starting rent
TAU = 40
DEMAND_K = 0.2  # landlords' response to inquiries; an assumption, not tuned to the real premium; 0 switches it off
INQUIRY_SAMPLE = 30  # rooms a searcher browses, let or not
DEMAND_CAP = 0.10  # largest yearly rent change from inquiries
INCOME = [("low", BOARD["work"]["income_mix"]["较低 4,000-7,000"], 4000, 7000), ("mid", BOARD["work"]["income_mix"]["中等 7,000-15,000"], 7000, 15000), ("high", BOARD["work"]["income_mix"]["较高 15,000-35,000"], 15000, 35000)]
LINES = {"low": (0.20, 0.40), "mid": (0.25, 0.40), "high": (0.25, 0.35)}
CAR = {"low": 0.40, "mid": 0.40, "high": 0.35}  # has a car and would drive to the CBD; set so car shares by income stay near the survey
COUPLE = {"low": 0.35, "mid": 0.42, "high": 0.46}  # Beijing survey: living with a partner, with or without children
SECOND_EARNER = 1.8
LOW_TOP, MID_TOP = 7000, 15000
CLASS = {"地铁": "subway", "骑车接地铁": "subway", "公交直达": "bus", "公交换乘": "bus", "电动车": "bike", "自行车": "bike", "步行": "walk", "私家车": "car", "打车": "taxi"}
ASC = {"subway": 0.0, "bus": 6.5, "bike": 40.2, "walk": 24.9, "car": -173.7, "taxi": -2.0}  # hours a month; from calibrate_modes.py
TASTE_SCALE = 50.0  # hours a month; from calibrate_modes.py
BIKE_TIRE = 2.0  # from calibrate_modes.py; extra minutes counted per minute beyond 30 on a bike or on foot
POLICIES = {
    "line_only": {},
    "frozen": {"frozen": True},
    "renewal_cap": {"cap": 0.02},
    "subsidy": {"subsidy": 250, "capture": 0.0},
    "subsidy_captured": {"subsidy": 250, "capture": 0.6},
    "near_job_rooms": {"public_rooms": 60, "public_rent": 1800},
    "free_fare": {"free_fare": True},
}


def largest_remainder(weights, total):
    scaled = [w * total / sum(weights) for w in weights]
    out = [math.floor(s) for s in scaled]
    for i in sorted(range(len(out)), key=lambda i: scaled[i] - out[i], reverse=True)[:total - sum(out)]:
        out[i] += 1
    return out


def allocate(tau=TAU, low_cost=1.0):
    weights = [z["renters_sample"] * math.exp(-z["options"]["地铁"]["min"] / tau) for z in ZONES]
    rooms = {}
    for z, n in zip(ZONES, largest_remainder(weights, N_ROOMS)):
        shares = [z["shares"][k] * (low_cost if k in TYPES[:2] else 1) for k in TYPES]
        for k, c in zip(TYPES, largest_remainder(shares, n)):
            rooms[(z["id"], k)] = c
    return rooms


class Room:
    __slots__ = ("zone", "kind", "rent", "public", "tenant", "vacant_for", "loaded", "start", "index", "up_front")

    def __init__(self, zone, kind, rent, public=False):
        self.zone, self.kind, self.rent, self.public = zone, kind, rent, public
        self.tenant, self.vacant_for, self.loaded, self.start, self.index = None, 0, 0.0, rent, 1.0
        self.up_front = PUBLIC_UP_FRONT


class Tenant:
    def __init__(self, rng, p, factor=1.0):
        worker, _, lo, hi = rng.choices(INCOME, weights=[g[1] for g in INCOME])[0]
        self.wage = rng.randrange(lo, hi + 1, 500)
        self.couple = rng.random() < COUPLE[worker]
        self.income = round(self.wage * (SECOND_EARNER if self.couple else 1))
        self.group = "low" if self.income <= LOW_TOP else "mid" if self.income < MID_TOP else "high"
        comfort, stretch = p.get("lines", LINES)[self.group]
        self.comfort = comfort + rng.uniform(-0.05, 0.05)
        self.stretch = stretch + rng.uniform(-0.05, 0.05)
        self.savings = self.income * rng.uniform(1, 3) * p.get("savings", 1)
        self.scale(p.get("income_scale", 1) * factor)
        self.car = rng.random() < CAR[self.group]
        self.taste = {k: -math.log(-math.log(rng.random())) for k in ASC}
        self.room, self.expires = None, 0

    def scale(self, m):
        self.wage *= m
        self.income *= m
        self.savings *= m
        self.cache = {}

    @property
    def low(self):
        return self.group == "low"

    @property
    def penalty(self):
        return max(200, 0.35 * self.income - 800)


class Game:
    def __init__(self, policy, seed, shock="replay", cbd_share=1.0, **variant):
        self.p = {**POLICIES[policy], **variant}
        self.rng = random.Random(seed)
        self.saved = {k: v * self.p.get("saving_scale", 1) for k, v in SHOCKS[shock].items()}
        self.cbd_share = cbd_share
        self.active = False
        self.options = {z["id"]: {m: dict(v) for m, v in z["options"].items()} for z in ZONES}
        self.rents = {z["id"]: z["rents"] for z in ZONES}
        self.rooms = []
        self.count = {}
        terms = random.Random(seed + 11)
        for (zone, kind), n in allocate(self.p.get("tau", TAU), self.p.get("low_cost", 1.0)).items():
            base = self.rents[zone][kind]
            self.rooms += [Room(zone, kind, base * self.rng.uniform(0.9, 1.1)) for _ in range(n)]
            for room in self.rooms[-n:] if n else []:
                months, shares = zip(*UP_FRONT[kind])
                room.up_front = self.p.get("up_front") or terms.choices(months, weights=shares)[0]
            self.count[(zone, kind)] = [n, n]
        self.tenants = []
        self.blocked = {"low": 0, "mid": 0, "high": 0}
        self.city_rent, self.city_wage = 1.0, 1.0
        self.month = 0
        self.browse_rng = random.Random(seed + 7)
        self.inquiries = {cell: [0] * MONTHS for cell in self.count}

    @property
    def frozen(self):
        return self.active and self.p.get("frozen", False)

    def travel(self, t, zone, net=None):
        """Best way to work. With net and afford_modes on, only modes that leave the monthly floor are considered."""
        budget = None
        if net is not None and self.p.get("afford_modes"):
            budget = t.income - net - FLOOR * self.city_wage
        got = t.cache.get(zone)
        if got and (budget is None or got[3] <= budget):
            return got
        hourly = self.p.get("vot", 0.5) * t.wage / 260
        best = None
        for mode, o in self.options[zone].items():
            if mode == "私家车" and not t.car:
                continue
            money = o["month"]
            if self.active and t.low and self.p.get("free_fare") and mode in SUBWAY + PUBLIC_FARE:
                money = 30 if mode == "骑车接地铁" else 0
            if budget is not None and money > budget:
                continue
            kind = CLASS[mode]
            felt = o["min"] + 5 * o.get("transfers", 0)
            if kind in ("bike", "walk"):
                felt += max(0, o["min"] - 30) * BIKE_TIRE
            hours = 2 * WORKDAYS * felt / 60 + ASC[kind] - TASTE_SCALE * t.taste[kind]
            cost = money + hours * hourly
            if best is None or cost < best[0]:
                best = (cost, mode, o["min"], money)
        if budget is None:
            t.cache[zone] = best
        return best

    def net(self, t, rent, room):
        if self.active and t.low and not room.public:
            return rent - self.p.get("subsidy", 0)
        return rent

    def load(self, t, room):
        if self.active and t.low and not room.public and room.loaded == 0:
            return self.p.get("subsidy", 0) * self.p.get("capture", 0)
        return 0.0

    def allowed(self, t, room, rent, moving):
        net = self.net(t, rent, room)
        if net > t.stretch * t.income:
            return False
        way = self.travel(t, room.zone, net)
        if way is None or t.income - net - way[3] < FLOOR * self.city_wage:
            return False
        return not moving or t.savings >= room.up_front * net + MOVE_CASH

    def score(self, t, room, rent, moving):
        net = self.net(t, rent, room)
        over = max(0.0, net - t.comfort * t.income) * COMFORT_WEIGHT
        return net + self.travel(t, room.zone, net)[0] + t.penalty * QUALITY[room.kind] + over + (MOVE_HASSLE / LEASE_MONTHS if moving else 0)

    def vacancy(self, room):
        total, empty = self.count[(room.zone, room.kind)]
        local = empty / max(total, 1)
        return self.cbd_share * local + (1 - self.cbd_share) * BACKGROUND_VACANCY

    def market_rate(self, v):
        if self.p.get("smooth"):
            return max(-0.04, 0.06 - v / 0.12 * 0.10) * self.p.get("rate_scale", 1)
        return 0.06 if v < 0.04 else 0.02 if v < 0.08 else -0.01 if v < 0.12 else -0.04

    def demand(self, room):
        """Yearly rent signal: inquiries over the last 12 months against the room type's own level before the line."""
        k = self.p.get("demand_k", DEMAND_K)
        if not k or self.month < LINE_OPENS:
            return 0.0
        counts = self.inquiries[(room.zone, room.kind)]
        before = sum(counts[LINE_OPENS - 12:LINE_OPENS])
        recent = sum(counts[self.month - 12:self.month])
        return max(-DEMAND_CAP, min(DEMAND_CAP, k * math.log((recent + 1) / (before + 1))))

    def browse(self, t, chosen):
        """A searcher also looks at rooms already let; one they would prefer counts as an inquiry for that room type."""
        for r in self.browse_rng.sample(self.rooms, INQUIRY_SAMPLE):
            if r.public or r is t.room:
                continue
            if self.allowed(t, r, r.rent, True) and self.score(t, r, r.rent, True) < chosen:
                self.inquiries[(r.zone, r.kind)][self.month] += 1

    def renewal(self, t):
        room = t.room
        if room.public or self.frozen:
            return room.rent
        if self.rng.random() < 0.30:
            return room.rent + self.load(t, room)
        r = (self.market_rate(self.vacancy(room)) + self.demand(room)) * self.p.get("stayer_share", 0.5)
        if self.active and "cap" in self.p:
            r = min(r, self.p["cap"])
        self.catch_up(room)
        return room.rent * (1 + r) + self.load(t, room)

    def catch_up(self, room):
        """Bring a room to the citywide rent trend when it is repriced."""
        room.rent *= self.city_rent / room.index
        room.index = self.city_rent

    def floor_rent(self, room):
        return room.start * self.p.get("floor", OUTSIDE_FLOOR) * self.city_rent

    def vacate(self, room):
        room.tenant = None
        room.vacant_for = 0
        if room.public:
            return
        self.count[(room.zone, room.kind)][1] += 1
        if self.frozen:
            return
        room.rent -= room.loaded
        room.loaded = 0.0
        self.catch_up(room)
        room.rent = max(self.floor_rent(room), room.rent * (1 + self.market_rate(self.vacancy(room)) + self.demand(room)))

    def place(self, t, room, month):
        extra = self.load(t, room)
        room.rent += extra
        room.loaded += extra
        room.tenant, t.room = t, room
        t.expires = month + LEASE_MONTHS
        if not room.public:
            self.count[(room.zone, room.kind)][1] -= 1

    def best(self, t, vacant, stay_rent=None, see_all=False):
        options = []
        if stay_rent is not None and self.allowed(t, t.room, stay_rent, False):
            options.append((self.score(t, t.room, stay_rent, False), t.room))
        within = [r for r in vacant if self.net(t, r.rent, r) <= t.stretch * t.income]
        seen = within if see_all else self.rng.sample(within, min(LISTINGS_SEEN, len(within)))
        if t.low:
            seen = seen + [r for r in self.public_rooms if r.tenant is None]
        for r in seen:
            rent = r.rent + self.load(t, r)
            if self.allowed(t, r, rent, True):
                options.append((self.score(t, r, rent, True), r))
        pick = min(options, key=lambda o: o[0]) if options else None
        if self.p.get("demand_k", DEMAND_K) and not see_all and not self.p.get("frozen"):
            self.browse(t, pick[0] if pick else math.inf)
        return pick[1] if pick else None

    def vacant_rooms(self):
        return [r for r in self.rooms if r.tenant is None and not r.public]

    def open_line(self):
        self.active = True
        if self.p.get("line", True):
            for zone, m in self.saved.items():
                for mode in SUBWAY:
                    if mode in self.options[zone]:
                        self.options[zone][mode]["min"] -= m
        for t in self.tenants:
            t.cache.clear()
        base = self.rents["Z00"]["合租单间"]
        for _ in range(self.p.get("public_rooms", 0)):
            room = Room("Z00", "合租单间", self.p["public_rent"], public=True)
            self.rooms.append(room)
            self.public_rooms.append(room)
        self.public_value = base

    def snapshot(self):
        rents = {}
        for r in self.rooms:
            if not r.public:
                rents.setdefault((r.zone, r.kind), []).append(r.rent)
        return {k: st.mean(v) for k, v in rents.items()}

    def run(self):
        rng = self.rng
        self.public_rooms = []
        self.public_value = 0
        n_tenants = round(N_ROOMS * self.p.get("occupancy", OCCUPANCY))
        people = sorted((Tenant(rng, self.p) for _ in range(n_tenants)), key=lambda x: x.income)
        seated_by = {"low": 0, "mid": 0, "high": 0}
        wanted_by = {"low": 0, "mid": 0, "high": 0}
        for t in people:
            wanted_by[t.group] += 1
            room = self.best(t, self.vacant_rooms()[:], see_all=True)
            if room is not None:
                self.place(t, room, rng.randrange(LEASE_MONTHS) - LEASE_MONTHS)
                self.tenants.append(t)
                seated_by[t.group] += 1
        seated = len(self.tenants)
        moves = left = 0
        left_by = {"low": 0, "mid": 0, "high": 0}
        before = {}
        tail = {k: [] for k in ["commute", "low_commute", "over60", "low_cash", "low_cost", "low_burden", "mid_burden", "high_burden", "low_over30", "low_over50", "all_burden", "revenue", "vacant", "budget", "n", "low_near", "watch_share", "watch_low", "watch_commute", "other_commute"]}
        modes = {}
        after = []
        for month in range(MONTHS):
            self.month = month
            if month == LINE_OPENS:
                before = self.snapshot()
                self.open_line()
            if self.p.get("rent_trend"):
                self.city_rent *= (1 + self.p["rent_trend"]) ** (1 / 12)
            if self.p.get("wage_trend"):
                step = (1 + self.p["wage_trend"]) ** (1 / 12)
                self.city_wage *= step
                for t in self.tenants:
                    t.scale(step)
            for r in self.rooms:
                if r.tenant is None and not r.public:
                    r.vacant_for += 1
                    if r.vacant_for > 1 and not self.frozen:
                        self.catch_up(r)
                        r.rent = max(self.floor_rent(r), r.rent * 0.97)
            vacant = self.vacant_rooms()
            for t in [x for x in self.tenants if rng.random() < CHURN]:
                room = t.room
                self.tenants.remove(t)
                self.vacate(room)
                vacant.append(room)
                for _ in range(10):
                    n = Tenant(rng, self.p, self.city_wage)
                    target = None
                    for _ in range(3):
                        target = self.best(n, vacant)
                        if target is not None:
                            break
                    if target is None:
                        self.blocked[n.group] += month >= LINE_OPENS
                        continue
                    if target in vacant:
                        vacant.remove(target)
                    self.place(n, target, month)
                    self.tenants.append(n)
                    break
            for t in list(self.tenants):
                if t.expires > month:
                    continue
                quote = self.renewal(t)
                target = self.best(t, vacant, stay_rent=quote)
                if target is None:
                    old = t.room
                    self.tenants.remove(t)
                    self.vacate(old)
                    vacant.append(old)
                    if month >= LINE_OPENS:
                        left += 1
                        left_by[t.group] += 1
                elif target is t.room:
                    if not t.room.public:
                        t.room.loaded += self.load(t, t.room)
                    t.room.rent = quote
                    t.expires = month + LEASE_MONTHS
                else:
                    old = t.room
                    self.vacate(old)
                    vacant.append(old)
                    if target in vacant:
                        vacant.remove(target)
                    self.place(t, target, month)
                    moves += month >= LINE_OPENS
            if month >= MONTHS - 12:
                self.measure(tail, modes)
                after.append(self.snapshot())
        out = {k: st.mean(v) for k, v in tail.items()}
        out.update(moves=moves, left=left, seated=seated, left_low=left_by["low"], left_mid=left_by["mid"], left_high=left_by["high"],
                   seated_low=seated_by["low"] / max(wanted_by["low"], 1), seated_mid=seated_by["mid"] / max(wanted_by["mid"], 1), seated_high=seated_by["high"] / max(wanted_by["high"], 1),
                   blocked_low=self.blocked["low"], blocked_mid=self.blocked["mid"], blocked_high=self.blocked["high"])
        out["before"] = before
        out["after"] = {k: st.mean(a[k] for a in after) for k in after[0]}
        out["modes"] = modes
        return out

    def measure(self, tail, modes):
        people = self.tenants
        low = [t for t in people if t.low]
        info = [(t, self.travel(t, t.room.zone, self.net(t, t.room.rent, t.room)) or self.travel(t, t.room.zone)) for t in people]
        burden = lambda t: self.net(t, t.room.rent, t.room) / t.income
        tail["commute"].append(st.mean(i[2] for _, i in info))
        tail["over60"].append(st.mean(i[2] > 60 for _, i in info))
        tail["low_commute"].append(st.mean(i[2] for t, i in info if t.low))
        tail["low_cash"].append(st.mean(self.net(t, t.room.rent, t.room) + i[3] for t, i in info if t.low))
        tail["low_cost"].append(st.mean(self.net(t, t.room.rent, t.room) + i[0] for t, i in info if t.low))
        for g in ("low", "mid", "high"):
            group = [t for t in people if t.group == g]
            tail[g + "_burden"].append(st.mean(burden(t) for t in group) if group else 0)
        tail["all_burden"].append(st.mean(burden(t) for t in people))
        tail["low_over30"].append(st.mean(burden(t) > 0.30 for t in low))
        tail["low_over50"].append(st.mean(burden(t) > 0.50 for t in low))
        tail["low_near"].append(st.mean(t.room.zone in ("Z00", "Z01", "Z02", "Z03", "Z04") for t in low))
        watch = self.p.get("watch", ())
        inside = [(t, i) for t, i in info if t.room.zone in watch]
        outside = [(t, i) for t, i in info if t.room.zone not in watch]
        tail["watch_share"].append(len(inside) / len(info))
        tail["watch_low"].append(st.mean(t.low for t, _ in inside) if inside else 0)
        tail["watch_commute"].append(st.mean(i[2] for _, i in inside) if inside else 0)
        tail["other_commute"].append(st.mean(i[2] for _, i in outside) if outside else 0)
        private = [r for r in self.rooms if not r.public]
        tail["revenue"].append(sum(r.rent for r in private if r.tenant) / len(private))
        tail["vacant"].append(sum(r.tenant is None for r in private) / len(private))
        public_cost = sum(self.public_value - r.rent for r in self.public_rooms if r.tenant)
        subsidy_cost = self.p.get("subsidy", 0) * sum(not t.room.public for t in low)
        fare_cost = sum(self.options[t.room.zone][i[1]]["month"] - i[3] for t, i in info if t.low) if self.p.get("free_fare") else 0
        tail["budget"].append(public_cost + subsidy_cost + fare_cost)
        tail["n"].append(len(people))
        for t, i in info:
            modes[(t.group, i[1])] = modes.get((t.group, i[1]), 0) + 1
