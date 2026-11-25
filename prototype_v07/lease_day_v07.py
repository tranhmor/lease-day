"""Lease Day v0.7 core simulation engine.

Separates environment mechanics (time, dynamic cash+deposit ledger, hard affordability checks,
announcement/opening events, 4-step batched monthly clearing, snapshot forking, JSONL audit logs)
from interchangeable LandlordPolicy / TenantPolicy decision modules.
"""
from collections import deque
import copy
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import random
import statistics as st
from typing import Any, Dict, List, Optional, Tuple

from .board_v07 import (
    BOARD,
    EAST_EXPRESS,
    QUALITY,
    SHOCKS,
    TAU_DEFAULT,
    TREATED_ZONES,
    TYPE_AMENITY_SCALE,
    TYPES,
    ZONE_AMENITY_RMB,
    ZONE_AMENITY_SCORE,
    ZONE_BY_ID,
    ZONES,
    Landlord,
    allocate_v06,
    allocate_v07,
    assign_landlords,
    sample_station_dist_m,
    station_walk_delta_min,
    zone_label,
)
from .agents.base import (
    LandlordPolicy,
    TenantPolicy,
    validate_answer_counter,
    validate_at_expiry,
    validate_pick_applicant,
    validate_price_vacant,
    validate_renewal_offer,
    validate_search,
)
from .agents.rule import (
    RuleLandlord,
    RuleLandlordV06Compat,
    RuleTenant,
    RuleTenantV06Compat,
)

# ---- Constants inherited & verified from v0.6 ----
SUBWAY = ("地铁", "骑车接地铁")
PUBLIC_FARE = ("地铁", "公交直达", "公交换乘")
LEASE_MONTHS = 12
WORKDAYS = 26
FLOOR = 2000
MOVE_CASH = 500
MOVE_HASSLE = 1500
COMFORT_WEIGHT = 0.5
OUTSIDE_FLOOR = 0.90
CHURN = 0.02
LISTINGS_SEEN = 5
DEMAND_K = 0.2
DEMAND_CAP = 0.10

UP_FRONT = {
    "低价房": ((2, 0.7), (3, 0.1), (4, 0.2)),
    "便宜单间": ((2, 0.5), (3, 0.2), (4, 0.3)),
    "合租单间": ((2, 0.3), (3, 0.2), (4, 0.5)),
    "整租": ((2, 0.1), (3, 0.1), (4, 0.8)),
}
INCOME = [
    ("low", BOARD["work"]["income_mix"]["较低 4,000-7,000"], 4000, 7000),
    ("mid", BOARD["work"]["income_mix"]["中等 7,000-15,000"], 7000, 15000),
    ("high", BOARD["work"]["income_mix"]["较高 15,000-35,000"], 15000, 35000),
]
LINES = {"low": (0.20, 0.40), "mid": (0.25, 0.40), "high": (0.25, 0.35)}
CAR = {"low": 0.40, "mid": 0.40, "high": 0.35}
COUPLE = {"low": 0.35, "mid": 0.42, "high": 0.46}
SECOND_EARNER = 1.8
LOW_TOP, MID_TOP = 7000, 15000

CLASS = {
    "地铁": "subway", "骑车接地铁": "subway",
    "公交直达": "bus", "公交换乘": "bus",
    "电动车": "bike", "自行车": "bike",
    "步行": "walk", "私家车": "car", "打车": "taxi",
}
ASC = {"subway": 0.0, "bus": 6.5, "bike": 40.2, "walk": 24.9, "car": -173.7, "taxi": -2.0}
TASTE_SCALE = 50.0
BIKE_TIRE = 2.0

ANNOUNCEMENT_TEXT = "东向快线将于第 25 个月开通，届时 Z05 通勤预计缩短约 12 分钟，Z11 约 15 分钟。"
# Shown identically in S and P from opening month on, so post-opening P-S gaps are not driven by an information gap.
LANDLORD_LINE_NOTE = "lease_months_after_open 为本房新签 12 个月租约中位于开通之后、且本区受益的月数（不受益的区域为 0）。"
TENANT_LINE_NOTE = ("合同期 12 个月。开通前的月份按 min 通勤，开通后的月份按 post_open_min 通勤；"
                    "contract_months_after_open 为该房新合同中位于开通之后的月数。")
OPENED_TEXT = "东向快线已于第 25 个月开通，Z05 通勤缩短约 12 分钟，Z11 约 15 分钟。"


@dataclass
class Config:
    scenario: str = "N"                  # "N" (no line), "S" (sudden open), "P" (announced M13 -> open M25)
    seed: int = 0
    n_rooms: int = 240
    occupancy: float = 0.95
    months: int = 36
    announce_month: int = 12             # 0-indexed: month 12 == 13th month
    line_opens: int = 24                 # 0-indexed: month 24 == 25th month
    n_landlords: int = 40
    treated_counts: Optional[Dict[str, int]] = field(default_factory=lambda: {"Z05": 24, "Z11": 16})
    treated_zones: Tuple[str, ...] = TREATED_ZONES
    shock: str = "east_express"
    demand_k: float = DEMAND_K
    # v0.7 calibrated environment toggles (all disabled in compat_v06 mode)
    compat_v06: bool = False
    amenity_weight: float = 0.85         # OLS spatial amenity weight
    couple_quality_boost: float = 2.0    # Higher privacy preference for couples
    couple_no_bedspace: bool = True      # Couples cannot rent 低价房
    use_station_dist: bool = True        # Room-level walk distance to subway
    use_dynamic_ledger: bool = True      # Monthly savings accumulation + real moving cash & deposit lockup
    savings_rate: float = 0.25           # Fraction of monthly surplus saved into liquid cash
    candidate_rent_cap_ratio: float = 0.55  # Hard candidate display ceiling (allows LLM to cross stretch!)
    vacancy_smooth_prior_m: float = 10.0 # Bayesian prior rooms for smoothed zone vacancy
    vacancy_window: int = 3              # Rolling months for zone vacancy
    # Opening fill: "until_full" keeps drawing applicants (same income distribution) until occupancy target is met,
    # mirroring steady-state newcomer arrival; "fixed_pool" = legacy single pool of n_rooms*occupancy applicants.
    initial_fill: str = "until_full"
    initial_fill_max_draws: float = 4.0  # cap on applicants drawn, as a multiple of the occupancy target
    log_dir: Optional[str] = None        # Directory to write decisions.jsonl & monthly.jsonl
    record_decisions: bool = True        # Record decision records (in memory or jsonl)


class Room:
    __slots__ = (
        "room_id", "zone", "kind", "rent", "start", "up_front", "landlord_id",
        "station_dist_m", "walk_delta_min", "tenant_id", "vacant_for",
        "last_vacant_months", "public", "loaded", "index",
    )

    def __init__(
        self,
        room_id: int,
        zone: str,
        kind: str,
        rent: float,
        up_front: int = 2,
        landlord_id: int = -1,
        station_dist_m: int = 600,
        walk_delta_min: int = 0,
    ):
        self.room_id = room_id
        self.zone = zone
        self.kind = kind
        self.rent = rent
        self.start = rent
        self.up_front = up_front
        self.landlord_id = landlord_id
        self.station_dist_m = station_dist_m
        self.walk_delta_min = walk_delta_min
        self.tenant_id: Optional[int] = None
        self.vacant_for = 0
        self.last_vacant_months = 0
        self.public = False
        self.loaded = 0.0
        self.index = 1.0


class Tenant:
    __slots__ = (
        "tenant_id", "wage", "couple", "income", "group", "comfort", "stretch",
        "cash", "locked_deposit", "car", "taste", "good_standing",
        "room_id", "expires", "tenure_months", "mode", "cache",
    )

    def __init__(self, tenant_id: int, rng: random.Random, compat_v06: bool = False):
        self.tenant_id = tenant_id
        worker, _, lo, hi = rng.choices(INCOME, weights=[g[1] for g in INCOME])[0]
        self.wage = rng.randrange(lo, hi + 1, 500)
        self.couple = rng.random() < COUPLE[worker]
        self.income = round(self.wage * (SECOND_EARNER if self.couple else 1.0))
        self.group = "low" if self.income <= LOW_TOP else "mid" if self.income < MID_TOP else "high"
        comfort, stretch = LINES[self.group]
        self.comfort = comfort + rng.uniform(-0.05, 0.05)
        self.stretch = stretch + rng.uniform(-0.05, 0.05)
        self.cash = self.income * rng.uniform(1.0, 3.0)
        self.locked_deposit = 0.0
        self.car = rng.random() < CAR[self.group]
        self.taste = {k: -math.log(-math.log(rng.random())) for k in ASC}
        # Standing draw only in v0.7 mode so compat_v06 RNG stream matches v0.6 identically!
        self.good_standing = True if compat_v06 else (rng.random() < 0.90)
        self.room_id: Optional[int] = None
        self.expires = 0
        self.tenure_months = 0
        self.mode: Optional[str] = None
        self.cache: Dict[Tuple[str, int], Tuple[float, str, int, float]] = {}

    @property
    def low(self) -> bool:
        return self.group == "low"

    @property
    def penalty(self) -> float:
        return max(200.0, 0.35 * self.income - 800.0)


