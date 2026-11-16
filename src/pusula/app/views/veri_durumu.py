"""Veri Durumu: data freshness, coverage, quality flags, update button (CLAUDE.md §7)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pusula.app.components.layout import disclaimer_footer
from pusula.app.i18n_tr import t
from pusula.config import get_settings
from pusula.data.quality import jump_flags
from pusula.data.sources import get_data_sources
from pusula.data.store import Store
from pusula.universe.load import load_energy_selected

STATUS_LABEL = {"ok": "✅ sorunsuz", "warn": "⚠️ uyarı", "missing": "❌ eksik"}

st.title(f"🗄️ {t('ds_title')}")
settings = get_settings()
db_path = settings.paths.db_path

if st.button(t("ds_update_button"), type="primary"):
    from pusula.data.update import run_update

    with st.spinner(t("ds_update_running")):
        try:
            log_df = run_update()
            st.success(t("ds_update_done"))
            st.dataframe(log_df[["series", "source", "status", "rows", "message"]], hide_index=True)
        except Exception as exc:  # shown to the user, not swallowed
            st.error(t("ds_update_failed"))
            st.exception(exc)
    st.cache_data.clear()


@st.cache_data(ttl=300)
def _load(path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    store = Store(settings.paths.db_path, settings.paths.raw_dir)
    rep = store.query("SELECT * FROM quality_report ORDER BY kind, series")
    th = settings.data_quality.jump_thresholds
    flags = jump_flags(store.prices(), th["stock"], th["index"])
    return rep, flags


if not db_path.exists():
    st.warning(t("ds_no_db"))
else:
    rep, flags = _load(str(db_path))
    if rep.empty:
        st.warning(t("ds_no_db"))
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(t("ds_metric_series"), len(rep))
        c2.metric(t("ds_metric_ok"), int((rep["status"] == "ok").sum()))
        c3.metric(t("ds_metric_warn"), int((rep["status"] == "warn").sum()))
        c4.metric(t("ds_metric_missing"), int((rep["status"] == "missing").sum()))

        st.subheader(t("ds_series_header"))
        view = rep.assign(status=rep["status"].map(STATUS_LABEL))
        view = view[
            [
                "series",
                "source",
                "first_date",
                "last_date",
                "coverage_pct",
                "missing_days",
                "stale_days",
                "jumps",
                "last_update",
                "status",
            ]
        ]
        view.columns = [
            t(k)
            for k in (
                "ds_col_series",
                "ds_col_source",
                "ds_col_first",
                "ds_col_last",
                "ds_col_coverage",
                "ds_col_missing",
                "ds_col_stale",
                "ds_col_jumps",
                "ds_col_updated",
                "ds_col_status",
            )
        ]
        st.dataframe(view, hide_index=True, use_container_width=True)

        st.subheader(t("ds_flags_header"))
        if flags.empty:
            st.info(t("ds_no_flags"))
        else:
            fv = flags[["date", "ticker", "prev_adj_close", "adj_close", "return"]].assign(
                date=flags["date"].dt.date, **{"return": flags["return"] * 100}
            )
            fv.columns = [
                t(k)
                for k in (
                    "ds_col_date",
                    "ds_col_ticker",
                    "ds_col_prev",
                    "ds_col_adj",
                    "ds_col_return",
                )
            ]
            st.dataframe(
                fv,
                hide_index=True,
                use_container_width=True,
                column_config={t("ds_col_return"): st.column_config.NumberColumn(format="%.1f%%")},
            )

st.subheader(t("ds_energy_header"))
sel = load_energy_selected()
if sel is None:
    st.info(t("ds_energy_missing"))
else:
    sv = sel[["ticker", "name", "sub_sector", "in_bist30", "verified"]]
    sv.columns = [
        t(k)
        for k in (
            "ds_col_ticker",
            "ds_col_name",
            "ds_col_subsector",
            "ds_col_inbist30",
            "ds_col_verified",
        )
    ]
    st.dataframe(sv, hide_index=True, use_container_width=True)

st.subheader(t("ds_manual_header"))
manual_dir = settings.paths.manual_dir
expected = sorted(
    {s.manual for s in get_data_sources().macro if s.manual}
    | {"ppk_decisions.csv", "cpi_release_dates.csv", "cpi_exp_12m_release_dates.csv"}
)
st.dataframe(
    pd.DataFrame(
        {
            t("ds_col_file"): expected,
            t("ds_col_status"): ["✅" if (manual_dir / f).exists() else "—" for f in expected],
        }
    ),
    hide_index=True,
)

disclaimer_footer()
