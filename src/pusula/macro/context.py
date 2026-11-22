"""Builds everything Phase 3 needs for one date (used by the pages and the CLI)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from pusula.config import get_regimes, get_settings
from pusula.data.adapters.manual_csv import ManualFileError, read_ppk
from pusula.data.store import Store
from pusula.macro.factor_model import FactorFit, InsufficientDataError, factors_for, fit_stock
from pusula.macro.factors import FactorPanel, build_factor_panel
from pusula.macro.passthrough import PassThrough, estimate
from pusula.macro.scenarios import Engine
from pusula.universe.members import universe_members


@dataclass
class MacroContext:
    as_of: date
    fp: FactorPanel
    members: pd.DataFrame
    fits_a: dict[str, FactorFit]
    fits_b: dict[str, FactorFit]
    skipped: dict[str, str]
    pt_events: pd.DataFrame
    passthrough: dict[str, PassThrough]
    current_regime: str | None
    warnings: list[str] = field(default_factory=list)
    infl_exp_annual: float | None = None  # latest released 12-month CPI expectation (%)


def build_context(
    store: Store, as_of: date, exclude_sources: set[str] | None = None
) -> MacroContext:
    s = get_settings()
    regimes = get_regimes()
    mem = universe_members(as_of)
    syms = sorted(mem["symbol"].unique())
    fp = build_factor_panel(
        store.prices(end=as_of), store.macro(), syms, as_of, exclude_sources=exclude_sources
    )
    avail = list(fp.X.columns)
    sub = mem.drop_duplicates("symbol").set_index("symbol")["sub_sector"]
    fits_a, fits_b, skipped = {}, {}, {}
    mkt = fp.returns["XU100.IS"]
    for sym in syms:
        if sym not in fp.returns:
            skipped[sym] = "no prices"
            continue
        cols = factors_for(sub.get(sym), avail)
        try:
            fits_a[sym] = fit_stock(fp.returns[sym], fp.X[cols], sym, "A")
            fits_b[sym] = fit_stock(
                fp.returns[sym], fp.X[cols], sym, "B", market=mkt, with_extras=False
            )
        except InsufficientDataError as exc:
            skipped[sym] = str(exc)
    warnings = [f"missing:{m}" for m in fp.missing]
    try:
        ppk = read_ppk(s.paths.manual_dir / "ppk_decisions.csv")
        ppk = ppk[ppk["meeting_date"] <= pd.Timestamp(as_of)]
        ev, pt = estimate(ppk, fp.daily_rate, as_of, regimes)
    except (ManualFileError, TypeError, AttributeError) as exc:
        ev, pt = pd.DataFrame(), {}
        warnings.append(f"passthrough:{exc}")
    exp = store.macro(["cpi_exp_12m"])
    exp = exp[exp["release_date"] <= pd.Timestamp(as_of)].sort_values("date")
    infl = float(exp["value"].iloc[-1]) if not exp.empty else None
    return MacroContext(
        as_of,
        fp,
        mem,
        fits_a,
        fits_b,
        skipped,
        ev,
        pt,
        regimes.regime_of(as_of),
        warnings,
        infl_exp_annual=infl,
    )


def make_engine(ctx: MacroContext, cov_regime: str = "current", n_paths: int = 10_000) -> Engine:
    """Engine with the macro covariance from ``cov_regime`` ('current', 'full' or a regime id).
    A regime with too few weeks falls back to the full sample (recorded in ``cov_source``)."""
    regimes = get_regimes()
    rid = ctx.current_regime if cov_regime == "current" else cov_regime
    members = ctx.members[ctx.members["symbol"].isin(ctx.fits_a)]
    seed = get_settings().project.random_seed
    if rid and rid != "full":
        rg = next(r for r in regimes.regimes if r.id == rid)
        try:
            return Engine.from_weekly(
                ctx.fp.X,
                ctx.fits_a,
                members,
                rg.start,
                rg.end,
                cov_source=rid,
                n_paths=n_paths,
                seed=seed,
                infl_exp_annual=ctx.infl_exp_annual,
            )
        except ValueError:
            pass
    return Engine.from_weekly(
        ctx.fp.X,
        ctx.fits_a,
        members,
        cov_source="full",
        n_paths=n_paths,
        seed=seed,
        infl_exp_annual=ctx.infl_exp_annual,
    )


def current_passthrough(ctx: MacroContext) -> PassThrough | None:
    return ctx.passthrough.get(ctx.current_regime or "", ctx.passthrough.get("pooled"))
