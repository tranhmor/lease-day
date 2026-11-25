"""Export Lease Day v0.7 simulation runs into static viz_data/ bundle for the 3D visualization app.

Strictly adheres to the data contract (§8.1) and academic integrity rules (§9):
- Reads completed runs (monthly.jsonl, decisions.jsonl, summary.json, room_states.jsonl).
- Computes cross-seed means + 95% CIs (aggregate/monthly_ci.json).
- Computes H1-H3 pre-registered verdicts ONLY via analyze_v07.evaluate_preregistered() (aggregate/verdicts.json).
- Selects default_seed as the median seed of M24 (P - S) treated rent index (§9.3).
- Stratifies monthly landlord reason feed with a fixed RNG seed written to meta.json (no cherry-picking, §9.2);
  computes mentions_line ratio over ALL landlord pricing decisions using the frozen keyword list (§8.1).
- Packs 36 x 240 room states into compact binary room_states.bin (16 bytes/record, ~135 KB/run).

Usage:
    python3 -m prototype_v07.export_viz --runs /tmp/verify_l --group L --baseline-runs rental_game/runs_r \
        --out rental_game/viz3d/public/viz_data --source-label "runs_d (qwen3.5:9b pilot)"
"""
import argparse
import json
import math
from pathlib import Path
import random
import shutil
import statistics as st
import struct
from typing import Any, Dict, List, Optional, Tuple

from .analyze_v07 import _load_monthly, _paired_seeds, ci95, evaluate_preregistered
from .board_v07 import BOARD, TREATED_ZONES, TYPES, ZONE_BY_ID, ZONES, allocate_v07

HERE = Path(__file__).resolve().parent
ANALYSIS = HERE.parent / "analysis"

# Frozen keyword list (§8.1) for detecting references to the new East Express Line
MENTION_KEYWORDS: List[str] = [
    "快线", "开通", "通车", "通勤改善", "通勤利好",
    "交通便利", "交通将改善", "未来利好", "溢价", "将受益",
]
FEED_SAMPLE_SEED = 20261125

# Bilingual zone labels matching analysis/viz_build.py + English transliterations
ZONE_NAMES_ZH: Dict[str, str] = {
    "Z00": "双井", "Z01": "定福庄", "Z02": "望京", "Z03": "方庄", "Z04": "金融街",
    "Z05": "果园", "Z06": "北苑", "Z07": "德胜门", "Z08": "广安门", "Z09": "马家堡",
    "Z10": "亦庄", "Z11": "武夷花园", "Z12": "天通苑", "Z13": "回龙观", "Z14": "鲁谷",
    "Z15": "看丹桥", "Z16": "后沙峪", "Z17": "西三旗", "Z18": "苹果园", "Z19": "黄村",
    "Z20": "马驹桥", "Z21": "顺义城", "Z22": "良乡", "Z23": "昌平",
}
ZONE_NAMES_EN: Dict[str, str] = {
    "Z00": "Shuangjing (CBD)", "Z01": "Dingfuzhuang", "Z02": "Wangjing", "Z03": "Fangzhuang",
    "Z04": "Financial St.", "Z05": "Guoyuan", "Z06": "Beiyuan", "Z07": "Deshengmen",
    "Z08": "Guang'anmen", "Z09": "Majiapu", "Z10": "Yizhuang", "Z11": "Wuyi Garden",
    "Z12": "Tiantongyuan", "Z13": "Huilongguan", "Z14": "Lugu", "Z15": "Kandanqiao",
    "Z16": "Houshayu", "Z17": "Xisanqi", "Z18": "Pingguoyuan", "Z19": "Huangcun",
    "Z20": "Majuqiao", "Z21": "Shunyi", "Z22": "Liangxiang", "Z23": "Changping",
}
MAJOR_ZONES = {"Z00", "Z01", "Z02", "Z03", "Z04", "Z05", "Z07", "Z10", "Z11", "Z12", "Z13", "Z21", "Z22"}

# Projection origin: CBD (Shuangjing Z00), Web Mercator scaled to km (1 scene unit = 1 km at 39.91°N)
ORIGIN_LAT = 39.9099
ORIGIN_LON = 116.4580
EARTH_R = 6378137.0
COS_LAT0 = math.cos(math.radians(ORIGIN_LAT))
METERS_PER_UNIT = 1000.0
GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))

