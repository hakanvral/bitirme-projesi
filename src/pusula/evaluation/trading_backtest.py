"""E4 · Weekly walk-forward decision backtest with LLM ablations (CLAUDE.md §6.5, D-070).

Stages (each resumable; rerunning skips finished work):
1. ``risk``   – relative risk levels for every decision date: TRY risk reports for the whole
                universe, computed in parallel workers and stored in ``risk_reports``;
2. ``inputs`` – point-in-time agent inputs (trend, risk, scenarios) for the 10 test stocks on
                every decision date, cached in ``data/e4_inputs/<date>.json``;
3. ``llm``    – one lean decision call (reasoning off) per stock-week and variant
                (P, P+R, P+R+S, P+R+S anonymised); finished calls are in the response cache;
4. ``eval``   – strategies, metrics, bootstrap CIs, tables and figures.

Rules (logged in docs/DECISIONS.md):
* **Stocks**: 5 BIST30 + 5 Energy names with the highest median daily traded value (close ×
  volume) over the 12 months before SELECTION_DATE, among names with a valid risk report at
  SELECTION_DATE (DSTKF has none). BIST30 names are picked first; Energy names already picked
  (overlap) are skipped so the 10 names are distinct.
* **Timing**: decide at the close of the last session of each week using data up to that close;
  hold over the following week (close to close). Costs 10 bp + 5 bp slippage per unit of
  position change.
* **Mapping**: primary AL = long, ALMA = cash, BEKLE = keep the previous position (start in
  cash); sensitivity BEKLE = 50% position.
* **Cash** earns TLREF. Each stock is a separate sleeve with 1/10 of the capital; the portfolio
  is the sum of the sleeves (no rebalancing between sleeves).
* **Rule-based filter (no LLM)**: long when price > 200-day MA and the hold-out-critic VaR 99
  (E1 forecast for the next day) is at or below its own median of the previous 252 sessions.
* **USD**: weekly TRY returns converted with the USD/TRY change; the risk-free rate in USD is
  TLREF converted the same way (the return of holding TRY cash, seen from USD).
* **Significance**: stationary bootstrap (mean block 4 weeks) for Sharpe differences.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date

import numpy as np
import pandas as pd

from pusula.config import get_settings
from pusula.data.store import Store
from pusula.evaluation.common import (
    latest_run,
    mark_latest,
    new_run_dir,
    save_fig,
    save_table,
)
from pusula.logging_setup import setup_logging

VARIANTS = {  # name -> (ablation, anonymised)
    "P": ("P", False),
    "P+R": ("P+R", False),
    "P+R+S": ("P+R+S", False),
    "P+R+S-anon": ("P+R+S", True),
}
BLOCK_OF = {"trend": "P", "risk": "P+R", "senaryo": "P+R+S"}
POST_CUTOFF = "2026-06-01"
N_BOOT = 5000
BLOCK_MEAN = 4


def _store() -> Store:
    s = get_settings()
    return Store(s.paths.db_path, s.paths.raw_dir)


def inputs_dir():
    d = get_settings().paths.data_dir / "e4_inputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- setup
def decision_dates(sessions: pd.DatetimeIndex, start: date, end: date | None = None) -> list:
    """Last session of each week from ``start``; the last week-end is dropped because its
    holding week has not happened yet."""
    s = pd.Series(sessions, index=sessions)
    s = s[s >= pd.Timestamp(start)]
    if end is not None:
        s = s[s <= pd.Timestamp(end)]
    wk = s.groupby([s.index.isocalendar().year, s.index.isocalendar().week]).max()
    ends = sorted(pd.DatetimeIndex(wk.to_numpy()))
    return [d.date() for d in ends[:-1]]


def select_stocks(store: Store, sel_date: date, n_each: int = 5) -> pd.DataFrame:
    from pusula.universe.members import universe_members

    mem = universe_members(sel_date)
    valid = set(
        store.query(
            "SELECT ticker FROM risk_reports WHERE as_of = ? AND basis = 'TRY'", [sel_date]
        )["ticker"]
    )
    px = store.prices(clean=False)
    lo = pd.Timestamp(sel_date) - pd.DateOffset(months=12)
    px = px[(px["date"] > lo) & (px["date"] <= pd.Timestamp(sel_date))]
    liq = (px["close"] * px["volume"]).groupby(px["ticker"]).median().rename("median_tv_try")
    m = mem.merge(liq, left_on="symbol", right_index=True, how="left")
    m["valid_report"] = m["symbol"].isin(valid)
    picked: list[str] = []
    rows = []
    for u in ("BIST30", "Energy"):
        g = m[(m["universe"] == u) & m["valid_report"] & ~m["symbol"].isin(picked)]
        g = g.sort_values("median_tv_try", ascending=False).head(n_each)
        picked += list(g["symbol"])
        rows.append(g)
    out = pd.concat(rows)[
        ["symbol", "ticker", "universe", "sub_sector", "median_tv_try", "in_bist30"]
    ]
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------- stage 1: risk
def _risk_worker(d: date) -> tuple[date, pd.DataFrame | str]:
    from pusula.risk.run_universe import run

    setup_logging("ERROR")
    try:
        return d, run(d, ("TRY",), _store(), persist=False)
    except Exception as exc:  # recorded, the stage continues
        return d, f"{type(exc).__name__}: {exc}"


def stage_risk(dates: list[date], workers: int) -> None:
    store = _store()
    have = set(
        pd.to_datetime(
            store.query("SELECT DISTINCT as_of FROM risk_reports WHERE basis = 'TRY'")["as_of"]
        ).dt.date
    )
    todo = [d for d in dates if d not in have]
    print(f"[risk] {len(dates) - len(todo)} dates done, {len(todo)} to compute", flush=True)
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, (d, tab) in enumerate(ex.map(_risk_worker, todo), 1):
            if isinstance(tab, str):
                print(f"[risk] {d} failed: {tab}", flush=True)
                continue
            store.replace_rows("risk_reports", tab, "as_of = ?", [d])
            print(f"[risk] {i}/{len(todo)} {d} ({time.perf_counter() - t0:.0f}s)", flush=True)


# --------------------------------------------------------------------------- stage 2: inputs
def _inputs_worker(args) -> tuple[date, str | None]:
    d, symbols = args
    from pusula.agents.inputs import build_stock_context

    setup_logging("ERROR")
    path = inputs_dir() / f"{d:%Y%m%d}.json"
    if path.exists():
        return d, None
    store = _store()
    rec = {}
    try:
        for sym in symbols:
            ctx = build_stock_context(store, sym, d, "P+R+S")
            rec[sym] = {
                "universe": ctx.universe,
                "sub_sector": ctx.sub_sector,
                "name": ctx.name,
                "blocks": ctx.blocks,
                "limitations": ctx.limitations,
            }
    except Exception as exc:
        return d, f"{type(exc).__name__}: {exc}"
    path.write_text(json.dumps(rec, ensure_ascii=False, default=float), encoding="utf-8")
    return d, None


def stage_inputs(dates: list[date], symbols: list[str], workers: int) -> None:
    todo = [d for d in dates if not (inputs_dir() / f"{d:%Y%m%d}.json").exists()]
    print(f"[inputs] {len(dates) - len(todo)} dates cached, {len(todo)} to build", flush=True)
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, (d, err) in enumerate(ex.map(_inputs_worker, [(d, symbols) for d in todo]), 1):
            msg = f"failed: {err}" if err else "ok"
            print(
                f"[inputs] {i}/{len(todo)} {d} {msg} ({time.perf_counter() - t0:.0f}s)", flush=True
            )


def variant_input(rec: dict, sym: str, d: date, variant: str) -> dict:
    """The agent input of one variant, built from the cached P+R+S context."""
    from pusula.agents.inputs import StockContext, to_input_json

    abl, anon = VARIANTS[variant]
    keep = {"P": ("trend",), "P+R": ("trend", "risk"), "P+R+S": ("trend", "risk", "senaryo")}[abl]
    ctx = StockContext(sym, d, rec["universe"], rec["sub_sector"], rec["name"])
    ctx.blocks = {k: v for k, v in rec["blocks"].items() if k in keep}
    ctx.limitations = {k: v for k, v in rec["limitations"].items() if k in keep}
    return to_input_json(ctx, anonymized=anon)


# --------------------------------------------------------------------------- stage 3: llm
def llm_tasks(dates, symbols, variants=tuple(VARIANTS)) -> list[tuple[date, str, str, dict]]:
    tasks = []
    for d in dates:
        p = inputs_dir() / f"{d:%Y%m%d}.json"
        if not p.exists():
            continue
        recs = json.loads(p.read_text(encoding="utf-8"))
        for sym in symbols:
            if sym in recs:
                for v in variants:
                    tasks.append((d, sym, v, variant_input(recs[sym], sym, d, v)))
    return tasks


def stage_llm(dates, symbols, yes: bool, out_csv) -> pd.DataFrame:
    from pusula.agents.agents import call_agent
    from pusula.agents.batch import estimate_wall_clock, run_batch
    from pusula.llm.factory import get_client

    s = get_settings()
    tasks = llm_tasks(dates, symbols)
    est = estimate_wall_clock(len(tasks), s.llm.rpm, 2.5, s.llm.max_concurrency)
    print(
        f"[llm] {len(tasks)} lean calls (cached ones are skipped): estimate "
        f"{est['estimate_h']:.2f} h at {s.llm.rpm} RPM ({est['bottleneck']})",
        flush=True,
    )
    if not yes and input("Continue? [y/N] ").strip().lower() != "y":
        raise SystemExit("aborted")
    client = get_client(lean=True)
    done = {"n": 0, "t0": time.perf_counter()}

    def make(t):
        d, sym, v, inp = t
        return lambda: call_agent(client, "lean_decision", inp, f"e4:{d}:{sym}:{v}")

    def on_done(i, res):
        done["n"] += 1
        if done["n"] % 50 == 0:
            el = time.perf_counter() - done["t0"]
            print(f"[llm] {done['n']}/{len(tasks)} ({el / 60:.1f} min)", flush=True)

    res = run_batch([make(t) for t in tasks], s.llm.max_concurrency, on_done)
    rows, recs = [], []
    for (d, sym, v, _), r in zip(tasks, res, strict=True):
        if isinstance(r, Exception):
            rows.append(
                {
                    "date": d,
                    "symbol": sym,
                    "variant": v,
                    "karar": None,
                    "guven": None,
                    "error": str(r)[:200],
                }
            )
            continue
        obj, rec = r
        recs.append(rec)
        rows.append(
            {
                "date": d,
                "symbol": sym,
                "variant": v,
                "karar": obj.karar,
                "guven": obj.guven,
                "gerekce": obj.kisa_gerekce,
                "cached": rec.cached,
                "latency_s": rec.latency_s,
                "json_failures": rec.json_failures,
                "error": None,
            }
        )
    _store().log_llm_calls([r for r in recs if not r.cached])
    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False)
    return df


# --------------------------------------------------------------------------- stage 4: eval
def weekly_frame(store: Store, symbols: list[str], dates: list[date]) -> dict[str, pd.DataFrame]:
    """Per decision date: next-week simple return of every symbol (+ XU030), TLREF cash return,
    USD/TRY change. Index = decision date d_k, values = return from d_k close to d_{k+1} close."""
    from pusula.features.returns import session_prices
    from pusula.risk.engine import load_inputs

    inp = load_inputs(store, store.prices()["date"].max().date())
    sess = inp.sessions
    ends = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    nxt = pd.DatetimeIndex([_next_week_end(sess, d) if (sess > d).any() else pd.NaT for d in ends])
    px = {sym: session_prices(inp.prices, sym, sess).ffill() for sym in [*symbols, "XU030.IS"]}
    rets = pd.DataFrame(
        {
            sym: (p.reindex(nxt).to_numpy() / p.reindex(ends).to_numpy() - 1)
            for sym, p in px.items()
        },
        index=ends,
    )
    macro = store.macro(["tlref", "interbank_on", "usdtry"])
    tl = macro[macro["series"] == "tlref"].set_index("date")["value"].sort_index()
    ib = macro[macro["series"] == "interbank_on"].set_index("date")["value"].sort_index()
    rate = tl.combine_first(ib[ib.index < tl.index.min()]) if not tl.empty else ib
    rate = rate.reindex(sess, method="ffill")
    fx = macro[macro["series"] == "usdtry"].set_index("date")["value"].sort_index()
    fx = fx.reindex(sess, method="ffill")
    days = (nxt - ends).days.to_numpy()
    rf = rate.reindex(ends).to_numpy() / 100 * days / 365
    dfx = fx.reindex(nxt).to_numpy() / fx.reindex(ends).to_numpy() - 1
    return {"ret": rets, "rf": pd.Series(rf, index=ends), "dfx": pd.Series(dfx, index=ends)}


def _next_week_end(sess: pd.DatetimeIndex, d: pd.Timestamp) -> pd.Timestamp:
    later = sess[sess > d]
    wk = later.isocalendar()
    first = (wk["year"].iloc[0], wk["week"].iloc[0])
    same = later[(wk["year"] == first[0]).to_numpy() & (wk["week"] == first[1]).to_numpy()]
    return same.max()


def positions(decisions: pd.Series, bekle: str = "keep") -> pd.Series:
    """AL -> 1, ALMA -> 0, BEKLE -> previous position ('keep', start 0) or 0.5 ('half').
    Missing decisions (failed calls) keep the previous position."""
    pos, prev = [], 0.0
    for k in decisions:
        if k == "AL":
            p = 1.0
        elif k == "ALMA":
            p = 0.0
        elif k == "BEKLE" and bekle == "half":
            p = 0.5
        else:
            p = prev
        pos.append(p)
        prev = p
    return pd.Series(pos, index=decisions.index)


def sleeve_returns(pos: pd.Series, r: pd.Series, rf: pd.Series, cost: float) -> pd.Series:
    """Weekly sleeve return: position in the stock, the rest in TLREF cash, minus trading costs
    on the change of position. Weeks without a stock return are held in cash."""
    r = r.reindex(pos.index)
    p = pos.where(r.notna(), 0.0)
    trade = (p - p.shift(1).fillna(0.0)).abs()
    return p * r.fillna(0.0) + (1 - p) * rf.reindex(pos.index) - cost * trade


def portfolio(sleeves: pd.DataFrame) -> pd.Series:
    """Equal initial capital in each sleeve, no rebalancing: portfolio = sum of sleeve values."""
    w = (1 + sleeves).cumprod()
    val = w.mean(axis=1)
    prev = pd.concat([pd.Series([1.0]), val.iloc[:-1]]).to_numpy()
    return pd.Series(val.to_numpy() / prev - 1, index=sleeves.index)


def to_usd(r: pd.Series, dfx: pd.Series) -> pd.Series:
    return (1 + r) / (1 + dfx.reindex(r.index)) - 1


def metrics(r: pd.Series, rf: pd.Series, pos: pd.DataFrame | None = None) -> dict:
    r, rf = r.dropna(), rf.reindex(r.dropna().index)
    if r.empty:
        return {}
    ex = r - rf
    n = len(r)
    wealth = (1 + r).cumprod()
    cum = float(wealth.iloc[-1] - 1)
    cagr = float((1 + cum) ** (52 / n) - 1)
    dd = float((wealth / wealth.cummax().clip(lower=1.0) - 1).min())
    downside = np.sqrt(np.mean(np.minimum(ex, 0) ** 2))
    out = {
        "weeks": n,
        "cum_return": cum,
        "cagr": cagr,
        "vol_ann": float(r.std(ddof=1) * np.sqrt(52)),
        "sharpe": float(ex.mean() / ex.std(ddof=1) * np.sqrt(52)) if ex.std(ddof=1) > 0 else np.nan,
        "sortino": float(ex.mean() / downside * np.sqrt(52)) if downside > 0 else np.nan,
        "max_drawdown": dd,
        "calmar": cagr / abs(dd) if dd < 0 else np.nan,
        "hit_rate": float((ex > 0).mean()),
    }
    if pos is not None:
        p = pos.reindex(r.index)
        out["avg_position"] = float(p.mean().mean())
        out["turnover_weekly"] = float((p - p.shift(1).fillna(0)).abs().mean().mean())
    return out


def _sharpe(ex: np.ndarray) -> float:
    s = ex.std(ddof=1)
    return ex.mean() / s * np.sqrt(52) if s > 0 else np.nan


def stationary_bootstrap_idx(n: int, mean_block: float, rng) -> np.ndarray:
    """Politis–Romano stationary bootstrap: blocks of geometric length (mean ``mean_block``)."""
    idx = np.empty(n, dtype=int)
    i = rng.integers(n)
    p = 1 / mean_block
    for t in range(n):
        idx[t] = i
        i = rng.integers(n) if rng.random() < p else (i + 1) % n
    return idx


def sharpe_diff_ci(ex_a: pd.Series, ex_b: pd.Series, seed: int, n_boot: int = N_BOOT) -> dict:
    d = pd.concat([ex_a, ex_b], axis=1).dropna().to_numpy()
    if len(d) < 10:
        return {"sharpe_diff": np.nan, "ci_lo": np.nan, "ci_hi": np.nan, "p_two_sided": np.nan}
    rng = np.random.default_rng(seed)
    obs = _sharpe(d[:, 0]) - _sharpe(d[:, 1])
    diffs = np.empty(n_boot)
    for b in range(n_boot):
        ix = stationary_bootstrap_idx(len(d), BLOCK_MEAN, rng)
        diffs[b] = _sharpe(d[ix, 0]) - _sharpe(d[ix, 1])
    diffs = diffs[np.isfinite(diffs)]
    p = 2 * min((diffs <= 0).mean(), (diffs >= 0).mean())
    return {
        "sharpe_diff": float(obs),
        "ci_lo": float(np.percentile(diffs, 2.5)),
        "ci_hi": float(np.percentile(diffs, 97.5)),
        "p_two_sided": float(min(1.0, p)),
    }


def rule_positions(store: Store, symbols: list[str], dates: list[date]) -> pd.DataFrame:
    """Rule-based risk filter (no LLM): price > MA200 and hold-out VaR99 <= its trailing
    252-session median, both known at the decision close."""
    from pusula.features.returns import session_prices
    from pusula.risk.engine import load_inputs

    e1 = latest_run("e1_var")
    if e1 is None:
        raise RuntimeError("E1 results not found: run pusula.evaluation.var_backtest first")
    var = pd.read_parquet(
        e1 / "var_forecasts.parquet", columns=["date", "symbol", "var99_critic_holdout"]
    )
    inp = load_inputs(store, store.prices()["date"].max().date())
    ends = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    out = {}
    for sym in symbols:
        p = session_prices(inp.prices, sym, inp.sessions)
        ma = p.rolling(200, min_periods=200).mean()
        v = var[var["symbol"] == sym].set_index("date")["var99_critic_holdout"].sort_index()
        med = v.rolling(252, min_periods=126).median().shift(1)
        # forecast for the first day after the decision close (made with data up to that close)
        nxt = v.index.searchsorted(ends, side="right")
        ok_idx = nxt < len(v)
        v_next = pd.Series(np.nan, index=ends)
        m_next = pd.Series(np.nan, index=ends)
        v_next[ok_idx] = v.iloc[nxt[ok_idx]].to_numpy()
        m_next[ok_idx] = med.iloc[nxt[ok_idx]].to_numpy()
        trend = (p.reindex(ends) > ma.reindex(ends)).to_numpy()
        out[sym] = pd.Series(np.where(trend & (v_next <= m_next).to_numpy(), 1.0, 0.0), index=ends)
    return pd.DataFrame(out)


def evaluate(dec: pd.DataFrame, stocks: pd.DataFrame, dates: list[date], out, seed: int) -> dict:
    s = get_settings()
    cost = (s.backtest.transaction_cost_bp + s.backtest.slippage_bp) / 1e4
    store = _store()
    syms = list(stocks["symbol"])
    W = weekly_frame(store, syms, dates)
    ret, rf, dfx = W["ret"], W["rf"], W["dfx"]
    idx = ret.index
    strat_pos: dict[str, pd.DataFrame] = {
        "Al-ve-tut (EW)": pd.DataFrame(1.0, index=idx, columns=syms),
        "Kural tabanlı risk filtresi": rule_positions(store, syms, dates),
    }
    dec = dec.copy()
    dec["date"] = pd.to_datetime(dec["date"])
    for v in VARIANTS:
        piv = dec[dec["variant"] == v].pivot(index="date", columns="symbol", values="karar")
        piv = piv.reindex(index=idx, columns=syms)
        strat_pos[f"LLM {v}"] = piv.apply(positions)
        strat_pos[f"LLM {v} (BEKLE=%50)"] = piv.apply(lambda c: positions(c, "half"))
    port, sleeves_all = {}, {}
    for name, pos in strat_pos.items():
        sl = pd.DataFrame({sym: sleeve_returns(pos[sym], ret[sym], rf, cost) for sym in syms})
        sleeves_all[name] = sl
        port[name] = portfolio(sl)
    xu = ret["XU030.IS"].copy()
    xu.iloc[0] -= cost
    port["XU030"] = xu

    rows, per_stock = [], []
    windows = {"tam": idx, "kesim sonrası": idx[idx >= pd.Timestamp(POST_CUTOFF)]}
    for wname, w in windows.items():
        for name, r in port.items():
            for basis in ("TRY", "USD"):
                rr = r.reindex(w)
                rff = rf.reindex(w)
                if basis == "USD":
                    rr, rff = to_usd(rr, dfx), to_usd(rff, dfx)
                pos = strat_pos.get(name)
                rows.append(
                    {
                        "window": wname,
                        "strategy": name,
                        "basis": basis,
                        **metrics(rr, rff, pos.reindex(w) if pos is not None else None),
                    }
                )
    for name, sl in sleeves_all.items():
        for sym in syms:
            m = metrics(sl[sym], rf, strat_pos[name][[sym]])
            per_stock.append({"strategy": name, "symbol": sym, **m})
    perf = pd.DataFrame(rows)
    save_table(
        perf,
        out,
        "e4_performance",
        "{:.3f}",
        caption="E4: weekly decision backtest (portfolio of 10 sleeves)",
    )
    save_table(pd.DataFrame(per_stock), out, "e4_performance_per_stock", "{:.3f}")

    # Sharpe-difference CIs (TRY, full window)
    ci_rows = []
    pairs = [(f"LLM {v}", "Al-ve-tut (EW)") for v in VARIANTS]
    pairs += [
        ("Kural tabanlı risk filtresi", "Al-ve-tut (EW)"),
        ("LLM P+R", "LLM P"),
        ("LLM P+R+S", "LLM P+R"),
        ("LLM P+R+S", "LLM P"),
        ("LLM P+R+S", "LLM P+R+S-anon"),
        ("LLM P+R+S", "Kural tabanlı risk filtresi"),
    ]
    for wname, w in windows.items():
        for a, b in pairs:
            ea, eb = port[a].reindex(w) - rf.reindex(w), port[b].reindex(w) - rf.reindex(w)
            ci_rows.append({"window": wname, "a": a, "b": b, **sharpe_diff_ci(ea, eb, seed)})
    save_table(
        pd.DataFrame(ci_rows),
        out,
        "e4_sharpe_diff_ci",
        "{:.3f}",
        caption="E4: stationary-bootstrap 95% CI of Sharpe differences (TRY)",
    )

    # decision distribution
    dist = dec.groupby(["variant", "karar"]).size().unstack(fill_value=0)
    dist = dist.div(dist.sum(axis=1), axis=0).reset_index()
    dist["BEKLE_dominates_(>70%)"] = dist.get("BEKLE", 0) > 0.70
    save_table(dist, out, "e4_decision_distribution", "{:.3f}")
    ds = dec.groupby(["variant", "symbol", "karar"]).size().unstack(fill_value=0)
    ds = ds.div(ds.sum(axis=1), axis=0).reset_index()
    save_table(ds, out, "e4_decision_distribution_per_stock", "{:.3f}")
    fails = dec["karar"].isna().groupby(dec["variant"]).mean().rename("failed_share").reset_index()
    save_table(fails, out, "e4_failed_calls", "{:.3f}")
    plot_equity(port, rf, out)
    return {"perf": perf, "dist": dist}


def plot_equity(port: dict[str, pd.Series], rf: pd.Series, out) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4.2))
    styles = {
        "Al-ve-tut (EW)": ("#444444", "-"),
        "XU030": ("#999999", "--"),
        "Kural tabanlı risk filtresi": ("#33A02C", "-"),
        "LLM P": ("#A6CEE3", "-"),
        "LLM P+R": ("#1F78B4", "-"),
        "LLM P+R+S": ("#E31A1C", "-"),
        "LLM P+R+S-anon": ("#FB9A99", "--"),
    }
    for name, (c, ls) in styles.items():
        if name in port:
            w = (1 + port[name].fillna(0)).cumprod()
            ax.plot(w.index, w.to_numpy(), color=c, ls=ls, lw=1.4, label=name)
    cash = (1 + rf.fillna(0)).cumprod()
    ax.plot(cash.index, cash.to_numpy(), color="k", ls=":", lw=1, label="Nakit (TLREF)")
    ax.axvline(pd.Timestamp(POST_CUTOFF), color="grey", lw=0.8)
    ax.text(
        pd.Timestamp(POST_CUTOFF),
        ax.get_ylim()[1],
        " model eğitim kesimi sonrası",
        fontsize=7,
        va="top",
    )
    ax.set_ylabel("portföy değeri (başlangıç = 1, TRY)")
    ax.set_title("E4: haftalık karar destek backtest'i (10 hisse, maliyetler dahil)")
    ax.legend(fontsize=7, ncol=3)
    fig.tight_layout()
    return save_fig(fig, out, "e4_equity_curves")


def long_sample(stocks: pd.DataFrame, out, seed: int) -> pd.DataFrame:
    """Non-LLM strategies over 2019–2026 (more statistical power than 52 LLM weeks)."""
    s = get_settings()
    cost = (s.backtest.transaction_cost_bp + s.backtest.slippage_bp) / 1e4
    store = _store()
    from pusula.risk.engine import load_inputs

    inp = load_inputs(store, store.prices()["date"].max().date())
    dates = decision_dates(inp.sessions, s.backtest.long_sample_start)
    syms = list(stocks["symbol"])
    W = weekly_frame(store, syms, dates)
    ret, rf, dfx = W["ret"], W["rf"], W["dfx"]
    idx = ret.index
    pos = {
        "Al-ve-tut (EW)": pd.DataFrame(1.0, index=idx, columns=syms),
        "Kural tabanlı risk filtresi": rule_positions(store, syms, dates),
    }
    port = {
        n: portfolio(pd.DataFrame({x: sleeve_returns(p[x], ret[x], rf, cost) for x in syms}))
        for n, p in pos.items()
    }
    xu = ret["XU030.IS"].copy()
    xu.iloc[0] -= cost
    port["XU030"] = xu
    rows = []
    for name, r in port.items():
        for basis in ("TRY", "USD"):
            rr, rff = (r, rf) if basis == "TRY" else (to_usd(r, dfx), to_usd(rf, dfx))
            rows.append(
                {
                    "strategy": name,
                    "basis": basis,
                    **metrics(rr, rff, pos.get(name)),
                }
            )
    tab = pd.DataFrame(rows)
    ci = sharpe_diff_ci(port["Kural tabanlı risk filtresi"] - rf, port["Al-ve-tut (EW)"] - rf, seed)
    tab.attrs["ci"] = ci
    save_table(
        tab,
        out,
        "e4_long_sample_2019_2026",
        "{:.3f}",
        caption="E4 reference: non-LLM strategies 2019–2026",
    )
    save_table(
        pd.DataFrame([{"a": "Kural tabanlı risk filtresi", "b": "Al-ve-tut (EW)", **ci}]),
        out,
        "e4_long_sample_sharpe_ci",
        "{:.3f}",
    )
    return tab


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="E4 weekly decision backtest (resumable)")
    ap.add_argument(
        "--stages",
        nargs="+",
        default=["risk", "inputs", "llm", "eval"],
        choices=["risk", "inputs", "llm", "eval"],
    )
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--yes", action="store_true", help="skip the confirmation before LLM calls")
    ap.add_argument("--end", type=date.fromisoformat, default=None)
    a = ap.parse_args(argv)
    setup_logging("WARNING")
    s = get_settings()
    store = _store()
    from pusula.risk.engine import load_inputs

    inp = load_inputs(store, store.prices()["date"].max().date())
    dates = decision_dates(inp.sessions, s.project.selection_date, a.end)
    stocks = select_stocks(store, s.project.selection_date)
    syms = list(stocks["symbol"])
    print(
        f"E4: {len(dates)} decision dates {dates[0]} → {dates[-1]}; stocks: {', '.join(syms)}",
        flush=True,
    )
    state = s.paths.results_dir / "e4_backtest" / "state"
    state.mkdir(parents=True, exist_ok=True)
    stocks.to_csv(state / "stocks.csv", index=False)
    if "risk" in a.stages:
        stage_risk(dates, a.workers)
    if "inputs" in a.stages:
        stage_inputs(dates, syms, a.workers)
    if "llm" in a.stages:
        stage_llm(dates, syms, a.yes, state / "decisions.csv")
    if "eval" in a.stages:
        dec = pd.read_csv(state / "decisions.csv")
        out = new_run_dir(
            "e4_backtest",
            {
                "dates": [str(d) for d in dates],
                "stocks": syms,
                "variants": VARIANTS,
                "post_cutoff": POST_CUTOFF,
                "n_boot": N_BOOT,
                "block_mean_weeks": BLOCK_MEAN,
            },
        )
        save_table(stocks, out, "e4_stocks", "{:,.0f}")
        evaluate(dec, stocks, dates, out, s.project.random_seed)
        long_sample(stocks, out, s.project.random_seed)
        mark_latest(out)
        print(out)


if __name__ == "__main__":
    main()
