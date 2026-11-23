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

**LLM variants** (lean, reasoning off, Nemotron 3 Ultra; evaluated only at ≥ 98 % coverage, D-074; status 2026-11-23 15:45 UTC)

| Variant | Coverage | Status |
|---|---|---|
| P+R+S | 540 / 540 (100 %) | ✅ evaluated |
| P | 112 / 540 | 🔄 running |
| P+R+S anonymised | 0 / 540 | ⏳ |
| P+R | 0 / 540 | ⏳ |

**LLM P+R+S vs the non-LLM strategies, TRY** (full window / post-cutoff window)

| Strategy | Cum. return | Ann. vol | Sharpe (TLREF) | Max DD | Avg. position | Weekly turnover |
|---|---|---|---|---|---|---|
| Buy & hold (EW) | +2.1 % / +0.2 % | 28.1 % | −1.16 / −1.16 | −18.3 % | 1.00 | 0.019 |
| Rule-based risk filter | +35.0 % / +18.5 % | 12.9 % | −0.67 / −0.15 | −9.3 % | 0.29 | 0.165 |
| **LLM P+R+S** (BEKLE = keep) | **+44.6 % / +18.3 %** | **6.5 %** | **−0.41 / −0.15** | **−1.9 %** | 0.22 | 0.006 |
| LLM P+R+S (BEKLE = 50 %) | +38.8 % / +16.2 % | 7.5 % | −0.87 / −0.63 | −2.4 % | 0.26 | 0.125 |
| XU030 | +17.7 % / −10.0 % | 27.2 % | −0.70 / −2.03 | −22.2 % | – | – |
| Cash (TLREF) | +48.8 % / +19.2 % | | | | 0 | |

Sharpe differences (stationary bootstrap, 95 % CI):

| Comparison | Full window | Post-cutoff |
|---|---|---|
| LLM P+R+S − buy & hold | +0.76 [−1.10, 2.71], p = 0.45 | +1.01 [−1.33, 4.37], p = 0.43 |
| LLM P+R+S − rule filter | +0.27 [−2.31, 2.76], p = 0.87 | +0.00 [−4.77, 4.85], p = 0.99 |

Decisions of P+R+S:
- AL 2.6 %, ALMA 51.7 %, BEKLE 45.7 %; no BEKLE dominance (< 70 %), no failed calls.
- By stock: mostly ALMA for the banks and small energy names (AKBNK, YKBNK 81 %, CANTE 91 %, ENERY 98 %); mostly BEKLE for THYAO (96 %), KCHOL (93 %) and TUPRS (85 %).
- The partial P variant (112 decisions) is 86 % BEKLE: price/trend information alone mostly leads to "wait"; to be confirmed when P is complete.

**In plain words (LLM part):**
- With risk and scenario information, the LLM was **very cautious**: it chose AL in only 2.6 % of stock-weeks and was invested 22 % of the time on average.
- In a year in which TLREF cash (+48.8 %) beat every equity strategy, this caution gave the **lowest volatility and drawdown** (−1.9 %) and the best Sharpe ratio of the equity strategies, but still less than cash (+44.6 %).
- **None of the Sharpe differences is statistically significant**: the 95 % intervals are wide and include zero (52 weeks, L-17). Much of the result comes from staying out of the market in a high-rate year, not from picking winners. The P, P+R and anonymised variants will show which input caused the caution.

## E5 · LLM reliability

*Pending: needs the Nemotron 3 Ultra endpoint (D-073).* The code, design and tests are in place (`src/pusula/evaluation/llm_reliability.py`, D-071):
- k = 5 repeats on 20 stock-weeks, Fleiss' κ;
- Nemotron vs Kimi K3.1 Pro vs Gemma 4 31B;
- reasoning on vs off;
- decision distribution per model;
- 6 full-mode audits;
- JSON failure rate and latency.

Evidence so far from P4 and Step 0 (full mode, 4 runs): the numeric audit passed in every final report, and the v3 prompts needed no regeneration (THYAO 165 numbers, ENJSA 213). Lean calls took ~2 s with reasoning off. Command:

```bash
PUSULA_LLM_RPM=20 PUSULA_LLM_CONCURRENCY=2 uv run python -m pusula.evaluation.llm_reliability --yes
```

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
