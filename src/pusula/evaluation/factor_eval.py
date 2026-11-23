"""E2 · Factor model evaluation (CLAUDE.md §6.5, D-067).

* **In-sample R²** of Model A (macro factors) and Model B (+ XU100 residual) on the full weekly
  sample (as in the dashboard).
* **Out-of-sample R²**, rolling: fit on 104 weeks (2 years), test on the next 26 weeks, then
  move forward 26 weeks. OOS R² = 1 − SSE/SST with SST around the *training* mean. The factor
  changes of the test weeks are the realised ones (the model explains contemporaneous moves, it
  does not forecast factors), so OOS R² measures how *stable* the stock–macro link is.
  Model B's market residual in the test weeks uses the orthogonalisation coefficients of the
  training window only.
* **Beta stability**: rolling 104-week betas: standard deviation, and share of windows whose sign
  agrees with the full-sample beta.
* **VIF** (multicollinearity): maximum per stock.
* **Regimes**: Model A refitted in each regime (≥ 52 weeks).
* **Heatmap**: response (%) of each stock to a 1-standard-deviation weekly move of each factor,
  BIST30 vs Energy sub-sectors.
* **Energy vs BIST30**, with and without the overlapping names (TUPRS): mean sensitivity and R²,
  Mann–Whitney p-values.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy import stats

from pusula.app.i18n_tr import t
from pusula.config import get_regimes, get_settings
from pusula.data.store import Store
from pusula.evaluation.common import mark_latest, new_run_dir, save_fig, save_table
from pusula.logging_setup import setup_logging
from pusula.macro.context import build_context
from pusula.macro.factor_model import factors_for, regime_betas, rolling_betas

FIT_WEEKS, TEST_WEEKS = 104, 26


def _ols(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    A = np.column_stack([np.ones(len(y)), X])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    return coef


def oos_r2(y: pd.Series, X: pd.DataFrame, market: pd.Series | None = None) -> dict:
    """Rolling out-of-sample R² (pooled over all test blocks) and the mean in-window R²."""
    cols = list(X.columns)
    d = pd.concat(
        [y.rename("y"), X] + ([market.rename("m")] if market is not None else []), axis=1
    ).dropna()
    sse = sst = 0.0
    n_blocks, n_test, is_r2 = 0, 0, []
    for start in range(0, len(d) - FIT_WEEKS - 4, TEST_WEEKS):
        tr = d.iloc[start : start + FIT_WEEKS]
        te = d.iloc[start + FIT_WEEKS : start + FIT_WEEKS + TEST_WEEKS]
        if len(te) < 4:
            break
        Xtr, Xte = tr[cols].to_numpy(), te[cols].to_numpy()
        if market is not None:  # orthogonalise XU100 on the macro factors, training window only
            g = _ols(tr["m"].to_numpy(), Xtr)
            res_tr = tr["m"].to_numpy() - np.column_stack([np.ones(len(tr)), Xtr]) @ g
            res_te = te["m"].to_numpy() - np.column_stack([np.ones(len(te)), Xte]) @ g
            Xtr, Xte = np.column_stack([Xtr, res_tr]), np.column_stack([Xte, res_te])
        b = _ols(tr["y"].to_numpy(), Xtr)
        fit_tr = np.column_stack([np.ones(len(tr)), Xtr]) @ b
        pred = np.column_stack([np.ones(len(te)), Xte]) @ b
        ytr, yte = tr["y"].to_numpy(), te["y"].to_numpy()
        is_r2.append(1 - np.sum((ytr - fit_tr) ** 2) / np.sum((ytr - ytr.mean()) ** 2))
        sse += float(np.sum((yte - pred) ** 2))
        sst += float(np.sum((yte - ytr.mean()) ** 2))
        n_blocks += 1
        n_test += len(te)
    return {
        "oos_r2": 1 - sse / sst if sst > 0 else np.nan,
        "rolling_is_r2": float(np.mean(is_r2)) if is_r2 else np.nan,
        "n_blocks": n_blocks,
        "n_test_weeks": n_test,
    }


def beta_stability(y: pd.Series, X: pd.DataFrame, full_beta: dict[str, float]) -> pd.DataFrame:
    """Rolling 104-week betas (every 4 weeks), expressed as the % response to a 1-sd weekly move
    so that factors are comparable."""
    sd = X.std() * 100
    rb = rolling_betas(y, X, window=FIT_WEEKS, step=4) * sd
    rows = []
    for c in X.columns:
        s = rb[c].dropna()
        if s.empty:
            continue
        rows.append(
            {
                "factor": c,
                "full_resp_1sd_pct": full_beta[c] * sd[c],
                "rolling_mean_resp_1sd_pct": s.mean(),
                "rolling_sd_resp_1sd_pct": s.std(),
                "sign_agreement": float((np.sign(s) == np.sign(full_beta[c])).mean()),
                "n_windows": len(s),
            }
        )
    return pd.DataFrame(rows)


def _mw(a: pd.Series, b: pd.Series) -> float:
    a, b = a.dropna(), b.dropna()
    if len(a) < 3 or len(b) < 3:
        return np.nan
    return float(stats.mannwhitneyu(a, b).pvalue)


def plot_heatmap(sens: pd.DataFrame, members: pd.DataFrame, out) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    order_sub = ["refining_petroleum", "natural_gas", "electricity"]
    mem = members.drop_duplicates(["symbol", "universe"])
    rows, labels, seps = [], [], []
    b30 = sorted(mem.loc[mem["universe"] == "BIST30", "symbol"])
    blocks = [("BIST30", b30)] + [
        (
            t(f"subsector_{s}"),
            sorted(mem.loc[(mem["universe"] == "Energy") & (mem["sub_sector"] == s), "symbol"]),
        )
        for s in order_sub
    ]
    piv = sens.pivot(index="symbol", columns="factor", values="resp_1sd_pct")
    pv = sens.pivot(index="symbol", columns="factor", values="p")
    facs = [
        f
        for f in ["rate", "usdtry", "brent", "ttf", "cds", "vix", "us10y", "ptf"]
        if f in piv.columns
    ]
    for name, syms in blocks:
        syms = [s for s in syms if s in piv.index]
        for s in syms:
            rows.append(s)
            labels.append(s.removesuffix(".IS") + ("" if name == "BIST30" else f"  ({name})"))
        seps.append(len(rows))
    M = piv.reindex(index=rows, columns=facs).to_numpy()
    P = pv.reindex(index=rows, columns=facs).to_numpy()
    lim = np.nanmax(np.abs(M))
    fig, ax = plt.subplots(figsize=(7.5, 0.24 * len(rows) + 1.6))
    im = ax.imshow(M, aspect="auto", cmap="RdBu", norm=TwoSlopeNorm(0, -lim, lim))
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if np.isfinite(M[i, j]):
                star = "*" if P[i, j] < 0.05 else ""
                ax.text(j, i, f"{M[i, j]:.1f}{star}", ha="center", va="center", fontsize=6)
    for s in seps[:-1]:
        ax.axhline(s - 0.5, color="k", lw=1.2)
    ax.set_xticks(
        range(len(facs)), [t(f"factor_{f}") for f in facs], rotation=30, ha="right", fontsize=8
    )
    ax.set_yticks(range(len(rows)), labels, fontsize=6.5)
    ax.set_title(
        "1 standart sapmalık haftalık faktör hareketine yüzde tepki (Model A)\n"
        "* p < 0,05 (Newey–West)",
        fontsize=9,
    )
    fig.colorbar(im, ax=ax, shrink=0.6, label="%")
    fig.tight_layout()
    return save_fig(fig, out, "e2_beta_heatmap")


def plot_r2(stock_tbl: pd.DataFrame, out) -> list[str]:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 3.6))
    cols = ["r2_A", "r2_B", "oos_r2_A", "oos_r2_B"]
    names = ["IS A", "IS B", "OOS A", "OOS B"]
    x = np.arange(len(cols))
    for k, (u, c) in enumerate((("BIST30", "#2E6FBA"), ("Energy", "#E07B1F"))):
        g = stock_tbl[stock_tbl["universe"] == u]
        ax.bar(
            x + (k - 0.5) * 0.4,
            g[cols].median().to_numpy(),
            0.4,
            label="BIST30" if u == "BIST30" else "Enerji",
            color=c,
        )
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x, names)
    ax.set_ylabel("medyan R²")
    ax.set_title("Faktör modeli: örneklem içi (IS) ve dışı (OOS) R²")
    ax.legend()
    fig.tight_layout()
    return save_fig(fig, out, "e2_r2_is_oos")


def run() -> str:
    s = get_settings()
    store = Store(s.paths.db_path, s.paths.raw_dir)
    as_of = store.prices()["date"].max().date()
    ctx = build_context(store, as_of)
    fp, mem = ctx.fp, ctx.members
    out = new_run_dir(
        "e2_factor",
        {
            "as_of": str(as_of),
            "fit_weeks": FIT_WEEKS,
            "test_weeks": TEST_WEEKS,
            "rate_source": fp.rate_source,
            "missing_factors": fp.missing,
        },
    )
    sub = mem.drop_duplicates("symbol").set_index("symbol")["sub_sector"]
    sd = fp.X.std()
    mkt = fp.returns["XU100.IS"]
    regimes = get_regimes()
    stock_rows, sens_rows, stab_rows, reg_rows = [], [], [], []
    for sym, fa in ctx.fits_a.items():
        fb = ctx.fits_b.get(sym)
        cols = factors_for(sub.get(sym), list(fp.X.columns))
        y = fp.returns[sym]
        oa = oos_r2(y, fp.X[cols])
        ob = oos_r2(y, fp.X[cols], market=mkt)
        stock_rows.append(
            {
                "symbol": sym,
                "r2_A": fa.r2,
                "adj_r2_A": fa.adj_r2,
                "r2_B": fb.r2 if fb else np.nan,
                "oos_r2_A": oa["oos_r2"],
                "oos_r2_B": ob["oos_r2"],
                "rolling_is_r2_A": oa["rolling_is_r2"],
                "n_weeks": fa.n,
                "n_test_weeks": oa["n_test_weeks"],
                "max_vif": max(fa.vif.values()) if fa.vif else np.nan,
                "max_vif_factor": max(fa.vif, key=fa.vif.get) if fa.vif else None,
            }
        )
        for c in fa.factors:
            sens_rows.append(
                {
                    "symbol": sym,
                    "factor": c,
                    "beta": fa.beta[c],
                    "p": fa.pval[c],
                    "resp_1sd_pct": fa.beta[c] * sd[c] * 100,
                    "vif": fa.vif.get(c),
                }
            )
        st = beta_stability(y, fp.X[cols], fa.beta)
        st.insert(0, "symbol", sym)
        stab_rows.append(st)
        rb = regime_betas(y, fp.X[cols], regimes, sym)
        if not rb.empty:
            rb.insert(0, "symbol", sym)
            rb["resp_1sd_pct"] = rb["beta"] * rb["factor"].map(sd) * 100
            reg_rows.append(rb)
    stocks = pd.DataFrame(stock_rows)
    sens = pd.DataFrame(sens_rows)
    stab = pd.concat(stab_rows, ignore_index=True)
    reg = pd.concat(reg_rows, ignore_index=True)

    # one row per (symbol, universe): TUPRS appears in both groups
    m = mem.drop_duplicates(["symbol", "universe"])[["symbol", "universe", "sub_sector", "overlap"]]
    stocks_u = m.merge(stocks, on="symbol")
    sens_u = m.merge(sens, on="symbol")

    # universe comparison, with and without overlapping names
    comp = []
    for sample in ("all", "no_overlap"):
        su = stocks_u if sample == "all" else stocks_u[~stocks_u["overlap"]]
        se = sens_u if sample == "all" else sens_u[~sens_u["overlap"]]
        b, e = su[su["universe"] == "BIST30"], su[su["universe"] == "Energy"]
        for col in ("r2_A", "r2_B", "oos_r2_A", "oos_r2_B", "max_vif"):
            comp.append(
                {
                    "sample": sample,
                    "metric": col,
                    "BIST30_mean": b[col].mean(),
                    "BIST30_median": b[col].median(),
                    "Energy_mean": e[col].mean(),
                    "Energy_median": e[col].median(),
                    "mw_p": _mw(b[col], e[col]),
                    "n_BIST30": len(b),
                    "n_Energy": len(e),
                }
            )
        for f, g in se.groupby("factor"):
            gb = g[g["universe"] == "BIST30"]["resp_1sd_pct"]
            ge = g[g["universe"] == "Energy"]["resp_1sd_pct"]
            comp.append(
                {
                    "sample": sample,
                    "metric": f"resp_1sd_pct:{f}",
                    "BIST30_mean": gb.mean(),
                    "BIST30_median": gb.median(),
                    "Energy_mean": ge.mean(),
                    "Energy_median": ge.median(),
                    "mw_p": _mw(gb, ge),
                    "n_BIST30": len(gb),
                    "n_Energy": len(ge),
                }
            )
    comp = pd.DataFrame(comp)

    # by sub-sector
    subs = stocks_u.assign(
        group=np.where(
            stocks_u["universe"] == "BIST30",
            "BIST30",
            "Energy:" + stocks_u["sub_sector"].fillna(""),
        )
    )
    by_sub = subs.groupby("group")[["r2_A", "r2_B", "oos_r2_A", "oos_r2_B", "max_vif"]].median()
    by_sub["n"] = subs.groupby("group").size()

    # regimes: median |response| and R² per universe
    reg_u = m.merge(reg, on="symbol")
    reg_sum = (
        reg_u.groupby(["universe", "regime", "factor"])["resp_1sd_pct"]
        .median()
        .unstack("factor")
        .reset_index()
    )
    reg_r2 = (
        reg_u.drop_duplicates(["symbol", "universe", "regime"])
        .groupby(["universe", "regime"])["r2"]
        .median()
        .rename("median_r2")
        .reset_index()
    )
    reg_sum = reg_sum.merge(reg_r2, on=["universe", "regime"])

    stab_u = m.merge(stab, on="symbol")
    stab_sum = stab_u.groupby(["universe", "factor"])[
        ["rolling_sd_resp_1sd_pct", "sign_agreement"]
    ].median()

    save_table(stocks_u, out, "e2_per_stock", "{:.3f}")
    save_table(sens_u, out, "e2_sensitivities", "{:.3f}")
    save_table(
        comp,
        out,
        "e2_universe_comparison",
        "{:.3f}",
        caption="E2: BIST30 vs Energy, with and without overlapping names",
    )
    save_table(by_sub.reset_index(), out, "e2_by_subsector", "{:.3f}")
    save_table(reg_sum, out, "e2_regime_sensitivities", "{:.2f}")
    save_table(stab_sum.reset_index(), out, "e2_beta_stability", "{:.3f}")
    plot_heatmap(sens, mem, out)
    plot_r2(stocks_u, out)
    mark_latest(out)
    return str(out)


def main() -> None:
    argparse.ArgumentParser(description="E2 factor model evaluation").parse_args()
    setup_logging("WARNING")
    print(run())


if __name__ == "__main__":
    main()
