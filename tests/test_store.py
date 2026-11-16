from datetime import date

import pandas as pd

from pusula.data.store import Store
from tests.helpers import bdays, price_long


def test_upsert_is_idempotent_and_updates(tmp_path):
    st = Store(tmp_path / "t.duckdb")
    df = price_long("AAA.IS", bdays("2024-01-01", 5), close=10.0)
    st.upsert_prices(df, "test")
    st.upsert_prices(df, "test")
    assert len(st.prices()) == 5
    df2 = df.copy()
    df2["close"] = 11.0
    st.upsert_prices(df2.tail(1), "test")
    p = st.prices()
    assert len(p) == 5 and p["close"].iloc[-1] == 11.0
    assert st.last_date("prices", "ticker", "AAA.IS") == date(2024, 1, 5)
    assert st.last_date("prices", "ticker", "NOPE.IS") is None


def test_macro_with_release_dates_roundtrip(tmp_path):
    st = Store(tmp_path / "t.duckdb")
    m = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
            "series": "cpi",
            "value": [100.0, 103.0],
            "release_date": pd.to_datetime(["2024-02-05", "2024-03-04"]),
        }
    )
    st.upsert_macro(m, "test")
    out = st.macro(["cpi"])
    assert list(out["release_date"]) == list(m["release_date"])


def test_events_and_raw_snapshot(tmp_path):
    st = Store(tmp_path / "t.duckdb", tmp_path / "raw")
    ev = pd.DataFrame({"meeting_date": pd.to_datetime(["2024-01-25"]), "change_bp": [250.0]})
    assert st.upsert_events(ev, "ppk", "meeting_date", "manual") == 1
    path = st.save_raw("src", ev, day=date(2024, 1, 26))
    st.save_raw("src", ev, day=date(2024, 1, 26))
    assert path.name == "20240126.parquet" and len(pd.read_parquet(path)) == 2
