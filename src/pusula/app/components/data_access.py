"""Cached data access shared by the pages (heavy work cached with st.cache_data)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from pusula.config import get_settings
from pusula.data.store import Store
from pusula.universe.members import universe_members


def store() -> Store:
    s = get_settings()
    return Store(s.paths.db_path, s.paths.raw_dir)


@st.cache_data(ttl=600)
def _latest_session() -> date | None:
    d = store().query("SELECT max(date) AS d FROM prices WHERE ticker = 'XU100.IS'")["d"].iloc[0]
    return None if pd.isna(d) else pd.Timestamp(d).date()


def latest_session() -> date:
    """Last market date in the database. With an empty database (fresh clone) the page shows
    what to run instead of failing."""
    d = _latest_session()
    if d is None:
        from pusula.app.components.layout import disclaimer_footer
        from pusula.app.i18n_tr import t

        st.warning(t("db_empty"))
        disclaimer_footer()
        st.stop()
    return d


@st.cache_data(ttl=600)
def members(as_of: date) -> pd.DataFrame:
    return universe_members(as_of)


def ticker_label(row) -> str:
    grp = "Enerji" if row.universe == "Energy" else "BIST30"
    return f"{row.ticker} ({grp})"
