"""E3 · PPK (MPC) event study (CLAUDE.md §6.5, D-069).

For every rate-change decision since 2018 (``data/manual/ppk_decisions.csv``):

* **Realised reaction** over the window [−1, +5] trading days around the decision day (day 0 =
  meeting date; the decision is announced at 14:00 during the session):
  - *market-model CAR*: Σ (r_i − α_i − β_i r_XU100), with α, β estimated on days [−250, −30];
  - *mean-adjusted return*: Σ (r_i − mean r_i on [−250, −30]); keeps the market-wide part of the
    reaction, which is what the scenario engine predicts.
* **Predicted reaction** from the scenario engine **fitted only on data before the event**
  (``as_of`` = day −2): Model A betas, the macro covariance of the regime current at that date,
  the regime's policy-rate → 2Y-yield pass-through (pooled fallback), shock = the actual policy
  change, propagated mode, a 1-week horizon. The prediction is the deterministic expected
  log-return change, Σ_k β_k (E[ΔX_k | shock] − E[ΔX_k]).
  - total prediction vs the mean-adjusted return;
  - abnormal prediction = total − β_i^MM × (prediction for XU100) vs the CAR.
* **Scores**: direction accuracy (sign agreement) and MAE, per universe and sub-sector, with 95%
  bootstrap CIs that resample *events* (stocks in the same event are correlated).
* **Holds** (no change) are reported separately as realised reactions only.

Small-sample caveat: only a few dozen decisions, clustered in a few policy cycles; the CIs are wide
and results by sub-sector rest on 2–6 stocks.
"""

from __future__ import annotations

import argparse
from datetime import date

import numpy as np
import pandas as pd

from pusula.config import get_settings
from pusula.data.adapters.manual_csv import read_ppk
from pusula.data.store import Store
from pusula.evaluation.common import mark_latest, new_run_dir, regime_of, save_fig, save_table
from pusula.logging_setup import setup_logging
from pusula.macro.context import build_context, current_passthrough, make_engine
from pusula.macro.factor_model import InsufficientDataError, fit_stock
from pusula.macro.scenarios import Z_GUARD, to_factor_shocks
from pusula.risk.engine import daily_returns, load_inputs

WIN = (-1, 5)
EST = (-250, -30)
MIN_EST = 120
N_BOOT = 2000
MARKET = "XU100.IS"


def predicted_responses(store: Store, as_of: date, policy_bp: float) -> dict | None:
    """Expected 1-week log-return change per stock (and XU100) for a policy-rate change, using
    only data up to ``as_of``."""
    try:
        ctx = build_context(store, as_of)
        if ctx.fp.X.empty or not ctx.fits_a:
            return None  # factor history too short at this date (needs 104 weeks)
        eng = make_engine(ctx, n_paths=10)
    except (ValueError, KeyError, InsufficientDataError):
        return None
    pt = current_passthrough(ctx)
    spec = to_factor_shocks({"policy_rate_bp": policy_bp}, eng.factors, pt)
    if not spec.factor_shocks:
        return None
    h = 1
    zs = eng.shock_z(h, spec.factor_shocks)
    mu_w, cov_w, cov_src = eng.mu_w, eng.cov_w, eng.cov_source
    if zs and max(abs(v) for v in zs.values()) > Z_GUARD and eng.cov_full is not None:
        mu_w, cov_w, cov_src = eng.mu_full, eng.cov_full, "full (guard)"
    z = np.zeros((eng.n_paths, len(eng.factors)))
    _, m_base = eng.macro_draws(h, None, "propagated", z, mu_w, cov_w)
    _, m_scen = eng.macro_draws(h, spec.factor_shocks, "propagated", z, mu_w, cov_w)
    dX = pd.Series(m_scen - m_base, index=eng.factors)
    pred = {
        s: float(sum(f.beta.get(c, 0.0) * dX[c] for c in eng.factors))
        for s, f in ctx.fits_a.items()
    }
    mk_cols = [c for c in eng.factors if c != "ptf"]
    try:
        fm = fit_stock(ctx.fp.returns[MARKET], ctx.fp.X[mk_cols], MARKET, "A", with_extras=False)
        pred[MARKET] = float(sum(fm.beta[c] * dX[c] for c in mk_cols))
    except (InsufficientDataError, KeyError):
        pass
    return {
        "pred": pred,
        "d_rate_pp": spec.factor_shocks.get("rate"),
        "passthrough_regime": pt.regime if pt else None,
        "passthrough_beta": pt.beta if pt else None,
        "cov_source": cov_src,
        "rate_source": ctx.fp.rate_source,
        "members": ctx.members,
    }


