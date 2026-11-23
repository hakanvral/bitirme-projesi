# Experiment instructions (verbatim, user message of 2026-11-23)

> Saved verbatim as requested; this is the authoritative spec for Step 0, Phases 5+6 (E1–E5) and Phase 7.

Phase 4 approved. Keep the free-tier pace (5–9 min per full analysis is fine; the demo will use cached runs).

STEP 0: prompt v3 (before any experiment, so E4/E5 use the final prompts)
- Glossary wording: VaR %99 (1 gün) = "100 günün 1'inde aşılabilecek kayıp eşiği", never "en kötü günlük kayıp". Factor sensitivities are "1 standart sapmalık haftalık harekete yüzde tepki", never "beta" (beta only for XU100).
- "temel_riskler" items must be short descriptive sentences, not bare numbers.
- "karari_degistirecek_kosullar": no new numeric thresholds. Use values present in the input or qualitative wording. Extend the numeric check so a number is matched together with its unit/context (field or keyword), so "%30" can't match an unrelated scenario "−%30". Add a test for this case.
- Add a final Turkish spelling/diacritics self-check instruction. Fix the spelling issues seen ("alınısa", "hissedenden").
- Bump to v3, rerun THYAO and ENJSA (full mode) and include the before/after in docs.

Then run the experiments (Phases 5 + 6 combined) and the final polish (Phase 7) per CLAUDE.md §6.5 and §10. Implement without waiting for plan approval. Run E1–E3 first, then E4–E5 in the background, resumable. Stop at the end with one summary. Log decisions in docs/DECISIONS.md.

E1: risk model validation
- Rolling 1-day VaR 95/99 for every stock, 2019-01 → latest. Refit every 5 trading days and apply the forecast to the next 5 days. Use fewer paths for 1-day VaR if needed (state how many) and parallelize across stocks. Target < 1 h.
- Models: HS, FHS, GBM, Merton, GARCH-t, the in-sample-critic choice and the hold-out-critic choice.
- Tests: exceedance rate, Kupiec POF, Christoffersen independence and conditional coverage, per model × universe (BIST30 / Energy / sub-sector) × regime.
- Key question: does the hold-out critic beat the in-sample critic and plain HS out of sample?

E2: factor model
- In-sample and out-of-sample R² for Model A/B (fit on 2 years, test on the next 26 weeks, rolling).
- Beta stability, max VIF, results by regime.
- Beta heatmap figure (stocks × factors, BIST30 vs Energy sub-sectors). Report Energy vs BIST30 with and without the TUPRS overlap.

E3: PPK event study
- All rate-change decisions since 2018. Abnormal returns over [−1, +5] days from a market model (estimation window [−250, −30]).
- Predicted response: the scenario engine fitted only on data before each event, with shock = actual policy-rate change.
- Report direction accuracy and MAE per universe/sub-sector, with bootstrap CIs. Holds are reported separately as realized reactions only. State the small-sample caveat.

E4: decision backtest (walk-forward, weekly)
- Window: 2025-11-03 → latest, plus a post-cutoff sub-window from 2026-06-01.
- Subset: 10 stocks (5 BIST30 + 5 Energy, the most liquid with a valid report at SELECTION_DATE; DSTKF excluded). Log the rule.
- Timing: decide at Friday close with data up to then; hold over the following week. Costs 10 bp + 5 bp slippage.
- Position mapping:
  - primary: AL = long, ALMA = cash, BEKLE = keep the previous position (start in cash);
  - sensitivity: BEKLE = 50% position.
- Report the decision distribution (AL/ALMA/BEKLE share) per variant and per stock. Flag it explicitly if BEKLE dominates (> 70%).
- Strategies:
  - buy & hold (each stock and equal-weight);
  - XU030;
  - rule-based risk filter (no LLM; also over the full 2019–2026 sample);
  - LLM lean mode, reasoning off: P, P+R, P+R+S, P+R+S anonymized.
- Metrics: cumulative return, CAGR, annualized vol, Sharpe and Sortino with TLREF as risk-free, max drawdown, Calmar, hit rate, turnover. All in TRY and USD.
- Significance: stationary-bootstrap CIs for Sharpe differences vs buy & hold and between ablations.

E5: LLM reliability
- k=5 repeats on 20 stock-weeks (lean): Fleiss' κ.
- Cross-model agreement on the same 20 stock-weeks: Nemotron 3 Ultra vs Kimi K3.1 Pro vs Gemma 4 31B (lean).
- Reasoning on vs off agreement on the same sample.
- Decision distribution per model (is there a BEKLE bias?).
- 6 full-mode analyses (3 BIST30, 3 Energy): auditor faithfulness and regeneration rate.
- Overall JSON failure rate and latency distribution.

OUTPUTS
- Every experiment writes CSV + LaTeX + PNG/SVG to results/<experiment>/<timestamp>/, with a config copy. `uv run python -m pusula.evaluation.paper_results` regenerates everything.
- docs/RESULTS.md: key E1–E5 numbers in compact tables, 2–3 plain-language sentences each, and a list of figures.
- Backtest & Değerlendirme page shows E1–E5.

PHASE 7: polish
- Genel Bakış page: macro snapshot + risk heatmap of both universes.
- `python -m pusula.demo.warmup`: pre-runs full analyses for THYAO, AKBNK, ENJSA and TUPRS so a live demo loads from cache.
- Turkish README: setup, data update, running the app, reproducing the paper results, required keys/files.
- Final tests + lint, cleanup, update PROGRESS and LIMITATIONS, commit and push.

Final summary: paste the key result tables (E1–E5) and the list of generated figures.