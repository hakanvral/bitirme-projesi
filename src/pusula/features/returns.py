"""Log returns in three bases: nominal TRY, real TRY and USD (CLAUDE.md §2.4, §6.1).

Plain-language summary
* A **log return** is ln(P_t / P_{t-1}). Log returns add up over time, which makes multi-day
  returns a simple sum.
* **USD basis**: the price divided by USD/TRY, i.e. what a dollar-based investor earns.
* **Real basis**: the price divided by the CPI level, i.e. the return after Turkish inflation.
  For anything "as of t" the CPI level comes from :func:`pusula.data.cpi.cpi_as_of`, so only
  inflation figures published by t are used (D-003).

Missing prices are never filled for stocks. A return is computed between two consecutive valid
prices; if more than ``max_gap`` sessions are missing in between, that return is dropped
(D-032), because a multi-week move is not a daily return.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from pusula.data.cpi import cpi_as_of

Basis = Literal["TRY", "REAL", "USD"]
BASES: tuple[Basis, ...] = ("TRY", "REAL", "USD")


def session_prices(
    prices: pd.DataFrame, ticker: str, sessions: pd.DatetimeIndex, field: str = "adj_close"
) -> pd.Series:
    """One ticker's price on every session (NaN where missing)."""
    p = prices[prices["ticker"] == ticker].copy()
    p["date"] = pd.to_datetime(p["date"])
    s = p.set_index("date")[field].sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s.reindex(sessions)


def log_returns(price: pd.Series, max_gap: int = 5) -> pd.Series:
    """Daily log returns between consecutive valid prices; returns spanning > max_gap missing
    sessions are dropped. Index = the later date."""
    valid = price.dropna()
    valid = valid[valid > 0]
    pos = pd.Series(np.arange(len(price)), index=price.index).reindex(valid.index)
    r = np.log(valid).diff()
    gap = pos.diff() - 1  # sessions skipped between the two prices
    r = r[gap <= max_gap]
    return r.dropna().rename(price.name)


def to_basis(
    price: pd.Series,
    basis: Basis,
    usdtry: pd.Series | None = None,
    cpi_monthly: pd.DataFrame | None = None,
    as_of: date | None = None,
) -> pd.Series:
    """Convert a TRY price series (session index) to the requested basis.

    USD: divide by USD/TRY of the same day (market fill allowed upstream).
    REAL: divide by the point-in-time CPI level as of ``as_of`` (D-003).
    """
    if basis == "TRY":
        return price
    if basis == "USD":
        if usdtry is None:
            raise ValueError("USD basis needs a USD/TRY series")
        fx = usdtry.reindex(price.index).ffill(limit=5)
        return price / fx
    if basis == "REAL":
        if cpi_monthly is None or as_of is None:
            raise ValueError("REAL basis needs monthly CPI with release dates and as_of")
        idx = price.index[price.index <= pd.Timestamp(as_of)]
        cpi = cpi_as_of(cpi_monthly, idx, as_of)
        return price.reindex(idx) / cpi
    raise ValueError(f"Unknown basis {basis!r}")


def weekly_log_returns(price: pd.Series) -> pd.Series:
    """Friday-close log returns (last valid price of each Mon–Fri week)."""
    w = price.dropna().resample("W-FRI").last().dropna()
    return np.log(w).diff().dropna()
