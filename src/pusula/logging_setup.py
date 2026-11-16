"""Project-wide logging. Call :func:`setup_logging` once at program start."""

from __future__ import annotations

import logging

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(level: str | None = None) -> None:
    """Configure the root logger. Level defaults to ``PUSULA_LOG_LEVEL`` (INFO)."""
    if level is None:
        from pusula.config import get_secrets

        level = get_secrets().pusula_log_level
    logging.basicConfig(level=level.upper(), format=_FORMAT, force=True)
    # Third-party libraries are noisy at INFO.
    for noisy in ("httpx", "urllib3", "yfinance", "peewee"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
