"""Geometric Brownian Motion (GBM): daily log returns are independent normal draws with constant
mean mu and volatility sigma, both estimated from the window (sample mean / std).
The simplest model; it ignores fat tails and volatility clustering."""

from __future__ import annotations

import numpy as np

from pusula.risk.models.base import RiskModel, Start


class GBM(RiskModel):
    name = "GBM"
    label_tr = "Geometrik Brown Hareketi"

    def fit(self, r: np.ndarray) -> None:
        r = self._check_input(r)
        self.params = {"mu": float(r.mean()), "sigma": float(r.std(ddof=1))}
        self.fitted = True

    def simulate(self, n_paths, horizon, rng, start: Start = "current"):
        self._require_fit()
        p = self.params
        return p["mu"] + p["sigma"] * rng.standard_normal((n_paths, horizon))
