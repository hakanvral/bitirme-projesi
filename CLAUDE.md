# PUSULA — Macro-Conditioned Agentic Risk Analysis Platform for Borsa Istanbul

> Project memory for Claude Code. Read this whole file before every task. Keep it up to date when decisions change.

---

## 0. How to work with me (read first)

- I am a **solo 4th-year undergraduate** building this as my **graduation project** and I will also write an **academic paper** from it. I am not a finance expert: whenever you make a financial / statistical choice, explain it in 2–3 plain sentences.
- Work **one phase at a time** (see §10). At the end of each phase:
  1. run `ruff` and `pytest`,
  2. update `docs/PROGRESS.md`,
  3. give me a short summary: what was built, how to run it, what is verified by tests, open issues / what I must provide,
  4. **STOP and wait for my approval** before starting the next phase.
- At the start of each phase, first show a short plan (files, libraries, decisions, open questions). Implement only after I approve.
- Prefer **simple, readable, well-documented code** over clever abstractions. My professor will read this code.
- **Never invent** data, ticker lists, index constituents, API endpoints, EVDS series codes or numeric results. If unsure, check the current official docs. If an API is unreachable, build the adapter anyway **plus a manual-CSV fallback** and tell me exactly what file to download and where to put it.
- Log every non-trivial methodological decision in `docs/DECISIONS.md` (decision, alternatives considered, reason). This becomes the paper's methodology section.
- Do not add features that are not in this file without asking.

---

## 1. Project summary

PUSULA is inspired by BlackRock's Aladdin: instead of picking stocks blindly, an investor can (1) see the **risk profile** of a stock, (2) simulate **"what happens if…" macroeconomic scenarios** (e.g. the TCMB policy rate is cut or hiked, USD/TRY jumps, oil spikes), and (3) receive an **explained decision-support output** (reasons to buy / reasons not to buy) produced by a team of AI agents.

**Universes:** BIST30 stocks and 10 rule-selected **energy** stocks (electricity, natural gas, refining/petroleum products) from Borsa Istanbul. The two groups share common macro drivers but react differently. **Comparing them is a core result.**

### 1.1 Base paper

Emmanoulopoulos, D., Olby, O., Lyon, J., Stillman, N. R. (2025). *To Trade or Not to Trade: An Agentic Approach to Estimating Market Risk Improves Trading Decisions.* arXiv:2507.08584.

What we take from it:
- A builder–critic loop that fits a stochastic price model and validates its simulated paths against history (KS, Wasserstein, moments, tails).
- Monte Carlo simulation → risk metrics (VaR, CVaR, max drawdown, EVT tail analysis) → passed to a trading agent.
- Ablation idea: an agent **without** model-based risk metrics vs **with** them.
- Evaluation with PnL, Sharpe ratio and max drawdown against buy-and-hold.

### 1.2 Our contributions (what makes this work different)

| # | Contribution | Gap in base paper |
|---|---|---|
| C1 | **Macro-conditioned risk**: a factor model links stock returns to macro variables; scenario shocks drive a conditional Monte Carlo | Base paper uses 1-D price-only SDEs, no macro variables |
| C2 | **Emerging, high-inflation market**: analysis in nominal TRY, real (CPI-deflated) TRY and USD terms | Base paper: 4 US stocks |
| C3 | **Two-universe comparison**: BIST30 vs Energy under identical shocks | Single small universe |
| C4 | **Deterministic tools + LLM interpretation + Auditor agent** that verifies every number in reports | LLM numerical faithfulness not checked |
| C5 | **Event study on TCMB rate decisions** to validate scenario responses against reality | Only synthetic scenario |
| C6 | **Look-ahead-bias controls** (point-in-time data, anonymized-ticker mode) and **LLM consistency** measurement | Pre-training bias acknowledged but not tested |
| C7 | **Interactive dashboard** (Aladdin-like panel) | No UI |

---

## 2. Non-negotiable principles

1. **Python computes, the LLM interprets.** All numbers (risk metrics, betas, scenario impacts, risk levels) are computed by deterministic Python code. Agents receive precomputed JSON and only explain and reason over it. Every number in an agent report must exist in that agent's input.
2. **Point-in-time correctness.** Any analysis "as of date t" uses only data available at t. That includes release lags: monthly CPI is usable only after its publication date. No look-ahead anywhere, especially in backtests.
3. **Reproducibility.**
   - Fixed random seeds and config-driven runs (YAML).
   - LLM calls cached on disk, keyed by a hash of (model, prompt version, input).
   - Every experiment writes to `results/<experiment>/<timestamp>/` together with a copy of its config.
