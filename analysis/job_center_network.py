"""Compare Beijing job centres as hubs of a radial game board, using OSM stop sequences.

Network-only estimates: 45 km/h, 0.6 min dwell, 5 min transfer. No crowding, no walking or waiting.
Era filters are hand-written from opening dates and need checking before use in the report.
"""
import heapq
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(HERE, "bj_routes_full.json"), encoding="utf-8"))
nodes = {e["id"]: e for e in data["elements"] if e["type"] == "node"}
rels = [e for e in data["elements"] if e["type"] == "relation"]
SPEED, DWELL, TRANSFER = 45, 0.6, 5

LATER_LINES = {"17", "19", "3", "11", "18"}
SEGMENTS = {"27": ("昌平西山口", "西二旗"), "8": ("朱辛庄", "南锣鼓巷"), "7": ("北京西站", "焦化厂"),
            "25N": ("郭公庄", "阎村东"), "16": ("北安河", "西苑"), "6": ("海淀五路居", "潞城")}
LATER_STOPS = {"14": set("东管头 丽泽商务区 菜户营 西铁营 景风门".split()),
               "1": set("花庄 环球度假区".split()), "1E": set("花庄 环球度假区".split()),
               "24;L2": {"亦庄火车站"}}
FORMER = {
    "2018": {},
    "2015": {"14": set("永定门外 景泰 蒲黄榆 方庄 十里河 南八里庄 北工大西门 平乐园 九龙山 大望路 红庙".split()),
             "27": set("北邵洼 昌平东关 昌平 十三陵景区 昌平西山口".split())},
}
CENTRES = {
    "CBD": "国贸 大望路 金台夕照 永安里 呼家楼",
    "中关村": "中关村 海淀黄庄 知春路 苏州街",
    "金融街": "复兴门 阜成门 西单 车公庄",
    "上地-西二旗": "上地 西二旗",
    "望京": "望京 望京南 阜通 望京西 东湖渠",
    "亦庄": "荣京东街 荣昌东街 同济南路 经海路",
    "丰台科技园": "科怡路 丰台科技园 丰台南路",
}


def km(a, b):
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 85.3)


def network(era):
    graph, pos, lines_at = {}, {}, {}
    for r in rels:
        t = r.get("tags", {})
        name, ref = t.get("name", ""), str(t.get("ref") or t.get("name", ""))
        if "机场" in name or "12号线" in name or ref in LATER_LINES:
            continue
        if era == "2015" and (ref == "16" or "燕房" in name):
            continue
        seq = []
        for m in r["members"]:
            if m["type"] == "node" and m.get("role", "").startswith("stop") and m["ref"] in nodes:
                n = nodes[m["ref"]]
                nm = n.get("tags", {}).get("name")
                if nm and (not seq or seq[-1][0] != nm):
                    seq.append((nm, (n["lat"], n["lon"])))
        names = [s[0] for s in seq]
        if ref in SEGMENTS:
            a, b = SEGMENTS[ref]
            if a in names and b in names:
                i, j = sorted((names.index(a), names.index(b)))
                seq = seq[i:j + 1]
        removed = set(LATER_STOPS.get(ref, set())) | FORMER[era].get(ref, set())
        for a, b in zip(seq, seq[1:]):
            if a[0] in removed or b[0] in removed:
                continue
            w = km(a[1], b[1]) * 1.12 / SPEED * 60 + DWELL
            graph.setdefault((a[0], ref), []).append(((b[0], ref), w))
            pos[a[0]], pos[b[0]] = a[1], b[1]
            lines_at.setdefault(a[0], set()).add(ref)
            lines_at.setdefault(b[0], set()).add(ref)
    for s, refs in lines_at.items():
        for x in refs:
            for y in refs:
                if x != y:
                    graph.setdefault((s, x), []).append(((s, y), TRANSFER))
    return graph, pos, lines_at


def dijkstra(graph, starts):
    dist, pq = {}, [(0, s) for s in starts]
    while pq:
        t, u = heapq.heappop(pq)
        if u in dist:
            continue
        dist[u] = t
        for v, w in graph.get(u, []):
            if v not in dist:
                heapq.heappush(pq, (t + w, v))
    return dist


def station_times(dist):
    out = {}
    for (s, _), t in dist.items():
        out[s] = min(out.get(s, 1e9), t)
    return out


def sector(p, c):
    angle = math.degrees(math.atan2((p[1] - c[1]) * 85.3, (p[0] - c[0]) * 111.2)) % 360
    return ["北", "东北", "东", "东南", "南", "西南", "西", "西北"][int((angle + 22.5) // 45) % 8]


g18, pos18, lines18 = network("2018")
g15, pos15, lines15 = network("2015")
print(f"stations 2018 network {len(pos18)}, 2015 network {len(pos15)}")
for name, anchors in CENTRES.items():
    anchors = [a for a in anchors.split() if a in lines18]
    centre = (sum(pos18[a][0] for a in anchors) / len(anchors), sum(pos18[a][1] for a in anchors) / len(anchors))
    arrivals = sorted({(a, r) for a in anchors for r in lines18[a]})
    t18 = station_times(dijkstra(g18, arrivals))
    a15 = [(a, r) for a in anchors if a in lines15 for r in lines15[a]]
    t15 = station_times(dijkstra(g15, a15))
    bands = [sum(lo < t <= hi for s, t in t18.items() if s not in anchors) for lo, hi in [(0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 200)]]
    sec = {}
    for s, t in t18.items():
        if 30 < t <= 60:
            k = sector(pos18[s], centre)
            sec[k] = sec.get(k, 0) + 1
    by_arrival = [dijkstra(g18, [a]) for a in arrivals]
    options = []
    for s, t in t18.items():
        if 30 < t <= 75:
            best = {}
            for a, d in zip(arrivals, by_arrival):
                v = min((x for (st, _), x in d.items() if st == s), default=None)
                if v is not None and v <= t + 10:
                    best[a[1]] = 1
            options.append(len(best))
    saved = sorted(((t15.get(s, 200) - t, s, round(t15.get(s, 200)), round(t)) for s, t in t18.items() if s in t15), reverse=True)
    big = [x for x in saved if x[0] >= 5]
    print(f"\n{name}: anchors {anchors}; lines {sorted({r for a in anchors for r in lines18[a]})}")
    print("  stations by time 0-15,15-30,30-45,45-60,60-75,75+:", bands)
    print("  30-60 min by direction:", dict(sorted(sec.items(), key=lambda x: -x[1])))
    print(f"  arrival lines within 10 min of best, 30-75 min stations: mean {sum(options) / max(len(options), 1):.2f}, share with 2+ {sum(o >= 2 for o in options) / max(len(options), 1):.0%}")
    print(f"  stations saving 5+ min from 2015 to 2018 network: {len(big)}; top:", [(s, a, b) for _, s, a, b in big[:6]])
    print("  newly reached stations:", [s for s in t18 if s not in t15][:12], len([s for s in t18 if s not in t15]))
