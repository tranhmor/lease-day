# Lease Day: Do LLM Landlords Price a Subway Line Before It Opens?

*UGOD 5066 final project — DRAFT (2026-11-25). Sections 1–4 and the rule-baseline results are written from the frozen design. Everything marked **[L]** waits for the LLM runs; do not fill it before `--prereg` has been run. Word budget: < 5,000 words in total (target ≈ 4,600; current text ≈ 2,700).*

---

## Abstract  **[L — write last, ≈ 150 words]**

---

## 1. Introduction  (≈ 450 words)

When a new rail line is announced, the people who live along it learn that their commute will become shorter in the future. Urban economics predicts that this future gain is capitalised into land and housing prices before the line opens. Studies of Chicago's Midway Line find that house prices near future stations began to rise once the plans became widely known, years before the line opened in October 1993 (McDonald & Osuji, 1995; McMillen & McDonald, 2004). Similar anticipation effects are reported for light-rail plans in Oregon (Knaap, Ding & Hopkins, 2001), Santiago Metro Line 4 (Agostini & Palmucci, 2008) and Beijing subway extensions (Dai et al., 2026).

These studies observe *prices*. They cannot observe the decisions that produce them: whether landlords raise quotes on announcement, whether tenants move in early to lock in a rent, and who ends up capturing the gain. Rental markets are a particularly useful place to ask these questions, because leases are renegotiated every year and the commuters who benefit from the line are often renters.

Agent-based models (ABMs) can make these decisions explicit, but rule-based agents only react to an announcement if the modeller writes that reaction into the rules, so the result is assumed rather than discovered. Large language models (LLMs) offer another option: agents that read the same information a person would read and decide in natural language (Horton, 2023; Park et al., 2023). If LLM landlords raise rents after an announcement that rule agents ignore by construction, the difference is a behavioural response that the modeller did not program.

This project builds *Lease Day v0.7*, a 36-month rental market for renters who work in Beijing's CBD, in which 40 landlords and about 228 tenant households are played by an LLM. We run a single policy experiment: an eastern express line that cuts commute times from two zones (Z05 by 12 minutes, Z11 by 15 minutes) and either opens without warning or is announced twelve months in advance. We ask three pre-registered questions:

- **H1.** Do landlords in the benefiting zones raise quotes after the announcement but before opening, relative to the no-warning case?
- **H2.** Are early movers into the benefiting zones richer than movers in the no-warning case?
- **H3.** Are LLM landlords over-concessive compared with rule landlords (keeping rents flat in tight markets, accepting almost every counter-offer)?

The contribution is methodological as much as substantive. We pair every LLM run with an identical rule-agent run, use common random numbers so that only decisions differ across scenarios, write all decision criteria down before any LLM output exists, and validate the model with Axtell and Epstein's (1994) four levels.

---

## 2. Theory and hypotheses  (≈ 450 words)

**Capitalisation of expected access.** In the bid-rent framework, a household's willingness to pay for a location falls with commute cost. A line that lowers commute cost in zone *z* from month 25 raises the value of living in *z* from month 25. With one-year leases, a forward-looking landlord who signs a lease in months 13–24 knows that part of that lease, or the next one, falls after opening. If tenants also anticipate the change, demand for *z* rises before opening and landlords can raise rents. With no announcement, neither side can anticipate, and any rise starts at opening. H1 is therefore stated as a difference between the *announced* (P) and *surprise* (S) scenarios in months 13–24, when the line exists in neither scenario.

**Sorting.** Moving is costly: deposits, agent fees and up-front rent. Households with more income and cash can act on expected future gains; constrained households cannot. If the announcement induces early moves, the movers should be positively selected (H2). This connects capitalisation to incidence: if rents rise before opening and richer households move in, the poorer incumbents who stay face higher rents before they enjoy the shorter commute.

**Why H3.** LLMs fine-tuned to be helpful and agreeable may behave as unusually generous landlords. If so, any H1 effect would be understated, and the market as a whole would be biased toward low rents. H3 is a test of the instrument, not of the city, and we report it whichever way it comes out.

