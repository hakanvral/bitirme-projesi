# Progress

## ▶ Current checklist: Step 0 + Phases 5–7 (spec: [EXPERIMENTS_PLAN.md](EXPERIMENTS_PLAN.md))

Status: ✅ done · 🔄 running · ⏳ todo. Updated after each experiment.

**Data freeze (D-076):** data as of 2026-11-20; the data update is disabled until E4 and E5 are finished.

| Step | Status | Output | Resume command |
|---|---|---|---|
| Step 0: prompt v3 + context-aware numeric check | ✅ done (THYAO, ENJSA rerun, audit passed) | `docs/prompt_v3_before_after.md` | `uv run pytest tests/test_agents.py` |
| E1 VaR backtest | ✅ done (41 stocks, 73,842 stock-days, 44 min) | `results/e1_var/<ts>/` | `uv run python -m pusula.evaluation.var_backtest` |
| E2 factor model | ✅ done | `results/e2_factor/<ts>/` | `uv run python -m pusula.evaluation.factor_eval` |
| E3 PPK event study | ✅ done | `results/e3_event/<ts>/` | `uv run python -m pusula.evaluation.event_study` |
| E4 decision backtest (LLM, resumable) | risk ✅ inputs ✅ non-LLM ✅ **P+R+S ✅ P ✅ (evaluated)**; anon, P+R ⏳ after E5 | `results/e4_backtest/<ts>/`, `llm_state/e4_decisions.csv` | `uv run python -m pusula.evaluation.llm_runner all` |
| E5 LLM reliability (reduced, D-074) | 🔄 lean calls done (48 min); 4 full analyses running | `results/e5_llm/<ts>/` | (part of `llm_runner all`) or `uv run python -m pusula.evaluation.llm_runner e5` |
| paper_results + docs/RESULTS.md + Backtest page | ✅ (E4 LLM part and E5 marked pending) | `results/`, `docs/RESULTS.md` | `uv run python -m pusula.evaluation.paper_results` |
| Phase 7: Genel Bakış, demo warmup, README, cleanup | ✅ (warmup needs the endpoint to run) | | `uv run python -m pusula.demo.warmup` |

<!-- llm-run-status:begin -->

**LLM run status** (updated 2026-11-23 21:44 UTC; `llm_runner`, D-074)

| E4 variant | Decisions | Coverage |
|---|---|---|
| P+R+S | 540 / 540 | 100% |
| P | 540 / 540 | 100% |
| P+R+S-anon | 126 / 540 | 23% |
| P+R | 0 / 540 | 0% |

Current pace: 10 RPM (1 worker).

Variant P finished at 2026-11-23 21:44 UTC.

Resume: `uv run python -m pusula.evaluation.llm_runner all` (fresh container: see `docs/RUN_LLM_LOCALLY.md`).

<!-- llm-run-status:end -->

LLM runs are resumable: finished calls are cached in `data/llm_cache.sqlite` (committed copy: `llm_state/llm_cache.sqlite.gz`) and logged in `llm_state/e4_decisions.csv`. Fresh container or own PC: `docs/RUN_LLM_LOCALLY.md`.

## P0 · Setup: ✅ done (2026-11-16)
- uv project (Python 3.12), ruff and pytest config, `.env.example`, `.gitignore`.
- `config/settings.yaml` (dates incl. `selection_date`, LLM training cutoff), `config/regimes.yaml`.
- `pusula.config` (typed settings, secrets as `SecretStr`), `pusula.logging_setup`.
- Streamlit entry `src/pusula/app/Home.py` (`st.navigation`), Turkish strings in `app/i18n_tr.py`, disclaimer footer.
- Docs: Turkish README, `DECISIONS.md` (D-001…D-012), `LIMITATIONS.md`, this file.
- Verified: `uv run pytest` (7 passed), `ruff check` clean, the Streamlit home page renders with the disclaimer.

## P1 · Data: ✅ code done, ⏳ waiting for user inputs (2026-11-16)

### Built
- Adapters: yfinance (stocks, indices, global series), EVDS3 (data + metadata search), manual CSV (strict schemas + clear errors). The live EPİAŞ API is optional (D-005), so PTF comes from a manual CSV.
- `data/store.py`: DuckDB tables `prices, macro, events, universe, analysis_runs, llm_usage, update_log, quality_report`; raw Parquet snapshots in `data/raw/<source>/<YYYYMMDD>.parquet`.
- `data/panel.py`: XIST calendar (D-013), fill rules (D-015), `as_of` point-in-time, weekly Friday close.
- `data/cpi.py`: `deflate_historical` vs `cpi_as_of` (D-003).
- `data/quality.py`: coverage, missing, stale, ±25% jumps, too-short history; CSV export to `results/data_quality/<ts>/`.
- `data/ppk.py`: rate-change detection + comparison with the manual PPK file.
- `data/update.py`: one command, incremental, per-source isolation (D-014).
- `universe/`: loader, Yahoo validator, rule-based energy selection → `config/energy_selected.yaml`, `docs/universe_selection.md`.
- **Veri Durumu** page (Turkish), with an update button.

