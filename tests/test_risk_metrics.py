import numpy as np
import pandas as pd
import pytest
from scipy import stats

from pusula.risk import critic, metrics
from pusula.risk.level import assign_risk_levels


def test_var_cvar_match_lognormal_analytics():
    mu, s = 0.0005, 0.02
    r = np.random.default_rng(0).normal(mu, s, 2_000_000)
    var, cvar = metrics.var_cvar(r, 0.99)
    q = mu + s * stats.norm.ppf(0.01)
    assert var == pytest.approx(-np.expm1(q), rel=0.01)
    # E[e^R | R < q] for R ~ N(mu, s^2)
    e_tail = np.exp(mu + s**2 / 2) * stats.norm.cdf((q - mu - s**2) / s) / 0.01
    assert cvar == pytest.approx(1 - e_tail, rel=0.01)


def test_prob_loss_and_drawdown_on_known_path():
    assert metrics.prob_loss_beyond(np.log(np.array([0.85, 0.95, 1.1, 0.89])), 0.10) == 0.5
    dd = metrics.max_drawdowns(np.array([[0.1, -0.2, 0.05]]))
    assert dd[0] == pytest.approx(1 - np.exp(-0.2))


def test_beta_recovered():
    rng = np.random.default_rng(1)
    x = pd.Series(rng.normal(0, 0.01, 1000))
    y = 1.3 * x + pd.Series(rng.normal(0, 0.005, 1000))
    b, n = metrics.beta_ols(y, x)
    assert b == pytest.approx(1.3, abs=0.05) and n == 1000


def test_decluster_toy():
    cl = metrics.decluster(np.array([1, 2, 3, 10, 11, 30]), run_length=5)
    assert [c.tolist() for c in cl] == [[1, 2, 3], [10, 11], [30]]


def test_evt_tail_index_student_t():
    r = stats.t.rvs(4, size=60_000, random_state=2) * 0.01
    out = metrics.evt_tail(r, 0.95, run_length=0, min_clusters=20)
    assert out["fitted"] and 0.1 < out["xi"] < 0.45  # theory: 1/nu = 0.25


def test_evt_reports_insufficient_data():
    out = metrics.evt_tail(np.random.default_rng(3).normal(0, 0.01, 200), 0.95, 5, 20)
    assert not out["fitted"] and "too few clusters" in out["reason"]


def test_critic_prefers_matching_model_and_schemes():
    rng = np.random.default_rng(4)
    hist = rng.normal(0, 0.02, 500)
    sims = {
        "good": rng.normal(0, 0.02, (200, 500)),
        "wide": rng.normal(0, 0.04, (200, 500)),
        "shifted": rng.normal(0.01, 0.02, (200, 500)),
    }
    table = critic.critic_table(hist, sims)
    sel, by_scheme, sc = critic.select(table)
    assert sel == "good" and set(by_scheme) == set(critic.WEIGHT_SCHEMES)
    assert sc["good"] < sc["wide"]


def test_risk_level_is_deterministic_relative_ranking():
    df = pd.DataFrame(
        {
            "ticker": list("ABCDEFGH"),
            "vol_ann": np.arange(1, 9) / 10,
            "cvar99_1d": np.arange(1, 9) / 100,
        }
    )
    out = assign_risk_levels(df).set_index("ticker")
    assert out.loc["A", "risk_level"] == "dusuk" and out.loc["H", "risk_level"] == "cok_yuksek"
    assert out["risk_level"].tolist() == assign_risk_levels(df)["risk_level"].tolist()
