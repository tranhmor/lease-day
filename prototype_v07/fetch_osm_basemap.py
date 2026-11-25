"""Fetch and simplify offline Beijing OSM basemap (L1) and low-poly buildings (L2) for Lease Day v0.7 3D viz.

Saves compact, self-contained GeoJSON files to rental_game/analysis/osm/:
  - basemap.geojson    (ring roads, arterials, major waterways/lakes, district boundaries)
  - buildings.geojson  (low-poly footprints + heights around CBD/Z00, Z01, Z05, Z11)

Pure Python stdlib (no external deps). Run once online; all runtime & export_viz.py steps stay 100% offline.
"""
import argparse
import json
import math
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Tuple

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent / "analysis" / "osm"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Beijing study bbox covering Z00..Z23 (lat_min, lon_min, lat_max, lon_max)
BBOX = (39.71, 116.12, 40.22, 116.74)

# Focused building clusters (3-4 zones per §5.1 to keep triangle count light)
BUILDING_CLUSTERS = [
    ("cbd", "CBD / 双井 (Z00)", (39.898, 116.440, 39.923, 116.476), 420),
    ("dingfuzhuang", "定福庄 (Z01)", (39.900, 116.524, 39.916, 116.548), 110),
    ("guoyuan", "果园 (Z05)", (39.884, 116.628, 39.908, 116.656), 200),
    ("wuyi", "武夷花园 (Z11)", (39.887, 116.658, 39.907, 116.684), 160),
]


def query_overpass(ql: str, timeout: int = 90) -> Dict[str, Any]:
    body = urllib.parse.urlencode({"data": ql}).encode("utf-8")
    last_err = None
    for url in OVERPASS_ENDPOINTS:
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={"User-Agent": "LeaseDay-v07-VizBuilder/1.0 (academic research)"},
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as exc:
                last_err = exc
                print(f"  [warn] {url} attempt {attempt + 1} failed: {exc}")
                time.sleep(2)
    raise RuntimeError(f"All Overpass endpoints failed: {last_err}")