def realised(rets: pd.DataFrame, day0: int) -> pd.DataFrame:
    """CAR and mean-adjusted window returns for every column of ``rets`` (daily log returns
    on the session calendar), event at row position ``day0``."""
    est = rets.iloc[day0 + EST[0] : day0 + EST[1] + 1]
    win = rets.iloc[day0 + WIN[0] : day0 + WIN[1] + 1]
    m_est, m_win = est[MARKET], win[MARKET]
    rows = []
    for s in rets.columns:
        e = pd.concat([est[s], m_est], axis=1).dropna()
        w = win[s]
        if len(e) < MIN_EST or w.isna().sum() > 1:
            continue
        x, y = e.iloc[:, 1].to_numpy(), e.iloc[:, 0].to_numpy()
        beta = float(np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1))
        alpha = float(y.mean() - beta * x.mean())
        ok = w.notna() & m_win.notna()
        car = float((w[ok] - alpha - beta * m_win[ok]).sum())
        mean_adj = float((w[ok] - y.mean()).sum())
        rows.append(
            {
                "symbol": s,
                "car": car,
                "mean_adj": mean_adj,
                "beta_mm": beta,
                "raw": float(w[ok].sum()),
            }
        )
    return pd.DataFrame(rows)


def _boot(df: pd.DataFrame, fn, rng) -> tuple[float, float]:
    ev = df["event"].unique()
    groups = {e: g for e, g in df.groupby("event")}
    vals = []
    for _ in range(N_BOOT):
        pick = rng.choice(ev, size=len(ev), replace=True)
        vals.append(fn(pd.concat([groups[e] for e in pick])))
    return float(np.nanpercentile(vals, 2.5)), float(np.nanpercentile(vals, 97.5))


