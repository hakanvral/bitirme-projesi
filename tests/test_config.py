from datetime import date

import pytest
from pydantic import ValidationError

from pusula.config import ROOT_DIR, Regimes, Secrets, get_regimes, get_settings


def test_settings_load_and_paths_absolute():
    s = get_settings()
    assert s.project.data_start == date(2018, 1, 1)
    assert s.project.selection_date < s.project.reference_date
    assert s.paths.db_path.is_absolute()
    assert s.paths.db_path.parent == ROOT_DIR / "data"


def test_llm_cutoff_before_post_cutoff_window():
    s = get_settings()
    assert s.llm.training_cutoff < s.llm.post_cutoff_start


def test_regimes_contiguous_and_lookup():
    r = get_regimes()
    assert r.regime_of(date(2018, 6, 1)) == "crisis_2018"
    assert r.regime_of(date(2022, 1, 1)) == "unorthodox_2021_2023"
    assert r.regime_of(date(2026, 11, 1)) == "easing_2024_2026"
    assert r.regime_of(date(2017, 1, 1)) is None


def test_regimes_reject_gaps():
    with pytest.raises(ValidationError):
        Regimes.model_validate(
            {
                "regimes": [
                    {"id": "a", "name_tr": "a", "start": "2018-01-01", "end": "2019-01-01"},
                    {"id": "b", "name_tr": "b", "start": "2019-02-01", "end": None},
                ]
            }
        )


def test_secrets_never_print(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-very-secret")
    s = Secrets(_env_file=None)
    assert "very-secret" not in repr(s)
    assert "very-secret" not in str(s.model_dump())
    assert s.key_status()["ANTHROPIC_API_KEY"] is True
