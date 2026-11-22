"""Filtered Historical Simulation (FHS).

1. Fit a GARCH(1,1) (normal quasi-likelihood) to remove volatility clustering;
2. standardised residuals z_t = e_t / sigma_t are roughly independent and keep the real shape of
   the distribution (fat tails, skew);
3. simulate by re-sampling these z's and feeding them back through the GARCH recursion.
So FHS combines "the shape from history" (like HS) with "today's volatility" (like GARCH).
"""

from __future__ import annotations

import numpy as np

from pusula.risk.models.base import ModelFitError, RiskModel, Start, garch_paths
from pusula.risk.models.garch_t import fit_garch


class FilteredHistoricalSimulation(RiskModel):
    name = "FHS"
    label_tr = "Filtrelenmiş Tarihsel Simülasyon"

    def fit(self, r: np.ndarray) -> None:
        r = self._check_input(r, min_obs=100)
        try:
            res = fit_garch(r, "normal")
        except ModelFitError:
            raise
        except Exception as exc:
            raise ModelFitError(f"GARCH filter estimation error: {exc}") from exc
        p = res.params
        mu, omega = float(p["mu"]) / 100, float(p["omega"]) / 1e4
        alpha, beta = float(p["alpha[1]"]), float(p["beta[1]"])
        sig = np.asarray(res.conditional_volatility) / 100
        z = (r - mu) / sig
        z = z[np.isfinite(z)]
        self.z = (z - z.mean()) / z.std()  # standardise exactly (mean 0, variance 1)
        last_s2 = float(sig[-1]) ** 2
        self.params = {
            "mu": mu, "omega": omega, "alpha": alpha, "beta": beta,
            "sigma2_next": omega + alpha * (r[-1] - mu) ** 2 + beta * last_s2,
            "sigma2_uncond": omega / (1 - alpha - beta),
        }  # fmt: skip
        self.fitted = True

    def simulate(self, n_paths, horizon, rng, start: Start = "current"):
        self._require_fit()
        p = self.params

        def draw(n):
            return rng.choice(self.z, size=n, replace=True)

        s2 = p["sigma2_next"] if start == "current" else p["sigma2_uncond"]
        return garch_paths(n_paths, horizon, p["mu"], p["omega"], p["alpha"], p["beta"], s2, draw)
