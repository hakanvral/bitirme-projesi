"""Macro factor model (CLAUDE.md §6.3):  r_i,t = alpha_i + sum_k beta_i,k * df_k,t + e_i,t.

Plain language
* A **beta** says how much a stock's weekly return moves when a factor moves by one unit, the
  other factors held fixed. Example: beta_usdtry = 0.5 means a 1% weekly USD/TRY rise goes with
  a +0.5% stock return on average.
* **Newey-West (HAC) standard errors** stay valid when the errors are autocorrelated or their
  variance changes over time, both common in weekly market data.
* **VIF** (variance inflation factor) measures how much a factor overlaps with the others.
  VIF > 5-10 means its individual beta is unreliable, although the combined effect is fine.
* **Model A**: macro factors only. **Model B**: adds the part of the XU100 return that the macro
  factors do not explain (the "market residual"). Because that residual is uncorrelated with the
  macro factors in the sample, Model B's macro betas equal Model A's; B only explains more of the
  remaining variance (higher R²).
* **Ridge** shrinks betas towards zero to tame overlapping factors. It is only a robustness check.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor

from pusula.macro.factors import ELECTRICITY_ONLY

MIN_WEEKS = 104
ROLL_WEEKS = 104


@dataclass
class FactorFit:
    ticker: str
    variant: str  # "A" | "B"
    factors: list[str]
    alpha: float
    beta: dict[str, float]
    se: dict[str, float]
    tstat: dict[str, float]
    pval: dict[str, float]
    r2: float
    adj_r2: float
    n: int
    hac_lags: int
    start: pd.Timestamp
    end: pd.Timestamp
    resid: pd.Series = field(repr=False)
    vif: dict[str, float] = field(default_factory=dict)
    ridge_beta: dict[str, float] = field(default_factory=dict)
    ridge_lambda: float | None = None


class InsufficientDataError(ValueError):
    pass


def newey_west_lags(n: int) -> int:
    """Standard rule of thumb: floor(4 (n/100)^(2/9))."""
    return int(np.floor(4 * (n / 100) ** (2 / 9)))


def factors_for(sub_sector: str | None, available: list[str]) -> list[str]:
    """PTF is used only for electricity names (CLAUDE.md §6.3)."""
    return [f for f in available if f not in ELECTRICITY_ONLY or sub_sector == "electricity"]


def vif(X: pd.DataFrame) -> dict[str, float]:
    Xc = sm.add_constant(X.to_numpy(), has_constant="add")
    return {c: float(variance_inflation_factor(Xc, i + 1)) for i, c in enumerate(X.columns)}


def ridge_gcv(X: pd.DataFrame, y: pd.Series) -> tuple[dict[str, float], float]:
    """Ridge on standardised X with the penalty chosen by generalised cross-validation.
    Returns betas in original units and the chosen lambda."""
    Xs = (X - X.mean()) / X.std(ddof=0)
    yc = (y - y.mean()).to_numpy()
    U, s, Vt = np.linalg.svd(Xs.to_numpy(), full_matrices=False)
    n = len(yc)
    best = (np.inf, None, None)
    for lam in np.logspace(-3, 4, 60):
        d = s / (s**2 + lam)
        b = Vt.T @ (d * (U.T @ yc))
        dof = np.sum(s**2 / (s**2 + lam))
        resid = yc - Xs.to_numpy() @ b
        gcv = (resid @ resid / n) / (1 - dof / n) ** 2
        if gcv < best[0]:
            best = (gcv, lam, b)
    _, lam, b = best
    return {
        c: float(v) for c, v in zip(X.columns, b / X.std(ddof=0).to_numpy(), strict=True)
    }, float(lam)


def fit_ols_hac(
    y: pd.Series, X: pd.DataFrame, ticker: str, variant: str, with_extras: bool = True
) -> FactorFit:
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    if len(d) < MIN_WEEKS:
        raise InsufficientDataError(f"{ticker}: {len(d)} complete weeks (< {MIN_WEEKS})")
    Xd = d[X.columns]
    lags = newey_west_lags(len(d))
    res = sm.OLS(d["y"], sm.add_constant(Xd)).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    cols = list(X.columns)
    fit = FactorFit(
        ticker=ticker,
        variant=variant,
        factors=cols,
        alpha=float(res.params["const"]),
        beta={c: float(res.params[c]) for c in cols},
        se={c: float(res.bse[c]) for c in cols},
        tstat={c: float(res.tvalues[c]) for c in cols},
        pval={c: float(res.pvalues[c]) for c in cols},
        r2=float(res.rsquared),
        adj_r2=float(res.rsquared_adj),
        n=len(d),
        hac_lags=lags,
        start=d.index.min(),
        end=d.index.max(),
        resid=res.resid,
    )
    if with_extras:
        fit.vif = vif(Xd)
        fit.ridge_beta, fit.ridge_lambda = ridge_gcv(Xd, d["y"])
    return fit


def market_residual(market: pd.Series, X: pd.DataFrame) -> pd.Series:
    """XU100 weekly return orthogonalised on the macro factors (Model B's extra factor)."""
    d = pd.concat([market.rename("m"), X], axis=1).dropna()
    res = sm.OLS(d["m"], sm.add_constant(d[X.columns])).fit()
    return res.resid.rename("market_resid")


def fit_stock(
    returns: pd.Series,
    X: pd.DataFrame,
    ticker: str,
    variant: str = "A",
    market: pd.Series | None = None,
    with_extras: bool = True,
) -> FactorFit:
    if variant == "B":
        if market is None:
            raise ValueError("Model B needs the XU100 weekly returns")
        X = pd.concat([X, market_residual(market, X)], axis=1)
    return fit_ols_hac(returns, X, ticker, variant, with_extras)


def rolling_betas(
    y: pd.Series, X: pd.DataFrame, window: int = ROLL_WEEKS, step: int = 1
) -> pd.DataFrame:
    """OLS betas on rolling windows (index = window end). Plain least squares, no HAC."""
    d = pd.concat([y.rename("y"), X], axis=1).dropna()
    A = np.column_stack([np.ones(len(d)), d[X.columns].to_numpy()])
    yy = d["y"].to_numpy()
    rows, idx = [], []
    for end in range(window, len(d) + 1, step):
        coef, *_ = np.linalg.lstsq(A[end - window : end], yy[end - window : end], rcond=None)
        rows.append(coef[1:])
        idx.append(d.index[end - 1])
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx, name="date"), columns=X.columns)