4. **Returns.** Use log returns. Every analysis can be shown in three bases: **nominal TRY**, **real TRY** (CPI-deflated) and **USD**.
5. **Not investment advice.** Every UI page shows: *"Bu uygulama akademik bir çalışmadır; yatırım tavsiyesi değildir."* The decision agent's output is called **"karar destek"**, never "tavsiye".
6. **Language.**
   - English for code, comments, docstrings, commit messages and LLM system prompts.
   - Turkish for all UI text and for the agents' final reports.
   - All UI strings live in one place (`src/pusula/app/i18n_tr.py` or a YAML file).
7. **Secrets.** API keys only in `.env` (git-ignored); provide `.env.example`. Never print keys.
8. **Cost safety.**
   - LLM calls happen only on explicit user action (button / CLI flag), never on page load.
   - Any batch LLM job first prints estimated call count and cost, and asks for confirmation.

---

## 3. Tech stack

| Area | Choice |
|---|---|
| Language | Python **3.12** (numpy ≥2.5 / scipy ≥1.18 require it), `pyproject.toml`, **uv** for env & deps |
| Data / math | pandas, numpy, scipy, statsmodels, arch (GARCH), scikit-learn (only if needed) |
| Data access | yfinance, requests / httpx |
| Storage | **DuckDB** (`data/pusula.duckdb`) + Parquet snapshots of raw downloads |
| Config & schemas | pydantic v2, pydantic-settings, YAML configs in `config/` |
| LLM | Own `LLMClient` interface; default `OpenAICompatibleClient` → **NVIDIA NIM free tier** (also Ollama / any OpenAI-compatible endpoint); `AnthropicClient` optional (D-054) |
| Orchestration | **Plain Python pipeline** (no LangChain/LangGraph); easier to explain in the paper |
| UI | **Streamlit** (multipage) + Plotly, runs locally in the browser |
| Quality | pytest, ruff, type hints everywhere |

**LLM defaults** (`config/settings.yaml` → `llm`, overridable in `.env`; D-054, D-055):
- provider `openai_compatible`, base_url `https://integrate.api.nvidia.com/v1`, key `NVIDIA_API_KEY` (cloud: network secret)
- model `nvidia/nemotron-3-ultra-550b-a55b` for analysts, decision **and** auditor (no smaller model passed the auditor test)
- 35 requests/min client-side limit, up to 4 parallel requests, temperature 0.2, max 16384 tokens (hidden reasoning needs room, D-068)
- lean (E4) calls: reasoning off (`enable_thinking: false`, D-061)
- cost = 0 on the free tier: track tokens and latency (cost fields kept)

---

## 4. Universes

### 4.1 BIST30

- Two dates (both in `config/settings.yaml`):
  - `REFERENCE_DATE` (default `2026-11-01`): "today's" universe, used by the dashboard.
  - `SELECTION_DATE` (default `2025-11-03`, i.e. the **start of the E4 backtest window**): the universe used for all backtests (E4) and for the energy selection, so that no test-period information leaks into stock selection.
- `config/universe.yaml` holds **two** BIST30 lists, one per date. **Do not fill them from memory.** I paste both official lists from Borsa Istanbul.
- Remaining limitation (must appear in the paper): E1–E3 use 2018–2026 history of stocks that are in the universe *today* → survivorship bias. Documented in `docs/LIMITATIONS.md`.
- Write a validator that checks each ticker downloads via yfinance (`<TICKER>.IS`) and reports problems.

### 4.2 Energy (10 stocks): rule-based, reproducible selection

Sub-sectors:
- `electricity`: generation, distribution, retail
- `natural_gas`: distribution / trading
- `refining_petroleum`: refining, LPG / fuel distribution

Candidate pool: `config/energy_candidates.yaml`. Each entry has `ticker`, `name` and `sub_sector`.
- Exclude **equipment manufacturers** (transformers, cables, solar panels, EPC contractors). The rule: the company's main revenue must come from producing, distributing or trading energy.
- Seed the pool with well-known names (e.g. TUPRS, AYGAZ, ENJSA, AKSEN, ZOREN, ODAS, AHGAZ, ENERY, AKFYE, AYDEM, GWIND, NATEN, ENTRA, CANTE, BIOEN, ESEN). Mark every entry `verified: false` until I confirm it.

