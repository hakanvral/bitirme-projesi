"""Risk engine: from cleaned prices to a :class:`RiskReport` (CLAUDE.md §6.2).

Point-in-time: :func:`load_inputs` keeps only data dated on or before ``as_of`` (and CPI prints
released by ``as_of``), so a report "as of t" cannot see anything after t.

Steps for one stock
1. daily log returns in the requested basis from ``prices_clean`` (D-024, D-032);
2. fewer than ``min_history`` returns -> :class:`InsufficientHistoryError` (no report, D-031);
3. calibration window = last ``calibration_window`` returns;
4. fit every model; a model that fails is skipped and its reason recorded (D-035);
5. critic: simulate each model, score against history, select (D-034);
6. forward Monte Carlo of the selected model -> VaR/CVaR, P(loss>10%), drawdowns, fan chart;
7. realised volatility and beta to XU100 on the window; EVT on the full history (D-036).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from pusula.config import RiskCfg
from pusula.data.panel import trading_calendar
from pusula.data.store import Store
from pusula.features.returns import Basis, log_returns, session_prices, to_basis
from pusula.risk import critic as critic_mod
from pusula.risk import metrics as m
from pusula.risk.models import ModelFitError, default_models
from pusula.risk.schemas import ModelResult, RiskReport, VarBlock
from pusula.risk.simulate import cumulative, rng_for

MARKET = "XU100.IS"
TRADING_DAYS = 252


class InsufficientHistoryError(ValueError):
    """Fewer valid daily returns than ``min_history`` at as_of: no report."""


@dataclass
class RiskInputs:
    as_of: date
    sessions: pd.DatetimeIndex
    prices: pd.DataFrame  # cleaned long table, dates <= as_of
    usdtry: pd.Series | None
    cpi_monthly: pd.DataFrame | None


def load_inputs(store: Store, as_of: date) -> RiskInputs:
    """Everything the engine needs, cut at ``as_of`` (point-in-time)."""
    ts = pd.Timestamp(as_of)
    prices = store.prices(end=as_of)  # prices_clean (corrections applied)
    sessions = trading_calendar(prices)
    sessions = sessions[sessions <= ts]
    macro = store.macro(["usdtry", "cpi"])
    fx = macro[(macro["series"] == "usdtry") & (macro["date"] <= ts)]
    usdtry = fx.set_index("date")["value"].sort_index() if not fx.empty else None
    cpi = macro[macro["series"] == "cpi"][["date", "value", "release_date"]]
    return RiskInputs(as_of, sessions, prices, usdtry, cpi if not cpi.empty else None)


def daily_returns(inp: RiskInputs, symbol: str, basis: Basis, max_gap: int) -> pd.Series:
    px = session_prices(inp.prices, symbol, inp.sessions)
    px = to_basis(px, basis, inp.usdtry, inp.cpi_monthly, inp.as_of)
    return log_returns(px, max_gap=max_gap)


def _var_block(log_ret: np.ndarray) -> VarBlock:
    v95, c95 = m.var_cvar(log_ret, 0.95)
    v99, c99 = m.var_cvar(log_ret, 0.99)
    return VarBlock(var95=v95, cvar95=c95, var99=v99, cvar99=c99)


def _dd_summary(dd: np.ndarray) -> dict[str, float]:
    return {
        "mean": float(dd.mean()),
        "p50": float(np.quantile(dd, 0.5)),
        "p75": float(np.quantile(dd, 0.75)),
        "p95": float(np.quantile(dd, 0.95)),
    }


def compute_risk_report(
    inp: RiskInputs, symbol: str, basis: Basis, cfg: RiskCfg, seed: int
) -> RiskReport:
    t0 = time.perf_counter()
    full = daily_returns(inp, symbol, basis, cfg.max_gap_sessions)
    if len(full) < cfg.min_history:
        raise InsufficientHistoryError(
            f"{symbol}: {len(full)} daily returns at {inp.as_of} (< {cfg.min_history})"
        )
    window = full.iloc[-cfg.calibration_window :]
    r = window.to_numpy()
    warnings: list[str] = []
    if len(window) < cfg.calibration_window:
        warnings.append(f"short_history:{len(window)}")

    results: list[ModelResult] = []
    critic_sims: dict[str, np.ndarray] = {}
    forward: dict[str, np.ndarray] = {}
    for i, model in enumerate(default_models(cfg.merton_threshold, cfg.merton_min_jumps)):
        ts = time.perf_counter()
        try:
            model.fit(r)
            critic_sims[model.name] = model.simulate(
                cfg.critic_paths,
                len(r),
                rng_for(seed, symbol, inp.as_of, i, "critic"),
                start="unconditional",
            )
            fwd = model.simulate(
                cfg.n_paths, cfg.horizon_days, rng_for(seed, symbol, inp.as_of, i, "forward")
            )
            if not np.all(np.isfinite(fwd)):
                raise ModelFitError("simulation produced non-finite values")
            forward[model.name] = fwd
            v99, c99 = m.var_cvar(fwd[:, 0], 0.99)
            results.append(
                ModelResult(
                    name=model.name,
                    fitted=True,
                    params=model.params,
                    var99_1d=v99,
                    cvar99_1d=c99,
                    seconds=time.perf_counter() - ts,
                )
            )
        except ModelFitError as exc:
            critic_sims.pop(model.name, None)
            results.append(
                ModelResult(
                    name=model.name,
                    fitted=False,
                    failure_reason=str(exc),
                    seconds=time.perf_counter() - ts,
                )
            )
    if not forward:
        raise ModelFitError(f"{symbol}: no model could be calibrated")

    table = critic_mod.critic_table(r, critic_sims)
    selected, by_scheme, eq_scores = critic_mod.select(table)
    for res in results:
        if res.fitted:
            res.critic = {k: float(v) for k, v in table.loc[res.name].items()}
            res.score = float(eq_scores[res.name])

    paths = forward[selected]
    dd1, dd3 = m.max_drawdowns(paths[:, :21]), m.max_drawdowns(paths)
    mkt = daily_returns(inp, MARKET, "TRY", cfg.max_gap_sessions)
    stock_try = full if basis == "TRY" else daily_returns(inp, symbol, "TRY", cfg.max_gap_sessions)
    beta, beta_n = m.beta_ols(stock_try.loc[window.index.min() :], mkt)

    if len(full) >= cfg.evt.min_history:
        evt = m.evt_tail(
            full.to_numpy(), cfg.evt.threshold_quantile, cfg.evt.run_length, cfg.evt.min_clusters
        )
    else:
        evt = {
            "fitted": False,
            "n_obs": len(full),
            "reason": f"history too short for EVT ({len(full)} < {cfg.evt.min_history})",
        }

    return RiskReport(
        ticker=symbol,
        as_of=inp.as_of,
        basis=basis,
        window_start=window.index.min().date(),
        window_end=window.index.max().date(),
        n_window=len(window),
        n_history=len(full),
        seed=seed,
        models=results,
        selected_model=selected,
        selection_by_scheme=by_scheme,
        selection_stable=len({by_scheme[k] for k in ("equal", "tail_heavy", "moment_heavy")}) == 1,
        horizon_1d=_var_block(paths[:, 0]),
        horizon_10d=_var_block(cumulative(paths, 10)),
        p_loss_10pct_1m=m.prob_loss_beyond(cumulative(paths, 21), 0.10),
        drawdown_1m=_dd_summary(dd1),
        drawdown_3m=_dd_summary(dd3),
        drawdown_3m_hist=m.histogram(dd3, bins=50),
        sim_1d_hist=m.histogram(paths[:, 0], bins=60),
        fan_chart=m.fan_chart(paths),
        vol_ann_realized=float(r.std(ddof=1) * np.sqrt(TRADING_DAYS)),
        vol_ann_model=float(paths[:, 0].std(ddof=1) * np.sqrt(TRADING_DAYS)),
        beta_xu100=None if np.isnan(beta) else beta,
        beta_n=beta_n,
        evt=evt,
        warnings=warnings,
        seconds_total=time.perf_counter() - t0,
    )
