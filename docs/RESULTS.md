# Results (E1–E5)

Compact version of the paper's results section. Full tables (CSV + LaTeX) and figures (PNG + SVG) are in `results/<experiment>/<timestamp>/`; `uv run python -m pusula.evaluation.paper_results` regenerates everything and copies the key files to `results/paper/<timestamp>/`. Data up to 2026-11-20. Design decisions: D-065 … D-072 in `docs/DECISIONS.md`; caveats: `docs/LIMITATIONS.md`.

---

## E1 · Risk model validation (rolling 1-day VaR, 2019-01 → 2026-11)

Setup:
- 41 stocks, 73,842 stock-days;
- refit every 5 trading days on 500 days;
- exact VaR quantiles (no Monte Carlo);
- critics rerun at every refit with 200 paths per model.

Runtime: 44 min on 4 cores.

**All stocks, VaR 99 % (target exceedance 1 %)**

| Model | Exceedance | Kupiec p (pooled) | Stocks rejected: POF | … independence | … cond. coverage | Quantile loss ×10⁴ |
|---|---|---|---|---|---|---|
| HS | 1.22 % | <0.001 | 7 % | 59 % | 51 % | 9.49 |
| FHS | 1.26 % | <0.001 | 7 % | **5 %** | **10 %** | 8.67 |
| GBM | 1.75 % | <0.001 | 85 % | 63 % | 88 % | 9.81 |
| Merton | 1.65 % | <0.001 | 73 % | 61 % | 80 % | 9.76 |
| GARCH-t | **1.06 %** | **0.09** | 15 % | 12 % | 15 % | **8.60** |
| In-sample critic | 1.23 % | <0.001 | 7 % | 56 % | 49 % | 9.45 |
| Hold-out critic | 1.42 % | <0.001 | 41 % | 39 % | 54 % | 9.32 |

**Key question: hold-out critic vs in-sample critic and plain HS** (per stock, 41 stocks)

| Level | Comparison | Hold-out has lower quantile loss | Sign-test p | Hold-out exceedance closer to target |
|---|---|---|---|---|
| 95 % | vs in-sample critic | 36 / 41 | <0.001 | 18 / 41 |
| 95 % | vs HS | 36 / 41 | <0.001 | 18 / 41 |
| 99 % | vs in-sample critic | 24 / 41 | 0.35 | 7 / 41 |
| 99 % | vs HS | 25 / 41 | 0.21 | 7 / 41 |

Model choice:

| Critic | HS | FHS | GBM | Merton | GARCH-t |
|---|---|---|---|---|---|
| In-sample | 94 % | 4 % | 0 % | 1 % | 1 % |
| Hold-out | 26 % | 24 % | 26 % | 8 % | 17 % |

**In plain words:**
- The volatility-clustering models, **GARCH-t and FHS**, give the best 1-day VaR. Their losses cross the VaR about as often as they should (GARCH-t 1.06 % vs the target 1 %), and the crossings do not cluster in time (FHS: only 5 % of stocks fail the independence test, HS 59 %).
- The **hold-out critic** beats the in-sample critic and plain HS on the overall scoring rule at the 95 % level (36 of 41 stocks). At 99 % the difference is not significant, and its exceedance rate is worse: it sometimes picks the thin-tailed GBM, because a 100-day hold-out contains almost no 1-in-100 days.
- The in-sample critic is practically plain HS (94 % of choices), confirming the bias that motivated D-050.

Further results:
- **By regime** (VaR 99, GARCH-t / HS / hold-out critic): every model breaches more often in the volatile regimes and less in the calm ones.
  - 2019–2020: 1.32 / 1.56 / 1.61 %.
  - 2021–2023 unorthodox period: 1.21 / 1.61 / 2.07 %.
  - 2023–2024 normalisation: 0.54 / 0.44 / 0.71 %.
- **Universes:** BIST30 and Energy behave alike. GARCH-t VaR 99: 1.06 % (BIST30) vs 1.08 % (Energy).

