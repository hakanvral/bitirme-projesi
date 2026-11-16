"""Universe loading (BIST30 lists, energy candidates / selection)."""

from __future__ import annotations

import logging
from typing import Literal

import pandas as pd

from pusula.config import CONFIG_DIR, load_yaml
from pusula.data.sources import get_data_sources

log = logging.getLogger(__name__)

Which = Literal["reference", "selection"]
SUB_SECTORS = ("electricity", "natural_gas", "refining_petroleum")


def to_yahoo(ticker: str) -> str:
    return ticker if ticker.endswith(".IS") else ticker + get_data_sources().price_tickers_suffix


def load_bist30(which: Which = "reference") -> list[str]:
    lst = load_yaml("universe.yaml")["bist30"][which]
    tickers = [str(t).strip().upper() for t in (lst.get("tickers") or [])]
    if not tickers:
        log.warning(
            "BIST30 %s list is empty: paste the official list into config/universe.yaml", which
        )
    elif len(tickers) != 30:
        log.warning("BIST30 %s list has %d tickers (expected 30)", which, len(tickers))
    return tickers


def load_energy_candidates() -> pd.DataFrame:
    df = pd.DataFrame(load_yaml("energy_candidates.yaml")["candidates"])
    bad = set(df["sub_sector"]) - set(SUB_SECTORS)
    if bad:
        raise ValueError(f"Unknown sub_sector(s) in energy_candidates.yaml: {bad}")
    if df["ticker"].duplicated().any():
        raise ValueError("Duplicate tickers in energy_candidates.yaml")
    n_unverified = int((~df["verified"]).sum())
    if n_unverified:
        log.warning("%d energy candidates are not verified yet (verified: false)", n_unverified)
    return df


def load_energy_selected() -> pd.DataFrame | None:
    path = CONFIG_DIR / "energy_selected.yaml"
    if not path.exists():
        return None
    return pd.DataFrame(load_yaml("energy_selected.yaml")["selected"])


def all_stock_tickers() -> list[str]:
    """Every stock we need prices for: both BIST30 lists + all energy candidates (plain codes)."""
    s = set(load_bist30("reference")) | set(load_bist30("selection"))
    s |= set(load_energy_candidates()["ticker"])
    return sorted(s)
