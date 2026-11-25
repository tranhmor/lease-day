"""Fit mode constants to the Beijing survey's mode shares by commute distance. Tenants are drawn as in the game; zones by room count."""
import csv
import json
import math
import os
import random

import numpy as np

import lease_day_v06 as g

KINDS = list(g.ASC)
SURVEY = {"地铁": "subway", "公交车": "bus", "自行车/电动自行车": "bike", "步行": "walk", "私家车": "car", "出租车/网约车": "taxi"}
BANDS = [(0, 5), (5, 10), (10, 20), (20, 999)]


def band(km):
    return next(i for i, (a, b) in enumerate(BANDS) if a <= km < b)


def survey_shares():
    rows = list(csv.DictReader(open(os.path.expanduser("~/Downloads/processed_individual_data.csv"), encoding="utf-8-sig", newline="")))
    table = np.zeros((len(BANDS), len(KINDS)))
    for r in rows:
        if r["mode"] in SURVEY:
            table[band(float(r["commute_dis"])), KINDS.index(SURVEY[r["mode"]])] += 1
    return table / table.sum(axis=1, keepdims=True)


def population(n=20000, seed=1):
    rng = random.Random(seed)
    zones = g.ZONES
    weights = [z["rooms_rule"] for z in zones]
    modes = list(g.CLASS)
    base = np.full((n, len(modes)), np.inf)
    minutes = np.zeros((n, len(modes)))
    taste = np.zeros((n, len(KINDS)))
    bands = np.zeros(n, dtype=int)
    groups = []
    for i in range(n):
        t = g.Tenant(rng, {})
        z = rng.choices(zones, weights=weights)[0]
        bands[i] = band(z["km"])
        groups.append(t.group)
        hourly = 0.5 * t.wage / 260
        for k, kind in enumerate(KINDS):
            taste[i, k] = t.taste[kind]
        for j, m in enumerate(modes):
            o = z["options"].get(m)
            if o is None or (m == "私家车" and not t.car):
                continue
            base[i, j] = (o["min"] + 5 * o.get("transfers", 0)) * 2 * g.WORKDAYS / 60 + o["month"] / hourly
            if g.CLASS[m] in ("bike", "walk"):
                minutes[i, j] = max(0, o["min"] - 30)
    return modes, base, taste, minutes, bands, np.array(groups)


def shares(choice, modes, bands):
    kind_of = np.array([KINDS.index(g.CLASS[m]) for m in modes])
    picked = kind_of[choice]
    out = np.zeros((len(BANDS), len(KINDS)))
    for b in range(len(BANDS)):
        mask = bands == b
        for k in range(len(KINDS)):
            out[b, k] = (picked[mask] == k).mean() if mask.any() else 0
    return out, picked


def fit(modes, base, taste, minutes, bands, scale, tire, target):
    kind_of = np.array([KINDS.index(g.CLASS[m]) for m in modes])
    weights = np.bincount(bands, minlength=len(BANDS)) / len(bands)
    aim = (target * weights[:, None]).sum(axis=0)
    walk = KINDS.index("walk")
    # Survey walkers beyond 5 km are a data quirk and no zone offers it, so walking is fitted to the shortest band only.
    rest = 1 - weights[0] * target[0, walk]
    aim = aim * rest / (1 - aim[walk])
    aim[walk] = weights[0] * target[0, walk]
    asc = np.zeros(len(KINDS))
    tiring = base + minutes * tire * 2 * g.WORKDAYS / 60
    for _ in range(60):
        u = tiring + asc[kind_of] - scale * taste[:, kind_of]
        choice = np.argmin(u, axis=1)
        by_band, picked = shares(choice, modes, bands)
        now = np.array([(picked == k).mean() for k in range(len(KINDS))])
        asc += 6 * np.log(np.maximum(now, 1e-4) / np.maximum(aim, 1e-4))
        asc -= asc[KINDS.index("subway")]
    u = tiring + asc[kind_of] - scale * taste[:, kind_of]
    choice = np.argmin(u, axis=1)
    by_band, picked = shares(choice, modes, bands)
    return asc, by_band, picked, np.abs(by_band - target)[weights > 0].sum()


if __name__ == "__main__":
    target = survey_shares()
    modes, base, taste, minutes, bands, groups = population()
    print("survey by band", KINDS)
    print(np.round(target, 2))
    print("zone weight by band", np.round(np.bincount(bands, minlength=4) / len(bands), 2))
    best = None
    for scale in (20, 30, 40, 50):
        for tire in (0.5, 1, 2):
            asc, by_band, picked, err = fit(modes, base, taste, minutes, bands, scale, tire, target)
            print(f"scale {scale} tire {tire} err {err:.3f}", flush=True)
            if best is None or err < best[0]:
                best = (err, scale, tire, asc, by_band, picked)
    err, scale, tire, asc, by_band, picked = best
    print("best", err, "TASTE_SCALE", scale, "BIKE_TIRE", tire)
    print("ASC", {k: round(float(v), 1) for k, v in zip(KINDS, asc)})
    print(np.round(by_band, 2))
    for grp in ("low", "mid", "high"):
        m = groups == grp
        print(grp, m.mean().round(3), {k: round(float((picked[m] == i).mean()), 2) for i, k in enumerate(KINDS)})
