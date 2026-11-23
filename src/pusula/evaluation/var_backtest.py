"""E1 · Risk model validation: rolling 1-day VaR backtests (CLAUDE.md §6.5, D-066).

Design (all point-in-time):
* every stock, nominal TRY daily log returns from ``prices_clean``; first forecast day 2019-01-02;
* **refit every 5 trading days** on the last ``calibration_window`` (500) returns available at the
  refit date (at least ``min_history`` = 250); the fitted model is applied to the next 5 days;
* volatility models (FHS, GARCH-t) keep the refit parameters but update tomorrow's variance every
  day with the realised return (standard "filter daily, re-estimate weekly" practice; it uses
  only data up to the day before the forecast day);
* 1-day VaR is computed **without Monte Carlo** (exact quantiles): HS empirical quantile, GBM
  normal quantile, Merton quantile of the Poisson mixture of normals (root search), GARCH-t
  scaled Student-t quantile, FHS empirical quantile of the standardised residuals;
* at every refit the two critics of the risk engine are rerun (same code, same seeds, 200 paths
  per model as in the engine) and the in-sample and hold-out choices are recorded: their VaR is the
  VaR of the chosen model;
* a VaR exceedance = realised simple loss above the VaR.

Tests per stock: Kupiec POF (right number of exceedances), Christoffersen independence (no
clustering) and conditional coverage (both). Groups: model × universe (BIST30 / Energy /
sub-sector) × regime. Pooled numbers are also reported, plus the quantile ("tick") loss, a scoring
rule that ranks VaR forecasts (lower = better).
"""

from __future__ import annotations

import argparse
import time
from datetime import date

import numpy as np
import pandas as pd
from scipy import optimize, stats

from pusula.config import get_settings
from pusula.data.store import Store
from pusula.evaluation.common import (
    mark_latest,
    new_run_dir,
    process_pool,
    regime_of,
    save_fig,
    save_table,
)
from pusula.logging_setup import setup_logging
from pusula.risk import critic as critic_mod
from pusula.risk.engine import daily_returns, load_inputs
from pusula.risk.models import ModelFitError, default_models
from pusula.risk.simulate import rng_for

LEVELS = (0.95, 0.99)
BASE_MODELS = ["HS", "FHS", "GBM", "Merton", "GARCH-t"]
CRITIC_MODELS = ["critic_insample", "critic_holdout"]
ALL_MODELS = BASE_MODELS + CRITIC_MODELS
REFIT_EVERY = 5
START = "2019-01-01"


# --------------------------------------------------------------------------- statistical tests
def kupiec_pof(x: int, n: int, p: float) -> tuple[float, float]:
    """Kupiec (1995) proportion-of-failures LR test. x exceedances in n days, expected rate p.
    Returns (LR statistic, p-value); chi-square with 1 degree of freedom."""
    if n == 0:
        return np.nan, np.nan
    phat = x / n

    def ll(q):
        if not 0 < q < 1:
            return 0.0
        return (n - x) * np.log1p(-q) + x * np.log(q)

    # log-likelihood at the observed rate is 0 when phat is 0 or 1 (0·log 0 = 0)
    lr = max(0.0, -2 * (ll(p) - ll(phat)))
    return float(lr), float(stats.chi2.sf(lr, 1))


def christoffersen(hits: np.ndarray, p: float) -> dict[str, float]:
    """Christoffersen (1998) independence and conditional-coverage LR tests on a 0/1 hit series.
    Independence asks whether an exceedance today makes one tomorrow more likely (clustering)."""
    h = np.asarray(hits, dtype=int)
    n = len(h)
    x = int(h.sum())
    lr_pof, _ = kupiec_pof(x, n, p)
    if n < 2:
        return {"lr_ind": np.nan, "p_ind": np.nan, "lr_cc": np.nan, "p_cc": np.nan}
    a, b = h[:-1], h[1:]
    n00 = int(((a == 0) & (b == 0)).sum())
    n01 = int(((a == 0) & (b == 1)).sum())
    n10 = int(((a == 1) & (b == 0)).sum())
    n11 = int(((a == 1) & (b == 1)).sum())

    def xlogy(k, q):
        return k * np.log(q) if k > 0 else 0.0

    pi0 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi1 = n11 / (n10 + n11) if n10 + n11 else 0.0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)
    l_null = xlogy(n00 + n10, 1 - pi) + xlogy(n01 + n11, pi)
    l_alt = xlogy(n00, 1 - pi0) + xlogy(n01, pi0) + xlogy(n10, 1 - pi1) + xlogy(n11, pi1)
    lr_ind = max(0.0, -2 * (l_null - l_alt))
    lr_cc = lr_pof + lr_ind
    return {
        "lr_ind": float(lr_ind),
        "p_ind": float(stats.chi2.sf(lr_ind, 1)),
        "lr_cc": float(lr_cc),
        "p_cc": float(stats.chi2.sf(lr_cc, 2)),
    }