### Verified
- `uv run pytest`: 44 passed (no network). Includes no-look-ahead tests for CPI, the panel and the energy selection; PPK detection on a toy series; the end-to-end update with a fake downloader.
- `ruff check`: clean.
- Live run in the cloud environment: Yahoo OK for all 16 energy candidates, XU100, XU030, BZ=F, TTF=F, ^VIX, ^TNX, DX-Y.NYB, TRY=X (2018 → 2026-11-16). Quality report produced.

### Data findings
- **XELKT:** Yahoo has no history (1 row) → needs `data/manual/index_XELKT.csv` if used.
- **XU100 on Yahoo** misses some real sessions (D-013) → official XIST calendar used.
- **Jump flags for review:** AYGAZ 2022-09-01 (+72.5%), NATEN 2020-03-12 (−25.2%), NATEN 2023-11-29 (+42.7%). Probably unadjusted bonus/rights issues; to be checked on KAP.
- Yahoo returns stock rows on some non-session days (e.g. 2018-01-01); the panel drops them by reindexing to XIST.

### Open issues / user actions
1. **EVDS series codes not verified.** The adapter and key work, but my metadata lookup calls were blocked by this session's auto-mode permission check. Run `uv run python -m pusula.data.evds_lookup "policy" "exchange rate" "consumer price" "market participants" "tlref" "bond"` (or allow it in this session) and I'll fill the codes.
2. **BIST30 lists** for 2026-11-01 and 2025-11-03 → `config/universe.yaml`.
3. **Energy candidates:** confirm activity and sub-sector, set `verified: true`.
4. **Natural-gas quota unmet** under the 3-year rule (AHGAZ, ENERY are too young at 2025-11-03). Options: (a) shorten the history rule to 2 years (both become eligible), (b) add other gas distributors you verify, (c) accept 0 gas names and report it.
5. **Manual CSVs** (see `data/manual/README.md`): `cds_tr_5y.csv`, `ptf.csv`, `ppk_decisions.csv`, `cpi_release_dates.csv`, `cpi_exp_12m_release_dates.csv`; optional `index_XELKT.csv`.
6. Note for P4: the Anthropic models page says Sonnet 5.5 does not accept disabling thinking. `LLM_TEMPERATURE=0` and the structured-output setup must be re-checked against the current docs then.

## P1 follow-ups: ✅ done (2026-11-16), see D-018 … D-030

### Built / changed
- **EVDS codes verified** via the metadata endpoints and downloaded (USD/TRY, EUR/TRY, TLREF, interbank O/N, CPI 2025=100, 12-month expectation). EVDS windowing (≤900 days/request) added after finding the ~1000-item cap.
- **Policy rate** from TCMB's official one-week repo table (`tcmb_web` adapter).
- **PPK decisions**: 93 meetings (2018-01 → 2026-10) pre-filled with press-release URLs → `data/manual/ppk_decisions.csv`; `ppk_detected_changes.csv` generated. Text and table agree for every meeting from June 2018 on.
- **BIST30 lists** (both dates) from Borsa Istanbul's constituent file plus period announcements (`universe/bist_index.py`) → `config/universe.yaml` (`pending_user_review`).
- **Energy selection** with the per-sub-sector 2-year relaxation → ENERY, AHGAZ enter as natural_gas (`entry_rule: 2y_relaxed`).
- **Cleaning step**: `config/corporate_actions.yaml` → `prices_clean`; generic rules (non-session rows, stale zero-volume rows); jump thresholds per class; `jump_review` with 4 proposals.
- **EPİAŞ API adapter** (TGT + MCP), plus release-date rules for CPI and the survey.
- Tests: 60 passed; ruff clean.

### Selected energy universe (2025-11-03)
TUPRS, AYGAZ (refining) · ENERY, AHGAZ (natural gas, relaxed rule) · CANTE, ODAS, ZOREN, ENJSA, AKSEN, NATEN (electricity). TUPRS is also in BIST30.

