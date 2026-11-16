import numpy as np
import pandas as pd

from pusula.data.jump_review import classify, to_proposals
from tests.helpers import price_long

D = pd.bdate_range("2024-02-01", periods=30)  # XIST sessions in Feb/Mar 2024 are weekdays


def _prices() -> pd.DataFrame:
    xu = price_long("XU100.IS", D, np.linspace(100, 101, 30))
    flat = [price_long(f"F{i}.IS", D, 10.0 + np.arange(30) * 0.001) for i in range(8)]
    split = price_long("SPL.IS", D, np.r_[np.full(15, 10.0), np.full(15, 17.0)])  # +70% raw
    div = price_long("DIV.IS", D, 10.0)
    div.loc[20:, "close"] = 9.3  # raw -7% on an ex-dividend day ...
    div.loc[20:, "adj_close"] = 11.3  # ... but the vendor's adjusted price rises 13%
    return pd.concat([xu, *flat, split, div], ignore_index=True)


def test_classify_split_and_dividend_errors():
    df = classify(_prices()).set_index("ticker")
    assert df.loc["SPL.IS", "cls"] == "split_or_bonus_misadjustment"
    assert df.loc["DIV.IS", "cls"] == "vendor_dividend_adjustment"
    props = {p["ticker"]: p for p in to_proposals(df.reset_index())}
    assert props["SPL"]["status"] == "proposed" and props["SPL"]["type"] == "factor"
    # applying the factor to the pre-date history leaves ~ the market return on that day
    assert abs(props["SPL"]["ratio"] - 1.7 / (1 + df.loc["SPL.IS", "market_return"])) < 1e-6
