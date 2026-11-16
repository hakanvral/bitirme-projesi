"""PPK (TCMB Monetary Policy Committee) helpers.

:func:`detect_rate_changes` finds the dates on which the policy-rate series changed. It is a
*helper* for building ``data/manual/ppk_decisions.csv``: meetings that left the rate unchanged
cannot be detected from the series, so the user completes the meeting list manually from the
TCMB press releases. :func:`compare_with_manual` reports mismatches between the two.
"""

from __future__ import annotations

import pandas as pd


def detect_rate_changes(rate: pd.DataFrame, min_change_bp: float = 1.0) -> pd.DataFrame:
    """``date, value`` (policy rate in %) -> one row per change.

    The returned ``effective_date`` is the first date with the new rate. The decision itself is
    usually announced on the meeting day, and the new rate applies from the next day, so the
    meeting date must be confirmed from the press release.
    """
    s = rate.dropna(subset=["value"]).sort_values("date").set_index("date")["value"]
    prev = s.shift()
    change_bp = (s - prev) * 100
    mask = change_bp.abs() >= min_change_bp
    out = pd.DataFrame(
        {
            "effective_date": s.index[mask],
            "previous_rate": prev[mask].to_numpy(),
            "new_rate": s[mask].to_numpy(),
            "change_bp": change_bp[mask].round(2).to_numpy(),
        }
    )
    return out.reset_index(drop=True)


def compare_with_manual(
    detected: pd.DataFrame, manual: pd.DataFrame, max_lag_days: int = 5
) -> pd.DataFrame:
    """Match detected changes to manual PPK meetings (meeting_date <= effective_date <= +lag).

    Returns detected changes with the matched meeting (or NaT) and a ``problem`` column.
    """
    rows = []
    manual = manual.sort_values("meeting_date")
    for _, d in detected.iterrows():
        eff = pd.Timestamp(d["effective_date"])
        cand = manual[
            (manual["meeting_date"] <= eff)
            & (manual["meeting_date"] >= eff - pd.Timedelta(days=max_lag_days))
        ]
        if cand.empty:
            problem = "no PPK meeting in manual file"
            meeting = pd.NaT
        else:
            m = cand.iloc[-1]
            meeting = m["meeting_date"]
            problem = "" if abs(m["change_bp"] - d["change_bp"]) <= 1 else "change_bp differs"
        rows.append({**d.to_dict(), "meeting_date": meeting, "problem": problem})
    return pd.DataFrame(rows)
