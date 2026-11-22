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
