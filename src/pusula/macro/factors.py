"""Weekly macro factor panel (CLAUDE.md §6.3), point-in-time.

Weekly frequency (Friday close) reduces day-to-day noise and the timing mismatch between the
Istanbul close and global markets (D-040).

Factors (change over the week):
* ``rate``   2Y TRY yield if ``tr_2y`` is available, else TLREF spliced with the interbank O/N rate
             before 2018-12-28 (D-019, D-041): change in percentage points
* ``usdtry`` USD/TRY (EVDS): log change
* ``brent``  Brent: log change
* ``ttf``    Dutch TTF gas: log change
* ``cds``    Türkiye 5Y CDS: change in basis points (only if ``cds_tr_5y.csv`` was provided)
* ``vix``    VIX: change in index points
* ``us10y``  US 10Y yield: change in percentage points
* ``ptf``    EPİAŞ day-ahead electricity price: log change (electricity names only; only if
             available)

A missing optional input simply removes its factor; :func:`availability` reports what is missing
so the pages can warn. Adding the file later only needs ``python -m pusula.data.update`` and a
rerun.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from pusula.data.panel import build_panel
from pusula.data.sources import SeriesSpec

# id -> (transform, source series candidates in order of preference)
FACTOR_DEFS: dict[str, tuple[str, list[str]]] = {
    "rate": ("diff", ["tr_2y", "tlref_spliced"]),
    "usdtry": ("log", ["usdtry"]),
    "brent": ("log", ["brent"]),
    "ttf": ("log", ["ttf"]),
    "cds": ("diff", ["cds_5y"]),
    "vix": ("diff", ["vix"]),
    "us10y": ("diff", ["us10y"]),
    "ptf": ("log", ["ptf"]),
}
ORDER = list(FACTOR_DEFS)
ELECTRICITY_ONLY = {"ptf"}
MIN_SERIES_WEEKS = 104  # a factor needs >= 2 years of weekly data to be used
LISTING_WEEKS = 4  # first weekly returns after a stock's first price are dropped (D-047)


def drop_listing_weeks(rets: pd.DataFrame, n: int = LISTING_WEEKS) -> pd.DataFrame:
    """Set the first ``n`` weekly returns of each series to NaN when the series starts after the
    panel start (newly listed stocks): listing-period price discovery is not a macro response."""
    out = rets.copy()
    panel_start = out.index.min()
    for c in out.columns:
        valid = out[c].dropna()
        if valid.empty or valid.index[0] <= panel_start + pd.Timedelta(days=7):
            continue
        out.loc[valid.index[:n], c] = np.nan
    return out


@dataclass
class FactorPanel:
    as_of: date
    X: pd.DataFrame  # weekly factor changes (columns = available factors)
    levels: pd.DataFrame  # weekly factor levels (Friday)
    returns: pd.DataFrame  # weekly stock / index log returns (columns = symbols)
    rate_source: str
    missing: list[str] = field(default_factory=list)
    daily_rate: pd.Series | None = None  # daily rate-factor level (for pass-through)


def splice_tlref(macro: pd.DataFrame) -> pd.DataFrame:
    """Add series ``tlref_spliced``: TLREF, and before its first date the interbank O/N rate."""
    t = macro[macro["series"] == "tlref"]
    i = macro[macro["series"] == "interbank_on"]
    if t.empty:
        return macro
    first = t["date"].min()
    sp = pd.concat([i[i["date"] < first], t]).assign(series="tlref_spliced")
    return pd.concat([macro, sp], ignore_index=True)


def _specs(series: list[str]) -> list[SeriesSpec]:
    fill = {"tlref_spliced": "market"}
    return [SeriesSpec(id=s, source="manual", fill=fill.get(s, "market")) for s in series]


def build_factor_panel(
    prices: pd.DataFrame,
    macro: pd.DataFrame,
    symbols: list[str],
    as_of: date,
    start: date | None = None,
) -> FactorPanel:
    """Weekly factors and weekly stock log returns using only data up to ``as_of``."""
    macro = splice_tlref(macro)
    upto = macro[macro["date"] <= pd.Timestamp(as_of)].dropna(subset=["value"])
    weeks = upto.groupby("series")["date"].apply(lambda d: d.dt.to_period("W-FRI").nunique())
    chosen, missing = {}, []
    for fid, (_, cands) in FACTOR_DEFS.items():
        # first candidate with enough history; a short file (e.g. a 2Y export covering only a
        # few weeks) must not knock out the factor: fall back to the next candidate (D-049)
        long_enough = [c for c in cands if weeks.get(c, 0) >= MIN_SERIES_WEEKS]
        for c in cands:
            if c in weeks and weeks[c] < MIN_SERIES_WEEKS:
                missing.append(f"{c}(short)" if c != fid else f"{fid}(short)")
        if long_enough:
            chosen[fid] = long_enough[0]
        elif fid not in {m.split("(")[0] for m in missing}:
            missing.append(fid)
    if chosen.get("rate") != "tr_2y" and "tr_2y" not in weeks:
        missing.append("tr_2y")

    tick = sorted(set(symbols) | {"XU100.IS"})
    panel = build_panel(
        prices, macro, _specs(list(set(chosen.values()))), tick, start=start, as_of=as_of, freq="W"
    )
    levels = pd.DataFrame({fid: panel[src] for fid, src in chosen.items()})
    X = pd.DataFrame(index=levels.index)
    for fid in levels:
        tr = FACTOR_DEFS[fid][0]
        lv = levels[fid].where(levels[fid] > 0) if tr == "log" else levels[fid]
        X[fid] = np.log(lv).diff() if tr == "log" else lv.diff()
    # drop factors without enough history (e.g. a CDS file covering only a few months)
    for fid in list(X):
        if X[fid].notna().sum() < MIN_SERIES_WEEKS:
            missing.append(f"{fid}(short)")
            X = X.drop(columns=fid)
    rets = drop_listing_weeks(np.log(panel[[c for c in tick if c in panel]]).diff())

    daily = macro[
        (macro["series"] == chosen.get("rate", "")) & (macro["date"] <= pd.Timestamp(as_of))
    ]
    daily_rate = daily.set_index("date")["value"].sort_index() if not daily.empty else None
    return FactorPanel(
        as_of=as_of,
        X=X.iloc[1:],
        levels=levels,
        returns=rets.iloc[1:],
        rate_source=chosen.get("rate", "none"),
        missing=sorted(set(missing)),
        daily_rate=daily_rate,
    )


def availability(fp: FactorPanel) -> dict[str, bool]:
    return {f: f in fp.X.columns for f in ORDER}
