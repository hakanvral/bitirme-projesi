"""DuckDB storage + raw Parquet snapshots.

Tables (CLAUDE.md §5):
* ``prices``        daily OHLCV per ticker (primary key: date, ticker)
* ``macro``         daily/monthly macro values (primary key: date, series)
* ``events``        e.g. PPK decisions
* ``universe``      universe membership snapshots
* ``analysis_runs`` agent pipeline outputs (filled from P4)
* ``llm_usage``     token / cost log (filled from P4)
* ``update_log``    one row per (run, series): status, rows, message
* ``quality_report`` latest data quality report

Upserts use ``INSERT OR REPLACE`` on the primary key, so re-running an update is idempotent and
also picks up revisions of recent values.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    date DATE NOT NULL, ticker VARCHAR NOT NULL,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, adj_close DOUBLE, volume DOUBLE,
    source VARCHAR, updated_at TIMESTAMP,
    PRIMARY KEY (date, ticker)
);
CREATE TABLE IF NOT EXISTS macro (
    date DATE NOT NULL, series VARCHAR NOT NULL, value DOUBLE,
    release_date DATE, source VARCHAR, updated_at TIMESTAMP,
    PRIMARY KEY (date, series)
);
CREATE TABLE IF NOT EXISTS events (
    event_date DATE NOT NULL, event_type VARCHAR NOT NULL, payload JSON,
    source VARCHAR, updated_at TIMESTAMP,
    PRIMARY KEY (event_date, event_type)
);
CREATE TABLE IF NOT EXISTS universe (
    universe VARCHAR NOT NULL, as_of DATE NOT NULL, ticker VARCHAR NOT NULL,
    sub_sector VARCHAR, in_bist30 BOOLEAN, updated_at TIMESTAMP,
    PRIMARY KEY (universe, as_of, ticker)
);
CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id VARCHAR PRIMARY KEY, ticker VARCHAR, as_of DATE, mode VARCHAR,
    payload JSON, created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS llm_usage (
    call_id VARCHAR PRIMARY KEY, run_id VARCHAR, agent VARCHAR, model VARCHAR,
    prompt_version VARCHAR, input_tokens BIGINT, output_tokens BIGINT,
    cache_read_tokens BIGINT, cost_usd DOUBLE, latency_s DOUBLE, cached BOOLEAN,
    created_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS update_log (
    run_at TIMESTAMP, series VARCHAR, source VARCHAR, status VARCHAR,
    rows BIGINT, message VARCHAR
);
CREATE TABLE IF NOT EXISTS quality_report (
    series VARCHAR, kind VARCHAR, source VARCHAR, first_date DATE, last_date DATE,
    coverage_pct DOUBLE, missing_days BIGINT, stale_days BIGINT, jumps BIGINT,
    last_update TIMESTAMP, status VARCHAR, generated_at TIMESTAMP
);
"""

