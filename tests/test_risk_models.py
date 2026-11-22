"""Synthetic-truth tests for the model library (CLAUDE.md §9)."""

import numpy as np
import pytest

from pusula.risk.models import (
    GBM,
    FilteredHistoricalSimulation,
    GarchT,
    HistoricalSimulation,
    MertonJumpDiffusion,
    ModelFitError,
)
from pusula.risk.models.base import garch_paths

RNG = np.random.default_rng(7)


def test_gbm_recovers_mu_sigma():
    r = 0.0005 + 0.02 * RNG.standard_normal(20_000)
    m = GBM()
    m.fit(r)
    assert m.params["sigma"] == pytest.approx(0.02, rel=0.02)
    assert abs(m.params["mu"] - 0.0005) < 3 * 0.02 / np.sqrt(20_000)
    sims = m.simulate(2000, 10, np.random.default_rng(1))
    assert sims.shape == (2000, 10) and sims.std() == pytest.approx(0.02, rel=0.03)


def test_merton_recovers_jumps():
    n = 40_000
    rng = np.random.default_rng(3)
    jumps = rng.poisson(0.02, n)
    r = (
        0.0002
        + 0.01 * rng.standard_normal(n)
        + jumps * -0.08
        + np.sqrt(jumps) * 0.02 * rng.standard_normal(n)
    )
    m = MertonJumpDiffusion()
    m.fit(r)
    p = m.params
    assert p["fallback_gbm"] == 0.0
    assert 0.015 < p["lam"] < 0.025
    assert p["mu_j"] == pytest.approx(-0.08, abs=0.01)
    assert p["sigma"] == pytest.approx(0.01, rel=0.1)


def test_merton_falls_back_to_gbm_without_jumps():
    r = 0.01 * np.random.default_rng(5).uniform(-1, 1, 400)  # bounded: no 3-sigma outliers
    m = MertonJumpDiffusion()
    m.fit(r)
    assert m.params["fallback_gbm"] == 1.0 and m.params["lam"] == 0.0


def _garch_sample(n, omega, alpha, beta, nu, seed):
    rng = np.random.default_rng(seed)
    scale = np.sqrt((nu - 2) / nu)
    paths = garch_paths(
        1,
        n + 500,
        0.0003,
        omega,
        alpha,
        beta,
        omega / (1 - alpha - beta),
        lambda k: rng.standard_t(nu, size=k) * scale,
    )
    return paths[0, 500:]


def test_garch_t_recovers_parameters():
    r = _garch_sample(6000, 4e-6, 0.08, 0.90, 6.0, seed=11)
    m = GarchT()
    m.fit(r)
    p = m.params
    assert p["alpha"] == pytest.approx(0.08, abs=0.03)
    assert p["beta"] == pytest.approx(0.90, abs=0.04)
    assert 4.0 < p["nu"] < 10.0
    assert p["sigma2_uncond"] == pytest.approx(4e-6 / 0.02, rel=0.35)


def test_fhs_residuals_standardised_and_simulation_shape():
    r = _garch_sample(3000, 4e-6, 0.08, 0.90, 6.0, seed=12)
    m = FilteredHistoricalSimulation()
    m.fit(r)
    assert m.z.mean() == pytest.approx(0, abs=1e-9) and m.z.std() == pytest.approx(1, abs=1e-9)
    sims = m.simulate(1000, 20, np.random.default_rng(0), start="unconditional")
    assert sims.shape == (1000, 20) and np.isfinite(sims).all()


def test_hs_only_resamples_history():
    r = np.array([-0.02, 0.0, 0.01, 0.03] * 30)
    m = HistoricalSimulation()
    m.fit(r)
    assert set(np.unique(m.simulate(100, 5, np.random.default_rng(0)))) <= set(r)


@pytest.mark.parametrize(
    "model",
    [
        GBM(),
        GarchT(),
        FilteredHistoricalSimulation(),
        MertonJumpDiffusion(),
        HistoricalSimulation(),
    ],
)
def test_constant_prices_raise_fit_error(model):
    with pytest.raises(ModelFitError):
        model.fit(np.zeros(300))
