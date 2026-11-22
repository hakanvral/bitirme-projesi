"""Seeded Monte Carlo helpers.

Every (ticker, as_of, model, purpose) gets its own reproducible random stream derived from the
global seed, so results do not depend on the order in which stocks or models are processed.
"""

from __future__ import annotations

import zlib
from datetime import date

import numpy as np

PURPOSE = {"critic": 1, "forward": 2, "holdout": 3}


def rng_for(
    seed: int, ticker: str, as_of: date, model_index: int, purpose: str
) -> np.random.Generator:
    ss = np.random.SeedSequence(
        [seed, zlib.crc32(ticker.encode()), as_of.toordinal(), model_index, PURPOSE[purpose]]
    )
    return np.random.default_rng(ss)


def cumulative(paths: np.ndarray, days: int) -> np.ndarray:
    """Sum of the first ``days`` daily log returns of each path."""
    return paths[:, :days].sum(axis=1)
