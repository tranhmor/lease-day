"""Build the CBD game board: one work zone, 23 home zones, room stock and door-to-door travel options.

Inputs: zone_listings.json (2018 listings), census tables 9-4 and 9-5 (2020), zone_modes.json (OSM roads and buses),
job_center_network.py (subway on the 2018 network).
Every parameter in ASSUMED is my assumption and needs checking against map samples or published figures.
"""
import contextlib
import heapq
import io
import itertools
import json
import math
import os

with contextlib.redirect_stdout(io.StringIO()):
    import job_center_network as j

HERE = os.path.dirname(os.path.abspath(__file__))
L = json.load(open(os.path.join(HERE, "zone_listings.json"), encoding="utf-8"))
MODES = json.load(open(os.path.join(HERE, "zone_modes.json"), encoding="utf-8"))
ACCESS = json.load(open(os.path.join(HERE, "center_access.json"), encoding="utf-8"))
STATION_NAMES = sorted(ACCESS["CBD"]["t18"])

ROOMS_RULE, ROOMS_LLM = 1200, 240
ASSUMED = {
    "subway_wait_and_entry_min": 5, "cbd_walk_min": 6,
    "bus_kmh": 15, "bus_wait_min": 8, "bus_home_walk_min": 5, "bus_transfer_min": 10,
    "bike_kmh": 12, "ebike_kmh": 20, "bike_park_min": 3, "foot_kmh": 4.43,
    "car_park_walk_min": 5, "fuel_per_km": 0.7, "parking_per_day": 60,
    "bike_month": 30, "ebike_month": 120, "workdays": 26, "max_option_min": 120,
    "wage_spread_sigma": 0.5, "wage_trade_estate": 7000, "wage_other": 5000, "gravity_tau_min": 40,
}
CAP = {"步行": 60, "自行车": 90, "电动车": 90}  # options above these minutes are not offered
PEAK_KMH = 26.05  # Amap and partners, Beijing peak driving speed, 2026 Q1, via Beijing News; a citywide average, not 2018

BANDS = [0, 200, 500, 1000, 2000, 3000, 4000, 6000, 8000, 10000, 15000]
RENT_TABLE = {  # census 9-5, sample households; totals reconcile with the table
    "东城": [5857, 265, 186, 635, 489, 404, 898, 1021, 445, 489],
    "西城": [5893, 415, 341, 1007, 868, 795, 1698, 1907, 814, 839],
    "朝阳": [3298, 795, 5860, 10347, 3755, 3578, 9180, 5876, 2082, 2433],
    "丰台": [4211, 754, 2804, 3258, 3243, 2974, 6141, 1958, 390, 180],
    "石景山": [517, 239, 547, 545, 687, 783, 1518, 305, 70, 68],
    "海淀": [3284, 1630, 3928, 9111, 5231, 3708, 5638, 5213, 1888, 1755],
    "门头沟": [318, 205, 549, 537, 1243, 576, 180, 13, 9, 1],
    "房山": [390, 1093, 1734, 3170, 2019, 1107, 353, 33, 8, 18],
    "通州": [507, 2911, 2630, 3208, 3254, 4837, 2444, 309, 57, 55],
    "顺义": [310, 4898, 8248, 3211, 1874, 2079, 1127, 175, 57, 219],
    "昌平": [627, 2450, 10994, 11444, 4053, 3543, 3999, 1569, 255, 127],
    "大兴": [425, 4327, 4038, 4144, 3632, 4424, 2289, 412, 118, 93],
}
PUBLIC = {"东城": 5163, "西城": 5629, "朝阳": 5952, "丰台": 4205, "石景山": 689, "海淀": 7789, "门头沟": 505,
          "房山": 1290, "通州": 1733, "顺义": 1134, "昌平": 2390, "大兴": 2656}  # census 9-4, public rental
PRIVATE = {"东城": 5526, "西城": 8948, "朝阳": 41252, "丰台": 21708, "石景山": 4590, "海淀": 33597, "门头沟": 3126,
           "房山": 8635, "通州": 18479, "顺义": 21064, "昌平": 36671, "大兴": 21246}  # census 9-4, other rental
CBD_JOBS = {"租赁和商务服务业": 16.2, "批发和零售业": 8.1, "金融业": 4.2, "房地产业": 3.4, "信息传输、软件和信息技术服务业": 3.0, "其他": 12.7}  # third economic census, 2013, 10k people


