"""GARCH(1,1) with Student-t innovations (via the ``arch`` package).

Volatility tomorrow depends on today's volatility and today's surprise:
sigma2_{t+1} = omega + alpha e_t^2 + beta sigma2_t. This reproduces volatility clustering
(calm and stormy periods). Student-t shocks give fatter tails than the normal distribution.
Returns are scaled by 100 for numerical stability during estimation (standard practice with
``arch``) and scaled back afterwards.
"""

from __future__ import annotations

import warnings

import numpy as np
from arch import arch_model

from pusula.risk.models.base import ModelFitError, RiskModel, Start, garch_paths


def fit_garch(r: np.ndarray, dist: str):
    am = arch_model(r * 100, mean="Constant", vol="GARCH", p=1, q=1, dist=dist, rescale=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = am.fit(disp="off", show_warning=False)
    if res.convergence_flag != 0:
        raise ModelFitError(f"GARCH optimiser did not converge (flag {res.convergence_flag})")
    p = res.params
    alpha, beta = float(p["alpha[1]"]), float(p["beta[1]"])
    if not (alpha >= 0 and beta >= 0 and alpha + beta < 0.999):
        raise ModelFitError(f"non-stationary GARCH (alpha+beta={alpha + beta:.3f})")
    return res


class GarchT(RiskModel):
    name = "GARCH-t"
    label_tr = "GARCH(1,1) Student-t"

    def fit(self, r: np.ndarray) -> None:
        r = self._check_input(r, min_obs=100)
        try:
            res = fit_garch(r, "t")
        except ModelFitError:
            raise
        except Exception as exc:  # arch can raise various numerical errors
            raise ModelFitError(f"GARCH-t estimation error: {exc}") from exc
        p = res.params
        nu = float(p["nu"])
        if nu <= 2.05:
            raise ModelFitError(f"Student-t degrees of freedom too low (nu={nu:.2f})")
        mu, omega = float(p["mu"]) / 100, float(p["omega"]) / 1e4
        alpha, beta = float(p["alpha[1]"]), float(p["beta[1]"])
        last_e = r[-1] - mu
        last_s2 = float(res.conditional_volatility[-1] / 100) ** 2
        self.params = {
            "mu": mu, "omega": omega, "alpha": alpha, "beta": beta, "nu": nu,
            "sigma2_next": omega + alpha * last_e**2 + beta * last_s2,
            "sigma2_uncond": omega / (1 - alpha - beta),
        }  # fmt: skip
        self.fitted = True

    def simulate(self, n_paths, horizon, rng, start: Start = "current"):
        self._require_fit()
        p = self.params
        nu = p["nu"]
        scale = np.sqrt((nu - 2) / nu)  # standardised t: variance 1

        def draw(n):
            return rng.standard_t(nu, size=n) * scale

        s2 = p["sigma2_next"] if start == "current" else p["sigma2_uncond"]
        return garch_paths(n_paths, horizon, p["mu"], p["omega"], p["alpha"], p["beta"], s2, draw)
