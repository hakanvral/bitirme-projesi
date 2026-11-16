"""Manual-CSV fallback (``data/manual/<file>.csv``).

Every manual file has a fixed, documented schema (see ``data/manual/README.md``). The reader
validates the header, parses dates strictly (``YYYY-MM-DD``) and returns the common long format.
Wrong files fail loudly with a message that says what to fix.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# file kind -> required columns (optional columns are allowed in addition)
SCHEMAS: dict[str, list[str]] = {
    "macro": ["date", "value"],
    "cpi": ["period", "value"],  # period = YYYY-MM; release_date optional here
    "cpi_release_dates": ["period", "release_date"],
    "ohlcv": ["date", "open", "high", "low", "close", "volume"],
    "ptf": ["date", "ptf_try_mwh"],  # hourly rows allowed (optional `hour`), averaged per day
    "ppk_decisions": ["meeting_date", "previous_rate", "new_rate", "change_bp"],
}


class ManualFileError(ValueError):
    """Raised when a manual CSV is missing or does not match its schema."""


def _read(path: Path, kind: str) -> pd.DataFrame:
    if not path.exists():
        raise ManualFileError(f"Manual file not found: {path}")
    df = pd.read_csv(path, dtype=str).rename(columns=lambda c: c.strip().lower())
    missing = [c for c in SCHEMAS[kind] if c not in df.columns]
    if missing:
        raise ManualFileError(
            f"{path.name}: missing columns {missing}; expected at least {SCHEMAS[kind]} "
            "(see data/manual/README.md)"
        )
    return df


def _to_date(s: pd.Series, name: str, file: str) -> pd.Series:
    out = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    bad = s[out.isna() & s.notna()]
    if not bad.empty:
        raise ManualFileError(
            f"{file}: column '{name}' has non YYYY-MM-DD values, e.g. {bad.iloc[0]!r}"
        )
    return out


def _to_float(s: pd.Series, name: str, file: str) -> pd.Series:
    out = pd.to_numeric(s, errors="coerce")
    bad = s[out.isna() & s.notna() & (s.str.strip() != "")]
    if not bad.empty:
        raise ManualFileError(
            f"{file}: column '{name}' has non-numeric values, e.g. {bad.iloc[0]!r} "
            "(use '.' as decimal separator)"
        )
    return out


def read_macro(path: Path, series_id: str) -> pd.DataFrame:
    """Daily macro CSV ``date,value`` -> ``date, series, value``."""
    df = _read(path, "macro")
    out = pd.DataFrame(
        {
            "date": _to_date(df["date"], "date", path.name),
            "series": series_id,
            "value": _to_float(df["value"], "value", path.name),
        }
    )
    return out.dropna(subset=["value"]).sort_values("date").reset_index(drop=True)


def read_monthly(path: Path, series_id: str) -> pd.DataFrame:
    """Monthly CSV ``period(YYYY-MM),value[,release_date]``.

    Returns ``date, series, value, release_date``.

    ``date`` is the first day of the reference month. ``release_date`` is kept if present.
    """
    df = _read(path, "cpi")
    period = pd.to_datetime(df["period"], format="%Y-%m", errors="coerce")
    if period.isna().any():
        raise ManualFileError(f"{path.name}: 'period' must be YYYY-MM")
    out = pd.DataFrame(
        {"date": period, "series": series_id, "value": _to_float(df["value"], "value", path.name)}
    )
    out["release_date"] = (
        _to_date(df["release_date"], "release_date", path.name)
        if "release_date" in df.columns
        else pd.NaT
    )
    return out.dropna(subset=["value"]).sort_values("date").reset_index(drop=True)


def read_release_dates(path: Path) -> pd.DataFrame:
    """``period(YYYY-MM),release_date`` -> ``date (month start), release_date``."""
    df = _read(path, "cpi_release_dates")
    period = pd.to_datetime(df["period"], format="%Y-%m", errors="coerce")
    if period.isna().any():
        raise ManualFileError(f"{path.name}: 'period' must be YYYY-MM")
    rel = _to_date(df["release_date"], "release_date", path.name)
    if (rel < period).any():
        raise ManualFileError(f"{path.name}: release_date before its reference month")
    return pd.DataFrame({"date": period, "release_date": rel}).sort_values("date")


def read_ohlcv(path: Path, ticker: str) -> pd.DataFrame:
    """OHLCV CSV -> price long format. ``adj_close`` defaults to ``close`` if absent."""
    df = _read(path, "ohlcv")
    out = pd.DataFrame({"date": _to_date(df["date"], "date", path.name), "ticker": ticker})
    for c in ("open", "high", "low", "close", "volume"):
        out[c] = _to_float(df[c], c, path.name)
    out["adj_close"] = (
        _to_float(df["adj_close"], "adj_close", path.name) if "adj_close" in df else out["close"]
    )
    return out.sort_values("date").reset_index(drop=True)


def read_ptf(path: Path) -> pd.DataFrame:
    """EPİAŞ PTF CSV (hourly or daily rows) -> daily mean ``date, series='ptf', value``."""
    df = _read(path, "ptf")
    tmp = pd.DataFrame(
        {
            "date": _to_date(df["date"], "date", path.name),
            "value": _to_float(df["ptf_try_mwh"], "ptf_try_mwh", path.name),
        }
    )
    daily = tmp.groupby("date", as_index=False)["value"].mean()
    daily["series"] = "ptf"
    return daily[["date", "series", "value"]]


def read_ppk(path: Path) -> pd.DataFrame:
    """PPK decisions CSV, validated. Returns one row per meeting."""
    df = _read(path, "ppk_decisions")
    out = pd.DataFrame({"meeting_date": _to_date(df["meeting_date"], "meeting_date", path.name)})
    for c in ("previous_rate", "new_rate", "change_bp"):
        out[c] = _to_float(df[c], c, path.name)
    for c in ("expected_rate",):
        out[c] = _to_float(df[c], c, path.name) if c in df else float("nan")
    for c in ("source_url", "notes"):
        out[c] = df.get(c, "")
    implied = (out["new_rate"] - out["previous_rate"]) * 100
    bad = (implied - out["change_bp"]).abs() > 1
    if bad.any():
        d = out.loc[bad, "meeting_date"].dt.date.tolist()
        raise ManualFileError(f"{path.name}: change_bp != (new_rate - previous_rate)*100 on {d}")
    return out.sort_values("meeting_date").reset_index(drop=True)
