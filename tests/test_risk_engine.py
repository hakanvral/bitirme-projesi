"""Engine tests on a synthetic DuckDB: no look-ahead, short history, failing models."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from pusula.config import RiskCfg
from pusula.data.panel import xist_sessions
from pusula.data.store import Store
from pusula.features.returns import log_returns
from pusula.risk import engine
from pusula.risk.models import ModelFitError
from pusula.risk.models.base import RiskModel
from tests.helpers import price_long

CFG = RiskCfg(n_paths=2000, critic_paths=50, calibration_window=300, min_history=250)
SESS = xist_sessions("2021-01-04", "2024-12-31")
T = date(2023, 12, 29)


def _store(tmp_path, corrupt_after: date | None = None, n_young: int = 0) -> Store:
    rng = np.random.default_rng(0)
    mkt = np.exp(np.cumsum(rng.normal(0.0005, 0.012, len(SESS)))) * 100
    stk = (
        np.exp(
            np.cumsum(0.8 * np.log(mkt / np.r_[mkt[0], mkt[:-1]]) + rng.normal(0, 0.012, len(SESS)))
        )
        * 50
    )
    frames = [price_long("XU100.IS", SESS, mkt), price_long("AAA.IS", SESS, stk)]
    if n_young:
        frames.append(price_long("NEW.IS", SESS[-n_young:], stk[-n_young:]))
    p = pd.concat(frames, ignore_index=True)
    if corrupt_after:
        late = p["date"] > pd.Timestamp(corrupt_after)
        p.loc[late, ["close", "adj_close"]] = 1e9
    st = Store(tmp_path / "t.duckdb")
    st.upsert_prices(p, "test")
    st.replace_prices_clean(p.assign(source="test", updated_at=pd.Timestamp("2024-01-01")))
    return st


def test_report_has_no_look_ahead(tmp_path):
    a = engine.compute_risk_report(
        engine.load_inputs(_store(tmp_path / "a"), T), "AAA.IS", "TRY", CFG, seed=42
    )
    b = engine.compute_risk_report(
        engine.load_inputs(_store(tmp_path / "b", corrupt_after=T), T),
        "AAA.IS",
        "TRY",
        CFG,
        seed=42,
    )
    da, db = (
        a.model_dump(exclude={"seconds_total", "models"}),
        b.model_dump(exclude={"seconds_total", "models"}),
    )
    assert da == db
    assert [m.params for m in a.models] == [m.params for m in b.models]
    assert a.beta_xu100 == pytest.approx(0.8, abs=0.15)


def test_short_history_gives_no_report(tmp_path):
    inp = engine.load_inputs(_store(tmp_path, n_young=200), date(2024, 12, 31))
    with pytest.raises(engine.InsufficientHistoryError):
        engine.compute_risk_report(inp, "NEW.IS", "TRY", CFG, seed=1)


def test_failing_model_is_skipped_and_recorded(tmp_path, monkeypatch):
    class Broken(RiskModel):
        name = "Broken"

        def fit(self, r):
            raise ModelFitError("did not converge (test)")

        def simulate(self, *a, **k):
            raise AssertionError

    from pusula.risk import models as models_mod

    orig = models_mod.default_models
    monkeypatch.setattr(engine, "default_models", lambda *a, **k: [*orig(), Broken()])
    rep = engine.compute_risk_report(
        engine.load_inputs(_store(tmp_path), T), "AAA.IS", "TRY", CFG, seed=1
    )
    broken = next(m for m in rep.models if m.name == "Broken")
    assert not broken.fitted and "converge" in broken.failure_reason
    assert rep.selected_model != "Broken"


def test_log_returns_drop_long_gaps():
    idx = pd.bdate_range("2024-01-01", periods=12)
    px = pd.Series(np.arange(1.0, 13.0), index=idx)
    px.iloc[2:9] = np.nan  # 7 missing sessions
    r = log_returns(px, max_gap=5)
    assert idx[9] not in r.index and len(r) == 1 + 2  # first gap-free pair + last two


def test_holdout_critic_is_default_and_in_sample_is_kept(tmp_path):
    rep = engine.compute_risk_report(
        engine.load_inputs(_store(tmp_path), T), "AAA.IS", "TRY", CFG, seed=3
    )
    assert rep.critic_method == "holdout" and rep.n_holdout == 60  # 20% of a 300-day window
    assert rep.selected_model_insample is not None
    assert set(rep.selection_by_scheme_insample) == set(rep.selection_by_scheme)
    fitted = [m for m in rep.models if m.fitted]
    assert all(m.score is not None and m.score_insample is not None for m in fitted)
    assert all(k.endswith(("_1d", "_10d")) for k in fitted[0].critic)
    # the report uses the full-window fit of the selected model (not the 80% hold-out fit)
    gbm = next(m for m in rep.models if m.name == "GBM")
    r = engine.daily_returns(engine.load_inputs(_store(tmp_path / "x"), T), "AAA.IS", "TRY", 5)
    assert gbm.params["sigma"] == pytest.approx(r.iloc[-300:].std(ddof=1))