def market_bands():
    """Census rent bands with public rental households taken out from the cheapest bands."""
    out = {}
    for d, row in RENT_TABLE.items():
        left, clean = PUBLIC[d], []
        for c in row:
            used = min(c, left)
            left -= used
            clean.append(c - used)
        out[d] = clean
    return out


def share_between(mix, lo, hi):
    total = sum(mix)
    s = 0
    for c, a, b in zip(mix, BANDS, BANDS[1:]):
        s += c * max(0, min(hi, b) - max(lo, a)) / (b - a)
    return s / total


def mean_below(mix, top):
    mids = [(a + min(b, top)) / 2 for a, b in zip(BANDS, BANDS[1:]) if a < top]
    weights = [c * (min(b, top) - a) / (b - a) for c, a, b in zip(mix, BANDS, BANDS[1:]) if a < top]
    return sum(m * w for m, w in zip(mids, weights)) / sum(weights)


def largest_remainder(weights, total):
    scaled = [w * total / sum(weights) for w in weights]
    out = [math.floor(s) for s in scaled]
    order = sorted(range(len(out)), key=lambda i: scaled[i] - out[i], reverse=True)
    for i in order[:total - sum(out)]:
        out[i] += 1
    return out


def subway_routes(station):
    anchors = [a for a in ACCESS["CBD"]["anchors"] if a in j.lines18]
    by_line = {}
    for a in anchors:
        for r in j.lines18[a]:
            by_line.setdefault(r, []).append((a, r))
    tick = itertools.count()
    found = {}
    for line, starts in by_line.items():
        dist, prev, pq = {}, {}, [(0, next(tick), s, None) for s in starts]
        while pq:
            t, _, u, p = heapq.heappop(pq)
            if u in dist:
                continue
            dist[u], prev[u] = t, p
            for v, w in j.g18.get(u, []):
                if v not in dist:
                    heapq.heappush(pq, (t + w, next(tick), v, u))
        ends = [(dist[n], n) for n in dist if n[0] == station]
        if not ends:
            continue
        t, node = min(ends)
        lines, length = [node[1]], 0.0
        while prev[node] is not None:
            back = prev[node]
            if back[1] == node[1]:
                length += (dist[node] - dist[back] - j.DWELL) * j.SPEED / 60
            else:
                lines.append(back[1])
            node = back
        key = tuple(lines)
        if key not in found or t < found[key][0]:
            found[key] = (t, length)
    routes = sorted(((t, k, n) for k, (t, n) in found.items()))
    if not routes:
        return []
    best, kept = routes[0][0], []
    for t, k, n in routes:
        # A route that only adds a last hop inside the CBD is not a different way in.
        if t <= best + 10 and not any(k[:len(x["lines"])] == tuple(x["lines"]) for x in kept):
            kept.append({"lines": list(k), "ride_min": round(t), "transfers": len(k) - 1, "km": round(n, 1)})
    return kept[:3]


def subway_fare(km):
    for top, fare in [(6, 3), (12, 4), (22, 5), (32, 6)]:
        if km <= top:
            return fare
    return 6 + math.ceil((km - 32) / 20)


def bus_fare(km):
    full = 2 if km <= 10 else 2 + math.ceil((km - 10) / 5)
    return full * 0.5


def taxi_fare(km, delay_min):
    return 14 + 2.3 * max(0, km - 3) + 1.15 * max(0, km - 15) + 4.6 * delay_min / 5


