"""Deterministic risk level (CLAUDE.md §6.2, D-037).

"Evren içi göreli risk düzeyi": a **relative** label. For every stock of the combined universe
(BIST30 + Energy) on the same date, in nominal TRY:
1. percentile rank (0-100) of annualised volatility,
2. percentile rank (0-100) of 1-day CVaR 99%,
3. score = average of the two; cutoffs 25 / 50 / 75 give four levels.
The LLM later explains the label; it never decides it.
"""

from __future__ import annotations

import pandas as pd

LEVEL_CODES = ["dusuk", "orta", "yuksek", "cok_yuksek"]


def assign_risk_levels(df: pd.DataFrame, cutoffs: list[float] | None = None) -> pd.DataFrame:
    """``df`` needs columns ticker, vol_ann, cvar99_1d. Returns a copy with percentile columns,
    ``risk_score`` and ``risk_level`` (code)."""
    cutoffs = cutoffs or [25, 50, 75]
    out = df.copy()
    out["vol_pct"] = out["vol_ann"].rank(pct=True, method="average") * 100
    out["cvar_pct"] = out["cvar99_1d"].rank(pct=True, method="average") * 100
    out["risk_score"] = (out["vol_pct"] + out["cvar_pct"]) / 2
    bins = [-float("inf"), *cutoffs, float("inf")]
    out["risk_level"] = pd.cut(out["risk_score"], bins=bins, labels=LEVEL_CODES,
                               right=False).astype(str)  # fmt: skip
    return out