class GameV07:
    """Modular Lease Day v0.7 simulation engine."""

    def __init__(
        self,
        cfg: Config,
        landlord_policy: Optional[LandlordPolicy] = None,
        tenant_policy: Optional[TenantPolicy] = None,
    ):
        self.cfg = cfg
        if cfg.compat_v06:
            self.landlord_policy = landlord_policy or RuleLandlordV06Compat()
            self.tenant_policy = tenant_policy or RuleTenantV06Compat()
        else:
            self.landlord_policy = landlord_policy or RuleLandlord()
            self.tenant_policy = tenant_policy or RuleTenant()

        self.rng = random.Random(cfg.seed)
        self.browse_rng = random.Random(cfg.seed + 7)
        self.ll_rng = random.Random(cfg.seed + 19)
        self.dist_rng = random.Random(cfg.seed + 29)
        # A2: exogenous monthly arrivals draw from their own stream (fixed count per month), so N/S/P forked from the
        # same warm-up receive identical newcomers. Churn, browsing and ordering use keyed streams (see _keyed_rng).
        self.arrival_rng = random.Random(cfg.seed + 43)
        self.external_log: List[Dict[str, Any]] = []

        shock_key = "none" if cfg.scenario == "N" else cfg.shock
        self.saved = dict(SHOCKS[shock_key])
        self.options = {z["id"]: {m: dict(v) for m, v in z["options"].items()} for z in ZONES}
        self.rents = {z["id"]: z["rents"] for z in ZONES}

        self.month = 0
        self.announced = False
        self.active = False  # True once line opens at cfg.line_opens

        # Allocate rooms
        alloc = allocate_v06(cfg.n_rooms) if cfg.compat_v06 else allocate_v07(cfg.n_rooms, cfg.treated_counts)
        self.rooms: List[Room] = []
        self.rooms_by_id: Dict[int, Room] = {}
        self.count: Dict[Tuple[str, str], List[int]] = {}
        self.zone_totals: Dict[str, int] = {}
        terms = random.Random(cfg.seed + 11)
        rid = 0
        for (zone, kind), n in alloc.items():
            base = self.rents[zone][kind]
            self.count[(zone, kind)] = [n, n]
            self.zone_totals[zone] = self.zone_totals.get(zone, 0) + n
            for _ in range(n):
                rent = base * self.rng.uniform(0.9, 1.1)
                room = Room(room_id=rid, zone=zone, kind=kind, rent=rent)
                self.rooms.append(room)
                self.rooms_by_id[rid] = room
                rid += 1
            for room in self.rooms[-n:] if n else []:
                months, shares = zip(*UP_FRONT[kind])
                room.up_front = terms.choices(months, weights=shares)[0]
                if cfg.use_station_dist and not cfg.compat_v06:
                    room.station_dist_m = sample_station_dist_m(self.dist_rng)
                    room.walk_delta_min = station_walk_delta_min(room.station_dist_m)

        # Assign 40 landlords (strictly separating treated vs control zones)
        self.landlords: Dict[int, Landlord] = {}
        if not cfg.compat_v06:
            self.landlords = assign_landlords(self.rooms, random.Random(cfg.seed + 37), cfg.n_landlords, cfg.treated_zones)

        # Tenant registry & state
        self.tenants: Dict[int, Tenant] = {}
        self.next_tenant_id = 0
        self.inquiries: Dict[Tuple[str, str], List[int]] = {cell: [0] * max(cfg.months, 60) for cell in self.count}
        self.zone_vac_hist: Dict[str, deque] = {z["id"]: deque(maxlen=cfg.vacancy_window) for z in ZONES}
        self.zone_apps_hist: Dict[str, deque] = {z["id"]: deque(maxlen=cfg.vacancy_window) for z in ZONES}
        self.zone_vacant_hist: Dict[str, deque] = {z["id"]: deque(maxlen=cfg.vacancy_window) for z in ZONES}

        # Counters & logs
        self.blocked = {"low": 0, "mid": 0, "high": 0}
        self.seated = 0
        self.seated_by = {"low": 0, "mid": 0, "high": 0}
        self.wanted_by = {"low": 0, "mid": 0, "high": 0}
        self.moves = 0
        self.left = 0
        self.left_by = {"low": 0, "mid": 0, "high": 0}
        self.fallback_count = 0
        # Run-quality diagnostics (reported, not gated): outputs clamped to 0.7-1.3x, outputs repaired by the validator
        self.guardrail_counts: Dict[str, int] = {}
        self.decision_count = 0
        self.total_tokens = 0

        # M12 baseline tracking for cohort & anticipation metrics
        self.m12_treated_cohort: Dict[int, Dict[str, Any]] = {}
        self.before_snapshot: Dict[Tuple[str, str], float] = {}
        self.after_snapshots: List[Dict[Tuple[str, str], float]] = []
        self.monthly_records: List[Dict[str, Any]] = []
        self.decision_records: List[Dict[str, Any]] = []
        self._log_dir_written: Optional[str] = None
        self.tail: Dict[str, List[float]] = {
            k: [] for k in [
                "commute", "low_commute", "over60", "low_cash", "low_cost",
                "low_burden", "mid_burden", "high_burden", "low_over30", "low_over50",
                "all_burden", "revenue", "vacant", "n", "low_near",
                "watch_share", "watch_low", "watch_commute", "other_commute",
            ]
        }
        self.modes_count: Dict[Tuple[str, str], int] = {}
        # A3: pooled tenant-month rent/income over the tail, by (room kind, income group): [sum, n]
        self.burden_cells: Dict[Tuple[str, str], List[float]] = {}
        # H3: renewal quotes made when zone vacancy < 4%: [n quotes, n with no hike (<= +0.05%)]
        self.tight_renewals: List[int] = [0, 0]

        # Per-month event accumulators
        self._m_events: Dict[str, Any] = {}
        self._initialized = False
        self._dec_fp = None
        self._mon_fp = None

    # ---- Snapshot / Fork Support (Shared M1-M12 Warm-Up) ----

    def export_snapshot(self) -> "GameV07":
        """Return a detached deep copy of simulation state (call right after warm-up before forking N/S/P)."""
        fp_d, fp_m = self._dec_fp, self._mon_fp
        lp, tp = self.landlord_policy, self.tenant_policy
        self._dec_fp = self._mon_fp = None
        self.landlord_policy = self.tenant_policy = None
        snap = copy.deepcopy(self)
        self._dec_fp, self._mon_fp = fp_d, fp_m
        self.landlord_policy, self.tenant_policy = lp, tp
        return snap

    @classmethod
    def from_snapshot(
        cls,
        snap: "GameV07",
        scenario: str,
        landlord_policy: Optional[LandlordPolicy] = None,
        tenant_policy: Optional[TenantPolicy] = None,
        log_dir: Optional[str] = None,
    ) -> "GameV07":
        """Fork a new scenario branch from a warm-up snapshot with zero pre-fork drift."""
        g = copy.deepcopy(snap)
        g.cfg.scenario = scenario
        g.cfg.log_dir = log_dir
        g._log_dir_written = None
        shock_key = "none" if scenario == "N" else g.cfg.shock
        g.saved = dict(SHOCKS[shock_key])
        if landlord_policy is not None:
            g.landlord_policy = landlord_policy
        elif g.landlord_policy is None:
            g.landlord_policy = RuleLandlordV06Compat() if g.cfg.compat_v06 else RuleLandlord()
        if tenant_policy is not None:
            g.tenant_policy = tenant_policy
        elif g.tenant_policy is None:
            g.tenant_policy = RuleTenantV06Compat() if g.cfg.compat_v06 else RuleTenant()
        return g

    # ---- Travel, Hard Affordability, and Scoring Helpers ----

    def room_mode_options(self, tenant: Tenant, room: Room, include_post_open: bool = False) -> List[Dict[str, Any]]:
        """Return feasible travel options for (tenant, room), accounting for station walk distance."""
        hourly = 0.5 * tenant.wage / 260.0
        delta = room.walk_delta_min if (self.cfg.use_station_dist and not self.cfg.compat_v06) else 0
        saved_m = self.saved.get(room.zone, 0) if include_post_open else 0
        out = []
        for mode, o in self.options[room.zone].items():
            if mode == "私家车" and not tenant.car:
                continue
            cur_min = max(5, o["min"] + (delta if mode in SUBWAY else 0))
            post_min = max(5, cur_min - (saved_m if mode in SUBWAY else 0)) if include_post_open else cur_min
            money = o["month"]
            kind = CLASS[mode]
            felt = cur_min + 5 * o.get("transfers", 0)
            if kind in ("bike", "walk"):
                felt += max(0, cur_min - 30) * BIKE_TIRE
            hours = 2 * WORKDAYS * felt / 60.0 + ASC[kind] - TASTE_SCALE * tenant.taste[kind]
            gen_cost = money + hours * hourly
            entry = {
                "mode": mode,
                "min": cur_min,
                "transfers": o.get("transfers", 0),
                "month_fare": money,
                "gen_cost": gen_cost,
            }
            if include_post_open and saved_m > 0 and mode in SUBWAY:
                entry["post_open_min"] = post_min
            out.append(entry)
        out.sort(key=lambda x: x["gen_cost"])
        return out

    def best_travel(self, tenant: Tenant, room: Room) -> Tuple[float, str, int, float]:
        delta = room.walk_delta_min if (self.cfg.use_station_dist and not self.cfg.compat_v06) else 0
        key = (room.zone, delta)
        got = tenant.cache.get(key)
        if got is not None:
            return got
        opts = self.room_mode_options(tenant, room, include_post_open=False)
        best = opts[0]
        res = (best["gen_cost"], best["mode"], best["min"], best["month_fare"])
        tenant.cache[key] = res
        return res

    def available_move_cash(self, tenant: Tenant, moving_from_existing: bool) -> float:
        if not self.cfg.use_dynamic_ledger or self.cfg.compat_v06:
            return tenant.cash
        return tenant.cash + (tenant.locked_deposit if moving_from_existing else 0.0)

    def required_upfront_cash(self, rent: float, up_front: int) -> float:
        return up_front * rent + MOVE_CASH

    def hard_allowed(self, tenant: Tenant, room: Room, rent: float, moving: bool, enforce_stretch: bool = False) -> bool:
        """Code-enforced hard feasibility check (cannot be bypassed by LLM)."""
        if self.cfg.couple_no_bedspace and not self.cfg.compat_v06 and tenant.couple and room.kind == "低价房":
            return False
        if enforce_stretch and rent > tenant.stretch * tenant.income:
            return False
        if not enforce_stretch and rent > self.cfg.candidate_rent_cap_ratio * tenant.income:
            return False
        way = self.best_travel(tenant, room)
        if tenant.income - rent - way[3] < FLOOR:
            return False
        if moving:
            avail = self.available_move_cash(tenant, moving_from_existing=(tenant.room_id is not None))
            if avail < self.required_upfront_cash(rent, room.up_front):
                return False
        return True

    def rule_score(self, tenant: Tenant, room: Room, rent: float, moving: bool) -> float:
        over = max(0.0, rent - tenant.comfort * tenant.income) * COMFORT_WEIGHT
        way = self.best_travel(tenant, room)
        if self.cfg.compat_v06:
            pen = tenant.penalty * QUALITY[room.kind]
            amen = 0.0
        else:
            boost = self.cfg.couple_quality_boost if tenant.couple else 1.0
            pen = tenant.penalty * boost * QUALITY[room.kind]
            amen = self.cfg.amenity_weight * ZONE_AMENITY_RMB[room.zone] * TYPE_AMENITY_SCALE[room.kind]
        return rent + way[0] + pen - amen + over + (MOVE_HASSLE / LEASE_MONTHS if moving else 0.0)

    # ---- Vacancy, Inquiry, and Demand Signals ----

    def cell_vacancy(self, room: Room) -> float:
        total, empty = self.count[(room.zone, room.kind)]
        return empty / max(total, 1)

    def zone_vacancy_smooth(self, zone: str, exclude_room: Optional[Room] = None) -> float:
        """Bayesian-smoothed rolling zone vacancy (eliminates small-cell discretization bug!)."""
        zrooms = [r for r in self.rooms if r.zone == zone]
        cur_empty = sum(1 for r in zrooms if r.tenant_id is None and r is not exclude_room)
        cur_total = max(len(zrooms) - (1 if exclude_room is not None else 0), 1)
        hist = list(self.zone_vac_hist[zone])
        if hist:
            # Blend rolling history with current state
            avg_empty = (sum(hist) + cur_empty) / (len(hist) + 1)
        else:
            avg_empty = float(cur_empty)
        m = self.cfg.vacancy_smooth_prior_m
        return (avg_empty + m * 0.05) / (cur_total + m)

    def demand_signal(self, room: Room) -> float:
        """Post-opening realized demand signal (strictly 0.0 before LINE_OPENS per v0.7 §3.3)."""
        k = self.cfg.demand_k
        if not k or self.month < self.cfg.line_opens:
            return 0.0
        if self.cfg.compat_v06:
            counts = self.inquiries[(room.zone, room.kind)]
            before = sum(counts[self.cfg.line_opens - 12:self.cfg.line_opens])
            recent = sum(counts[self.month - 12:self.month])
            return max(-DEMAND_CAP, min(DEMAND_CAP, k * math.log((recent + 1) / (before + 1))))
        # Zone-level application heat relative to baseline (smooth, scale-invariant!)
        z_apps = sum(self.zone_apps_hist[room.zone])
        z_vacs = max(sum(self.zone_vacant_hist[room.zone]), 1)
        ratio = z_apps / z_vacs
        # Baseline expectation ~1.2 applications per vacant room
        return max(-DEMAND_CAP, min(DEMAND_CAP, 0.04 * math.log((ratio + 0.5) / 1.7)))

    def nearby_avg_rent(self, room: Room) -> float:
        peers = [r.rent for r in self.rooms if r.zone == room.zone and r.kind == room.kind and r.room_id != room.room_id]
        if not peers:
            peers = [r.rent for r in self.rooms if r.zone == room.zone and r.room_id != room.room_id]
        return round(st.mean(peers), 1) if peers else round(room.start, 1)

    def recent_apps_per_vacant(self, zone: str) -> Optional[float]:
        """Applications per vacant room over the window; None when the zone had no vacant room at all (fully let),
        so a tight market is not shown as "zero demand". zone_vacant_hist stores max(emp, 1), so use zone_vac_hist."""
        if sum(self.zone_vac_hist[zone]) <= 0:
            return None
        apps = sum(self.zone_apps_hist[zone])
        vacs = sum(self.zone_vacant_hist[zone])
        return round(apps / max(vacs, 1), 2)

    def floor_rent(self, room: Room) -> float:
        return room.start * OUTSIDE_FLOOR

    # ---- Announcement & Opening Events ----

    def announce(self) -> None:
        if self.cfg.scenario == "P":
            self.announced = True

    def open_line(self) -> None:
        self.active = True
        if self.cfg.scenario in ("S", "P"):
            for zone, m in self.saved.items():
                for mode in SUBWAY:
                    if mode in self.options[zone]:
                        self.options[zone][mode]["min"] = max(5, self.options[zone][mode]["min"] - m)
            for t in self.tenants.values():
                t.cache.clear()

    # ---- Structured Context Builders (ready for both Rule & LLM!) ----

    @property
    def line_built(self) -> bool:
        """True only in scenarios that actually have the new line (S/P) once it has opened."""
        return self.active and self.cfg.scenario in ("S", "P")

    @property
    def line_info_visible(self) -> bool:
        """Whether agents may see anything about the new line this month (P after announcement, S/P after opening)."""
        return self.announced or self.line_built

    def _announcement_payload(self, zone: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Line fact for prompts. zone=None (tenants) omits zone-specific fields; tenants read per-card fields instead."""
        if not self.line_info_visible:
            return None
        # The announcement text itself is fixed by design (§2.1); only the surrounding structure carries the
        # explanation, so line-related wording appears only where line information is allowed (never in templates).
        to_open = max(0, self.cfg.line_opens - self.month)
        out: Dict[str, Any] = {
            "text": OPENED_TEXT if self.line_built else ANNOUNCEMENT_TEXT,
            "opens_at_month": self.cfg.line_opens + 1,
            "months_to_opening": to_open,
            "already_open": self.line_built,
        }
        if zone is not None:
            out["affects_this_zone"] = zone in self.cfg.treated_zones
            out["expected_time_saving_min"] = self.saved.get(zone, 0)
            # Same convention as tenant cards' contract_months_after_open: 0 outside the zones the line serves
            affected = zone in self.cfg.treated_zones
            out["lease_months_after_open"] = (LEASE_MONTHS if self.line_built else max(0, LEASE_MONTHS - to_open)) if affected else 0
            out["note"] = LANDLORD_LINE_NOTE
        else:
            out["note"] = TENANT_LINE_NOTE
        return out

    def _landlord_base_ctx(self, room: Room) -> Dict[str, Any]:
        ll = self.landlords.get(room.landlord_id)
        ll_info = ll.to_dict() if ll else {"landlord_id": -1, "kind": "个人房东", "risk": "怕空置", "treated": room.zone in self.cfg.treated_zones, "zones": [room.zone], "n_rooms": 1}
        ll_vac = sum(1 for rid in (ll.room_ids if ll else [room.room_id]) if self.rooms_by_id[rid].tenant_id is None)
        v_smooth = self.zone_vacancy_smooth(room.zone, exclude_room=room if room.tenant_id is None else None)
        return {
            "month": self.month + 1,
            "room_id": room.room_id,
            "zone": room.zone,
            "zone_label": zone_label(room.zone),
            "amenity_score": ZONE_AMENITY_SCORE[room.zone],
            "kind": room.kind,
            "current_rent": round(room.rent, 2),
            "start_rent": round(room.start, 2),
            "floor_rent": round(self.floor_rent(room), 2),
            "up_front": room.up_front,
            "vacant_for": room.vacant_for,
            "last_vacant_months": room.last_vacant_months,
            "landlord": ll_info,
            "landlord_vacant_rooms": ll_vac,
            "zone_vacancy_smooth": round(v_smooth, 4),
            "cell_vacancy": round(self.cell_vacancy(room), 4),
            "nearby_avg_rent": self.nearby_avg_rent(room),
            "recent_apps_per_vacant": self.recent_apps_per_vacant(room.zone),
            "demand_signal": self.demand_signal(room),
            "announcement": self._announcement_payload(room.zone),
            # A2: rule-landlord noise keyed by (room, month); each room gets at most one renewal quote per month
            "_rng": self.rng if self.cfg.compat_v06 else self._keyed_rng("landlord", room.room_id, self.month),
        }

    def _build_room_card(self, tenant: Tenant, room: Room, rent: float, moving: bool) -> Dict[str, Any]:
        include_post = self.announced and not self.active
        raw_modes = self.room_mode_options(tenant, room, include_post_open=include_post)
        modes_out = []
        for m in raw_modes:
            residual = round(tenant.income - rent - m["month_fare"], 1)
            entry = {
                "mode": m["mode"],
                "min": m["min"],
                "transfers": m["transfers"],
                "month_fare": m["month_fare"],
                "monthly_residual": residual,
                "feasible": residual >= FLOOR,
            }
            if "post_open_min" in m:
                entry["post_open_min"] = m["post_open_min"]
            modes_out.append(entry)

        way = self.best_travel(tenant, room)
        upfront_needed = self.required_upfront_cash(rent, room.up_front) if moving else 0.0
        avail_cash = self.available_move_cash(tenant, moving_from_existing=(tenant.room_id is not None))
        aff = self.hard_allowed(tenant, room, rent, moving=moving, enforce_stretch=False)
        within_stretch = rent <= tenant.stretch * tenant.income
        r_score = self.rule_score(tenant, room, rent, moving=moving)

        rem = max(0, self.cfg.line_opens - self.month)
        months_after_open = max(0, LEASE_MONTHS - rem) if (self.announced and not self.active) else (LEASE_MONTHS if self.line_built else 0)

        card = {
            "room_id": room.room_id,
            "zone": room.zone,
            "zone_label": zone_label(room.zone),
            "amenity_score": ZONE_AMENITY_SCORE[room.zone],
            "kind": room.kind,
            "rent": round(rent, 2),
            "current_rent": round(room.rent, 2),
            "offer_rent": round(rent, 2),
            "rent_pct_income": round(rent / tenant.income, 3),
            "up_front": room.up_front,
            "upfront_cash_needed": round(upfront_needed, 1),
            "cash_gap": round(avail_cash - upfront_needed, 1),
            "station_dist_m": room.station_dist_m,
            "modes": modes_out,
            "affordable": aff,
            "rule_within_stretch": within_stretch,
            "rule_score": round(r_score, 2),
            "rule_best_mode": way[1],
            "contract_months": LEASE_MONTHS,
        }
        if self.line_info_visible:
            card["contract_months_after_open"] = months_after_open if (room.zone in self.cfg.treated_zones) else 0
        return card

    def _tenant_profile_dict(self, tenant: Tenant) -> Dict[str, Any]:
        return {
            "tenant_id": tenant.tenant_id,
            "income": round(tenant.income, 1),
            "group": tenant.group,
            "couple": tenant.couple,
            "car": tenant.car,
            "cash": round(tenant.cash, 1),
            "locked_deposit": round(tenant.locked_deposit, 1),
            "available_move_cash": round(self.available_move_cash(tenant, tenant.room_id is not None), 1),
            "comfort_ratio": round(tenant.comfort, 3),
            "stretch_ratio": round(tenant.stretch, 3),
            "good_standing": tenant.good_standing,
            "tenure_months": tenant.tenure_months,
        }

    def _keyed_rng(self, *key: Any) -> random.Random:
        """Common random numbers across scenarios: the draw depends only on (seed, key), never on how many draws
        happened earlier in this branch. String seeds are hashed with SHA-512, so this is stable across processes."""
        return random.Random("|".join(str(k) for k in (self.cfg.seed,) + key))

    def _sample_candidates(self, tenant: Tenant, vacant_rooms: List[Room], see_all: bool = False) -> List[Room]:
        if self.cfg.compat_v06:
            within = [r for r in vacant_rooms if r.rent <= tenant.stretch * tenant.income]
            return within if see_all else self.rng.sample(within, min(LISTINGS_SEEN, len(within)))
        # v0.7: display all hard-affordable rooms (up to 55% income & >=2000 residual & cash) so LLM can cross stretch!
        within = [r for r in vacant_rooms if self.hard_allowed(tenant, r, r.rent, moving=True, enforce_stretch=False)]
        if see_all or len(within) <= LISTINGS_SEEN:
            return within
        # A2: per (tenant, month) stream over a room-id-ordered list -> same sample whenever the feasible set matches
        within.sort(key=lambda r: r.room_id)
        return self._keyed_rng("browse", tenant.tenant_id, self.month).sample(within, LISTINGS_SEEN)

    # ---- Safe Policy Execution with Logging & Fallback Tracking ----

    def _log_decision(
        self,
        agent_type: str,
        agent_id: int,
        decision: str,
        ctx: Dict[str, Any],
        output: Dict[str, Any],
        fallback: bool = False,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.decision_count += 1
        if fallback:
            self.fallback_count += 1
        elif agent_type in ("landlord", "tenant"):
            if output.get("clamped"):
                self.guardrail_counts[f"clamped:{decision}"] = self.guardrail_counts.get(f"clamped:{decision}", 0) + 1
            if output.get("repaired"):
                k = f"repaired:{output['repaired']}"
                self.guardrail_counts[k] = self.guardrail_counts.get(k, 0) + 1
        meta = meta or {}
        toks = meta.get("tokens", 0)
        self.total_tokens += toks
        if not self.cfg.record_decisions and self._dec_fp is None:
            return
        # Strip private internal objects (e.g., _rng) and verbose rule internals from logged inputs
        clean_inputs = {k: v for k, v in ctx.items() if not k.startswith("_")}
        rec = {
            "month": self.month + 1,
            "agent_type": agent_type,
            "agent_id": agent_id,
            "decision": decision,
            "prompt_hash": meta.get("prompt_hash", "rule"),
            "inputs": clean_inputs,
            "output": output,
            "reason": output.get("reason", ""),
            "fallback": fallback,
            "tokens": toks,
        }
        if self._dec_fp is not None:
            self._dec_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        elif self.cfg.record_decisions:
            self.decision_records.append(rec)

    def _call_landlord(self, method: str, ctx: Dict[str, Any], validator, fallback_fn) -> Dict[str, Any]:
        policy = self.landlord_policy
        raw = getattr(policy, method)(ctx)
        meta = raw.pop("_meta", {}) if isinstance(raw, dict) else {}
        validated, err = validator(raw, ctx)
        fallback = False
        if validated is None:
            fallback = True
            fb_raw = fallback_fn(ctx)
            validated, _ = validator(fb_raw, ctx)
            validated["fallback_error"] = err
        elif meta.get("fallback"):
            fallback = True
        self._log_decision("landlord", ctx["landlord"]["landlord_id"], method, ctx, validated, fallback=fallback, meta=meta)
        return validated

    def _call_tenant(self, method: str, ctx: Dict[str, Any], validator, fallback_fn) -> Dict[str, Any]:
        policy = self.tenant_policy
        raw = getattr(policy, method)(ctx)
        meta = raw.pop("_meta", {}) if isinstance(raw, dict) else {}
        validated, err = validator(raw, ctx)
        fallback = False
        if validated is None:
            fallback = True
            fb_raw = fallback_fn(ctx)
            validated, _ = validator(fb_raw, ctx)
            validated["fallback_error"] = err
        elif meta.get("fallback"):
            fallback = True
        self._log_decision("tenant", ctx["tenant"]["tenant_id"], method, ctx, validated, fallback=fallback, meta=meta)
        return validated

    # ---- Room Occupancy & Ledger Transitions ----

    def _place(self, tenant: Tenant, room: Room, month: int, mode: Optional[str] = None, charge_move: bool = True) -> None:
        old_room_id = tenant.room_id
        is_move = charge_move and (old_room_id != room.room_id)
        if self.cfg.use_dynamic_ledger and not self.cfg.compat_v06:
            if is_move:
                # Refund old deposit if moving from an existing flat; deduct moving cash + new 1-month deposit lockup
                refund = tenant.locked_deposit if old_room_id is not None else 0.0
                new_dep = room.rent  # 1-month deposit locked with new landlord
                tenant.cash = max(0.0, tenant.cash + refund - MOVE_CASH - new_dep)
                tenant.locked_deposit = new_dep
            elif old_room_id is None:
                # Initial seating at month 0: set locked deposit without double-charging move cash
                tenant.locked_deposit = room.rent
        room.tenant_id = tenant.tenant_id
        room.last_vacant_months = room.vacant_for
        room.vacant_for = 0
        tenant.room_id = room.room_id
        tenant.expires = month + LEASE_MONTHS
        tenant.tenure_months = 0
        tenant.mode = mode or self.best_travel(tenant, room)[1]
        self.count[(room.zone, room.kind)][1] -= 1

    def _vacate_only(self, room: Room) -> None:
        """Mark room vacant without repricing yet (v0.7 batched flow calls price_vacant explicitly)."""
        room.tenant_id = None
        room.vacant_for = 0
        self.count[(room.zone, room.kind)][1] += 1

    def _vacate_and_price(self, room: Room, rule_fb: LandlordPolicy) -> None:
        self._vacate_only(room)
        ctx = self._landlord_base_ctx(room)
        res = self._call_landlord("price_vacant", ctx, validate_price_vacant, rule_fb.price_vacant)
        room.rent = res["rent"]
        room.up_front = res["up_front"]

    def _browse_v06(self, tenant: Tenant, chosen_score: float) -> None:
        for r in self.browse_rng.sample(self.rooms, min(30, len(self.rooms))):
            if r.room_id == tenant.room_id:
                continue
            if self.hard_allowed(tenant, r, r.rent, moving=True, enforce_stretch=True):
                if self.rule_score(tenant, r, r.rent, moving=True) < chosen_score:
                    self.inquiries[(r.zone, r.kind)][self.month] += 1

    # ---- Initialization (Month 0 Seating) ----

    def initialize(self) -> None:
        if self._initialized:
            return
        rng = self.rng
        n_tenants = round(self.cfg.n_rooms * self.cfg.occupancy)
        if not self.cfg.compat_v06 and self.cfg.initial_fill == "until_full":
            self._initialize_until_full(n_tenants)
            return
        raw_people = [Tenant(tid, rng, compat_v06=self.cfg.compat_v06) for tid in range(n_tenants)]
        self.next_tenant_id = n_tenants

        # v0.6 sorts ascending by income; v0.7 shuffles so no permanent low-to-high queue bias
        people = sorted(raw_people, key=lambda x: x.income) if self.cfg.compat_v06 else raw_people
        if not self.cfg.compat_v06:
            rng.shuffle(people)

        vacant = list(self.rooms)
        rule_t = RuleTenantV06Compat() if self.cfg.compat_v06 else RuleTenant()
        # Evenly stagger initial expiry across 12 months so every tenant expires once in M13-M24!
        expiry_offsets = [i % LEASE_MONTHS for i in range(len(people))]
        if not self.cfg.compat_v06:
            rng.shuffle(expiry_offsets)

        for idx, t in enumerate(people):
            self.wanted_by[t.group] += 1
            best_pair = None
            for r in vacant:
                if not self.hard_allowed(t, r, r.rent, moving=True, enforce_stretch=True):
                    continue
                sc = self.rule_score(t, r, r.rent, moving=True)
                if best_pair is None or sc < best_pair[0]:
                    best_pair = (sc, r)
            if best_pair is None:
                continue
            room = best_pair[1]
            mode = self.best_travel(t, room)[1]
            start_m = (rng.randrange(LEASE_MONTHS) - LEASE_MONTHS) if self.cfg.compat_v06 else (expiry_offsets[idx] - LEASE_MONTHS)
            self._place(t, room, start_m, mode=mode, charge_move=False)
            t.tenure_months = max(0, -start_m)
            self.tenants[t.tenant_id] = t
            vacant.remove(room)
            self.seated_by[t.group] += 1

        self._finish_initialize()

    def _initialize_until_full(self, target: int) -> None:
        """Draw applicants one at a time until `target` are seated (or the draw cap is hit).

        Each applicant takes the best room he can afford under the same hard rules as later months. Unseated
        applicants simply leave, as unmatched newcomers do each month. Lease expiries are staggered evenly
        over the SEATED tenants, so every tenant meets exactly one expiry in M13-M24.
        """
        rng = self.rng
        expiry_offsets = [i % LEASE_MONTHS for i in range(target)]
        rng.shuffle(expiry_offsets)
        vacant = list(self.rooms)
        max_draws = int(target * self.cfg.initial_fill_max_draws)
        drawn = 0
        while len(self.tenants) < target and drawn < max_draws and vacant:
            t = Tenant(drawn, rng, compat_v06=False)
            drawn += 1
            self.wanted_by[t.group] += 1
            best_pair = None
            for r in vacant:
                if not self.hard_allowed(t, r, r.rent, moving=True, enforce_stretch=True):
                    continue
                sc = self.rule_score(t, r, r.rent, moving=True)
                if best_pair is None or sc < best_pair[0]:
                    best_pair = (sc, r)
            if best_pair is None:
                continue
            room = best_pair[1]
            start_m = expiry_offsets[len(self.tenants)] - LEASE_MONTHS
            self._place(t, room, start_m, mode=self.best_travel(t, room)[1], charge_move=False)
            t.tenure_months = -start_m
            self.tenants[t.tenant_id] = t
            vacant.remove(room)
            self.seated_by[t.group] += 1
        self.next_tenant_id = drawn
        self.initial_applicants_drawn = drawn
        self._finish_initialize()

    def _finish_initialize(self) -> None:
        self.seated = len(self.tenants)
        # Seed initial rolling zone vacancy history
        for z in ZONES:
            zid = z["id"]
            emp = sum(1 for r in self.rooms if r.zone == zid and r.tenant_id is None)
            self.zone_vac_hist[zid].append(emp)
        self._initialized = True

    # ---- Monthly Tick: Compat v0.6 Sequential vs v0.7 4-Step Batched ----

    def _step_compat_v06(self) -> None:
        rng = self.rng
        rule_ll = RuleLandlordV06Compat()
        rule_t = RuleTenantV06Compat()

        # Vacant room monthly -3% decay
        for r in self.rooms:
            if r.tenant_id is None:
                r.vacant_for += 1
                if r.vacant_for > 1:
                    r.rent = max(self.floor_rent(r), r.rent * 0.97)

        vacant = [r for r in self.rooms if r.tenant_id is None]

        # 2% churn + newcomer arrivals
        for t in [x for x in list(self.tenants.values()) if rng.random() < CHURN]:
            room = self.rooms_by_id[t.room_id]
            del self.tenants[t.tenant_id]
            self._vacate_and_price(room, rule_ll)
            vacant.append(room)
            for _ in range(10):
                n = Tenant(self.next_tenant_id, rng, compat_v06=True)
                self.next_tenant_id += 1
                placed = False
                for _ in range(3):
                    cands = self._sample_candidates(n, vacant, see_all=False)
                    cards = [self._build_room_card(n, r, r.rent, moving=True) for r in cands]
                    ctx = {"month": self.month + 1, "tenant": self._tenant_profile_dict(n), "candidates": cards, "hard_floor": FLOOR, "announcement": None}
                    res = self._call_tenant("search", ctx, validate_search, rule_t.search)
                    pick_score = math.inf
                    if res["apply"]:
                        rid = res["apply"][0]["room_id"]
                        room_pick = self.rooms_by_id[rid]
                        pick_score = self.rule_score(n, room_pick, room_pick.rent, moving=True)
                        if self.cfg.demand_k:
                            self._browse_v06(n, pick_score)
                        vacant.remove(room_pick)
                        self._place(n, room_pick, self.month, mode=res["apply"][0]["mode"], charge_move=True)
                        self.tenants[n.tenant_id] = n
                        placed = True
                        break
                    if self.cfg.demand_k:
                        self._browse_v06(n, pick_score)
                if placed:
                    break
                if self.month >= self.cfg.line_opens:
                    self.blocked[n.group] += 1

        # Expiring leases
        for t in list(self.tenants.values()):
            if t.expires > self.month:
                continue
            cur_room = self.rooms_by_id[t.room_id]
            l_ctx = self._landlord_base_ctx(cur_room)
            l_ctx["tenant_tenure_months"] = t.tenure_months
            l_ctx["tenant_good_standing"] = t.good_standing
            quote = self._call_landlord("renewal_offer", l_ctx, validate_renewal_offer, rule_ll.renewal_offer)["rent"]

            cands = self._sample_candidates(t, vacant, see_all=False)
            cur_card = self._build_room_card(t, cur_room, quote, moving=False)
            cand_cards = [self._build_room_card(t, r, r.rent, moving=True) for r in cands]
            t_ctx = {
                "month": self.month + 1,
                "tenant": self._tenant_profile_dict(t),
                "current_room": cur_card,
                "candidates": cand_cards,
                "hard_floor": FLOOR,
                "announcement": None,
            }
            res = self._call_tenant("at_expiry", t_ctx, validate_at_expiry, rule_t.at_expiry)
            if res["action"] == "leave":
                if self.cfg.demand_k:
                    self._browse_v06(t, math.inf)
                del self.tenants[t.tenant_id]
                self._vacate_and_price(cur_room, rule_ll)
                vacant.append(cur_room)
                if self.month >= self.cfg.line_opens:
                    self.left += 1
                    self.left_by[t.group] += 1
            elif res["action"] == "renew":
                if self.cfg.demand_k:
                    self._browse_v06(t, self.rule_score(t, cur_room, quote, moving=False))
                cur_room.rent = quote
                t.expires = self.month + LEASE_MONTHS
                t.mode = res["mode"]
            else:
                target = self.rooms_by_id[res["apply"][0]["room_id"]]
                if self.cfg.demand_k:
                    self._browse_v06(t, self.rule_score(t, target, target.rent, moving=True))
                self._vacate_and_price(cur_room, rule_ll)
                vacant.append(cur_room)
                if target in vacant:
                    vacant.remove(target)
                self._place(t, target, self.month, mode=res["apply"][0]["mode"], charge_move=True)
                if self.month >= self.cfg.line_opens:
                    self.moves += 1

    def _step_v07(self) -> None:
        """v0.7 4-step batched monthly clearing:
        1. Vacant rooms age & reprice via price_vacant.
        2. 2% external churn vacates rooms; newcomers submit up to 2 applications into the monthly pool.
        3. Expiring leases: landlord renewal_offer -> tenant at_expiry -> optional single-round answer_counter.
           Movers submit up to 2 applications into the SAME monthly pool (holding their old room as safe fallback until matched!).
        4. Unified applicant clearing: multi-applicant rooms call landlord pick_applicant; losers fall back to 2nd choice or safe renewal.
        """
        rule_ll = RuleLandlord()
        rule_t = RuleTenant()

        ev = {
            "tr_vacates": 0,
            "tr_move_ins": 0,
            "tr_move_in_incomes": [],
            "tr_move_in_cash": [],
            "tr_move_in_groups": {"low": 0, "mid": 0, "high": 0},
            "tr_expiries": 0,
            "tr_renewals": 0,
            "tr_renewal_hikes": [],
            "counters": 0,
            "counter_accepts": 0,
            "multi_app_rooms": 0,
            "zone_apps": {z["id"]: 0 for z in ZONES},
        }
        self._m_events = ev

        # Update tenure & dynamic monthly cash savings for seated tenants
        for t in self.tenants.values():
            t.tenure_months += 1
            if self.cfg.use_dynamic_ledger:
                r = self.rooms_by_id[t.room_id]
                way = self.best_travel(t, r)
                surplus = t.income - r.rent - way[3] - FLOOR
                if surplus > 0:
                    t.cash += self.cfg.savings_rate * surplus

        # ---- Step 1: Existing vacant rooms age & reprice ----
        for r in self.rooms:
            if r.tenant_id is None:
                r.vacant_for += 1
                if r.vacant_for > 1:
                    ctx = self._landlord_base_ctx(r)
                    res = self._call_landlord("price_vacant", ctx, validate_price_vacant, rule_ll.price_vacant)
                    r.rent = res["rent"]
                    r.up_front = res["up_front"]

        # ---- Step 2: 2% external churn + exogenous monthly inflow of CBD job-seekers ----
        # A2: churn is a per-(tenant, month) draw, so a tenant present in every branch leaves in every branch
        present_ids = sorted(self.tenants)
        leavers = sorted(
            (t for t in self.tenants.values() if self._keyed_rng("churn", t.tenant_id, self.month).random() < CHURN),
            key=lambda t: self._keyed_rng("order_churn", t.tenant_id, self.month).random(),
        )
        for t in leavers:
            room = self.rooms_by_id[t.room_id]
            del self.tenants[t.tenant_id]
            if room.zone in self.cfg.treated_zones:
                ev["tr_vacates"] += 1
            self._vacate_and_price(room, rule_ll)

        # Exogenous inflow (~2x expected churn) keeps occupancy in realistic 90-96% equilibrium
        # and creates genuine multi-applicant competition without scenario-dependent backfilling.
        n_arrivals = max(2, round(self.cfg.n_rooms * CHURN * 2.0))
        newcomers_to_place: List[Tenant] = []
        for _ in range(n_arrivals):
            newcomers_to_place.append(Tenant(self.next_tenant_id, self.arrival_rng, compat_v06=False))
            self.next_tenant_id += 1
        self.external_log.append({
            "month": self.month + 1,
            "present": present_ids,
            "leavers": [t.tenant_id for t in leavers],
            "newcomers": [(n.tenant_id, n.wage, n.couple, round(n.cash, 6), n.good_standing) for n in newcomers_to_place],
        })

        vacant_pool = [r for r in self.rooms if r.tenant_id is None]
        # Track applications: list of dicts {tenant, is_newcomer, old_room, fallback_renew_rent, fallback_mode, apply: [{room_id, mode}]}
        pending_applicants: List[Dict[str, Any]] = []

        for n in newcomers_to_place:
            cands = self._sample_candidates(n, vacant_pool, see_all=False)
            if not cands:
                if self.month >= self.cfg.announce_month:
                    self.blocked[n.group] += 1
                continue
            cards = [self._build_room_card(n, r, r.rent, moving=True) for r in cands]
            t_ctx = {
                "month": self.month + 1,
                "tenant": self._tenant_profile_dict(n),
                "candidates": cards,
                "hard_floor": FLOOR,
                "announcement": self._announcement_payload(),
            }
            res = self._call_tenant("search", t_ctx, validate_search, rule_t.search)
            if res["apply"]:
                pending_applicants.append({
                    "tenant": n,
                    "is_newcomer": True,
                    "old_room": None,
                    "fallback_renew_rent": None,
                    "fallback_mode": None,
                    "apply": res["apply"],
                })
                for item in res["apply"]:
                    ev["zone_apps"][self.rooms_by_id[item["room_id"]].zone] += 1
            else:
                if self.month >= self.cfg.announce_month:
                    self.blocked[n.group] += 1

        # ---- Step 3: Expiring leases (randomized order!) ----
        expiring = sorted(
            (t for t in self.tenants.values() if t.expires <= self.month),
            key=lambda t: self._keyed_rng("order_expiry", t.tenant_id, self.month).random(),
        )

        for t in expiring:
            cur_room = self.rooms_by_id[t.room_id]
            in_treated = cur_room.zone in self.cfg.treated_zones
            if in_treated:
                ev["tr_expiries"] += 1

            # 3a. Landlord renewal offer
            l_ctx = self._landlord_base_ctx(cur_room)
            l_ctx["tenant_tenure_months"] = t.tenure_months
            l_ctx["tenant_good_standing"] = t.good_standing
            offer_res = self._call_landlord("renewal_offer", l_ctx, validate_renewal_offer, rule_ll.renewal_offer)
            quote = offer_res["rent"]
            if l_ctx["zone_vacancy_smooth"] < 0.04:  # H3 concession diagnostic: tight-market renewal quotes
                self.tight_renewals[0] += 1
                self.tight_renewals[1] += int(quote <= cur_room.rent * 1.0005)

            # 3b. Tenant at_expiry decision (with renewal + up to 5 candidates)
            cands = self._sample_candidates(t, vacant_pool, see_all=False)
            cur_card = self._build_room_card(t, cur_room, quote, moving=False)
            cand_cards = [self._build_room_card(t, r, r.rent, moving=True) for r in cands]
            t_ctx = {
                "month": self.month + 1,
                "tenant": self._tenant_profile_dict(t),
                "current_room": cur_card,
                "candidates": cand_cards,
                "hard_floor": FLOOR,
                "announcement": self._announcement_payload(),
            }
            t_res = self._call_tenant("at_expiry", t_ctx, validate_at_expiry, rule_t.at_expiry)
            act = t_res["action"]

            # 3c. Optional single-round counter-offer
            if act == "counter":
                ev["counters"] += 1
                c_ctx = self._landlord_base_ctx(cur_room)
                c_ctx["tenant_tenure_months"] = t.tenure_months
                c_ctx["tenant_good_standing"] = t.good_standing
                c_ctx["initial_offer"] = quote
                c_ctx["counter_rent"] = t_res["rent"]
                ans = self._call_landlord("answer_counter", c_ctx, validate_answer_counter, rule_ll.answer_counter)
                if ans["accept"]:
                    ev["counter_accepts"] += 1
                    agreed = ans["rent"]
                    if in_treated:
                        ev["tr_renewals"] += 1
                        ev["tr_renewal_hikes"].append((agreed - cur_room.rent) / cur_room.rent)
                    cur_room.rent = agreed
                    t.expires = self.month + LEASE_MONTHS
                    t.mode = t_res["mode"]
                    continue
                # Counter rejected -> execute bundled fallback without an extra round-trip LLM call!
                fb_act = t_res["if_rejected"]
                if fb_act == "accept_offer" and cur_card["affordable"]:
                    act = "renew"
                elif fb_act == "move" and t_res["apply"]:
                    act = "move"
                else:
                    act = "leave"

            if act == "renew":
                if in_treated:
                    ev["tr_renewals"] += 1
                    ev["tr_renewal_hikes"].append((quote - cur_room.rent) / cur_room.rent)
                cur_room.rent = quote
                t.expires = self.month + LEASE_MONTHS
                t.mode = t_res["mode"]
            elif act == "leave":
                del self.tenants[t.tenant_id]
                if in_treated:
                    ev["tr_vacates"] += 1
                self._vacate_and_price(cur_room, rule_ll)
                vacant_pool.append(cur_room)
                if self.month >= self.cfg.announce_month:
                    self.left += 1
                    self.left_by[t.group] += 1
            elif act == "move":
                pending_applicants.append({
                    "tenant": t,
                    "is_newcomer": False,
                    "old_room": cur_room,
                    "fallback_renew_rent": quote if cur_card["affordable"] else None,
                    "fallback_mode": cur_card["rule_best_mode"] if cur_card["affordable"] else None,
                    "apply": t_res["apply"],
                })
                for item in t_res["apply"]:
                    ev["zone_apps"][self.rooms_by_id[item["room_id"]].zone] += 1

        # ---- Step 4: Unified Multi-Applicant Clearing (Round 1 = 1st choice, Round 2 = 2nd choice) ----
        matched_tenants = set()
        for choice_idx in (0, 1):
            by_room: Dict[int, List[Tuple[Dict[str, Any], str]]] = {}
            for app in pending_applicants:
                tid = app["tenant"].tenant_id
                if tid in matched_tenants or len(app["apply"]) <= choice_idx:
                    continue
                target_item = app["apply"][choice_idx]
                rid = target_item["room_id"]
                room = self.rooms_by_id[rid]
                if room.tenant_id is not None:
                    continue  # Already taken in round 1
                by_room.setdefault(rid, []).append((app, target_item["mode"]))

            for rid in sorted(by_room.keys()):
                room = self.rooms_by_id[rid]
                contenders = by_room[rid]
                if len(contenders) == 1:
                    win_app, win_mode = contenders[0]
                else:
                    ev["multi_app_rooms"] += 1
                    p_ctx = self._landlord_base_ctx(room)
                    # Anonymized, occupation-free applicant cards!
                    p_ctx["applicants"] = [
                        {
                            "tenant_id": a["tenant"].tenant_id,
                            "offered_rent": round(room.rent, 2),
                            "requested_up_front": room.up_front,
                            "income_to_rent": round(a["tenant"].income / max(room.rent, 1.0), 2),
                            "cash_verified": True,
                            "household_size": 2 if a["tenant"].couple else 1,
                            "good_standing": a["tenant"].good_standing,
                        }
                        for a, _ in contenders
                    ]
                    pick = self._call_landlord("pick_applicant", p_ctx, validate_pick_applicant, rule_ll.pick_applicant)
                    chosen_tid = pick["tenant_id"]
                    if chosen_tid is None:
                        continue
                    win_app, win_mode = next((a, m) for a, m in contenders if a["tenant"].tenant_id == chosen_tid)

                # Finalize match
                t = win_app["tenant"]
                matched_tenants.add(t.tenant_id)
                old_room = win_app["old_room"]
                if old_room is not None:
                    if old_room.zone in self.cfg.treated_zones:
                        ev["tr_vacates"] += 1
                    self._vacate_and_price(old_room, rule_ll)
                    if self.month >= self.cfg.announce_month:
                        self.moves += 1
                else:
                    self.tenants[t.tenant_id] = t

                # Liquid funds before paying move cost / new deposit (H2 compares pre-move wealth)
                pre_move_cash = t.cash + t.locked_deposit
                self._place(t, room, self.month, mode=win_mode, charge_move=True)
                if room.zone in self.cfg.treated_zones:
                    ev["tr_move_ins"] += 1
                    ev["tr_move_in_incomes"].append(t.income)
                    ev["tr_move_in_cash"].append(pre_move_cash)
                    ev["tr_move_in_groups"][t.group] += 1

        # Handle unmatched applicants safely
        for app in pending_applicants:
            t = app["tenant"]
            if t.tenant_id in matched_tenants:
                continue
            if app["is_newcomer"]:
                if self.month >= self.cfg.announce_month:
                    self.blocked[t.group] += 1
            else:
                # Safe fallback: stay at current renewal quote if affordable; otherwise exit
                old_room = app["old_room"]
                if app["fallback_renew_rent"] is not None:
                    if old_room.zone in self.cfg.treated_zones:
                        ev["tr_renewals"] += 1
                        ev["tr_renewal_hikes"].append((app["fallback_renew_rent"] - old_room.rent) / old_room.rent)
                    old_room.rent = app["fallback_renew_rent"]
                    t.expires = self.month + LEASE_MONTHS
                    t.mode = app["fallback_mode"]
                else:
                    del self.tenants[t.tenant_id]
                    if old_room.zone in self.cfg.treated_zones:
                        ev["tr_vacates"] += 1
                    self._vacate_and_price(old_room, rule_ll)
                    if self.month >= self.cfg.announce_month:
                        self.left += 1
                        self.left_by[t.group] += 1

        # Update rolling zone vacancy & application histories at end of month
        for z in ZONES:
            zid = z["id"]
            emp = sum(1 for r in self.rooms if r.zone == zid and r.tenant_id is None)
            self.zone_vac_hist[zid].append(emp)
            self.zone_vacant_hist[zid].append(max(emp, 1))
            self.zone_apps_hist[zid].append(ev["zone_apps"][zid])

    # ---- Monthly Measurement & Snapshot ----

    def rent_snapshot(self) -> Dict[Tuple[str, str], float]:
        rents: Dict[Tuple[str, str], List[float]] = {}
        for r in self.rooms:
            rents.setdefault((r.zone, r.kind), []).append(r.rent)
        return {k: st.mean(v) for k, v in rents.items()}

    def _record_m12_cohort(self) -> None:
        """Freeze the cohort of M12 treated-zone residents for panel benefit-incidence tracking."""
        self.m12_treated_cohort = {}
        for t in self.tenants.values():
            r = self.rooms_by_id[t.room_id]
            if r.zone in self.cfg.treated_zones:
                way = self.best_travel(t, r)
                hourly = 0.5 * t.wage / 260.0
                time_cost = 2 * WORKDAYS * way[2] / 60.0 * hourly
                self.m12_treated_cohort[t.tenant_id] = {
                    "group": t.group,
                    "zone": r.zone,
                    "kind": r.kind,
                    "income": t.income,
                    "m12_rent": r.rent,
                    "m12_commute_min": way[2],
                    "m12_fare": way[3],
                    "m12_full_cost": r.rent + way[3] + time_cost,
                }

    def _measure_month(self) -> Dict[str, Any]:
        people = list(self.tenants.values())
        low = [t for t in people if t.low]
        info = [(t, self.rooms_by_id[t.room_id], self.best_travel(t, self.rooms_by_id[t.room_id])) for t in people]
        watch = set(self.cfg.treated_zones)

        tr_rooms = [r for r in self.rooms if r.zone in watch]
        ot_rooms = [r for r in self.rooms if r.zone not in watch]
        tr_idx = st.mean(r.rent / r.start for r in tr_rooms) * 100.0 if tr_rooms else 100.0
        ot_idx = st.mean(r.rent / r.start for r in ot_rooms) * 100.0 if ot_rooms else 100.0
        all_idx = st.mean(r.rent / r.start for r in self.rooms) * 100.0

        vac_all = sum(1 for r in self.rooms if r.tenant_id is None) / len(self.rooms)
        vac_tr = sum(1 for r in tr_rooms if r.tenant_id is None) / max(len(tr_rooms), 1)
        vac_ot = sum(1 for r in ot_rooms if r.tenant_id is None) / max(len(ot_rooms), 1)

        inside = [(t, r, i) for t, r, i in info if r.zone in watch]
        outside = [(t, r, i) for t, r, i in info if r.zone not in watch]

        comm_all = st.mean(i[2] for _, _, i in info) if info else 0.0
        comm_tr = st.mean(i[2] for _, _, i in inside) if inside else 0.0
        comm_ot = st.mean(i[2] for _, _, i in outside) if outside else 0.0
        over60 = st.mean(i[2] > 60 for _, _, i in info) if info else 0.0
        burden_all = st.mean(r.rent / t.income for t, r, _ in info) if info else 0.0

        ev = self._m_events
        rec = {
            "month": self.month + 1,
            "announced": self.announced,
            "line_open": self.line_built,
            "occupied": len(people),
            "vacancy_all": round(vac_all, 4),
            "vacancy_treated": round(vac_tr, 4),
            "vacancy_other": round(vac_ot, 4),
            "rent_index_all": round(all_idx, 3),
            "rent_index_treated": round(tr_idx, 3),
            "rent_index_other": round(ot_idx, 3),
            "commute_all": round(comm_all, 2),
            "commute_treated": round(comm_tr, 2),
            "commute_other": round(comm_ot, 2),
            "over60": round(over60, 4),
            "burden_all": round(burden_all, 4),
            "treated_low_share": round(st.mean(t.low for t, _, _ in inside), 4) if inside else 0.0,
            "treated_vacates": ev.get("tr_vacates", 0),
            "treated_move_ins": ev.get("tr_move_ins", 0),
            "treated_move_in_incomes": ev.get("tr_move_in_incomes", []),
            "treated_move_in_cash": ev.get("tr_move_in_cash", []),
            "treated_move_in_groups": ev.get("tr_move_in_groups", {"low": 0, "mid": 0, "high": 0}),
            "treated_expiries": ev.get("tr_expiries", 0),
            "treated_renewals": ev.get("tr_renewals", 0),
            "treated_renewal_hikes": ev.get("tr_renewal_hikes", []),
            "counters": ev.get("counters", 0),
            "counter_accepts": ev.get("counter_accepts", 0),
            "multi_app_rooms": ev.get("multi_app_rooms", 0),
        }
        self.monthly_records.append(rec)
        if self._mon_fp is not None:
            self._mon_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # Accumulate v0.6-compatible tail metrics over final 12 months
        if self.month >= self.cfg.months - 12:
            self.tail["commute"].append(comm_all)
            self.tail["over60"].append(over60)
            self.tail["low_commute"].append(st.mean(i[2] for t, _, i in info if t.low) if low else 0.0)
            self.tail["low_cash"].append(st.mean(r.rent + i[3] for t, r, i in info if t.low) if low else 0.0)
            self.tail["low_cost"].append(st.mean(r.rent + i[0] for t, r, i in info if t.low) if low else 0.0)
            for gname in ("low", "mid", "high"):
                grp = [(t, r) for t, r, _ in info if t.group == gname]
                self.tail[gname + "_burden"].append(st.mean(r.rent / t.income for t, r in grp) if grp else 0.0)
            self.tail["all_burden"].append(burden_all)
            for t, r, _ in info:
                cell = self.burden_cells.setdefault((r.kind, t.group), [0.0, 0])
                cell[0] += r.rent / t.income
                cell[1] += 1
            self.tail["low_over30"].append(st.mean(r.rent / t.income > 0.30 for t, r, _ in info if t.low) if low else 0.0)
            self.tail["low_over50"].append(st.mean(r.rent / t.income > 0.50 for t, r, _ in info if t.low) if low else 0.0)
            self.tail["low_near"].append(st.mean(r.zone in ("Z00", "Z01", "Z02", "Z03", "Z04") for t, r, _ in info if t.low) if low else 0.0)
            self.tail["watch_share"].append(len(inside) / max(len(info), 1))
            self.tail["watch_low"].append(st.mean(t.low for t, _, _ in inside) if inside else 0.0)
            self.tail["watch_commute"].append(comm_tr)
            self.tail["other_commute"].append(comm_ot)
            self.tail["revenue"].append(sum(r.rent for r in self.rooms if r.tenant_id is not None) / len(self.rooms))
            self.tail["vacant"].append(vac_all)
            self.tail["n"].append(len(people))
            for t, _, i in info:
                m_used = t.mode or i[1]
                self.modes_count[(t.group, m_used)] = self.modes_count.get((t.group, m_used), 0) + 1
            self.after_snapshots.append(self.rent_snapshot())
        return rec

    def _compute_cohort_summary(self) -> Dict[str, Any]:
        """Evaluate M12 treated-zone cohort at end of simulation (eliminates Simpson's paradox!)."""
        by_grp: Dict[str, Dict[str, Any]] = {}
        for gname in ("low", "mid", "high"):
            members = [(tid, d) for tid, d in self.m12_treated_cohort.items() if d["group"] == gname]
            if not members:
                by_grp[gname] = {"n_m12": 0, "stayed_in_treated": 0, "retention_rate": 0.0, "delta_full_cost": None}
                continue
            stayed = []
            for tid, d in members:
                t = self.tenants.get(tid)
                if t is not None:
                    r = self.rooms_by_id[t.room_id]
                    if r.zone in self.cfg.treated_zones:
                        way = self.best_travel(t, r)
                        hourly = 0.5 * t.wage / 260.0
                        full_now = r.rent + way[3] + 2 * WORKDAYS * way[2] / 60.0 * hourly
                        stayed.append(full_now - d["m12_full_cost"])
            by_grp[gname] = {
                "n_m12": len(members),
                "stayed_in_treated": len(stayed),
                "retention_rate": round(len(stayed) / len(members), 3),
                "delta_full_cost": round(st.mean(stayed), 1) if stayed else None,
            }
        return by_grp

    def _open_logs(self) -> None:
        if self.cfg.log_dir:
            p = Path(self.cfg.log_dir)
            p.mkdir(parents=True, exist_ok=True)
            # First open of this log_dir by this object: truncate, then flush in-memory (warm-up) records.
            # Only a later run_until() call on the same object appends, so re-running into an existing
            # --out directory never duplicates lines.
            first_open = self._log_dir_written != str(p)
            mode = "w" if first_open else "a"
            if self.cfg.record_decisions:
                self._dec_fp = (p / "decisions.jsonl").open(mode, encoding="utf-8")
            else:
                self._dec_fp = None
                if first_open:
                    (p / "decisions.jsonl").unlink(missing_ok=True)
            self._mon_fp = (p / "monthly.jsonl").open(mode, encoding="utf-8")
            self._log_dir_written = str(p)
            if first_open:
                for rec in self.monthly_records:
                    self._mon_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
                if self._dec_fp is not None:
                    for rec in self.decision_records:
                        self._dec_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _close_logs(self) -> None:
        if self._dec_fp is not None:
            self._dec_fp.close()
            self._dec_fp = None
        if self._mon_fp is not None:
            self._mon_fp.close()
            self._mon_fp = None

    # ---- Run Controls ----

    def run_until(self, end_month: int) -> None:
        """Advance simulation from self.month up to end_month (exclusive)."""
        self.initialize()
        self._open_logs()
        try:
            while self.month < end_month:
                if self.month == self.cfg.announce_month:
                    self._record_m12_cohort()
                    self.announce()
                if self.month == self.cfg.line_opens:
                    self.before_snapshot = self.rent_snapshot()
                    self.open_line()
                if self.cfg.compat_v06:
                    self._step_compat_v06()
                else:
                    self._step_v07()
                self._measure_month()
                self.month += 1
        finally:
            self._close_logs()

    def run(self) -> Dict[str, Any]:
        """Run full simulation to cfg.months and return summary dictionary."""
        self.run_until(self.cfg.months)
        return self.summary()

    def summary(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {k: st.mean(v) if v else 0.0 for k, v in self.tail.items()}
        out.update(
            scenario=self.cfg.scenario,
            seed=self.cfg.seed,
            moves=self.moves,
            left=self.left,
            seated=self.seated,
            left_low=self.left_by["low"],
            left_mid=self.left_by["mid"],
            left_high=self.left_by["high"],
            seated_low=self.seated_by["low"] / max(self.wanted_by["low"], 1),
            seated_mid=self.seated_by["mid"] / max(self.wanted_by["mid"], 1),
            seated_high=self.seated_by["high"] / max(self.wanted_by["high"], 1),
            blocked_low=self.blocked["low"],
            blocked_mid=self.blocked["mid"],
            blocked_high=self.blocked["high"],
            decision_count=self.decision_count,
            fallback_count=self.fallback_count,
            fallback_rate=(self.fallback_count / max(self.decision_count, 1)),
            total_tokens=self.total_tokens,
            m12_cohort=self._compute_cohort_summary(),
        )
        out["before"] = self.before_snapshot
        if self.after_snapshots:
            out["after"] = {k: st.mean(a[k] for a in self.after_snapshots if k in a) for k in self.after_snapshots[0]}
        else:
            out["after"] = self.rent_snapshot()
        out["modes"] = self.modes_count
        out["tight_renewals"] = list(self.tight_renewals)
        out["guardrail_counts"] = dict(sorted(self.guardrail_counts.items()))
        out["burden_cells"] = {f"{k}|{g}": [round(sv / n, 5), n] for (k, g), (sv, n) in sorted(self.burden_cells.items())}
        out["landlords_meta"] = [ll.to_dict() for ll in self.landlords.values()]
        # Key monthly milestones for quick inspection
        if self.monthly_records:
            m_by_num = {r["month"]: r for r in self.monthly_records}
            out["rent_tr_m12"] = m_by_num.get(12, {}).get("rent_index_treated", 100.0)
            out["rent_tr_m24"] = m_by_num.get(24, {}).get("rent_index_treated", 100.0)
            out["rent_tr_m36"] = m_by_num.get(self.cfg.months, {}).get("rent_index_treated", 100.0)
            m13_24 = [r for r in self.monthly_records if 13 <= r["month"] <= 24]
            out["tr_vacates_m13_24"] = sum(r["treated_vacates"] for r in m13_24)
            out["tr_move_ins_m13_24"] = sum(r["treated_move_ins"] for r in m13_24)
            out["tr_expiries_m13_24"] = sum(r["treated_expiries"] for r in m13_24)
            out["tr_renewals_m13_24"] = sum(r["treated_renewals"] for r in m13_24)
            out["multi_app_total"] = sum(r["multi_app_rooms"] for r in self.monthly_records)
            out["counters_total"] = sum(r["counters"] for r in self.monthly_records)
            out["counter_accepts_total"] = sum(r["counter_accepts"] for r in self.monthly_records)
        if self.cfg.log_dir:
            # Save JSON-serializable summary (convert tuple keys in before/after/modes)
            ser = dict(out)
            ser["before"] = {f"{z}|{k}": v for (z, k), v in out["before"].items()}
            ser["after"] = {f"{z}|{k}": v for (z, k), v in out["after"].items()}
            ser["modes"] = {f"{g}|{m}": v for (g, m), v in out["modes"].items()}
            (Path(self.cfg.log_dir) / "summary.json").write_text(json.dumps(ser, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


# ---- Replay Utility (Acceptance Criterion #6) ----

def replay_agent(decisions_jsonl: str, agent_type: str, agent_id: int) -> List[Dict[str, Any]]:
    """Reconstruct the complete chronological decision history of any tenant or landlord from decisions.jsonl."""
    events: List[Dict[str, Any]] = []
    with Path(decisions_jsonl).open("r", encoding="utf-8") as fp:
        for line in fp:
            rec = json.loads(line)
            if rec["agent_type"] == agent_type and rec["agent_id"] == agent_id:
                events.append(rec)
    events.sort(key=lambda r: r["month"])
    return events
