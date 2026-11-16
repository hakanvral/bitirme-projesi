import numpy as np
import pandas as pd

from pusula.data.ppk import compare_with_manual, detect_rate_changes
from pusula.data.quality import build_report, jump_flags
from tests.helpers import bdays, price_long

CAL = bdays("2024-01-01", 20)


def test_jump_flag_and_report():
    close = np.full(20, 10.0)
    close[10:] = 20.0  # +100% one-day move (e.g. unadjusted bonus issue)
    close += np.arange(20) * 0.01  # avoid stale flags
    prices = pd.concat(
        [
            price_long("XU100.IS", CAL, np.arange(20.0) + 1000),
            price_long("AAA.IS", CAL.delete([3, 4]), np.delete(close, [3, 4])),
            price_long("STALE.IS", CAL, 5.0),
        ]
    ).assign(source="test", updated_at=pd.Timestamp("2024-02-01"))
    flags = jump_flags(prices)
    assert list(flags["ticker"]) == ["AAA.IS"]

    macro = pd.DataFrame(
        {
            "date": CAL,
            "series": "vix",
            "value": 15.0,
            "source": "yfinance",
            "updated_at": pd.Timestamp("2024-02-01"),
        }
    )
    rep = build_report(
        prices,
        macro,
        CAL,
        ["AAA.IS", "STALE.IS", "NONE.IS"],
        {"vix": ("yfinance", "D"), "cds_5y": ("manual", "D")},
        stale_days=5,
    )
    r = rep.set_index("series")
    assert r.loc["AAA.IS", "missing_days"] == 2 and r.loc["AAA.IS", "jumps"] == 1
    assert r.loc["AAA.IS", "coverage_pct"] == 90.0 and r.loc["AAA.IS", "status"] == "warn"
    assert r.loc["STALE.IS", "stale_days"] == 20 and r.loc["STALE.IS", "status"] == "warn"
    assert r.loc["NONE.IS", "status"] == "missing"
    assert r.loc["vix", "status"] == "ok"
    assert r.loc["cds_5y", "status"] == "missing"


def test_ppk_detection_on_toy_series():
    dates = pd.bdate_range("2024-01-01", periods=10)
    vals = [42.5, 42.5, 45.0, 45.0, 45.0, 45.0, 50.0, 50.0, 47.5, 47.5]
    det = detect_rate_changes(pd.DataFrame({"date": dates, "value": vals}))
    assert list(det["change_bp"]) == [250.0, 500.0, -250.0]
    assert list(det["effective_date"]) == [dates[2], dates[6], dates[8]]

    manual = pd.DataFrame({"meeting_date": [dates[1], dates[5]], "change_bp": [250.0, 400.0]})
    cmp = compare_with_manual(det, manual, max_lag_days=2)
    assert list(cmp["problem"]) == ["", "change_bp differs", "no PPK meeting in manual file"]
