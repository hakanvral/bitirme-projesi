import json

import httpx
import numpy as np
import pandas as pd
import pytest

from pusula.data.adapters import manual_csv, yfinance_adapter
from pusula.data.adapters.evds_adapter import EvdsClient, EvdsError, parse_series
from tests.helpers import bdays, yf_wide


# ----------------------------------------------------------------------------- EVDS
def test_evds_parse_daily(fixtures_dir):
    payload = json.loads((fixtures_dir / "evds_series_daily.json").read_text())
    df = parse_series(payload, "TEST.SERIES.A")
    assert list(df["value"]) == [10.5, 10.75, 11.0]  # null dropped
    assert df["date"].iloc[0] == pd.Timestamp("2018-01-02")


def test_evds_parse_monthly(fixtures_dir):
    payload = json.loads((fixtures_dir / "evds_series_monthly.json").read_text())
    df = parse_series(payload, "TEST.SERIES.M")
    assert list(df["date"]) == [
        pd.Timestamp("2018-01-01"),
        pd.Timestamp("2018-02-01"),
        pd.Timestamp("2018-12-01"),
    ]


def test_evds_missing_column_raises():
    with pytest.raises(EvdsError):
        parse_series({"items": [{"Tarih": "01-01-2018", "OTHER": "1"}]}, "TEST.X")


def test_evds_client_request_format_and_key_header(fixtures_dir):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("key")
        return httpx.Response(200, content=(fixtures_dir / "evds_series_daily.json").read_bytes())

    client = EvdsClient(
        "https://example.test/api/",
        "secret-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    df = client.series(
        "TEST.SERIES.A", pd.Timestamp("2018-01-01").date(), pd.Timestamp("2018-01-31").date()
    )
    assert len(df) == 3
    assert seen["key"] == "secret-key"
    assert "series=TEST.SERIES.A&startDate=01-01-2018&endDate=31-01-2018&type=json" in seen["url"]


def test_evds_client_no_key_sends_no_header_and_errors_cleanly():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "key" not in request.headers
        return httpx.Response(403, json={"status": "403", "message": "no key"})

    client = EvdsClient(
        "https://example.test/api/",
        None,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(EvdsError, match="403"):
        client.categories()


# ----------------------------------------------------------------------------- yfinance
@pytest.mark.parametrize("field_first", [False, True])
def test_yfinance_to_long_both_column_orders(field_first):
    dates = bdays("2024-01-01", 5)
    raw = yf_wide(["AAA.IS", "BBB.IS"], dates, field_first=field_first)
    df = yfinance_adapter.to_long(raw, ["AAA.IS", "BBB.IS", "MISSING.IS"])
    assert set(df["ticker"]) == {"AAA.IS", "BBB.IS"}
    assert len(df) == 10
    a = df[df["ticker"] == "AAA.IS"].iloc[0]
    assert a["close"] == 10.5 and a["adj_close"] == 10.0 and a["volume"] == 1000.0


def test_yfinance_fetch_uses_inclusive_end_and_unadjusted():
    calls = {}

    def fake(**kw):
        calls.update(kw)
        return yf_wide(["AAA.IS"], bdays("2024-01-01", 3))

    yfinance_adapter.fetch(
        ["AAA.IS"],
        pd.Timestamp("2024-01-01").date(),
        pd.Timestamp("2024-01-03").date(),
        downloader=fake,
    )
    assert calls["end"] == "2024-01-04"
    assert calls["auto_adjust"] is False


def test_yfinance_empty():
    assert yfinance_adapter.to_long(pd.DataFrame(), ["A"]).empty


# ----------------------------------------------------------------------------- manual CSV
def test_manual_macro_ok(tmp_path):
    p = tmp_path / "cds.csv"
    p.write_text("date,value\n2024-01-02,300.5\n2024-01-03,301\n")
    df = manual_csv.read_macro(p, "cds_5y")
    assert list(df["value"]) == [300.5, 301.0] and (df["series"] == "cds_5y").all()


@pytest.mark.parametrize(
    "content,match",
    [
        ("day,value\n2024-01-02,1\n", "missing columns"),
        ("date,value\n02.01.2024,1\n", "YYYY-MM-DD"),
        ('date,value\n2024-01-02,"1,5"\n', "non-numeric"),
    ],
)
def test_manual_macro_schema_errors(tmp_path, content, match):
    p = tmp_path / "x.csv"
    p.write_text(content)
    with pytest.raises(manual_csv.ManualFileError, match=match):
        manual_csv.read_macro(p, "x")


def test_manual_ptf_hourly_averaged(tmp_path):
    p = tmp_path / "ptf.csv"
    p.write_text("date,hour,ptf_try_mwh\n2024-01-02,0,100\n2024-01-02,1,200\n2024-01-03,0,50\n")
    df = manual_csv.read_ptf(p)
    assert list(df["value"]) == [150.0, 50.0]


def test_manual_ppk_checks_change_bp(tmp_path):
    p = tmp_path / "ppk.csv"
    p.write_text("meeting_date,previous_rate,new_rate,change_bp\n2024-01-25,42.5,45,250\n")
    assert manual_csv.read_ppk(p)["change_bp"].iloc[0] == 250
    p.write_text("meeting_date,previous_rate,new_rate,change_bp\n2024-01-25,42.5,45,200\n")
    with pytest.raises(manual_csv.ManualFileError, match="change_bp"):
        manual_csv.read_ppk(p)


def test_manual_release_dates_before_period_rejected(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("period,release_date\n2024-05,2024-04-30\n")
    with pytest.raises(manual_csv.ManualFileError):
        manual_csv.read_release_dates(p)


def test_manual_ohlcv_adj_defaults_to_close(tmp_path):
    p = tmp_path / "i.csv"
    p.write_text("date,open,high,low,close,volume\n2024-01-02,1,2,0.5,1.5,10\n")
    df = manual_csv.read_ohlcv(p, "XU030.IS")
    assert np.isclose(df["adj_close"].iloc[0], 1.5)