**Burden gradient (validation, not a hypothesis).** Schwabe's law states that the share of income spent on rent falls as income rises (Stigler, 1954, p. 100). We use it as a stylised fact that a credible rental model must reproduce (Section 4).

---

## 3. Model and experimental design  (≈ 900 words)

### 3.1 Environment

The board has 24 zones arranged around the CBD by direction (north, east, south, west) and ring (inner, middle, outer), built from Beijing rental listings and commuting data (Appendix A). Each zone has a rent level, a room-type mix (low-cost room, cheap single, shared room, whole unit), and travel times and monthly costs by mode (subway, bus, bike, car, walking). Zones are shown to agents as codes with direction and ring (e.g. "Z05, east, middle ring"), never as real place names, so the LLM cannot draw on what it knows about real neighbourhoods.

There are 240 rooms owned by 40 landlords (4–8 rooms each, clustered in one or two zones) and about 228 tenant households. Tenants work in the CBD and are drawn from a single income distribution (low, middle, high; single or dual-earner; with or without a car). The two benefiting zones are **over-sampled** (Z05: 24 rooms, Z11: 16 rooms; 17% of the stock) so that enough leases expire there during the test window. This is a design choice for statistical power, not a claim about real housing stock.

### 3.2 Timeline and market rules

The model runs for 36 months with one-year leases whose expiry months are spread evenly, so every household reaches an expiry once in months 13–24. Each month:

1. landlords price vacant rooms (`price_vacant`);
2. 2% of tenants leave the city, and 10 newcomers arrive and search (`search`, up to two applications);
3. for each expiring lease, the landlord quotes a renewal rent (`renewal_offer`); the tenant renews, counters once, moves or leaves (`at_expiry`); a counter is answered by the landlord (`answer_counter`);
4. a landlord with several applicants for one room picks one (`pick_applicant`).

Hard rules that the agents cannot override come from v0.6: a household is only shown rooms it can afford (at least 2,000 yuan left each month after rent and commuting, and enough cash for the up-front payment), only the five best affordable candidates are shown, and any quote outside 0.7–1.3× the current rent is truncated.

### 3.3 Scenarios and agent groups

| Scenario | Month 13 | Month 25 |
|---|---|---|
| N — no line | – | – |
| S — surprise opening | – | line opens |
| P — announced opening | all agents told: *"The eastern express line will open in month 25; commutes from Z05 will fall by about 12 minutes and from Z11 by about 15."* | line opens |

In P, every decision from month 13 includes the announcement and the months remaining until opening. Before opening, the travel-time table shows current times in all scenarios.

Two agent groups run the same three scenarios:

- **R (rule):** landlords and tenants follow the v0.6 scoring rules. Rule agents do not read the announcement, so **P and S must be identical seed by seed**; this is a code check, and the R group is the zero baseline. 20 seeds.
- **L (LLM):** every landlord and tenant decision is made by one fixed LLM (**[model, version, quantisation]**), temperature 0, JSON output, cached by prompt hash. Landlords are assigned a persona (individual or agency; vacancy-averse or patient). Invalid outputs are retried once and then replaced by the rule decision and logged as *fallback*. 5 seeds.

### 3.4 Identification: shared history and common random numbers

All three scenarios of a seed share one 12-month warm-up and fork from the same month-12 snapshot. After the fork, everything external to decisions is identical across scenarios: the same newcomers arrive with the same attributes, and each tenant's exit, search sample and processing order are drawn from a random stream keyed on (seed, agent, month), not on how many draws the scenario has made so far. A tenant present in both P and S therefore leaves in P if and only if they leave in S. What can still differ is only the consequence of decisions. This common-random-numbers design reduced the seed-to-seed standard deviation of S − N differences by about 35% in the rule group.

The initial market is filled by drawing applicants from the newcomer distribution until 95% of rooms are let (instead of drawing a fixed pool), so that the month-1 vacancy rate (5.5%) is already close to its steady state and the warm-up does not carry a filling trend into the test window.

### 3.5 Measures and pre-registered criteria

The criteria below were fixed on 2026-11-25, before any LLM run, and are implemented in `analyze_v07.py --prereg`.

