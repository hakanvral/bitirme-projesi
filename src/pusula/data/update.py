"""One command to fetch / update all data (incremental).

    uv run python -m pusula.data.update            # incremental
    uv run python -m pusula.data.update --full     # re-download everything from data_start
    uv run python -m pusula.data.update --only prices

Rules (D-014): every source is tried independently; a failure is logged to ``update_log`` and
the run continues. If an API is unavailable or an EVDS code is not verified yet, the series'
manual CSV (``data/manual/...``) is used when present.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from pusula.config import get_secrets, get_settings
from pusula.data import quality
from pusula.data.adapters import manual_csv, yfinance_adapter
from pusula.data.adapters.evds_adapter import EvdsClient, EvdsError
from pusula.data.panel import trading_calendar
from pusula.data.ppk import compare_with_manual, detect_rate_changes
from pusula.data.sources import DataSources, SeriesSpec, get_data_sources
from pusula.data.store import Store
from pusula.logging_setup import setup_logging
from pusula.universe.load import all_stock_tickers, to_yahoo

log = logging.getLogger(__name__)

OVERLAP_DAYS = 10  # re-download the last N days to pick up revisions
YF_CHUNK = 20  # symbols per yfinance request


@dataclass
class Context:
    store: Store
    sources: DataSources
    manual_dir: Path
    data_start: date
    today: date
    full: bool
    run_at: datetime
    yf_downloader: Callable | None = None
    evds: EvdsClient | None = None

    def log(self, series: str, source: str, status: str, rows: int, msg: str = "") -> None:
        level = logging.INFO if status == "ok" else logging.WARNING
        log.log(level, "%-14s %-9s %-8s rows=%d %s", series, source, status, rows, msg)
        self.store.log_update(self.run_at, series, source, status, rows, msg)


def _start_for(ctx: Context, table: str, key_col: str, key: str) -> date:
    if ctx.full:
        return ctx.data_start
    last = ctx.store.last_date(table, key_col, key)
    return ctx.data_start if last is None else max(ctx.data_start, last - timedelta(OVERLAP_DAYS))


# --------------------------------------------------------------------------- prices
def update_prices(ctx: Context) -> None:
    stocks = [to_yahoo(t) for t in all_stock_tickers()]
    index_specs = {s.code: s for s in ctx.sources.indices if s.code}
    symbols = stocks + list(index_specs)
    by_start: dict[date, list[str]] = {}
    for sym in symbols:
        by_start.setdefault(_start_for(ctx, "prices", "ticker", sym), []).append(sym)

    got: set[str] = set()
    for start, syms in sorted(by_start.items()):
        for i in range(0, len(syms), YF_CHUNK):
            chunk = syms[i : i + YF_CHUNK]
            try:
                df = yfinance_adapter.fetch(chunk, start, ctx.today, downloader=ctx.yf_downloader)
            except Exception as exc:
                for s in chunk:
                    ctx.log(s, "yfinance", "error", 0, str(exc))
                continue
            if not df.empty:
                ctx.store.save_raw("yfinance", df)
                ctx.store.upsert_prices(df, "yfinance")
            for s, g in df.groupby("ticker"):
                got.add(str(s))
                ctx.log(str(s), "yfinance", "ok", len(g))

    # manual fallback: index_<CODE>.csv for indices, prices_<TICKER>.csv for stocks
    for sym in symbols:
        if sym in got:
            continue
        spec = index_specs.get(sym)
        fname = spec.manual if spec and spec.manual else f"prices_{sym.removesuffix('.IS')}.csv"
        path = ctx.manual_dir / fname
        if path.exists():
            try:
                df = manual_csv.read_ohlcv(path, sym)
                ctx.store.upsert_prices(df, "manual")
                ctx.log(sym, "manual", "ok", len(df), fname)
            except manual_csv.ManualFileError as exc:
                ctx.log(sym, "manual", "error", 0, str(exc))
        else:
            ctx.log(sym, "yfinance", "missing", 0, f"no data; optional fallback {fname}")


# --------------------------------------------------------------------------- macro
def _release_dates(ctx: Context, spec: SeriesSpec) -> pd.DataFrame | None:
    path = ctx.manual_dir / f"{spec.id}_release_dates.csv"
    if not path.exists():
        return None
    return manual_csv.read_release_dates(path)


def _attach_release(ctx: Context, spec: SeriesSpec, df: pd.DataFrame) -> pd.DataFrame:
    if spec.fill != "release":
        return df
    rel = _release_dates(ctx, spec)
    if rel is None:
        log.warning("%s: no %s_release_dates.csv -> not usable point-in-time", spec.id, spec.id)
        if "release_date" not in df:
            df = df.assign(release_date=pd.NaT)
        return df
    df = df.drop(columns=["release_date"], errors="ignore")
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp()
    return df.merge(rel, on="date", how="left")


def _manual_macro(ctx: Context, spec: SeriesSpec) -> pd.DataFrame | None:
    if not spec.manual:
        return None
    path = ctx.manual_dir / spec.manual
    if not path.exists():
        return None
    if spec.id == "ptf":
        return manual_csv.read_ptf(path)
    if spec.freq == "M":
        return manual_csv.read_monthly(path, spec.id)
    return manual_csv.read_macro(path, spec.id)


def update_macro(ctx: Context) -> None:
    for spec in ctx.sources.macro:
        df: pd.DataFrame | None = None
        source = spec.source
        start = _start_for(ctx, "macro", "series", spec.id)
        try:
            if spec.source == "yfinance":
                df = yfinance_adapter.fetch_macro(
                    spec.code, spec.id, start, ctx.today, downloader=ctx.yf_downloader
                )
            elif spec.source == "evds":
                if not spec.code_verified:
                    raise EvdsError("EVDS code not verified yet (TODO_VERIFY)")
                if ctx.evds is None:
                    raise EvdsError("EVDS client not configured")
                # monthly series: always reload fully (small, and revisions happen)
                s0 = ctx.data_start if spec.freq == "M" else start
                df = ctx.evds.series(spec.code, s0, ctx.today).assign(series=spec.id)
        except Exception as exc:
            log.warning("%s via %s failed: %s", spec.id, spec.source, exc)
            df = None

        if df is None or df.empty:
            try:
                df = _manual_macro(ctx, spec)
                source = "manual"
            except manual_csv.ManualFileError as exc:
                ctx.log(spec.id, "manual", "error", 0, str(exc))
                continue
        if df is None or df.empty:
            hint = f"provide data/manual/{spec.manual}" if spec.manual else ""
            ctx.log(spec.id, spec.source, "missing", 0, hint)
            continue

        df = _attach_release(ctx, spec, df)
        ctx.store.save_raw(source, df)
        n = ctx.store.upsert_macro(df, source)
        ctx.log(spec.id, source, "ok", n)


# --------------------------------------------------------------------------- events
def update_events(ctx: Context) -> None:
    path = ctx.manual_dir / "ppk_decisions.csv"
    manual = None
    if path.exists():
        try:
            manual = manual_csv.read_ppk(path)
            n = ctx.store.upsert_events(manual, "ppk", "meeting_date", "manual")
            ctx.log("ppk_decisions", "manual", "ok", n)
        except manual_csv.ManualFileError as exc:
            ctx.log("ppk_decisions", "manual", "error", 0, str(exc))
    else:
        ctx.log("ppk_decisions", "manual", "missing", 0, "provide data/manual/ppk_decisions.csv")

    rate = ctx.store.macro(["policy_rate"])
    if rate.empty:
        return
    detected = detect_rate_changes(rate)
    out = ctx.manual_dir / "ppk_detected_changes.csv"  # helper for the user, not an input
    detected.to_csv(out, index=False, date_format="%Y-%m-%d")
    log.info("Wrote %d detected policy-rate changes to %s", len(detected), out)
    if manual is not None:
        cmp = compare_with_manual(detected, manual)
        bad = cmp[cmp["problem"] != ""]
        if not bad.empty:
            log.warning("PPK file vs policy-rate series mismatches:\n%s", bad.to_string())


# --------------------------------------------------------------------------- quality
def update_quality(ctx: Context, results_dir: Path, jump: float, stale: int) -> pd.DataFrame:
    prices = ctx.store.prices()
    macro = ctx.store.macro()
    if prices.empty:
        log.warning("No prices stored: quality report skipped")
        return pd.DataFrame()
    try:
        cal = trading_calendar(prices)
    except ValueError as exc:
        log.warning("Quality report skipped: %s", exc)
        return pd.DataFrame()
    expected = [to_yahoo(t) for t in all_stock_tickers()] + [
        s.code for s in ctx.sources.indices if s.code
    ]
    rep = quality.build_report(
        prices,
        macro,
        cal,
        expected,
        {s.id: (s.source, s.freq) for s in ctx.sources.macro},
        jump_threshold=jump,
        stale_days=stale,
    )
    ctx.store.replace_quality_report(rep)
    out = results_dir / "data_quality" / ctx.run_at.strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    rep.to_csv(out / "quality_report.csv", index=False)
    quality.jump_flags(prices, jump).to_csv(out / "jump_flags.csv", index=False)
    log.info("Quality report written to %s", out)
    return rep


# --------------------------------------------------------------------------- main
STEPS = ("prices", "macro", "events", "quality")


def run_update(
    only: list[str] | None = None,
    full: bool = False,
    store: Store | None = None,
    yf_downloader: Callable | None = None,
    evds: EvdsClient | None = None,
    today: date | None = None,
    manual_dir: Path | None = None,
    results_dir: Path | None = None,
) -> pd.DataFrame:
    s = get_settings()
    manual_dir = manual_dir or s.paths.manual_dir
    results_dir = results_dir or s.paths.results_dir
    sources = get_data_sources()
    store = store or Store(s.paths.db_path, s.paths.raw_dir)
    if evds is None:
        key = get_secrets().evds_api_key
        evds = EvdsClient(sources.evds.base_url, key.get_secret_value() if key else None)
    manual_dir.mkdir(parents=True, exist_ok=True)
    ctx = Context(
        store=store,
        sources=sources,
        manual_dir=manual_dir,
        data_start=s.project.data_start,
        today=today or date.today(),
        full=full,
        run_at=datetime.now(UTC).replace(tzinfo=None),
        yf_downloader=yf_downloader,
        evds=evds,
    )
    steps = only or list(STEPS)
    if "prices" in steps:
        update_prices(ctx)
    if "macro" in steps:
        update_macro(ctx)
    if "events" in steps:
        update_events(ctx)
    if "quality" in steps:
        update_quality(ctx, results_dir, s.data_quality.jump_threshold, s.data_quality.stale_days)
    return store.query("SELECT * FROM update_log WHERE run_at = ?", [ctx.run_at])


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Fetch / update all PUSULA data.")
    p.add_argument("--full", action="store_true", help="re-download from data_start")
    p.add_argument("--only", nargs="+", choices=STEPS, help="run only these steps")
    args = p.parse_args(argv)
    setup_logging()
    res = run_update(only=args.only, full=args.full)
    summary = res.groupby("status").size().to_dict() if not res.empty else {}
    print("\nUpdate summary:", summary)
    problems = res[res["status"] != "ok"]
    if not problems.empty:
        print("\nNeeds attention:")
        print(problems[["series", "source", "status", "message"]].to_string(index=False))


if __name__ == "__main__":
    main()
