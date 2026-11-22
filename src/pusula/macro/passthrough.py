"""Policy-rate pass-through (CLAUDE.md §6.3, D-042).

Question: when the TCMB changes the policy rate by x bp, how much does the market rate used as
the rate factor (2Y yield, or TLREF when the 2Y yield is not available) move?

For every PPK meeting from 2018-06-01 (D-018) up to ``as_of``:
  d_market = market rate on the 5th session after the meeting - market rate on the last session
             before the meeting  (window [-1, +5], same as the event study E3)
  d_policy = new_rate - previous_rate   (percentage points)

Per regime: d_market = beta * d_policy + e, least squares through the origin, with a 90%
confidence band beta +/- t * se. Meetings without a change are kept (they show what the market
rate does when the policy rate does not move). A regime with fewer than 3 actual rate changes
falls back to the pooled estimate over all regimes, and this is flagged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

from pusula.config import Regimes

FIRST_MEETING = pd.Timestamp("2018-06-01")
POST_SESSIONS = 5
MIN_CHANGES = 3
CI = 0.90


@dataclass
class PassThrough:
    regime: str
    beta: float
    se: float
    lo: float
    hi: float
    n_meetings: int
    n_changes: int
    fallback_pooled: bool

    def convert(self, policy_bp: float) -> tuple[float, float, float]:
        """Policy change in bp -> (low, central, high) market-rate change in percentage points."""
        pp = policy_bp / 100
        a, b = sorted((self.lo * pp, self.hi * pp))
        return a, self.beta * pp, b


def event_changes(decisions: pd.DataFrame, rate: pd.Series, as_of: date) -> pd.DataFrame:
    """One row per meeting with d_policy and d_market (only data up to ``as_of``)."""
    rate = rate.dropna().sort_index()
    rate = rate[rate.index <= pd.Timestamp(as_of)]
    rows = []
    for d in decisions.itertuples():
        m = pd.Timestamp(d.meeting_date)
        if m < FIRST_MEETING:
            continue
        before = rate[rate.index < m]
        after = rate[rate.index > m]
        if before.empty or len(after) < POST_SESSIONS:
            continue  # the post-event window is not complete yet at as_of
        rows.append(
            {
                "meeting_date": m,
                "d_policy": float(d.new_rate - d.previous_rate),
                "d_market": float(after.iloc[POST_SESSIONS - 1] - before.iloc[-1]),
            }
        )
    return pd.DataFrame(rows, columns=["meeting_date", "d_policy", "d_market"])


def _fit(ev: pd.DataFrame) -> tuple[float, float, int]:
    x, y = ev["d_policy"].to_numpy(), ev["d_market"].to_numpy()
    sxx = float(x @ x)
    if sxx == 0 or len(x) < 2:
        return float("nan"), float("nan"), len(x)
    b = float(x @ y) / sxx
    s2 = float(((y - b * x) ** 2).sum()) / (len(x) - 1)
    return b, float(np.sqrt(s2 / sxx)), len(x)


def estimate(
    decisions: pd.DataFrame, rate: pd.Series, as_of: date, regimes: Regimes
) -> tuple[pd.DataFrame, dict[str, PassThrough]]:
    ev = event_changes(decisions, rate, as_of)
    ev["regime"] = [regimes.regime_of(d.date()) for d in ev["meeting_date"]]
    pb, pse, pn = _fit(ev)
    pooled_changes = int((ev["d_policy"] != 0).sum())
    out = {}
    for rg in regimes.regimes:
        sub = ev[ev["regime"] == rg.id]
        n_ch = int((sub["d_policy"] != 0).sum())
        if n_ch >= MIN_CHANGES:
            b, se, n = _fit(sub)
            fb = False
        else:
            b, se, n, fb = pb, pse, len(sub), True
        dof = max((pn if fb else n) - 1, 1)
        tq = stats.t.ppf(0.5 + CI / 2, dof)
        out[rg.id] = PassThrough(rg.id, b, se, b - tq * se, b + tq * se, len(sub), n_ch, fb)
    if pn:
        tq = stats.t.ppf(0.5 + CI / 2, max(pn - 1, 1))
        out["pooled"] = PassThrough(
            "pooled", pb, pse, pb - tq * pse, pb + tq * pse, pn, pooled_changes, False
        )
    return ev, out


def summary_table(pt: dict[str, PassThrough]) -> pd.DataFrame:
    return pd.DataFrame([vars(p) for p in pt.values()])
