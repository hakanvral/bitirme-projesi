"""Cleaning step: corporate-action corrections (D-024).

Raw downloads stay untouched (``data/raw/*.parquet`` and the ``prices`` table). Corrections from
``config/corporate_actions.yaml`` are applied to a copy, the ``prices_clean`` table, which every
analysis reads.

Action types and ``ratio`` meaning (price factor f multiplies ``adj_close`` of all days BEFORE
the ex-date, so the series becomes continuous):

* ``bonus_issue`` (bedelsiz): ratio = new shares per old share (100% bonus -> 1.0); f = 1/(1+ratio)
* ``split``: ratio = shares after / shares before (2-for-1 -> 2.0); f = 1/ratio
* ``reverse_split``: ratio = shares before / shares after; f = ratio
* ``rights_issue`` (bedelli): ratio = new shares per old share, needs ``subscription_price``;
  f = TERP / cum price, TERP = (P_cum + ratio * S) / (1 + ratio) (theoretical ex-rights price)
* ``factor``: explicit price factor in ``ratio`` (e.g. to undo a wrong vendor adjustment)
* ``bad_print``: the price on ``date`` is removed (set to missing)

Only actions whose ``status`` is in ``apply_statuses`` (default: ``confirmed``) are applied, so a
proposal never changes results before the user has checked it on KAP.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

import pandas as pd
from pydantic import BaseModel, model_validator

from pusula.config import load_yaml

log = logging.getLogger(__name__)

ActionType = Literal["bonus_issue", "split", "reverse_split", "rights_issue", "factor", "bad_print"]


class CorporateAction(BaseModel):
    ticker: str
    date: date  # ex-date: first trading day at the post-action price
    type: ActionType
    ratio: float | None = None
    subscription_price: float | None = None
    status: Literal["proposed", "confirmed", "rejected"] = "proposed"
    source_url: str = ""
    note: str = ""

    @model_validator(mode="after")
    def _check(self) -> CorporateAction:
        if self.type != "bad_print" and (self.ratio is None or self.ratio <= 0):
            raise ValueError(f"{self.ticker} {self.date}: {self.type} needs a positive ratio")
        if self.type == "rights_issue" and self.subscription_price is None:
            raise ValueError(f"{self.ticker} {self.date}: rights_issue needs subscription_price")
        return self

    @property
    def symbol(self) -> str:
        return self.ticker if self.ticker.endswith(".IS") else f"{self.ticker}.IS"

    def price_factor(self, cum_price: float | None = None) -> float:
        r = float(self.ratio or 0)
        if self.type == "bonus_issue":
            return 1.0 / (1.0 + r)
        if self.type == "split":
            return 1.0 / r
        if self.type == "reverse_split":
            return r
        if self.type == "factor":
            return r
        if self.type == "rights_issue":
            if cum_price is None:
                raise ValueError("rights_issue factor needs the cum-rights price")
            terp = (cum_price + r * float(self.subscription_price)) / (1.0 + r)
            return terp / cum_price
        raise ValueError(f"No price factor for {self.type}")


class CorporateActions(BaseModel):
    apply_statuses: list[str] = ["confirmed"]
    actions: list[CorporateAction] = []


def load_actions() -> CorporateActions:
    return CorporateActions.model_validate(load_yaml("corporate_actions.yaml"))


def apply_generic_rules(prices: pd.DataFrame, sessions: pd.DatetimeIndex | None) -> pd.DataFrame:
    """Generic cleaning rules that need no per-stock decision (D-025).

    1. Rows on days that are not Borsa Istanbul sessions are dropped (e.g. Yahoo rows on
       2018-01-01 or on the cancelled session 2023-02-08).
    2. Stale rows: zero volume AND close equal to the previous close -> prices set to missing.
       Yahoo fills days it lacks with the previous close and volume 0 (e.g. 2020-03-11), which
       would otherwise merge two days' moves into one.
    """
    out = prices.copy()
    out["date"] = pd.to_datetime(out["date"])
    if sessions is not None and len(sessions):
        lo, hi = sessions.min(), sessions.max()
        in_range = (out["date"] >= lo) & (out["date"] <= hi)
        out = out[~in_range | out["date"].isin(sessions)]
    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)
    prev_close = out.groupby("ticker")["close"].shift()
    stale = (out["volume"].fillna(0) == 0) & (out["close"] == prev_close)
    stale &= ~out["ticker"].str.startswith("X")  # indices report no volume on some feeds
    out.loc[stale, ["open", "high", "low", "close", "adj_close"]] = float("nan")
    if stale.any():
        log.info("Generic cleaning: %d stale zero-volume rows set to missing", int(stale.sum()))
    return out


def apply_actions(prices: pd.DataFrame, cfg: CorporateActions) -> pd.DataFrame:
    """Return a corrected copy of the long ``prices`` table (``adj_close`` adjusted)."""
    out = prices.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)
    for a in sorted(cfg.actions, key=lambda x: x.date, reverse=True):
        if a.status not in cfg.apply_statuses:
            continue
        mask_t = out["ticker"] == a.symbol
        ex = pd.Timestamp(a.date)
        if a.type == "bad_print":
            out.loc[mask_t & (out["date"] == ex), ["open", "high", "low", "close", "adj_close"]] = (
                float("nan")
            )
            continue
        before = mask_t & (out["date"] < ex)
        if not before.any():
            log.warning("Corporate action %s %s: no prices before ex-date", a.ticker, a.date)
            continue
        cum = float(out.loc[before, "close"].dropna().iloc[-1])  # last cum price (unadjusted)
        f = a.price_factor(cum)
        out.loc[before, "adj_close"] = out.loc[before, "adj_close"] * f
        log.info("Applied %s %s %s: factor %.6f", a.ticker, a.date, a.type, f)
    return out


def rebuild_clean_prices(store, cfg: CorporateActions | None = None) -> int:
    """Rebuild ``prices_clean`` from ``prices`` + corporate actions. Returns row count."""
    from pusula.data.panel import trading_calendar

    cfg = cfg or load_actions()
    raw = store.prices(clean=False)
    if raw.empty:
        return 0
    try:
        sessions = trading_calendar(raw)
    except ValueError:
        sessions = None
    clean = apply_actions(apply_generic_rules(raw, sessions), cfg)
    store.replace_prices_clean(clean)
    return len(clean)
