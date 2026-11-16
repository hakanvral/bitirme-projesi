"""Check that every configured ticker / Yahoo symbol downloads, and print Yahoo's company name.

    uv run python -m pusula.universe.validate            # last 30 days for every symbol
    uv run python -m pusula.universe.validate --names    # also fetch company names (slower)

Writes ``results/universe_validation/<timestamp>/validation.csv``.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta

import pandas as pd

from pusula.config import get_settings
from pusula.data.adapters import yfinance_adapter
from pusula.data.sources import get_data_sources
from pusula.logging_setup import setup_logging
from pusula.universe.load import load_bist30, load_energy_candidates, to_yahoo

MIN_ROWS_30D = 10  # ~20 trading days in 30 calendar days; fewer = no usable history


def collect_symbols() -> pd.DataFrame:
    rows = []
    for which in ("reference", "selection"):
        rows += [{"symbol": to_yahoo(t), "group": f"bist30_{which}"} for t in load_bist30(which)]
    cand = load_energy_candidates()
    rows += [{"symbol": to_yahoo(t), "group": "energy_candidate"} for t in cand["ticker"]]
    src = get_data_sources()
    rows += [{"symbol": s.code, "group": "index"} for s in src.indices if s.code]
    rows += [
        {"symbol": s.code, "group": f"macro:{s.id}"}
        for s in src.macro
        if s.source == "yfinance" and s.code
    ]
    df = pd.DataFrame(rows)
    return df.groupby("symbol", as_index=False)["group"].agg(", ".join)


def validate(symbols: pd.DataFrame, names: bool = False, downloader=None) -> pd.DataFrame:
    end = date.today()
    px = yfinance_adapter.fetch(
        symbols["symbol"].tolist(), end - timedelta(days=30), end, downloader=downloader
    )
    stats = px.groupby("ticker").agg(rows=("date", "size"), last_date=("date", "max"))
    out = symbols.merge(stats, left_on="symbol", right_index=True, how="left")
    out["rows"] = out["rows"].fillna(0).astype(int)
    out["ok"] = out["rows"] >= MIN_ROWS_30D
    if names:
        out["yahoo_name"] = [yfinance_adapter.fetch_long_name(s) for s in out["symbol"]]
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--names", action="store_true")
    args = p.parse_args(argv)
    setup_logging()
    res = validate(collect_symbols(), names=args.names)
    out = (
        get_settings().paths.results_dir
        / "universe_validation"
        / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "validation.csv", index=False)
    print(res.to_string(index=False))
    bad = res[~res["ok"]]
    print(f"\n{len(res) - len(bad)}/{len(res)} symbols OK. Saved to {out}")
    if not bad.empty:
        print("PROBLEMS:", ", ".join(bad["symbol"]))


if __name__ == "__main__":
    main()
