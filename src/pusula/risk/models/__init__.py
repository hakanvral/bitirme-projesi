"""Model library (CLAUDE.md §6.2). Fixed, deterministic code; no LLM-written models."""

from pusula.risk.models.base import ModelFitError, RiskModel
from pusula.risk.models.filtered_hs import FilteredHistoricalSimulation
from pusula.risk.models.garch_t import GarchT
from pusula.risk.models.gbm import GBM
from pusula.risk.models.historical import HistoricalSimulation
from pusula.risk.models.merton import MertonJumpDiffusion

__all__ = [
    "GBM",
    "FilteredHistoricalSimulation",
    "GarchT",
    "HistoricalSimulation",
    "MertonJumpDiffusion",
    "ModelFitError",
    "RiskModel",
    "default_models",
]


def default_models(merton_threshold: float = 3.0, merton_min_jumps: int = 3) -> list[RiskModel]:
    """The core library in a fixed order (the order is part of the random-seed derivation)."""
    return [
        HistoricalSimulation(),
        FilteredHistoricalSimulation(),
        GBM(),
        MertonJumpDiffusion(threshold=merton_threshold, min_jumps=merton_min_jumps),
        GarchT(),
    ]