def tick_loss(r: np.ndarray, var_loss: np.ndarray, level: float) -> float:
    """Average quantile (pinball) loss of the VaR forecast as a return quantile; lower = better."""
    q = -var_loss  # VaR as a (simple) return quantile
    y = np.expm1(r)
    a = 1 - level
    return float(np.mean((a - (y < q)) * (y - q)))


# --------------------------------------------------------------------------- 1-day VaR, exact
def _loss(log_q: float | np.ndarray):
    return -np.expm1(log_q)


def merton_quantile(p: dict, a: float) -> float:
    """a-quantile of a 1-day Merton log return: Poisson(lam) mixture of normals."""
    if p["lam"] <= 0:
        return p["mu"] + p["sigma"] * stats.norm.ppf(a)
    ks = np.arange(0, 8)
    w = stats.poisson.pmf(ks, p["lam"])
    w = w / w.sum()
    m = p["mu"] + ks * p["mu_j"]
    s = np.sqrt(p["sigma"] ** 2 + ks * p["sigma_j"] ** 2)

    def cdf(x):
        return float((w * stats.norm.cdf((x - m) / s)).sum()) - a

    lo, hi = p["mu"] - 20 * s.max(), p["mu"] + 20 * s.max()
    return float(optimize.brentq(cdf, lo, hi, xtol=1e-10))


class Forecaster:
    """A fitted model that gives the 1-day VaR (loss fraction) for the next day and can be
    updated with the realised return (only the GARCH-type models change)."""

    def __init__(self, model, r: np.ndarray):
        self.name = model.name
        p = model.params
        self.p = p
        if self.name == "HS":
            self.q = {lv: float(np.quantile(r, 1 - lv)) for lv in LEVELS}
        elif self.name == "GBM":
            self.q = {lv: p["mu"] + p["sigma"] * stats.norm.ppf(1 - lv) for lv in LEVELS}
        elif self.name == "Merton":
            self.q = {lv: merton_quantile(p, 1 - lv) for lv in LEVELS}
        elif self.name == "GARCH-t":
            nu = p["nu"]
            scale = np.sqrt((nu - 2) / nu)
            self.z = {lv: stats.t.ppf(1 - lv, nu) * scale for lv in LEVELS}
            self.s2 = p["sigma2_next"]
        elif self.name == "FHS":
            self.z = {lv: float(np.quantile(model.z, 1 - lv)) for lv in LEVELS}
            self.s2 = p["sigma2_next"]
        else:
            raise ValueError(self.name)

    def var(self) -> dict[float, float]:
        if self.name in ("GARCH-t", "FHS"):
            sd = np.sqrt(self.s2)
            return {lv: float(_loss(self.p["mu"] + sd * self.z[lv])) for lv in LEVELS}
        return {lv: float(_loss(self.q[lv])) for lv in LEVELS}

    def update(self, r_t: float) -> None:
        if self.name in ("GARCH-t", "FHS"):
            p = self.p
            self.s2 = p["omega"] + p["alpha"] * (r_t - p["mu"]) ** 2 + p["beta"] * self.s2


def critic_choices(r: np.ndarray, symbol: str, as_of: date, cfg, seed: int, fitted: dict):
    """In-sample and hold-out critic choices, mirroring ``risk.engine.compute_risk_report``
    (same seeds, same number of critic paths). ``fitted`` = full-window fitted models by name."""
    n_hold = max(20, round(len(r) * cfg.critic_holdout_share))
    r_fit, r_hold = r[:-n_hold], r[-n_hold:]
    sims_in, sims_h = {}, {}
    for i, model in enumerate(default_models(cfg.merton_threshold, cfg.merton_min_jumps)):
        if model.name not in fitted:
            continue
        m_full = fitted[model.name]
        sims_in[model.name] = m_full.simulate(
            cfg.critic_paths, len(r), rng_for(seed, symbol, as_of, i, "critic"), "unconditional"
        )
        try:
            model.fit(r_fit)
            hs = model.simulate(
                cfg.critic_paths, n_hold, rng_for(seed, symbol, as_of, i, "holdout"), "current"
            )
            if np.all(np.isfinite(hs)):
                sims_h[model.name] = hs
        except ModelFitError:
            pass
    sel_in = critic_mod.select(critic_mod.critic_table(r, sims_in))[0]
    sel_h = critic_mod.select(critic_mod.critic_table(r_hold, sims_h))[0] if sims_h else sel_in
    return sel_in, sel_h


