# Methodological decisions

Each entry: **decision**, alternatives considered, reason. This file becomes the paper's methodology
section. IDs are stable; superseded decisions are marked, never deleted.

---

## Kickoff review (2026-11-16)

### D-001 · Python 3.12, project at repository root
- **Decision:** Python 3.12; the package lives at the repo root (`src/pusula`).
- **Alternatives:** Python 3.11 (as first written in the brief); a `pusula/` subfolder.
- **Reason:** current numpy (2.5) and scipy (1.18) require ≥3.12. A subfolder adds a path level with no benefit.

### D-002 · Separate `SELECTION_DATE` for backtests and universe selection
- **Decision:** `SELECTION_DATE` = start of the E4 backtest window (default 2025-11-03). The energy selection uses only data up to that date, and E4 uses the BIST30 list in force on that date. `REFERENCE_DATE` (2026-11-01) is used only by the dashboard.
- **Alternatives:** one reference date for everything (as first written in the brief).
- **Reason:** choosing stocks by liquidity measured during the test window means test-period information leaks into the backtest (look-ahead).
- **Remaining limitation:** E1–E3 still use 2018–2026 history of today's constituents (survivorship bias), so see `LIMITATIONS.md` L-01.

### D-003 · Two CPI functions: historical deflation vs point-in-time
- **Decision:** `deflate_historical()` (full monthly CPI, interpolation allowed; used for describing the past) and `cpi_as_of(t)` (only prints released by *t*, carried forward with the last known monthly inflation rate; used for every "as of t" analysis and backtest).
- **Alternatives:** one daily-interpolated CPI series (as first written in the brief).
- **Reason:** interpolating between two monthly prints uses the *next* print, which is not yet published at *t*, so it is look-ahead.
- **Plain language:** to say what a stock earned in real terms in 2019 we can use all 2019 CPI data. To make a decision on a given day we may only use the inflation figures that had been announced by that day.

### D-004 · Merton jump-diffusion in core with robust calibration; GJR-GARCH optional
- **Decision:** Merton stays in the core model library and is calibrated with a simple threshold method (returns beyond ~3× robust σ are treated as jumps; intensity, jump mean and std come from them; the diffusion part comes from the rest; parameters are bounded; it falls back to GBM if there are too few jumps). GJR-GARCH moves to optional (P8).
- **Alternatives:** full maximum-likelihood Merton (often numerically unstable); dropping Merton.
- **Reason:** Merton is one of the base paper's target models. The threshold method is transparent and stable.

### D-005 · EPİAŞ PTF via manual CSV (core); live EPİAŞ API optional
- **Decision:** the day-ahead electricity price (PTF) is core data, loaded from a manual CSV exported from the EPİAŞ Transparency Platform. The live API adapter (CAS ticket auth) is optional.
- **Alternatives:** live API only (needs an account and auth flow, and the API changes often); dropping PTF.
- **Reason:** PTF is needed for the electricity-vs-others contrast (C3); the manual export is reliable and reproducible.

### D-006 · Structural cost control for the E4 LLM backtest
- **Decision:** a *lean backtest mode* (one structured decision call per stock-week that receives precomputed JSON, with no narrative agents and no Bull/Bear); the full Bull/Bear/Judge pipeline runs on a smaller random sample; the Auditor runs on a seeded ~10% sample; support for the Anthropic Message Batches API and prompt caching; a cost estimate and confirmation before every batch run.
- **Alternatives:** the full pipeline for every stock-week (~9,400 calls for 10 stocks × 52 weeks × 6 calls × 3 ablations).
- **Reason:** keeps the cost at student scale while the full pipeline is still evaluated on a sample.

### D-007 · LLM training cutoff and post-cutoff window
- **Decision:** `llm.training_cutoff = 2026-06-30` and `post_cutoff_start = 2026-07-01` in `config/settings.yaml`.
- **Source:** Anthropic models overview (platform.claude.com/docs/en/models/overview, checked 2026-11-16) lists **Training data cutoff: Jun 2026** (and reliable knowledge cutoff Jun 2026) for both `claude-sonnet-5-5` and `claude-haiku-5-5`. The month is given without a day, so we take the conservative end of the month.
- **Use:** results for the post-cutoff window (~4.5 months at kickoff) are reported as **supplementary**. Anonymized mode stays the **main** look-ahead control, because most of the 12-month test window is before the cutoff.

### D-008 · Rate-shock input: policy rate or market rate
- **Decision:** in the scenario lab the user enters the rate shock either as a policy-rate change (converted to a 2Y-yield change using **regime-specific** pass-through, shown with an uncertainty band) or directly as a 2Y-yield change.
- **Reason:** pass-through has been unstable (in 2021 rates were cut while market yields rose), so a single number would be misleading. Experts may prefer to shock the market rate directly.

