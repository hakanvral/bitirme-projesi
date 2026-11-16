"""End-to-end update with fake downloader + manual files (no network)."""

from datetime import date

import httpx
import pandas as pd

from pusula.data.adapters.evds_adapter import EvdsClient
from pusula.data.store import Store
from pusula.data.update import run_update
from tests.helpers import yf_wide


def fake_yf(**kw):
    syms = kw["tickers"]
    dates = pd.bdate_range(kw["start"], pd.Timestamp(kw["end"]) - pd.Timedelta(days=1))
    syms = [s for s in syms if s != "XELKT.IS"]  # simulate a symbol Yahoo does not have
    return yf_wide(syms, dates)


def no_network_evds():
    def handler(request):
        raise AssertionError("EVDS must not be called while codes are TODO_VERIFY")

    return EvdsClient(
        "https://example.test/", None, client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_run_update_end_to_end(tmp_path):
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "cds_tr_5y.csv").write_text("date,value\n2018-01-02,170\n2018-01-03,171\n")
    (manual / "ppk_decisions.csv").write_text(
        "meeting_date,previous_rate,new_rate,change_bp\n2018-01-18,8,8,0\n"
    )
    (manual / "index_XELKT.csv").write_text(
        "date,open,high,low,close,volume\n2018-01-02,1,1,1,1,1\n"
    )
    (manual / "policy_rate.csv").write_text("date,value\n2018-01-01,8\n2018-06-08,17.75\n")
    store = Store(tmp_path / "db.duckdb", tmp_path / "raw")

    log = run_update(
        store=store,
        yf_downloader=fake_yf,
        evds=no_network_evds(),
        today=date(2018, 2, 28),
        manual_dir=manual,
        results_dir=tmp_path / "res",
    )
    st = log.set_index("series")
    assert st.loc["XU100.IS", "status"] == "ok"
    assert st.loc["XELKT.IS", "source"] == "manual"
    assert st.loc["cds_5y", "status"] == "ok"
    assert st.loc["policy_rate", "source"] == "manual"
    assert st.loc["tlref", "status"] == "missing"  # TODO_VERIFY and no manual file
    assert st.loc["ppk_decisions", "status"] == "ok"
    assert (manual / "ppk_detected_changes.csv").exists()
    rep = store.query("SELECT * FROM quality_report")
    assert not rep.empty and "XU100.IS" in set(rep["series"])
    assert list((tmp_path / "res" / "data_quality").iterdir())

    # Incremental: second run re-downloads only the overlap window, no duplicates.
    n_before = len(store.prices(["XU100.IS"]))
    run_update(
        store=store,
        yf_downloader=fake_yf,
        evds=no_network_evds(),
        today=date(2018, 2, 28),
        manual_dir=manual,
        results_dir=tmp_path / "res",
    )
    assert len(store.prices(["XU100.IS"])) == n_before
