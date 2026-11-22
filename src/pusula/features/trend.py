"""Trend metrics for the decision agent (CLAUDE.md §6.1), from cleaned prices up to as_of.

* RSI(14): Wilder's relative strength index (0–100); above 70 is often called "overbought",
  below 30 "oversold".
* price vs 50- and 200-day moving average (% above/below);
* momentum: 3-, 6- and 12-month price change (63/126/252 sessions, %);
* distance from the 52-week high (%, <= 0).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(price: pd.Series, n: int = 14) -> float:
    d = price.dropna().diff().dropna()
    if len(d) < n + 1:
        return float("nan")
    up, down = d.clip(lower=0), -d.clip(upper=0)
    au = up.ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    ad = down.ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    if ad == 0:
        return 100.0
    return float(100 - 100 / (1 + au / ad))


def _pct(a: float, b: float) -> float:
    return float((a / b - 1) * 100) if b and np.isfinite(b) else float("nan")


def trend_metrics(price: pd.Series) -> dict[str, float | None]:
    """``price``: adjusted close on sessions up to as_of (NaN allowed)."""
    p = price.dropna()
    last = float(p.iloc[-1])

    def back(k):
        return float(p.iloc[-k - 1]) if len(p) > k else float("nan")

    out = {
        "rsi14": rsi(p),
        "fiyat_ma50_fark_yuzde": _pct(last, p.iloc[-50:].mean()) if len(p) >= 50 else np.nan,
        "fiyat_ma200_fark_yuzde": _pct(last, p.iloc[-200:].mean()) if len(p) >= 200 else np.nan,
        "momentum_3a_yuzde": _pct(last, back(63)),
        "momentum_6a_yuzde": _pct(last, back(126)),
        "momentum_12a_yuzde": _pct(last, back(252)),
        "zirveden_uzaklik_52h_yuzde": _pct(last, p.iloc[-252:].max()),
    }
    return {
        k: (None if v is None or not np.isfinite(v) else round(float(v), 2)) for k, v in out.items()
    }
