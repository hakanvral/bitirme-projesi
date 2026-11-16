"""Home page (static in P0; the macro snapshot 'Genel Bakış' arrives in P7)."""

from __future__ import annotations

import streamlit as st

from pusula.app.components.layout import disclaimer_footer
from pusula.app.i18n_tr import t

st.title(f"🧭 {t('app_title')}")
st.subheader(t("app_subtitle"))
st.markdown(t("home_intro"))
st.markdown(t("home_universes"))
st.info(f"**{t('home_status_header')}** — {t('home_status_body')}")

disclaimer_footer()
