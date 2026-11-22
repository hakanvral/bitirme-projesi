"""The analysis universe on a given date: BIST30 + selected Energy names, with labels."""

from __future__ import annotations

from datetime import date

import pandas as pd

from pusula.config import get_settings
from pusula.universe.load import load_bist30, load_energy_selected, to_yahoo


def universe_members(as_of: date) -> pd.DataFrame:
    """Columns: ticker (plain), symbol (.IS), universe (BIST30 | Energy), sub_sector, in_bist30.

    BIST30 list: the ``reference`` list for dates on/after REFERENCE_DATE, otherwise the
    ``selection`` list (D-002). Names in both groups appear once per group (overlap flagged).
    """
    s = get_settings().project
    which = "reference" if as_of >= s.reference_date else "selection"
    b30 = load_bist30(which)
    rows = [{"ticker": t, "universe": "BIST30", "sub_sector": None, "in_bist30": True}
            for t in b30]  # fmt: skip
    energy = load_energy_selected()
    if energy is not None:
        for e in energy.itertuples():
            rows.append({"ticker": e.ticker, "universe": "Energy", "sub_sector": e.sub_sector,
                         "in_bist30": e.ticker in b30})  # fmt: skip
    df = pd.DataFrame(rows)
    df["symbol"] = df["ticker"].map(to_yahoo)
    return df
