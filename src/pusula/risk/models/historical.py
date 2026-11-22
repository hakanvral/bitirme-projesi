"""Historical Simulation (HS): future daily returns are drawn at random (with replacement)
from the returns of the calibration window. No distributional assumption, but every day is
treated as independent, so calm and stormy periods are mixed (no volatility clustering)."""

from __future__ import annotations

import numpy as np

from pusula.risk.models.base import RiskModel, Start


class HistoricalSimulation(RiskModel):
    name = "HS"
    label_tr = "Tarihsel Simülasyon"

    def fit(self, r: np.ndarray) -> None:
        self.r = self._check_input(r)
        self.params = {"n_obs": float(self.r.size)}
        self.fitted = True

    def simulate(self, n_paths, horizon, rng, start: Start = "current"):
        self._require_fit()
        return rng.choice(self.r, size=(n_paths, horizon), replace=True)
