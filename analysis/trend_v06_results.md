# Rent and wage trends, Lease Day v0.6

Generated from `trend_v06_output.txt`, made by `prototype/trend_v06.py`. Rule agents, no LLM, inquiries on (k = 0.2), payment terms by room type, 30 paired seeds, no new line unless marked, last 12 months of 60.

Trend inputs: area-adjusted rent +44.1% from 2015 to 2018 (+13% a year; `line_rent_results.md`) and income +28.69% (+8.8% a year; Wang & Goetz). Income 2018 to 2020: 62,361 to 69,434 yuan, +11.3%. These are citywide per-capita incomes, not wages by group, and the 2015–18 pace is carried across all 60 months.

| Scenario | End tenants | Vacancy | Commute | Rent share | Low-income over 30% | Left, total (low / mid / high) | Blocked, low / mid / high | Moves | Z05+Z11 rent, east express |
|---|---|---|---|---|---|---|---|---|---|
| base, no trend | 1,118 | 6.9% | 48.5 | 21.9% | 20% | 9.5 (7.0 / 2.4 / 0.1) | 226 / 64 / 1 | 515 | +1.09% ±0.46 |
| wages back to 2018 level | 1,082 | 9.8% | 49.1 | 22.8% | 24% | 11.0 (6.9 / 4.1 / 0.0) | 262 / 76 / 1 | 492 | +0.84% ±0.49 |
| rent +5%, wage +5% | 1,114 | 7.2% | 47.6 | 21.3% | 16% | 10.0 (7.3 / 2.5 / 0.2) | 216 / 61 / 0 | 484 | +1.13% ±0.62 |
| rent +5%, wage 0 | 1,070 | 10.8% | 48.4 | 23.6% | 30% | 46.6 (29.2 / 16.3 / 1.1) | 302 / 107 / 2 | 637 | +1.07% ±0.46 |
| rent +13%, wage +8.8% (2015-18) | 1,082 | 9.9% | 47.2 | 22.0% | 21% | 37.6 (23.1 / 13.4 / 1.1) | 275 / 95 / 1 | 582 | +1.42% ±0.57 |
| rent +13%, wage +8.8%, low-cost -30% | 1,045 | 12.9% | 47.1 | 22.7% | 24% | 47.0 (28.6 / 17.8 / 0.6) | 293 / 97 / 1 | 620 | +0.98% ±0.73 |

Reading: when rents outrun wages, about four times as many tenants leave, while the average rent share barely moves because those who cannot pay are the ones who go. Rent shares among those still seated therefore understate the pressure.
