"""Yahoo Finance adapter (via the ``yfinance`` package).

We request **unadjusted** OHLC plus the separate ``Adj Close`` column (``auto_adjust=False``):
* ``adj_close`` (dividend- and split/bonus-adjusted) is used for returns;
* ``close`` x ``volume`` approximates traded value in TRY for the liquidity ranking.

The download function is injectable so tests can run on recorded fixtures without network.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd

log = logging.getLogger(__name__)

_FIELD_MAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}
PRICE_COLUMNS = ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]

Downloader = Callable[..., pd.DataFrame]


def _default_downloader(**kwargs) -> pd.DataFrame:
    import yfinance as yf  # imported lazily: tests never need it

    return yf.download(**kwargs)


def to_long(raw: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    """Convert ``yf.download`` output (wide, MultiIndex columns) to the price long format.

    Handles both column orders, ``(ticker, field)`` and ``(field, ticker)``, and single-level
    columns for a single symbol. Symbols that returned no data are simply absent.
    """
    if raw is None or raw.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)

    frames = []
    if isinstance(raw.columns, pd.MultiIndex):
        lvl0 = set(raw.columns.get_level_values(0))
        ticker_level = 0 if lvl0 & set(symbols) else 1
        for sym in symbols:
            if sym not in raw.columns.get_level_values(ticker_level):
                continue
            sub = raw.xs(sym, axis=1, level=ticker_level)
            frames.append(_one(sub, sym))
    else:
        frames.append(_one(raw, symbols[0]))

    if not frames:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    return pd.concat(frames, ignore_index=True)[PRICE_COLUMNS]


def _one(sub: pd.DataFrame, sym: str) -> pd.DataFrame:
    sub = sub.rename(columns=_FIELD_MAP)
    for c in _FIELD_MAP.values():
        if c not in sub.columns:
            sub[c] = float("nan")
    if sub["adj_close"].isna().all():
        sub["adj_close"] = sub["close"]
    out = sub[list(_FIELD_MAP.values())].copy()
    out.index = pd.to_datetime(out.index).tz_localize(None).normalize()
    out = out.dropna(subset=["close"])
    out.insert(0, "ticker", sym)
    out.insert(0, "date", out.index)
    return out.reset_index(drop=True)


def fetch(
    symbols: list[str],
    start: date,
    end: date,
    downloader: Downloader | None = None,
) -> pd.DataFrame:
    """Download daily bars for Yahoo ``symbols`` in ``[start, end]`` (end inclusive)."""
    if not symbols:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    dl = downloader or _default_downloader
    raw = dl(
        tickers=symbols,
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),  # yfinance `end` is exclusive
        interval="1d",
        auto_adjust=False,
        actions=False,
        group_by="ticker",
        progress=False,
        threads=True,
    )
    out = to_long(raw, symbols)
    got = set(out["ticker"].unique())
    for s in symbols:
        if s not in got:
            log.warning("yfinance returned no rows for %s", s)
    return out


def fetch_macro(symbol: str, series_id: str, start: date, end: date, **kw) -> pd.DataFrame:
    """A Yahoo symbol used as a macro series: ``date, series, value`` (unadjusted close)."""
    px = fetch([symbol], start, end, **kw)
    return pd.DataFrame({"date": px["date"], "series": series_id, "value": px["close"]})


def fetch_long_name(symbol: str) -> str | None:
    """Official company name from Yahoo (used only by the universe validator)."""
    import yfinance as yf

    try:
        info = yf.Ticker(symbol).get_info()
    except Exception as exc:  # network / parsing problems must not stop validation
        log.warning("Could not fetch info for %s: %s", symbol, exc)
        return None
    return info.get("longName") or info.get("shortName")
