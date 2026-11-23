"""Pre-run full analyses so a live demo loads from the response cache (Phase 7).

    uv run python -m pusula.demo.warmup            # THYAO, AKBNK, ENJSA, TUPRS on the latest date
    uv run python -m pusula.demo.warmup --yes      # without the confirmation prompt

Every agent call is stored in the LLM response cache (``data/llm_cache.sqlite``) and every run in
DuckDB (``analysis_runs``). On the "Ajan Kararı" page the same stock and date then returns at once
(cached calls need no request). Already cached calls are skipped here too, so the command is cheap
to repeat.
"""

from __future__ import annotations

import argparse
import time
from datetime import date

from pusula.config import get_settings
from pusula.data.store import Store
from pusula.logging_setup import setup_logging

DEMO_TICKERS = ["THYAO", "AKBNK", "ENJSA", "TUPRS"]
CALLS_PER_FULL_RUN = 6  # risk, scenario, bull, bear, judge, auditor (without regenerations)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--tickers", nargs="+", default=DEMO_TICKERS)
    ap.add_argument("--as-of", type=date.fromisoformat, default=None)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args(argv)
    setup_logging("WARNING")
    s = get_settings()
    store = Store(s.paths.db_path, s.paths.raw_dir)
    as_of = a.as_of or store.prices()["date"].max().date()
    n = len(a.tickers) * CALLS_PER_FULL_RUN
    print(
        f"Warm-up: {len(a.tickers)} full analyses on {as_of} (≈{n} LLM calls, cached ones are "
        f"skipped; ≈4–9 min per uncached analysis on the free tier, cost 0)."
    )
    if not a.yes and input("Continue? [y/N] ").strip().lower() != "y":
        raise SystemExit("aborted")
    from pusula.pipeline import run_analysis

    for tk in a.tickers:
        t0 = time.perf_counter()
        try:
            run = run_analysis(tk, as_of, mode="full", store=store)
        except Exception as exc:  # keep going with the other tickers
            print(f"{tk}: failed ({exc})")
            continue
        live = run.totals.get("live_calls", 0)
        print(
            f"{tk}: {run.decision.karar} (güven {run.decision.guven:.2f}), audit "
            f"{'OK' if run.audit.passed else 'FAILED'}, {live} live calls, "
            f"{time.perf_counter() - t0:.0f}s"
        )


if __name__ == "__main__":
    main()
