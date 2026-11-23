"""Smoke tests: pages render without exceptions and show the disclaimer."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from pusula.app.i18n_tr import t

PAGES = Path(__file__).resolve().parents[1] / "src" / "pusula" / "app" / "views"


def _all_text(at: AppTest) -> str:
    parts = [e.value for e in at.markdown] + [e.value for e in at.caption]
    parts += [e.value for e in at.title] + [e.value for e in at.info]
    return "\n".join(str(p) for p in parts)


def test_home_page_renders_with_disclaimer():
    at = AppTest.from_file(str(PAGES / "ana_sayfa.py"), default_timeout=30).run()
    assert not at.exception
    assert t("disclaimer") in _all_text(at)


def test_entrypoint_runs():
    entry = PAGES.parent / "Home.py"
    at = AppTest.from_file(str(entry), default_timeout=30).run()
    assert not at.exception


def test_data_status_page_renders_without_db():
    at = AppTest.from_file(str(PAGES / "veri_durumu.py"), default_timeout=30).run()
    assert not at.exception
    assert t("disclaimer") in _all_text(at)


def test_risk_page_renders():
    at = AppTest.from_file(str(PAGES / "hisse_risk.py"), default_timeout=120).run()
    assert not at.exception
    assert t("disclaimer") in _all_text(at)


@pytest.mark.parametrize("page", ["senaryo.py", "karsilastirma.py"])
def test_macro_pages_render(page):
    at = AppTest.from_file(str(PAGES / page), default_timeout=180).run()
    assert not at.exception
    assert t("disclaimer") in _all_text(at)


@pytest.mark.parametrize("page", ["ajan_karari.py", "ayarlar.py", "degerlendirme.py"])
def test_agent_pages_render_without_llm_calls(page):
    at = AppTest.from_file(str(PAGES / page), default_timeout=120).run()
    assert not at.exception
    assert t("disclaimer") in _all_text(at)


def test_pages_show_a_hint_instead_of_failing_on_an_empty_database(tmp_path, monkeypatch):
    """Fresh clone: no prices yet -> a Turkish hint, no exception."""
    from pusula.app.components import data_access

    monkeypatch.setattr(data_access, "_latest_session", lambda: None)
    at = AppTest.from_file(str(PAGES / "ana_sayfa.py"), default_timeout=30)
    at.run()
    assert not at.exception
    assert any("frozen-rebuild" in w.value for w in at.warning)
