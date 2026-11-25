"""Board loader, room allocation (v0.6 compat & v0.7 oversampled), OLS zone amenity, and 40-landlord assignment."""
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import random
import statistics as st
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ANALYSIS = HERE.parent / "analysis"

BOARD = json.loads((ANALYSIS / "board_cbd_v01.json").read_text(encoding="utf-8"))
ZONES = BOARD["zones"]
ZONE_BY_ID = {z["id"]: z for z in ZONES}
ZONE_SHOCK = json.loads((ANALYSIS / "zone_shock.json").read_text(encoding="utf-8"))

TYPES = ["低价房", "便宜单间", "合租单间", "整租"]
QUALITY = {"低价房": 1.0, "便宜单间": 0.5, "合租单间": 0.25, "整租": 0.0}
TYPE_AMENITY_SCALE = {"低价房": 0.10, "便宜单间": 0.25, "合租单间": 0.45, "整租": 1.00}

TREATED_ZONES = ("Z05", "Z11")
EAST_EXPRESS = {"Z05": 12, "Z11": 15}
REPLAY_SHOCK = {z: v["replay_2015_2018"] for z, v in ZONE_SHOCK.items()}
SHOCKS = {"none": {}, "replay": REPLAY_SHOCK, "east_express": EAST_EXPRESS}

TAU_DEFAULT = 40
# Station-distance bands matching Beijing Commuting Survey (<300, 300-800, 800-1500, >1500m)
STATION_DIST_BANDS = ((250, 0.22), (600, 0.50), (1100, 0.19), (1700, 0.09))
STATION_DIST_MEAN_M = sum(d * w for d, w in STATION_DIST_BANDS)
WALK_MIN_PER_KM = 12.0  # ~5 km/h

LANDLORD_KINDS = (("个人房东", 0.65), ("托管机构", 0.35))
LANDLORD_RISKS = (("怕空置", 0.55), ("愿意等", 0.45))


def largest_remainder(weights: List[float], total: int) -> List[int]:
    if total <= 0:
        return [0 for _ in weights]
    s_w = sum(weights)
    if s_w <= 0:
        out = [0 for _ in weights]
        for i in range(total):
            out[i % len(weights)] += 1
        return out
    scaled = [w * total / s_w for w in weights]
    out = [math.floor(s) for s in scaled]
    rem = total - sum(out)
    for i in sorted(range(len(out)), key=lambda i: scaled[i] - out[i], reverse=True)[:rem]:
        out[i] += 1
    return out


def compute_zone_amenities() -> Tuple[Dict[str, float], Dict[str, float]]:
    """Derive non-CBD spatial amenity value directly from 2018 whole-unit rent OLS residuals on subway minutes.

    Returns:
        resid_rmb: {zone_id: residual in RMB/month} (positive in West/North, negative in East/South)
        score_1_5: {zone_id: interpretable 1.0-5.0 amenity score for LLM cards}
    """
    xs = [z["options"]["地铁"]["min"] for z in ZONES]
    ys = [z["rents"]["整租"] for z in ZONES]
    mx, my = st.mean(xs), st.mean(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    intercept = my - slope * mx
    resid = {z["id"]: z["rents"]["整租"] - (intercept + slope * z["options"]["地铁"]["min"]) for z in ZONES}
    rmin, rmax = min(resid.values()), max(resid.values())
    span = max(rmax - rmin, 1.0)
    score = {zid: round(1.0 + 4.0 * (val - rmin) / span, 1) for zid, val in resid.items()}
    return resid, score


ZONE_AMENITY_RMB, ZONE_AMENITY_SCORE = compute_zone_amenities()


def zone_label(zone_id: str) -> str:
    """Anonymized spatial label (no real Beijing neighborhood names)."""
    z = ZONE_BY_ID[zone_id]
    return f"{zone_id}（{z['dir']}向，{z['ring']}圈）"


def allocate_v06(n_rooms: int = 1200, tau: float = TAU_DEFAULT, low_cost: float = 1.0) -> Dict[Tuple[str, str], int]:
    """Exact reproduction of Lease Day v0.6 room allocation."""
    weights = [z["renters_sample"] * math.exp(-z["options"]["地铁"]["min"] / tau) for z in ZONES]
    rooms: Dict[Tuple[str, str], int] = {}
    for z, n in zip(ZONES, largest_remainder(weights, n_rooms)):
        shares = [z["shares"][k] * (low_cost if k in TYPES[:2] else 1.0) for k in TYPES]
        for k, c in zip(TYPES, largest_remainder(shares, n)):
            rooms[(z["id"], k)] = c
    return rooms


def allocate_v07(
    n_rooms: int = 240,
    treated_counts: Optional[Dict[str, int]] = None,
    tau: float = TAU_DEFAULT,
    low_cost: float = 1.0,
) -> Dict[Tuple[str, str], int]:
    """v0.7 allocation: oversample treated zones (default Z05=24, Z11=16, total 40 = 16.7%), scale others proportionally."""
    if treated_counts is None:
        treated_counts = {"Z05": 24, "Z11": 16}
    treated_total = sum(treated_counts.values())
    other_total = n_rooms - treated_total
    if other_total < 0:
        raise ValueError("treated_counts exceed total n_rooms")
    others = [z for z in ZONES if z["id"] not in treated_counts]
    w_other = [z["renters_sample"] * math.exp(-z["options"]["地铁"]["min"] / tau) for z in others]
    zcounts = dict(treated_counts)
    for z, n in zip(others, largest_remainder(w_other, other_total)):
        zcounts[z["id"]] = n

    rooms: Dict[Tuple[str, str], int] = {}
    for z in ZONES:
        n = zcounts[z["id"]]
        shares = [z["shares"][k] * (low_cost if k in TYPES[:2] else 1.0) for k in TYPES]
        for k, c in zip(TYPES, largest_remainder(shares, n)):
            rooms[(z["id"], k)] = c
    return rooms


@dataclass
class Landlord:
    landlord_id: int
    kind: str  # "个人房东" or "托管机构"
    risk: str  # "怕空置" or "愿意等"
    treated: bool  # True iff exclusively owns treated-zone rooms
    zones: List[str] = field(default_factory=list)
    room_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "landlord_id": self.landlord_id,
            "kind": self.kind,
            "risk": self.risk,
            "treated": self.treated,
            "zones": list(self.zones),
            "n_rooms": len(self.room_ids),
        }


