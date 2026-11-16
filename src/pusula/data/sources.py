"""Typed view of ``config/data_sources.yaml``."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field

from pusula.config import load_yaml

TODO_CODE = "TODO_VERIFY"

FillRule = Literal["step", "market", "release", "none"]


class SeriesSpec(BaseModel):
    id: str
    source: Literal["yfinance", "evds", "manual"]
    code: str | None = None
    freq: Literal["D", "M", "E"] = "D"
    fill: FillRule = "market"
    unit: str = ""
    manual: str | None = None
    desc: str = ""

    @property
    def code_verified(self) -> bool:
        return self.code is not None and self.code != TODO_CODE


class EventSpec(BaseModel):
    id: str
    source: Literal["manual"] = "manual"
    manual: str
    desc: str = ""


class EvdsCfg(BaseModel):
    base_url: str


class DataSources(BaseModel):
    evds: EvdsCfg
    price_tickers_suffix: str = ".IS"
    indices: list[SeriesSpec] = Field(default_factory=list)
    macro: list[SeriesSpec] = Field(default_factory=list)
    events: list[EventSpec] = Field(default_factory=list)

    def macro_by_id(self) -> dict[str, SeriesSpec]:
        return {s.id: s for s in self.macro}


@lru_cache(maxsize=1)
def get_data_sources() -> DataSources:
    return DataSources.model_validate(load_yaml("data_sources.yaml"))