Figures: `e1_exceedance_rates`, `e1_rolling_exceedance_var99`.

---

## E2 · Factor model (weekly, 2018 → 2026)

| | BIST30 median | Energy median | Mann–Whitney p | Energy, without TUPRS |
|---|---|---|---|---|
| In-sample R², Model A (macro only) | 0.137 | 0.092 | 0.007 | 0.087 |
| In-sample R², Model B (+ market residual) | 0.458 | 0.332 | 0.003 | 0.291 |
| Out-of-sample R², Model A | −0.039 | −0.057 | 0.51 | −0.061 |
| Out-of-sample R², Model B | 0.355 | 0.242 | 0.012 | 0.208 |
| Max VIF | 1.25 | 1.25 | 0.72 | 1.25 |

Mean response to a 1-sd weekly factor move (%):

| Factor | BIST30 | Energy | Mann–Whitney p |
|---|---|---|---|
| CDS | −1.58 | −0.96 | 0.008 |
| USD/TRY | +0.64 | +0.10 | 0.049 |
| US 10Y | +0.29 | +0.60 | 0.006 |
| Rate (2Y) | −0.69 | −0.72 | 0.76 |
| VIX | −0.54 | −0.45 | 0.25 |
| Brent | +0.18 | +0.36 | 0.30 |
| TTF | −0.27 | −0.30 | 0.73 |

**In plain words:**
- Macro factors explain a modest part of weekly returns: about 14 % for BIST30 and 9 % for Energy.
- **Out of sample, the macro-only model has no predictive value** (R² slightly below zero in 2-year-fit / 26-week-test windows): the stock–macro links change too much between periods. With the market residual (Model B) out-of-sample R² stays clearly positive.
- **BIST30 is much more sensitive to country risk (CDS) and benefits more from a weaker lira** (possibly because of the many exporters and holding companies in BIST30; an interpretation, not tested). Energy reacts more to global rates and oil. The differences hold without the overlapping TUPRS. Multicollinearity is not a problem in weekly changes (max VIF 1.6).

Further results:
- **Stability:** the CDS response keeps its sign in every rolling window (sign agreement 96–100 %). The USD/TRY response flips sign often (59–62 %) and varies the most (rolling sd ≈ 1.8–2.0 percentage points).
- **Regimes:** in the 2024–2026 easing cycle the CDS response is 2.5–4× larger than in earlier regimes (BIST30: −3.75 % vs −0.93 … −1.53 %). The USD/TRY response turns strongly negative (−3.71 %), while it was mixed earlier (−0.98 … +1.16 %). Regime responses use the full-sample factor sd.
- **Sub-sectors (median R² A / B):** electricity 0.09 / 0.33, natural gas 0.08 / 0.12, refining 0.14 / 0.43.

Figures: `e2_beta_heatmap` (stocks × factors, BIST30 vs Energy sub-sectors), `e2_r2_is_oos`.

---

## E3 · PPK event study (rate decisions 2019 → 2026)

Design:
- 37 rate changes with a pre-event model (2020-01 → 2026-10), plus 4 changes in 2019 with realised reactions only (factor history too short);
- 43 holds;
- window [−1, +5]; market model estimated on [−250, −30];
- 95 % CIs from 2,000 bootstrap draws over events.

| Group | Comparison | Events | Direction accuracy [95 % CI] | MAE (pp) | Mean predicted | Mean realised |
|---|---|---|---|---|---|---|
| All | total | 37 | 0.53 [0.44, 0.61] | 6.86 | −0.03 % | +0.81 % |
| All | abnormal (CAR) | 37 | 0.46 [0.43, 0.50] | 4.70 | +0.01 % | +0.07 % |
| BIST30 | total | 37 | 0.52 [0.44, 0.61] | 6.75 | −0.03 % | +0.62 % |
| Energy | total | 37 | 0.55 [0.42, 0.66] | 7.22 | 0.00 % | +1.61 % |
| Cuts | total | 23 | 0.58 [0.46, 0.69] | 6.84 | +0.09 % | +0.41 % |
| Hikes | total | 14 | 0.43 [0.32, 0.56] | 6.89 | −0.22 % | +1.48 % |