# --------------------------------------------------------------------------- one stock
def backtest_stock(args) -> pd.DataFrame:
    symbol, ret, cfg, seed, start = args
    ret = ret.dropna()
    dates = ret.index
    vals = ret.to_numpy()
    first = int(np.searchsorted(dates, pd.Timestamp(start)))
    first = max(first, cfg.min_history)
    rows = []
    for t0 in range(first, len(vals), REFIT_EVERY):
        win = vals[max(0, t0 - cfg.calibration_window) : t0]  # returns strictly before day t0
        as_of = dates[t0 - 1].date()
        fitted, fc = {}, {}
        for model in default_models(cfg.merton_threshold, cfg.merton_min_jumps):
            try:
                model.fit(win)
                f = Forecaster(model, win)
                if not all(np.isfinite(v) for v in f.var().values()):
                    raise ModelFitError("non-finite VaR")
                fitted[model.name], fc[model.name] = model, f
            except (ModelFitError, ValueError):
                continue
        if not fc:
            continue
        try:
            sel_in, sel_h = critic_choices(win, symbol, as_of, cfg, seed, fitted)
        except Exception:  # critic failure: record no critic choice for this block
            sel_in = sel_h = None
        for t in range(t0, min(t0 + REFIT_EVERY, len(vals))):
            row = {
                "date": dates[t],
                "symbol": symbol,
                "r": vals[t],
                "refit_date": dates[t0 - 1],
                "sel_insample": sel_in,
                "sel_holdout": sel_h,
            }
            for name, f in fc.items():
                v = f.var()
                for lv in LEVELS:
                    row[f"var{int(lv * 100)}_{name}"] = v[lv]
            for crit, sel in (("critic_insample", sel_in), ("critic_holdout", sel_h)):
                for lv in LEVELS:
                    k = f"var{int(lv * 100)}_{sel}"
                    row[f"var{int(lv * 100)}_{crit}"] = row.get(k, np.nan) if sel else np.nan
            rows.append(row)
            for f in fc.values():
                f.update(vals[t])
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- summaries
def _summ(g: pd.DataFrame, model: str, lv: float) -> dict:
    col = f"var{int(lv * 100)}_{model}"
    d = g[["symbol", "r", col]].dropna()
    if d.empty:
        return {}
    loss = -np.expm1(d["r"].to_numpy())
    hit = loss > d[col].to_numpy()
    p = 1 - lv
    n, x = len(d), int(hit.sum())
    _, p_pof = kupiec_pof(x, n, p)
    rej = {"pof": [], "ind": [], "cc": []}
    for _, s in d.assign(hit=hit).groupby("symbol"):
        if len(s) < 100:
            continue
        hs = s["hit"].to_numpy()
        rej["pof"].append(kupiec_pof(int(hs.sum()), len(hs), p)[1] < 0.05)
        c = christoffersen(hs, p)
        rej["ind"].append(c["p_ind"] < 0.05)
        rej["cc"].append(c["p_cc"] < 0.05)
    return {
        "model": model,
        "level": lv,
        "n_days": n,
        "n_stocks": d["symbol"].nunique(),
        "exceed_rate": x / n,
        "expected": p,
        "pooled_kupiec_p": p_pof,
        "share_reject_pof": float(np.mean(rej["pof"])) if rej["pof"] else np.nan,
        "share_reject_ind": float(np.mean(rej["ind"])) if rej["ind"] else np.nan,
        "share_reject_cc": float(np.mean(rej["cc"])) if rej["cc"] else np.nan,
        "tick_loss_x1e4": tick_loss(d["r"].to_numpy(), d[col].to_numpy(), lv) * 1e4,
        "mean_var": float(d[col].mean()),
    }