Selection algorithm (`src/pusula/universe/select_energy.py`):
1. Eligibility: at least 3 years of daily price history before `SELECTION_DATE`, and no long trading halts. **All selection inputs use data up to `SELECTION_DATE` only.**
2. Liquidity: median daily traded value (TRY) over the last 12 months.
3. Size: market cap if reliably available; otherwise use liquidity only, and log that decision.
4. Composite score = average of the ranks.
5. Sub-sector quotas: **≥2 `refining_petroleum`, ≥2 `natural_gas`**, the rest `electricity`. If a quota cannot be met, report it.
6. Overlap with BIST30 is **allowed and flagged** (`in_bist30: true`). Universe comparisons are reported both **with and without** overlapping names.
7. Outputs: `config/energy_selected.yaml` and `docs/universe_selection.md` (score table for the paper's appendix).

---

## 5. Data

Period: **2018-01-01 → today**. This window includes regime changes that the analysis must allow splitting on:
- the 2018 currency crisis,
- the 2021–2023 unorthodox low-rate period,
- the mid-2023 policy normalization,
- the 2024–2026 easing cycle.

Default regime boundaries go in `config/regimes.yaml`.

All series are declared in `config/data_sources.yaml`. **EVDS series codes must be looked up in EVDS, not guessed** (Claude verifies them via the EVDS metadata endpoints; until verified they stay `TODO_VERIFY`). EVDS moved to **EVDS3** in 2025: API base `https://evds3.tcmb.gov.tr/igmevdsms-dis/`, API key sent in the HTTP header `key` (evds2 redirects to evds3). Each source has an adapter plus a manual-CSV fallback (`data/manual/<series>.csv`, documented schema).

| Group | Series | Freq | Purpose | Source (fallback: manual CSV) |
|---|---|---|---|---|
| Prices | OHLCV for all universe tickers | D | Everything | yfinance `.IS` |
| Indices | XU100, XU030, XELKT (if available) | D | Market beta, benchmarks | yfinance / manual |
| TR rates | TCMB policy rate (1-week repo) | D (step) | Scenario input | TCMB website "1 Hafta Repo" table (EVDS has no daily series; D-018) |
| TR rates | TLREF | D | Market rate; risk-free rate for Sharpe | EVDS / manual |
| TR rates | 2Y (and 10Y) benchmark government bond yield | D | Rate factor, yield-curve slope (banks) | EVDS if available, else manual |
| FX | USD/TRY, EUR/TRY | D | FX factor, USD-based returns | EVDS / yfinance `TRY=X` |
| Inflation | CPI index (2025=100, `TP.TUKFIY2025.GENEL`) + **release dates** | M | Real returns, scenarios | EVDS (TÜİK); release dates: official file if provided, else conservative rule (D-023) |
| Expectations | Market participants survey: 12-month CPI expectation | M | Context, real rate | EVDS |
| Country risk | Türkiye 5Y CDS | D | Risk premium factor | manual CSV |
| Global | Brent (`BZ=F`), TTF gas (`TTF=F`), VIX (`^VIX`), US 10Y (`^TNX`), DXY | D | Global / commodity factors | yfinance |
| Energy | EPİAŞ PTF (day-ahead electricity price, hourly → daily average) | D | Electricity revenue driver (**core**, needed for C3) | **Core: manual CSV export** from the EPİAŞ Transparency Platform website. Live API adapter (account + CAS ticket from `giris.epias.com.tr`) is **optional** |
| Events | TCMB MPC (PPK) decisions: date, previous rate, new rate, change (bp), market expectation if available | Event | Event study, pass-through | `data/manual/ppk_decisions.csv`, pre-filled from TCMB's PPK pages with a source URL per row (`python -m pusula.data.prefill ppk`, D-028); user reviews |

Data engineering requirements:
- Raw downloads go to `data/raw/<source>/<YYYYMMDD>.parquet`. Cleaned data goes to DuckDB tables: `prices`, `macro`, `events`, `universe`, `analysis_runs`, `llm_usage`.
- Aligned panel builder:
  - business-day calendar of Borsa Istanbul,
  - explicit forward-fill rules per series (e.g. policy rate: step; CPI: only after release date),
  - optional weekly resampling (Friday close).
- **Corporate actions:** Turkish stocks have frequent bonus issues ("bedelsiz"). Use adjusted prices; flag daily moves above **±10.5% for stocks** (indices ±10%, FX ±10%, commodities ±25%; D-026) and classify them with `python -m pusula.data.jump_review`. Corrections live in `config/corporate_actions.yaml` and are applied in a cleaning step to the `prices_clean` table; raw data is never modified, and only `status: confirmed` entries are applied (D-024, D-025).
- **EVDS** returns at most ~1000 items per request, so daily series are fetched in ≤900-day windows.
- **Data quality report:** coverage %, missing days, stale prices, flagged jumps and last update per series. Shown on the "Veri Durumu" page.
- One command updates everything: `uv run python -m pusula.data.update` (incremental).

---

## 6. Methodology

### 6.1 Returns & features (`pusula/features`)

- Log returns: daily and weekly.
- Real returns. Two separate, explicitly named functions (never mix them):
  - `deflate_historical()`: for describing the past ex post; uses the full monthly CPI series (interpolation allowed).
  - `cpi_as_of(t)`: for any "as of t" analysis or backtest; uses only CPI prints **released** by t, carried forward from the last release with the last known monthly inflation rate. No interpolation towards an unreleased print.
- USD-based returns.
- Trend metrics for the decision agent: RSI(14), price vs 50/200-day MA, 3/6/12-month momentum, distance from 52-week high.

### 6.2 Risk engine: tools for Agent 1 (`pusula/risk`)

Simplified, deterministic version of the base paper's builder–critic loop.

**Model library** (fixed code, not LLM-written):
- Historical Simulation (HS)
- Filtered HS
- GBM
- Merton jump-diffusion (**core**; it is a base-paper target model). Simple, robust calibration: jumps = returns beyond a threshold (e.g. 3× robust σ), jump intensity/mean/std from those, diffusion from the rest; parameter bounds + fallback to GBM if too few jumps.
- GARCH(1,1) with Student-t innovations
- GJR-GARCH (**optional**)

**Calibration:** rolling window, default 500 trading days (configurable).

**Critic / model selection:**
- Simulate N paths (default 10,000, seeded).
- Score each model against history: KS statistic, Wasserstein distance, moment match (mean, vol, skew, kurtosis), tail match (1% and 5% quantiles).
- Pick the best model by weighted total score.
- Store all scores; they are shown in the UI and in the paper.

**Outputs** (pydantic schema `RiskReport`):
- VaR 95/99 at 1-day and 10-day horizons
- CVaR / Expected Shortfall
- P(loss > 10%) over 1 month
- Max-drawdown distribution
- Annualized volatility
- Beta to XU100
- EVT peaks-over-threshold tail index **with declustering** (fixes a limitation of the base paper)
- Fan-chart percentiles

**Deterministic risk level** (Düşük / Orta / Yüksek / Çok Yüksek), computed from the volatility and CVaR percentile within the combined universe. The LLM explains this label; it does not decide it.

### 6.3 Macro factor model & scenario engine: tools for Agent 2 (`pusula/macro`)

**Factor model** (weekly frequency, to reduce noise and timing mismatch between BIST and global closes):

`r_i,t = α_i + Σ_k β_i,k · Δf_k,t + ε_i,t`

Factors (Δ = change / log-change):
- 2Y TRY yield (or TLREF)
- USD/TRY
- Brent
- TTF
- CDS
- VIX
- US 10Y
- for electricity names only: PTF

Model variants:
- **Model A**: macro factors only.
- **Model B**: adds a market residual (XU100 orthogonalized on the macro factors).

Estimation:
- OLS with Newey–West (HAC) standard errors (default).
- Report **VIF** for every factor (multicollinearity check: USD/TRY, CDS and rates co-move).
- Ridge regression only as an **optional robustness check**.
- Rolling 2-year betas to show instability.
- Results split by regime.

**Policy-rate pass-through.** Users think in policy-rate terms ("faiz 36 → 33"), but the factor is a market rate.
- Estimate how policy-rate changes pass through to the 2Y yield / TLREF using PPK event data.
- A scenario "policy rate −300 bp" is converted to an implied Δ2Y using **regime-specific** pass-through, always shown **with an uncertainty band**.
- In the UI the rate shock can be entered **either** as a policy-rate change (converted as above) **or** directly as a market-rate (2Y yield) change.
- The current policy rate is **read from data, never hard-coded**.

**Joint macro behaviour.** A rate cut usually moves TRY too. Two scenario modes:
- `isolated`: only the shocked factors move; all other factors stay at their expected change.
- `propagated` (default): the non-shocked factors follow their **conditional Gaussian distribution** given the shock, `μ₂ + Σ₂₁Σ₁₁⁻¹(x₁ − μ₁)`, using the macro covariance from the selected regime. A VAR(p) impulse-response variant is optional (Phase 8).

**Scenario simulation:**
- Horizons: 1 month and 3 months.
- Simulate macro paths conditional on the shock, add idiosyncratic noise by bootstrapping residuals, and get each stock's return distribution.
- Compare with the baseline (no-shock) run: Δ expected return, Δ VaR / CVaR, P(loss), and rank changes within each universe.

**Historical analogues:** find past windows with similar macro moves and show realized returns, as a sanity check next to the model output.

**Preset scenarios** in `config/scenarios.yaml` (Turkish names; shocks may be combined):
- Faiz indirimi (−300 bp)
- Sert faiz indirimi (−750 bp)
- Faiz artırımı (+500 bp)
- Kur şoku (USD/TRY +%15)
- Petrol şoku (Brent +%30)
- Petrol çöküşü (Brent −%30)
- Doğalgaz şoku (TTF +%50)
- Ülke riski artışı (CDS +200 bp)
- Küresel risk-off (VIX +15, US10Y +50 bp)
- Stagflasyon (kur +%10, faiz +300 bp, Brent +%20)

Users can also build custom scenarios in the UI.

### 6.4 Agents (`pusula/agents`, `pusula/llm`)

**LLM layer:**
- `LLMClient` interface: `generate(system, user, schema) → pydantic model`.
- Implementations:
  - `AnthropicClient`
  - `MockLLMClient` (deterministic, used in all tests)
  - `OllamaClient` stub (filled in during Phase 8)
- JSON-schema-validated structured output, with up to 2 retries.
- SQLite disk cache.
- Token and cost logging to the `llm_usage` table.
- Prompts live in `pusula/agents/prompts/*.md` with a `prompt_version`, which is stored in every output.

**Agents.** All final texts are in Turkish.

| Agent | Input | Output (pydantic) |
|---|---|---|
| **1. Risk Analisti** | `RiskReport` JSON (+ universe percentiles) | `RiskNarrative`: summary, risk level explanation, main risk drivers, what the metrics mean for a non-expert |
| **2. Senaryo Analisti** | Scenario results for selected scenarios (+ peer comparison) | `ScenarioNarrative`: which scenarios hurt or help and why (via betas), most sensitive factor, BIST30-vs-Energy contrast |
| **3. Karar Ajanı** | Agent 1 & 2 outputs + structured metrics + trend metrics | First a **Bull** call and a **Bear** call (arguments), then a **Judge** call producing `Decision`: `{karar: AL / ALMA / BEKLE, guven: 0–1, vade, lehte_gerekceler[3], aleyhte_gerekceler[3], temel_riskler, karari_degistirecek_kosullar}` |
| **4. Denetçi (Auditor)** | All reports + all input JSON | `AuditResult`. (a) Deterministic numeric check: extract every number from the reports and match it to the inputs within a tolerance. (b) LLM consistency check, e.g. a decision that contradicts the risk level without saying why. On failure, regenerate once and record that it happened. |

**Orchestrator** (`pusula/pipeline.py`):

`run_analysis(ticker, as_of, scenarios, mode)`
1. Build point-in-time context.
2. Run the deterministic tools.
3. Run Agents 1 & 2.
4. Run Agent 3.
5. Run the Auditor.
6. Persist an `AnalysisRun` (DuckDB + JSON) for the UI.

**Anonymized mode** (`mode="anonymized"`): replace ticker and company names with "Hisse A", and absolute dates with relative ones. Used to test look-ahead / memorization bias.

### 6.5 Evaluation (`pusula/evaluation`): the paper's results section

**E1 · Risk model validation**
- Rolling 1-day VaR 95/99 backtests per stock: exceedance rate, Kupiec POF test, Christoffersen independence and conditional coverage tests.
- Compare HS, FHS, GBM, Merton, GARCH-t and the critic-selected model.
- Split results by regime and by universe.

**E2 · Factor model**
- In-sample and out-of-sample R².
- Beta stability.
- **BIST30 vs Energy beta heatmap** (a key figure).

**E3 · PPK event study**
- For every rate decision since 2018: abnormal returns over [−1, +5] days from a market model.
- Compare the scenario engine's predicted response (fitted only on data before the event) with the realized response: direction accuracy, MAE.
- Split by universe and sub-sector. If expectation data exists, also split by surprise vs expected decisions.

**E4 · Decision backtest (walk-forward)**
- Setup:
  - **Weekly** decisions, long-only (long or cash).
  - Default test window: the last 12 months, starting at `SELECTION_DATE`.
- **Post-cutoff window:** `LLM_TRAINING_CUTOFF` (in `config/settings.yaml`) is the official training-data cutoff of the configured model. Nemotron 3 Ultra model card: post-training data cutoff **May 2026**, pre-training Sep 2025 (checked 2026-11-22, D-062). The post-cutoff window starts 2026-06-01 → today. Reported as a **supplementary** result even if short; anonymized mode remains the **main** look-ahead control.
  - Transaction cost 10 bp + slippage 5 bp (configurable).
  - Default subset: 10 stocks (5 BIST30 + 5 Energy) to control cost; full universe optional.
- **Cost control (structural):**
  - **Lean backtest mode** (default for E4): each stock-week = **one** structured decision call that receives the precomputed JSON directly (no narrative agents, no Bull/Bear).
  - The **full** Bull/Bear/Judge pipeline is evaluated on a smaller random sample of stock-weeks.
  - Auditor runs on a ~10% random sample (seeded).
  - No batch API on the free tier: rate-limited (35 RPM), parallel (≤4), **resumable** batch runs (cached calls are skipped).
  - A **wall-clock estimate** (`python -m pusula.agents.plan`) is printed and confirmed before **every** batch run.
- Strategies:
  - Buy & hold (each stock)
  - XU030
  - Equal-weight universe
  - Rule-based risk filter without an LLM
  - LLM ablations:
    - **P**: price/trend only
    - **P+R**: + risk
    - **P+R+S**: + scenarios (full)
    - **full-anonymized**
- Metrics: cumulative return, CAGR, annualized vol, **Sharpe and Sortino using TLREF as the risk-free rate** (essential in Türkiye), max drawdown, Calmar, hit rate, turnover. Reported in TRY and USD.
- Significance: stationary-bootstrap confidence intervals for Sharpe differences.
- **Long-sample reference:** the non-LLM strategies (buy & hold, XU030, equal-weight, rule-based risk filter) are also run over the full **2019–2026** period, because 52 weekly LLM decisions have low statistical power.

**E5 · LLM reliability**
- Decision agreement across k=5 repeated runs (temperature > 0) (Fleiss' κ). Cross-model agreement is **optional**.
- Auditor numeric-faithfulness rate.
- Cost and latency per analysis.

Every experiment exports CSV, LaTeX tables and PNG/SVG figures to `results/`. `uv run python -m pusula.evaluation.paper_results` regenerates everything.

---

## 7. Dashboard (Streamlit, Turkish UI)

Run with `uv run streamlit run src/pusula/app/Home.py`.

| Page | Content |
|---|---|
| **Genel Bakış** | Macro snapshot (policy rate, TLREF, USD/TRY, CPI, Brent, TTF, CDS, XU100); risk heatmap of both universes |
| **Hisse Risk Analizi** | Stock selector; price chart; return distribution; MC fan chart; VaR/CVaR; model-selection scores; Agent 1 report (button) |
| **Senaryo Laboratuvarı** | Preset or custom shocks (sliders: rate shock entered as policy-rate bp **or** 2Y-yield bp, USD/TRY %, Brent %, TTF %, CDS bp, VIX); isolated/propagated toggle; per-stock and per-universe impact; BIST30 vs Energy side by side; historical analogues; Agent 2 report (button) |
| **Ajan Kararı** | Full pipeline for one stock: three reports, decision card (AL / ALMA / BEKLE, güven, gerekçeler), auditor badge, run history |
| **BIST30 vs Enerji** | Beta heatmap; scenario sensitivity comparison; sub-sector breakdown |
| **Backtest & Değerlendirme** | Viewer for E1–E5 results |
| **Veri Durumu** | Freshness, coverage, quality flags, update button |
| **Ayarlar** | LLM provider/model, API key status (never the key), cost tracker |

Rules:
- Consistent colours (BIST30 one colour, Energy another).
- Heavy computations cached (`st.cache_data`); LLM calls only via buttons.
- Disclaimer footer on every page.
- Return basis toggle (TRY / Reel / USD) where relevant.

---

## 8. Repository structure (target)

The project lives at the **repository root** (`bitirme-projesi/`); the tree below shows its contents.

```
bitirme-projesi/
├── CLAUDE.md
├── README.md                 # Turkish: what it is, setup, how to run
├── pyproject.toml
├── .env.example
├── config/                   # universe.yaml, energy_candidates.yaml, data_sources.yaml,
│                             # scenarios.yaml, regimes.yaml, settings.yaml
├── data/                     # raw/, manual/, pusula.duckdb   (git-ignored except manual/README)
├── docs/                     # DECISIONS.md, PROGRESS.md, LIMITATIONS.md, universe_selection.md, data_sources.md
├── results/                  # experiment outputs (git-ignored)
├── src/pusula/
│   ├── config.py
│   ├── data/                 # adapters/, store.py, panel.py, quality.py, update.py
│   ├── universe/             # load.py, select_energy.py
│   ├── features/
│   ├── risk/                 # models/, simulate.py, metrics.py, critic.py, backtest.py
│   ├── macro/                # factor_model.py, passthrough.py, scenarios.py, analogues.py
│   ├── llm/                  # base.py, anthropic_client.py, mock.py, ollama_client.py, cache.py
│   ├── agents/               # prompts/, risk_analyst.py, scenario_analyst.py, decision.py, auditor.py, schemas.py
│   ├── pipeline.py
│   ├── evaluation/           # var_backtest.py, event_study.py, trading_backtest.py, llm_reliability.py, paper_results.py
│   └── app/                  # Home.py, views/ (pages), components/, i18n_tr.py
└── tests/
```

---

## 9. Testing

Use synthetic data where the truth is known:
- GBM calibration recovers μ and σ.
- Simulated normal returns give a VaR exceedance rate ≈ α, and the Kupiec test behaves correctly.
- The factor model recovers known betas.
- Gaussian conditioning matches the analytic result.
- PPK change detection works on a toy series.

**No-look-ahead test:** corrupt every value after date t (NaN / huge numbers) and assert that outputs as of t do not change.

Agents and the pipeline are tested with `MockLLMClient`. Live API tests are marked `@pytest.mark.live` and skipped by default.

**Network:** tests never hit the network. Data adapters are tested with recorded fixtures.

---

## 10. Phases & acceptance criteria

| Phase | Scope | Done when |
|---|---|---|
| **P0 Setup** | Repo skeleton, uv/pyproject, ruff, pytest, config + settings, logging, `.env.example`, Turkish README, `docs/DECISIONS.md`, `docs/PROGRESS.md` | `uv run pytest` passes; `uv run streamlit run …/Home.py` shows an empty Turkish home page with disclaimer |
| **P1 Data** | Adapters (yfinance, EVDS, EPİAŞ, manual CSV), DuckDB store, panel builder, quality report, universe loader + energy selection, **Veri Durumu** page | `python -m pusula.data.update` fills the DB; quality report and energy selection table are produced; I know exactly which manual files/keys I must provide |
| **P2 Risk engine** | Model library, MC, critic, risk metrics, deterministic risk level, **Hisse Risk Analizi** page (no LLM) | Synthetic-truth tests pass; page works for any stock |
| **P3 Macro & scenarios** | Factor model A/B, pass-through, conditional scenarios, analogues, **Senaryo Laboratuvarı** + **BIST30 vs Enerji** pages | Preset scenarios run for both universes in < 30 s; beta heatmap rendered |
| **P4 Agents** | LLM layer, 4 agents, orchestrator, anonymized mode, **Ajan Kararı** + **Ayarlar** pages | One full analysis runs end-to-end with Claude; auditor passes; cost is logged; mock-based tests pass |
| **P5 Evaluation I** | E1 VaR backtests, E2 factor model, E3 PPK event study + result viewer | Tables and figures exported to `results/` |
| **P6 Evaluation II** | E4 decision backtest with ablations, E5 LLM reliability | Ablation table and Sharpe confidence intervals produced; cost estimate shown before running |
| **P7 Polish** | Genel Bakış page, docs, `paper_results` script, cleanup | Fresh clone → README steps → everything runs |
| **P8 Optional** | LLM-driven model discovery as in base paper; Ollama local model comparison; news/KAP agent; VAR impulse responses; GJR-GARCH; live EPİAŞ API adapter; cross-model E5; ridge robustness | Agreed case by case |

---

## 11. Commands (keep updated)

```bash
uv sync                                          # install
uv run python -m pusula.data.update              # fetch/update data (incremental; --full, --only)
uv run python -m pusula.data.evds_lookup "<text>" # search EVDS metadata to verify series codes
uv run python -m pusula.universe.validate --names # check every Yahoo symbol downloads
uv run python -m pusula.universe.select_energy    # rule-based energy selection
uv run python -m pusula.universe.bist_index       # BIST30 lists from Borsa Istanbul (+ reconstruction)
uv run python -m pusula.data.prefill ppk          # pre-fill ppk_decisions.csv from TCMB
uv run python -m pusula.data.jump_review --write  # classify price jumps, propose corrections
uv run python -m pusula.risk.run_universe --as-of YYYY-MM-DD  # risk reports + relative risk levels
uv run python -m pusula.macro.run --as-of YYYY-MM-DD  # factor models, pass-through, preset scenarios
uv run python -m pusula.agents.plan              # E4/E5 wall-clock estimate at the rate limit
uv run python -m pusula.evaluation.var_backtest   # E1 rolling VaR backtest (~45 min, 4 cores)
uv run python -m pusula.evaluation.factor_eval    # E2 factor model evaluation
uv run python -m pusula.evaluation.event_study    # E3 PPK event study
uv run python -m pusula.evaluation.trading_backtest --yes   # E4 (stages risk inputs llm eval; resumable)
uv run python -m pusula.evaluation.llm_reliability --yes    # E5 (resumable via the cache)
uv run python -m pusula.evaluation.llm_runner all  # paced LLM work: E4 P+R+S, P, E5, anon, P+R (D-074)
uv run python -m pusula.evaluation.llm_runner restore  # fresh container: restore committed LLM cache
uv run python -m pusula.demo.warmup              # pre-run demo analyses (THYAO, AKBNK, ENJSA, TUPRS)
uv run streamlit run src/pusula/app/Home.py      # dashboard
uv run pytest                                    # tests
uv run ruff check . && uv run ruff format .      # lint/format
uv run python -m pusula.evaluation.paper_results # regenerate paper tables/figures
```

---

## 12. Agreed decisions (2026-11-16, kickoff review)

Details, alternatives and reasons are in `docs/DECISIONS.md` (D-001 …). Short list:
- Python 3.12; project at repo root.
- `SELECTION_DATE` = start of backtest window; two BIST30 lists; survivorship bias of E1–E3 documented as a limitation.
- Two CPI functions (historical deflation vs point-in-time `cpi_as_of`).
- Merton core (robust calibration); GJR-GARCH optional.
- EPİAŞ PTF core via manual CSV; live EPİAŞ API optional.
- E4 lean mode + Batches API + prompt caching + 10% auditor sample + cost estimate before every batch. *(Batches API and prompt caching superseded by D-054/D-057: NIM free tier)*
- `LLM_TRAINING_CUTOFF` from official docs; post-cutoff window as supplementary result.
- Rate shock input as policy-rate or 2Y-yield change; regime-specific pass-through with uncertainty band.
- VIF reported; OLS default; ridge optional.
- Non-LLM strategies also run over 2019–2026.
- Cloud environment `bitirme-projesi` allows the data hosts; keys are provided as environment secrets, never in chat or in `.env` committed to git.

Follow-ups (same day, D-018 … D-030):
- Policy rate from TCMB's 1-week repo table; TLREF from 2018-12-28 with interbank O/N before; 2Y/10Y yields manual (or TLREF, decide in P3).
- BIST30 lists from Borsa Istanbul (reference = current file; selection = reconstructed), pending user review.
- Energy: 3-year rule, relaxed to 2 years per sub-sector only when a quota is unmet (`entry_rule`).
- Stock jump threshold ±10.5%; corporate actions in `config/corporate_actions.yaml` → `prices_clean`.
- EPİAŞ live API needs local `.env` credentials (form-body login); cloud uses `ptf.csv`.
- **P4 note:** Sonnet 5.5 cannot disable thinking, so temperature=0 is not deterministic. Rely on the response cache for reproducibility and measure run-to-run variation in E5.

Phase 2–3 (2026-11-22, D-031 … D-048):
- Risk engine reads `prices_clean`; <250 returns → no report; EVT on full history (≥750, ≥20 clusters); relative risk level ("evren içi göreli"); critic equal-weight ranks plus sensitivity schemes; model failures skipped and recorded.
- Inputs committed: `ppk_decisions.csv`, `corporate_actions.yaml`, `universe.yaml`; never investing.com-derived files.
- Factor model: weekly, TLREF as rate factor until the 2Y yield is provided; first 4 weeks after listing dropped; scenarios use Model A, the current-regime covariance, common random numbers, and mean + median universe summaries.

P2/P3 revisions and Phase 4 (2026-11-22, D-049 … D-062):
- Risk critic: **hold-out** (fit on the first 80%, score on the realized last 20%, refit on all) is the default; in-sample kept as a variant.
- Scenarios in TRY, USD and Reel (expected-inflation deflator); extrapolation guard (>4 sd → full-sample moments).
- Rate factor = 2Y yield (≥2 years of history), TLREF as a robustness comparison; CDS included.
- LLM: NVIDIA NIM (Nemotron 3 Ultra), OpenAI-compatible client, JSON mode + pydantic retries, SQLite cache, 35 RPM limiter, resumable batches, tokens/latency logging.
- Agents: Risk Analisti, Senaryo Analisti, Bull/Bear/Judge, Denetçi (numeric check with Turkish number formats + LLM consistency, regenerate once). Modes full/lean/anonymized; ablations P, P+R, P+R+S.

Phases 5–7 (2026-11-23, D-065 … D-072):
- Prompt v3: glossary wording, no new thresholds, sentence-form risks, Turkish self-check; numeric audit matches unit and context; RSI zone/thresholds in the trend input.
- E1 exact-quantile VaR, refit every 5 days, both critics rerun per refit; E2 rolling OOS R² (104/26 weeks); E3 market-model CAR [−1,+5] vs scenario engine fitted pre-event; E4 10 stocks by liquidity, weekly, BEKLE = keep, cash at TLREF, rule filter = MA200 + VaR99 below its 1-year median; E5 k=5 repeats at production temperature, cross-model, reasoning on/off, 6 full audits.
- Experiment worker pools are single-thread `spawn` processes with a read-only Store (DuckDB lock retry).
- Anonymised mode also hides sector-specific limitation texts.

LLM run under free-tier instability (2026-11-23, D-073 … D-075):
- `llm_runner`: 1 worker, adaptive 2–20 RPM, decision log `llm_state/e4_decisions.csv` + compressed cache committed every 100 answers (repo is public: E4 inputs are NOT committed). E4 evaluates only variants with ≥98% coverage. E5 reduced to 10 stock-weeks and 4 full analyses.
- Backup provider Gemini (`gemini-3.5-flash`, OpenAI-compatible) configured in `llm_backup`, **inactive**; switching needs the user's approval and a full rerun with one model.
