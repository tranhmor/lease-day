"""Turn viz_v06_data.json and viz_v06_replay.json into the row files behind the results page, in analysis/viz_dash/.

Also lays out the map: real zone centroids and subway lines, with room dots packed around each centroid and clusters
pushed apart until they stop overlapping. Inner zones move about 2 to 4 km outward as a result.
"""
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "viz_dash")
os.makedirs(OUT, exist_ok=True)
load = lambda name: json.load(open(os.path.join(HERE, name), encoding="utf-8"))
D = load("viz_v06_data.json")
R = load("viz_v06_replay.json")
BOARD = load("board_cbd_v01.json")
CENTROIDS = load("zone_centroids.json")
ROUTES = load("bj_routes_full.json")["elements"]
ARMS = ("A", "A0", "B", "C")
LISTINGS = {z["id"]: z for z in load("zone_listings.json")["zones"]}

NAMES = dict(Z00="双井", Z01="定福庄", Z02="望京", Z03="方庄", Z04="金融街", Z05="果园", Z06="北苑", Z07="德胜门", Z08="广安门", Z09="马家堡", Z10="亦庄", Z11="武夷花园",
             Z12="天通苑", Z13="回龙观", Z14="鲁谷", Z15="看丹桥", Z16="后沙峪", Z17="西三旗", Z18="苹果园", Z19="黄村", Z20="马驹桥", Z21="顺义城", Z22="良乡", Z23="昌平")
MAJOR = {"Z00", "Z02", "Z03", "Z04", "Z05", "Z07", "Z10", "Z11", "Z12", "Z13", "Z21", "Z22"}
WATCH = set(D["watch"])
ZONE_IDS = D["zone_ids"]


def save(name, rows):
    path = os.path.join(OUT, name + ".json")
    json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"{name:16} {len(rows):6} rows {os.path.getsize(path) / 1024:8.1f} KB")


def tail(values, n=D["tail"]):
    return sum(values[-n:]) / n


# ----- map layout: virtual canvas 1000 units wide -----
LAT0, LON0 = 40.235, 116.11
KM = 1000 / 57.0
project = lambda lat, lon: ((lon - LON0) * 85.3 * KM, (LAT0 - lat) * 111.2 * KM)
SPACING = 11.0
GOLDEN = math.pi * (3 - math.sqrt(5))
rooms_meta = R["arms"]["A"]["rooms"]
count = [0] * len(ZONE_IDS)
for zone, _, _ in rooms_meta:
    count[zone] += 1
CLEAR_CENTRE = {"Z00": 10}  # leaves the CBD marker uncovered
radius = {}
for i, z in enumerate(ZONE_IDS):
    skip = CLEAR_CENTRE.get(z, 0)
    radius[z] = 0.62 * SPACING * math.sqrt(count[i] + skip + 0.5) + 6
pos = {z: list(project(*CENTROIDS[z])) for z in ZONE_IDS}
true_pos = {z: tuple(pos[z]) for z in ZONE_IDS}
cbd = project(*BOARD["work"]["centre"])
pos["Z00"] = list(cbd)
for _ in range(600):
    moved = False
    for a in ZONE_IDS:
        for b in ZONE_IDS:
            if a >= b:
                continue
            dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
            dist = math.hypot(dx, dy) or 1e-6
            need = radius[a] + radius[b] + 8
            if dist < need:
                moved = True
                push = (need - dist) / dist / 2
                if a == "Z00":
                    pos[b][0] += dx * push * 2
                    pos[b][1] += dy * push * 2
                else:
                    pos[a][0] -= dx * push
                    pos[a][1] -= dy * push
                    pos[b][0] += dx * push
                    pos[b][1] += dy * push
    if not moved:
        break
shift = {z: math.hypot(pos[z][0] - true_pos[z][0], pos[z][1] - true_pos[z][1]) / KM for z in ZONE_IDS}
print("largest cluster shift km", round(max(shift.values()), 1), "still overlapping", moved)
HEIGHT = max(pos[z][1] + radius[z] for z in ZONE_IDS) + 44


