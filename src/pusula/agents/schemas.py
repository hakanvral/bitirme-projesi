"""Pydantic output schemas of the agents (CLAUDE.md §6.4). Field names are Turkish because the
reports are Turkish; every text field is written for a non-expert reader."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

DISCLAIMER = "karar destek amaçlıdır, yatırım tavsiyesi değildir"


def _has_disclaimer(v: str) -> str:
    low = v.lower().replace("İ", "i").replace("I", "ı")
    if "yatırım tavsiyesi değildir" not in low and "yatirim tavsiyesi degildir" not in low:
        raise ValueError(f"'uyari' must contain the sentence: '{DISCLAIMER}'")
    return v


class RiskNarrative(BaseModel):
    ozet: str = Field(description="2-4 cümlelik özet")
    risk_duzeyi_aciklamasi: str = Field(description="Verilen göreli risk düzeyinin açıklaması")
    ana_risk_kaynaklari: list[str] = Field(min_length=1, max_length=5)
    metriklerin_anlami: str = Field(description="VaR, CVaR, beta, düşüş: sade dille")
    veri_kisitlari: list[str] = Field(default_factory=list)
    uyari: str

    _d = field_validator("uyari")(_has_disclaimer)


class ScenarioNarrative(BaseModel):
    ozet: str
    zarar_veren_senaryolar: list[str] = Field(default_factory=list, max_length=6)
    fayda_saglayan_senaryolar: list[str] = Field(default_factory=list, max_length=6)
    en_hassas_faktor: str
    bist30_enerji_karsilastirmasi: str
    veri_kisitlari: list[str] = Field(default_factory=list)
    uyari: str

    _d = field_validator("uyari")(_has_disclaimer)


class CaseArgument(BaseModel):
    """Bull (lehte) or Bear (aleyhte) case."""

    tez: str
    gerekceler: list[str] = Field(min_length=3, max_length=5)


class Decision(BaseModel):
    karar: Literal["AL", "ALMA", "BEKLE"]
    guven: float = Field(ge=0, le=1)
    vade: str
    lehte_gerekceler: list[str] = Field(min_length=3, max_length=3)
    aleyhte_gerekceler: list[str] = Field(min_length=3, max_length=3)
    temel_riskler: list[str] = Field(min_length=1, max_length=5)
    karari_degistirecek_kosullar: list[str] = Field(min_length=1, max_length=5)
    uyari: str

    _d = field_validator("uyari")(_has_disclaimer)

    @field_validator("temel_riskler")
    @classmethod
    def _risks_are_sentences(cls, v: list[str]) -> list[str]:
        """Prompt v3: each key risk is a short descriptive sentence, not a bare number."""
        for item in v:
            words = [w for w in item.split() if any(ch.isalpha() for ch in w)]
            if len(words) < 3:
                raise ValueError(
                    f"temel_riskler items must be short descriptive sentences, got {item!r}"
                )
        return v


class LeanDecision(BaseModel):
    """Single structured decision for the E4 backtest (lean mode)."""

    karar: Literal["AL", "ALMA", "BEKLE"]
    guven: float = Field(ge=0, le=1)
    kisa_gerekce: str = Field(description="En fazla 2 cümle")


class ConsistencyCheck(BaseModel):
    tutarli: bool
    sorunlar: list[str] = Field(default_factory=list)
    # keys of the reports that contain the problems (risk_analyst, scenario_analyst, bull, bear,
    # judge) so exactly those can be regenerated (D-063)
    sorunlu_raporlar: list[Literal["risk_analyst", "scenario_analyst", "bull", "bear", "judge"]] = (
        Field(default_factory=list)
    )


class NumericIssue(BaseModel):
    report: str
    field: str
    text: str
    value: float


class AuditResult(BaseModel):
    passed: bool
    numeric_ok: bool
    numbers_checked: int
    numeric_issues: list[NumericIssue] = Field(default_factory=list)
    consistency_checked: bool = False
    consistency_ok: bool | None = None
    consistency_issues: list[str] = Field(default_factory=list)
    problem_reports: list[str] = Field(default_factory=list)
    regenerated: list[str] = Field(default_factory=list)  # reports regenerated once
    notes: list[str] = Field(default_factory=list)