def options(zone, m):
    a, wd = ASSUMED, ASSUMED["workdays"]
    out = {}
    routes = subway_routes(STATION_NAMES[zone["st"][0]])
    if routes:
        fixed = a["subway_wait_and_entry_min"] + a["cbd_walk_min"]
        minutes = zone["t"] + fixed
        out["地铁"] = {"min": minutes, "transfers": routes[0]["transfers"], "month": 2 * wd * subway_fare(routes[0]["km"]),
                     "routes": [{**r, "door_min": r["ride_min"] - routes[0]["ride_min"] + minutes} for r in routes]}
        if zone["wk"] >= 10:
            saved = zone["wk"] * (1 - 5 / 12) - 2
            out["骑车接地铁"] = {"min": round(minutes - saved), "transfers": routes[0]["transfers"], "month": out["地铁"]["month"] + a["bike_month"]}
    centre = zone["id"] == "Z00"
    bike_km = zone["km"] * 1.3 if centre else m["bike_km"]
    foot_km = bike_km if centre else m["foot_km"]
    road_km = bike_km if centre else min(m["car_km"], m["bike_km"] * 1.15)
    bus_km = bike_km * 1.1
    bus_min = bus_km / a["bus_kmh"] * 60 + a["bus_home_walk_min"] + a["bus_wait_min"] + a["cbd_walk_min"]
    if m["direct_bus_lines"]:
        out["公交直达"] = {"min": round(bus_min), "transfers": 0, "lines": m["direct_bus_lines"], "month": round(2 * wd * bus_fare(bus_km))}
    else:
        out["公交换乘"] = {"min": round(bus_min + a["bus_transfer_min"]), "transfers": 1, "lines": 0, "month": round(2 * wd * bus_fare(bus_km))}
    out["电动车"] = {"min": round(bike_km / a["ebike_kmh"] * 60 + a["bike_park_min"]), "transfers": 0, "month": a["ebike_month"]}
    out["自行车"] = {"min": round(bike_km / a["bike_kmh"] * 60 + a["bike_park_min"]), "transfers": 0, "month": a["bike_month"]}
    out["步行"] = {"min": round(foot_km / a["foot_kmh"] * 60), "transfers": 0, "month": 0}
    peak = road_km / PEAK_KMH * 60
    free = road_km / 60 * 60
    out["私家车"] = {"min": round(peak + a["car_park_walk_min"]), "transfers": 0, "month": round(wd * (2 * road_km * a["fuel_per_km"] + a["parking_per_day"]))}
    out["打车"] = {"min": round(peak), "transfers": 0, "month": round(2 * wd * taxi_fare(road_km, peak - free))}
    return {k: v for k, v in out.items() if v["min"] <= CAP.get(k, a["max_option_min"])}


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def income_mix():
    medians = {"租赁和商务服务业": 5167, "批发和零售业": ASSUMED["wage_trade_estate"], "金融业": 23783, "房地产业": ASSUMED["wage_trade_estate"],
               "信息传输、软件和信息技术服务业": 17508, "其他": ASSUMED["wage_other"]}
    total = sum(CBD_JOBS.values())
    low = mid = 0.0
    for k, n in CBD_JOBS.items():
        s = ASSUMED["wage_spread_sigma"]
        a, b = phi(math.log(7000 / medians[k]) / s), phi(math.log(15000 / medians[k]) / s)
        low += n / total * a
        mid += n / total * (b - a)
    return {"较低 4,000-7,000": round(low, 3), "中等 7,000-15,000": round(mid, 3), "较高 15,000-35,000": round(1 - low - mid, 3)}


def build():
    bands = market_bands()
    all_by_d = L["listing_all_by_district"]
    zones = []
    for z in L["zones"]:
        h = {d.replace("区", ""): PRIVATE[d] * n / all_by_d[d] for d, n in z["dd"].items() if d in PRIVATE and all_by_d.get(d)}
        total = sum(h.values())
        mix = [sum(h[d] * bands[d][i] / sum(bands[d]) for d in h) / total for i in range(len(BANDS) - 1)]
        r10, r50 = z["r"][0], z["r"][2]
        trusted = z["nr"] >= 30
        if not trusted:  # too few room ads; ratios are typical of the zones at 45-75 min
            r10, r50 = round(z["w"][1] * 0.36), round(z["w"][1] * 0.45)
        split = (r50 + z["w"][1]) / 2
        shares = {"低价房": share_between(mix, 0, 1000), "便宜单间": share_between(mix, 1000, r10),
                  "合租单间": share_between(mix, r10, split), "整租": share_between(mix, split, 15000)}
        rents = {"低价房": round(mean_below(mix, 1000), -1), "便宜单间": round((1000 + r10) / 2, -2), "合租单间": r50, "整租": z["w"][1]}
        zones.append({**{k: z[k] for k in ("id", "dir", "ring", "comm", "n", "nw", "nr", "psm", "t", "sv5", "km")},
                      "renters_sample": round(total), "shares": {k: round(v, 3) for k, v in shares.items()}, "rents": rents,
                      "room_rent_from_listings": trusted, "whole_2015": z["w15"][1], "whole_2018": z["w"][1],
                      "options": options(z, MODES[z["id"]]), "top_stations": [STATION_NAMES[i] for i in z["st"]]})
    stock = sum(z["renters_sample"] for z in zones)
    weights = []
    for z in zones:
        z["stock_share"] = round(z["renters_sample"] / stock, 3)
        weights.append(z["renters_sample"] * math.exp(-z["options"]["地铁"]["min"] / ASSUMED["gravity_tau_min"]))
    for n, key in [(ROOMS_RULE, "rooms_rule"), (ROOMS_LLM, "rooms_llm")]:
        for zone, count in zip(zones, largest_remainder(weights, n)):
            zone[key] = count
            zone[key + "_by_type"] = dict(zip(zone["shares"], largest_remainder(list(zone["shares"].values()), count)))
    work = {"name": "CBD", "anchors": ACCESS["CBD"]["anchors"], "centre": [39.912, 116.456], "area_km2": 7,
            "units_2013": 20229, "jobs_2013_10k": 47.7, "jobs_by_industry_10k": CBD_JOBS, "income_mix": income_mix()}
    return {"assumed": ASSUMED, "peak_kmh": PEAK_KMH, "work": work, "zones": zones}