def label_box(z, x, y, width_per_char=17.0, height=20.0):
    w = width_per_char * len(NAMES[z]) + 6
    return x - w / 2, y - height / 2, x + w / 2, y + height / 2


def hits_circle(box, zone):
    cx, cy, r = pos[zone][0], pos[zone][1], radius[zone]
    nx, ny = min(max(cx, box[0]), box[2]), min(max(cy, box[1]), box[3])
    return math.hypot(nx - cx, ny - cy) < r


def hits_box(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


labels, placed = {}, []
for z in sorted(ZONE_IDS, key=lambda v: -radius[v]):
    best, best_cost = None, 1e18
    base = math.atan2(pos[z][1] - cbd[1], pos[z][0] - cbd[0]) if z != "Z00" else -math.pi / 2
    for step in range(24):
        for gap in (15, 24, 36):
            angle = base + (step // 2 + step % 2) * (1 if step % 2 else -1) * math.pi / 12
            x = pos[z][0] + (radius[z] + gap) * math.cos(angle)
            y = pos[z][1] + (radius[z] + gap) * math.sin(angle)
            box = label_box(z, x, y)
            cost = step + gap / 12
            if box[0] < 4 or box[2] > 996 or box[1] < 4 or box[3] > HEIGHT - 4:
                cost += 1000
            cost += 400 * sum(hits_circle(box, o) for o in ZONE_IDS) + 400 * sum(hits_box(box, p) for p in placed)
            if cost < best_cost:
                best, best_cost = (round(x), round(y), box), cost
    labels[z] = best[:2]
    placed.append(best[2])
    if best_cost >= 400:
        print("label conflict", z, best_cost)

# ----- subway lines, 2018 network: same filters as job_center_network.py -----
nodes = {e["id"]: e for e in ROUTES if e["type"] == "node"}
LATER_LINES = {"17", "19", "3", "11", "18"}
SEGMENTS = {"27": ("昌平西山口", "西二旗"), "8": ("朱辛庄", "南锣鼓巷"), "7": ("北京西站", "焦化厂"), "25N": ("郭公庄", "阎村东"), "16": ("北安河", "西苑"), "6": ("海淀五路居", "潞城")}
LATER_STOPS = {"14": set("东管头 丽泽商务区 菜户营 西铁营 景风门".split()), "1": set("花庄 环球度假区".split()), "1E": set("花庄 环球度假区".split()), "24;L2": {"亦庄火车站"}}
lines, seen = [], set()
for r in (e for e in ROUTES if e["type"] == "relation"):
    t = r.get("tags", {})
    name, ref = t.get("name", ""), str(t.get("ref") or t.get("name", ""))
    if "机场" in name or "12号线" in name or ref in LATER_LINES:
        continue
    seq = []
    for m in r["members"]:
        if m["type"] == "node" and m.get("role", "").startswith("stop") and m["ref"] in nodes:
            n = nodes[m["ref"]]
            nm = n.get("tags", {}).get("name")
            if nm and (not seq or seq[-1][0] != nm):
                seq.append((nm, n["lat"], n["lon"]))
    names = [s[0] for s in seq]
    if ref in SEGMENTS and SEGMENTS[ref][0] in names and SEGMENTS[ref][1] in names:
        i, j = sorted((names.index(SEGMENTS[ref][0]), names.index(SEGMENTS[ref][1])))
        seq = seq[i:j + 1]
    removed = LATER_STOPS.get(ref, set())
    run = []
    for s in seq + [None]:
        if s is None or s[0] in removed:
            if len(run) > 1:
                key = (ref, frozenset(x[0] for x in run))
                if key not in seen:
                    seen.add(key)
                    lines.append({"line": ref, "points": [[round(v, 1) for v in project(x[1], x[2])] for x in run]})
            run = []
        else:
            run.append(s)
save("metro", lines)

# ----- rooms: fixed slot of each room inside its zone's cluster -----
slot = [0] * len(ZONE_IDS)
rows = []
for i, (zone, kind, start) in enumerate(rooms_meta):
    z = ZONE_IDS[zone]
    k = slot[zone] + CLEAR_CENTRE.get(z, 0)
    slot[zone] += 1
    rr = 0.62 * SPACING * math.sqrt(k + 0.5)
    th = k * GOLDEN
    rows.append({"room": i, "zone": z, "kind": R["types"][kind], "start": start, "x": round(pos[z][0] + rr * math.cos(th), 1), "y": round(pos[z][1] + rr * math.sin(th), 1)})
save("replay_rooms", rows)

# ----- replay: one row per arm and month -----
rows = []
for arm in ARMS:
    a = R["arms"][arm]
    for month, (delta, events, renew) in enumerate(zip(a["deltas"], a["events"], a["renew"])):
        rows.append({"arm": arm, "month": month, "rooms": delta, "events": events, "renew": renew})
save("replay", rows)
save("replay_people", [{"arm": arm, "people": [R["arms"][arm]["people"][str(i)] for i in range(len(R["arms"][arm]["people"]))]} for arm in ARMS])

# ----- monthly paths -----
METRICS = ["watch_commute", "other_commute", "commute", "watch_rent", "other_rent", "inq_in", "inq_out", "mode_in_subway", "cum_in", "vac_in", "vac_out", "low_cash", "rev_in", "blocked_low", "cum_blocked"]
SCALE = {"mode_in_subway": 100, "vac_in": 100, "vac_out": 100}
rows = []
for k in METRICS:
    for arm in ARMS:
        s = D["monthly"][arm][k]
        f = SCALE.get(k, 1)
        for month, (m, h) in enumerate(zip(s["m"], s["h"])):
            rows.append({"metric": k, "arm": arm, "month": month, "mean": round(m * f, 3), "half": round(h * f, 3)})
save("monthly", rows)

rows = []
for k, by_month in D["effect_by_month"].items():
    f = SCALE.get(k, 1)
    for month, e in enumerate(by_month):
        for name in ("direct", "total", "interaction"):
            rows.append({"metric": k, "effect": name, "month": month, "value": round(e[name][0] * f, 3), "half": round(e[name][1] * f, 3)})
save("effect_by_month", rows)

# ----- effects at the end: window averages, or the end of the run for totals -----
TABLE = [("watch_commute", 1, 1, None), ("commute", 2, 1, None), ("low_commute", 2, 1, None), ("watch_rent", 2, 1, None), ("other_rent", 2, 1, None), ("low_cash", 0, 1, None), ("rev_in", 0, 1, None),
         ("mode_in_subway", 1, 100, None), ("cum_in", 1, 1, "end"), ("cum_moves", 0, 1, "end"), ("cum_left", 1, 1, "end"), ("cum_blocked", 0, 1, "end")]
rows = []
for k, digits, f, how in TABLE:
    e = D["effect_by_month"][k][-1] if how == "end" else D["effect"][k]
    for name in ("direct", "total", "interaction"):
        v, h = round(e[name][0] * f, digits), round(e[name][1] * f, digits + 1 if digits < 2 else digits)
        rows.append({"metric": k, "effect": name, "value": v + 0, "half": h, "size": abs(v), "digits": digits})
save("effects", rows)

# ----- levels used in sentences -----
M = D["monthly"]
gain = lambda arm, key="inq_in": sum(M[arm][key]["m"][25:37]) / 12
rows = [
    {"key": "vac_in", "value": round(100 * D["tails"]["A"]["vac_in"], 1)},
    {"key": "vac_out", "value": round(100 * D["tails"]["A"]["vac_out"], 1)},
    {"key": "inq_gain", "value": round(100 * (gain("C") / gain("A") - 1), 1)},
    {"key": "share_in", "value": round(100 * D["tails"]["C"]["watch_share"], 1)},
    {"key": "rent_gap_60", "value": round(D["effect_by_month"]["watch_rent"][-1]["total"][0], 2)},
    {"key": "rent_gap_48", "value": round(D["effect_by_month"]["watch_rent"][48]["total"][0], 2)},
    {"key": "commute_jump", "value": round(M["C"]["watch_commute"]["m"][24] - M["C"]["watch_commute"]["m"][25], 1)},
    {"key": "drift_rent_A", "value": round(tail(M["A"]["watch_rent"]["m"]) - 100, 1)},
    {"key": "subway_start", "value": round(100 * M["A"]["mode_in_subway"]["m"][0])},
    {"key": "subway_end", "value": round(100 * M["A"]["mode_in_subway"]["m"][-1])},
    {"key": "seeds", "value": D["seeds"]},
    {"key": "months", "value": D["months"]},
    {"key": "opens", "value": D["opens"] + 1},
    {"key": "tail", "value": D["tail"]},
    {"key": "rooms", "value": len(rooms_meta)},
    {"key": "zones", "value": len(ZONE_IDS)},
    {"key": "tenants", "value": 1140},
    {"key": "replay_seed", "value": R["seed"]},
]
vac = {z: tail(D["zones"]["A"][z]["vac"]) for z in ZONE_IDS}
rows.append({"key": "max_shift_km", "value": round(max(shift.values()), 1)})
rows.append({"key": "vac_max", "value": round(100 * max(vac.values()), 1)})
rest = [z for z in ZONE_IDS if z not in WATCH and vac[z] <= 0.10]
rows.append({"key": "vac_rest", "value": round(100 * sum(vac[z] * count[ZONE_IDS.index(z)] for z in rest) / sum(count[ZONE_IDS.index(z)] for z in rest), 1)})
rows.append({"key": "vac_high_zones", "value": sum(v > 0.10 for v in vac.values())})
rows.append({"key": "vac_low_zones", "value": sum(v < 0.05 for v in vac.values())})
save("levels", rows)

# ----- zones -----
rows = []
for i, z in enumerate(BOARD["zones"]):
    zid = z["id"]
    e = D["zone_effect"][zid]
    rows.append(dict(zone=zid, name=NAMES[zid], dir=z["dir"], ring=z["ring"], lat=CENTROIDS[zid][0], lon=CENTROIDS[zid][1], x=round(pos[zid][0], 1), y=round(pos[zid][1], 1), r=round(radius[zid], 1), lx=labels[zid][0], ly=labels[zid][1],
                     major=zid in MAJOR, treated=zid in WATCH, rooms=count[ZONE_IDS.index(zid)], subway=z["options"]["地铁"]["min"], whole=z["rents"]["整租"], psm=LISTINGS[zid]["psm"],
                     vac=round(100 * tail(D["zones"]["A"][zid]["vac"]), 1), tenants=round(tail(D["zones"]["C"][zid]["n"]), 1),
                     rent=round(e["rent"]["total"][0], 2), rent_h=round(e["rent"]["total"][1], 2), commute=round(e["commute"]["direct"][0], 2), commute_h=round(e["commute"]["direct"][1], 2), n=round(e["n"]["total"][0], 2), n_h=round(e["n"]["total"][1], 2)))
rows.sort(key=lambda r: r["subway"])
save("zones", rows)
print("map height", round(HEIGHT))
save("map", [{"width": 1000, "height": round(HEIGHT), "cbd_x": round(cbd[0], 1), "cbd_y": round(cbd[1], 1)}])

# ----- who gets what -----
GROUP = {"low": "较低", "mid": "中等", "high": "较高"}
rows = []
for where, title in (("in", "受益区"), ("out", "其他区域")):
    for g, label in GROUP.items():
        b = D["ledger"][f"{g}_{where}"]
        rows.append({"row": f"{g}_{where}", "where": title, "who": f"{label}收入租客", "n": round(b["n"]["level"]["C"]), "commute": round(b["commute"]["effect"]["direct"][0], 1), "commute_h": round(b["commute"]["effect"]["direct"][1], 1),
                     "rent": round(b["rent"]["effect"]["total"][0]), "rent_h": round(b["rent"]["effect"]["total"][1]), "fare": round(b["fare"]["effect"]["direct"][0]), "fare_h": round(b["fare"]["effect"]["direct"][1])})
for key, title in (("rev_in", "受益区"), ("rev_out", "其他区域")):
    e = D["effect"][key]["total"]
    rows.append({"row": key, "where": title, "who": "房东（每间房）", "n": None, "commute": None, "commute_h": None, "rent": round(e[0]), "rent_h": round(e[1]), "fare": None, "fare_h": None})
save("ledger", rows)

# ----- assumption tests, from the earlier 30-seed run -----
LABEL = {"base": "基准", "tau 25": "房量衰减 25 分钟", "tau 60": "房量衰减 60 分钟", "low-cost rooms -30%": "低价房减少 30%", "low-cost rooms -60%": "低价房减少 60%", "occupancy 0.99": "入住率 99%", "savings half": "存款减半",
         "saving x2": "快线省时翻倍", "mid lines 20/30": "中等收入占比线 20/30", "mid lines 30/55": "中等收入占比线 30/55", "low lines 15/30": "较低收入占比线 15/30", "low lines 25/55": "较低收入占比线 25/55", "outside floor 0.8": "外部下限 80%", "outside floor 1.0": "外部下限 100%"}
rows = []
text = open(os.path.join(HERE, "run_v06_output.txt"), encoding="utf-8").read()
for line in text[text.index("assumption tests"):].splitlines():
    m = re.match(r"^(.+?)\s{2,}(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([+-][\d.]+) \+-([\d.]+)", line)
    if m:
        rows.append({"variant": m[1], "label": LABEL[m[1]], "seated": int(m[2]), "commute": float(m[4]), "low_burden": round(100 * float(m[6]), 1), "low_over30": round(100 * float(m[7])), "left": float(m[8]), "blocked_low": float(m[9]), "premium": float(m[11]), "premium_h": float(m[12])})
assert len(rows) == len(LABEL)
save("assumptions", rows)

rows = []
for name, label, k in (("scenarios_v06_k0.txt", "只看空置率", 0.0), ("scenarios_v06_output.txt", "加询盘，强度 0.2（基准）", 0.2), ("scenarios_v06_k0.4.txt", "加询盘，强度 0.4", 0.4)):
    text = open(os.path.join(HERE, name), encoding="utf-8").read()
    hits = re.findall(r"^watch_rent.*?([+-][\d.]+)±([\d.]+)\s*$", text, re.M)
    rows.append({"k": k, "label": label, "express": float(hits[0][0]), "express_h": float(hits[0][1]), "replay": float(hits[1][0]), "replay_h": float(hits[1][1])})
save("landlord_rules", rows)

# ----- real rent gaps, copied from line_rent_results.md and center_compare_results.md -----
real = [("16 号线北段", 5.8, -4.8, 13.7, 10), ("14 号线中段", 2.3, -1.5, 6.7, 46), ("昌平线二期", 0.0, -16.6, 11.8, 8), ("2014 年底开通的线路", -1.3, -3.6, 1.0, 145), ("2017 年底开通的线路", -3.4, -6.9, 0.0, 9), ("CBD 省时 5 分钟以上的网格", 5.9, 2.9, 9.1, 69)]
rows = [{"label": a, "group": "真实挂牌（%）", "value": v, "lo": lo, "hi": hi, "cells": c} for a, v, lo, hi, c in real]
rule = json.load(open(os.path.join(OUT, "landlord_rules.json"), encoding="utf-8"))
for label, r, key in (("真实路网回放", rule[1], "replay"), ("假想快线，询盘 0.2", rule[1], "express"), ("假想快线，询盘 0.4", rule[2], "express")):
    rows.append({"label": label, "group": "规则版（指数点）", "value": r[key], "lo": round(r[key] - r[key + "_h"], 2), "hi": round(r[key] + r[key + "_h"], 2), "cells": None})
save("real_vs_rule", rows)

# ----- baseline against reported figures, as in the plan -----
t = D["tails"]["A"]
save("baseline", [
    {"metric": "平均通勤（分钟）", "model": round(t["commute"], 1), "real": "48（2021，通勤监测报告）"},
    {"metric": "60 分钟以上占比（%）", "model": round(100 * t["over60"]), "real": "28–30（通勤监测报告）"},
    {"metric": "房租占收入（%）", "model": round(100 * t["all_burden"], 1), "real": "24.0–26.3（贝壳与清华，北京）"},
    {"metric": "低收入者房租超过 30%（%）", "model": round(100 * t["low_over30"]), "real": "近 3 成（贝壳与清华，全国）"},
])