### D-009 · Multicollinearity: VIF reported, OLS default, ridge optional
- **Decision:** report the Variance Inflation Factor for each factor; OLS with Newey–West standard errors stays the default; ridge regression is only an optional robustness check.
- **Plain language:** USD/TRY, CDS and interest rates tend to move together, so the model cannot cleanly separate their individual effects. VIF measures how bad this is. The *combined* effect of a scenario that moves them together is still estimated well.

### D-010 · Long-sample reference for non-LLM strategies
- **Decision:** buy & hold, XU030, equal-weight and the rule-based risk filter are also backtested over 2019-01-01 → today.
- **Reason:** 52 weekly LLM decisions give very wide Sharpe confidence intervals, so the long sample shows how the rule-based baseline behaves across regimes.

### D-011 · Secrets as environment / network secrets
- **Decision:** API keys are never written in chat or committed. Locally they go in `.env`; in the cloud environment they are injected by the network proxy as HTTP headers.
- **Consequence:** adapters send the key header only if a key is configured; behind the proxy a placeholder value is enough.

### D-012 · Default regime boundaries
- **Decision:** regime boundaries are placed at the PPK meetings that started a new policy direction: 2019-07-25 (first cut of the easing cycle), 2020-11-19 (sharp hike), 2021-09-23 (start of cuts despite high inflation), 2023-06-22 (normalization hike), 2024-12-26 (start of the 2024–26 easing). See `config/regimes.yaml`.
- **Alternatives:** statistical break detection (e.g. Bai–Perron), possibly as a robustness check later.
- **Reason:** policy-based boundaries are easy to explain. They will be cross-checked against `ppk_decisions.csv` once it is filled.

---

## Phase 1 · Data (2026-11-16)

### D-013 · Trading calendar = official XIST sessions
- **Decision:** the panel's business-day calendar is the official Borsa Istanbul calendar from `exchange_calendars` ("XIST"), limited to the date range of the stored XU100 data.
- **Alternatives:** the dates on which Yahoo's XU100 has a close (the plan before the data check).
- **Reason (found in the data):** Yahoo's XU100 misses real sessions (every 25 December 2018–2025 and 2021-04-02), while the stocks themselves have prices on those days. It also contains 2023-02-08, a day XIST treats as closed. The observed calendar is kept as a diagnostic (`compare_with_xist`).

### D-014 · Robust update: per-source failure isolation and manual fallback
- **Decision:** `python -m pusula.data.update` tries each series independently, logs the result to `update_log` (`ok` / `missing` / `error`) and continues. If an API fails, or an EVDS code is still `TODO_VERIFY`, it uses the series' manual CSV when one exists. Incremental runs re-download the last 10 days to pick up revisions; `INSERT OR REPLACE` keeps them idempotent.
- **Reason:** one broken source must not block the rest; reproducible and restartable.

### D-015 · Forward-fill rules per series
- **Decision:** `step` (policy rate: a decision holds until changed), `market` (daily market series: carried at most 5 business days, then left missing), `release` (monthly CPI / survey: visible only from its release date, then carried to the next release), `none`. **Stock prices are never forward-filled** (a missing day stays missing and shows in the quality report).
- **Reason:** keeps the panel point-in-time and makes data gaps visible instead of hiding them.
- **Plain language:** if Brent has no price on a Turkish trading day (e.g. a US holiday) we use the previous day's price, but not for more than a week. Inflation only "exists" in the model from the day TÜİK announces it.

### D-016 · Energy selection details
- **Liquidity:** median of close (unadjusted) × volume over the last 252 trading days before `SELECTION_DATE`. This approximates daily traded value in TRY, because Yahoo has no traded-value field.
- **Eligibility:** first price at least 3 years before `SELECTION_DATE`; no gap longer than 20 trading days in that window.
- **Size:** dropped. There is no free point-in-time market-cap history, so the composite score = liquidity rank (logged in the output).
- **Quotas:** the best-ranked names of each quota sub-sector are taken first; the remaining slots go to the best remaining names of any sub-sector (CLAUDE.md: "≥2 … the rest electricity"). Unmet quotas are reported, not hidden.
- **Open (user decision):** with the 3-year rule **no natural-gas candidate is eligible** at 2025-11-03 (AHGAZ listed 2022-12-26, ENERY 2023-08-23). See PROGRESS.md open issues.

### D-017 · EVDS adapter targets EVDS3
- **Decision:** base URL `https://evds3.tcmb.gov.tr/igmevdsms-dis/` with header `key`. The parameter format follows the EVDS API (`series=…&startDate=dd-mm-yyyy&endDate=…&type=json`). Metadata (`categories/`, `datagroups/`, `serieList/`) is wrapped by `python -m pusula.data.evds_lookup`.
- **Checked:** endpoint and auth on 2026-11-16 (`categories/` returned JSON with the key). Series download and codes are not yet verified live (see PROGRESS.md).

