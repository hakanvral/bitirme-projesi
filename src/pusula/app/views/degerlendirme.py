"""Backtest & Değerlendirme (CLAUDE.md §7): viewer for the E1–E5 results in ``results/``.

The page only reads files written by the experiment scripts (latest run of each experiment);
it never starts an experiment or an LLM call.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from pusula.app.components.layout import disclaimer_footer
from pusula.app.i18n_tr import EVAL_COLUMNS, t
from pusula.evaluation.common import latest_run

st.title(f"📊 {t('nav_eval')}")
st.caption(t("ev_intro"))


def _table(run: Path, name: str, query: str | None = None, cols: list[str] | None = None):
    f = run / f"{name}.csv"
    if not f.exists():
        st.info(t("ev_missing_file").format(f=f.name))
        return None
    df = pd.read_csv(f)
    if query:
        df = df.query(query)
    if cols:
        df = df[[c for c in cols if c in df.columns]]
    shown = df.rename(columns=EVAL_COLUMNS)
    fmt = {}
    for c in shown.select_dtypes("number").columns:
        vals = shown[c].dropna()
        whole = not vals.empty and bool((vals % 1 == 0).all())
        fmt[c] = "{:,.0f}" if whole else "{:.3f}"
    st.dataframe(
        shown.style.format(fmt, na_rep="—"),
        hide_index=True,
        use_container_width=True,
    )
    return df


def _figure(run: Path, name: str, caption: str | None = None):
    f = run / f"{name}.png"
    if f.exists():
        st.image(str(f), caption=caption, use_container_width=True)


def _header(exp: str):
    run = latest_run(exp)
    if run is None:
        st.info(t("ev_not_run").format(cmd=t(f"ev_cmd_{exp}")))
        return None
    st.caption(t("ev_run").format(run=run.name, path=run))
    return run


tabs = st.tabs([t("ev_tab_e1"), t("ev_tab_e2"), t("ev_tab_e3"), t("ev_tab_e4"), t("ev_tab_e5")])

with tabs[0]:
    st.markdown(t("ev_e1_text"))
    run = _header("e1_var")
    if run:
        lv = st.radio(
            t("ev_level"), [0.99, 0.95], horizontal=True, format_func=lambda x: f"%{x * 100:.0f}"
        )
        _table(run, "e1_key_table", f"level == {lv}")
        st.markdown(f"**{t('ev_e1_critic')}**")
        _table(run, "e1_critic_comparison", f"level == {lv}")
        _figure(run, "e1_exceedance_rates")
        _figure(run, "e1_rolling_exceedance_var99")
        with st.expander(t("ev_more")):
            st.markdown(f"**{t('ev_e1_selection')}**")
            _table(run, "e1_model_selection_shares")
            st.markdown(f"**{t('ev_e1_regime')}**")
            grp = st.selectbox(t("ev_group"), ["Tümü", "BIST30", "Energy"])
            _table(run, "e1_summary_by_group_regime", f"group == '{grp}' and level == {lv}")

with tabs[1]:
    st.markdown(t("ev_e2_text"))
    run = _header("e2_factor")
    if run:
        _table(run, "e2_universe_comparison")
        _table(run, "e2_by_subsector")
        _figure(run, "e2_beta_heatmap")
        _figure(run, "e2_r2_is_oos")
        with st.expander(t("ev_more")):
            _table(run, "e2_beta_stability")
            _table(run, "e2_regime_sensitivities")

with tabs[2]:
    st.markdown(t("ev_e3_text"))
    run = _header("e3_event")
    if run:
        _table(run, "e3_scores")
        _figure(run, "e3_pred_vs_realised")
        _table(run, "e3_realised_by_direction")
        _figure(run, "e3_event_car_by_universe")
        with st.expander(t("ev_more")):
            _table(run, "e3_holds_realised")
            _table(run, "e3_events")

with tabs[3]:
    st.markdown(t("ev_e4_text"))
    run = _header("e4_backtest")
    if run:
        a, b = st.columns(2)
        win = a.radio(t("ev_window"), ["tam", "kesim sonrası"], horizontal=True)
        basis = b.radio(t("basis_label"), ["TRY", "USD"], horizontal=True)
        _table(
            run,
            "e4_performance",
            f"window == '{win}' and basis == '{basis}'",
            [
                "strategy",
                "cum_return",
                "cagr",
                "vol_ann",
                "sharpe",
                "sortino",
                "max_drawdown",
                "calmar",
                "hit_rate",
                "turnover_weekly",
                "avg_position",
            ],
        )
        _figure(run, "e4_equity_curves")
        st.markdown(f"**{t('ev_e4_coverage')}**")
        _table(run, "e4_coverage")
        st.markdown(f"**{t('ev_e4_ci')}**")
        _table(run, "e4_sharpe_diff_ci", f"window == '{win}'")
        st.markdown(f"**{t('ev_e4_dist')}**")
        _table(run, "e4_decision_distribution")
        with st.expander(t("ev_more")):
            _table(run, "e4_stocks")
            _table(run, "e4_long_sample_2019_2026")
            _table(run, "e4_long_sample_sharpe_ci")
            _table(run, "e4_decision_distribution_per_stock")
            _table(run, "e4_performance_per_stock")

with tabs[4]:
    st.markdown(t("ev_e5_text"))
    run = _header("e5_llm")
    if run:
        _table(run, "e5_agreement_summary")
        _table(run, "e5_pairwise_agreement")
        _figure(run, "e5_decision_distribution")
        st.markdown(f"**{t('ev_e5_full')}**")
        _table(run, "e5_full_mode_audit")
        with st.expander(t("ev_more")):
            _table(run, "e5_latency_by_rater")
            _table(run, "e5_usage_by_agent")
            _table(run, "e5_items_decisions")

disclaimer_footer()