Realised mean CAR [−1, +5]:

| Decision | BIST30 | Energy |
|---|---|---|
| Cuts | −0.29 % | +0.21 % |
| Hikes | +0.03 % | +1.33 % |
| Holds | −0.04 % | −0.47 % |

**In plain words:**
- The scenario engine **cannot predict how stocks react to PPK decisions**: the direction is right about half the time, no better than a coin flip.
- The predicted moves are tiny (≈0.1 %) next to realised moves of several percent, for two reasons:
  - policy-rate changes pass through only weakly to the 2-year yield (L-14);
  - announcement-day moves are driven by the *surprise* and other news, which a weekly factor model does not see.
- Most rate **hikes** in 2023–2024 were followed by *positive* stock reactions (e.g. XU100 +13 % around 2023-06-22) (the market welcomed the return to orthodox policy), the opposite of the model's "hike hurts" logic.
- *Interpretation (not tested):* the 2023–24 hikes coincided with the return to orthodox monetary policy after the 2021–23 low-rate period. Investors may have read them as a **credibility signal** (lower inflation and country risk ahead) rather than as tighter financing. If so, the sign of the rate–equity relation is **regime-dependent**: a weekly factor model fitted on the previous regime will get it wrong exactly at a policy turning point. A test would need expectation (surprise) data and more events per regime.
- The sample is small (37 events in a few policy cycles) and the CIs are wide. This is a validation result: the engine is useful for "what-if" comparisons, not for forecasting announcement-day moves (L-16).

Figures: `e3_pred_vs_realised`, `e3_event_car_by_universe`.

---

## E4 · Decision backtest (weekly, 2025-11-07 → 2026-11-20)

Stocks (rule D-070; median daily traded value over the 12 months before SELECTION_DATE):
- BIST30: THYAO, YKBNK, AKBNK, ISCTR, KCHOL;
- Energy: TUPRS (refining), CANTE, ODAS, ZOREN (electricity), ENERY (natural gas).

Setup: 54 weekly decisions per stock; costs 10 + 5 bp; cash earns TLREF; Sharpe and Sortino use TLREF as the risk-free rate.

**Non-LLM strategies, 10-stock portfolio, TRY** (full window / post-cutoff window from 2026-06-01, 24 weeks)

| Strategy | Cum. return | CAGR | Ann. vol | Sharpe | Sortino | Max DD | Calmar | Avg. position |
|---|---|---|---|---|---|---|---|---|
| Buy & hold (EW) | +2.1 % / +0.2 % | 2.0 % | 28.1 % | −1.16 / −1.16 | −1.48 | −18.3 % | 0.11 | 1.00 |
| XU030 | +17.7 % / −10.0 % | 17.0 % | 27.2 % | −0.70 / −2.03 | −0.96 | −22.2 % | 0.77 | – |
| Rule-based risk filter | +35.0 % / +18.5 % | 33.5 % | 12.9 % | −0.67 / −0.15 | −0.83 | −9.3 % | 3.58 | 0.29 |
| Cash (TLREF) | +48.8 % / +19.2 % | | | | | | | 0 |

Sharpe difference, rule filter − buy & hold: +0.49 (95 % CI [−0.72, 2.01], p = 0.45).
In USD, every strategy lost value except the rule filter (+12.6 %). The USD Sharpe ratios equal the TRY ones by construction (D-070).

**Long sample 2019–2026 (411 weeks, same 10 stocks)**

