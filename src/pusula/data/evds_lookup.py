"""Search EVDS metadata to verify series codes (never guess them).

    uv run python -m pusula.data.evds_lookup "policy rate" "exchange rate" "consumer price"

Prints matching data groups and their series codes. Copy the verified code into
``config/data_sources.yaml`` and note the lookup in ``docs/data_sources.md``.
"""

from __future__ import annotations

import argparse

import pandas as pd

from pusula.config import get_secrets
from pusula.data.adapters.evds_adapter import EvdsClient, search_series
from pusula.data.sources import get_data_sources
from pusula.logging_setup import setup_logging


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("patterns", nargs="+", help="case-insensitive text to search in group names")
    args = p.parse_args(argv)
    setup_logging()
    key = get_secrets().evds_api_key
    client = EvdsClient(get_data_sources().evds.base_url, key.get_secret_value() if key else None)
    res = search_series(client, *args.patterns)
    with pd.option_context("display.max_rows", 500, "display.width", 200):
        print(res.to_string(index=False) if not res.empty else "No match.")


if __name__ == "__main__":
    main()
