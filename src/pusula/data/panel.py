"""Aligned panel builder (CLAUDE.md §5).

* Calendar (D-013): the official Borsa Istanbul calendar (``exchange_calendars`` "XIST") over
  the date range of the stored XU100 data. Yahoo's XU100 dates miss real sessions (every
  25 December, 2021-04-02) and contain 2023-02-08 (XIST: closed), so observed dates are only a
  diagnostic (``method="observed"``, also used by synthetic tests).
* Each macro series is aligned to that calendar with an explicit fill rule (D-015):
  ``step`` (carry forever), ``market`` (carry at most N days), ``release`` (only from the
  release date on), ``none``.
* ``as_of`` makes the panel point-in-time: nothing dated after ``as_of`` and no monthly value
  released after ``as_of`` enters the panel.
* Optional weekly resampling: Friday close (the last trading day of each week).
"""

from __future__ import annotations

import logging
import warnings
from datetime import date

import pandas as pd

from pusula.data.sources import SeriesSpec

log = logging.getLogger(__name__)

CALENDAR_TICKER = "XU100.IS"


# --------------------------------------------------------------------------- calendar
def trading_calendar(
    prices: pd.DataFrame, ticker: str = CALENDAR_TICKER, method: str = "xist"
) -> pd.DatetimeIndex:
    """Borsa Istanbul trading days over the date range of ``ticker`` (XU100) in ``prices``.

    ``method="xist"`` (default): official sessions from ``exchange_calendars``.
    ``method="observed"``: the dates on which ``ticker`` has a close.
    """
    d = prices.loc[(prices["ticker"] == ticker) & prices["close"].notna(), "date"]
    if d.empty:
        raise ValueError(f"No {ticker} prices: cannot build the trading calendar")
    observed = pd.DatetimeIndex(sorted(pd.to_datetime(d).unique()), name="date")
    if method == "observed":
        return observed
    if method != "xist":
        raise ValueError("method must be 'xist' or 'observed'")
    return xist_sessions(observed.min(), observed.max())


def xist_sessions(start, end) -> pd.DatetimeIndex:
    """Official Borsa Istanbul sessions (``exchange_calendars`` "XIST") in ``[start, end]``."""
    import exchange_calendars as xcals

    start, end = pd.Timestamp(start), pd.Timestamp(end)
    pad = pd.Timedelta(days=30)  # the calendar object must start before `start`
    with warnings.catch_warnings():  # pandas 3 deprecation inside exchange_calendars
        warnings.simplefilter("ignore", category=FutureWarning)
        warnings.simplefilter("ignore", category=DeprecationWarning)
        cal = xcals.get_calendar("XIST", start=start - pad, end=end + pad)
    s = pd.DatetimeIndex(cal.sessions)
    s = s.tz_localize(None) if s.tz is not None else s
    return pd.DatetimeIndex(s[(s >= start) & (s <= end)], name="date")


def compare_with_xist(calendar: pd.DatetimeIndex) -> dict[str, list[date]]:
    """Compare an observed calendar with XIST (diagnostic, D-013)."""
    xist = xist_sessions(calendar.min(), calendar.max())
    return {
        "only_in_data": [d.date() for d in calendar.difference(xist)],
        "only_in_xist": [d.date() for d in xist.difference(calendar)],
    }


# --------------------------------------------------------------------------- alignment
def align_series(
    obs: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    fill: str,
    max_ffill: int = 5,
    as_of: date | None = None,
) -> pd.Series:
    """Align one series (``date, value[, release_date]``) to ``calendar``.

    For ``fill == "release"`` the value becomes *visible* on its ``release_date`` (or the next
    trading day), not on its reference date.
    """
    o = obs.copy()
    o["date"] = pd.to_datetime(o["date"])
    if fill == "release":
        if "release_date" not in o or o["release_date"].isna().all():
            raise ValueError(
                "fill='release' needs release dates (data/manual/cpi_release_dates.csv)"
            )
        n_missing = int(o["release_date"].isna().sum())
        if n_missing:
            log.warning("Dropping %d rows without release_date (unknown availability)", n_missing)
        o = o.dropna(subset=["release_date"])
        o["date"] = pd.to_datetime(o["release_date"])
    if as_of is not None:
        o = o[o["date"] <= pd.Timestamp(as_of)]
    s = o.groupby("date")["value"].last().sort_index()
    if s.empty:
        return pd.Series(index=calendar, dtype=float)

    union = s.index.union(calendar)
    full = s.reindex(union)
    if fill in ("step", "release"):
        full = full.ffill()
    elif fill == "market":
        full = full.ffill(limit=max_ffill)
    elif fill != "none":
        raise ValueError(f"Unknown fill rule {fill!r}")
    out = full.reindex(calendar)
    if as_of is not None:
        out[out.index > pd.Timestamp(as_of)] = float("nan")
    return out


def build_panel(
    prices: pd.DataFrame,
    macro: pd.DataFrame,
    specs: list[SeriesSpec],
    tickers: list[str],
    start: date | None = None,
    end: date | None = None,
    as_of: date | None = None,
    freq: str = "D",
    max_ffill: int = 5,
    price_field: str = "adj_close",
    calendar_method: str = "xist",
) -> pd.DataFrame:
    """Wide panel: one column per ticker (``price_field``) and per macro series id.

    ``prices`` / ``macro`` are long tables as stored in DuckDB.
    """
    if as_of is not None:
        prices = prices[pd.to_datetime(prices["date"]) <= pd.Timestamp(as_of)]
    cal = trading_calendar(prices, method=calendar_method)
    if start:
        cal = cal[cal >= pd.Timestamp(start)]
    end_eff = min(filter(None, [end, as_of]), default=None)
    if end_eff:
        cal = cal[cal <= pd.Timestamp(end_eff)]

    px = prices[prices["ticker"].isin(tickers)].pivot_table(
        index="date", columns="ticker", values=price_field
    )
    px.index = pd.to_datetime(px.index)
    panel = px.reindex(cal)  # stock prices are NOT forward-filled: a missing day stays missing

    for spec in specs:
        obs = macro[macro["series"] == spec.id]
        if obs.empty:
            log.warning("Panel: no data for macro series %s", spec.id)
            panel[spec.id] = float("nan")
            continue
        panel[spec.id] = align_series(obs, cal, spec.fill, max_ffill=max_ffill, as_of=as_of)

    if freq == "W":
        panel = to_weekly(panel)
    elif freq != "D":
        raise ValueError("freq must be 'D' or 'W'")
    return panel


def to_weekly(panel: pd.DataFrame) -> pd.DataFrame:
    """Friday close: last available trading-day value of each Mon–Fri week, labelled Friday."""
    return panel.resample("W-FRI").last().dropna(how="all")
