from datetime import date

import numpy as np
import pandas as pd

from pusula.universe.select_energy import select_energy
from tests.helpers import price_long

SEL = date(2024, 12, 31)
CAL = pd.bdate_range("2020-01-01", "2025-06-30")


def _universe() -> tuple[pd.DataFrame, pd.DataFrame]:
    cands = pd.DataFrame(
        [
            # ticker, sub_sector, volume (liquidity rank driver)
            ("REF1", "refining_petroleum", 50),
            ("REF2", "refining_petroleum", 10),
            ("GAS1", "natural_gas", 40),
            ("GAS2", "natural_gas", 5),
            ("GASNEW", "natural_gas", 1000),  # too short history
            ("ELGAP", "electricity", 900),  # long trading halt
            *[(f"EL{i}", "electricity", 100 + i) for i in range(8)],
        ],
        columns=["ticker", "sub_sector", "vol"],
    )
    cands["name"] = cands["ticker"]
    cands["verified"] = True
    frames = [price_long("XU100.IS", CAL)]
    for r in cands.itertuples():
        dates = CAL
        if r.ticker == "GASNEW":
            dates = CAL[CAL >= "2023-06-01"]
        if r.ticker == "ELGAP":
            dates = CAL[(CAL < "2023-01-01") | (CAL > "2023-03-01")]
        frames.append(price_long(f"{r.ticker}.IS", dates, close=10.0, volume=float(r.vol)))
    return pd.concat(frames, ignore_index=True), cands.drop(columns="vol")


def test_selection_rules_and_quotas():
    prices, cands = _universe()
    res = select_energy(prices, cands, SEL, bist30=["EL7"], n=10, calendar_method="observed")
    sel = res.selected.set_index("ticker")
    assert len(sel) == 10
    assert (sel["sub_sector"] == "refining_petroleum").sum() >= 2
    assert (sel["sub_sector"] == "natural_gas").sum() >= 2
    s = res.scores.set_index("ticker")
    assert not s.loc["GASNEW", "eligible"] and "history" in s.loc["GASNEW", "reason"]
    assert not s.loc["ELGAP", "eligible"] and "gap" in s.loc["ELGAP", "reason"]
    assert sel.loc["EL7", "in_bist30"]
    # liquid electricity names beat illiquid ones; quotas force REF2 / GAS2 in
    assert {"REF2", "GAS2"} <= set(sel.index)


def test_selection_is_point_in_time():
    prices, cands = _universe()
    base = select_energy(prices, cands, SEL, bist30=[], calendar_method="observed")
    corrupted = prices.copy()
    after = pd.to_datetime(corrupted["date"]) > pd.Timestamp(SEL)
    corrupted.loc[after, ["close", "volume"]] = 1e15
    other = select_energy(corrupted, cands, SEL, bist30=[], calendar_method="observed")
    pd.testing.assert_frame_equal(base.scores, other.scores)


def test_unmet_quota_reported():
    prices, cands = _universe()
    cands = cands[cands["ticker"] != "REF2"]
    res = select_energy(prices, cands, SEL, bist30=[], calendar_method="observed")
    assert any("Quota not met: refining_petroleum" in n for n in res.notes)
    assert np.isfinite(res.scores["composite_score"].dropna()).all()
