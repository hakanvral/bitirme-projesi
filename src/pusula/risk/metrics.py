"""Risk metrics computed from simulated paths (and, for EVT and beta, from history).

Conventions (plain language)
* **Loss** = -(simple return), so a 7% fall is a loss of 0.07. VaR and CVaR are reported as
  positive loss fractions.
* **VaR 99%, 1 day** = the loss that is exceeded on only 1 day in 100 (according to the model).
* **CVaR / Expected Shortfall 99%** = the average loss on those worst 1-in-100 days. It says how
  bad the bad days are, not just where they start.
* Multi-day horizons use the simulated paths directly (sum of daily log returns), not the
  "1-day x sqrt(days)" shortcut (D-034).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

FAN_PCTS = (5, 25, 50, 75, 95)


def losses(log_ret: np.ndarray) -> np.ndarray:
    return -np.expm1(log_ret)


def var_cvar(log_ret: np.ndarray, level: float) -> tuple[float, float]:
    """VaR and CVaR (positive loss fractions) at confidence ``level`` (e.g. 0.99)."""
    loss = losses(np.asarray(log_ret))
    var = float(np.quantile(loss, level))
    tail = loss[loss >= var]
    return var, float(tail.mean()) if tail.size else var


def prob_loss_beyond(log_ret: np.ndarray, threshold: float = 0.10) -> float:
    """P(simple return < -threshold)."""
    return float(np.mean(np.expm1(log_ret) < -threshold))


def max_drawdowns(paths: np.ndarray) -> np.ndarray:
    """Maximum drawdown of each path (fraction of the running peak, starting at price 1)."""
    wealth = np.exp(np.cumsum(paths, axis=1))
    wealth = np.concatenate([np.ones((paths.shape[0], 1)), wealth], axis=1)
    peak = np.maximum.accumulate(wealth, axis=1)
    return (1 - wealth / peak).max(axis=1)


def fan_chart(paths: np.ndarray, pcts=FAN_PCTS) -> dict[str, list[float]]:
    """Percentiles of the price level (start = 1) for each future day."""
    wealth = np.exp(np.cumsum(paths, axis=1))
    q = np.percentile(wealth, pcts, axis=0)
    return {f"p{p}": [round(float(x), 6) for x in row] for p, row in zip(pcts, q, strict=True)}


def histogram(x: np.ndarray, bins: int = 60) -> dict[str, list[float]]:
    counts, edges = np.histogram(x, bins=bins, density=True)
    return {"edges": [float(e) for e in edges], "density": [float(c) for c in counts]}


def beta_ols(stock: pd.Series, market: pd.Series) -> tuple[float, int]:
    """OLS beta of daily stock log returns on XU100 log returns (common dates)."""
    j = pd.concat([stock, market], axis=1, join="inner").dropna()
    if len(j) < 30:
        return float("nan"), len(j)
    x, y = j.iloc[:, 1].to_numpy(), j.iloc[:, 0].to_numpy()
    return float(np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1)), len(j)


# --------------------------------------------------------------------------- EVT (D-036)
def decluster(exceed_idx: np.ndarray, run_length: int) -> list[np.ndarray]:
    """Runs declustering: a new cluster starts when more than ``run_length`` non-exceedance
    days separate two exceedances. Returns the index arrays of each cluster."""
    if exceed_idx.size == 0:
        return []
    breaks = np.where(np.diff(exceed_idx) > run_length)[0] + 1
    return np.split(exceed_idx, breaks)


def evt_tail(log_ret: np.ndarray, threshold_q: float = 0.95, run_length: int = 5,
             min_clusters: int = 20) -> dict:  # fmt: skip
    """Peaks-over-threshold tail index of the **loss** distribution, with declustering.

    Plain language: we look only at the worst ~5% of days, group extreme days that happen close
    together (one crisis = one event), keep the worst day of each group, and fit a Generalised
    Pareto Distribution to how far these go beyond the threshold. Its shape xi is the tail index:
    xi > 0 means fat tails (extreme losses more likely than a normal distribution suggests);
    roughly, xi = 0.25 behaves like a Student-t with 4 degrees of freedom.
    """
    loss = losses(np.asarray(log_ret))
    u = float(np.quantile(loss, threshold_q))
    idx = np.where(loss > u)[0]
    clusters = decluster(idx, run_length)
    out = {"threshold": u, "n_obs": int(loss.size), "n_exceedances": int(idx.size),
           "n_clusters": len(clusters), "fitted": False, "xi": None, "scale": None,
           "extremal_index": (len(clusters) / idx.size) if idx.size else None}  # fmt: skip
    if len(clusters) < min_clusters:
        out["reason"] = f"too few clusters ({len(clusters)} < {min_clusters})"
        return out
    peaks = np.array([loss[c].max() for c in clusters]) - u
    xi, _, scale = stats.genpareto.fit(peaks, floc=0)
    out.update({"fitted": True, "xi": float(xi), "scale": float(scale)})
    return out