| Strategy | Cum. return (TRY) | CAGR | Sharpe | Max DD | Cum. return (USD) |
|---|---|---|---|---|---|
| Buy & hold (EW) | +1,562 % | 42.7 % | 0.45 | −41.9 % | +80 % |
| XU030 | +1,151 % | 37.7 % | 0.34 | −29.6 % | +36 % |
| Rule-based risk filter | +879 % | 33.5 % | 0.26 | −15.5 % | +6 % |

Sharpe difference, rule filter − buy & hold: −0.19 (95 % CI [−0.83, 0.40], p = 0.52).

**In plain words (non-LLM part):**
- In the LLM test year, **TLREF cash (+48.8 %) beat every equity strategy**, so all Sharpe ratios are negative. With the policy rate at 36–38 % (TLREF 35.5–40 %), Turkish stocks must clear a very high bar, which is why TLREF (not zero) is the right risk-free rate (CLAUDE.md §6.5).
- The rule-based risk filter was in the market only 29 % of the time. That gave it the best result of the window, but the gain over buy & hold is not statistically significant.
- Over 2019–2026 the same filter **halves the maximum drawdown (−16 % vs −42 %) but gives up return** and has a lower Sharpe ratio. It works as a risk reducer, not as an alpha source.

**LLM variants** (lean, reasoning off, Nemotron 3 Ultra; evaluated only at ≥ 98 % coverage, D-074; finished 2026-11-24 04:02 UTC)

| Variant | Coverage | Status |
|---|---|---|
| P+R+S | 540 / 540 (100 %) | ✅ evaluated |
| P | 540 / 540 (100 %) | ✅ evaluated |
| P+R+S anonymised | 540 / 540 (100 %) | ✅ evaluated |
| P+R | 540 / 540 (100 %) | ✅ evaluated |

**LLM variants vs the non-LLM strategies, TRY** (full window / post-cutoff window)

| Strategy | Cum. return | Ann. vol | Sharpe (TLREF) | Max DD | Avg. position | Weekly turnover |
|---|---|---|---|---|---|---|
| Buy & hold (EW) | +2.1 % / +0.2 % | 28.1 % | −1.16 / −1.16 | −18.3 % | 1.00 | 0.019 |
| Rule-based risk filter | +35.0 % / +18.5 % | 12.9 % | −0.67 / −0.15 | −9.3 % | 0.29 | 0.165 |
| LLM P (price/trend only; BEKLE = keep) | +29.5 % / +7.9 % | 17.6 % | −0.69 / −0.94 | −12.4 % | 0.53 | 0.050 |
| LLM P (BEKLE = 50 %) | +21.4 % / +7.9 % | 16.6 % | −1.11 / −1.32 | −9.3 % | 0.54 | 0.122 |
| LLM P+R (price/trend + risk; BEKLE = keep) | +39.3 % / +17.3 % | 8.3 % | −0.74 / −0.33 | −3.3 % | 0.32 | 0.017 |
| LLM P+R (BEKLE = 50 %) | +22.8 % / +6.4 % | 12.6 % | −1.42 / −1.88 | −8.5 % | 0.47 | 0.146 |
| **LLM P+R+S** (BEKLE = keep) | **+44.6 % / +18.3 %** | **6.5 %** | **−0.41 / −0.15** | **−1.9 %** | 0.22 | 0.006 |
| LLM P+R+S (BEKLE = 50 %) | +38.8 % / +16.2 % | 7.5 % | −0.87 / −0.63 | −2.4 % | 0.26 | 0.125 |
| LLM P+R+S anonymised (BEKLE = keep) | +48.2 % / +19.6 % | 5.8 % | −0.05 / +0.14 | −1.6 % | 0.15 | 0.007 |
| LLM P+R+S anonymised (BEKLE = 50 %) | +45.0 % / +17.9 % | 6.6 % | −0.36 / −0.25 | −1.6 % | 0.22 | 0.102 |
| XU030 | +17.7 % / −10.0 % | 27.2 % | −0.70 / −2.03 | −22.2 % | – | – |
| Cash (TLREF) | +48.8 % / +19.2 % | | | | 0 | |

