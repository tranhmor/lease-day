"""Time saved per home zone by two network changes: 2015 to 2018 (replay) and adding Line 17 (the game's main shock).

Each zone is sampled at its listing centroid and three busiest stations, walking at 12 min/km to any station within 3 km.
Network-only times from job_center_network.py, so only the differences are used.
"""
import contextlib
import io
import json
import math
import os

with contextlib.redirect_stdout(io.StringIO()):
    import job_center_network as j

HERE = os.path.dirname(os.path.abspath(__file__))
ACCESS = json.load(open(os.path.join(HERE, "center_access.json"), encoding="utf-8"))
NAMES = sorted(ACCESS["CBD"]["t18"])
ZONES = json.load(open(os.path.join(HERE, "zone_listings.json"), encoding="utf-8"))["zones"]
CENTROIDS = json.load(open(os.path.join(HERE, "zone_centroids.json"), encoding="utf-8"))
ANCHORS = ACCESS["CBD"]["anchors"]


def times(graph, lines):
    starts = sorted({(a, r) for a in ANCHORS if a in lines for r in lines[a]})
    return j.station_times(j.dijkstra(graph, starts))


def door(point, table, pos):
    best = None
    for s, t in table.items():
        if s in pos:
            d = j.km(point, pos[s])
            if d <= 3 and (best is None or t + 12 * d < best):
                best = t + 12 * d
    return best


g18, pos18, lines18 = j.network("2018")
g15, pos15, lines15 = j.network("2015")
t18, t15 = times(g18, lines18), times(g15, lines15)
j.LATER_LINES.discard("17")
g17, pos17, lines17 = j.network("2018")
t17 = times(g17, lines17)
added = sorted(s for s in pos17 if s not in pos18)
print("Line 17 stops in the data:", sorted(lines17_s for lines17_s, refs in lines17.items() if "17" in refs))
print("stations added:", len(added))
out = {}
for z in ZONES:
    points = [tuple(ACCESS["pos"][NAMES[i]]) for i in z["st"]] + [tuple(CENTROIDS[z["id"]])]
    line17, replay = [], []
    for p in points:
        a, b, c = door(p, t18, pos18), door(p, t17, pos17), door(p, t15, pos15)
        if a is not None and b is not None:
            line17.append(max(0, a - b))
        if a is not None and c is not None:
            replay.append(max(0, c - a))
    out[z["id"]] = {"line17": round(sum(line17) / len(line17), 1) if line17 else 0, "replay_2015_2018": round(sum(replay) / len(replay), 1) if replay else 0}
    print(z["id"], z["dir"], z["ring"], z["comm"], out[z["id"]])
json.dump(out, open(os.path.join(HERE, "zone_shock.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