- **H1 (main evidence, decision level).** All benefiting-zone landlord quotes (renewal offers and vacant-room prices) in months 13–24, P and S pooled. We regress the proposed change, (quote − current rent) / current rent, on a P indicator and the zone's smoothed vacancy rate, with standard errors clustered by seed and a *t*(G − 1) critical value. H1 is supported if the P coefficient is positive and its 95% CI excludes zero. Because five clusters make clustered errors unstable, we also report the sign of the coefficient seed by seed, and, as an auxiliary market-level measure, the P − S difference in the benefiting-zone rent index at month 24.
- **H2.** Mean income and mean pre-move cash of households moving into benefiting zones in months 13–24, P − S, with a seed bootstrap (2,000 draws). Supported if both differences are positive with CIs excluding zero; "directional" if both point estimates are positive. With roughly 90 movers per scenario, power is low and stated as such.
- **H3.** In scenario N, L versus R: (a) the share of renewal quotes with no increase when zone vacancy is below 4%; (b) the counter-offer acceptance rate. Over-concessive if either exceeds the rule baseline by more than 20 percentage points, or if (b) exceeds 98%.
- **Run quality.** A run with fallback ≥ 2% is void and rerun.
- **Bias B.** L-N minus R-N at month 36 (rent indices, vacancy, commute). If the rent-index gap exceeds ±3 points, every P − S result carries that caveat.
- **Cross-model check.** One paired seed is rerun with a cloud model (**[model]**). Same H1 sign as the local model on that seed: "robust"; opposite: "model-dependent", reported as such.

---

## 4. Validation framework and rule-baseline results  (≈ 700 words)

Code verification (14 automated acceptance tests: P = S in the rule group, reproduction of the v0.6 baseline within 1%, replay of any household from the decision log, cache reproducibility, prompt-leakage checks, identical external events across scenarios, and estimator unit tests) shows that the program does what the design says. It does not show that the model resembles a rental market. For that we use the four levels of Axtell and Epstein (1994), with thresholds fixed before the LLM runs.

**Table 1. Validation checks and rule-group (R, 20 seeds) results**

| Level | Check | Criterion | R result |
|---|---|---|---|
| 0 | Decision directions plausible | LLM diagnostics: higher quotes with announcement, lower with high vacancy, robust to rewording | **[L — Section 5.1]** |
| 1 | V1.1 Stable without shock | N: rent drift M12→M36 within ±3 pts; vacancy M13–36 in 3–12% | Pass: −0.51 ± 0.35 pts; 6.0% |
| 1 | V1.2 Burden falls with income | Formal market (excl. low-cost rooms): low > mid > high in ≥ 80% of seeds, and strictly decreasing within each room type | Pass: 24.4 / 21.3 / 17.3%, 18/20 seeds; all four room types decreasing |
| 1 | V1.3 Rent–commute trade-off | Spearman(zone rent, subway minutes) < 0 | Pass: ρ = −0.75 |
| 1 | V1.4 Opening premium positive | S − N benefiting-zone rent index at M36 > 0 | Pass: +0.45 (+0.12, +0.78) |
| 1 | V1.5 Announcement effect positive | P − S benefiting-zone rent index at M24 > 0 | n/a by design (R ignores announcements); **[L]** |
| 2 | V2.1 Premium magnitude | S vs N premium within Line 14's 95% CI (−1.5%, +6.7%) | Consistent: +0.45% — but weakly discriminating |
| 2 | V2.2 Commute level | N mean one-way commute within 48 min ± 10% (CAUPD/Baidu, Beijing 2021) | **Consistent**: 48.56 ± 0.25 min. Share over 60 min 23.7% vs 28–31% observed (reported only). Weakly independent |
| 3 | Individual behaviour | — | Not testable: no individual rental panel |

The empirical anchor for V2.1 is our own difference-in-differences on Beijing rental listings in 2015 and 2018 (Appendix B): rents per m² within 1 km of the middle section of Line 14 rose 2.3 percentage points more than in comparable cells (95% CI −1.5 to 6.7). The model and the data differ in horizon (12 months versus 1.5–2.5 years after opening) and coverage (all rooms versus asking rents for 30–150 m² units), so V2.1 is a check on order of magnitude only.

