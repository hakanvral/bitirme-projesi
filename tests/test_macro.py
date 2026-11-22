"""Phase 3 synthetic-truth tests (CLAUDE.md §9)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from pusula.config import Regimes
from pusula.data.panel import xist_sessions
from pusula.macro import factor_model as fm
from pusula.macro.analogues import find_analogues
from pusula.macro.factors import build_factor_panel, drop_listing_weeks
from pusula.macro.passthrough import PassThrough, estimate
from pusula.macro.scenarios import Engine, ShockSpec, conditional_gaussian, to_factor_shocks
from tests.helpers import price_long

W = pd.date_range("2015-01-02", periods=520, freq="W-FRI")
BETA = {"usdtry": 0.6, "brent": -0.2, "rate": -0.01, "vix": -0.004}


def _synthetic(seed=0, noise=0.02):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(
        rng.multivariate_normal(
            [0.004, 0.0, 0.05, 0.0],
            [
                [0.0006, 0.0001, 0.002, 0.0],
                [0.0001, 0.003, 0.0, -0.02],
                [0.002, 0.0, 1.0, 0.0],
                [0.0, -0.02, 0.0, 9.0],
            ],
            size=len(W),
        ),
        index=W,
        columns=["usdtry", "brent", "rate", "vix"],
    )
    y = 0.001 + X @ pd.Series(BETA) + rng.normal(0, noise, len(W))
    return X, y


def test_factor_model_recovers_known_betas_with_hac():
    X, y = _synthetic()
    f = fm.fit_stock(y, X, "AAA", "A")
    for k, b in BETA.items():
        assert abs(f.beta[k] - b) < 3 * f.se[k], k
    assert f.hac_lags == fm.newey_west_lags(len(W)) and f.n == len(W)
    assert all(v < 2 for v in f.vif.values())  # weakly correlated factors


def test_vif_detects_collinearity():
    rng = np.random.default_rng(1)
    a = rng.normal(size=500)
    X = pd.DataFrame({"a": a, "b": a + 0.05 * rng.normal(size=500), "c": rng.normal(size=500)})
    v = fm.vif(X)
    assert v["a"] > 10 and v["b"] > 10 and v["c"] < 1.5


def test_model_b_keeps_macro_betas_and_raises_r2():
    X, y = _synthetic()
    rng = np.random.default_rng(2)
    mkt = 0.5 * X["usdtry"] + rng.normal(0, 0.02, len(W))
    y2 = y + 0.8 * fm.market_residual(mkt, X)
    a = fm.fit_stock(y2, X, "AAA", "A")
    b = fm.fit_stock(y2, X, "AAA", "B", market=mkt)
    for k in BETA:
        assert b.beta[k] == pytest.approx(a.beta[k], abs=1e-10)
    assert b.r2 > a.r2 and b.beta["market_resid"] == pytest.approx(0.8, abs=0.1)


def test_ridge_shrinks_and_rolling_betas_are_stable():
    X, y = _synthetic()
    f = fm.fit_stock(y, X, "AAA", "A")
    ols = np.array([f.beta[k] * X[k].std() for k in X])
    rid = np.array([f.ridge_beta[k] * X[k].std() for k in X])
    assert np.linalg.norm(rid) <= np.linalg.norm(ols) + 1e-12
    rb = fm.rolling_betas(y, X)
    assert len(rb) == len(W) - fm.ROLL_WEEKS + 1
    assert rb["usdtry"].median() == pytest.approx(0.6, abs=0.15)


def test_conditional_gaussian_matches_analytic():
    mu = np.array([1.0, 2.0])
    s1, s2, rho = 2.0, 3.0, 0.5
    cov = np.array([[s1**2, rho * s1 * s2], [rho * s1 * s2, s2**2]])
    m, c = conditional_gaussian(mu, cov, [0], np.array([3.0]))
    assert m[0] == pytest.approx(2 + rho * s2 / s1 * (3 - 1))
    assert c[0, 0] == pytest.approx(s2**2 * (1 - rho**2))


def _engine(X, betas, resid_zero=True):
    from pusula.macro.factor_model import FactorFit

    resid = pd.Series(
        np.zeros(200) if resid_zero else np.random.default_rng(0).normal(0, 0.01, 200)
    )
    fit = FactorFit(
        "AAA.IS", "A", list(X), 0.0, betas, {}, {}, {}, 0, 0, 200, 4, X.index[0], X.index[-1], resid
    )
    mem = pd.DataFrame(
        [
            {
                "symbol": "AAA.IS",
                "ticker": "AAA",
                "universe": "BIST30",
                "sub_sector": None,
                "in_bist30": True,
                "overlap": False,
            }
        ]
    )
    return Engine.from_weekly(X, {"AAA.IS": fit}, mem, n_paths=20_000)


def test_isolated_vs_propagated_shock():
    X, _ = _synthetic()
    eng = _engine(X, {"usdtry": 1.0, "brent": 0.0, "rate": 0.0, "vix": 0.0})
    # shock only the rate; the stock loads only on usdtry, which is correlated with rate
    shock = ShockSpec({"rate": 2.0})
    iso = eng.run(shock, "1m", "isolated")
    pro = eng.run(shock, "1m", "propagated")
    assert abs(iso["stocks"]["d_exp_ret"].iloc[0]) < 0.002
    h = 4
    i_r, i_u = eng.factors.index("rate"), eng.factors.index("usdtry")
    expected_shift = eng.cov_w[i_u, i_r] / eng.cov_w[i_r, i_r] * (2.0 - h * eng.mu_w[i_r])
    imp = pro["implied"].set_index("factor")
    assert imp.loc["usdtry", "scenario_mean"] - imp.loc["usdtry", "baseline_mean"] == pytest.approx(
        expected_shift, rel=1e-6
    )
    # the stock loads 1.0 on usdtry, so its return shifts by ~ the conditional usdtry shift
    assert pro["stocks"]["d_exp_ret"].iloc[0] == pytest.approx(expected_shift, abs=0.0006)


def test_shock_conversion_and_missing_factor():
    pt = PassThrough("r", 0.8, 0.1, 0.6, 1.0, 10, 5, False)
    spec = to_factor_shocks(
        {"usdtry_pct": 15, "policy_rate_bp": -300, "cds_bp": 200}, ["usdtry", "rate"], pt
    )
    assert spec.factor_shocks["usdtry"] == pytest.approx(np.log(1.15))
    assert spec.factor_shocks["rate"] == pytest.approx(-2.4) and spec.rate_band == pytest.approx(
        (-3.0, -2.4, -1.8)
    )
    assert spec.ignored == ["cds"]
    with pytest.raises(ValueError):
        to_factor_shocks({"policy_rate_bp": 100, "market_rate_bp": 50}, ["rate"], pt)


def test_passthrough_recovers_beta_and_falls_back():
    days = pd.bdate_range("2018-01-01", "2024-12-31")
    rng = np.random.default_rng(3)
    meetings = pd.bdate_range("2018-07-02", "2024-11-01", freq="40B")
    dpol = rng.choice([-2.0, -1.0, 0.0, 1.0, 2.0], size=len(meetings))
    rate = pd.Series(10.0, index=days)
    for m, d in zip(meetings, dpol, strict=True):
        rate[rate.index > m] += 0.7 * d + rng.normal(0, 0.02)
    dec = pd.DataFrame({"meeting_date": meetings, "previous_rate": 10.0, "new_rate": 10.0 + dpol})
    regs = Regimes.model_validate(
        {
            "regimes": [
                {"id": "a", "name_tr": "a", "start": "2018-01-01", "end": "2024-06-01"},
                {"id": "b", "name_tr": "b", "start": "2024-06-01", "end": "2024-08-01"},
                {"id": "c", "name_tr": "c", "start": "2024-08-01", "end": None},
            ]
        }
    )
    _, pt = estimate(dec, rate, date(2024, 12, 31), regs)
    assert pt["a"].beta == pytest.approx(0.7, abs=0.02) and not pt["a"].fallback_pooled
    assert pt["a"].lo < 0.7 < pt["a"].hi
    assert pt["b"].fallback_pooled  # too few rate changes in a 2-month regime


def test_analogues_find_planted_window():
    X, _ = _synthetic()
    X.loc[W[300] : W[303], "usdtry"] = 0.05  # +20% over 4 weeks
    rets = pd.DataFrame({"AAA": np.zeros(len(W))}, index=W)
    win, _ = find_analogues(X, rets, {"usdtry": 0.2}, h=4, k=3)
    assert win["end"].iloc[0] == W[303] and len(win) == 3


def test_drop_listing_weeks():
    r = pd.DataFrame(
        {"OLD": np.ones(20), "NEW": [np.nan] * 5 + [1.0] * 15},
        index=pd.date_range("2020-01-03", periods=20, freq="W-FRI"),
    )
    out = drop_listing_weeks(r, 4)
    assert out["OLD"].notna().all() and out["NEW"].notna().sum() == 11


def test_factor_panel_no_look_ahead():
    sess = xist_sessions("2019-01-02", "2023-12-29")
    rng = np.random.default_rng(4)
    p = pd.concat(
        [
            price_long("XU100.IS", sess, np.exp(np.cumsum(rng.normal(0, 0.01, len(sess))))),
            price_long("AAA.IS", sess, np.exp(np.cumsum(rng.normal(0, 0.02, len(sess))))),
        ]
    )
    macro = pd.concat(
        [
            pd.DataFrame({"date": sess, "series": s, "value": v, "release_date": pd.NaT})
            for s, v in [
                ("usdtry", np.exp(np.cumsum(rng.normal(0.001, 0.01, len(sess))))),
                ("brent", np.exp(np.cumsum(rng.normal(0, 0.02, len(sess))))),
                ("vix", 20 + np.cumsum(rng.normal(0, 0.5, len(sess)))),
                ("tlref", 10 + np.cumsum(rng.normal(0, 0.05, len(sess)))),
            ]
        ]
    )
    t = date(2022, 12, 30)
    fp1 = build_factor_panel(p, macro, ["AAA.IS"], t)
    p2, m2 = p.copy(), macro.copy()
    p2.loc[p2["date"] > pd.Timestamp(t), ["close", "adj_close"]] = 1e9
    m2.loc[m2["date"] > pd.Timestamp(t), "value"] = 1e9
    fp2 = build_factor_panel(p2, m2, ["AAA.IS"], t)
    pd.testing.assert_frame_equal(fp1.X, fp2.X)
    a = fm.fit_stock(fp1.returns["AAA.IS"], fp1.X, "AAA", "A")
    b = fm.fit_stock(fp2.returns["AAA.IS"], fp2.X, "AAA", "A")
    assert a.beta == b.beta


def test_optional_factors_switch_on_when_data_exists_and_ptf_only_for_electricity():
    sess = xist_sessions("2019-01-02", "2023-12-29")
    rng = np.random.default_rng(5)
    p = price_long("XU100.IS", sess, np.exp(np.cumsum(rng.normal(0, 0.01, len(sess)))))

    def series(name, v):
        return pd.DataFrame({"date": sess, "series": name, "value": v, "release_date": pd.NaT})

    base = [
        series("usdtry", np.exp(np.cumsum(rng.normal(0.001, 0.01, len(sess))))),
        series("tlref", 10 + np.cumsum(rng.normal(0, 0.05, len(sess)))),
    ]
    fp = build_factor_panel(p, pd.concat(base), [], date(2023, 12, 29))
    assert "cds" in fp.missing and "cds" not in fp.X
    with_cds = pd.concat(
        [
            *base,
            series("cds_5y", 300 + np.cumsum(rng.normal(0, 5, len(sess)))),
            series("ptf", np.exp(np.cumsum(rng.normal(0, 0.03, len(sess)))) * 1000),
        ]
    )
    fp2 = build_factor_panel(p, with_cds, [], date(2023, 12, 29))
    assert {"cds", "ptf"} <= set(fp2.X.columns) and "cds" not in fp2.missing
    assert "ptf" in fm.factors_for("electricity", list(fp2.X))
    assert "ptf" not in fm.factors_for("natural_gas", list(fp2.X))
    assert "ptf" not in fm.factors_for(None, list(fp2.X))
