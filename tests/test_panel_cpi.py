from datetime import date

import numpy as np
import pandas as pd
import pytest

from pusula.data.cpi import cpi_as_of, deflate_historical
from pusula.data.panel import align_series, build_panel, to_weekly, trading_calendar
from pusula.data.sources import SeriesSpec
from tests.helpers import bdays, price_long

CAL = bdays("2024-01-01", 30)  # 2024-01-01 .. 2024-02-09


def test_calendar_from_xu100():
    prices = pd.concat([price_long("XU100.IS", CAL[:-1]), price_long("AAA.IS", CAL)])
    cal = trading_calendar(prices, method="observed")
    assert len(cal) == 29  # extra AAA day does not create a trading day


def test_step_fill_carries_forever():
    obs = pd.DataFrame({"date": [CAL[0]], "value": [45.0]})
    s = align_series(obs, CAL, "step")
    assert s.notna().all() and (s == 45).all()


def test_market_fill_is_limited():
    obs = pd.DataFrame({"date": [CAL[0]], "value": [1.0]})
    s = align_series(obs, CAL, "market", max_ffill=3)
    assert s.iloc[:4].notna().all() and s.iloc[4:].isna().all()


def test_release_fill_waits_for_release_date():
    obs = pd.DataFrame(
        {
            "date": [pd.Timestamp("2023-12-01")],
            "value": [100.0],
            "release_date": [pd.Timestamp("2024-01-03")],
        }
    )
    s = align_series(obs, CAL, "release")
    assert s.loc[:"2024-01-02"].isna().all()
    assert (s.loc["2024-01-03":] == 100).all()


def test_build_panel_as_of_and_weekly():
    prices = pd.concat(
        [
            price_long("XU100.IS", CAL, np.arange(30.0)),
            price_long("AAA.IS", CAL, np.arange(30.0) + 100),
        ]
    )
    macro = pd.DataFrame(
        {"date": [CAL[0]], "series": "policy_rate", "value": [50.0], "release_date": pd.NaT}
    )
    specs = [SeriesSpec(id="policy_rate", source="evds", fill="step")]
    p = build_panel(
        prices, macro, specs, ["AAA.IS"], calendar_method="observed", as_of=CAL[9].date()
    )
    assert p.index.max() == CAL[9] and p["policy_rate"].eq(50).all()
    w = to_weekly(build_panel(prices, macro, specs, ["AAA.IS"], calendar_method="observed"))
    assert (w.index.day_of_week == 4).all()
    assert w["AAA.IS"].iloc[0] == 104.0  # Friday 2024-01-05 is the 5th trading day


# --------------------------------------------------------------------------- CPI (D-003)
def _cpi() -> pd.DataFrame:
    months = pd.date_range("2023-01-01", periods=12, freq="MS")
    level = 100 * np.exp(0.03 * np.arange(12))  # 3% log inflation per month, known truth
    release = months + pd.offsets.MonthBegin(1) + pd.Timedelta(days=2)  # 3rd of next month
    return pd.DataFrame({"date": months, "value": level, "release_date": release})


def test_deflate_historical_hits_mid_month_anchors():
    cpi = _cpi()
    s = deflate_historical(cpi, pd.DatetimeIndex(["2023-03-15", "2023-07-15"]))
    np.testing.assert_allclose(s.values, cpi["value"].iloc[[2, 6]].values)


def test_cpi_as_of_extrapolates_with_last_known_inflation():
    cpi = _cpi()
    # On 2023-06-10 the May print (released 2023-06-03) is the latest known.
    d = pd.DatetimeIndex(["2023-06-10"])
    s = cpi_as_of(cpi, d, date(2023, 6, 10))
    may = cpi["value"].iloc[4]
    days = (pd.Timestamp("2023-06-10") - pd.Timestamp("2023-05-15")).days
    daily = 0.03 / (pd.Timestamp("2023-05-15") - pd.Timestamp("2023-04-15")).days
    np.testing.assert_allclose(s.iloc[0], may * np.exp(daily * days), rtol=1e-12)


def test_cpi_as_of_rejects_future_dates():
    with pytest.raises(ValueError, match="look-ahead"):
        cpi_as_of(_cpi(), pd.DatetimeIndex(["2023-07-01"]), date(2023, 6, 30))


def test_no_look_ahead_cpi_and_panel():
    """Corrupt everything after t: outputs as of t must not change (CLAUDE.md §9)."""
    t = date(2023, 6, 10)
    cpi = _cpi()
    dates = pd.bdate_range("2023-01-02", "2023-06-09")
    base = cpi_as_of(cpi, dates, t)
    bad = cpi.copy()
    after = bad["release_date"] > pd.Timestamp(t)
    bad.loc[after, "value"] = 1e12  # huge garbage in unreleased prints
    pd.testing.assert_series_equal(base, cpi_as_of(bad, dates, t))

    cal = pd.bdate_range("2023-01-02", "2023-08-31")
    prices = pd.concat(
        [
            price_long("XU100.IS", cal, np.linspace(1, 2, len(cal))),
            price_long("AAA.IS", cal, np.linspace(5, 6, len(cal))),
        ]
    )
    macro = pd.concat(
        [
            cpi.assign(series="cpi"),
            pd.DataFrame(
                {
                    "date": cal,
                    "series": "usdtry",
                    "value": np.linspace(18, 27, len(cal)),
                    "release_date": pd.NaT,
                }
            ),
        ]
    )
    specs = [
        SeriesSpec(id="cpi", source="evds", freq="M", fill="release"),
        SeriesSpec(id="usdtry", source="evds", fill="market"),
    ]
    p1 = build_panel(prices, macro, specs, ["AAA.IS"], calendar_method="observed", as_of=t)

    prices2 = prices.copy()
    prices2.loc[prices2["date"] > pd.Timestamp(t), ["close", "adj_close"]] = np.nan
    macro2 = macro.copy()
    macro2.loc[macro2["date"] > pd.Timestamp(t), "value"] = 1e12
    macro2.loc[
        (macro2["series"] == "cpi") & (macro2["release_date"] > pd.Timestamp(t)), "value"
    ] = 1e12
    p2 = build_panel(prices2, macro2, specs, ["AAA.IS"], calendar_method="observed", as_of=t)
    pd.testing.assert_frame_equal(p1, p2)


def test_xist_calendar_includes_dec25_and_excludes_new_year():
    prices = price_long("XU100.IS", pd.bdate_range("2024-12-20", "2025-01-03"))
    cal = trading_calendar(prices)  # default: official XIST sessions
    assert pd.Timestamp("2024-12-25") in cal
    assert pd.Timestamp("2025-01-01") not in cal
