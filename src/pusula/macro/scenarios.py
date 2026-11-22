"""Scenario engine (CLAUDE.md §6.3, D-043 … D-045).

1. **Macro distribution.** Weekly factor changes in the chosen regime (default: the regime of
   ``as_of``) give a mean vector mu and covariance Sigma. Over h weeks the cumulative change is
   taken as Normal(h mu, h Sigma) (weekly changes treated as independent).
2. **Shock.** The user fixes the cumulative change of some factors (x1). Two modes:
   * ``isolated``: the other factors are drawn from their own distribution, as if the shock
     carried no information about them (mean = their expected change);
   * ``propagated`` (default): the other factors follow their **conditional** distribution
     given the shock: mean mu2 + S21 S11^-1 (x1 - mu1), covariance S22 - S21 S11^-1 S12.
     Plain language: if USD/TRY and the rate usually move together, a rate shock also shifts the
     expected USD/TRY move.
3. **Stocks.** For each stock, Model A gives R = h alpha + X beta + (sum of h weekly residuals
   bootstrapped from its own history). The same macro draws are used for every stock, so
   cross-stock comparisons are consistent.
4. **Comparison with the baseline** (no shock) using the same random numbers (common random
   numbers), so the differences come from the shock, not from simulation noise: change in
   expected return, VaR/CVaR, probability of a loss, and the stock's rank in its universe.

Returns are nominal TRY log returns; the USD view subtracts the simulated USD/TRY change. A real
(CPI) view is not available because CPI is not a factor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from pusula.config import load_yaml
from pusula.macro.factor_model import FactorFit
from pusula.macro.passthrough import PassThrough

HORIZONS = {"1m": 4, "3m": 13}
SHOCK_KEYS = {
    # input key -> (factor, conversion to factor units)
    "market_rate_bp": ("rate", lambda v: v / 100),
    "usdtry_pct": ("usdtry", lambda v: np.log1p(v / 100)),
    "brent_pct": ("brent", lambda v: np.log1p(v / 100)),
    "ttf_pct": ("ttf", lambda v: np.log1p(v / 100)),
    "ptf_pct": ("ptf", lambda v: np.log1p(v / 100)),
    "cds_bp": ("cds", lambda v: float(v)),
    "vix_pts": ("vix", lambda v: float(v)),
    "us10y_bp": ("us10y", lambda v: v / 100),
}


@dataclass
class Scenario:
    id: str
    name_tr: str
    shocks: dict[str, float]


def load_presets() -> list[Scenario]:
    return [Scenario(**s) for s in load_yaml("scenarios.yaml")["scenarios"]]


@dataclass
class ShockSpec:
    """Shocks in factor units (cumulative over the horizon), plus the rate band if the rate shock
    came from a policy-rate change."""

    factor_shocks: dict[str, float]
    rate_band: tuple[float, float, float] | None = None  # (low, central, high) in pp
    ignored: list[str] = field(default_factory=list)  # shocked factors that are not available
    policy_bp: float | None = None


def to_factor_shocks(
    shocks: dict[str, float], available: list[str], pt: PassThrough | None
) -> ShockSpec:
    vals: dict[str, float] = {}
    band = None
    ignored: list[str] = []
    pol = shocks.get("policy_rate_bp")
    if pol and "market_rate_bp" in shocks:
        raise ValueError("Give the rate shock either as policy_rate_bp or market_rate_bp, not both")
    for k, v in shocks.items():
        if not v:
            continue
        if k == "policy_rate_bp":
            if pt is None or not np.isfinite(pt.beta):
                ignored.append("rate (no pass-through estimate)")
                continue
            band = pt.convert(v)
            fac, val = "rate", band[1]
        else:
            fac, conv = SHOCK_KEYS[k]
            val = conv(v)
        if fac not in available:
            ignored.append(fac)
            continue
        vals[fac] = float(val)
    return ShockSpec(vals, band, ignored, pol)


def conditional_gaussian(
    mu: np.ndarray, cov: np.ndarray, idx1: list[int], x1: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Mean and covariance of X2 | X1 = x1 for X ~ N(mu, cov). idx2 = all other indices."""
    idx2 = [i for i in range(len(mu)) if i not in idx1]
    s11 = cov[np.ix_(idx1, idx1)]
    s21 = cov[np.ix_(idx2, idx1)]
    s22 = cov[np.ix_(idx2, idx2)]
    k = s21 @ np.linalg.pinv(s11)
    return mu[idx2] + k @ (x1 - mu[idx1]), s22 - k @ s21.T


def _chol(c: np.ndarray) -> np.ndarray:
    c = (c + c.T) / 2
    w, v = np.linalg.eigh(c)
    return v @ np.diag(np.sqrt(np.clip(w, 0, None)))  # works for semi-definite matrices