---

## P1 follow-ups (2026-11-16)

### D-018 · Policy rate from TCMB's official one-week repo table (not EVDS)
- **Decision:** `policy_rate` = lending rate of TCMB's "1 Hafta Repo" table (www.tcmb.gov.tr, Merkez Bankası Faiz Oranları → 1 Hafta Repo), dated from the day each rate took effect; step-filled.
- **Alternatives:** EVDS. Its metadata search found no daily one-week repo series, only the monthly BIS series `TP.BISPOLFAIZ.TUR` (too coarse for the event study).
- **Note:** the series jumps from 8.0% to 16.5% on 2018-06-01 without a PPK meeting. That date is not a rate decision: it is when the one-week repo rate was lifted to the 16.5% funding rate in mid-2018. Before that, the late liquidity window (LON) was the binding rate, so PPK decisions before 2018-06-01 are flagged in `ppk_decisions.csv` and must be handled separately in E3.

### D-019 · Risk-free rate before TLREF
- **Decision:** TLREF (`TP.BISTTLREF.ORAN`) starts 2018-12-28. For 2018 the interbank O/N weighted average rate (`TP.AOFO`, archive, until 2019-02-08) will be spliced in when computing Sharpe/Sortino (from P2/P6).
- **Reason:** both are overnight TRY money-market rates. The splice affects only 2018.

### D-020 · 2Y/10Y government bond yields stay manual
- **Decision:** EVDS has no benchmark-yield series (`bie_pydibs` holds per-bond, per-ISIN indicative values only), so `tr_2y` / `tr_10y` come from manual CSVs.
- **Open:** if no reliable source is found, the rate factor uses TLREF (allowed by CLAUDE.md §6.3: "2Y TRY yield (or TLREF)"). This will be decided in the P3 plan.

### D-021 · BIST30 lists from official Borsa Istanbul sources, with backward reconstruction
- **Decision:** the current list comes from `borsaistanbul.com/datum/hisse_endeks_ds.csv`. Past lists are rebuilt backwards with the quarterly "BIST Pay Endeksleri Dönemsel Değişiklikleri" announcements (added/removed shares per period) and checked against the announcement of the target period (`python -m pusula.universe.bist_index`).
- **Limitation:** changes *within* a period (delisting, merger, ticker change) are not in these announcements, so both lists are marked `pending_user_review`.

### D-022 · EPİAŞ live API needs local credentials
- **Decision:** the EPİAŞ adapter follows the official docs (TGT from `giris.epias.com.tr/cas/v1/tickets` via form fields, then `POST /electricity-service/v1/markets/dam/data/mcp` with header `TGT`). It reads `EPIAS_USERNAME`/`EPIAS_PASSWORD` from the local `.env`.
- **Finding:** credentials stored as a cloud network secret (HTTP header injection) cannot work: tested on 2026-11-16, the login answered "No credentials can be extracted to authenticate the REST request" because it accepts only form-body credentials. So in the cloud environment PTF falls back to `data/manual/ptf.csv`.

### D-023 · Conservative release-date rules when official dates are unavailable
- **Decision:** if no official release-date file exists, monthly series get a conservative release date: CPI → first BIST session on or after the **6th** of the following month; Sectoral Inflation Expectations (market participants, `TP.ENFBEK.PKA12ENF`) → first session on or after the **1st** of the following month. A user-provided `<id>_release_dates.csv` always takes precedence.
- **Reason:** the rules are meant never to be earlier than the real publication, so there is no look-ahead; the cost is a few days' delay in using the information. The official TÜİK release calendar could not be read automatically (the TÜİK data portal API answered "Erişim engellendi" / access denied), and TCMB publishes no history of survey dates. Evidence for the survey rule: the October 2026 report PDF was created on 2026-10-20, i.e. inside the reference month.
- **Plain language:** we pretend each inflation number became known a little later than it really did. That can only make the model slightly slower, never let it "see the future".

### D-024 · Corporate-action corrections in a separate cleaning step
- **Decision:** raw downloads (`data/raw/`, table `prices`) are never modified. Corrections from `config/corporate_actions.yaml` (ticker, date, type, ratio, source_url, note, status) are applied to a copy, the `prices_clean` table, which all analyses read. Only `status: confirmed` entries are applied, so a proposal never changes results before the user checks it on KAP.
- **Types:** bonus_issue, split, reverse_split, rights_issue (theoretical ex-rights price), factor (explicit, e.g. to undo a wrong vendor adjustment), bad_print.

### D-025 · Generic cleaning rules
- **Decision:** (1) rows on non-session days inside the data range are dropped (e.g. Yahoo rows on 2018-01-01 and 2023-02-08); (2) stale rows (zero volume and close equal to the previous close) are set to missing. 61 such rows were found, e.g. on 2020-03-11, where they would merge two Covid-crash days into one apparent "jump".

