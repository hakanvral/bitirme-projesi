"""Historical analogues (CLAUDE.md §6.3): past windows where the shocked factors moved like the
scenario, with the stock returns that actually followed. A sanity check next to the model.

Distance = root mean square of (realised h-week change - shock) / (std of h-week changes), over
the shocked factors only. The k closest **non-overlapping** windows are returned.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def find_analogues(X: pd.DataFrame, returns: pd.DataFrame, shock: dict[str, float], h: int,
                   k: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:  # fmt: skip
    """Returns (windows, realised simple returns per stock for each window)."""
    facs = [f for f in shock if f in X.columns]
    if not facs:
        return pd.DataFrame(), pd.DataFrame()
    S = X[facs].rolling(h, min_periods=h).sum().dropna()
    sd = S.std(ddof=1)
    target = pd.Series({f: shock[f] for f in facs})
    dist = np.sqrt((((S - target) / sd) ** 2).mean(axis=1)).sort_values()
    chosen: list[pd.Timestamp] = []
    for end in dist.index:
        if all(abs((end - c).days) >= 7 * h for c in chosen):
            chosen.append(end)
        if len(chosen) == k:
            break
    win = pd.DataFrame({
        "start": [X.index[X.index.get_loc(e) - h + 1] for e in chosen],
        "end": chosen,
        "distance": [float(dist[e]) for e in chosen],
        **{f"move_{f}": [float(S.loc[e, f]) for e in chosen] for f in facs},
    })  # fmt: skip
    R = returns.rolling(h, min_periods=h).sum()
    realised = np.expm1(R.reindex(chosen)).T  # rows = stocks, columns = window end
    realised.columns = [str(c.date()) for c in chosen]
    return win, realised
