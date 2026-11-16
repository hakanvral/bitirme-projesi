"""Shared page elements (disclaimer footer, headers)."""

from __future__ import annotations

import streamlit as st

from pusula.app.i18n_tr import t


def disclaimer_footer() -> None:
    """Render the mandatory academic / not-investment-advice disclaimer (CLAUDE.md §2.5)."""
    st.divider()
    st.caption(f"⚠️ {t('disclaimer')}")