def per_stock_tests(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (sym, model, lv), _ in [
        ((s, m, lv), None) for s in panel["symbol"].unique() for m in ALL_MODELS for lv in LEVELS
    ]:
        col = f"var{int(lv * 100)}_{model}"
        d = panel.loc[panel["symbol"] == sym, ["r", col]].dropna()
        if d.empty:
            continue
        hit = (-np.expm1(d["r"].to_numpy())) > d[col].to_numpy()
        lr, p_pof = kupiec_pof(int(hit.sum()), len(hit), 1 - lv)
        c = christoffersen(hit, 1 - lv)
        rows.append(
            {
                "symbol": sym,
                "model": model,
                "level": lv,
                "n_days": len(d),
                "exceedances": int(hit.sum()),
                "exceed_rate": hit.mean(),
                "kupiec_lr": lr,
                "kupiec_p": p_pof,
                **c,
                "tick_loss_x1e4": tick_loss(d["r"].to_numpy(), d[col].to_numpy(), lv) * 1e4,
            }
        )
    return pd.DataFrame(rows)


def grouped(panel: pd.DataFrame, members: pd.DataFrame) -> pd.DataFrame:
    """model × level × group (all / BIST30 / Energy / sub-sector) × regime."""
    groups = {"Tümü": panel["symbol"].unique()}
    for u in ("BIST30", "Energy"):
        groups[u] = members.loc[members["universe"] == u, "symbol"].unique()
    for sub, g in members.dropna(subset=["sub_sector"]).groupby("sub_sector"):
        groups[f"Energy:{sub}"] = g["symbol"].unique()
    rows = []
    for gname, syms in groups.items():
        sub = panel[panel["symbol"].isin(syms)]
        for reg in ["all", *sorted(sub["regime"].dropna().unique())]:
            part = sub if reg == "all" else sub[sub["regime"] == reg]
            for model in ALL_MODELS:
                for lv in LEVELS:
                    s = _summ(part, model, lv)
                    if s:
                        rows.append({"group": gname, "regime": reg, **s})
    return pd.DataFrame(rows)


def critic_comparison(panel: pd.DataFrame) -> pd.DataFrame:
    """Key question of E1: hold-out critic vs in-sample critic vs plain HS, out of sample.
    Per stock and level: which of the three has the lower tick loss and the exceedance rate
    closer to the target; plus a paired sign test across stocks."""
    rows = []
    for lv in LEVELS:
        per = []
        for sym, g in panel.groupby("symbol"):
            rec = {"symbol": sym}
            for m in ("critic_holdout", "critic_insample", "HS"):
                col = f"var{int(lv * 100)}_{m}"
                d = g[["r", col]].dropna()
                if len(d) < 100:
                    break
                rec[m] = tick_loss(d["r"].to_numpy(), d[col].to_numpy(), lv)
                hit = (-np.expm1(d["r"].to_numpy())) > d[col].to_numpy()
                rec[f"{m}_dev"] = abs(hit.mean() - (1 - lv))
            else:
                per.append(rec)
        per = pd.DataFrame(per)
        for other in ("critic_insample", "HS"):
            wins = int((per["critic_holdout"] < per[other]).sum())
            n = len(per)
            cov_wins = int((per["critic_holdout_dev"] < per[f"{other}_dev"]).sum())
            rows.append(
                {
                    "level": lv,
                    "comparison": f"critic_holdout vs {other}",
                    "n_stocks": n,
                    "holdout_lower_tick_loss": wins,
                    "sign_test_p": float(stats.binomtest(wins, n, 0.5).pvalue) if n else np.nan,
                    "mean_tick_loss_holdout_x1e4": per["critic_holdout"].mean() * 1e4,
                    "mean_tick_loss_other_x1e4": per[other].mean() * 1e4,
                    "holdout_closer_coverage": cov_wins,
                }
            )
    return pd.DataFrame(rows)


def selection_shares(panel: pd.DataFrame) -> pd.DataFrame:
    blocks = panel.drop_duplicates(["symbol", "refit_date"])
    out = []
    for crit in ("sel_insample", "sel_holdout"):
        vc = blocks[crit].value_counts(normalize=True)
        out.append(vc.rename(crit))
    return pd.concat(out, axis=1).fillna(0.0).rename_axis("model").reset_index()


def plot_exceedance(summary: pd.DataFrame, out) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for ax, lv in zip(axes, LEVELS, strict=True):
        s = summary[
            (summary["regime"] == "all")
            & (summary["level"] == lv)
            & summary["group"].isin(["BIST30", "Energy"])
        ]
        piv = s.pivot(index="model", columns="group", values="exceed_rate").reindex(ALL_MODELS)
        x = np.arange(len(piv))
        ax.bar(x - 0.2, piv["BIST30"] * 100, 0.4, label="BIST30", color="#2E6FBA")
        ax.bar(x + 0.2, piv["Energy"] * 100, 0.4, label="Enerji", color="#E07B1F")
        ax.axhline((1 - lv) * 100, color="k", ls="--", lw=1, label="hedef")
        ax.set_xticks(x, [m.replace("critic_", "kritik\n") for m in piv.index], fontsize=8)
        ax.set_title(f"VaR %{int(lv * 100)} (1 gün): aşım oranı")
        ax.set_ylabel("%")
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    return save_fig(fig, out, "e1_exceedance_rates")


def plot_rolling(panel: pd.DataFrame, out) -> list[str]:
    import matplotlib.pyplot as plt

    p = panel.copy()
    p["loss"] = -np.expm1(p["r"])
    fig, ax = plt.subplots(figsize=(10, 3.6))
    for m, c in (
        ("HS", "#888888"),
        ("critic_insample", "#6A3D9A"),
        ("critic_holdout", "#2E6FBA"),
        ("GARCH-t", "#33A02C"),
    ):
        hit = (p["loss"] > p[f"var99_{m}"]).where(p[f"var99_{m}"].notna())
        s = hit.groupby(p["date"]).mean().rolling(126, min_periods=60).mean() * 100
        ax.plot(s.index, s.to_numpy(), label=m.replace("critic_", "kritik "), color=c, lw=1.2)
    ax.axhline(1, color="k", ls="--", lw=1)
    ax.set_ylabel("aşım oranı, % (126 gün hareketli)")
    ax.set_title("VaR %99 (1 gün): zaman içinde aşım oranı (tüm hisseler)")
    ax.legend(fontsize=8, ncol=4)
    fig.tight_layout()
    return save_fig(fig, out, "e1_rolling_exceedance_var99")


# --------------------------------------------------------------------------- main
def run(start: str = START, workers: int = 4, symbols: list[str] | None = None) -> str:
    from pusula.universe.members import universe_members

    s = get_settings()
    cfg, seed = s.risk, s.project.random_seed
    store = Store(s.paths.db_path, s.paths.raw_dir)
    mem = pd.concat(
        [universe_members(s.project.selection_date), universe_members(s.project.reference_date)]
    ).drop_duplicates(["symbol", "universe"])
    syms = symbols or sorted(mem["symbol"].unique())
    inp = load_inputs(store, store.prices()["date"].max().date())
    rets = {sym: daily_returns(inp, sym, "TRY", cfg.max_gap_sessions) for sym in syms}
    params = {
        "start": start,
        "refit_every": REFIT_EVERY,
        "window": cfg.calibration_window,
        "min_history": cfg.min_history,
        "critic_paths": cfg.critic_paths,
        "var_method": "exact quantiles (no Monte Carlo); critics 200 paths/model",
        "symbols": syms,
        "as_of_data": str(inp.as_of),
    }
    out = new_run_dir("e1_var", params)
    t0 = time.perf_counter()
    jobs = [(sym, rets[sym], cfg, seed, start) for sym in syms if len(rets[sym]) > cfg.min_history]
    parts = []
    with process_pool(workers) as ex:
        for i, part in enumerate(ex.map(backtest_stock, jobs), 1):
            parts.append(part)
            el = (time.perf_counter() - t0) / 60
            print(f"[e1] {i}/{len(jobs)} stocks done ({el:.1f} min)", flush=True)
    panel = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    panel["regime"] = regime_of(panel["date"]).to_numpy()
    panel.to_parquet(out / "var_forecasts.parquet", index=False)
    elapsed = time.perf_counter() - t0

    summary = grouped(panel, mem)
    save_table(summary, out, "e1_summary_by_group_regime", "{:.4f}")
    key = summary[
        (summary["regime"] == "all") & summary["group"].isin(["Tümü", "BIST30", "Energy"])
    ]
    save_table(
        key[
            [
                "group",
                "model",
                "level",
                "n_days",
                "exceed_rate",
                "pooled_kupiec_p",
                "share_reject_pof",
                "share_reject_ind",
                "share_reject_cc",
                "tick_loss_x1e4",
            ]
        ],
        out,
        "e1_key_table",
        "{:.3f}",
        caption="E1: 1-day VaR backtest, all regimes",
    )
    save_table(per_stock_tests(panel), out, "e1_per_stock_tests", "{:.4f}")
    save_table(
        critic_comparison(panel),
        out,
        "e1_critic_comparison",
        "{:.3f}",
        caption="E1: hold-out critic vs in-sample critic and HS (out of sample)",
    )
    save_table(selection_shares(panel), out, "e1_model_selection_shares", "{:.3f}")
    plot_exceedance(summary, out)
    plot_rolling(panel, out)
    (out / "runtime.txt").write_text(
        f"{len(jobs)} stocks, {len(panel)} stock-days, {elapsed / 60:.1f} min, {workers} workers\n"
    )
    mark_latest(out)
    return str(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="E1 rolling 1-day VaR backtest")
    ap.add_argument("--start", default=START)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--symbols", nargs="*")
    a = ap.parse_args()
    setup_logging("WARNING")
    print(run(a.start, a.workers, a.symbols))


if __name__ == "__main__":
    main()