### Open issues / user actions
1. Review `config/universe.yaml` (both BIST30 lists) → set `status: confirmed`.
2. Confirm the energy candidates (`verified: true`).
3. Check the 4 proposals in `config/corporate_actions.yaml` on KAP (AYGAZ 2018-03-29, 2019-03-28, 2022-09-01; NATEN 2023-11-29) and set `status: confirmed` / `rejected`, adding `source_url`. Also look at the 58 `review` cases in `docs/price_jump_review.md`, mainly those from 2022 on.
4. Review `data/manual/ppk_decisions.csv` (rows before 2018-06-01 are flagged).
5. Provide `cds_tr_5y.csv` (steps in `data/manual/README.md`).
6. Decide in P3: 2Y yield (manual CSV) or TLREF as the rate factor.
7. Optional: official CPI / survey release-date files (otherwise conservative rules); `ptf.csv`, or run the update locally with EPİAŞ credentials in `.env`.
8. DSTKF (in the 2025-11-03 BIST30 list) has prices only from 2025-02-06, which is relevant for the P2 calibration window.

## P2 · Risk engine: ✅ done (2026-11-22)
- `features/returns.py` (log returns, gap rule, TRY / real / USD bases); `risk/models/` (HS, FHS, GBM, Merton, GARCH-t); `risk/critic.py`, `risk/metrics.py`, `risk/level.py`, `risk/schemas.py` (`RiskReport`), `risk/engine.py`, `risk/run_universe.py`; **Hisse Risk Analizi** page.
- Run: `uv run python -m pusula.risk.run_universe --as-of 2026-11-20`, then open the page.
- Verified by tests (synthetic truth): GBM recovers μ and σ; Merton recovers λ and the jump mean; GARCH-t recovers α, β and ν; VaR/CVaR match lognormal analytics; drawdown on a known path; beta recovery; EVT ξ for Student-t(4) ≈ 0.25; declustering; critic prefers the true model; deterministic risk levels; **no look-ahead** (corrupted future → identical report); short history → no report; failing model skipped and recorded.
- Timings: 0.4–0.6 s per stock and basis (target ≤ 5 s); a universe run (39 stocks × 3 bases) takes ~56 s.
- Finding: the in-sample critic picks HS for 212 of 231 reports (D-034).

## P3 · Macro & scenarios: ✅ done (2026-11-22)
- `macro/factors.py` (weekly panel), `macro/factor_model.py` (Model A/B, Newey–West, VIF, ridge, rolling and regime betas), `macro/passthrough.py`, `macro/scenarios.py` (isolated/propagated, 1m/3m, residual bootstrap, baseline comparison), `macro/analogues.py`, `macro/context.py`, `macro/run.py`; `config/scenarios.yaml`; pages **Senaryo Laboratuvarı** and **BIST30 vs Enerji**.
- Run: `uv run python -m pusula.macro.run --as-of 2026-11-20` (results in `results/macro/…` and DuckDB `factor_betas`, `scenario_results`).
- Verified by tests: known betas recovered with HAC; VIF detects collinearity; Model B keeps Model A's macro betas; ridge shrinks; rolling betas; Gaussian conditioning matches the analytic 2-D formula; propagated shift equals the analytic conditional shift; shock conversion, pass-through recovery and regime fallback; analogues find a planted window; listing-week rule; optional factors switch on when data appears; **no look-ahead** for the factor panel and betas.
- Speed: 39 factor fits in 1.4 s; all 10 presets × 2 horizons × 2 modes for both universes in ~5 s (target < 30 s).
- Missing inputs at this point: CDS, PTF, 2Y/10Y yields (warnings shown; TLREF used as the rate factor).

## P2/P3 revisions: ✅ done (2026-11-22)
- **Hold-out critic** is the default (fit on the first 80%, score on the realized last 20%, refit on all); in-sample kept as a variant. Model choice in 231 reports: hold-out GBM 63, GARCH-t 54, HS 53, FHS 47, Merton 14; in-sample HS 209.
- **Scenarios in TRY / USD / Reel** (batch outputs and both pages have a basis toggle). Docs note: a weaker lira can raise TRY prices while lowering USD value.
- **Data:** CDS (2018 → 2026-11-19) and the 2Y yield (2018 → 2026-11-20) added. The 2Y yield is the rate factor (TLREF kept as a comparison). The first two 2Y exports covered only ~20 days (handled by D-049).
- New Model A/B mean R²: BIST30 0.140 / 0.462, Energy 0.091 / 0.286. CDS significant for 90% of stocks. Ülke riski +200 bp (3 months, TRY): BIST30 −16.0%, Energy −11.4%. Pass-through of the policy rate to the 2Y yield is weak (β 0.19), so rate scenarios shrank (D-052).
- **Extrapolation guard** (D-053): the Kur şoku preset uses full-sample moments (z = 6.9 in the current regime).