**V1.2 needs explanation.** Pooled across all room types, low-income tenants pay a *lower* share of income than middle-income tenants (15.8% vs 20.4%). This reverses when the low-cost segment is removed or when room types are compared one at a time (e.g. shared rooms 33.2% / 21.8% / 13.2%). The pooled reversal is a composition effect: about two thirds of low-income renters live in the 600–730 yuan low-cost rooms, which come from the census's below-1,000-yuan band and correspond to informal housing, while dual-earner households, mostly middle-income, are barred from low-cost rooms. Schwabe's law concerns households in the same housing market, so we gate on the formal-market and within-type versions and report the pooled figure alongside. We changed the criterion, not the model, and did so before any LLM run.

**Two limitations follow from the same mechanism.** First, low-income hardship in the model appears mainly as *exclusion*, not as high burden among those housed: in months 13–36 the affordability rules turn away low-income searchers 75.7 times per run, versus 43.4 (middle) and 5.8 (high). Second, the sitting population gets richer over time (the low-income share falls from 27.7% to 19.5%, mean savings from about 34,000 to 104,000 yuan), because newcomers must pass the affordability rules while incumbents only accumulate savings. This is why H2 is defined as a P − S difference rather than as movers versus the average tenant.

**Rule-group treatment effects.** Table 2 shows the seed-paired differences. With rule agents, the opening itself has a small effect: benefiting-zone rents +0.45 points at month 36, benefiting-zone vacancy −0.74 points, mean commute −1.54 minutes, and no change in who lives there. Every P − S cell is exactly zero. Any non-zero P − S in the LLM group must therefore come from how the LLM agents respond to the announcement.

**Table 2. Rule group: seed-paired differences (20 seeds; 95% CI)**

| Indicator | N level | S − N | P − S |
|---|---|---|---|
| Benefiting-zone rent index, M24 | 101.46 | +0.00 | +0.00 |
| Benefiting-zone rent index, M36 | 102.25 | +0.45 (+0.12, +0.78) | +0.00 |
| Benefiting-zone vacancy, M25–36 (pp) | 4.57 | −0.74 (−1.24, −0.24) | +0.00 |
| Mean commute, M25–36 (min) | 48.56 | −1.54 (−1.72, −1.36) | +0.00 |
| Move-ins to benefiting zones, M13–24 | 17.65 | +0.00 | +0.00 |
| Low-income share in benefiting zones, M25–36 (pp) | 27.39 | −0.11 (−0.76, +0.55) | +0.00 |
| Low-income searchers turned away, M13–36 | 75.70 | +0.25 (−0.55, +1.05) | +0.00 |

*Figure 1: benefiting-zone rent index by month, N/S/P, with 95% bands (`figs_r/fig1_rent_index.png`; replace with the L-group version and keep R as a panel).*

---

## 5. Results  **[L]**  (≈ 1,300 words)

### 5.1 LLM behaviour diagnostics (Level 0)
**[L — from `diagnose.py`: valid-output rate; quote response to announcement × vacancy × months-to-opening × tenant standing; rewording stability; tenant grid.]**

### 5.2 Run quality and bias B
**[L — max fallback rate; L-N vs R-N gaps at M36; whether the ±3-point caveat applies.]**

### 5.3 H1: quotes before opening
**[L — b_P with clustered CI; k/5 seeds positive; Figure 4 (quotes by month, P vs S); auxiliary P − S rent index at M24; V1.5 verdict.]**

### 5.4 H2: who moves early
**[L — P − S income and cash with bootstrap CIs; Figure 5; power caveat.]**

### 5.5 H3: are LLM landlords too soft?
**[L — no-hike share under tight vacancy and counter acceptance, L vs R (R baseline: 38.6% and 92.9%).]**

### 5.6 Incidence and a replayed case
**[L — M12 cohort cost change by income group; one landlord and one tenant traced through decisions.jsonl.]**

