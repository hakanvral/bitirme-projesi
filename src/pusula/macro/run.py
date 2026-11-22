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
    res_rows, summ = [], []
    for sc in load_presets():
        spec = to_factor_shocks(sc.shocks, eng.factors, pt)
        for hz in HORIZONS:
            for mode in MODES:
                r = eng.run(spec, hz, mode)
                st = r["stocks"]
                if "d_exp_ret" not in st:
                    continue  # every shocked factor missing (e.g. CDS without data)
                st = st.assign(scenario=sc.id, horizon=hz, mode=mode, basis="TRY")
                res_rows.append(st)
                summ.append(
                    universe_summary(st).assign(
                        scenario=sc.id, horizon=hz, mode=mode, ignored=",".join(spec.ignored)
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
