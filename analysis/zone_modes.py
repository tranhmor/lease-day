"""Open-data travel inputs for the CBD board: OSM road distances (FOSSGIS routing) and OSM bus routes through the CBD.

Bus lines are found from each zone's three busiest stations and are today's OSM routes, direct only.
Free-flow times from the router are kept as raw inputs. Peak speed, waiting and fares are applied in `build_board.py`.
Road data: OpenStreetMap contributors, ODbL. Routing service: routing.openstreetmap.de (light use, one request per second).
"""
import json
import math
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CBD = (39.912, 116.456)
AGENT = {"User-Agent": "UGOD5066-course-project"}
SERVERS = ["https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass-api.de/api/interpreter"]
CENTROIDS = json.load(open(os.path.join(HERE, "zone_centroids.json"), encoding="utf-8"))


def km(a, b):
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 85.3)


def route(profile, a, b):
    url = f"https://routing.openstreetmap.de/routed-{profile}/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}?overview=false"
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=40) as r:
        leg = json.load(r)["routes"][0]
    return round(leg["distance"] / 1000, 1), round(leg["duration"] / 60, 1)


def overpass(query):
    body = urllib.parse.urlencode({"data": f"[out:json][timeout:120];{query}"}).encode()
    last = None
    for server in SERVERS:
        for _ in range(2):
            try:
                with urllib.request.urlopen(urllib.request.Request(server, body, AGENT), timeout=150) as r:
                    return json.load(r)
            except Exception as e:
                last = e
                time.sleep(5)
    raise last


def bus_routes():
    data = overpass('node(around:1500,39.908,116.458)["highway"="bus_stop"];rel(bn)["route"="bus"];out body;>;out skel qt;')
    nodes = {e["id"]: (e["lat"], e["lon"]) for e in data["elements"] if e["type"] == "node"}
    out = []
    for r in (e for e in data["elements"] if e["type"] == "relation"):
        stops = [nodes[m["ref"]] for m in r["members"] if m["type"] == "node" and m.get("role", "").startswith(("stop", "platform")) and m["ref"] in nodes]
        if len(stops) >= 2:
            out.append({"ref": r.get("tags", {}).get("ref", ""), "stops": stops})
    return out


def direct_buses(points, routes, reach=1.0):
    """Lines that pass within reach of a sample point and carry on to the CBD; length runs to the stop nearest the centre."""
    lengths = []
    lines = set()
    for r in routes:
        stops = r["stops"]
        end = min(range(len(stops)), key=lambda i: km(stops[i], CBD))
        if km(stops[end], CBD) > 1.5:
            continue
        starts = [i for i, s in enumerate(stops[:end]) if any(km(s, p) <= reach for p in points)]
        if starts:
            lines.add(r["ref"])
            lengths.append(sum(km(stops[k], stops[k + 1]) for k in range(starts[-1], end)))
    return len(lines), min(lengths) if lengths else None


if __name__ == "__main__":
    path = os.path.join(HERE, "zone_modes.json")
    out = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    names = sorted(json.load(open(os.path.join(HERE, "center_access.json"), encoding="utf-8"))["CBD"]["t18"])
    pos = json.load(open(os.path.join(HERE, "center_access.json"), encoding="utf-8"))["pos"]
    samples = {z["id"]: [tuple(pos[names[i]]) for i in z["st"]] for z in json.load(open(os.path.join(HERE, "zone_listings.json"), encoding="utf-8"))["zones"]}
    routes = bus_routes()
    print("bus relations through the CBD with usable stops:", len(routes))
    for z, c in CENTROIDS.items():
        c = tuple(c)
        row = out.get(z) or {"straight_km": round(km(c, CBD), 1)}
        if "car_km" not in row:
            for profile, key in [("car", "car"), ("bike", "bike"), ("foot", "foot")]:
                row[key + "_km"], row[key + "_free_min"] = route(profile, c, CBD)
                time.sleep(1)
        n, length = direct_buses(samples[z], routes)
        row["direct_bus_lines"] = n
        row["bus_km"] = round(length, 1) if length else None
        row.pop("bus_walk_km", None)
        out[z] = row
        print(z, n, row["bus_km"], flush=True)
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
