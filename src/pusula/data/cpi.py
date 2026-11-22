"""CPI handling (docs/DECISIONS.md D-003).

Two functions with different purposes. **Never mix them.**

* :func:`deflate_historical` — describes the past *ex post*. Uses every monthly print.
* :func:`cpi_as_of` — for anything computed "as of date t" (backtests, agents). Uses only prints
  whose ``release_date <= t``. Dates after the last released month are extrapolated with the
  last *known* monthly inflation rate, never interpolated towards an unreleased print.

Both turn monthly index levels into a daily level the same way: each monthly value is placed on
the 15th of its reference month (CPI is a monthly *average*), and we interpolate log-linearly
between those points (= constant daily inflation rate within each gap).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

ANCHOR_DAY = 15


def _anchors(cpi_monthly: pd.DataFrame) -> pd.Series:
    """Monthly ``date (month start), value`` -> log level indexed by mid-month timestamp."""
    m = cpi_monthly.dropna(subset=["value"]).sort_values("date")
    if len(m) < 2:
        raise ValueError("Need at least two monthly CPI values")
    idx = pd.to_datetime(m["date"]).dt.to_period("M").dt.to_timestamp() + pd.Timedelta(
        days=ANCHOR_DAY - 1
    )
    return pd.Series(np.log(m["value"].to_numpy(dtype=float)), index=idx)


def _days(idx: pd.DatetimeIndex) -> np.ndarray:
    return ((idx - pd.Timestamp("1970-01-01")) / pd.Timedelta(days=1)).to_numpy(dtype=float)


def _interp_log_level(anchors: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    # Days since epoch as floats (unit-safe: pandas 3 may store dates in s/us/ns resolution).
    x = _days(anchors.index)
    y = anchors.to_numpy()
    t = _days(dates)
    out = np.interp(t, x, y)  # flat outside the range -> fixed below with slopes
    # Extrapolate beyond the last anchor with the last known slope (last monthly inflation),
    # and before the first anchor with the first slope.
    last_slope = (y[-1] - y[-2]) / (x[-1] - x[-2])
    first_slope = (y[1] - y[0]) / (x[1] - x[0])
    after = t > x[-1]
    before = t < x[0]
    out[after] = y[-1] + last_slope * (t[after] - x[-1])
    out[before] = y[0] + first_slope * (t[before] - x[0])
    return pd.Series(np.exp(out), index=dates, name="cpi")


def deflate_historical(cpi_monthly: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.Series:
    """Daily CPI level for ``dates`` using ALL monthly prints (ex-post analysis only)."""
    return _interp_log_level(_anchors(cpi_monthly), pd.DatetimeIndex(dates))


def cpi_as_of(cpi_monthly: pd.DataFrame, dates: pd.DatetimeIndex, as_of: date) -> pd.Series:
    """Daily CPI level for ``dates`` using only prints released on or before ``as_of``.

    ``cpi_monthly`` needs a ``release_date`` column. Rows without a release date are treated as
    unknown (excluded), which is the safe choice.
    """
    dates = pd.DatetimeIndex(dates)
    ts = pd.Timestamp(as_of)
    if (dates > ts).any():
        raise ValueError("cpi_as_of: requested dates after as_of (that would be look-ahead)")
    if "release_date" not in cpi_monthly:
        raise ValueError("cpi_as_of needs a 'release_date' column")
    known = cpi_monthly[pd.to_datetime(cpi_monthly["release_date"]) <= ts]
    return _interp_log_level(_anchors(known), dates)


def real_price(nominal: pd.Series, cpi_daily: pd.Series) -> pd.Series:
    """Deflate a nominal TRY price series by a daily CPI level (same index)."""
    return nominal / cpi_daily.reindex(nominal.index)
