"""Build lease_day_v06_visuals.ipynb: the experiment and its results as one notebook, data included, for sending to the partner.

Reads the row files in analysis/viz_dash/ (from viz_build.py). Needs nbformat. Run the result with nbclient to save its outputs.
"""
import base64
import gzip
import json
import os
import textwrap

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.join(HERE, "viz_dash")
OUT = os.path.join(HERE, "..", "lease_day_v06_visuals.ipynb")
NAMES = ["levels", "effects", "monthly", "effect_by_month", "zones", "ledger", "assumptions", "landlord_rules", "real_vs_rule", "baseline", "map", "metro", "replay_rooms", "replay", "replay_people"]
data = {n: json.load(open(os.path.join(DASH, n + ".json"), encoding="utf-8")) for n in NAMES}
packed = base64.b64encode(gzip.compress(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)).decode()
print("embedded data", len(packed) // 1024, "KB")
template = open(os.path.join(DASH, "page", "replay_notebook.html"), encoding="utf-8").read()
assert "'''" not in template

L = {r["key"]: r["value"] for r in data["levels"]}
E = {(r["metric"], r["effect"]): r for r in data["effects"]}
e = lambda m, k, d=None: f"{abs(E[(m, k)]['value']):.{E[(m, k)]['digits'] if d is None else d}f}"
H = lambda m, k: f"{E[(m, k)]['half']}"
led = {r["row"]: r for r in data["ledger"]}
months = [r for r in data["monthly"] if r["metric"] == "cum_in" and r["month"] == 60]
cum = {r["arm"]: r["mean"] for r in months}


def code(source, hidden=False):
    cell = new_code_cell(source.strip("\n"))
    if hidden:
        cell.metadata["cellView"] = "form"
        cell.metadata["jupyter"] = {"source_hidden": True}
    return cell


def md(source):
    return new_markdown_cell(textwrap.dedent(source).strip("\n"))


cells = [
    md(f"""
    # 《到期日》实验可视化

    新线开通后，受益区租客通勤少 **{e('watch_commute', 'direct')} 分钟**，但他们只占全部租客的 {L['share_in']}%。这些区域本来就住满了，几乎没人能迁入；统计窗口内，受益区租金只比没有新线时多涨 **{e('watch_rent', 'interaction')} 个指数点**。

    规则版，没有 LLM，四组各 {L['seeds']} 局，同一编号的随机种子配对。这些数字用来检查设计，不代表北京的真实情况。

    **怎么用：** 图已经保存在文件里，打开就能看。数据也在文件里，从上到下运行不需要其他文件，只需要 matplotlib、numpy 和 pandas，Colab 自带。
    """),
    code("""
#@title 准备：载入工具和中文字体
import base64, gzip, json, os, subprocess, sys, uuid

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import HTML, display
from matplotlib import font_manager, patheffects
from matplotlib.colors import LinearSegmentedColormap

CJK = ["PingFang SC", "Hiragino Sans GB", "Heiti TC", "STHeiti", "Arial Unicode MS", "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Noto Sans CJK JP", "WenQuanYi Micro Hei"]
installed = {f.name for f in font_manager.fontManager.ttflist}
if "google.colab" in sys.modules and not installed & set(CJK):
    subprocess.run(["apt-get", "-qq", "install", "-y", "fonts-noto-cjk"], capture_output=True)
    path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
    if os.path.exists(path):
        font_manager.fontManager.addfont(path)
        installed = {f.name for f in font_manager.fontManager.ttflist}
found = [f for f in CJK if f in installed]
if not found:
    print("没有找到中文字体，图里的中文会显示成方块。安装任意一种中文字体后重新运行。")
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": found + ["DejaVu Sans"], "axes.unicode_minus": False, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#9a9ea4", "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.labelsize": 9, "xtick.labelsize": 9, "ytick.labelsize": 9,
                     "xtick.color": "#6b6f76", "ytick.color": "#6b6f76", "figure.dpi": 110, "savefig.dpi": 110})
ORANGE, GREY, BLUE, INK, MUTED = "#d95926", "#6b6f76", "#2a78d6", "#1b1f24", "#b4b8bd"
"""),
    code(f'''
#@title 数据（已放在文件里，不用下载）
DATA_PACKED = """
{chr(10).join(textwrap.wrap(packed, 160))}
"""
DATA = json.loads(gzip.decompress(base64.b64decode(DATA_PACKED)))
''', hidden=True),
    code("""
#@title 画图用的小工具
monthly = pd.DataFrame(DATA["monthly"])
by_month = pd.DataFrame(DATA["effect_by_month"])
effects = pd.DataFrame(DATA["effects"])
zones = pd.DataFrame(DATA["zones"])
ledger = pd.DataFrame(DATA["ledger"])
assumptions = pd.DataFrame(DATA["assumptions"])
rules = pd.DataFrame(DATA["landlord_rules"])
real_vs_rule = pd.DataFrame(DATA["real_vs_rule"])
baseline = pd.DataFrame(DATA["baseline"])
LEVEL = {row["key"]: row["value"] for row in DATA["levels"]}
OPENS, MONTHS, TAIL = LEVEL["opens"], LEVEL["months"], LEVEL["tail"]

# 两个因素，两种画法：有新线用橙色，没有新线用灰色；租金冻结用虚线，租金变化用实线
ARMS = {"A": dict(color=GREY, ls="-", label="A 没有新线，租金变化"), "A0": dict(color=GREY, ls="--", label="A0 没有新线，租金冻结"),
        "C": dict(color=ORANGE, ls="-", label="C 新线，租金变化"), "B": dict(color=ORANGE, ls="--", label="B 新线，租金冻结")}

def mark_time(ax):
    # 竖线是开通，阴影是统计窗口
    ax.axvline(OPENS - 0.5, color="#9a9ea4", lw=1)
    ax.axvspan(MONTHS - TAIL, MONTHS, color="#eceef0", lw=0, zorder=0)
    ax.set_xlim(0, MONTHS)
    ax.set_xticks([12, 24, 36, 48, 60])
    ax.grid(axis="y", color="#eceef0", lw=1)
    ax.set_axisbelow(True)

def whisker(ax, x, lo, hi, y, color, size=5, lw=1.6, **kw):
    ax.plot([lo, hi], [y, y], color=color, lw=lw, solid_capstyle="round", zorder=3, **kw)
    ax.plot([x], [y], "o", color=color, ms=size, zorder=4)

def sign(v, d=1):
    return "0" if abs(v) < 0.5 * 10 ** -d else f"{v:+,.{d}f}"
""", hidden=True),
    md(f"""
    ## 实验设计：两个因素，四组

    所有租客都在 CBD 上班，{L['rooms']:,} 间房分布在 {L['zones']} 个住房区域。每回合一个月，共 {L['months']} 个月。第 {L['opens']} 个月，假想的东向快线开通，果园和武夷花园的地铁通勤变短；冻结组的租金从这个月起不再变化。结果取最后 {L['tail']} 个月的平均。

    | | 租金正常变化 | 租金冻结 |
    |---|---|---|
    | **没有新线** | A：基线 | A0：对照，用来扣除冻结本身 |
    | **有新线** | C：新线，租金变化 | B：新线，租金不变 |

    - **直接效应 = B − A0：** 租金不动时，新线带来多少
    - **总效应 = C − A：** 租金能动时，新线带来多少
    - **交互影响 = 总效应 − 直接效应：** 租金反应把结果改变了多少
    """),
    code("""
fig, ax = plt.subplots(figsize=(10, 1.15))
ax.barh(0, MONTHS, height=0.35, color="#e1e3e6")
ax.barh(0, TAIL, left=MONTHS - TAIL, height=0.35, color=ORANGE)
ax.plot([OPENS - 0.5] * 2, [-0.3, 0.3], color=INK, lw=2)
ax.text(OPENS - 0.5, 0.42, f"第 {OPENS} 月：新线开通，冻结开始", ha="center", fontsize=10)
ax.text(0, -0.62, "第 1 月", fontsize=9, color=GREY)
ax.text(MONTHS, -0.62, f"第 {MONTHS - TAIL + 1}–{MONTHS} 月：统计窗口", ha="right", fontsize=9, color=GREY)
ax.set_xlim(0, MONTHS); ax.set_ylim(-0.75, 0.75); ax.axis("off")
plt.show()
"""),
    md(f"""
    ## 回放一局：每个点是一间房

    实心点是有人住的房间，空心点是空房。这是编号 {L['replay_seed']} 的一局，不是平均值；四组用同一个种子，所以开通前完全相同，之后才分开。

    按“播放”看租客怎样搬家，切换分组时月份不变。在 notebook 里，如果下面没有出现地图，从上到下运行一次（Run All）。

    地铁线是 2018 年路网（OpenStreetMap）。区域按真实方向摆放，为了放下所有点，靠近中心的区域向外移开，最多约 {L['max_shift_km']} 公里。东向快线只是示意，没有真实走向。
    """),
    code(f"""
#@title 回放的网页代码
REPLAY_PAGE = r'''
{template}
'''
""", hidden=True),
    code("""
def show_replay():
    rows_by_arm = {arm: [] for arm in ARMS}
    for row in sorted(DATA["replay"], key=lambda r: r["month"]):
        rows_by_arm[row["arm"]].append({"rooms": row["rooms"], "events": row["events"], "renew": row["renew"]})
    people = {row["arm"]: row["people"] for row in DATA["replay_people"]}
    size = DATA["map"][0]
    payload = {
        "width": size["width"], "height": size["height"], "cbd": [size["cbd_x"], size["cbd_y"]], "opens": OPENS, "last": MONTHS, "metro": [line["points"] for line in DATA["metro"]],
        "zones": [{"id": z["zone"], "name": z["name"], "x": z["x"], "y": z["y"], "r": z["r"], "lx": z["lx"], "ly": z["ly"], "major": z["major"], "treated": z["treated"], "rooms": z["rooms"]} for z in DATA["zones"]],
        "rooms": [{"zone": r["zone"], "start": r["start"], "x": r["x"], "y": r["y"]} for r in DATA["replay_rooms"]],
        "arms": {arm: {"rows": rows_by_arm[arm], "people": people[arm]} for arm in ARMS},
    }
    uid = "ld" + uuid.uuid4().hex[:10]
    display(HTML(REPLAY_PAGE.replace("__UID__", uid).replace("__DATA__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))))

show_replay()
"""),
    md("""
    同一局的三个时刻（C 组）。开通后两个受益区颜色马上变浅，也就是通勤变短；空心点几乎都在西北、北部和金融街一带。
    """),
    code("""
def room_state(arm, month):
    n = len(DATA["replay_rooms"])
    who, minutes = np.full(n, -1), np.zeros(n)
    for row in sorted(DATA["replay"], key=lambda r: r["month"]):
        if row["arm"] == arm and row["month"] <= month:
            for i, tenant, _, _, mins in row["rooms"]:
                who[i], minutes[i] = tenant, mins
    return who, minutes

cmap = LinearSegmentedColormap.from_list("commute", ["#b7d3f6", "#0d366b"])
halo = [patheffects.withStroke(linewidth=2.5, foreground="white")]
xs = np.array([r["x"] for r in DATA["replay_rooms"]])
ys = np.array([r["y"] for r in DATA["replay_rooms"]])
fig, axes = plt.subplots(1, 3, figsize=(13, 4.9))
for ax, month, title in zip(axes, [OPENS - 1, OPENS, MONTHS], [f"第 {OPENS - 1} 个月：开通前", f"第 {OPENS} 个月：开通", f"第 {MONTHS} 个月"]):
    who, minutes = room_state("C", month)
    for line in DATA["metro"]:
        pts = np.array(line["points"])
        ax.plot(pts[:, 0], pts[:, 1], color="#d5d8dc", lw=0.6, zorder=1)
    occupied = who >= 0
    dots = ax.scatter(xs[occupied], ys[occupied], c=minutes[occupied], cmap=cmap, vmin=20, vmax=110, s=5, linewidths=0, zorder=3)
    ax.scatter(xs[~occupied], ys[~occupied], facecolors="none", edgecolors=GREY, s=5, linewidths=0.5, zorder=3)
    for z in DATA["zones"]:
        if z["treated"]:
            ax.add_patch(plt.Circle((z["x"], z["y"]), z["r"], fill=False, color=ORANGE, lw=1.4, zorder=4))
        if z["treated"]:
            below = z["name"] == "果园"  # the two treated zones sit side by side, so their names go on opposite sides
            ax.text(z["x"], z["y"] + (z["r"] + 34) * (1 if below else -1), z["name"], fontsize=8, ha="center", va="center", color=INK, zorder=5, path_effects=halo)
        elif z["major"]:
            ax.text(z["lx"], z["ly"], z["name"], fontsize=7.5, ha="center", va="center", color=GREY, zorder=5, path_effects=halo)
    size = DATA["map"][0]
    ax.plot([size["cbd_x"]], [size["cbd_y"]], "D", color=INK, ms=4, zorder=6)
    ax.set_xlim(0, size["width"]); ax.set_ylim(size["height"], 0); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title(title, loc="left")
fig.colorbar(dots, ax=axes, shrink=0.55, pad=0.01, label="单程通勤（分钟）")
plt.show()
"""),
    md(f"""
    ## 逐月结果：通勤马上变，租金慢慢变

    四组各 {L['seeds']} 局的平均，浅色带是 A、C 两组的 95% 区间。竖线是开通，右侧阴影是统计窗口。

    - **通勤：** 开通当月少 {L['commute_jump']} 分钟，之后没有继续下降。
    - **租金：** 开通前就在涨，到统计窗口已涨 {L['drift_rent_A']} 点（A 组），这部分和新线无关。
    - **租金差：** 第 48 个月 {L['rent_gap_48']:.2f}，第 60 个月 {L['rent_gap_60']:.2f}，到最后还在扩大。统计窗口的平均值 {e('watch_rent', 'interaction')} 没有反映这个趋势。
    - **询盘：** 开通后 12 个月，有新线比没有新线只多 {L['inq_gain']}%。冻结组不统计询盘，所以只画两组。
    - **地铁占比：** 新线后有人改坐地铁；但 A 组没有新线，也从 {L['subway_start']}% 降到 {L['subway_end']}%，基线本身在漂移。
    - **搬入：** 开通后累计搬入受益区 {cum['C']:.1f} 人，没有新线时 {cum['A']:.1f} 人。可能是因为住在里面的人更少搬走，空出的房更少。
    """),
    code("""
PANELS = [("watch_commute", "通勤在开通当月就下降", "受益区租客平均通勤（分钟）", ["A0", "B", "A", "C"]),
          ("watch_rent", "租金差慢慢拉开", "受益区租金指数（起点 = 100）", ["A0", "B", "A", "C"]),
          ("gap", "到最后一个月，租金差还在扩大", "C - A 的受益区租金指数差，95% 区间", None),
          ("inq_in", "房东看到的询盘只多了一点", "受益区每间房每月询盘", ["A", "C"]),
          ("mode_in_subway", "有人改坐地铁，但基线本身在漂移", "受益区坐地铁的占比（%，含骑车接地铁）", ["A0", "B", "A", "C"]),
          ("cum_in", "搬入受益区的人没有变多，反而略少", "开通后累计搬入受益区（人）", ["A0", "B", "A", "C"])]

fig, axes = plt.subplots(2, 3, figsize=(13, 7))
for ax, (metric, title, note, arms) in zip(axes.flat, PANELS):
    mark_time(ax)
    ax.set_title(title + "\\n", loc="left")
    ax.text(0, 1.02, note, transform=ax.transAxes, fontsize=9, color=GREY)
    if metric == "gap":
        d = by_month[(by_month.metric == "watch_rent") & (by_month.effect == "total") & (by_month.month >= OPENS)].sort_values("month")
        ax.fill_between(d.month, d.value - d.half, d.value + d.half, color=ORANGE, alpha=0.14, lw=0)
        ax.plot(d.month, d.value, color=ORANGE, lw=2)
        ax.axhline(0, color="#9a9ea4", lw=1)
        ax.annotate(sign(d.value.iloc[-1], 2), (MONTHS, d.value.iloc[-1]), xytext=(4, 0), textcoords="offset points", fontsize=9, va="center", annotation_clip=False)
        continue
    for arm in arms:
        d = monthly[(monthly.metric == metric) & (monthly.arm == arm)].sort_values("month")
        if metric == "inq_in":
            d = d[d.month > 0]
        style = ARMS[arm]
        if arm in ("A", "C"):
            ax.fill_between(d.month, d["mean"] - d.half, d["mean"] + d.half, color=style["color"], alpha=0.1, lw=0)
        ax.plot(d.month, d["mean"], color=style["color"], ls=style["ls"], lw=2 if style["ls"] == "-" else 1.6, label=style["label"])
handles = [plt.Line2D([], [], color=ARMS[a]["color"], ls=ARMS[a]["ls"], lw=2, label=ARMS[a]["label"]) for a in ARMS]
fig.legend(handles=handles, loc="upper center", ncol=4, frameon=False, fontsize=10, bbox_to_anchor=(0.5, 1.03))
fig.supxlabel("月份", fontsize=9, color=GREY)
fig.tight_layout(rect=(0, 0, 1, 0.98))
plt.show()
"""),
    md("""
    ## 效应分解

    点是平均值，线段是 95% 区间，竖线是零。每行有自己的刻度，只看区间是否离开零；深色表示区间不含零。“累计”是开通后到第 60 个月的总数，其余是统计窗口的平均。
    """),
    code("""
ROWS = [("watch_commute", "受益区租客通勤（分钟）"), ("commute", "全体通勤（分钟）"), ("low_commute", "低收入者通勤（分钟）"), ("mode_in_subway", "受益区地铁占比（百分点）"),
        ("watch_rent", "受益区租金指数（点）"), ("other_rent", "其他区域租金指数（点）"), ("rev_in", "受益区房东每间月收入（元）"), ("low_cash", "低收入者月租加通勤费（元）"),
        ("cum_in", "累计搬入受益区（人）"), ("cum_moves", "累计搬家（次）"), ("cum_left", "累计离开（人）"), ("cum_blocked", "低收入者累计被挡（次）")]
COLUMNS = [("direct", "直接效应 B - A0"), ("total", "总效应 C - A"), ("interaction", "交互影响")]

fig, ax = plt.subplots(figsize=(13, 5.2))
ax.set_xlim(-0.05, 4.05); ax.set_ylim(len(ROWS) - 0.4, -1); ax.axis("off")
for j, (_, head) in enumerate(COLUMNS):
    ax.text(1.05 + j, -0.75, head, fontsize=10, color=GREY)
for i, (metric, label) in enumerate(ROWS):
    ax.text(0, i, label, fontsize=10, va="center")
    ax.plot([0, 4], [i + 0.5, i + 0.5], color="#eceef0", lw=1)
    rows = effects[effects.metric == metric].set_index("effect")
    scale = (rows.value.abs() + rows.half).max() * 1.05 or 1
    for j, (effect, _) in enumerate(COLUMNS):
        r = rows.loc[effect]
        digits = int(r.digits)
        ax.text(1.05 + j, i, f"{sign(r.value, digits)}" + (f" ±{r.half:g}" if r.half > 0 else ""), fontsize=9.5, va="center")
        centre, width = 1.72 + j, 0.24
        ax.plot([centre, centre], [i - 0.32, i + 0.32], color="#9a9ea4", lw=1)
        clear = abs(r.value) > r.half and r.half > 0
        whisker(ax, centre + r.value / scale * width, centre + (r.value - r.half) / scale * width, centre + (r.value + r.half) / scale * width, i, INK if clear else MUTED)
plt.show()
"""),
    md(f"""
    ## 好处和代价分给了谁

    受益区里，低收入者省的时间最多（{led['low_in']['commute']} 分钟）。房东每间房的月收入小幅增加（{led['rev_in']['rent']:+d} 元），其他区域的人和房东几乎不受影响。这是统计窗口内各组住户的平均，住户在换，不是跟踪同一批人。
    """),
    code("""
def pair(v, h, d):
    return "" if pd.isna(v) else f"{sign(v, d)} ±{h:.{d}f}"

def tenant_table(where):
    rows = ledger[(ledger["where"] == where) & ledger.n.notna()]
    return pd.DataFrame({"谁": rows.who, "人数（C 组）": rows.n.astype(int), "通勤（B − A0，分钟）": [pair(a, b, 1) for a, b in zip(rows.commute, rows.commute_h)],
                         "月租（C − A，元）": [pair(a, b, 0) for a, b in zip(rows.rent, rows.rent_h)], "通勤费（B − A0，元）": [pair(a, b, 0) for a, b in zip(rows.fare, rows.fare_h)]}).set_index("谁")

print("受益区的租客"); display(tenant_table("受益区"))
print("其他区域的租客"); display(tenant_table("其他区域"))
owners = ledger[ledger.n.isna()]
print("房东"); display(pd.DataFrame({"区域": owners["where"], "每间房月收入（C − A，元）": [pair(a, b, 0) for a, b in zip(owners.rent, owners.rent_h)]}).set_index("区域"))
"""),
    md(f"""
    ## 分区结果：只有两个受益区明显变化

    周边区域没有明显的外溢。空置率很低也不是受益区独有的：{L['vac_low_zones']} 个区域低于 5%，高空置集中在 {L['vac_high_zones']} 个区域，最高 {L['vac_max']}%；扣掉这些区域，其他区域约 {L['vac_rest']}%。所以受益区 {L['vac_in']}% 与其他区域 {L['vac_out']}% 的对比，主要反映少数区域空置很高。

    按地铁门到门时间从近到远排列。空置率来自 A 组统计窗口；租金差是 C − A，通勤差是 B − A0。
    """),
    code("""
z = zones.sort_values("subway").reset_index(drop=True)
y = np.arange(len(z))
fig, axes = plt.subplots(1, 3, figsize=(13, 7), sharey=True, gridspec_kw={"wspace": 0.08})
colors = [ORANGE if t else MUTED for t in z.treated]
for ax in axes:
    for i in y[z.treated]:
        ax.axhspan(i - 0.5, i + 0.5, color="#f6efe9", lw=0, zorder=0)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
axes[0].barh(y, z.vac, color=colors, height=0.55)
for i, v in zip(y, z.vac):
    axes[0].text(v + 0.3, i, f"{v:.1f}", va="center", fontsize=8.5, color=GREY)
axes[0].set_title("空置率（%）")
axes[0].set_yticks(y, [f"{n} {m} 分" for n, m in zip(z.name, z.subway)], fontsize=9.5)
axes[0].set_ylim(len(z) - 0.5, -0.5)
for ax, value, half, title in ((axes[1], "rent", "rent_h", "租金差（指数点）"), (axes[2], "commute", "commute_h", "通勤差（分钟）")):
    ax.axvline(0, color="#9a9ea4", lw=1)
    for i, r in z.iterrows():
        whisker(ax, r[value], r[value] - r[half], r[value] + r[half], i, ORANGE if r.treated else MUTED)
    ax.set_title(title)
plt.show()
"""),
    md("""
    ## 和真实数据、其他假设对照

    **左图：** 新线的租金差。真实线路的点估计有正有负，多数区间包含零；规则版的估计落在 14、16 号线的区间内。两边窗口和口径不同，只比量级，真实值也只是描述性比较。

    **右图：** 改假设后，受益区的租金差（C − A，早先的假设检验，局数较少）。
    """),
    code("""
fig, (left, right) = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"wspace": 0.42})
rows = real_vs_rule.iloc[::-1].reset_index(drop=True)
for i, r in rows.iterrows():
    rule = r.group.startswith("规则")
    whisker(left, r.value, r.lo, r.hi, i, ORANGE if rule else BLUE)
left.axvline(0, color="#9a9ea4", lw=1)
left.set_yticks(rows.index, rows.label)
left.set_title("真实挂牌（蓝，%）与规则版（橙，指数点）")
left.grid(axis="x", color="#eceef0"); left.set_axisbelow(True)
rows = assumptions.iloc[::-1].reset_index(drop=True)
for i, r in rows.iterrows():
    whisker(right, r.premium, r.premium - r.premium_h, r.premium + r.premium_h, i, ORANGE if r.variant == "base" else GREY)
right.axvline(0, color="#9a9ea4", lw=1)
right.set_yticks(rows.index, rows.label)
right.set_title("改假设后的受益区租金差")
right.grid(axis="x", color="#eceef0"); right.set_axisbelow(True)
plt.show()
"""),
    md("""
    **低价房减少的影响比新线大得多。** 低价房和便宜单间一起减少，来自同一组假设检验。
    """),
    code("""
low = assumptions[assumptions.variant.isin(["base", "low-cost rooms -30%", "low-cost rooms -60%"])]
display(pd.DataFrame({"低价房": ["现状", "减少 30%", "减少 60%"], "入住户数": low.seated.values, "低收入者房租超 30%（%）": low.low_over30.values, "在住者离开（人）": low.left.values, "低收入新来者被挡（次）": low.blocked_low.values}).set_index("低价房"))
"""),
    md("""
    **房东的定价规则改变租金差。** 交互影响（指数点）。询盘强度是假设，没有按真实溢价调参。
    """),
    code("""
display(pd.DataFrame({"房东规则": rules.label, "假想快线": [f"{a:+.2f} ±{b:.2f}" for a, b in zip(rules.express, rules.express_h)], "真实路网回放": [f"{a:+.2f} ±{b:.2f}" for a, b in zip(rules.replay, rules.replay_h)]}).set_index("房东规则"))
"""),
    md("""
    **基线和现实比较。** A 组，统计窗口。局数比早先的基线多，数字略有差别。上班方式已用北京调查校准，这里的比较不算完全独立。
    """),
    code("""
display(baseline.rename(columns={"metric": "指标", "model": "模型", "real": "现实"}).set_index("指标"))
"""),
]
nb = new_notebook(cells=cells, metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}, "colab": {"provenance": []}})
nbformat.validate(nb)
nbformat.write(nb, OUT)
print("wrote", os.path.relpath(OUT, HERE), os.path.getsize(OUT) // 1024, "KB")
