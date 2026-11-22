"""Streamlit entry point.

Run with:  uv run streamlit run src/pusula/app/Home.py

We use ``st.navigation`` so page titles can be Turkish while file names stay ASCII.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from pusula.app.i18n_tr import t

PAGES_DIR = Path(__file__).parent / "views"  # not "pages/": that name triggers auto-navigation

st.set_page_config(page_title=t("app_title"), page_icon="🧭", layout="wide")

pages = [
    st.Page(PAGES_DIR / "ana_sayfa.py", title=t("nav_home"), icon="🏠", default=True),
]
for fname, key, icon in (
    ("hisse_risk.py", "nav_risk", "📉"),
    ("senaryo.py", "nav_scenario", "🧪"),
    ("karsilastirma.py", "nav_compare", "⚖️"),
):
    if (PAGES_DIR / fname).exists():
        pages.append(st.Page(PAGES_DIR / fname, title=t(key), icon=icon))
data_status = PAGES_DIR / "veri_durumu.py"
if data_status.exists():
    pages.append(st.Page(data_status, title=t("nav_data_status"), icon="🗄️"))

st.navigation(pages).run()
