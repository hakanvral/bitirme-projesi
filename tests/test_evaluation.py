"""Experiment helpers E1–E5 on synthetic data with a known truth (CLAUDE.md §9)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from pusula.evaluation.factor_eval import oos_r2
from pusula.evaluation.llm_reliability import cohen_kappa, fleiss_kappa
from pusula.evaluation.trading_backtest import (
    decision_dates,
    metrics,
    portfolio,
    positions,
    sharpe_diff_ci,
    sleeve_returns,
    stationary_bootstrap_idx,
)
from pusula.evaluation.var_backtest import christoffersen, kupiec_pof, merton_quantile, tick_loss


# ----------------------------------------------------------------------------- E1
def test_normal_var_has_the_right_exceedance_rate_and_kupiec_accepts():
    rng = np.random.default_rng(0)
    r = rng.normal(0, 0.02, 20_000)
    var99 = -np.expm1(stats.norm.ppf(0.01, 0, 0.02))
    hits = -np.expm1(r) > var99
    assert hits.mean() == pytest.approx(0.01, abs=0.002)
    assert kupiec_pof(int(hits.sum()), len(hits), 0.01)[1] > 0.05
    assert christoffersen(hits, 0.01)["p_ind"] > 0.05


def test_kupiec_rejects_a_too_small_var_and_christoffersen_detects_clusters():
    assert kupiec_pof(60, 1000, 0.01)[1] < 1e-6
    h = np.zeros(1000, dtype=int)
    h[100:110] = 1  # 10 exceedances in a row
    assert christoffersen(h, 0.01)["p_ind"] < 0.01


def test_merton_quantile_without_jumps_is_the_normal_quantile():
    p = {"mu": 0.001, "sigma": 0.02, "lam": 0.0, "mu_j": 0.0, "sigma_j": 0.0}
    assert merton_quantile(p, 0.01) == pytest.approx(stats.norm.ppf(0.01, 0.001, 0.02))
    pj = {**p, "lam": 0.05, "mu_j": -0.05, "sigma_j": 0.03}
    assert merton_quantile(pj, 0.01) < merton_quantile(p, 0.01)  # jumps fatten the left tail


def test_tick_loss_prefers_the_true_quantile():
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.02, 50_000)
    true = -np.expm1(stats.norm.ppf(0.05, 0, 0.02))
    assert tick_loss(r, np.full(r.size, true), 0.95) < tick_loss(
        r, np.full(r.size, true * 1.5), 0.95
    )


# ----------------------------------------------------------------------------- E2
def test_oos_r2_is_high_for_a_stable_relation_and_negative_for_noise():
    rng = np.random.default_rng(2)
    idx = pd.date_range("2018-01-05", periods=400, freq="W-FRI")
    X = pd.DataFrame({"f": rng.normal(0, 1, 400)}, index=idx)
    y = pd.Series(0.8 * X["f"] + rng.normal(0, 0.3, 400), index=idx)
    assert oos_r2(y, X)["oos_r2"] > 0.8
    noise = pd.Series(rng.normal(0, 1, 400), index=idx)
    assert oos_r2(noise, X)["oos_r2"] < 0.02


# ----------------------------------------------------------------------------- E4
def test_decision_dates_are_week_ends_without_the_last_week():
    sess = pd.bdate_range("2025-11-03", "2025-11-28")
    d = decision_dates(sess, date(2025, 11, 3))
    assert d == [date(2025, 11, 7), date(2025, 11, 14), date(2025, 11, 21)]


def test_position_mapping_keep_and_half():
    k = pd.Series(["BEKLE", "AL", "BEKLE", "ALMA", "BEKLE", None])
    assert positions(k).tolist() == [0, 1, 1, 0, 0, 0]
    assert positions(k, "half").tolist() == [0.5, 1, 0.5, 0, 0.5, 0.5]


def test_sleeve_costs_cash_and_portfolio():
    idx = pd.date_range("2025-01-03", periods=3, freq="W-FRI")
    pos = pd.Series([1.0, 1.0, 0.0], index=idx)
    r = pd.Series([0.10, -0.05, 0.20], index=idx)
    rf = pd.Series([0.01, 0.01, 0.01], index=idx)
    sl = sleeve_returns(pos, r, rf, 0.0015)
    assert sl.tolist() == pytest.approx([0.10 - 0.0015, -0.05, 0.01 - 0.0015])
    two = pd.DataFrame({"a": [0.1, 0.0], "b": [0.0, 0.0]})
    assert portfolio(two).tolist() == pytest.approx([0.05, 0.0])


def test_metrics_and_bootstrap():
    rng = np.random.default_rng(3)
    idx = pd.date_range("2020-01-03", periods=200, freq="W-FRI")
    r = pd.Series(rng.normal(0.004, 0.03, 200), index=idx)
    rf = pd.Series(0.001, index=idx)
    m = metrics(r, rf)
    assert m["weeks"] == 200 and m["max_drawdown"] <= 0 and np.isfinite(m["sharpe"])
    ix = stationary_bootstrap_idx(1000, 4, rng)
    runs = np.diff(ix) == 1
    assert 0.6 < runs.mean() < 0.85  # mean block length 4 -> P(continue) = 0.75
    ci = sharpe_diff_ci(r - rf, r - rf, seed=1, n_boot=200)
    assert ci["sharpe_diff"] == pytest.approx(0.0) and ci["ci_lo"] <= 0 <= ci["ci_hi"]


# ----------------------------------------------------------------------------- E5
def test_kappa_values():
    same = pd.DataFrame({"a": ["AL", "ALMA", "BEKLE", "AL"], "b": ["AL", "ALMA", "BEKLE", "AL"]})
    assert fleiss_kappa(same) == pytest.approx(1.0)
    assert cohen_kappa(same["a"], same["b"]) == pytest.approx(1.0)
    opp = pd.DataFrame({"a": ["AL", "ALMA"] * 10, "b": ["ALMA", "AL"] * 10})
    assert fleiss_kappa(opp) < 0
