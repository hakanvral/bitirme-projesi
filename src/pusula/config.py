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

    # Overrides for config/settings.yaml (llm section); empty = use the YAML value.
    llm_provider: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_model_light: str | None = None
    nvidia_api_key: SecretStr | None = None
    llm_api_key: SecretStr | None = None  # generic key for other OpenAI-compatible endpoints
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_model_light: str = "claude-haiku-5-5"

    evds_api_key: SecretStr | None = None
    epias_username: str | None = None
    epias_password: SecretStr | None = None

    pusula_log_level: str = "INFO"

    def key_status(self) -> dict[str, bool]:
        """Which keys are configured (booleans only - safe to show in the UI)."""
        return {
            "NVIDIA_API_KEY": bool(self.nvidia_api_key),
            "LLM_API_KEY": bool(self.llm_api_key),
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
    provider: str = "openai_compatible"
    base_url: str = "https://integrate.api.nvidia.com/v1"
    model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    model_light: str = "nvidia/nemotron-3-ultra-550b-a55b"
    api_key_env: str = "NVIDIA_API_KEY"
    rpm: int = 35
    max_concurrency: int = 4
    timeout_s: float = 180
    max_tokens: int = 16384  # D-068
    temperature: float = 0.2
    json_mode: str = "auto"
    max_json_retries: int = 2
    max_backoff_retries: int = 6
    cache_path: Path = Path("data/llm_cache.sqlite")
    extra_body: dict = {}  # merged into every request (all agents)
    extra_body_lean: dict = {}  # merged into lean-mode requests only (E4 throughput)

    @model_validator(mode="after")
    def _abs_cache(self) -> LLMCfg:
        if not self.cache_path.is_absolute():
            self.cache_path = ROOT_DIR / self.cache_path
        return self


class DataQualityCfg(BaseModel):
    jump_thresholds: dict[str, float] = {
        "stock": 0.105,
        "index": 0.10,
        "fx": 0.10,
        "commodity": 0.25,
    }
    stale_days: int = 5
    max_ffill_days_market: int = 5


class EvtCfg(BaseModel):
    min_history: int = 750
    threshold_quantile: float = 0.95
    run_length: int = 5
    min_clusters: int = 20


class RiskCfg(BaseModel):
    calibration_window: int = 500
    min_history: int = 250
    max_gap_sessions: int = 5
    n_paths: int = 10_000
    horizon_days: int = 63
    critic_paths: int = 200
    critic_holdout_share: float = 0.2  # hold-out critic: last 20% of the window (100 of 500)
    merton_threshold: float = 3.0
    merton_min_jumps: int = 3
    evt: EvtCfg = EvtCfg()
    risk_level_cutoffs: list[float] = [25, 50, 75]


class BacktestCfg(BaseModel):
    transaction_cost_bp: float = 10
    slippage_bp: float = 5
    auditor_sample_rate: float = Field(0.10, ge=0, le=1)
    long_sample_start: date


class DataFreezeCfg(BaseModel):
    """While enabled, commands that change input data refuse to run (D-076)."""

    enabled: bool = False
    as_of: date | None = None
    reason: str = ""


class DataFrozenError(RuntimeError):
    """Raised by data-changing commands while the data freeze is on."""


def assert_data_not_frozen(action: str) -> None:
    fz = get_settings().data_freeze
    if fz.enabled:
        raise DataFrozenError(
            f"{action} refused: data freeze is on (data as of {fz.as_of}; {fz.reason}). "
            "Set data_freeze.enabled: false in config/settings.yaml only after all LLM "
            "experiments are finished (D-076)."
        )


class LLMBackupCfg(BaseModel):
    """Alternative OpenAI-compatible provider, used only when ``enabled`` (D-075)."""

    enabled: bool = False
    base_url: str = ""
    model: str = ""
    api_key_env: str = ""
    rpm: int = 10
    extra_body: dict = {}
    extra_body_lean: dict = {}


class Settings(BaseModel):
    project: ProjectCfg
    paths: PathsCfg
    llm: LLMCfg
    llm_backup: LLMBackupCfg = LLMBackupCfg()
    data_freeze: DataFreezeCfg = DataFreezeCfg()
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
    """Settings from ``config/settings.yaml``. The LLM pace can be lowered for long batch runs
    without editing the file: ``PUSULA_LLM_RPM`` and ``PUSULA_LLM_CONCURRENCY`` (D-073)."""
    import os

    s = Settings.model_validate(load_yaml("settings.yaml"))
    if os.environ.get("PUSULA_LLM_RPM"):
        s.llm.rpm = int(os.environ["PUSULA_LLM_RPM"])
    if os.environ.get("PUSULA_LLM_CONCURRENCY"):
        s.llm.max_concurrency = int(os.environ["PUSULA_LLM_CONCURRENCY"])
    return s


@lru_cache(maxsize=1)
def get_regimes() -> Regimes:
    return Regimes.model_validate(load_yaml("regimes.yaml"))


@lru_cache(maxsize=1)
def get_secrets() -> Secrets:
    return Secrets()