## P4 · Agents: ✅ done (2026-11-23)
- **LLM layer** (`src/pusula/llm/`): `OpenAICompatibleClient` (NVIDIA NIM default; Ollama/others), optional `AnthropicClient`, `MockLLMClient`, SQLite cache, 35 RPM limiter with backoff, JSON mode + pydantic retries, usage logging (tokens, latency, attempts, JSON failures, cost = 0).
- **Agents** (`src/pusula/agents/`): versioned prompts (v2/v3), input builders (P, P+R, P+R+S), Risk Analisti, Senaryo Analisti, Bull, Bear, Judge, lean decision, Denetçi (Turkish-format numeric check + LLM consistency, regenerate once). `pipeline.run_analysis` with full / lean / anonymized modes, persisted runs. `agents/batch.py` (resumable, parallel) and `python -m pusula.agents.plan` (wall-clock estimate).
- **Pages:** Ajan Kararı, Ayarlar; LLM buttons on Hisse Risk Analizi (Agent 1) and Senaryo Laboratuvarı (Agent 2). No LLM call on page load.
- **Model:** nvidia/nemotron-3-ultra-550b-a55b for every role (comparison in D-055). Lean calls run with reasoning off (~2 s).
- **Live check (2026-11-20, full mode):** THYAO (BIST30) and ENJSA (Energy) both end with **BEKLE** (confidence 0.40 / 0.35) and pass the audit (171 / 181 numbers, consistency OK) after one regeneration round. Fresh runs took about 5–9 minutes and about 55–80k input / 30–40k output tokens.
- **Estimates at 35 RPM, 4 parallel requests:** E4 lean (2,080 requests) ~1.0 h; full-pipeline sample (240) ~0.6 h; auditor 10% (208) ~0.5 h; E5 k=5 × 20 analyses (600) ~1.6 h.
- **Tests:** 136 passed (mock-based; no network); ruff clean.
- **Open:** Turkish is not in the model's official language list (L-13); the numeric audit is value-based (L-15); model-to-model disagreement on the same input (D-055) can be measured in E5.

## Step 0 · Prompt v3: ✅ done (2026-11-23)
- Glossary wording (VaR, factor sensitivities), sentence-form `temel_riskler`, no new thresholds, Turkish self-check; prompts v3 (auditor v4).
- The numeric audit matches unit and context; the trend input has the RSI zone and its thresholds; the token budget is 16,384 (D-065, D-068).
- THYAO and ENJSA reruns: audit passed with no regeneration (165 / 213 numbers). Before/after: `docs/prompt_v3_before_after.md`.

## P5 + P6 · Experiments (2026-11-23)
- **Code:** `src/pusula/evaluation/` (`var_backtest`, `factor_eval`, `event_study`, `trading_backtest`, `llm_reliability`, `paper_results`, `common`); tests in `tests/test_evaluation.py`.
- **Results:** see `docs/RESULTS.md`.
- **E1 ✅:** 41 stocks, 73,842 stock-days, 44 min. GARCH-t and FHS are best. The hold-out critic beats the in-sample critic and HS at 95 % (36/41 stocks) but not at 99 %.
- **E2 ✅:**
  - in-sample R² A/B: BIST30 0.14 / 0.46, Energy 0.09 / 0.33;
  - out-of-sample R² A ≈ 0 (negative), B ≈ 0.36 / 0.24;
  - BIST30 is more CDS- and USD/TRY-sensitive.
  - Fixed the empty regime-beta bug.
- **E3 ✅:** 37 rate changes; direction accuracy 0.53 [0.44, 0.61], i.e. no predictive skill for announcement reactions.
- **E4 non-LLM ✅:**
  - TLREF cash (+48.8 %) beat all equity strategies in the test year;
  - the rule filter halves drawdowns over 2019–2026 but lowers the Sharpe ratio.
- **E4 LLM ⏸:** ~330 of 2,160 lean calls done. The NVIDIA NIM endpoint was throttled, then DEGRADED (D-073). It resumes automatically or with the command in the checklist.
- **E5 ⏸:** waits for the endpoint. Cross-model calls (Kimi, Gemma) are being pre-cached, slowly.

## P7 · Polish (2026-11-23)
- **Genel Bakış** page: macro snapshot with weekly changes and point-in-time CPI; risk heatmap of both universes.
- **Backtest & Değerlendirme** page (E1–E5 viewer).
- `python -m pusula.demo.warmup`.
- Turkish README (setup, keys and files, data update, app, reproducing the results).
- CLAUDE.md commands; LIMITATIONS L-15 (updated), L-16, L-17.
- Infrastructure: single-thread spawn worker pools; read-only Store with lock retry; LLM pace overrides via environment variables.
