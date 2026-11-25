"""Export station travel times to CBD and Wangjing for the 2015 and 2018 networks."""
import contextlib
import io
import json

with contextlib.redirect_stdout(io.StringIO()):
    import job_center_network as j

out = {}
for name in ["CBD", "望京"]:
    anchors = [a for a in j.CENTRES[name].split() if a in j.lines18]
    t18 = j.station_times(j.dijkstra(j.g18, sorted({(a, r) for a in anchors for r in j.lines18[a]})))
    t15 = j.station_times(j.dijkstra(j.g15, [(a, r) for a in anchors if a in j.lines15 for r in j.lines15[a]]))
    out[name] = {"anchors": anchors, "t18": {k: round(v, 1) for k, v in t18.items()}, "t15": {k: round(v, 1) for k, v in t15.items()}}
out["pos"] = {k: [round(v[0], 5), round(v[1], 5)] for k, v in j.pos18.items()}
json.dump(out, open("center_access.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(out["pos"]), len(out["CBD"]["t18"]), len(out["CBD"]["t15"]), len(out["望京"]["t15"]))
