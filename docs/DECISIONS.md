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
