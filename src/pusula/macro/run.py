"""Phase 3 batch run: factor models + pass-through + all preset scenarios for one date.

    uv run python -m pusula.macro.run                       # latest session
    uv run python -m pusula.macro.run --as-of 2026-11-20

Writes DuckDB tables ``factor_betas`` and ``scenario_results`` and the folder
``results/macro/<as_of>_<timestamp>/`` (betas, rolling betas, regime betas, VIF, pass-through,
scenario results, universe summaries, timings, copies of the configs).
"""

from __future__ import annotations

import argparse
import logging
import shutil
import time
from datetime import UTC, date, datetime

import pandas as pd

from pusula.config import CONFIG_DIR, get_regimes, get_settings
from pusula.data.store import Store
from pusula.logging_setup import setup_logging
from pusula.macro.context import build_context, current_passthrough, make_engine
from pusula.macro.factor_model import beta_table, regime_betas, rolling_betas
from pusula.macro.passthrough import summary_table
from pusula.macro.scenarios import HORIZONS, load_presets, to_factor_shocks, universe_summary

log = logging.getLogger(__name__)
MODES = ("propagated", "isolated")


def run(as_of: date, store: Store | None = None) -> dict:
    s = get_settings()
    store = store or Store(s.paths.db_path, s.paths.raw_dir)
    run_at = datetime.now(UTC).replace(tzinfo=None)
    t0 = time.perf_counter()
    ctx = build_context(store, as_of)
    t_fit = time.perf_counter() - t0
    out = s.paths.results_dir / "macro" / f"{as_of:%Y%m%d}_{run_at:%Y%m%d_%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    for f in ("settings.yaml", "scenarios.yaml", "regimes.yaml"):
        shutil.copy(CONFIG_DIR / f, out / f)

    bt = beta_table(list(ctx.fits_a.values()) + list(ctx.fits_b.values()))
    bt.to_csv(out / "factor_betas.csv", index=False)
    store.replace_rows("factor_betas", bt.assign(as_of=as_of, run_at=run_at), "as_of = ?", [as_of])
    roll, reg = [], []
    for sym, f in ctx.fits_a.items():
        X = ctx.fp.X[f.factors]
        rb = rolling_betas(ctx.fp.returns[sym], X, step=4)
        roll.append(rb.assign(ticker=sym).reset_index())
        reg.append(regime_betas(ctx.fp.returns[sym], X, get_regimes(), sym).assign(ticker=sym))
    pd.concat(roll).to_csv(out / "rolling_betas.csv", index=False)
    pd.concat(reg).to_csv(out / "regime_betas.csv", index=False)
    summary_table(ctx.passthrough).to_csv(out / "passthrough.csv", index=False)
    ctx.pt_events.to_csv(out / "passthrough_events.csv", index=False)

    t1 = time.perf_counter()
    eng = make_engine(ctx)
    pt = current_passthrough(ctx)
    # TRY and USD always; REAL when a released inflation expectation exists (D-051)
    bases = ["TRY", "USD"] + (["REAL"] if ctx.infl_exp_annual is not None else [])
    res_rows, summ = [], []
    for sc in load_presets():
        spec = to_factor_shocks(sc.shocks, eng.factors, pt)
        for hz in HORIZONS:
            for mode in MODES:
                for basis in bases:
                    r = eng.run(spec, hz, mode, basis)
                    st = r["stocks"]
                    if "d_exp_ret" not in st:
                        continue  # every shocked factor missing (e.g. CDS without data)
                    st = st.assign(
                        scenario=sc.id,
                        horizon=hz,
                        mode=mode,
                        basis=basis,
                        cov_used=r["cov_source"],
                        max_shock_z=max(
                            (abs(v) for v in r["shock_z_regime"].values()), default=0.0
                        ),
                    )
                    res_rows.append(st)
                    summ.append(
                        universe_summary(st).assign(
                            scenario=sc.id,
                            horizon=hz,
                            mode=mode,
                            basis=basis,
                            ignored=",".join(spec.ignored),
                            cov_used=r["cov_source"],
                            max_shock_z=st["max_shock_z"].iloc[0],
                        )
                    )
    t_scen = time.perf_counter() - t1
    res = pd.concat(res_rows, ignore_index=True)
    cols = [
        "scenario",
        "horizon",
        "mode",
        "basis",
        "symbol",
        "universe",
        "sub_sector",
        "overlap",
        "base_exp_ret",
        "scen_exp_ret",
        "d_exp_ret",
        "d_var99",
        "d_cvar99",
        "d_p_loss",
        "rank_change",
        "scen_exp_ret_low",
        "scen_exp_ret_high",
    ]
    res = res.reindex(columns=cols)
    res.to_csv(out / "scenario_results.csv", index=False)
    store.replace_rows(
        "scenario_results", res.assign(as_of=as_of, run_at=run_at), "as_of = ?", [as_of]
    )
    pd.concat(summ).to_csv(out / "universe_summary.csv", index=False)
    pd.DataFrame(
        [
            {
                "fit_seconds": t_fit,
                "scenario_seconds": t_scen,
                "n_scenario_runs": len(summ),
                "factors": ",".join(eng.factors),
                "missing": ",".join(ctx.fp.missing),
                "cov_source": eng.cov_source,
                "rate_source": ctx.fp.rate_source,
            }
        ]
    ).to_csv(out / "run_info.csv", index=False)
    if ctx.fp.rate_source == "tr_2y":
        _compare_rate_source(store, as_of, ctx, out)
    log.info(
        "Macro run %s: %d fits, %d scenario runs in %.1fs (fits %.1fs) -> %s",
        as_of,
        len(ctx.fits_a),
        len(summ),
        t_scen,
        t_fit,
        out,
    )
    return {"out": out, "t_fit": t_fit, "t_scen": t_scen, "ctx": ctx}