def scores(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = []
    for gname, g in _groups(df):
        for kind, p, r in (("total", "pred_total", "mean_adj"), ("abnormal", "pred_abn", "car")):
            d = g.dropna(subset=[p, r])
            d = d[d[p] != 0]
            if d.empty:
                continue

            def acc(x, p=p, r=r):
                return float((np.sign(x[p]) == np.sign(x[r])).mean())

            def mae(x, p=p, r=r):
                return float((x[p] - x[r]).abs().mean())

            a_lo, a_hi = _boot(d, acc, rng)
            m_lo, m_hi = _boot(d, mae, rng)
            out.append(
                {
                    "group": gname,
                    "comparison": kind,
                    "n_events": d["event"].nunique(),
                    "n_obs": len(d),
                    "direction_accuracy": acc(d),
                    "acc_ci_lo": a_lo,
                    "acc_ci_hi": a_hi,
                    "mae_pct": mae(d) * 100,
                    "mae_ci_lo": m_lo * 100,
                    "mae_ci_hi": m_hi * 100,
                    "mean_pred_pct": d[p].mean() * 100,
                    "mean_real_pct": d[r].mean() * 100,
                    "corr": float(d[[p, r]].corr().iloc[0, 1]) if len(d) > 2 else np.nan,
                }
            )
    return pd.DataFrame(out)


def _groups(df: pd.DataFrame):
    yield "Tümü", df.drop_duplicates(["event", "symbol"])
    for u in ("BIST30", "Energy"):
        yield u, df[df["universe"] == u]
    for sub, g in df[df["universe"] == "Energy"].groupby("sub_sector"):
        yield f"Energy:{sub}", g
    for d, g in df.groupby("direction"):
        yield f"Tümü:{d}", g.drop_duplicates(["event", "symbol"])


def plot_scatter(df: pd.DataFrame, out) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for ax, (p, r, title) in zip(
        axes,
        (("pred_total", "mean_adj", "Toplam tepki"), ("pred_abn", "car", "Anormal tepki (CAR)")),
        strict=True,
    ):
        for u, c in (("BIST30", "#2E6FBA"), ("Energy", "#E07B1F")):
            g = df[df["universe"] == u]
            ax.scatter(
                g[p] * 100,
                g[r] * 100,
                s=8,
                alpha=0.45,
                color=c,
                label="BIST30" if u == "BIST30" else "Enerji",
            )
        lim = np.nanpercentile(np.abs(df[[p, r]].to_numpy()) * 100, 99)
        ax.plot([-lim, lim], [-lim, lim], "k--", lw=0.8)
        ax.axhline(0, color="grey", lw=0.5)
        ax.axvline(0, color="grey", lw=0.5)
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.set_xlabel("model tahmini, %")
        ax.set_ylabel("gerçekleşen [−1, +5], %")
        ax.set_title(title)
    axes[0].legend(fontsize=8)
    fig.suptitle(
        "PPK faiz değişiklikleri: senaryo motoru tahmini ve gerçekleşen tepki", fontsize=10
    )
    fig.tight_layout()
    return save_fig(fig, out, "e3_pred_vs_realised")


def plot_events(ev: pd.DataFrame, out) -> list[str]:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 3.6))
    e = ev.sort_values("meeting_date")
    x = np.arange(len(e))
    ax.bar(x - 0.2, e["car_BIST30"] * 100, 0.4, color="#2E6FBA", label="BIST30 ort. CAR")
    ax.bar(x + 0.2, e["car_Energy"] * 100, 0.4, color="#E07B1F", label="Enerji ort. CAR")
    ax.set_xticks(
        x,
        [f"{d:%Y-%m}\n{b:+.0f}" for d, b in zip(e["meeting_date"], e["change_bp"], strict=True)],
        fontsize=6,
    )
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("ort. CAR [−1, +5], %")
    ax.set_title(
        "PPK faiz değişiklikleri: evren ortalaması anormal getiri (alt satır: değişim, bp)"
    )
    ax.legend(fontsize=8)
    fig.tight_layout()
    return save_fig(fig, out, "e3_event_car_by_universe")


