// Aggregates the DRUM listings (DOI 10.13020/ejpy-2r93) into analysis/zone_listings.json.
//
// This ran in the browser console on the repository's item page, because direct downloads were blocked:
// https://conservancy.umn.edu/items/29cab34a-f4d7-4ba0-ac9e-bd1bbe7d371e
// It is a record of the method. With the two files saved locally, the same steps can be rewritten in Python.
//
// STATIONS comes from center_access.json, one row per station in sorted name order:
// [round((lat - 39) * 1000), round((lon - 116) * 1000), round(t18), round(t15, or 999 if absent)]

const FILES = { y2015: "4cc48cf1-6701-40ee-8895-ebcd340b1571", y2018: "00d9f237-b540-440b-bffa-8f10aa602e7a" };
const CENTRE = [39.912, 116.456];
const EXCLUDED = /车位|车库|商铺|办公|写字楼|仓库|底商|门面/;
const ROOM = /次卧|主卧|单间|隔断|卧室|室友|床位/;
const km = (a, b, c, d) => Math.hypot((a - c) * 111.2, (b - d) * 85.3);

async function load(id) {
  const buffer = await fetch(`/server/api/core/bitstreams/${id}/content`).then((r) => r.arrayBuffer());
  const text = new TextDecoder("utf-16le").decode(buffer).replace(/^﻿/, "");
  const lines = text.split(/\r?\n/).filter((x) => x.length);
  const sep = lines[0].includes("\t") ? "\t" : ",";
  const head = lines[0].split(sep);
  return lines.slice(1).map((l) => Object.fromEntries(l.split(sep).map((v, i) => [head[i], v])));
}

// Direction index runs N, NE, E, SE, S, SW, W, NW; band index runs 0-30, 30-45, 45-60, 60-75, 75-90, 90+ minutes.
const ZONE = {
  "E|0": 1, "SE|0": 1, "N|0": 2, "NE|0": 2, "S|0": 3, "SW|0": 3, "W|0": 4, "NW|0": 4,
  "E|1": 5, "N|1": 6, "NE|1": 6, "NE|2": 6, "NW|1": 7, "W|1": 8, "SW|1": 9,
  "S|1": 10, "SE|1": 10, "S|2": 10, "SE|2": 10, "E|2": 11, "E|3": 11, "E|4": 11, "E|5": 11,
  "N|2": 12, "NW|2": 13, "W|2": 14, "SW|2": 15, "N|3": 16, "N|4": 16, "N|5": 16,
  "NW|3": 17, "NW|4": 17, "W|3": 18, "W|4": 18, "W|5": 18, "SW|3": 19,
  "S|3": 20, "S|4": 20, "S|5": 20, "SE|3": 20, "SE|4": 20, "SE|5": 20,
  "NE|3": 21, "NE|4": 21, "NE|5": 21, "SW|4": 22, "SW|5": 22, "NW|5": 23,
};

function assign(rows, STATIONS) {
  const seen = new Set();
  const out = [];
  for (const r of rows) {
    const key = [r.residence, r.area, r.rent, r.POINT_X, r.POINT_Y, r.house_type || ""].join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    const a = +r.area, p = +r.rent, la = +r.POINT_Y, lo = +r.POINT_X;
    if (!(a > 0 && p > 0 && la > 39 && lo > 115) || EXCLUDED.test(r.title || "")) continue;
    const isRoom = ROOM.test(r.title || "");
    let type = null;
    if (isRoom && p >= 300 && p <= 6000) type = "room";
    else if (!isRoom && a >= 30 && a <= 150 && p / a >= 10 && p / a <= 500) type = "whole";
    if (!type) continue;
    // Best station within 3 km, walking at 12 minutes per km. Listings with none are dropped.
    let best = 1e9, t15 = 1e9, si = -1, walk = 0;
    STATIONS.forEach((s, i) => {
      const d = km(la, lo, 39 + s[0] / 1000, 116 + s[1] / 1000);
      if (d > 3) return;
      const t = s[2] + 12 * d;
      if (t < best) { best = t; si = i; walk = 12 * d; }
      if (s[3] < 999 && s[3] + 12 * d < t15) t15 = s[3] + 12 * d;
    });
    if (si < 0) continue;
    const dist = km(la, lo, CENTRE[0], CENTRE[1]);
    const angle = (Math.atan2((lo - CENTRE[1]) * 85.3, (la - CENTRE[0]) * 111.2) * 180 / Math.PI + 360) % 360;
    const dir = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.floor((angle + 22.5) / 45) % 8];
    const band = best < 30 ? 0 : best < 45 ? 1 : best < 60 ? 2 : best < 75 ? 3 : best < 90 ? 4 : 5;
    // Z00 is everything within 2.5 km of the centre, taken out of the other zones.
    const z = dist <= 2.5 ? 0 : ZONE[`${dir}|${band}`];
    if (z === undefined) continue;
    out.push({ z, type, a, p, la, lo, t: best, t15, walk, si, dist, comm: r.commercial, d: r.district });
  }
  return out;
}

const q = (arr, f) => {
  if (!arr.length) return null;
  const s = [...arr].sort((x, y) => x - y);
  return s[Math.min(s.length - 1, Math.floor(s.length * f))];
};

// A blank 2018 district is filled with the most common district of the listing's business area.
function fillDistricts(listings) {
  const counts = {};
  for (const x of listings) if (x.comm && x.d) { (counts[x.comm] ||= {})[x.d] = (counts[x.comm][x.d] || 0) + 1; }
  const pick = Object.fromEntries(Object.entries(counts).map(([c, m]) => [c, Object.entries(m).sort((a, b) => b[1] - a[1])[0][0]]));
  for (const x of listings) x.dd = x.d || pick[x.comm] || null;
}

function summarise(z, y18, y15) {
  const v = y18.filter((x) => x.z === z), u = y15.filter((x) => x.z === z);
  const whole = (a) => a.filter((x) => x.type === "whole");
  const mid = (a) => whole(a).filter((x) => x.a >= 40 && x.a <= 90).map((x) => x.p);
  const rooms = v.filter((x) => x.type === "room").map((x) => x.p);
  return {
    z, n: v.length, nw: whole(v).length, nr: rooms.length, n15: u.length,
    w: [0.25, 0.5, 0.75].map((f) => q(mid(v), f)),
    r: [0.1, 0.25, 0.5, 0.75].map((f) => q(rooms, f)),
    w15: [0.25, 0.5, 0.75].map((f) => q(mid(u), f)),
    psm: Math.round(q(whole(v).map((x) => x.p / x.a), 0.5)),
    psm15: Math.round(q(whole(u).map((x) => x.p / x.a), 0.5)),
    t: Math.round(q(v.map((x) => x.t), 0.5)),
    sv5: Math.round((100 * v.filter((x) => x.t15 - x.t >= 5).length) / v.length),
    wk: Math.round(q(v.map((x) => x.walk), 0.5)),
    km: +q(v.map((x) => x.dist), 0.5).toFixed(1),
    lat: +(v.reduce((s, x) => s + x.la, 0) / v.length).toFixed(4),
    lon: +(v.reduce((s, x) => s + x.lo, 0) / v.length).toFixed(4),
  };
}

async function main(STATIONS) {
  const y18 = assign(await load(FILES.y2018), STATIONS);
  const y15 = assign(await load(FILES.y2015), STATIONS);
  fillDistricts(y18);
  return Array.from({ length: 24 }, (_, z) => summarise(z, y18, y15));
}