@dataclass
class Engine:
    """Everything needed to simulate scenarios for a set of stocks at one date."""

    factors: list[str]
    mu_w: np.ndarray
    cov_w: np.ndarray
    fits: dict[str, FactorFit]
    members: pd.DataFrame  # symbol, ticker, universe, sub_sector, in_bist30
    cov_source: str
    n_paths: int = 10_000
    seed: int = 42

    @classmethod
    def from_weekly(
        cls,
        X: pd.DataFrame,
        fits: dict[str, FactorFit],
        members: pd.DataFrame,
        start=None,
        end=None,
        cov_source: str = "full",
        **kw,
    ) -> Engine:
        sub = X.dropna()
        if start is not None:
            sub = sub[sub.index >= pd.Timestamp(start)]
        if end is not None:
            sub = sub[sub.index < pd.Timestamp(end)]
        if len(sub) < 2 * len(X.columns):
            raise ValueError(f"Too few weeks ({len(sub)}) to estimate the macro covariance")
        return cls(
            list(X.columns),
            sub.mean().to_numpy(),
            np.cov(sub.to_numpy().T),
            fits,
            members,
            cov_source,
            **kw,
        )

    # --------------------------------------------------------------------- draws
    def _random(self, h: int):
        rng = np.random.default_rng(np.random.SeedSequence([self.seed, h]))
        z = rng.standard_normal((self.n_paths, len(self.factors)))
        idx = {
            s: rng.integers(0, len(f.resid), size=(self.n_paths, h))
            for s, f in sorted(self.fits.items())
        }
        return z, idx

    def macro_draws(
        self, h: int, shock: dict[str, float] | None, mode: str, z: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """(n_paths, K) cumulative factor changes and their mean vector."""
        mu, cov = h * self.mu_w, h * self.cov_w
        if not shock:
            return mu + z @ _chol(cov).T, mu
        i1 = [self.factors.index(f) for f in shock]
        x1 = np.array([shock[f] for f in shock])
        i2 = [i for i in range(len(mu)) if i not in i1]
        if mode == "propagated":
            m2, c2 = conditional_gaussian(mu, cov, i1, x1)
        elif mode == "isolated":
            m2, c2 = mu[i2], cov[np.ix_(i2, i2)]
        else:
            raise ValueError("mode must be 'isolated' or 'propagated'")
        X = np.empty((self.n_paths, len(mu)))
        X[:, i1] = x1
        if i2:
            X[:, i2] = m2 + z[:, i2] @ _chol(c2).T
        mean = np.empty(len(mu))
        mean[i1], mean[i2] = x1, m2
        return X, mean

    def stock_returns(self, symbol: str, X: np.ndarray, h: int, idx: np.ndarray) -> np.ndarray:
        f = self.fits[symbol]
        beta = np.array([f.beta.get(c, 0.0) for c in self.factors])
        resid = f.resid.to_numpy()
        return h * f.alpha + X @ beta + resid[idx].sum(axis=1)

    # --------------------------------------------------------------------- run
    def run(
        self,
        shock: ShockSpec | None,
        horizon: str = "3m",
        mode: str = "propagated",
        basis: str = "TRY",
    ) -> dict:
        h = HORIZONS[horizon]
        z, idx = self._random(h)
        Xb, mean_b = self.macro_draws(h, None, mode, z)
        variants = {"central": shock.factor_shocks if shock else None}
        if shock and shock.rate_band:
            for name, val in (("low", shock.rate_band[0]), ("high", shock.rate_band[2])):
                variants[name] = {**shock.factor_shocks, "rate": val}
        draws = {k: self.macro_draws(h, v, mode, z) for k, v in variants.items() if v}
        rows = []
        for sym in self.fits:
            Rb = self.stock_returns(sym, Xb, h, idx[sym])
            if basis == "USD":
                Rb = Rb - Xb[:, self.factors.index("usdtry")]
            base = _stats(Rb)
            row = {"symbol": sym, **{f"base_{k}": v for k, v in base.items()}}
            for name, (Xs, _) in draws.items():
                Rs = self.stock_returns(sym, Xs, h, idx[sym])
                if basis == "USD":
                    Rs = Rs - Xs[:, self.factors.index("usdtry")]
                st = _stats(Rs)
                if name == "central":
                    row.update({f"scen_{k}": v for k, v in st.items()})
                else:
                    row[f"scen_exp_ret_{name}"] = st["exp_ret"]
            rows.append(row)
        df = pd.DataFrame(rows).merge(self.members, on="symbol", how="left")
        if shock and shock.factor_shocks:
            for k in ("exp_ret", "var99", "cvar99", "var95", "p_loss", "p_loss10"):
                df[f"d_{k}"] = df[f"scen_{k}"] - df[f"base_{k}"]
            for _, g in df.groupby("universe"):
                df.loc[g.index, "rank_base"] = g["base_exp_ret"].rank(ascending=False)
                df.loc[g.index, "rank_scen"] = g["scen_exp_ret"].rank(ascending=False)
            df["rank_change"] = df["rank_base"] - df["rank_scen"]  # > 0: moved up
        implied = pd.DataFrame(
            {
                "factor": self.factors,
                "baseline_mean": mean_b,
                "scenario_mean": draws["central"][1] if "central" in draws else mean_b,
            }
        )
        return {
            "stocks": df,
            "implied": implied,
            "horizon_weeks": h,
            "mode": mode,
            "basis": basis,
            "cov_source": self.cov_source,
        }


def _stats(R: np.ndarray) -> dict[str, float]:
    simple = np.expm1(R)
    loss = -simple
    v95, v99 = np.quantile(loss, [0.95, 0.99])
    return {
        "exp_ret": float(simple.mean()),
        "median_ret": float(np.median(simple)),
        "var95": float(v95),
        "var99": float(v99),
        "cvar95": float(loss[loss >= v95].mean()),
        "cvar99": float(loss[loss >= v99].mean()),
        "p_loss": float((R < 0).mean()),
        "p_loss10": float((simple < -0.10).mean()),
    }


def universe_summary(stocks: pd.DataFrame) -> pd.DataFrame:
    """Average (and median) changes per universe, with and without names in both universes."""
    rows = []
    for u, g in stocks.groupby("universe"):
        for label, gg in (("all", g), ("no_overlap", g[~g["overlap"]])):
            row = {"universe": u, "sample": label, "n": len(gg)}
            for c in ("d_exp_ret", "d_var99", "d_cvar99", "d_p_loss"):
                if c in gg:
                    row[c] = gg[c].mean()
            if "d_exp_ret" in gg:  # robust to one dominant name (D-047)
                row["median_d_exp_ret"] = gg["d_exp_ret"].median()
            rows.append(row)
    return pd.DataFrame(rows)