**Final ablation table** (TRY, full window 2025-11-07 → 2026-11-20, BEKLE = keep; all 4 × 540 decisions, 0 failed calls)

| Variant | Inputs | Cum. return | Sharpe (TLREF) | Max DD | Avg. position | AL / ALMA / BEKLE |
|---|---|---|---|---|---|---|
| P | price/trend | +29.5 % | −0.69 | −12.4 % | 0.53 | 15 / 8 / 77 % |
| P+R | + risk | +39.3 % | −0.74 | −3.3 % | 0.32 | 14 / 21 / 65 % |
| P+R+S | + scenarios (full) | +44.6 % | −0.41 | −1.9 % | 0.22 | 3 / 52 / 46 % |
| P+R+S anonymised | full, names/dates hidden | +48.2 % | −0.05 | −1.6 % | 0.15 | 2 / 58 / 40 % |
| Buy & hold (EW) | – | +2.1 % | −1.16 | −18.3 % | 1.00 | – |
| Rule-based risk filter | – | +35.0 % | −0.67 | −9.3 % | 0.29 | – |
| Cash (TLREF) | – | +48.8 % | – | – | 0 | – |

Sharpe differences (stationary bootstrap, 95 % CI):

| Comparison | Full window | Post-cutoff |
|---|---|---|
| LLM P+R+S − buy & hold | +0.76 [−1.10, 2.71], p = 0.45 | +1.01 [−1.33, 4.37], p = 0.43 |
| LLM P+R+S − rule filter | +0.27 [−2.31, 2.76], p = 0.87 | +0.00 [−4.77, 4.85], p = 0.99 |
| LLM P − buy & hold | +0.48 [−0.07, 1.02], p = 0.08 | +0.22 [−0.71, 0.98], p = 0.58 |
| LLM P+R − buy & hold | +0.42 [−0.78, 1.71], p = 0.51 | +0.83 [−0.84, 3.34], p = 0.38 |
| LLM P+R − LLM P (value of the risk block) | −0.06 [−1.29, 1.29], p = 0.90 | +0.61 [−1.16, 3.14], p = 0.53 |
| LLM P+R+S − LLM P+R (value of the scenario block) | +0.34 [−0.85, 1.71], p = 0.64 | +0.19 [−0.75, 1.30], p = 0.74 |
| **LLM P+R+S − LLM P** (value of risk + scenario inputs) | +0.28 [−1.54, 2.17], p = 0.81 | +0.79 [−1.50, 3.98], p = 0.52 |
| LLM P+R+S anonymised − buy & hold | +1.11 [−1.21, 3.40], p = 0.37 | +1.30 [−2.63, 5.66], p = 0.52 |
| **LLM P+R+S − LLM P+R+S anonymised** (memorisation test) | −0.36 [−1.11, 0.63], p = 0.47 | −0.29 [−1.74, 1.62], p = 0.76 |

Decision distribution:

| Variant | AL | ALMA | BEKLE | BEKLE > 70 %? |
|---|---|---|---|---|
| P | 14.8 % | 7.8 % | 77.4 % | **yes (flagged)** |
| P+R | 14.1 % | 20.7 % | 65.2 % | no |
| P+R+S | 2.6 % | 51.7 % | 45.7 % | no |
| P+R+S anonymised | 1.9 % | 58.3 % | 39.8 % | no |

- No failed calls in any evaluated variant.
- P+R+S by stock: mostly ALMA for the banks and small energy names (AKBNK, YKBNK 81 %, CANTE 91 %, ENERY 98 %); mostly BEKLE for THYAO (96 %), KCHOL (93 %) and TUPRS (85 %).
- P by stock: BEKLE everywhere; AL most often for TUPRS (41 %).
- P+R by stock: still mostly BEKLE; AL for TUPRS 70 %, THYAO 37 %, KCHOL 28 %; ALMA mainly for CANTE (80 %) and ENERY (39 %).
- P+R+S anonymised by stock: the same pattern as with names (ALMA for AKBNK 94 %, YKBNK 94 %, CANTE 93 %, ENERY 98 %; BEKLE for THYAO 100 %, TUPRS 89 %, KCHOL 83 %).
- Named vs anonymised, same stock-week: **88.1 % identical decisions** (476 / 540). Most differences are BEKLE → ALMA (45 cases); AL never turned into ALMA or back.