INCOME_GROUP_CODE = {"low": 1, "mid": 2, "high": 3}

# 16-byte little-endian binary record per (month, room):
#   float32 rent, int32 tenant_id, uint8 occupied, uint8 vacant_for, uint8 group_code, uint8 commute_min, float32 income
ROOM_RECORD_STRUCT = struct.Struct("<fiBBBBf")


def _mercator_xy(lat: float, lon: float) -> Tuple[float, float]:
    x = EARTH_R * math.radians(lon)
    y = EARTH_R * math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))
    return x, y


_OX, _OY = _mercator_xy(ORIGIN_LAT, ORIGIN_LON)


def project_xz(lat: float, lon: float) -> Tuple[float, float]:
    """Project (lat, lon) to Three.js Y-up local plane (x=East km, z=South km) with CBD at (0, 0)."""
    mx, my = _mercator_xy(lat, lon)
    x = (mx - _OX) * COS_LAT0 / METERS_PER_UNIT
    z = -((my - _OY) * COS_LAT0 / METERS_PER_UNIT)  # North is -Z, South is +Z
    return x, z


def compute_zone_and_room_layout(
    centroids: Dict[str, List[float]],
    rooms_meta: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Compute pushed-apart zone centers and phyllotaxis room positions in Three.js XZ units (km)."""
    zone_ids = [z["id"] for z in ZONES]
    counts: Dict[str, int] = {zid: 0 for zid in zone_ids}
    for r in rooms_meta:
        counts[r["zone"]] = counts.get(r["zone"], 0) + 1

    spacing = 0.44  # 440m visual spacing between pillars
    clear_centre = {"Z00": 3}
    radius: Dict[str, float] = {}
    pos: Dict[str, List[float]] = {}
    true_pos: Dict[str, Tuple[float, float]] = {}

    for zid in zone_ids:
        lat, lon = centroids[zid]
        tx, tz = project_xz(lat, lon)
        true_pos[zid] = (tx, tz)
        pos[zid] = [tx, tz]
        skip = clear_centre.get(zid, 0)
        radius[zid] = 0.65 * spacing * math.sqrt(counts[zid] + skip + 0.6) + 0.35

    pos["Z00"] = [0.0, 0.0]

    # Push-apart algorithm inherited from analysis/viz_build.py
    for _ in range(500):
        moved = False
        for i, a in enumerate(zone_ids):
            for b in zone_ids[i + 1 :]:
                dx = pos[b][0] - pos[a][0]
                dz = pos[b][1] - pos[a][1]
                dist = math.hypot(dx, dz) or 1e-6
                need = radius[a] + radius[b] + 0.55
                if dist < need:
                    moved = True
                    push = (need - dist) / dist * 0.5
                    if a == "Z00":
                        pos[b][0] += dx * push * 2.0
                        pos[b][1] += dz * push * 2.0
                    elif b == "Z00":
                        pos[a][0] -= dx * push * 2.0
                        pos[a][1] -= dz * push * 2.0
                    else:
                        pos[a][0] -= dx * push
                        pos[a][1] -= dz * push
                        pos[b][0] += dx * push
                        pos[b][1] += dz * push
        if not moved:
            break

    # Build zones.json payload
    zones_out: List[Dict[str, Any]] = []
    for z in ZONES:
        zid = z["id"]
        lat, lon = centroids[zid]
        zx, zz = pos[zid]
        zones_out.append({
            "id": zid,
            "name": ZONE_NAMES_ZH.get(zid, zid),
            "name_en": ZONE_NAMES_EN.get(zid, zid),
            "dir": z["dir"],
            "ring": z["ring"],
            "lat": lat,
            "lon": lon,
            "x": round(zx, 3),
            "z": round(zz, 3),
            "true_x": round(true_pos[zid][0], 3),
            "true_z": round(true_pos[zid][1], 3),
            "radius": round(radius[zid], 3),
            "treated": zid in TREATED_ZONES,
            "major": zid in MAJOR_ZONES,
            "n_rooms": counts[zid],
            "subway_min": z["options"]["地铁"]["min"],
            "whole_rent": z["rents"]["整租"],
            "label_offset": [0.0, round(radius[zid] + 0.5, 3)],
        })

    # Per-kind rent normalization bounds (for pillar height normalization §5.2)
    kind_rents: Dict[str, List[float]] = {k: [] for k in TYPES}
    for r in rooms_meta:
        kind_rents.setdefault(r["kind"], []).append(float(r["start"]))
    kind_bounds: Dict[str, Tuple[float, float]] = {}
    for k, vals in kind_rents.items():
        if vals:
            s_vals = sorted(vals)
            lo = s_vals[max(0, int(0.05 * len(s_vals)))]
            hi = s_vals[min(len(s_vals) - 1, int(0.95 * len(s_vals)))]
            kind_bounds[k] = (lo, max(hi, lo + 100.0))
        else:
            kind_bounds[k] = (500.0, 5000.0)

    # Phyllotaxis room placement within each zone cluster
    slot: Dict[str, int] = {zid: clear_centre.get(zid, 0) for zid in zone_ids}
    rooms_out: List[Dict[str, Any]] = []
    for r in sorted(rooms_meta, key=lambda item: item["id"]):
        zid = r["zone"]
        k = slot[zid]
        slot[zid] += 1
        rr = 0.65 * spacing * math.sqrt(k + 0.5)
        th = k * GOLDEN_ANGLE
        rx = pos[zid][0] + rr * math.cos(th)
        rz = pos[zid][1] + rr * math.sin(th)
        lo, hi = kind_bounds[r["kind"]]
        rooms_out.append({
            "id": r["id"],
            "zone": zid,
            "kind": r["kind"],
            "landlord_id": r["landlord_id"],
            "start_rent": round(float(r["start"]), 2),
            "station_dist_m": r.get("station_dist_m", 600),
            "layout_xy": [round(rx, 3), round(rz, 3)],
            "kind_rent_range": [round(lo, 1), round(hi, 1)],
        })

    return zones_out, rooms_out


def build_metro_geojson() -> Dict[str, Any]:
    """Convert analysis/bj_routes_full.json into 2018 Beijing subway GeoJSON (lines + stations)."""
    routes = json.loads((ANALYSIS / "bj_routes_full.json").read_text(encoding="utf-8"))["elements"]
    nodes = {e["id"]: e for e in routes if e["type"] == "node"}
    later_lines = {"17", "19", "3", "11", "18"}
    segments = {
        "27": ("昌平西山口", "西二旗"),
        "8": ("朱辛庄", "南锣鼓巷"),
        "7": ("北京西站", "焦化厂"),
        "25N": ("郭公庄", "阎村东"),
        "16": ("北安河", "西苑"),
        "6": ("海淀五路居", "潞城"),
    }
    later_stops = {
        "14": set("东管头 丽泽商务区 菜户营 西铁营 景风门".split()),
        "1": set("花庄 环球度假区".split()),
        "1E": set("花庄 环球度假区".split()),
        "24;L2": {"亦庄火车站"},
    }
    features: List[Dict[str, Any]] = []
    seen_lines = set()
    seen_stations = set()

    for rel in (e for e in routes if e["type"] == "relation"):
        tags = rel.get("tags", {})
        name, ref = tags.get("name", ""), str(tags.get("ref") or tags.get("name", ""))
        if "机场" in name or "12号线" in name or ref in later_lines:
            continue
        seq = []
        for m in rel["members"]:
            if m["type"] == "node" and m.get("role", "").startswith("stop") and m["ref"] in nodes:
                n = nodes[m["ref"]]
                nm = n.get("tags", {}).get("name")
                if nm and (not seq or seq[-1][0] != nm):
                    seq.append((nm, n["lat"], n["lon"]))
        names = [s[0] for s in seq]
        if ref in segments and segments[ref][0] in names and segments[ref][1] in names:
            i, j = sorted((names.index(segments[ref][0]), names.index(segments[ref][1])))
            seq = seq[i : j + 1]
        removed = later_stops.get(ref, set())
        run: List[Tuple[str, float, float]] = []
        for s in seq + [None]:
            if s is None or s[0] in removed:
                if len(run) > 1:
                    key = (ref, frozenset(x[0] for x in run))
                    if key not in seen_lines:
                        seen_lines.add(key)
                        features.append({
                            "type": "Feature",
                            "properties": {"feature_kind": "line", "line": ref, "name": name},
                            "geometry": {
                                "type": "LineString",
                                "coordinates": [[round(x[2], 5), round(x[1], 5)] for x in run],
                            },
                        })
                        for st_name, slat, slon in run:
                            if st_name not in seen_stations:
                                seen_stations.add(st_name)
                                features.append({
                                    "type": "Feature",
                                    "properties": {"feature_kind": "station", "name": st_name, "line": ref},
                                    "geometry": {"type": "Point", "coordinates": [round(slon, 5), round(slat, 5)]},
                                })
                run = []
            else:
                run.append(s)
    return {"type": "FeatureCollection", "features": features}


def _catmull_rom(pts: List[Tuple[float, float]], samples_per_seg: int = 16) -> List[List[float]]:
    """Smooth Catmull-Rom spline through control points [(lon, lat), ...]."""
    ext = [pts[0]] + pts + [pts[-1]]
    out: List[List[float]] = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for j in range(samples_per_seg):
            t = j / samples_per_seg
            t2, t3 = t * t, t * t * t
            lon = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            lat = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append([round(lon, 5), round(lat, 5)])
    out.append([round(pts[-1][0], 5), round(pts[-1][1], 5)])
    return out


def build_newline_geojson(centroids: Dict[str, List[float]]) -> Dict[str, Any]:
    """Hypothetical East Express Line: CBD (Z00) -> Dingfuzhuang (Z01) -> Guoyuan (Z05) -> Wuyi Garden (Z11)."""
    stops = [
        ("Z00", "双井 CBD", "Shuangjing CBD"),
        ("Z01", "定福庄", "Dingfuzhuang"),
        ("Z05", "果园", "Guoyuan"),
        ("Z11", "武夷花园", "Wuyi Garden"),
    ]
    ctrl = [(centroids[zid][1], centroids[zid][0]) for zid, _, _ in stops]
    curve = _catmull_rom(ctrl, samples_per_seg=18)
    features: List[Dict[str, Any]] = [
        {
            "type": "Feature",
            "properties": {
                "feature_kind": "line",
                "name": "东向快线",
                "name_en": "East Express Line",
                "hypothetical": True,
                "announce_month": 13,
                "open_month": 25,
                "savings_min": {"Z05": 12, "Z11": 15},
            },
            "geometry": {"type": "LineString", "coordinates": curve},
        }
    ]
    for zid, zh, en in stops:
        lat, lon = centroids[zid]
        features.append({
            "type": "Feature",
            "properties": {
                "feature_kind": "station",
                "zone_id": zid,
                "name": zh,
                "name_en": en,
                "hypothetical": True,
                "treated": zid in TREATED_ZONES,
            },
            "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
        })
    return {"type": "FeatureCollection", "features": features}


def mentions_newline(text: str) -> bool:
    if not text:
        return False
    return any(kw in text for kw in MENTION_KEYWORDS)


def export_run(
    run_dir: Path,
    out_run_dir: Path,
    n_rooms: int = 240,
    months: int = 36,
) -> Dict[str, Any]:
    """Export one (scenario, seed) run into room_states.bin, events.json, decisions.json, monthly.json."""
    out_run_dir.mkdir(parents=True, exist_ok=True)

    # 1. monthly.json
    monthly_rows = []
    with (run_dir / "monthly.jsonl").open("r", encoding="utf-8") as fp:
        for line in fp:
            monthly_rows.append(json.loads(line))
    (out_run_dir / "monthly.json").write_text(
        json.dumps(monthly_rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    # 2. room_states.bin & events.json
    rs_path = run_dir / "room_states.jsonl"
    events_out: List[Dict[str, Any]] = []
    rooms_meta: Optional[List[Dict[str, Any]]] = None
    zone_monthly_stats: Dict[int, Dict[str, Dict[str, Any]]] = {}

    buf = bytearray(months * n_rooms * ROOM_RECORD_STRUCT.size)
    has_room_states = rs_path.exists()
    if has_room_states:
        with rs_path.open("r", encoding="utf-8") as fp:
            for line in fp:
                rec = json.loads(line)
                m = int(rec["month"])
                if not (1 <= m <= months):
                    continue
                if "rooms_meta" in rec and rooms_meta is None:
                    rooms_meta = rec["rooms_meta"]
                base_off = (m - 1) * n_rooms * ROOM_RECORD_STRUCT.size
                for rm in rec["rooms"]:
                    rid = int(rm["id"])
                    if not (0 <= rid < n_rooms):
                        continue
                    rent = float(rm["rent"])
                    occ = int(rm["occ"])
                    tid = int(rm["tid"])
                    vac = min(255, int(rm["vac"]))
                    grp_code = INCOME_GROUP_CODE.get(rm.get("grp", ""), 0) if occ else 0
                    comm = min(255, int(round(rm.get("comm", 0)))) if occ else 0
                    inc = float(rm.get("inc", 0.0)) if occ else 0.0
                    ROOM_RECORD_STRUCT.pack_into(
                        buf, base_off + rid * ROOM_RECORD_STRUCT.size,
                        rent, tid, occ, vac, grp_code, comm, inc,
                    )
                for ev in rec.get("events", []):
                    ev_copy = {"m": m}
                    ev_copy.update(ev)
                    events_out.append(ev_copy)
    (out_run_dir / "room_states.bin").write_bytes(bytes(buf))
    (out_run_dir / "events.json").write_text(
        json.dumps(events_out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    # 3. decisions.json + stratified non-cherry-picked monthly feed sample + full-denominator mention rates (§9.2)
    dec_path = run_dir / "decisions.jsonl"
    compact_decisions: List[Dict[str, Any]] = []
    # Full denominator per month for landlord pricing decisions (price_vacant + renewal_offer)
    ll_pricing_by_m: Dict[int, List[int]] = {m: [] for m in range(1, months + 1)}
    mention_stats: Dict[str, Dict[str, Any]] = {}

    if dec_path.exists():
        with dec_path.open("r", encoding="utf-8") as fp:
            for line in fp:
                rec = json.loads(line)
                m = int(rec["month"])
                atype = rec["agent_type"]
                dec = rec["decision"]
                inp = rec.get("inputs", {})
                out = rec.get("output", {})
                reason = rec.get("reason", "") or out.get("reason", "")
                m_line = mentions_newline(reason)

                if atype == "landlord":
                    rid = inp.get("room_id")
                    zid = inp.get("zone")
                    rent_before = inp.get("current_rent")
                    rent_after = out.get("rent", rent_before)
                    ll_info = inp.get("landlord", {})
                    # Keep compact full input card for Room Card collapsible inspector (§6.2)
                    compact_inp = {
                        "zone": zid,
                        "kind": inp.get("kind"),
                        "amenity_score": inp.get("amenity_score"),
                        "current_rent": rent_before,
                        "floor_rent": inp.get("floor_rent"),
                        "up_front": inp.get("up_front"),
                        "vacant_for": inp.get("vacant_for"),
                        "zone_vacancy_smooth": inp.get("zone_vacancy_smooth"),
                        "nearby_avg_rent": inp.get("nearby_avg_rent"),
                        "recent_apps_per_vacant": inp.get("recent_apps_per_vacant"),
                        "tenant_tenure_months": inp.get("tenant_tenure_months"),
                        "tenant_good_standing": inp.get("tenant_good_standing"),
                        "initial_offer": inp.get("initial_offer"),
                        "counter_rent": inp.get("counter_rent"),
                        "announcement": inp.get("announcement"),
                    }
                    compact_inp = {k: v for k, v in compact_inp.items() if v is not None}
                    idx = len(compact_decisions)
                    compact_decisions.append({
                        "m": m,
                        "agent_type": "landlord",
                        "agent_id": rec["agent_id"],
                        "decision": dec,
                        "room_id": rid,
                        "zone": zid,
                        "kind": inp.get("kind"),
                        "ll_kind": ll_info.get("kind"),
                        "ll_risk": ll_info.get("risk"),
                        "vacant_for": inp.get("vacant_for", 0),
                        "rent_before": round(float(rent_before), 1) if rent_before is not None else None,
                        "rent_after": round(float(rent_after), 1) if rent_after is not None else None,
                        "reason": reason,
                        "mentions_line": m_line,
                        "prompt_hash": rec.get("prompt_hash", ""),
                        "fallback": bool(rec.get("fallback", False)),
                        "inputs": compact_inp,
                    })
                    if dec in ("price_vacant", "renewal_offer") and 1 <= m <= months:
                        ll_pricing_by_m[m].append(idx)
                else:
                    # Tenant decision (search / at_expiry) — keep compact card for Tenant Card (§6.2)
                    cur_room = inp.get("current_room") or {}
                    cands = inp.get("candidates") or []
                    t_prof = inp.get("tenant") or {}
                    compact_decisions.append({
                        "m": m,
                        "agent_type": "tenant",
                        "agent_id": rec["agent_id"],
                        "decision": dec,
                        "room_id": cur_room.get("room_id"),
                        "zone": cur_room.get("zone"),
                        "action": out.get("action") or ("apply" if out.get("apply") else "skip"),
                        "apply": out.get("apply", []),
                        "counter_rent": out.get("rent") if out.get("action") == "counter" else None,
                        "tenant_group": t_prof.get("income_group") or t_prof.get("group"),
                        "tenant_income": t_prof.get("income"),
                        "candidates": [
                            {
                                "room_id": c.get("room_id"),
                                "zone": c.get("zone"),
                                "kind": c.get("kind"),
                                "rent": c.get("rent"),
                                "min": (c.get("modes")[0].get("min") if c.get("modes") else None),
                            }
                            for c in cands[:5]
                        ],
                        "reason": reason,
                        "mentions_line": m_line,
                        "prompt_hash": rec.get("prompt_hash", ""),
                        "fallback": bool(rec.get("fallback", False)),
                    })

    # Compute exact mention rates over ALL landlord pricing decisions + deterministic stratified feed sample (§9.2)
    sample_rng = random.Random(FEED_SAMPLE_SEED)
    feed_sample_by_m: Dict[str, List[int]] = {}
    for m in range(1, months + 1):
        idxs = ll_pricing_by_m[m]
        tr_idxs = [i for i in idxs if compact_decisions[i]["zone"] in TREATED_ZONES]
        ot_idxs = [i for i in idxs if compact_decisions[i]["zone"] not in TREATED_ZONES]
        all_mentions = sum(1 for i in idxs if compact_decisions[i]["mentions_line"])
        tr_mentions = sum(1 for i in tr_idxs if compact_decisions[i]["mentions_line"])
        mention_stats[str(m)] = {
            "total": len(idxs),
            "mentions": all_mentions,
            "rate": round(all_mentions / len(idxs), 4) if idxs else 0.0,
            "treated_total": len(tr_idxs),
            "treated_mentions": tr_mentions,
            "treated_rate": round(tr_mentions / len(tr_idxs), 4) if tr_idxs else 0.0,
        }
        # Stratified random draw (never cherry-picked): up to 6 treated + 4 other
        tr_copy, ot_copy = list(tr_idxs), list(ot_idxs)
        sample_rng.shuffle(tr_copy)
        sample_rng.shuffle(ot_copy)
        picked = tr_copy[:6] + ot_copy[:4]
        feed_sample_by_m[str(m)] = picked

    dec_payload = {
        "decisions": compact_decisions,
        "mention_stats": mention_stats,
        "feed_sample_by_month": feed_sample_by_m,
        "llm_calls_by_month": {
            str(m): sum(1 for d in compact_decisions if d["m"] == m)
            for m in range(1, months + 1)
        },
    }
    (out_run_dir / "decisions.json").write_text(
        json.dumps(dec_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    return {
        "has_room_states": has_room_states,
        "rooms_meta": rooms_meta,
        "n_decisions": len(compact_decisions),
        "n_events": len(events_out),
    }


def compute_monthly_ci(
    runs_dir: Path,
    group: str,
    seeds: List[int],
    months: int = 36,
) -> Dict[str, Any]:
    """Compute cross-seed means & 95% CIs for all key series plus paired P-S, P-N, S-N gaps."""
    mon = {(sc, s): _load_monthly(runs_dir / f"{group}_{sc}_{s}") for sc in "NSP" for s in seeds}
    metrics = [
        "rent_index_treated", "rent_index_all", "rent_index_other",
        "vacancy_treated", "vacancy_all", "vacancy_other",
        "commute_treated", "commute_all", "commute_other",
        "treated_move_ins", "treated_low_share", "burden_all", "over60",
    ]
    by_scen: Dict[str, Dict[str, List[List[float]]]] = {}
    for sc in "NSP":
        by_scen[sc] = {}
        for k in metrics:
            series = []
            for m in range(1, months + 1):
                vals = [float(mon[(sc, s)][m][k]) for s in seeds if m in mon[(sc, s)]]
                mean, half = ci95(vals)
                series.append([round(mean, 4), round(half, 4)])
            by_scen[sc][k] = series

    paired_diffs: Dict[str, Dict[str, List[List[float]]]] = {}
    for name, a, b in (("P_minus_S", "P", "S"), ("P_minus_N", "P", "N"), ("S_minus_N", "S", "N")):
        paired_diffs[name] = {}
        for k in ("rent_index_treated", "vacancy_treated", "commute_treated", "treated_move_ins"):
            series = []
            for m in range(1, months + 1):
                vals = [float(mon[(a, s)][m][k]) - float(mon[(b, s)][m][k]) for s in seeds if m in mon[(a, s)] and m in mon[(b, s)]]
                mean, half = ci95(vals)
                series.append([round(mean, 4), round(half, 4)])
            paired_diffs[name][k] = series

    # Median seed rule (§9.3): seed whose M24 (P - S) treated rent index is closest to median
    m24_ps = [(s, float(mon[("P", s)][24]["rent_index_treated"]) - float(mon[("S", s)][24]["rent_index_treated"])) for s in seeds]
    med_val = st.median([v for _, v in m24_ps])
    median_seed = min(m24_ps, key=lambda item: (abs(item[1] - med_val), item[0]))[0]

    return {
        "seeds": seeds,
        "months": months,
        "median_seed": median_seed,
        "median_seed_m24_ps": round(dict(m24_ps)[median_seed], 3),
        "m24_ps_by_seed": {str(s): round(v, 3) for s, v in m24_ps},
        "scenarios": by_scen,
        "paired_diffs": paired_diffs,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Export Lease Day v0.7 runs into viz_data/ bundle")
    ap.add_argument("--runs", required=True, help="Directory with {GROUP}_{SCEN}_{SEED} folders")
    ap.add_argument("--group", choices=["R", "L", "M"], default="L")
    ap.add_argument("--baseline-runs", type=str, default=None, help="Rule baseline dir (runs_r) for H3/B verdicts")
    ap.add_argument("--osm-dir", type=str, default=str(ANALYSIS / "osm"), help="Directory with basemap.geojson & buildings.geojson")
    ap.add_argument("--out", required=True, help="Output viz_data directory")
    ap.add_argument("--illustrative", action="store_true", help="Mark bundle with is_illustrative=true watermark (§9.1)")
    ap.add_argument("--source-label", type=str, default="", help="Human-readable data source label for footer/watermark")
    ap.add_argument("--seeds-limit", type=int, default=None, help="Optional cap on exported per-run seeds (aggregate still uses all)")
    args = ap.parse_args()

    runs_dir = Path(args.runs)
    out_dir = Path(args.out)
    geo_dir = out_dir / "geo"
    agg_dir = out_dir / "aggregate"
    out_runs_dir = out_dir / "runs"
    for d in (out_dir, geo_dir, agg_dir, out_runs_dir):
        d.mkdir(parents=True, exist_ok=True)

    seeds = _paired_seeds(runs_dir, args.group)
    if not seeds:
        raise FileNotFoundError(f"No complete paired (N, S, P) seeds found for group={args.group} in {runs_dir}")

    print(f"[export_viz] Found {len(seeds)} paired seeds for group {args.group}: {seeds}")

    # 1. Aggregate CIs & median seed (§9.3)
    monthly_ci = compute_monthly_ci(runs_dir, args.group, seeds)
    (agg_dir / "monthly_ci.json").write_text(
        json.dumps(monthly_ci, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    median_seed = monthly_ci["median_seed"]
    print(f"[export_viz] Median seed = {median_seed} (M24 P-S = {monthly_ci['median_seed_m24_ps']:+.3f})")

    # 2. Pre-registered verdicts (§9.7)
    verdicts = None
    try:
        baseline_path = Path(args.baseline_runs) if args.baseline_runs else None
        verdicts = evaluate_preregistered(runs_dir, args.group, baseline_runs=baseline_path)
    except Exception as exc:
        print(f"[warn] evaluate_preregistered failed ({exc}); writing placeholder verdict record")
        verdicts = {"group": args.group, "seeds": seeds, "error": str(exc), "results": {}}
    (agg_dir / "verdicts.json").write_text(
        json.dumps(verdicts, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 3. Export individual runs (ensure median_seed is always included)
    export_seeds = list(seeds)
    if args.seeds_limit is not None and len(export_seeds) > args.seeds_limit:
        export_seeds = [median_seed] + [s for s in seeds if s != median_seed][: max(0, args.seeds_limit - 1)]
        export_seeds.sort()

    rooms_meta = None
    landlords_meta = None
    has_any_room_states = False
    for s in export_seeds:
        for sc in ("N", "S", "P"):
            rdir = runs_dir / f"{args.group}_{sc}_{s}"
            info = export_run(rdir, out_runs_dir / f"{sc}_{s}")
            if info["rooms_meta"] and rooms_meta is None:
                rooms_meta = info["rooms_meta"]
            if info["has_room_states"]:
                has_any_room_states = True
            if landlords_meta is None:
                summ = json.loads((rdir / "summary.json").read_text(encoding="utf-8"))
                landlords_meta = summ.get("landlords_meta", [])
            print(f"  exported {sc}_{s}: room_states={info['has_room_states']}, decisions={info['n_decisions']}, events={info['n_events']}")

    # Fallback rooms_meta from deterministic allocate_v07 if room_states.jsonl was absent
    if rooms_meta is None:
        alloc = allocate_v07(240)
        rooms_meta = []
        rid = 0
        for (zid, kind), n in alloc.items():
            base = ZONE_BY_ID[zid]["rents"][kind]
            for _ in range(n):
                rooms_meta.append({"id": rid, "zone": zid, "kind": kind, "landlord_id": -1, "start": base, "station_dist_m": 600})
                rid += 1

    # 4. Geo files: zones, metro, newline, basemap, buildings
    centroids = json.loads((ANALYSIS / "zone_centroids.json").read_text(encoding="utf-8"))
    zones_out, rooms_out = compute_zone_and_room_layout(centroids, rooms_meta)
    (geo_dir / "zones.json").write_text(json.dumps(zones_out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out_dir / "rooms.json").write_text(json.dumps(rooms_out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out_dir / "landlords.json").write_text(json.dumps(landlords_meta or [], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    metro_gj = build_metro_geojson()
    (geo_dir / "metro.geojson").write_text(json.dumps(metro_gj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    newline_gj = build_newline_geojson(centroids)
    (geo_dir / "newline.geojson").write_text(json.dumps(newline_gj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    osm_dir = Path(args.osm_dir)
    for fname in ("basemap.geojson", "buildings.geojson"):
        src = osm_dir / fname
        dst = geo_dir / fname
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  copied {fname} ({dst.stat().st_size / 1024:.1f} KB)")
        else:
            print(f"  [warn] {src} not found; writing empty FeatureCollection placeholder")
            dst.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

    # 5. meta.json
    import datetime
    meta = {
        "version": "0.7",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "group": args.group,
        "scenarios": ["N", "S", "P"],
        "seeds": export_seeds,
        "all_aggregate_seeds": seeds,
        "default_seed": median_seed,
        "default_seed_rule": "median_m24_p_minus_s",
        "months": 36,
        "n_rooms": len(rooms_out),
        "n_landlords": len(landlords_meta or []),
        "event_months": {"announce": 13, "open": 25},
        "treated_zones": list(TREATED_ZONES),
        "source_label": args.source_label or f"{runs_dir.name} ({args.group}, {len(seeds)} seeds)",
        "is_illustrative": bool(args.illustrative or not has_any_room_states),
        "has_room_states": has_any_room_states,
        "mention_keywords": MENTION_KEYWORDS,
        "feed_sample_seed": FEED_SAMPLE_SEED,
        "projection": {
            "type": "local_web_mercator_km",
            "origin_zone": "Z00",
            "origin_lat": ORIGIN_LAT,
            "origin_lon": ORIGIN_LON,
            "cos_lat0": COS_LAT0,
            "meters_per_unit": METERS_PER_UNIT,
        },
        "room_states_schema": {
            "bytes_per_record": ROOM_RECORD_STRUCT.size,
            "endian": "little",
            "fields": [
                {"name": "rent", "type": "float32", "offset": 0},
                {"name": "tenant_id", "type": "int32", "offset": 4},
                {"name": "occupied", "type": "uint8", "offset": 8},
                {"name": "vacant_for", "type": "uint8", "offset": 9},
                {"name": "group_code", "type": "uint8", "offset": 10},
                {"name": "commute_min", "type": "uint8", "offset": 11},
                {"name": "income", "type": "float32", "offset": 12},
            ],
        },
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Report total bundle size
    total_bytes = sum(p.stat().st_size for p in out_dir.rglob("*") if p.is_file())
    print(f"[export_viz] Done! Total viz_data size: {total_bytes / (1024 * 1024):.2f} MB -> {out_dir}")


if __name__ == "__main__":
    main()