PRICE_COLS = ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]
MACRO_COLS = ["date", "series", "value", "release_date"]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Store:
    def __init__(self, db_path: Path, raw_dir: Path | None = None) -> None:
        self.db_path = Path(db_path)
        self.raw_dir = Path(raw_dir) if raw_dir else self.db_path.parent / "raw"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.execute(SCHEMA)

    @contextmanager
    def connect(self, read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
        con = duckdb.connect(str(self.db_path), read_only=read_only)
        try:
            yield con
        finally:
            con.close()

    # ------------------------------------------------------------------ raw snapshots
    def save_raw(self, source: str, df: pd.DataFrame, day: date | None = None) -> Path:
        """Append ``df`` to ``data/raw/<source>/<YYYYMMDD>.parquet`` (one file per source/day)."""
        day = day or date.today()
        path = self.raw_dir / source / f"{day:%Y%m%d}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
        df.to_parquet(path, index=False)
        return path

    # ------------------------------------------------------------------ writes
    def upsert_prices(self, df: pd.DataFrame, source: str) -> int:
        if df.empty:
            return 0
        d = df[PRICE_COLS].copy()
        d["date"] = pd.to_datetime(d["date"]).dt.date
        d["source"] = source
        d["updated_at"] = _now()
        with self.connect() as con:
            con.register("incoming", d)
            con.execute("INSERT OR REPLACE INTO prices SELECT * FROM incoming")
        return len(d)

    def upsert_macro(self, df: pd.DataFrame, source: str) -> int:
        if df.empty:
            return 0
        d = df.copy()
        if "release_date" not in d:
            d["release_date"] = pd.NaT
        d = d[MACRO_COLS]
        d["date"] = pd.to_datetime(d["date"]).dt.date
        d["release_date"] = pd.to_datetime(d["release_date"]).dt.date
        d["source"] = source
        d["updated_at"] = _now()
        with self.connect() as con:
            con.register("incoming", d)
            con.execute("INSERT OR REPLACE INTO macro SELECT * FROM incoming")
        return len(d)

    def upsert_events(self, df: pd.DataFrame, event_type: str, date_col: str, source: str) -> int:
        if df.empty:
            return 0
        rows = pd.DataFrame(
            {
                "event_date": pd.to_datetime(df[date_col]).dt.date,
                "event_type": event_type,
                "payload": [
                    json.dumps(r, default=str, ensure_ascii=False)
                    for r in df.drop(columns=[date_col]).to_dict("records")
                ],
                "source": source,
                "updated_at": _now(),
            }
        )
        with self.connect() as con:
            con.register("incoming", rows)
            con.execute(
                "INSERT OR REPLACE INTO events SELECT event_date, event_type, payload::JSON, "
                "source, updated_at FROM incoming"
            )
        return len(rows)

    def replace_universe(self, universe: str, as_of: date, df: pd.DataFrame) -> None:
        d = df[["ticker", "sub_sector", "in_bist30"]].copy()
        d.insert(0, "as_of", as_of)
        d.insert(0, "universe", universe)
        d["updated_at"] = _now()
        with self.connect() as con:
            con.execute("DELETE FROM universe WHERE universe = ? AND as_of = ?", [universe, as_of])
            con.register("incoming", d)
            con.execute("INSERT INTO universe SELECT * FROM incoming")

    def log_update(
        self, run_at: datetime, series: str, source: str, status: str, rows: int, message: str = ""
    ) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT INTO update_log VALUES (?, ?, ?, ?, ?, ?)",
                [run_at, series, source, status, rows, message[:500]],
            )

    def replace_quality_report(self, df: pd.DataFrame) -> None:
        d = df.copy()
        d["generated_at"] = _now()
        with self.connect() as con:
            con.execute("DELETE FROM quality_report")
            con.register("incoming", d)
            con.execute("INSERT INTO quality_report BY NAME SELECT * FROM incoming")

    # ------------------------------------------------------------------ reads
    def query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        with self.connect(read_only=True) as con:
            return con.execute(sql, params or []).df()

    def last_date(self, table: str, key_col: str, key: str) -> date | None:
        """Most recent stored date for one ticker / series (for incremental updates)."""
        assert table in {"prices", "macro"} and key_col in {"ticker", "series"}
        res = self.query(f"SELECT max(date) AS d FROM {table} WHERE {key_col} = ?", [key])
        v = res["d"].iloc[0]
        return None if pd.isna(v) else pd.Timestamp(v).date()

    def prices(self, tickers: list[str] | None = None, end: date | None = None) -> pd.DataFrame:
        sql, params = "SELECT * FROM prices WHERE 1=1", []
        if tickers:
            sql += f" AND ticker IN ({','.join('?' * len(tickers))})"
            params += tickers
        if end:
            sql += " AND date <= ?"
            params.append(end)
        df = self.query(sql + " ORDER BY ticker, date", params)
        df["date"] = pd.to_datetime(df["date"])
        return df

    def macro(self, series: list[str] | None = None) -> pd.DataFrame:
        sql, params = "SELECT * FROM macro", []
        if series:
            sql += f" WHERE series IN ({','.join('?' * len(series))})"
            params += series
        df = self.query(sql + " ORDER BY series, date", params)
        df["date"] = pd.to_datetime(df["date"])
        df["release_date"] = pd.to_datetime(df["release_date"])
        return df
