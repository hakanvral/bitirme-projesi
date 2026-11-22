"""Merton jump-diffusion with a simple, robust calibration (D-004).

Model: r_t = mu + sigma z_t + sum_{k=1..N_t} J_k,  N_t ~ Poisson(lam),  J_k ~ N(mu_J, sigma_J^2).

Calibration (threshold method instead of full maximum likelihood, which is often unstable):
1. robust sigma = 1.4826 * median absolute deviation (insensitive to the jumps themselves);
2. a day is a "jump day" if |r - median| > threshold * robust sigma (default 3);
3. lam = share of jump days; mu_J, sigma_J = mean / std of the jump-day returns minus mu;
4. mu, sigma = mean / std of the remaining (normal) days.
Bounds: lam <= 0.1 per day. With fewer than ``min_jumps`` jump days the jump part cannot be
estimated, so the model falls back to GBM (lam = 0) and records ``fallback_gbm = 1``.
"""

from __future__ import annotations

import numpy as np

from pusula.risk.models.base import RiskModel, Start

MAX_LAMBDA = 0.10


class MertonJumpDiffusion(RiskModel):
    name = "Merton"
    label_tr = "Merton Sıçramalı Difüzyon"

    def __init__(self, threshold: float = 3.0, min_jumps: int = 3) -> None:
        super().__init__()
        self.threshold = threshold
        self.min_jumps = min_jumps

    def fit(self, r: np.ndarray) -> None:
        r = self._check_input(r)
        med = np.median(r)
        rob = 1.4826 * np.median(np.abs(r - med))
        if rob <= 0:
            rob = r.std(ddof=1)
        jump = np.abs(r - med) > self.threshold * rob
        normal = r[~jump]
        mu, sigma = float(normal.mean()), float(normal.std(ddof=1))
        n_j = int(jump.sum())
        if n_j < self.min_jumps:
            self.params = {"mu": float(r.mean()), "sigma": float(r.std(ddof=1)), "lam": 0.0,
                           "mu_j": 0.0, "sigma_j": 0.0, "n_jumps": float(n_j),
                           "fallback_gbm": 1.0}  # fmt: skip
        else:
            jr = r[jump] - mu
            self.params = {
                "mu": mu,
                "sigma": sigma,
                "lam": float(min(n_j / r.size, MAX_LAMBDA)),
                "mu_j": float(jr.mean()),
                "sigma_j": float(jr.std(ddof=1)),
                "n_jumps": float(n_j),
                "fallback_gbm": 0.0,
            }
        self.fitted = True

    def simulate(self, n_paths, horizon, rng, start: Start = "current"):
        self._require_fit()
        p = self.params
        out = p["mu"] + p["sigma"] * rng.standard_normal((n_paths, horizon))
        if p["lam"] > 0:
            n = rng.poisson(p["lam"], size=(n_paths, horizon))
            # sum of n normal jumps ~ N(n mu_J, n sigma_J^2)
            out += n * p["mu_j"] + np.sqrt(n) * p["sigma_j"] * rng.standard_normal(n.shape)
        return out
