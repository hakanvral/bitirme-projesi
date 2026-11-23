"""Paced, resumable runner for the remaining LLM work: E4 variants and the reduced E5 (D-074).

    uv run python -m pusula.evaluation.llm_runner restore     # fresh container: restore the state
    uv run python -m pusula.evaluation.llm_runner all          # E4 P+R+S, P, E5, P+R+S-anon, P+R
    uv run python -m pusula.evaluation.llm_runner e4 --variants P+R+S P
    uv run python -m pusula.evaluation.llm_runner e5
    uv run python -m pusula.evaluation.llm_runner save         # compress the cache (no commit)
    add --no-push to skip the automatic git commit/push

Why: on 2026-11-23 the NVIDIA NIM free tier first throttled a 4-worker, 35 RPM batch and then
reported the model as DEGRADED (D-073). This runner is gentle and adaptive:
* **1 worker**, starting at 10 requests/min. The pause is applied only after *live* calls
  (answers from the cache cost nothing).
* On HTTP 429, a DEGRADED model, a timeout or a 5xx error, the pace is halved (min 2 RPM) and the
  runner waits (60 s, doubling up to 15 min) before retrying the **same** item. After 30
  successful live calls in a row and 5 minutes at the current pace it speeds up by 2 RPM
  (cap 20 RPM).
* Every finished E4 decision is appended to ``llm_state/e4_decisions.csv`` (committed).
  Rerunning skips them, even in a fresh container whose rebuilt inputs would not match the cache
  keys exactly.
* Every 100 new live answers: the LLM cache is saved as ``llm_state/llm_cache.sqlite.gz``, the
  status block in ``docs/PROGRESS.md`` is refreshed, and both are committed and pushed.
The E4 inputs themselves are *not* committed (they contain numbers derived from the manual
CDS / 2Y data); a fresh container rebuilds them with
``python -m pusula.evaluation.trading_backtest --stages risk inputs``.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import shutil
import sqlite3
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from pusula.config import ROOT_DIR, get_settings
from pusula.logging_setup import setup_logging

STATE_DIR = ROOT_DIR / "llm_state"
DECISIONS = STATE_DIR / "e4_decisions.csv"
CACHE_GZ = STATE_DIR / "llm_cache.sqlite.gz"
PROGRESS = ROOT_DIR / "docs" / "PROGRESS.md"
E4_ORDER = ["P+R+S", "P", "P+R+S-anon", "P+R"]
FIELDS = [
    "date",
    "symbol",
    "variant",
    "karar",
    "guven",
    "gerekce",
    "model",
    "prompt_version",
    "cached",
    "latency_s",
    "finished_at",
]
CHECKPOINT_EVERY = 100
BEGIN, END = "<!-- llm-run-status:begin -->", "<!-- llm-run-status:end -->"


# --------------------------------------------------------------------------- pacing
TRANSIENT = ("429", "DEGRADED", "HTTP 5", "request failed", "timed out", "Timeout", "502", "503")


def is_transient(exc: Exception) -> bool:
    """Provider-side trouble (retry the same item later) vs a real failure of this item."""
    return any(t in str(exc) for t in TRANSIENT)


class AdaptivePacer:
    """Requests-per-minute controller for one sequential worker."""

    def __init__(
        self,
        start=10.0,
        lo=2.0,
        cap=20.0,
        step=2.0,
        stable_calls=30,
        stable_s=300,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self.rpm, self.lo, self.cap, self.step = start, lo, cap, step
        self.stable_calls, self.stable_s = stable_calls, stable_s
        self.ok_streak, self.backoff_s = 0, 60.0
        self._sleep, self._clock = sleep, clock
        self.changed_at = clock()
        self.events: list[str] = []

    def after_live_call(self, started: float) -> None:
        """Keep at least 60/rpm seconds between the starts of two live calls."""
        wait = 60.0 / self.rpm - (self._clock() - started)
        if wait > 0:
            self._sleep(wait)

    def success(self) -> None:
        self.ok_streak += 1
        self.backoff_s = 60.0
        if (
            self.ok_streak >= self.stable_calls
            and self.rpm < self.cap
            and self._clock() - self.changed_at >= self.stable_s
        ):
            self.rpm = min(self.cap, self.rpm + self.step)
            self.ok_streak, self.changed_at = 0, self._clock()
            self.events.append(f"{_now()} pace up to {self.rpm:.0f} RPM")

    def trouble(self, exc: Exception) -> float:
        """Slow down and wait; returns the seconds waited."""
        self.rpm = max(self.lo, self.rpm / 2)
        self.ok_streak, self.changed_at = 0, self._clock()
        wait = self.backoff_s
        self.backoff_s = min(900.0, self.backoff_s * 2)
        self.events.append(f"{_now()} {str(exc)[:80]!r}: pace {self.rpm:.0f} RPM, wait {wait:.0f}s")
        print(self.events[-1], flush=True)
        self._sleep(wait)
        return wait


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def paced(fn, pacer: AdaptivePacer, max_item_failures: int = 2):
    """Call ``fn()`` (returns (obj, CallRecord)) until it succeeds; transient errors are retried
    without limit (with backoff); other errors are retried ``max_item_failures`` times, then
    returned as the exception."""
    fails = 0
    while True:
        t0 = time.monotonic()
        try:
            obj, rec = fn()
        except Exception as exc:
            if is_transient(exc):
                pacer.trouble(exc)
                continue
            fails += 1
            if fails > max_item_failures:
                return exc
            pacer.after_live_call(t0)
            continue
        if not rec.cached:
            pacer.success()
            pacer.after_live_call(t0)
        return obj, rec


# --------------------------------------------------------------------------- state
def save_cache() -> Path:
    """Consistent copy of the SQLite cache (backup API), gzip-compressed into llm_state/."""
    src = get_settings().llm.cache_path
    STATE_DIR.mkdir(exist_ok=True)
    tmp = STATE_DIR / "_cache_copy.sqlite"
    with sqlite3.connect(src) as a, sqlite3.connect(tmp) as b:
        a.backup(b)
    with open(tmp, "rb") as f, gzip.open(CACHE_GZ, "wb", compresslevel=9) as g:
        shutil.copyfileobj(f, g)
    tmp.unlink()
    return CACHE_GZ


def restore_cache() -> int:
    """Merge the committed cache into the local one (existing rows are kept). Returns the number
    of rows added."""
    if not CACHE_GZ.exists():
        print("no committed cache found")
        return 0
    dst = get_settings().llm.cache_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_DIR / "_restore.sqlite"
    with gzip.open(CACHE_GZ, "rb") as g, open(tmp, "wb") as f:
        shutil.copyfileobj(g, f)
    from pusula.llm.cache import ResponseCache

    ResponseCache(dst)  # creates the table if the local cache does not exist yet
    with sqlite3.connect(dst) as con:
        before = con.execute("SELECT count(*) FROM responses").fetchone()[0]
        con.execute("ATTACH DATABASE ? AS src", (str(tmp),))
        con.execute("INSERT OR IGNORE INTO responses SELECT * FROM src.responses")
        con.commit()
        after = con.execute("SELECT count(*) FROM responses").fetchone()[0]
        con.execute("DETACH DATABASE src")
    tmp.unlink()
    print(f"cache restored: {after - before} rows added ({after} in total) -> {dst}")
    return after - before


def done_decisions() -> pd.DataFrame:
    if not DECISIONS.exists():
        return pd.DataFrame(columns=FIELDS)
    return pd.read_csv(DECISIONS, dtype={"date": str})


def append_decision(row: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    new = not DECISIONS.exists()
    with open(DECISIONS, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k) for k in FIELDS})


def status_markdown(total_per_variant: int, pacer: AdaptivePacer | None, note: str = "") -> str:
    d = done_decisions()
    lines = [
        BEGIN,
        "",
        f"**LLM run status** (updated {_now()}; `llm_runner`, D-074)",
        "",
        "| E4 variant | Decisions | Coverage |",
        "|---|---|---|",
    ]
    for v in E4_ORDER:
        n = int((d["variant"] == v).sum()) if not d.empty else 0
        lines.append(f"| {v} | {n} / {total_per_variant} | {n / total_per_variant:.0%} |")
    if pacer is not None:
        lines += ["", f"Current pace: {pacer.rpm:.0f} RPM (1 worker)."]
        if pacer.events:
            lines += ["", "Recent pacing events: " + "; ".join(pacer.events[-3:])]
    if note:
        lines += ["", note]
    lines += [
        "",
        "Resume: `uv run python -m pusula.evaluation.llm_runner all` (fresh container: "
        "see `docs/RUN_LLM_LOCALLY.md`).",
        "",
        END,
    ]
    return "\n".join(lines)


def write_status(total: int, pacer: AdaptivePacer | None, note: str = "") -> None:
    text = PROGRESS.read_text(encoding="utf-8")
    block = status_markdown(total, pacer, note)
    if BEGIN in text and END in text:
        pre, rest = text.split(BEGIN, 1)
        post = rest.split(END, 1)[1]
        text = pre + block + post
    else:  # place it right below the checklist heading
        marker = "LLM runs are resumable"
        text = (
            text.replace(marker, block + "\n\n" + marker, 1)
            if marker in text
            else (text + "\n" + block + "\n")
        )
    PROGRESS.write_text(text, encoding="utf-8")


def checkpoint(total: int, pacer: AdaptivePacer | None, push: bool, note: str = "") -> None:
    save_cache()
    write_status(total, pacer, note)
    if not push:
        return
    paths = [str(STATE_DIR.relative_to(ROOT_DIR)), str(PROGRESS.relative_to(ROOT_DIR))]
    subprocess.run(["git", "add", *paths], cwd=ROOT_DIR, check=False)
    msg = (
        f"llm_state checkpoint: {len(done_decisions())} E4 decisions\n\n"
        "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"
        "Claude-Session: https://claude.ai/code/session_015Gt1b9wm3LSVZig5UfPjcX"
    )
    r = subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT_DIR, check=False)
    if r.returncode != 0:
        return  # nothing to commit
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT_DIR, capture_output=True, text=True
    ).stdout.strip()
    for attempt in range(4):
        if subprocess.run(["git", "push", "-q", "origin", branch], cwd=ROOT_DIR).returncode == 0:
            return
        time.sleep(2 ** (attempt + 1))
    print("warning: git push failed; the commit stays local", flush=True)


# --------------------------------------------------------------------------- E4
def run_e4(variants: list[str], pacer: AdaptivePacer, push: bool) -> None:
    from pusula.agents.agents import call_agent
    from pusula.evaluation.trading_backtest import (
        _store,
        decision_dates,
        inputs_dir,
        llm_tasks,
        select_stocks,
    )
    from pusula.llm.factory import get_client
    from pusula.risk.engine import load_inputs

    s = get_settings()
    store = _store()
    inp = load_inputs(store, store.prices()["date"].max().date())
    dates = decision_dates(inp.sessions, s.project.selection_date)
    syms = list(select_stocks(store, s.project.selection_date)["symbol"])
    total = len(dates) * len(syms)
    missing = [d for d in dates if not (inputs_dir() / f"{d:%Y%m%d}.json").exists()]
    if missing:
        raise SystemExit(
            f"{len(missing)} E4 input dates missing: run "
            "`python -m pusula.evaluation.trading_backtest --stages risk inputs`"
        )
    client = get_client(lean=True)
    client.max_backoff_retries = 0  # the pacer handles 429s (D-074)
    new_live = 0
    for v in variants:
        done = done_decisions()
        have = set(zip(done["date"].astype(str), done["symbol"], done["variant"], strict=True))
        tasks = [t for t in llm_tasks(dates, syms, (v,)) if (str(t[0]), t[1], t[2]) not in have]
        print(
            f"[e4] {v}: {total - len(tasks)}/{total} done, {len(tasks)} to go "
            f"(start pace {pacer.rpm:.0f} RPM)",
            flush=True,
        )
        for i, (d, sym, var, payload) in enumerate(tasks, 1):
            res = paced(
                lambda p=payload, d=d, sym=sym, var=var: call_agent(
                    client, "lean_decision", p, f"e4:{d}:{sym}:{var}"
                ),
                pacer,
            )
            if isinstance(res, Exception):
                print(f"[e4] {d} {sym} {var} failed: {str(res)[:120]}", flush=True)
                continue
            obj, rec = res
            store.log_llm_calls([] if rec.cached else [rec])
            append_decision(
                {
                    "date": str(d),
                    "symbol": sym,
                    "variant": var,
                    "karar": obj.karar,
                    "guven": obj.guven,
                    "gerekce": obj.kisa_gerekce,
                    "model": rec.model,
                    "prompt_version": rec.prompt_version,
                    "cached": rec.cached,
                    "latency_s": round(rec.latency_s, 2),
                    "finished_at": _now(),
                }
            )
            new_live += not rec.cached
            if i % 50 == 0:
                print(f"[e4] {v}: {i}/{len(tasks)} (pace {pacer.rpm:.0f} RPM)", flush=True)
            if new_live and new_live % CHECKPOINT_EVERY == 0 and not rec.cached:
                checkpoint(total, pacer, push)
        checkpoint(total, pacer, push, note=f"Variant {v} finished at {_now()}.")


# --------------------------------------------------------------------------- E5
def run_e5(pacer: AdaptivePacer, push: bool) -> str:
    from pusula.evaluation import llm_reliability as e5

    def executor(thunks):
        out = []
        for i, fn in enumerate(thunks, 1):
            out.append(paced(fn, pacer))
            if i % 20 == 0:
                print(f"[e5] {i}/{len(thunks)} calls (pace {pacer.rpm:.0f} RPM)", flush=True)
        return out

    path = e5.main(["--yes"], executor=executor, max_backoff_retries=0)
    d = done_decisions()
    total = int(d.groupby("variant").size().max()) if not d.empty else 0
    checkpoint(total or 540, pacer, push, note=f"E5 (reduced) finished at {_now()}: {path}")
    return path


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("command", choices=["all", "e4", "e5", "save", "restore"])
    ap.add_argument("--variants", nargs="+", default=E4_ORDER, choices=E4_ORDER)
    ap.add_argument("--start-rpm", type=float, default=10.0)
    ap.add_argument("--no-push", action="store_true", help="do not commit/push checkpoints")
    a = ap.parse_args(argv)
    setup_logging("WARNING")
    if a.command == "save":
        print(save_cache())
        return
    if a.command == "restore":
        restore_cache()
        return
    pacer = AdaptivePacer(start=a.start_rpm)
    push = not a.no_push
    if a.command == "e4":
        run_e4(a.variants, pacer, push)
    elif a.command == "e5":
        run_e5(pacer, push)
    else:  # all: the two most important variants, then the reduced E5, then the rest
        run_e4(["P+R+S", "P"], pacer, push)
        run_e5(pacer, push)
        run_e4(["P+R+S-anon", "P+R"], pacer, push)
    print(f"done at {_now()}", flush=True)


if __name__ == "__main__":
    main()
