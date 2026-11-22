"""Critic: score every fitted model against the history it was calibrated on (D-034).

For each model we simulate ``critic_paths`` paths as long as the calibration window, starting
from the model's long-run state, and compare with history at two horizons:
* 1 day: all simulated daily returns vs the window's daily returns;
* 10 days: non-overlapping 10-day sums of the simulated paths vs overlapping 10-day sums of
  history. This catches volatility clustering, which 1-day returns alone cannot show.

Eight criteria per horizon, all "lower is better" and unit-free (divided by the historical
standard deviation where needed): KS statistic, Wasserstein distance, mean error, volatility
error, skewness error, excess-kurtosis error, 1% quantile error, 5% quantile error.

Scores: each criterion is ranked across models (1 = best); a model's score is the weighted
average rank. Equal weights select the model (accepted by the user); tail-heavy, moment-heavy
and multi-day-only weights are stored as a sensitivity check for the paper.

Caveat: the comparison is in-sample. Historical Simulation reproduces the 1-day distribution of
its own window by construction, so it has an in-sample advantage at 1 day; the out-of-sample
test is the VaR backtest (E1, Phase 5).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

CRITERIA = ["ks", "wasserstein", "mean", "vol", "skew", "kurt", "q01", "q05"]
HORIZONS = (1, 10)
MOMENT = {"mean", "vol", "skew", "kurt"}
TAIL = {"q01", "q05"}


def _w(fn) -> dict[str, float]:
    """Weights per table column '<criterion>_<h>d'."""
    return {f"{c}_{h}d": fn(c, h) for c in CRITERIA for h in HORIZONS}


WEIGHT_SCHEMES: dict[str, dict[str, float]] = {
    "equal": _w(lambda c, h: 1.0),
    "tail_heavy": _w(lambda c, h: 3.0 if c in TAIL else 1.0),
    "moment_heavy": _w(lambda c, h: 3.0 if c in MOMENT else 1.0),
    # Diagnostic: ignores the 1-day criteria where HS has an in-sample advantage (D-034).
    "multi_day_only": _w(lambda c, h: 1.0 if h > 1 else 0.0),
}


def compare(hist: np.ndarray, sim: np.ndarray) -> dict[str, float]:
    hist, sim = np.asarray(hist), np.asarray(sim)
    s = hist.std(ddof=1)
    return {
        "ks": float(stats.ks_2samp(hist, sim).statistic),
        "wasserstein": float(stats.wasserstein_distance(hist, sim) / s),
        "mean": float(abs(sim.mean() - hist.mean()) / s),
        "vol": float(abs(sim.std(ddof=1) / s - 1)),
        "skew": float(abs(stats.skew(sim) - stats.skew(hist))),
        "kurt": float(abs(stats.kurtosis(sim) - stats.kurtosis(hist))),
        "q01": float(abs(np.quantile(sim, 0.01) - np.quantile(hist, 0.01)) / s),
        "q05": float(abs(np.quantile(sim, 0.05) - np.quantile(hist, 0.05)) / s),
    }


def horizon_sums(hist: np.ndarray, sim_paths: np.ndarray, h: int) -> tuple[np.ndarray, np.ndarray]:
    if h == 1:
        return hist, sim_paths.ravel()
    hs = np.convolve(hist, np.ones(h), mode="valid")  # overlapping h-day sums
    n = sim_paths.shape[1] // h
    ss = sim_paths[:, : n * h].reshape(sim_paths.shape[0], n, h).sum(axis=2).ravel()
    return hs, ss


def critic_table(hist: np.ndarray, sims: dict[str, np.ndarray]) -> pd.DataFrame:
    """Rows = models, columns = '<criterion>_<h>d'."""
    rows = {}
    for name, paths in sims.items():
        row = {}
        for h in HORIZONS:
            hh, ss = horizon_sums(hist, paths, h)
            row.update({f"{k}_{h}d": v for k, v in compare(hh, ss).items()})
        rows[name] = row
    return pd.DataFrame.from_dict(rows, orient="index")


def scores(table: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted average rank (lower = better)."""
    ranks = table.rank(axis=0, method="average")
    w = pd.Series({col: weights[col] for col in table.columns})
    return (ranks * w).sum(axis=1) / w.sum()


def select(table: pd.DataFrame) -> tuple[str, dict[str, str], pd.Series]:
    """Selected model (equal weights), the selection under every scheme, and equal scores."""
    by_scheme = {name: str(scores(table, w).idxmin()) for name, w in WEIGHT_SCHEMES.items()}
    eq = scores(table, WEIGHT_SCHEMES["equal"])
    return str(eq.idxmin()), by_scheme, eq