def regime_betas(
    y: pd.Series, X: pd.DataFrame, regimes, ticker: str, min_weeks: int = 52
) -> pd.DataFrame:
    """Model A fitted separately in each regime with at least ``min_weeks`` complete weeks."""
    out = []
    for rg in regimes.regimes:
        lo = pd.Timestamp(rg.start)
        hi = pd.Timestamp(rg.end) if rg.end else pd.Timestamp.max
        sel = (X.index >= lo) & (X.index < hi)
        try:
            f = fit_ols_hac(y[sel], X[sel], ticker, "A", with_extras=False)
        except (InsufficientDataError, ValueError):
            continue
        except np.linalg.LinAlgError:
            continue
        if f.n < min_weeks:
            continue
        for c in f.factors:
            out.append(
                {
                    "regime": rg.id,
                    "factor": c,
                    "beta": f.beta[c],
                    "se": f.se[c],
                    "p": f.pval[c],
                    "n": f.n,
                    "r2": f.r2,
                }
            )
    return pd.DataFrame(out)


def beta_table(fits: list[FactorFit]) -> pd.DataFrame:
    """Long table: one row per (ticker, variant, factor)."""
    rows = []
    for f in fits:
        for c in f.factors:
            rows.append(
                {
                    "ticker": f.ticker,
                    "variant": f.variant,
                    "factor": c,
                    "beta": f.beta[c],
                    "se": f.se[c],
                    "t": f.tstat[c],
                    "p": f.pval[c],
                    "vif": f.vif.get(c),
                    "ridge_beta": f.ridge_beta.get(c),
                    "r2": f.r2,
                    "adj_r2": f.adj_r2,
                    "n": f.n,
                }
            )
    return pd.DataFrame(rows)
