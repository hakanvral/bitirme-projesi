"""Data quality report (CLAUDE.md §5): coverage, missing days, stale prices, jumps, freshness.

Definitions (also shown on the Veri Durumu page):
* coverage %  = trading days with a value / trading days between the series' first and last date
* missing     = trading days in that range without a value
* stale days  = days inside runs of unchanged values longer than ``stale_days``
                (suspicious for a stock: often a trading halt or a data gap that was filled)
* jumps       = daily |simple return| of the adjusted close above ``jump_threshold`` (±25%).
                Usually an unadjusted bonus issue ("bedelsiz"): flagged for manual review,
                not fixed.
Monthly series are checked for missing months instead of days.
"""

from __future__ import annotations

import pandas as pd

OK, WARN, MISSING = "ok", "warn", "missing"
COVERAGE_WARN = 95.0
MIN_OBS = 20  # fewer observations than this = effectively no history (e.g. XELKT on Yahoo)


def _stale_count(values: pd.Series, stale_days: int) -> int:
    v = values.dropna()
    if v.empty:
        return 0
    run_id = (v != v.shift()).cumsum()
    run_len = v.groupby(run_id).transform("size")
    return int((run_len > stale_days).sum())


def jump_flags(
    prices: pd.DataFrame,
    threshold: float = 0.105,
    index_threshold: float | None = None,
    is_index=lambda t: str(t).startswith("X"),
) -> pd.DataFrame:
    """Rows where the adjusted close moved more than the threshold vs the previous valid row.

    Stocks use ``threshold``; index tickers (``is_index``) use ``index_threshold`` (defaults to
    ``threshold``). Missing prices are skipped, so the return spans the gap (``gap_days``).
    """
    p = prices.dropna(subset=["adj_close"]).sort_values(["ticker", "date"]).copy()
    g = p.groupby("ticker")
    p["prev_adj_close"] = g["adj_close"].shift()
    p["prev_date"] = g["date"].shift()
    p["return"] = p["adj_close"] / p["prev_adj_close"] - 1
    p["raw_return"] = p["close"] / g["close"].shift() - 1
    thr = p["ticker"].map(
        lambda t: index_threshold if (index_threshold is not None and is_index(t)) else threshold
    )
    flagged = p[p["return"].abs() > thr]
    cols = ["date", "ticker", "prev_date", "prev_adj_close", "adj_close", "return", "raw_return"]
    return flagged[cols].reset_index(drop=True)


def macro_jump_flags(
    macro: pd.DataFrame, thresholds: dict[str, float], classes: dict[str, str]
) -> pd.DataFrame:
    """Daily macro series with |change| above the threshold of their jump class."""
    rows = []
    for sid, cls in classes.items():
        if cls not in thresholds:
            continue
        s = macro[macro["series"] == sid].sort_values("date")
        r = s["value"] / s["value"].shift() - 1
        hit = s[r.abs() > thresholds[cls]]
        rows += [
            {"date": d, "series": sid, "class": cls, "change": float(x)}
            for d, x in zip(hit["date"], r[hit.index], strict=True)
        ]
    return pd.DataFrame(rows, columns=["date", "series", "class", "change"])


def _daily_stats(dates: pd.Series, values: pd.Series, calendar: pd.DatetimeIndex) -> dict:
    s = pd.Series(values.to_numpy(), index=pd.to_datetime(dates)).dropna()
    first, last = s.index.min(), s.index.max()
    cal = calendar[(calendar >= first) & (calendar <= last)]
    have = s.index.intersection(cal)
    expected = max(len(cal), 1)
    return {
        "first_date": first.date(),
        "last_date": last.date(),
        "coverage_pct": round(100 * len(have) / expected, 2),
        "missing_days": int(len(cal) - len(have)),
    }


def _monthly_stats(dates: pd.Series) -> dict:
    p = pd.to_datetime(dates).dt.to_period("M")
    full = pd.period_range(p.min(), p.max(), freq="M")
    missing = len(full.difference(pd.PeriodIndex(p.unique())))
    return {
        "first_date": p.min().to_timestamp().date(),
        "last_date": p.max().to_timestamp().date(),
        "coverage_pct": round(100 * (len(full) - missing) / len(full), 2),
        "missing_days": int(missing),  # here: missing months
    }


def _status(row: dict) -> str:
    if row.get("first_date") is None:
        return MISSING
    if row.get("n_obs", MIN_OBS) < MIN_OBS:
        return WARN
    if row["coverage_pct"] < COVERAGE_WARN or row["jumps"] > 0 or row["stale_days"] > 0:
        return WARN
    return OK


def build_report(
    prices: pd.DataFrame,
    macro: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    expected_tickers: list[str],
    expected_macro: dict[str, tuple[str, str]],  # id -> (source, freq)
    jump_thresholds: dict[str, float] | None = None,
    stale_days: int = 5,
    macro_classes: dict[str, str] | None = None,
) -> pd.DataFrame:
    """One row per expected ticker and macro series (missing ones included, status 'missing')."""
    th = {"stock": 0.105, "index": 0.10, "fx": 0.10, "commodity": 0.25, **(jump_thresholds or {})}
    rows: list[dict] = []
    jumps = jump_flags(prices, th["stock"], th["index"]) if not prices.empty else pd.DataFrame()
    mjumps = macro_jump_flags(macro, th, macro_classes or {}) if not macro.empty else None
    for t in expected_tickers:
        p = prices[prices["ticker"] == t]
        row: dict = {
            "series": t,
            "kind": "price",
            "source": None,
            "first_date": None,
            "last_date": None,
            "coverage_pct": 0.0,
            "missing_days": 0,
            "stale_days": 0,
            "jumps": 0,
            "last_update": None,
        }
        if not p.empty:
            row.update(_daily_stats(p["date"], p["close"], calendar))
            row["n_obs"] = len(p)
            row["source"] = p["source"].iloc[-1] if "source" in p else None
            row["stale_days"] = _stale_count(p.sort_values("date")["close"], stale_days)
            row["jumps"] = int((jumps["ticker"] == t).sum()) if not jumps.empty else 0
            row["last_update"] = p["updated_at"].max() if "updated_at" in p else None
        row["status"] = _status(row)
        row.pop("n_obs", None)
        rows.append(row)

    for sid, (source, freq) in expected_macro.items():
        m = macro[macro["series"] == sid]
        row = {
            "series": sid,
            "kind": "macro",
            "source": source,
            "first_date": None,
            "last_date": None,
            "coverage_pct": 0.0,
            "missing_days": 0,
            "stale_days": 0,
            "jumps": 0,
            "last_update": None,
        }
        if not m.empty:
            row.update(
                _monthly_stats(m["date"])
                if freq == "M"
                else _daily_stats(m["date"], m["value"], calendar)
            )
            row["source"] = m["source"].iloc[-1] if "source" in m else source
            row["last_update"] = m["updated_at"].max() if "updated_at" in m else None
            if mjumps is not None and not mjumps.empty:
                row["jumps"] = int((mjumps["series"] == sid).sum())
        row["status"] = _status(row)
        rows.append(row)

    return pd.DataFrame(rows)
