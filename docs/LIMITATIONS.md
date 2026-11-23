# Known limitations

To be reported in the paper's "Limitations" section.

### L-01 · Survivorship bias in E1–E3
E1 (VaR backtests), E2 (factor model) and E3 (PPK event study) use 2018–2026 price history of stocks that are in the universe **today** (BIST30 at `REFERENCE_DATE`, energy selection at `SELECTION_DATE`). Firms that were delisted, merged or dropped from the index are missing, which may make historical risk look lower and returns look higher. E4 reduces this by using the universe as of `SELECTION_DATE` (D-002), but does not remove it.

### L-02 · LLM pre-training knowledge
Most of the E4 test window (2025-11 → 2026-11) is before the configured models' training-data cutoff (Nemotron 3 Ultra: post-training May 2026, D-062), so the model may "remember" what happened. The main control is the anonymized mode; the post-cutoff window (2026-06-01 →) is short and reported as supplementary. Result: with names and dates hidden, 88 % of the P+R+S decisions were identical and performance was not worse (Sharpe difference −0.36, p = 0.47; RESULTS E4), so we find no sign of memorisation. The input numbers themselves can still hint at a stock, so this does not rule it out.

### L-03 · Data source quality
Prices come from Yahoo Finance (an unofficial API). Corporate-action adjustment for Turkish bonus issues is not always consistent, so moves above ±25% are flagged for manual review rather than corrected automatically. There is no free official source for Türkiye 5Y CDS.

### L-04 · Statistical power of E4
52 weekly decisions per stock give wide confidence intervals for Sharpe-ratio differences. Partly mitigated by the long-sample non-LLM reference (D-010).

### L-05 · Yahoo index data gaps
Yahoo's XU100 history misses some real sessions (25 December in several years, 2021-04-02), and Yahoo has no history for XELKT (only the latest day). The panel uses the official XIST calendar (D-013); XELKT needs a manual CSV if it is used as a benchmark.

### L-06 · Release dates by rule
CPI and survey release dates use conservative rules (D-023) unless official dates are provided, so information enters the model a few days later than it did in reality.

### L-07 · Price limit history
The analysis cannot rule out that some 10–20% daily moves before 2021 are data errors; they are consistent with a ±20% band but were not verified (D-026).

### L-08 · Reconstructed BIST30 list
The 2025-11-03 BIST30 list is reconstructed from period-change announcements and does not capture intra-period changes (D-021).

### L-09 · Weak macro explanatory power
Weekly macro factors explain little of single-stock returns in nominal TRY (Model A mean R² ≈ 0.06 for both universes; Model B with the market residual ≈ 0.46 for BIST30 and 0.28 for Energy). Most betas are not significant at 5%, except VIX (significant for 82% of stocks). Scenario effects are therefore small relative to normal return dispersion and should be read with their uncertainty.

### L-10 · Rate factor and missing inputs
Without the 2Y yield, the rate factor is TLREF (an overnight rate), and CDS and PTF are missing at the time of writing (D-041, D-046).

### L-11 · Gaussian, independent weekly macro moves
The scenario engine assumes normally distributed, independent weekly factor changes within a regime (D-043), so fat tails and momentum in macro variables are not captured.

### L-12 · In-sample critic
The risk-model critic selects Historical Simulation in most cases because it is in-sample (D-034); out-of-sample validation follows in E1.

### L-13 · LLM language support and determinism
Turkish is not in Nemotron 3 Ultra's list of officially supported languages; output quality was judged on examples. Reasoning models are not deterministic even at low temperature, so reproducibility relies on the response cache, and run-to-run variation is measured in E5.

### L-14 · Weak policy-rate pass-through to the 2Y yield
On PPK days the 2Y yield moves much less than the policy rate (current regime β ≈ 0.19 with a wide band), so policy-rate scenarios have small, uncertain effects (D-052).

### L-15 · The numeric audit checks values, not meaning
Originally, a number passed if the same value appeared anywhere in the input, so an invented threshold could pass by coincidence (live example: "volatility below %30" passed because "−%30" appears in a scenario name). Since prompt v3 (D-065) the check also requires a compatible unit, and, for numbers inside input strings, a matching context keyword, sign and direction. This closes that case but is still a heuristic: a number with the right unit and a coincidentally equal value elsewhere in the input still passes, and the ±70-character keyword window can be fooled. Semantic misreadings (e.g. describing VaR as "the worst-day loss") are left to the prompt rules, the LLM consistency check and human review.

### L-16 · E3 predictions start in 2020 and rest on few events
The factor model needs 104 weeks of factor history, and the data start in 2018-01, so the four 2019 rate cuts have realised reactions only. Predictions cover 37 rate changes (2020–2026), clustered in a few policy cycles; per-sub-sector results rest on 2–6 stocks. The scenario engine predicts a 1-week expected response from weekly betas, while the event window is 7 trading days around a single announcement. A mismatch in horizon and in information (surprise vs expected decision) is therefore built in.

### L-17 · E4 has low statistical power
52 weekly decisions on 10 stocks cannot separate strategies with similar Sharpe ratios; the bootstrap intervals are wide. The non-LLM strategies are also run over 2019–2026 for context, but the LLM variants cannot be (cost and the look-ahead problem).

### L-18 · Free-tier LLM API instability
The LLM experiments depend on NVIDIA NIM's free tier, which gives no service guarantee.
- **The 2026-11-23 outage:**
  - A 35 RPM, 4-worker batch was throttled after ~6 minutes (HTTP 429 without `Retry-After`).
  - The model was then reported `DEGRADED` (HTTP 400) for several hours.
  - The effective throughput was ~12 requests/min at best and often ~1–4/min, against the planned 35.
  - After the outage, even 5–10 RPM triggered 429s at first.
- **Consequences:** E4/E5 take many hours of wall-clock time, and the runner had to be made adaptive and resumable (D-073, D-074). E5 was reduced to 10 stock-weeks and 4 full analyses.
- **What this does not affect:** throttling changes only *when* answers arrive, not *what* they are. The prompt, model, temperature and inputs are fixed, and every answer is cached.
- **Backup:** a provider is configured but not used (D-075). Mixing models across variants would break the ablation, so a switch would mean rerunning everything with one model.