**In plain words (LLM part):**
- With risk and scenario information, the LLM was **very cautious**: it chose AL in only 2.6 % of stock-weeks and was invested 22 % of the time on average.
- In a year in which TLREF cash (+48.8 %) beat every equity strategy, this caution gave the **lowest volatility and drawdown** (−1.9 %) and the best Sharpe ratio of the equity strategies, but still less than cash (+44.6 %).
- **Ablation P → P+R+S:** with price/trend only, the model mostly said BEKLE (77 %, above the 70 % flag) and, once in, stayed long (invested 53 % of the time; +29.5 %, max DD −12.4 %). Adding the risk and scenario blocks changed the answer from "wait" to "do not buy" (ALMA 8 % → 52 %): it was invested 22 % of the time, with a better Sharpe (−0.41 vs −0.69) and a much smaller drawdown (−1.9 % vs −12.4 %).
- **None of the Sharpe differences is statistically significant**: the 95 % intervals are wide and include zero (52 weeks, L-17). P vs buy & hold comes closest (p = 0.08). Much of the P+R+S result comes from staying out of the market in a high-rate year, not from picking winners. 
- **Risk block vs scenario block (P → P+R → P+R+S):** the risk block alone (P+R) moved some decisions from BEKLE to ALMA (ALMA 8 % → 21 %) and cut the drawdown (−12.4 % → −3.3 %) and the time in the market (53 % → 32 %), but did not raise the Sharpe ratio (−0.74 vs −0.69). Adding the scenario block (P+R+S) made the model much more cautious (ALMA 52 %, AL 3 %) and gave the best Sharpe of the named variants (−0.41). So the step-by-step picture is: risk information mainly **reduces losses**, scenario information mainly **reduces market exposure** further. None of these steps is statistically significant (p ≥ 0.53), so this is a description of the behaviour, not a proven effect.
- **Memorisation / look-ahead test (anonymised mode):** hiding the ticker, company name and absolute dates did **not** make the decisions worse. 88 % of the decisions are identical, the anonymised variant was slightly more cautious (ALMA 58 % vs 52 %) and had a slightly higher Sharpe ratio (−0.05 vs −0.41), and the difference is not significant (p = 0.47). So we find **no sign** that the P+R+S result depends on the model recognising the stock or the period. This is an absence of evidence within one year, not a proof: the numbers in the input (e.g. volatility levels) could still hint at the stock (L-02).

## E5 · LLM reliability (reduced, D-074; finished 2026-11-23 21:40 UTC)

Design:
- 10 stock-weeks from the E4 inputs (P+R+S, lean prompt);
- Nemotron 3 Ultra repeated 5× at the production temperature (0.2, reasoning off; repeats 2–5 bypass the cache);
- the same 10 inputs for Kimi K3.1 Pro, Gemma 4 31B and Nemotron with reasoning on;
- 4 full analyses (THYAO, AKBNK; ENJSA, TUPRS) on the freeze date.

80 lean calls, 0 failures.

| Measure | Value |
|---|---|
| Repeatability, Fleiss' κ (5 Nemotron repeats) | **1.00** (all 10 stock-weeks unanimous) |
| Cross-model Fleiss' κ (Nemotron, Kimi, Gemma) | 0.22 |
| Nemotron vs Gemma: agreement / Cohen's κ | 80 % / 0.67 |
| Nemotron vs Kimi | 30 % / −0.19 |
| Kimi vs Gemma | 50 % / 0.21 |
| Nemotron reasoning off vs on | 70 % / 0.41 |

