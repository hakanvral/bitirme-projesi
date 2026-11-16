# Known limitations

To be reported in the paper's "Limitations" section.

### L-01 · Survivorship bias in E1–E3
E1 (VaR backtests), E2 (factor model) and E3 (PPK event study) use 2018–2026 price history of stocks that are in the universe **today** (BIST30 at `REFERENCE_DATE`, energy selection at `SELECTION_DATE`). Firms that were delisted, merged or dropped from the index are missing, which may make historical risk look lower and returns look higher. E4 reduces this by using the universe as of `SELECTION_DATE` (D-002), but does not remove it.

### L-02 · LLM pre-training knowledge
Most of the E4 test window (2025-11 → 2026-11) is before the configured models' training-data cutoff (Jun 2026, D-007), so the model may "remember" what happened. The main control is the anonymized mode; the post-cutoff window (2026-07 →) is short and reported as supplementary.

### L-03 · Data source quality
Prices come from Yahoo Finance (an unofficial API). Corporate-action adjustment for Turkish bonus issues is not always consistent, so moves above ±25% are flagged for manual review rather than corrected automatically. There is no free official source for Türkiye 5Y CDS.

### L-04 · Statistical power of E4
52 weekly decisions per stock give wide confidence intervals for Sharpe-ratio differences. Partly mitigated by the long-sample non-LLM reference (D-010).

### L-05 · Yahoo index data gaps
Yahoo's XU100 history misses some real sessions (25 December in several years, 2021-04-02), and Yahoo has no history for XELKT (only the latest day). The panel uses the official XIST calendar (D-013); XELKT needs a manual CSV if it is used as a benchmark.
