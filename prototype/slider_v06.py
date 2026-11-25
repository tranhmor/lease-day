"""Rerun the core experiment with changed settings, for the slider notebook. Rule-only.

Games run through the recorder in viz_v06.py, so rules and random draws are those of scenarios_v06.py: with default settings
and the same seeds the results are the same. Standard library only, so it also runs on Colab as it is.
Usage: python3 slider_v06.py baseline [seeds]; python3 slider_v06.py check
"""
import concurrent.futures as cf
import json
import math
import os
import statistics as st
import sys

import lease_day_v06 as g
import viz_v06 as v

DEFAULTS = {"saving_scale": 1.0, "demand_k": g.DEMAND_K, "low_cost": 1.0, "savings": 1.0, "rent_trend": 0.0, "wage_trend": 0.0, "stayer_share": 0.5}
ARMS = tuple(v.ARMS)
KEEP = ("watch_commute", "commute", "watch_rent", "inq_in", "mode_in_subway", "rev_in", "low_cash", "low_over30", "vac_in", "vac_out", "n", "moves_in", "left", "blocked_low", "moves")
CUMULATIVE = {"cum_in": "moves_in", "cum_left": "left", "cum_blocked": "blocked_low", "cum_moves": "moves"}
CHART = ("watch_commute", "watch_rent", "inq_in", "mode_in_subway", "cum_in")
PERCENT = {"mode_in_subway", "low_over30", "vac_in", "vac_out"}
# key, what to read, label, decimals, tail = average of the window, end = last month
ROWS = (
    ("watch_commute", "direct", "受益区租客通勤，直接效应（分钟）", 1, "tail"),
    ("commute", "direct", "全体通勤，直接效应（分钟）", 2, "tail"),
    ("watch_rent", "interaction", "受益区租金，交互影响（指数点）", 2, "tail"),
    ("watch_rent", "total", "第 60 个月的受益区租金差 C-A（指数点）", 2, "end"),
    ("rev_in", "total", "受益区房东每间月收入，总效应（元）", 0, "tail"),
    ("low_cash", "total", "低收入者月租加通勤费，总效应（元）", 0, "tail"),
    ("cum_in", "total", "累计搬入受益区，总效应（人）", 1, "end"),
    ("low_over30", "C", "低收入者房租超过 30%（%，C 组）", 0, "tail"),
    ("cum_left", "C", "累计离开（人，C 组）", 1, "end"),
    ("cum_blocked", "C", "低收入者累计被挡（次，C 组）", 0, "end"),
    ("vac_in", "C", "受益区空置率（%，C 组）", 1, "tail"),
    ("vac_out", "C", "其他区域空置率（%，C 组）", 1, "tail"),
    ("seated", "C", "开局入住户数（C 组）", 0, "tail"),
)


def play(job):
    arm, seed, settings = job
    policy, shock = v.ARMS[arm]
    game = v.Recorder(policy, seed, shock, watch=v.WATCH, **settings)
    out = game.run()
    series = {k: game.series[k] for k in KEEP}
    for key, base in CUMULATIVE.items():
        total, series[key] = 0, []
        for i, value in enumerate(game.series[base]):
            total += value if i > g.LINE_OPENS else 0
            series[key].append(total)
    series["seated"] = [out["seated"]] * len(series["n"])
    return arm, seed, series


def run(settings, seeds, workers=None, progress=None):
    """All four arms. Parallel where the platform allows it, one by one otherwise."""
    jobs = [(arm, s, settings) for arm in ARMS for s in range(seeds)]
    runs = {arm: [None] * seeds for arm in ARMS}
    workers = workers or min(8, os.cpu_count() or 1)

    def keep(result, done):
        arm, seed, series = result
        runs[arm][seed] = series
        if progress:
            progress(done, len(jobs))

    finished = 0
    if workers > 1:
        try:
            with cf.ProcessPoolExecutor(max_workers=workers) as pool:
                for result in pool.map(play, jobs, chunksize=2):
                    finished += 1
                    keep(result, finished)
            return runs
        except (cf.process.BrokenProcessPool, OSError, RuntimeError):
            runs = {arm: [None] * seeds for arm in ARMS}
            finished = 0
    for job in jobs:
        finished += 1
        keep(play(job), finished)
    return runs


def half(values):
    return 1.96 * st.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0


def mean(values):
    return sum(values) / len(values)


def summarize(runs):
    a, a0, b, c = (runs[arm] for arm in ("A", "A0", "B", "C"))
    seeds = len(a)
    months = len(a[0]["n"])
    window = v.TAIL

    def read(r, key, how, at=None):
        scale = 100 if key in PERCENT else 1
        if at is not None:
            return r[key][at] * scale
        return scale * (r[key][-1] if how == "end" else mean(r[key][-window:]))

    def effect(what, pick):
        if what == "direct":
            return [pick(b[i]) - pick(a0[i]) for i in range(seeds)]
        if what == "total":
            return [pick(c[i]) - pick(a[i]) for i in range(seeds)]
        if what == "interaction":
            return [(pick(c[i]) - pick(a[i])) - (pick(b[i]) - pick(a0[i])) for i in range(seeds)]
        return [pick(r) for r in runs[what]]

    table = []
    for key, what, label, digits, how in ROWS:
        values = effect(what, lambda r, k=key, h=how: read(r, k, h))
        table.append({"key": f"{key}|{what}", "label": label, "digits": digits, "value": round(mean(values), 4), "half": round(half(values), 4)})
    monthly = {key: {arm: {"m": [round(mean([read(r, key, None, i) for r in runs[arm]]), 3) for i in range(months)],
                           "h": [round(half([read(r, key, None, i) for r in runs[arm]]), 3) for i in range(months)]} for arm in ARMS} for key in CHART}
    gap = [effect("total", lambda r, at=i: read(r, "watch_rent", None, at)) for i in range(months)]
    return {"seeds": seeds, "table": table, "monthly": monthly, "gap": {"m": [round(mean(x), 3) for x in gap], "h": [round(half(x), 3) for x in gap]}}


def check():
    """Changed settings must reproduce the earlier assumption tests at the same seed count; those were printed rounded."""
    want = {"low_cost": ({"low_cost": 0.4}, "C", {"seated": 1082, "cum_left": 18.3, "cum_blocked": 271.3}),
            "savings": ({"savings": 0.5}, "C", {"seated": 1054, "cum_left": 4.2, "cum_blocked": 256.4}),
            "saving_scale": ({"saving_scale": 2}, "C", {"seated": 1134, "cum_left": 9.7, "cum_blocked": 217.6}),
            "trend": ({"rent_trend": 0.13, "wage_trend": 0.088}, "A", {"cum_left": 37.6})}
    for name, (change, arm, values) in want.items():
        runs = run({**DEFAULTS, **change}, 30)
        for key, target in values.items():
            got = mean([r[key][-1] for r in runs[arm]])
            print(f"{name:14} {arm} {key:12} got {got:8.1f} earlier {target:8.1f} {'ok' if abs(got - target) < (0.5 if key == 'seated' else 0.15) else 'DIFFERENT'}", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "check":
        check()
    else:
        seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 100
        result = summarize(run(dict(DEFAULTS), seeds))
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis", "slider_baseline.json")
        json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        for row in result["table"]:
            print(f"{row['label']:40} {row['value']:10.3f} +-{row['half']:.3f}")