def run(start: str = "2018-01-01") -> str:
    s = get_settings()
    store = Store(s.paths.db_path, s.paths.raw_dir)
    ppk = read_ppk(s.paths.manual_dir / "ppk_decisions.csv")
    ppk = ppk[ppk["meeting_date"] >= pd.Timestamp(start)].sort_values("meeting_date")
    last = store.prices()["date"].max().date()
    inp = load_inputs(store, last)
    from pusula.universe.members import universe_members

    syms = sorted(
        set(universe_members(s.project.selection_date)["symbol"])
        | set(universe_members(s.project.reference_date)["symbol"])
        | {MARKET}
    )
    rets = pd.DataFrame({x: daily_returns(inp, x, "TRY", s.risk.max_gap_sessions) for x in syms})
    rets = rets.reindex(inp.sessions[1:])
    out = new_run_dir(
        "e3_event",
        {
            "window": WIN,
            "estimation": EST,
            "n_boot": N_BOOT,
            "start": start,
            "horizon_weeks": 1,
            "mode": "propagated",
        },
    )
    rows, ev_rows = [], []
    for e in ppk.itertuples():
        m = pd.Timestamp(e.meeting_date)
        day0 = int(rets.index.searchsorted(m))
        if day0 + WIN[1] >= len(rets) or day0 + EST[0] < 0:
            continue
        real = realised(rets, day0)
        if real.empty:
            continue
        change = float(e.change_bp)
        kind = "hold" if change == 0 else ("cut" if change < 0 else "hike")
        as_of = rets.index[day0 - 2].date()
        info = {
            "event": m.date(),
            "meeting_date": m,
            "change_bp": change,
            "direction": kind,
            "regime": regime_of([m]).iloc[0],
        }
        pred = predicted_responses(store, as_of, change) if change != 0 else None
        if pred:
            mem = pred["members"].drop_duplicates(["symbol", "universe"])
            info.update(
                {
                    k: pred[k]
                    for k in (
                        "d_rate_pp",
                        "passthrough_regime",
                        "passthrough_beta",
                        "cov_source",
                        "rate_source",
                    )
                }
            )
        else:
            mem = universe_members(as_of).drop_duplicates(["symbol", "universe"])
        if change != 0:
            info["no_prediction_reason"] = "factor history < 104 weeks before the event"
        mkt_pred = pred["pred"].get(MARKET) if pred else None
        r = real.merge(mem[["symbol", "universe", "sub_sector"]], on="symbol")
        for x in r.itertuples():
            p = pred["pred"].get(x.symbol) if pred else None
            rows.append(
                {
                    **info,
                    "symbol": x.symbol,
                    "universe": x.universe,
                    "sub_sector": x.sub_sector,
                    "car": x.car,
                    "mean_adj": x.mean_adj,
                    "raw": x.raw,
                    "beta_mm": x.beta_mm,
                    "pred_total": p,
                    "pred_abn": (p - x.beta_mm * mkt_pred)
                    if (p is not None and mkt_pred is not None)
                    else None,
                }
            )
        mk = real[real["symbol"] == MARKET]
        ev_rows.append(
            {
                **info,
                "xu100_raw": float(mk["raw"].iloc[0]) if not mk.empty else None,
                "xu100_pred": mkt_pred,
                **{f"car_{u}": r[r["universe"] == u]["car"].mean() for u in ("BIST30", "Energy")},
                **{
                    f"mean_adj_{u}": r[r["universe"] == u]["mean_adj"].mean()
                    for u in ("BIST30", "Energy")
                },
            }
        )
        print(f"{m.date()} {change:+.0f} bp: {len(r)} stocks", flush=True)
    df = pd.DataFrame(rows)
    ev = pd.DataFrame(ev_rows)
    df.to_csv(out / "e3_stock_events.csv", index=False)
    changes = df[df["direction"] != "hold"].copy()
    for c in ("pred_total", "pred_abn"):
        changes[c] = changes[c].astype(float)
    sc = scores(changes, s.project.random_seed)
    save_table(
        sc,
        out,
        "e3_scores",
        "{:.3f}",
        caption="E3: scenario-engine prediction vs realised [-1,+5] reaction, rate changes",
    )
    save_table(ev.drop(columns=["meeting_date"]), out, "e3_events", "{:.4f}")
    holds = df[df["direction"] == "hold"]
    hold_sum = holds.groupby("universe")[["car", "mean_adj"]].agg(["mean", "median", "count"])
    hold_sum.columns = ["_".join(c) for c in hold_sum.columns]
    save_table(hold_sum.reset_index(), out, "e3_holds_realised", "{:.4f}")
    real_by = (
        df.groupby(["direction", "universe"])[["car", "mean_adj"]].mean() * 100
    ).reset_index()
    real_by["n_events"] = df.groupby(["direction", "universe"])["event"].nunique().to_numpy()
    save_table(real_by, out, "e3_realised_by_direction", "{:.3f}")
    if not changes.empty:
        plot_scatter(changes.dropna(subset=["pred_total"]), out)
        plot_events(ev[ev["direction"] != "hold"], out)
    mark_latest(out)
    return str(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="E3 PPK event study")
    ap.add_argument("--start", default="2018-01-01")
    a = ap.parse_args()
    setup_logging("WARNING")
    print(run(a.start))


if __name__ == "__main__":
    main()