def _weighted_choice(rng: random.Random, pairs: Tuple[Tuple[str, float], ...]) -> str:
    vals, wts = zip(*pairs)
    return rng.choices(vals, weights=wts)[0]


def sample_station_dist_m(rng: random.Random) -> int:
    vals, wts = zip(*STATION_DIST_BANDS)
    return int(rng.choices(vals, weights=wts)[0])


def station_walk_delta_min(station_dist_m: int) -> int:
    """Mean-zero walk adjustment in minutes relative to mean station access distance."""
    return round((station_dist_m - STATION_DIST_MEAN_M) / 1000.0 * WALK_MIN_PER_KM)


def assign_landlords(
    rooms: list,
    rng: random.Random,
    n_landlords: int = 40,
    treated_zones: Tuple[str, ...] = TREATED_ZONES,
) -> Dict[int, Landlord]:
    """Assign rooms to n_landlords with strict separation between treated and control landlords.

    - Treated rooms (Z05, Z11) are assigned exclusively to dedicated treated landlords (4-7 rooms each).
    - Control rooms are grouped geographically by zone order into the remaining landlords (4-8 rooms each,
      concentrated in 1-2 zones).
    """
    treated_set = set(treated_zones)
    treated_by_zone: Dict[str, list] = {}
    control_rooms: list = []
    for r in rooms:
        if r.zone in treated_set:
            treated_by_zone.setdefault(r.zone, []).append(r)
        else:
            control_rooms.append(r)

    n_treated_rooms = sum(len(v) for v in treated_by_zone.values())
    if n_treated_rooms == 0:
        n_treated_ll = 0
    else:
        n_treated_ll = max(len(treated_by_zone), round(n_landlords * n_treated_rooms / max(len(rooms), 1)))
        n_treated_ll = min(n_treated_ll, n_landlords - 1) if control_rooms else n_landlords
    n_control_ll = max(1, n_landlords - n_treated_ll) if control_rooms else 0

    landlords: Dict[int, Landlord] = {}
    lid = 0

    # 1. Dedicated treated landlords (each confined to a single treated zone!)
    if n_treated_ll > 0:
        tz_list = sorted(treated_by_zone.keys())
        tz_weights = [len(treated_by_zone[z]) for z in tz_list]
        ll_per_tz = largest_remainder(tz_weights, n_treated_ll)
        for z, k_ll in zip(tz_list, ll_per_tz):
            zrooms = list(treated_by_zone[z])
            rng.shuffle(zrooms)
            k_ll = max(1, k_ll)
            chunks = [zrooms[i::k_ll] for i in range(k_ll)]
            for chunk in chunks:
                if not chunk:
                    continue
                ll = Landlord(
                    landlord_id=lid,
                    kind=_weighted_choice(rng, LANDLORD_KINDS),
                    risk=_weighted_choice(rng, LANDLORD_RISKS),
                    treated=True,
                    zones=[z],
                    room_ids=[r.room_id for r in chunk],
                )
                for r in chunk:
                    r.landlord_id = lid
                landlords[lid] = ll
                lid += 1

    # 2. Control landlords (ordered by zone so each landlord covers 1-2 nearby zones, 4-8 rooms)
    if n_control_ll > 0:
        # Sort by (direction, ring_min, zone) so adjacent zones stay grouped
        order_key = lambda r: (ZONE_BY_ID[r.zone]["dir"], ZONE_BY_ID[r.zone]["options"]["地铁"]["min"], r.zone, r.room_id)
        ordered = sorted(control_rooms, key=order_key)
        sizes = largest_remainder([1.0] * n_control_ll, len(ordered))
        cursor = 0
        for sz in sizes:
            chunk = ordered[cursor:cursor + sz]
            cursor += sz
            if not chunk:
                continue
            z_unique = sorted({r.zone for r in chunk})
            ll = Landlord(
                landlord_id=lid,
                kind=_weighted_choice(rng, LANDLORD_KINDS),
                risk=_weighted_choice(rng, LANDLORD_RISKS),
                treated=False,
                zones=z_unique,
                room_ids=[r.room_id for r in chunk],
            )
            for r in chunk:
                r.landlord_id = lid
            landlords[lid] = ll
            lid += 1

    return landlords