### D-026 · Jump thresholds by asset class, and jump review
- **Decision:** stocks ±10.5% (BIST main-market daily limit ±10% plus tick rounding), indices ±10%, FX ±10%, commodities ±25%. `python -m pusula.data.jump_review` classifies every flagged stock-day (market event / multi-day gap / vendor dividend error / split-bonus misadjustment / review) and writes proposals to `corporate_actions.yaml`.
- **Finding:** in the data, 10.5–20% moves are common in 2018–2020 and stop at about ±20%, with none in 2021. This fits a wider (±20%) band applying to many stocks before then, so the ±10% rule may not hold for the whole sample. I could not verify the official band history, so those cases are listed as `review` (58 cases) and not corrected.

### D-027 · Energy selection: per-sub-sector relaxed history rule
- **Decision:** the 3-year history rule stays the default. If a quota sub-sector cannot be filled, the rule is relaxed to 2 years **for that sub-sector only**, and those names are recorded with `entry_rule: 2y_relaxed`.
- **Result:** at 2025-11-03, natural_gas had no 3-year names, so ENERY and AHGAZ entered under the relaxed rule.

### D-028 · Pre-filled manual inputs
- **Decision:** `python -m pusula.data.prefill ppk` builds `ppk_decisions.csv` from TCMB's yearly PPK pages (decision dates plus press-release URL), with rates from the repo table and the press-release text as a cross-check. An existing file is never overwritten.

### D-029 · Earthquake closure, February 2023
- **Decision:** keep the XIST calendar, which has no session on 2023-02-08 and reopens on 2023-02-15.
- **Evidence:** Borsa Istanbul announcement no. 15151, dated 14.02.2023 ("Piyasaların Açılışı ile Birlikte Piyasa İşleyiş Esaslarında Yapılacak Değişiklikler Hk.", borsaistanbul.com/files/20230214-15151-Duyuru.pdf), confirms the reopening with changed market rules. I could **not** find an official Borsa Istanbul document stating that the trades of 2023-02-08 were cancelled, so that part remains unconfirmed.

### D-030 · Note for P4: LLM determinism (not implemented yet)
- Claude Sonnet 5.5 cannot disable extended thinking (Anthropic models overview), so `temperature=0` does not guarantee identical outputs. Reproducibility will rely on the on-disk response cache (keyed by model, prompt version and input hash), and run-to-run variation will be measured in E5.

---

## Phase 2 · Risk engine (2026-11-22)

### D-031 · Calibration window and minimum history
- **Decision:** models are fitted on the last 500 daily returns available at `as_of`. With fewer than 500 returns, all available returns are used (`short_history` warning). With fewer than **250**, no report is produced.
- **Reason:** 500 days ≈ 2 years covers more than one volatility episode; below ~1 year, GARCH-type estimates are unreliable.

### D-032 · Return construction
- **Decision:** daily log returns from `prices_clean` (adjusted close) on the official XIST calendar. Stock prices are never filled; a return spanning more than 5 missing sessions is dropped. USD basis = price / USD/TRY (EVDS); real basis = price / point-in-time CPI (`cpi_as_of`, D-003). Beta is always computed in TRY against XU100 (TRY).
- **Bug found and fixed while building this:** the CPI interpolation compared dates stored at different pandas time resolutions (pandas 3), which made the real basis explode. It now works in "days since 1970" floats.

### D-033 · Which inputs are committed
- **Decision:** reviewed public-source inputs are committed: `data/manual/ppk_decisions.csv` (TCMB, with source URLs), `config/corporate_actions.yaml`, `config/universe.yaml` (Borsa Istanbul). Files derived from investing.com (`cds_tr_5y.csv`, `tr_2y_yield.csv`, `tr_10y_yield.csv`) are **not** committed, because redistribution is not allowed; `data/manual/README.md` explains how to obtain them.

### D-034 · Critic: what is compared and how models are scored
- **Decision:** each fitted model simulates 200 paths as long as the calibration window, starting from its long-run state, and is compared with history at 1 day (all daily returns) and 10 days (non-overlapping simulated sums vs overlapping historical sums). There are 8 unit-free criteria per horizon: KS, Wasserstein/σ, |Δmean|/σ, |vol ratio − 1|, |Δskew|, |Δexcess kurtosis|, |Δq01|/σ, |Δq05|/σ. Each criterion is ranked across models; the score is the equal-weight average rank (user decision). Stored sensitivity checks: tail-heavy (×3 on q01/q05), moment-heavy (×3 on the moments), plus a diagnostic multi-day-only scheme (1-day criteria weighted 0).
- **Multi-day VaR** comes from the simulated paths (sum of daily log returns), not from "1-day × √10". The square-root rule assumes independent days with constant volatility, which underestimates risk when volatility clusters.
- **Result (universe runs 2025-11-03, 2026-11-13: 231 reports):** equal weights select **HS in 212**, FHS 14, GARCH-t 4, Merton 1. The selection changes between equal/tail/moment weights in 28 of 231 reports. With the multi-day-only diagnostic, the choices spread (HS 86, Merton 66, GBM 36, FHS 29, GARCH-t 14).
- **Interpretation for the paper:** the critic is in-sample, as in the base paper. HS reproduces its own window's 1-day distribution almost exactly, so it wins on the 1-day criteria; the 10-day criteria are where models really differ. Whether HS's in-sample win carries over out-of-sample is tested in E1 (Phase 5). An out-of-sample (hold-out) critic is a possible change, left for the user to decide.

