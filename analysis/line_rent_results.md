# New-line rent test, Beijing listings 2015 and 2018

Run 2026-11-01 in browser memory on the DRUM files (DOI 10.13020/ejpy-2r93, CC0). The browser pane aborted the file downloads, so `rental_game/data/` is empty. Station coordinates are in `stations.json`, from OpenStreetMap (ODbL). Opening dates: Line 14 middle and Changping Line phase 2, 2015-12-26 (China News); Line 16 north, 2016-12-31; S1, Xijiao and Yanfang, 2017-12-30 (Beijing News). The 2014 group's date is from reports for Lines 7 and 14 east, and from memory for Line 6.

## Reproduction
- 2015: 68,732 rows. 2018: 48,923 rows. Readme says the same; the paper says 68,733 and 48,925.
- Raw mean rent per m²: 72.59 to 105.65, +45.55%. Affordable share: 24.09% to 10.69%. Both match the paper.
- 2018 has 27,387 unique ids but 47,488 unique rows on complex, area, rent, coordinates and house type, so the ids look reused or truncated. 2015 has 60,700 unique rows on the same fields without house type.
- Some 2018 update dates are blank (16,578) or later than the stated collection window.

## Method
- Clean: drop repeats, keep 10–500 yuan per m². Main sample: whole-unit proxy of 30–150 m².
- Per year, regress log rent per m² on log area and use the area-adjusted value.
- Grid about 500 m; cells need at least 3 listings in each year. Weight by the smaller count.
- Treated: cell within 1 km of a new station. Control: cell over 1.5 km from any new station, within 4 km of the treated group's mean distance to the centre. Ring control: 1.5–5 km from the line.
- Cell bootstrap, 1,000 draws. Differences are percent changes from the log difference.

## Main result (30–150 m², 1 km, same-distance control)
| Line | Cells | Listings 2015 / 2018 | Change | Control | Difference (95%) |
|---|---|---|---|---|---|
| Line 16 north | 10 | 145 / 60 | +58.2% | +49.6% | +5.8% (-4.8, 13.7) |
| Line 14 middle | 46 | 1,740 / 1,227 | +43.0% | +39.8% | +2.3% (-1.5, 6.7) |
| Changping Line phase 2 | 8 | 68 / 67 | +62.1% | +62.2% | 0.0% (-16.6, 11.8) |
| Opened late 2014 | 145 | 5,264 / 4,527 | +37.9% | +39.7% | -1.3% (-3.6, 1.0) |
| Opened late 2017 | 9 | 146 / 122 | +51.3% | +56.5% | -3.4% (-6.9, 0.0) |

## Other specifications, same-distance control
- All sizes, 1 km: Line 16 +2.3% (-4.5, 9.4); Line 14 +2.9% (-0.8, 7.4).
- 40–120 m², cells with 5+ listings, 1 km: Line 16 +9.9% (1.3, 16.9), only 4 cells; Line 14 +2.5% (-1.5, 6.5).
- 30–150 m², 0.8 km: Line 16 +4.0% (-8.2, 11.6); Line 14 +4.1% (-0.5, 9.5).
- 30–150 m², 1.5 km: Line 16 +7.0% (-1.8, 14.0); Line 14 +2.2% (-0.6, 5.5).
- Ring control, 30–150 m², 1 km: Line 16 +8.6% (-2.5, 17.2); Line 14 +3.8% (-0.6, 8.1). Changping's ring has only 3 cells and is not usable.

## Distance from the line (30–150 m²)
- Line 16: 0–0.8 km +56.0%; 0.8–1.5 km +73.4% (3 cells); 1.5–3 km +55.0%; 3–5 km +44.8%; 5–8 km +45.0%.
- Line 14: 0–0.8 km +45.4%; 0.8–1.5 km +41.2%; 1.5–3 km +38.9%; 3–5 km +36.9%; 5–8 km +44.7%.

## Distance from the city centre (30–150 m²; 1,711 cells; city +44.1%)
0–5 km +38.6%; 5–10 km +40.1%; 10–15 km +42.2%; 15–20 km +48.7%; 20–30 km +61.2%; 30–60 km +58.2%.

## Corridor, 40–90 m², median monthly rent (zones approximate, 3–4 km radius)
| Zone | 2015 | 2018 | Listings 2015 / 2018 |
|---|---|---|---|
| Zhongguancun | 5,400 | 7,500 | 1,042 / 718 |
| Shangdi | 3,800 | 5,500 | 557 / 356 |
| Huilongguan | 3,500 | 5,300 | 735 / 538 |
| Shahe | 2,300 | 4,000 | 36 / 33 |
| Changping town | 2,300 | 3,300 | 173 / 147 |

## Limits
Two periods only, so no pre-trend test. Lines were known before opening. Listings are asking rents for formal stock, not contracts. The stations with new access are a hand-built set. These are descriptive comparisons, not causal estimates. Units under 30 m² rose from 4.9% to 13.4% of listings, so raw unit-rent growth is overstated.
