from datetime import date

import numpy as np
import pandas as pd
import pytest

from pusula.data.cleaning import (
    CorporateAction,
    CorporateActions,
    apply_actions,
    apply_generic_rules,
)
from pusula.data.update import rule_release_dates
from tests.helpers import bdays, price_long


def test_bonus_issue_makes_series_continuous_and_keeps_raw():
    d = bdays("2024-01-01", 6)
    close = np.array([100, 100, 100, 50, 50, 50.0])  # 100% bonus issue on day 4
    raw = price_long("AAA.IS", d, close)
    cfg = CorporateActions(
        actions=[
            CorporateAction(
                ticker="AAA", date=d[3].date(), type="bonus_issue", ratio=1.0, status="confirmed"
            )
        ]
    )
    out = apply_actions(raw, cfg)
    assert np.allclose(out["adj_close"], 50.0)
    assert raw["adj_close"].iloc[0] == 100.0  # input untouched


def test_proposed_actions_are_not_applied_by_default():
    d = bdays("2024-01-01", 3)
    raw = price_long("AAA.IS", d, 10.0)
    cfg = CorporateActions(
        actions=[CorporateAction(ticker="AAA", date=d[2].date(), type="factor", ratio=2.0)]
    )
    assert np.allclose(apply_actions(raw, cfg)["adj_close"], 10.0)


def test_rights_issue_terp_factor():
    a = CorporateAction(
        ticker="X",
        date=date(2024, 1, 1),
        type="rights_issue",
        ratio=1.0,
        subscription_price=1.0,
        status="confirmed",
    )
    assert a.price_factor(cum_price=3.0) == pytest.approx(2.0 / 3.0)  # TERP = (3+1)/2


def test_generic_rules_drop_non_sessions_and_stale_rows():
    d = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-06"])
    p = price_long("AAA.IS", d, np.array([10, 11, 11, 12.0]))
    p.loc[2, "volume"] = 0.0  # stale copy of the previous close
    sessions = pd.DatetimeIndex([*d[:3], pd.Timestamp("2024-01-08")])
    out = apply_generic_rules(p, sessions)
    assert pd.Timestamp("2024-01-06") not in set(out["date"])  # Saturday inside the range
    assert np.isnan(out.loc[out["date"] == "2024-01-04", "close"]).all()


def test_rule_release_dates_are_sessions_after_target():
    periods = pd.Series(pd.to_datetime(["2024-01-01", "2024-05-01"]))
    rel = rule_release_dates(periods, "next_month_day:6")
    assert rel.iloc[0] == pd.Timestamp("2024-02-06")  # Tuesday, a session
    assert rel.iloc[1] >= pd.Timestamp("2024-06-06")
    assert (rel.dt.day_of_week < 5).all()