def _perp_dist(pt: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0.0 and dy == 0.0:
        return math.hypot(pt[0] - a[0], pt[1] - a[1])
    t = max(0.0, min(1.0, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(pt[0] - (a[0] + t * dx), pt[1] - (a[1] + t * dy))


def simplify_rdp(pts: List[Tuple[float, float]], eps: float) -> List[Tuple[float, float]]:
    if len(pts) <= 2:
        return pts
    max_d, idx = 0.0, 0
    a, b = pts[0], pts[-1]
    for i in range(1, len(pts) - 1):
        d = _perp_dist(pts[i], a, b)
        if d > max_d:
            max_d, idx = d, i
    if max_d > eps:
        left = simplify_rdp(pts[: idx + 1], eps)
        right = simplify_rdp(pts[idx:], eps)
        return left[:-1] + right
    return [a, b]


def round_coords(pts: List[Tuple[float, float]], ndigits: int = 4) -> List[List[float]]:
    return [[round(lon, ndigits), round(lat, ndigits)] for lon, lat in pts]


def poly_area_approx(ring: List[Tuple[float, float]]) -> float:
    # Area in rough square meters at Beijing latitude (~40N)
    if len(ring) < 4:
        return 0.0
    s = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0] * 85300.0, ring[i][1] * 111200.0
        x2, y2 = ring[i + 1][0] * 85300.0, ring[i + 1][1] * 111200.0
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5


def parse_height(tags: Dict[str, str], area_m2: float, cluster_id: str) -> float:
    h_raw = tags.get("height") or tags.get("building:height")
    if h_raw:
        clean = "".join(ch for ch in h_raw if ch.isdigit() or ch == ".")
        try:
            v = float(clean)
            if 4.0 <= v <= 550.0:
                return round(v, 1)
        except ValueError:
            pass
    lvl_raw = tags.get("building:levels")
    if lvl_raw:
        clean = "".join(ch for ch in lvl_raw if ch.isdigit() or ch == ".")
        try:
            lv = float(clean)
            if 1.0 <= lv <= 120.0:
                return round(lv * 3.6, 1)
        except ValueError:
            pass
    # Fallback height from footprint & cluster character (CBD towers taller than suburban blocks)
    if cluster_id == "cbd":
        return round(min(220.0, max(24.0, math.sqrt(area_m2) * 1.15)), 1)
    return round(min(72.0, max(15.0, math.sqrt(area_m2) * 0.65)), 1)


def fetch_basemap() -> Dict[str, Any]:
    s, w, n, e = BBOX
    bbox_str = f"{s},{w},{n},{e}"
    features: List[Dict[str, Any]] = []

    # 1. Major roads: motorways, ring roads, trunks, primary arterials
    print("[1/4] Fetching Beijing ring roads & major arterials from OSM...")
    ql_roads = f"""
    [out:json][timeout:60];
    (
      way["highway"~"^(motorway|trunk|primary)$"]({bbox_str});
    );
    out geom qt;
    """
    data_roads = query_overpass(ql_roads)
    road_kept = 0
    for el in data_roads.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        tags = el.get("tags", {})
        hw = tags.get("highway", "primary")
        name = tags.get("name", "")
        pts = [(g["lon"], g["lat"]) for g in el["geometry"]]
        # Aggressive simplification: ~120m tolerance for primary, ~70m for motorway/trunk
        eps = 0.0007 if hw in ("motorway", "trunk") else 0.0011
        pts = simplify_rdp(pts, eps)
        if len(pts) < 2:
            continue
        # Drop tiny ramps / micro-links
        length = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
        if length < (0.0018 if hw == "primary" else 0.0012):
            continue
        is_ring = any(k in name for k in ("二环", "三环", "四环", "五环", "六环", "Ring"))
        features.append({
            "type": "Feature",
            "properties": {
                "layer": "ring_road" if (is_ring or hw == "motorway") else ("trunk" if hw == "trunk" else "arterial"),
                "highway": hw,
                "name": name,
            },
            "geometry": {"type": "LineString", "coordinates": round_coords(pts, 4)},
        })
        road_kept += 1
    print(f"  -> kept {road_kept} road segments")

    # 2. Waterways & major lakes
    print("[2/4] Fetching Beijing rivers, canals & major lakes from OSM...")
    ql_water = f"""
    [out:json][timeout:60];
    (
      way["waterway"~"^(river|canal)$"]({bbox_str});
      way["natural"="water"]["water"~"^(lake|reservoir|river)$"]({bbox_str});
      way["natural"="water"]["name"]({bbox_str});
    );
    out geom qt;
    """
    data_water = query_overpass(ql_water)
    water_lines, water_polys = 0, 0
    for el in data_water.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        tags = el.get("tags", {})
        pts = [(g["lon"], g["lat"]) for g in el["geometry"]]
        if len(pts) < 2:
            continue
        if tags.get("natural") == "water" and len(pts) >= 4 and pts[0] == pts[-1]:
            area = poly_area_approx(pts)
            if area < 45000.0:  # >= 4.5 ha lakes/reservoirs only
                continue
            sp = simplify_rdp(pts[:-1], 0.0005)
            if len(sp) < 3:
                continue
            sp.append(sp[0])
            features.append({
                "type": "Feature",
                "properties": {"layer": "water_poly", "name": tags.get("name", "")},
                "geometry": {"type": "Polygon", "coordinates": [round_coords(sp, 4)]},
            })
            water_polys += 1
        elif "waterway" in tags:
            sp = simplify_rdp(pts, 0.0008)
            length = sum(math.hypot(sp[i + 1][0] - sp[i][0], sp[i + 1][1] - sp[i][1]) for i in range(len(sp) - 1))
            if len(sp) < 2 or length < 0.003:
                continue
            features.append({
                "type": "Feature",
                "properties": {"layer": "waterway", "name": tags.get("name", "")},
                "geometry": {"type": "LineString", "coordinates": round_coords(sp, 4)},
            })
            water_lines += 1
    print(f"  -> kept {water_lines} waterways, {water_polys} water polygons")

    # 3. District boundaries (admin_level=6 in Beijing)
    print("[3/4] Fetching Beijing district boundaries (admin_level=6) from OSM...")
    ql_dist = f"""
    [out:json][timeout:60];
    (
      way["boundary"="administrative"]["admin_level"="6"]({bbox_str});
    );
    out geom qt;
    """
    data_dist = query_overpass(ql_dist)
    dist_kept = 0
    for el in data_dist.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        pts = [(g["lon"], g["lat"]) for g in el["geometry"]]
        sp = simplify_rdp(pts, 0.0014)
        if len(sp) < 2:
            continue
        features.append({
            "type": "Feature",
            "properties": {"layer": "district", "name": el.get("tags", {}).get("name", "")},
            "geometry": {"type": "LineString", "coordinates": round_coords(sp, 4)},
        })
        dist_kept += 1
    print(f"  -> kept {dist_kept} district boundary segments")

    return {"type": "FeatureCollection", "features": features}


def fetch_buildings() -> Dict[str, Any]:
    print("[4/4] Fetching low-poly building footprints around CBD & treated zones...")
    features: List[Dict[str, Any]] = []
    for cid, label, (s, w, n, e), max_count in BUILDING_CLUSTERS:
        ql = f"""
        [out:json][timeout:60];
        (
          way["building"]({s},{w},{n},{e});
        );
        out geom qt;
        """
        data = query_overpass(ql)
        candidates: List[Tuple[float, Dict[str, Any]]] = []
        for el in data.get("elements", []):
            if el.get("type") != "way" or "geometry" not in el:
                continue
            pts = [(g["lon"], g["lat"]) for g in el["geometry"]]
            if len(pts) < 4 or pts[0] != pts[-1]:
                continue
            area = poly_area_approx(pts)
            if area < 280.0:  # ignore tiny sheds/kiosks
                continue
            sp = simplify_rdp(pts[:-1], 0.00008)
            if len(sp) < 3 or len(sp) > 24:
                # Fallback to bounding rectangle if overly complex
                lons = [p[0] for p in pts]
                lats = [p[1] for p in pts]
                sp = [(min(lons), min(lats)), (max(lons), min(lats)), (max(lons), max(lats)), (min(lons), max(lats))]
            sp.append(sp[0])
            tags = el.get("tags", {})
            h = parse_height(tags, area, cid)
            score = h * math.sqrt(area)
            candidates.append((
                score,
                {
                    "type": "Feature",
                    "properties": {
                        "cluster": cid,
                        "height": h,
                        "area_m2": round(area, 0),
                        "name": tags.get("name", ""),
                    },
                    "geometry": {"type": "Polygon", "coordinates": [round_coords(sp, 5)]},
                },
            ))
        candidates.sort(key=lambda x: x[0], reverse=True)
        picked = [f for _, f in candidates[:max_count]]
        features.extend(picked)
        print(f"  -> {label}: {len(picked)} buildings (from {len(candidates)} footprints)")
        time.sleep(1.0)
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch offline Beijing OSM GeoJSON for Lease Day v0.7 3D viz")
    ap.add_argument("--out", type=str, default=str(OUT_DIR))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    basemap = fetch_basemap()
    bm_path = out / "basemap.geojson"
    bm_path.write_text(json.dumps(basemap, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {bm_path} ({bm_path.stat().st_size / 1024:.1f} KB, {len(basemap['features'])} features)")

    buildings = fetch_buildings()
    bld_path = out / "buildings.geojson"
    bld_path.write_text(json.dumps(buildings, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {bld_path} ({bld_path.stat().st_size / 1024:.1f} KB, {len(buildings['features'])} features)")


if __name__ == "__main__":
    main()
