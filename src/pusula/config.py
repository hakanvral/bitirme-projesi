"""Configuration loading.

Two sources:
* ``.env`` / process environment -> :class:`Secrets` (API keys, LLM model names).
* ``config/*.yaml`` -> typed pydantic models (non-secret, version controlled).

Everything is resolved relative to the repository root so the code works no matter which
directory a command is started from.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"


# --------------------------------------------------------------------------- secrets
class Secrets(BaseSettings):
    """Values read from the environment / ``.env``. Keys are ``SecretStr`` so they never print."""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    llm_provider: str = "anthropic"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_model_light: str = "claude-haiku-5-5"
    llm_temperature: float = 0.0

    evds_api_key: SecretStr | None = None
    epias_username: str | None = None
    epias_password: SecretStr | None = None

    pusula_log_level: str = "INFO"

    def key_status(self) -> dict[str, bool]:
        """Which keys are configured (booleans only - safe to show in the UI)."""
        return {
            "ANTHROPIC_API_KEY": bool(self.anthropic_api_key),
            "EVDS_API_KEY": bool(self.evds_api_key),
            "EPIAS_USERNAME": bool(self.epias_username),
        }


# --------------------------------------------------------------------------- settings.yaml
class ProjectCfg(BaseModel):
    name: str = "PUSULA"
    data_start: date
    reference_date: date
    selection_date: date
    random_seed: int = 42

    @model_validator(mode="after")
    def _check_dates(self) -> ProjectCfg:
        if not (self.data_start < self.selection_date <= self.reference_date):
            raise ValueError("Expected data_start < selection_date <= reference_date")
        return self


class PathsCfg(BaseModel):
    data_dir: Path
    raw_dir: Path
    manual_dir: Path
    db_path: Path
    results_dir: Path

    @model_validator(mode="after")
    def _absolute(self) -> PathsCfg:
        for name in ("data_dir", "raw_dir", "manual_dir", "db_path", "results_dir"):
            p = getattr(self, name)
            if not p.is_absolute():
                setattr(self, name, ROOT_DIR / p)
        return self


class LLMCfg(BaseModel):
    training_cutoff: date
    post_cutoff_start: date


class DataQualityCfg(BaseModel):
    jump_threshold: float = 0.25
    stale_days: int = 5
    max_ffill_days_market: int = 5


class RiskCfg(BaseModel):
    calibration_window: int = 500
    n_paths: int = 10_000


class BacktestCfg(BaseModel):
    transaction_cost_bp: float = 10
    slippage_bp: float = 5
    auditor_sample_rate: float = Field(0.10, ge=0, le=1)
    long_sample_start: date


class Settings(BaseModel):
    project: ProjectCfg
    paths: PathsCfg
    llm: LLMCfg
    data_quality: DataQualityCfg = DataQualityCfg()
    risk: RiskCfg = RiskCfg()
    backtest: BacktestCfg


# --------------------------------------------------------------------------- regimes.yaml
class Regime(BaseModel):
    id: str
    name_tr: str
    start: date
    end: date | None = None

    def contains(self, d: date) -> bool:
        return self.start <= d and (self.end is None or d < self.end)


class Regimes(BaseModel):
    regimes: list[Regime]

    @model_validator(mode="after")
    def _contiguous(self) -> Regimes:
        for a, b in zip(self.regimes, self.regimes[1:], strict=False):
            if a.end != b.start:
                raise ValueError(f"Regimes must be contiguous: {a.id} -> {b.id}")
        return self

    def regime_of(self, d: date) -> str | None:
        for r in self.regimes:
            if r.contains(d):
                return r.id
        return None


# --------------------------------------------------------------------------- loaders
def load_yaml(name: str, config_dir: Path | None = None) -> dict[str, Any]:
    """Load ``config/<name>`` as a dict (empty dict for an empty file)."""
    path = (config_dir or CONFIG_DIR) / name
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.model_validate(load_yaml("settings.yaml"))


@lru_cache(maxsize=1)
def get_regimes() -> Regimes:
    return Regimes.model_validate(load_yaml("regimes.yaml"))


@lru_cache(maxsize=1)
def get_secrets() -> Secrets:
    return Secrets()