Decision distribution on the same 10 stock-weeks:

| Model | AL | ALMA | BEKLE |
|---|---|---|---|
| Nemotron 3 Ultra (reasoning off) | 10 % | 30 % | 60 % |
| Nemotron 3 Ultra (reasoning on) | 10 % | 20 % | 70 % |
| Kimi K3.1 Pro | 20 % | 30 % | 50 % |
| Gemma 4 31B | 10 % | 50 % | 40 % |

**Full-mode audit (4 analyses):**

| Stock | Decision (confidence) | Numbers checked | Not found in input (final) | Consistency | Regenerations (numeric / consistency) |
|---|---|---|---|---|---|
| THYAO | BEKLE (0.55) | 191 | 0 | OK | 0 / 2 |
| AKBNK | BEKLE (0.35) | 212 | 0 | OK | 2 / 4 |
| ENJSA | BEKLE (0.45) | 121 | 0 | OK | 0 / 0 |
| TUPRS | BEKLE (0.40) | 176 | 0 | OK | 0 / 0 |

- **Audit totals:** 700 numbers, 100 % faithful after the audit. 2 of 4 analyses needed regeneration (THYAO and AKBNK); 1 needed a numeric fix (AKBNK).
- **Latency:**
  - lean call, reasoning off: median 2.9 s;
  - lean call, reasoning on: median 24.8 s;
  - Gemma: median 107 s (free-tier queue);
  - Kimi: all 10 answers came from the cache of the earlier pre-run (latency ~94 s in D-055);
  - full analysis: 5.5–10 min.
- **JSON failure rate** (all logged calls): 0 % for the 985 lean calls; 19 % of auditor and 7 % of scenario-analyst attempts needed a retry, and all succeeded.

**In plain words:**
- **Nemotron is fully repeatable** at the production settings: the same input gave the same decision 5 times out of 5 for all 10 stock-weeks. Run-to-run randomness does not drive the E4 results.
- **Different models disagree a lot** (κ = 0.22). Gemma agrees with Nemotron on 8 of 10 cases, Kimi on only 3. Switching on hidden reasoning changes the decision in 3 of 10 cases and pushes towards BEKLE. The decision therefore depends on the model choice, which is why all E4 variants use one model (D-075) and why the paper should report E4 as "this model's" behaviour.
- **The auditor works as intended:** every number in the final reports exists in the input. In half of the full analyses the consistency check found a real issue and the named reports were regenerated (D-063).
- Every model chose BEKLE or ALMA in most cases; none shows an AL bias.

Figures: `results/paper/figures_tr/sekil_15_e5_uyum_matrisi` (agreement matrix); table `tablo_11_ajan_karar_karsilastirmasi` (four full analyses).

---

## Figures

| Experiment | File (in `results/<exp>/<timestamp>/`, PNG + SVG) | Content |
|---|---|---|
| E1 | `e1_exceedance_rates` | VaR 95/99 exceedance rate per model, BIST30 vs Energy |
| E1 | `e1_rolling_exceedance_var99` | 126-day rolling VaR 99 exceedance rate, 2019–2026 |
| E2 | `e2_beta_heatmap` | Factor sensitivities (% per 1-sd move), stocks × factors |
| E2 | `e2_r2_is_oos` | In-sample vs out-of-sample R², Model A/B, by universe |
| E3 | `e3_pred_vs_realised` | Predicted vs realised [−1, +5] reaction per stock-event |
| E3 | `e3_event_car_by_universe` | Mean CAR per rate change, BIST30 vs Energy |
| E4 | `e4_equity_curves` | Portfolio value of all strategies vs TLREF cash, post-cutoff marker |
| E4 (paper) | `results/paper/figures_tr/sekil_13_*`, `sekil_14_*` | Equity and drawdown curves; LLM decision distribution |
