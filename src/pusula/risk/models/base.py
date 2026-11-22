"""Common interface for all risk models.

Every model works on **daily log returns** (a 1-D numpy array):

* ``fit(r)`` estimates the parameters; it raises :class:`ModelFitError` with a readable reason
  when calibration fails (the engine then skips the model, D-035).
* ``simulate(n_paths, horizon, rng, start="current")`` returns an array ``(n_paths, horizon)``
  of simulated daily log returns.
  - ``start="current"``: the forward-looking simulation used for risk metrics. Volatility models
    start from today's estimated volatility.
  - ``start="unconditional"``: start from the model's long-run state. The critic uses this to
    compare a model's typical behaviour with the history it was fitted on (D-034).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

import numpy as np

Start = Literal["current", "unconditional"]


class ModelFitError(RuntimeError):
    """Calibration failed; the message is stored in the RiskReport."""


class RiskModel(ABC):
    name: str = "base"
    label_tr: str = ""

    def __init__(self) -> None:
        self.params: dict[str, float] = {}
        self.fitted = False

    @abstractmethod
    def fit(self, r: np.ndarray) -> None: ...

    @abstractmethod
    def simulate(self, n_paths: int, horizon: int, rng: np.random.Generator,
                 start: Start = "current") -> np.ndarray: ...  # fmt: skip

    def _check_input(self, r: np.ndarray, min_obs: int = 50) -> np.ndarray:
        r = np.asarray(r, dtype=float)
        r = r[np.isfinite(r)]
        if r.size < min_obs:
            raise ModelFitError(f"too few returns ({r.size} < {min_obs})")
        if np.std(r) <= 0:
            raise ModelFitError("zero variance (constant price)")
        return r

    def _require_fit(self) -> None:
        if not self.fitted:
            raise RuntimeError(f"{self.name}: simulate() called before fit()")


def garch_paths(
    n_paths: int,
    horizon: int,
    mu: float,
    omega: float,
    alpha: float,
    beta: float,
    sigma2_start: float,
    draw_z,
) -> np.ndarray:
    """Vectorised GARCH(1,1) recursion: r_t = mu + e_t, e_t = sigma_t z_t,
    sigma2_{t+1} = omega + alpha e_t^2 + beta sigma2_t. ``draw_z(size)`` returns standardised
    shocks (mean 0, variance 1)."""
    out = np.empty((n_paths, horizon))
    s2 = np.full(n_paths, sigma2_start, dtype=float)
    for t in range(horizon):
        e = np.sqrt(s2) * draw_z(n_paths)
        out[:, t] = mu + e
        s2 = omega + alpha * e**2 + beta * s2
    return out
