# CBD and Wangjing compared as the game's job centre

Run 2026-11-01. Listings were read in browser memory from the DRUM files (30–150 m², repeats dropped, 1,711 grid cells of about 500 m with 3+ listings per year). Travel times come from `job_center_network.py` and `center_access.json`: network-only, 45 km/h, 5 min transfer, walking 12 min/km from the cell to the best station. Era filters are hand-written.

| Measure | CBD | Wangjing |
|---|---|---|
| Arrival lines | 1, 6, 10, 14 | 13, 14, 15 |
| Arrival lines within 10 min of best | 3.47 | 2.55 |
| Stations within 60 min | 253 | 231 |
| Cells saving 5+ min, 2015 to 2018 network (2018 listings) | 69 (1,145) | 235 (5,234) |
| Cells saving 10+ min (2018 listings) | 44 (559) | 168 (3,616) |
| Rent change, saved 5+ min vs unchanged at same distance from centre | +5.9% (2.9, 9.1) | +4.1% (1.5, 7.2) |
| Rent change per 10 min saved, controls | -0.6% (-2.3, 1.2) | +0.2% (-1.4, 2.0) |
| Rent per 10 min further from the centre, 2018 | -9.7% (R² 0.41) | -8.0% (R² 0.36) |
| Same, controlling for distance to Tiananmen | -3.4% (R² 0.58) | -4.8% (R² 0.67) |
| R² at 30–75 min, time only and with direction | 0.27 and 0.68 | 0.27 and 0.68 |

Both centres in one model, per 10 min saved: CBD -1.4% (-4.6, 1.2), Wangjing +1.5% (-0.8, 3.4).

## 30–75 min band by direction (2018 listings; median rent per m²; median minutes)
| Direction | CBD | Wangjing |
|---|---|---|
| N | 2,448; 89; 43 | 177; 51; 55 |
| NE | 391; 77; 62 | 737; 55; 52 |
| E | 2,693; 56; 44 | 23; 45; 72 |
| SE | 132; 60; 67 | 3,603; 64; 57 |
| S | 689; 64; 53 | 4,784; 95; 40 |
| SW | 3,778; 77; 50 | 8,777; 105; 53 |
| W | 5,107; 95; 46 | 2,234; 110; 43 |
| NW | 4,468; 100; 49 | 1,439; 79; 38 |

## Time bands (2018 listings; rent per m²; 40–90 m² median monthly rent; affordable share)
| Minutes | CBD | Wangjing |
|---|---|---|
| 0–30 | 13,397; 112; 6,500; 0.9% | 8,325; 111; 6,800; 1.9% |
| 30–45 | 10,025; 100; 6,000; 4.5% | 10,078; 106; 6,500; 2.5% |
| 45–60 | 6,631; 76; 5,000; 15.1% | 7,509; 95; 5,700; 6.4% |
| 60–75 | 3,050; 65; 4,500; 25.3% | 4,187; 72; 4,700; 18.9% |
| 75–90 | 777; 53; 4,000; 54.7% | 3,154; 64; 4,300; 27.6% |
| 90–120 | 890; 48; 3,400; 65.6% | 1,264; 54; 4,000; 51.3% |

## Resident education by sub-district, 2020 census table C6 (aged 3+; read by eye from the image)
| Area | Population | Bachelor or above | Master or above |
|---|---|---|---|
| Beijing | 21,344,070 | 29.3% | 7.0% |
| Chaoyang | 3,371,966 | 36.6% | 8.7% |
| Jianwai, Hujialou, Chaowai (CBD core) | 120,252 | 39.8% | 10.5% |
| Those plus Shuangjing, Tuanjiehu, Maizidian | 273,027 | 42.5% | 10.6% |
| Wangjing, Donghu | 203,603 | 47.9% | 12.1% |
| Laiguangying | 158,845 | 46.9% | 11.5% |
| Cuigezhuang | 104,991 | 22.0% | 3.4% |

These describe residents, not workers, and education is not income. No wage or occupation data by job centre was found.

## Limits
Cell bootstrap ignores spatial correlation, so intervals are too narrow. Treated cells cluster in the east and south-east. Rents respond to all reachable jobs, not one centre. Descriptive only. Listings are formal asking rents.