MODE_ORDER = ["地铁", "骑车接地铁", "公交直达", "公交换乘", "电动车", "自行车", "步行", "私家车", "打车"]
DOC = """# CBD 棋盘 v0.1

状态：2026-11-01 生成，由 `build_board.py` 输出；机器可读版本是 `board_cbd_v01.json`。游戏和 LLM 都还没有在这张棋盘上跑。

## 工作区

| 定量 | 取值 | 来源和年份 |
|---|---|---|
| 范围 | 国贸、大望路、金台夕照、永安里、呼家楼；规划约 7 km² | 北京统计年鉴 2012 |
| 就业 | 47.7 万人，法人单位 20,229 个 | 第三次经济普查，2013 |
| 行业 | 商务服务 16.2，批发零售 8.1，金融 4.2，房地产 3.4，信息 3.0，其他 12.7（万人） | 同上 |
| 收入构成 | 较低 / 中等 / 较高 = {mix} | 粗估：行业人数 × 北京 2020 行业中位薪酬，批发零售、房地产和其他的工资及组内离散度是假设 |

## 住房区域

划分规则：8 个方向 × 通勤时段，房源少于约 200 条的格子并入相邻格；离 CBD 中心 2.5 km 内单列 Z00。

CBD 租客可竞争房量（1,200 间版本）：{rings}。按房型：{types}。

{zones}

- 整租、合租单间的租金是 2018 年挂牌中位数；带 * 的区域单间挂牌不足 30 条，按整租租金的 45% 估算。
- 低价房（1,000 元以下）和便宜单间（1,000 元到该区单间挂牌第 10 百分位）几乎不在挂牌数据里，由普查租金分档推得。
- 全市租房存量份额 = 普查各区市场租房户 × 该区域在本区挂牌中的份额。房型比例按区级普查分档，已扣除公租房，所以同一区内差别被抹平。
- 真实区域的房子大多住着在别处上班的人。CBD 租客可竞争房量 = 存量份额 × exp(−地铁分钟 / 40)，40 分钟是假设，测试时会改变。

## 每个区域到 CBD 的出行选项（早高峰单程分钟 / 每月通勤费）

{trips}

- 地铁：2018 路网 + 家到站步行 + 进站候车 5 分钟 + CBD 端步行 6 分钟，不含拥挤。路线只列真正不同的走法，不列 CBD 内多换一站的走法。
- 公交：长度为 OSM 骑行距离 × 1.1，15 km/h，等车 8 分钟。直达与否看 OSM 线路，OSM 未必完整，且是今天的线路。
- 自行车 12 km/h，电动车 20 km/h，步行 4.43 km/h，距离来自 OSM 道路。
- 私家车和打车：全市高峰均速 26 km/h，CBD 进城方向可能更慢。私家车含油费和每天 60 元停车费，不是所有人都有车。
- 票价：地铁、公交按 2014 年规则，公交刷卡 5 折凭记忆未核实；出租车按 2013 年规则。
- 超过 120 分钟（步行 60、自行车和电动车 90）的方式不提供。

## 各定量的状态

| 定量 | 依据 | 状态 |
|---|---|---|
| 区域租金 | 2018 挂牌，2015 可作起点 | 真实要价，不是成交价 |
| 区域房量和房型 | 普查 2020 + 挂牌份额 | 估算 |
| CBD 就业和行业 | 经普 2013 | 真实但偏旧 |
| 收入构成 | 行业中位薪酬 2020 + 假设 | 粗估 |
| 地铁路线和换乘 | OSM + 手写年代筛选 | 待校准 |
| 其他方式时间 | OSM 距离 + 假设速度 | 待校准 |
| 通勤费 | 官方票价规则 | 真实；电动车、自行车、停车是假设 |
| 空置率 5%（租客 = 房量 × 0.95） | 无 | 假设 |
| 非 CBD 租客占比 | CBD 就业约占全市 3.5%（分子 2013，分母 2018） | 缺，按情景处理 |

## 校验

- 约 13 km 的区域（Z06、Z08）地铁 47–49 分钟；北京交通发展研究院 2023 报告的中心城平均通勤是 51 分钟、13.2 km（全部交通方式）。
- 后续校验目标：通州到 CBD、天通苑到 CBD 应是主要通勤走廊；各收入、各距离的方式比例对照北京调查数据（`processed_individual_data.csv`）。

## 已知局限

- 年份不一致：就业 2013，挂牌 2018，普查 2020，薪酬 2020，公交线路和车速 2026。
- 真实区域里 CBD 上班者只占少数。假如房东只看 CBD 租客的空置，会高估新线对租金的影响，所以要跑两档：房东只看 CBD 租客；房东看到的空置只有 10% 来自 CBD 租客，其余 90% 来自稳定在 5% 空置的背景租客。
- 区域内部差异被中位数抹平；单间挂牌标题识别不完全。
"""