### 5.7 Cross-model check
**[L — cloud vs local H1 sign on the same seed.]**

---

## 6. Discussion and limitations  (≈ 500 words; partly drafted)

**What the design can and cannot say.** The P − S contrast isolates the response to information: the line, the rooms, the households and the external shocks are the same. It cannot tell us whether a real landlord would respond in the same way, because Level 3 validation is not possible without individual rental data. The LLM is a hypothesis generator about behaviour, disciplined by the rule baseline and by macro-level checks.

**Known limitations (fixed now; results-dependent points to be added):**
- Five LLM seeds; clustered inference with five clusters is fragile, so seed-level signs are reported alongside.
- One local model, quantised; the cross-model check covers only one seed.
- Benefiting zones are over-sampled.
- Low-income hardship appears mainly as exclusion from the market, which V1.2 does not measure.
- The sitting population becomes richer over time; H2 is defined as P − S for this reason.
- The empirical premium is for asking rents, 1.5–2.5 years after opening; the model's horizon is 12 months.
- Commute-level agreement (V2.2) is only weakly independent: the 48-minute target was not used in formal calibration, but the distance-decay constant may have been chosen with it in mind. The model also under-predicts long commutes (23.7% over 60 minutes vs 28–31%), likely because it has no peak-hour congestion and no cross-border commuters.
- Prompts were frozen before the main runs; LLM outputs may still be sensitive to wording beyond the three paraphrases tested.

---

## 7. Conclusion  **[L]**  (≈ 200 words)

---

## References

Agostini, C. A., & Palmucci, G. A. (2008). The anticipated capitalisation effect of a new metro line on housing prices. *Fiscal Studies, 29*(2), 233–256. https://doi.org/10.1111/j.1475-5890.2008.00074.x

Axtell, R. L., & Epstein, J. M. (1994). Agent-based modeling: Understanding our creations. *The Bulletin of the Santa Fe Institute, 9*(2), 28–32.

Dai, T., Fang, Y., Jiang, S., & Jiang, Y. (2026). Contradictory capitalization: The uneven effects of subway expansion on second-hand housing prices in Beijing. *Transportation Research Part A: Policy and Practice, 214*, 105272. https://doi.org/10.1016/j.tra.2026.105272

Horton, J. J. (2023). *Large language models as simulated economic agents: What can we learn from Homo silicus?* NBER Working Paper 31122. https://www.nber.org/papers/w31122

Knaap, G. J., Ding, C., & Hopkins, L. D. (2001). Do plans matter? The effects of light rail plans on land values in station areas. *Journal of Planning Education and Research, 21*(1), 32–39. https://doi.org/10.1177/0739456X0102100103

McDonald, J. F., & Osuji, C. I. (1995). The effect of anticipated transportation improvement on residential land values. *Regional Science and Urban Economics, 25*(3), 261–278. https://doi.org/10.1016/0166-0462(94)02085-U

McMillen, D. P., & McDonald, J. F. (2004). Reaction of house prices to a new rapid transit line: Chicago's Midway Line, 1983–1999. *Real Estate Economics, 32*(3), 463–486. https://doi.org/10.1111/j.1080-8620.2004.00099.x

Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). Generative agents: Interactive simulacra of human behavior. In *Proceedings of UIST '23* (Article 2, pp. 1–22). https://doi.org/10.1145/3586183.3606763

Stigler, G. J. (1954). The early history of empirical studies of consumer behavior. *Journal of Political Economy, 62*(2), 95–113. https://doi.org/10.1086/257495

**[Data: DRUM Beijing rental listings 2015/2018, DOI 10.13020/ejpy-2r93 (CC0); OpenStreetMap stations (ODbL); commute target: CAUPD/Baidu Maps, *2022 Annual China Major Cities Commuting Monitoring Report* (Beijing, 2021).]**

---

## Appendices (not counted in the word limit if allowed — **check with instructor**)
- A. Board construction (zones, room types, modes).
- B. Line-rent difference-in-differences (`analysis/line_rent_results.md`).
- C. Prompts (frozen hashes) and the decision JSON schema.
- D. Acceptance tests.
