"""Synthetic data builders for tests (known truth, no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def bdays(start: str, n: int) -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def price_long(
    ticker: str, dates: pd.DatetimeIndex, close: np.ndarray | float = 100.0, volume: float = 1_000.0
) -> pd.DataFrame:
    close = np.broadcast_to(np.asarray(close, dtype=float), (len(dates),)).copy()
    return pd.DataFrame(
        {
            "date": dates,
            "ticker": ticker,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "adj_close": close,
            "volume": volume,
        }
    )


def yf_wide(symbols: list[str], dates: pd.DatetimeIndex, field_first: bool = False) -> pd.DataFrame:
    """Mimic ``yf.download(group_by='ticker', auto_adjust=False)`` output."""
    fields = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    data = {}
    for i, s in enumerate(symbols):
        for f in fields:
            val = 1000.0 if f == "Volume" else 10.0 + i + (0.5 if f == "Close" else 0.0)
            key = (f, s) if field_first else (s, f)
            data[key] = np.full(len(dates), val)
    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates, name="Date"))
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df