def tables(board):
    rows = ["| 区域 | 方向 | 圈层 | 代表地名 | 挂牌：整租 / 单间 | 全市租房存量份额 | CBD 租客可竞争房量（1,200 / 240） | 低价房 / 便宜单间 / 合租 / 整租 占比 | 对应月租 | 整租 2015→2018 | 2015–18 省时 5 分钟以上 |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for z in board["zones"]:
        s, r = z["shares"], z["rents"]
        note = "" if z["room_rent_from_listings"] else "*"
        rows.append(f"| {z['id']} | {z['dir']} | {z['ring']} | {z['comm']} | {z['nw']:,} / {z['nr']:,} | {z['stock_share']:.1%} | {z['rooms_rule']} / {z['rooms_llm']} | "
                    + " / ".join(f"{v:.0%}" for v in s.values()) + f" | {r['低价房']:,.0f} / {r['便宜单间']:,.0f} / {r['合租单间']:,}{note} / {r['整租']:,} | {z['whole_2015']:,}→{z['whole_2018']:,} | {z['sv5']}% |")
    trips = ["| 区域 | 地铁路线 | " + " | ".join(MODE_ORDER) + " |", "|---|---|" + "---|" * len(MODE_ORDER)]
    for z in board["zones"]:
        o = z["options"]
        lines = "；".join(" → ".join(r["lines"]) for r in o.get("地铁", {}).get("routes", []))
        trips.append(f"| {z['id']} | {lines} | " + " | ".join(f"{o[m]['min']} 分 / {o[m]['month']:,} 元" if m in o else "—" for m in MODE_ORDER) + " |")
    return "\n".join(rows), "\n".join(trips)


if __name__ == "__main__":
    board = build()
    json.dump(board, open(os.path.join(HERE, "board_cbd_v01.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    zones_table, trips_table = tables(board)
    rings = {}
    types = {}
    for z in board["zones"]:
        rings[z["ring"]] = rings.get(z["ring"], 0) + z["rooms_rule"]
        for k, v in z["rooms_rule_by_type"].items():
            types[k] = types.get(k, 0) + v
    mix = board["work"]["income_mix"]
    doc = DOC.format(zones=zones_table, trips=trips_table, mix=" / ".join(f"{v:.0%}" for v in mix.values()),
                     rings="，".join(f"{k} {v}" for k, v in rings.items()), types="，".join(f"{k} {v}" for k, v in types.items()))
    open(os.path.join(HERE, "board_cbd_v01.md"), "w", encoding="utf-8").write(doc)
    print(mix, rings, types)
