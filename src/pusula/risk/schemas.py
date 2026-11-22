"""Pydantic schema of the risk engine output (input of Agent 1 in Phase 4)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class ModelResult(BaseModel):
    name: str
    fitted: bool
    failure_reason: str | None = None
    params: dict[str, float] = Field(default_factory=dict)
    critic: dict[str, float] = Field(default_factory=dict)  # hold-out criteria (default)
    score: float | None = None  # hold-out equal-weight average rank (lower = better)
    critic_insample: dict[str, float] = Field(default_factory=dict)
    score_insample: float | None = None
    holdout_failure: str | None = None  # fit on the first 80% failed
    var99_1d: float | None = None
    cvar99_1d: float | None = None
    seconds: float = 0.0


class VarBlock(BaseModel):
    var95: float
    cvar95: float
    var99: float
    cvar99: float


class RiskReport(BaseModel):
    ticker: str
    as_of: date
    basis: str
    window_start: date
    window_end: date
    n_window: int
    n_history: int
    seed: int
    models: list[ModelResult]
    critic_method: str = "holdout"  # how selected_model was chosen (D-050)
    n_holdout: int = 0
    selected_model: str
    selection_by_scheme: dict[str, str]
    selection_stable: bool
    selected_model_insample: str | None = None
    selection_by_scheme_insample: dict[str, str] = Field(default_factory=dict)
    horizon_1d: VarBlock
    horizon_10d: VarBlock
    p_loss_10pct_1m: float
    drawdown_1m: dict[str, float]
    drawdown_3m: dict[str, float]
    drawdown_3m_hist: dict[str, list[float]]
    sim_1d_hist: dict[str, list[float]]
    fan_chart: dict[str, list[float]]
    vol_ann_realized: float
    vol_ann_model: float
    beta_xu100: float | None
    beta_n: int
    evt: dict
    risk_level: str | None = None  # filled by the universe run (relative measure)
    risk_score: float | None = None
    warnings: list[str] = Field(default_factory=list)
    seconds_total: float = 0.0