### D-035 · Model failures
- **Decision:** if a model cannot be calibrated (optimizer non-convergence, non-stationary GARCH with α+β ≥ 0.999, Student-t ν ≤ 2.05, zero variance, non-finite simulation), it is skipped for that stock/date, the reason is stored in the `RiskReport`, and the critic chooses among the remaining models. Observed: 7 of 231 reports had a GARCH fit rejected as non-stationary (FHS 3, GARCH-t 4).
- **Merton** uses the threshold calibration from D-004 (3× robust σ; fallback to GBM with fewer than 3 jumps).

### D-036 · EVT on the full history
- **Decision (user):** the peaks-over-threshold tail index is fitted on the **full** history up to `as_of` (at least 750 returns), not on the 500-day window. Threshold = 95th percentile of losses, runs declustering with run length 5 (extremes less than 6 days apart = one event, keep its largest loss), GPD fitted to cluster peaks, at least **20** clusters; otherwise "EVT: yetersiz veri".
- **Reason:** 5% of a 500-day window is only about 25 days, and fewer clusters after declustering, too few to estimate a tail.
- **Result:** fitted in 222 of 231 reports. Estimates for short histories can be extreme (e.g. ENERY ξ ≈ −1.1 with 23 clusters) and must be read together with the number of clusters.

### D-037 · Risk level is relative
- **Decision (user):** the cutoffs 25/50/75 on the average of the volatility and CVaR99 (1-day) percentile ranks within the combined universe on the same date, in nominal TRY. The UI calls it **"evren içi göreli risk düzeyi"** and shows absolute annualized volatility and CVaR99 next to it.

### D-038 · E4 eligibility
- **Decision (user):** E4's default subset may only use names with a valid risk report at `SELECTION_DATE`. At 2025-11-03, **DSTKF** is excluded (183 daily returns < 250). The list is in `docs/e4_eligibility.md`, generated by `python -m pusula.risk.run_universe --as-of 2025-11-03`.

### D-039 · Price jumps under "review" are treated as real moves
- **Decision (user):** the 58 `review` jumps (10.5–20.5%) stay uncorrected. BIST's daily price band was likely wider (about ±20%) for many stocks before 2021 (consistent with the data; **unverified**). The 4 proposed corrections stay `proposed` until the user confirms them on KAP. The risk engine reads `prices_clean`, so confirming them later only requires `python -m pusula.data.update --only prices` and a rerun of `python -m pusula.risk.run_universe`.

---

## Phase 3 · Macro factor model & scenarios (2026-11-22)

### D-040 · Weekly factor panel
- **Decision:** Friday-close weekly data from the aligned panel (XIST calendar, fill rules D-015), as of `as_of`. Factors: rate (pp change), USD/TRY, Brent, TTF (log changes), CDS (bp), VIX (points), US10Y (pp), PTF (log; electricity names only). A factor needs ≥104 weeks of data; a stock needs ≥104 complete weeks. Sample: 2018 → as_of (463 weeks at 2026-11-20).

### D-041 · Rate factor without the 2Y yield
- **Decision (user):** as long as `tr_2y_yield.csv` is missing, the rate factor is **TLREF**, spliced with the interbank O/N rate before 2018-12-28 (D-019). If the 2Y file is added, `python -m pusula.data.update` plus a rerun switches automatically to the 2Y yield (`tr_2y` takes precedence).
- **Caveat:** an overnight rate follows the policy rate almost one-to-one, so the rate factor mostly measures policy moves, not changes in market expectations.