RATE_SCENARIOS = ("faiz_indirimi", "sert_faiz_indirimi", "faiz_artirimi", "stagflasyon")


def _fit_summary(ctx) -> pd.DataFrame:
    rows = []
    for sym, f in ctx.fits_a.items():
        u = ctx.members[ctx.members["symbol"] == sym]["universe"].iloc[0]
        rows.append(
            {
                "symbol": sym,
                "universe": u,
                "r2_a": f.r2,
                "r2_b": ctx.fits_b[sym].r2,
                "beta_rate": f.beta.get("rate"),
                "p_rate": f.pval.get("rate"),
            }
        )
    return pd.DataFrame(rows)


def _compare_rate_source(store: Store, as_of: date, ctx, out) -> None:
    """Robustness (D-052): the same run with TLREF instead of the 2Y yield as the rate factor."""
    alt = build_context(store, as_of, exclude_sources={"tr_2y"})
    rows = []
    for label, c in (("tr_2y", ctx), ("tlref", alt)):
        fs = _fit_summary(c)
        eng = make_engine(c)
        pt = current_passthrough(c)
        for sc in load_presets():
            if sc.id not in RATE_SCENARIOS:
                continue
            spec = to_factor_shocks(sc.shocks, eng.factors, pt)
            us = universe_summary(eng.run(spec, "3m", "propagated", "TRY")["stocks"])
            for r in us[us["sample"] == "all"].itertuples():
                rows.append(
                    {
                        "rate_source": label,
                        "scenario": sc.id,
                        "universe": r.universe,
                        "d_exp_ret": r.d_exp_ret,
                        "median_d_exp_ret": r.median_d_exp_ret,
                        "rate_shock_pp": spec.factor_shocks.get("rate"),
                        "passthrough_beta": pt.beta if pt else None,
                    }
                )
        for u, g in fs.groupby("universe"):
            rows.append(
                {
                    "rate_source": label,
                    "scenario": "_fit",
                    "universe": u,
                    "r2_a": g["r2_a"].mean(),
                    "r2_b": g["r2_b"].mean(),
                    "share_rate_sig": (g["p_rate"] < 0.05).mean(),
                }
            )
    pd.DataFrame(rows).to_csv(out / "rate_source_comparison.csv", index=False)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", type=date.fromisoformat, default=None)
    a = p.parse_args(argv)
    setup_logging()
    s = get_settings()
    st = Store(s.paths.db_path, s.paths.raw_dir)
    last = st.query("SELECT max(date) AS d FROM prices WHERE ticker = 'XU100.IS'")["d"].iloc[0]
    run(a.as_of or pd.Timestamp(last).date(), st)


if __name__ == "__main__":
    main()