### D-042 · Policy-rate pass-through
- **Decision:** for each PPK meeting from 2018-06-01 to as_of, Δmarket = rate on the 5th session after the meeting − rate on the last session before it (window [−1, +5], as in E3); Δpolicy = new − previous rate. Per regime: least squares through the origin with a 90% band (t distribution). A regime with fewer than 3 rate changes uses the pooled estimate (flagged). Meetings with no change are kept.
- **Result (TLREF, as of 2026-11-20):** 2019–20 easing 0.81 [0.59, 1.03]; 2020–21 tightening 0.36 [0.00, 0.73] (only 3 changes); 2021–23 unorthodox 0.83 [0.59, 1.08]; 2023–24 normalization 1.01 [0.81, 1.22]; **current 2024–26 easing 0.97 [0.74, 1.21]**; 2018 uses the pooled 0.90 [0.80, 0.99].
- **UI:** the rate shock can be entered as a policy-rate change (converted with the current regime's pass-through; the band is propagated as low/high scenario runs and shown as error bars) or directly as a market-rate change.

### D-043 · Macro distribution for scenarios
- **Decision:** the cumulative h-week factor change ~ Normal(h·μ, h·Σ), with μ and Σ estimated from weekly changes in the **current regime** by default (selectable: full sample). Weekly changes are treated as independent. Horizons: 1 month = 4 weeks, 3 months = 13 weeks.

### D-044 · Isolated vs propagated
- **Decision:** propagated (default) draws the non-shocked factors from N(μ₂ + Σ₂₁Σ₁₁⁻¹(x₁ − μ₁), Σ₂₂ − Σ₂₁Σ₁₁⁻¹Σ₁₂). In isolated mode the non-shocked factors are **still random**, drawn from their unconditional distribution (mean = expected change).
- **Reason:** fixing them at their mean would remove macro noise from the scenario but not from the baseline, so ΔVaR would mix "shock" and "less noise". With both random, the comparison is fair.
- **Finding:** in the current data the weekly factor correlations are small (|ρ| ≤ 0.3; rate vs USD/TRY ≈ 0), so propagated and isolated results are close. Propagation will matter more once CDS and the 2Y yield are added.

### D-045 · Stock simulation and comparison
- **Decision:** Model A is used for scenarios. R = h·α + X·β + the sum of h weekly residuals bootstrapped from the stock's own history. The same macro draws and the same residual indices are used for every stock and for baseline and scenario alike (common random numbers), so differences come from the shock, not from simulation noise. Outputs: Δ expected simple return, ΔVaR/CVaR 95/99, ΔP(loss), ΔP(loss > 10%), rank change within each universe, and universe means **and medians** (with and without overlap names). USD view = TRY return − simulated USD/TRY change; there is no real view (CPI is not a factor). 10,000 paths.
- **Why Model A:** Model B's macro betas are identical to Model A's (the market residual is orthogonal to the factors), and its extra factor is not a macro shock.

### D-046 · Missing optional inputs
- **Decision (user):** without `cds_tr_5y.csv`, `ptf.csv` or the 2Y/10Y yields, the model runs without those factors, the pages show a clear warning, and shocks to missing factors are ignored and listed. Adding a file later only needs `python -m pusula.data.update` and a rerun (covered by a test).

### D-047 · Newly listed stocks
- **Decision:** the first 4 weekly returns after a stock's first price are dropped in the factor model (listing-period price discovery is not a macro response). Universe summaries report the median next to the mean.
- **Reason (found in the data):** ENERY's first trading week (+38%, 2023-09-01) and one joint shock week (2025-03-21: USD/TRY +3.7%, ENERY −18%) gave it a USD/TRY beta of −4.9. That single name drove the Energy average in the FX-shock scenario (ENERY −40% vs the other nine ≈ +1%). After the change: Energy mean −1.9%, median −1.1% (3 months, propagated).

### D-048 · Ridge and VIF
- **Decision:** ridge regression on standardized factors, with the penalty chosen by generalized cross-validation, as a robustness column only. VIF is reported per stock and for the factor set. **Result:** maximum VIF 1.57, i.e. no multicollinearity problem with the current factor set (CDS, which tends to move with USD/TRY and rates, is not yet included).

### D-049 · A rate source must have enough history
- **Decision:** a factor's source series is used only if it has at least 104 weeks of data up to `as_of`; otherwise the next candidate is used (for the rate factor: `tr_2y` → TLREF spliced). The page warns "tr_2y(short)".
- **Reason:** the first 2Y yield export (investing.com) covered only 2026-10-22 → 2026-11-20 (21 days). Without this rule it would have replaced TLREF and then been dropped as too short, removing the rate factor entirely.

---

## P2/P3 revisions and Phase 4 · Agents (2026-11-22)

### D-050 · Hold-out critic is the default (user revision)
- **Decision:** each model is calibrated on the first 80% of the 500-day window (400 days) and simulates the last 20% (100 days) forward from its state at day 400 (200 paths). The simulated 1-day and 10-day returns are scored against the **realized** last 100 days with the same 8 criteria and rank averaging. The chosen model is refit on all 500 days for the report. The in-sample critic (D-034) is kept as a reported variant (`selected_model_insample`, `score_insample`). Shorter windows use the same 80/20 split.
- **Reason:** in-sample, HS resamples the very history it is scored on, so it wins structurally.
- **Result (231 reports, 2025-11-03 and 2026-11-20):**

| Selected model | Hold-out (default) | In-sample |
|---|---|---|
| GBM | 63 | 0 |
| GARCH-t | 54 | 4 |
| HS | 53 | 209 |
| FHS | 47 | 17 |
| Merton | 14 | 1 |

- Per-run distributions are in `results/risk_universe/<run>/model_choice.csv`.

### D-051 · Scenario results in TRY, USD and real terms (user revision)
- **Decision:** scenario results are computed in three bases. **USD** = TRY log return − the simulated USD/TRY change of the same path. **Real** = TRY log return − expected inflation over the horizon, h/52 · ln(1 + π), where π is the latest market-participants 12-month CPI expectation released by as_of (deterministic; CPI is not a simulated factor). Batch outputs (`scenario_results`, `universe_summary.csv`) contain all three bases. Both pages have a basis toggle. On BIST30 vs Enerji, the USD view lowers the USD/TRY beta by exactly 1, and the real view leaves betas unchanged.
- **Note for the paper:** a TRY depreciation shock can **raise nominal TRY prices** (exporters, FX-linked revenues) while **lowering the same stock's USD value**. Example (2026-11-20, 3 months, propagated): Kur şoku → BIST30 mean −0.2% in TRY but −7.2% in USD; Energy −1.3% in TRY but −8.3% in USD.

### D-052 · New data: CDS and the 2Y yield; rate-factor comparison
- **Decision (user rule):** the 2Y yield (investing.com export, 2018-01-02 → 2026-11-20, 2,141 days) now has more than 2 years of history, so it is the rate factor; TLREF is kept as a robustness comparison (`rate_source_comparison.csv`). CDS (2018-01-01 → 2026-11-19, 2,308 days) enters as a factor. The earlier, too short exports (21 and 20 days) were handled by D-049.
- **Results (Model A / Model B mean R²):** BIST30 0.140 / 0.462 and Energy 0.091 / 0.286 (before: 0.057 / 0.458 and 0.054 / 0.283). CDS is significant for 90% of stocks; max VIF 1.64.
- **Pass-through to the 2Y yield is weak:** current regime β = 0.19 (90% band −0.29 … 0.67); pooled 0.10 [−0.03, 0.23]. With TLREF it was 0.97. Policy-rate scenarios therefore move the market rate much less, and their effects shrink. For example, faiz artırımı +500 bp (3 months, TRY): BIST30 −1.35% (2Y) vs −2.85% (TLREF); Energy −1.16% vs −0.66%. Plain language: the 2-year yield already prices in expected policy, so on decision days it moves far less than the overnight rate.
- **CDS scenario (Ülke riski +200 bp, 3 months, propagated):** BIST30 −16.0% (median −16.1%), Energy −11.4% (median −11.8%) in TRY; −17.3% / −12.9% in USD. In isolated mode: −10.7% / −6.7%.

### D-053 · Extrapolation guard for propagated scenarios
- **Decision:** a shock's size is measured in standard deviations of the selected regime's h-week distribution. If any shock lies beyond **4 sd**, propagated mode uses the **full-sample** moments for that run (baseline and scenario), and the run records `extrapolation_guard` and the z-score. The page warns.
- **Reason (found in the data):** in the current regime USD/TRY is tightly managed (weekly σ 0.37%), so a +15% shock is about 25 sd outside the regime. Gaussian conditioning then extrapolated absurd companion moves (rate +24 pp, CDS +166 bp, VIX −14), giving −18% for both universes. With the guard, Kur şoku uses the full sample (z = 6.9); all other presets stay below 4 sd and keep the regime covariance.

### D-054 · LLM provider: NVIDIA NIM free tier via an OpenAI-compatible client (user decision)
- **Decision:** `OpenAICompatibleClient` is the default (`https://integrate.api.nvidia.com/v1`, `Authorization: Bearer`, key `NVIDIA_API_KEY` stored as a cloud network secret). The same client serves Ollama (`http://localhost:11434/v1`) and other compatible providers. `AnthropicClient` is optional; `MockLLMClient` is used in all tests. Settings live in `config/settings.yaml` (`llm`), with `.env` overrides. The Message Batches API and prompt caching were dropped (not available).

### D-055 · Model choice (comparison for the paper)
Test: the same real analysis (THYAO, 2026-11-20, full mode, 6 calls), a lean decision call and an auditor-only call, on NIM's free tier.

| Model | Role tested | Result |
|---|---|---|
| nvidia/nemotron-3-ultra-550b-a55b | full pipeline (THYAO, ENJSA), lean, auditor | Valid JSON at the first attempt in 11 of 12 agent calls (1 auditor retry). Numeric audit 222/222 and 185/185 numbers found in the input; consistency OK; fluent, careful Turkish. ~25–70 s per call with reasoning on (≈250–270 s per full analysis); lean 14–38 s with reasoning on, **~2 s with reasoning off** |
| nvidia/nemotron-3.5-lightning-30b-a3b | auditor, lean | Auditor: empty replies 3/3 (failed). Lean: valid, 6.5 s, but weaker Turkish (mixes English terms) |
| z-ai/glm-5.3-flash | auditor | Empty replies 3/3, 698 s (failed) |
| mistralai/mistral-large-4-1t-a52b | full pipeline | see the PROGRESS note (still running at the time of writing; the probe gave empty content at 600 tokens and ~50 s per call) |
| moonshotai/kimi-k3.1-pro | full pipeline | see the PROGRESS note (probe: empty content / timeouts) |
| google/gemma-4-31b-it | lean | probe: timeouts at 120 s |

- **Decision:** **Nemotron 3 Ultra** for the analysts, decision and auditor. No smaller model passed the auditor test, so `model_light` = the same model.
- **Caveat:** Turkish is **not** in the model card's list of supported languages; quality is judged on the outputs (examples in PROGRESS / the P4 summary).

### D-056 · Structured output
- **Decision:** JSON mode (`response_format: json_object`) when the endpoint accepts it; if it is rejected, the client switches it off and relies on "answer with JSON". Replies are extracted (code fences, `<think>` blocks and prose tolerated), validated with pydantic, and on failure retried up to 2 times with the validation error fed back. JSON failures are logged per call (`llm_usage.json_failures`) for E5. Schemas enforce the disclaimer sentence and exactly 3 reasons for / against.

### D-057 · Rate limiting and resumable batches
- **Decision:** one sliding-window limiter per process (default 35 requests/min, configurable), exponential backoff with jitter on 429/5xx/timeouts (honours `Retry-After`, up to 6 retries), up to 4 parallel requests in batch runs. Batches are resumable because every call goes through the SQLite cache keyed by (provider, model, prompt version, input hash). Usage is logged as tokens and latency; `cost_usd` = 0 on the free tier (the field is kept for paid providers).

### D-058 · Auditor
- **Decision:** (1) a deterministic numeric check: every number in every report must match a number in the input JSON (values, numbers inside strings, digits in key names) within 2% relative or 0.051 absolute. Turkish formats are normalized: decimal comma, thousands dots, "%" before/after (and a sign before "%"), fraction vs percent (0.0497 ≈ %4,97), bp/"baz puan" vs percentage points. Names such as XU100/BIST30 are not numbers, and small structural integers (0–13, 21, 26, 52, 63, 95, 99, 100) are always allowed. (2) An LLM consistency check (decision vs risk level, contradictions between reports, deciding the risk level, presenting advice). On a numeric failure the offending report is regenerated once with the numbers fed back; on a consistency failure the decision is regenerated once with the issues fed back. Both events are recorded.
- **Inputs** give ratios in percent with 2 decimals (`*_yuzde`), so the model can quote them without rescaling.

### D-059 · Orchestrator modes and ablations
- **Decision:** `run_analysis(ticker, as_of, scenarios, mode, ablation)` with mode ∈ {full, lean, anonymized} and ablation ∈ {P, P+R, P+R+S}. Full = Risk Analisti (if R), Senaryo Analisti (if S), Bull, Bear, Judge, then the auditor. Lean = one structured decision call on the precomputed JSON, with the free numeric audit only. Every run is persisted (`analysis_runs` plus `results/analysis_runs/<date>/…json`) with prompt versions, inputs, outputs, audit, tokens and latency.

### D-060 · Anonymized mode
- **Decision:** ticker → "Hisse A"; universe → "Grup A" (BIST30) / "Grup B" (Energy); no company name or sub-sector; the analysis date is replaced by "t"; BIST30/Enerji mentions inside input strings are replaced too. Tested: no ticker, name, sector or year appears in the input.

### D-061 · Reasoning off for lean calls
- **Decision:** lean (E4) calls send `chat_template_kwargs: {enable_thinking: false}` (documented on the model card). Full-mode narratives keep reasoning on.
- **Evidence:** on 3 stocks (THYAO, ENJSA, AKBNK), reasoning off gave **the same decision** in 3/3 cases (confidence within ±0.05), with 0 numbers outside the input, ~2 s and ~100 output tokens per call, vs 18–38 s and 1,150–2,900 tokens with reasoning on.

### D-062 · Training cutoff of the configured model
- **Decision:** `llm.training_cutoff = 2026-05-31` and `post_cutoff_start = 2026-06-01`, from the Nemotron 3 Ultra model card: *"The post-training data has a cutoff date of May 2026. The pre-training data has a cutoff date of September 2025."* The later date is used, conservatively. Hosts `build.nvidia.com` and `huggingface.co` were added to the environment to read the card. The E4 post-cutoff window is now 2026-06-01 → today; anonymized mode remains the main control.
