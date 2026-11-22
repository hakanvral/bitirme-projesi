"""Ajan Kararı (CLAUDE.md §7): button-triggered agent pipeline for one stock."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from pusula.app.components.agent_ui import audit_badge, decision_card, risk_report, scenario_report
from pusula.app.components.data_access import latest_session, members, store, ticker_label
from pusula.app.components.layout import disclaimer_footer
from pusula.app.i18n_tr import t
from pusula.config import get_settings

st.title(f"🤖 {t('ag_title')}")
st.caption(t("ag_intro"))
as_of = latest_session()
mem = members(as_of).drop_duplicates("symbol")
labels = {ticker_label(r): r.ticker for r in mem.itertuples()}
c1, c2, c3 = st.columns([2, 2, 1.5])
choice = c1.selectbox(t("stock"), list(labels))
mode = c2.radio(
    t("ag_mode"),
    ["full", "anonymized", "lean"],
    format_func=lambda m: t(f"ag_mode_{m}"),
    horizontal=True,
)
ablation = c3.selectbox(t("ag_ablation"), ["P+R+S", "P+R", "P"], help=t("ag_ablation_help"))
n_req = 1 if mode == "lean" else {"P+R+S": 6, "P+R": 5, "P": 4}[ablation]
st.info(t("ag_cost_note").format(n=n_req, rpm=get_settings().llm.rpm))

if st.button(t("ag_run"), type="primary"):
    from pusula.pipeline import run_analysis

    with st.spinner(t("ag_running")):
        try:
            run = run_analysis(labels[choice], as_of, mode=mode, ablation=ablation)
            st.session_state["last_run"] = json.loads(run.model_dump_json())
        except Exception as exc:
            st.error(f"{t('ag_error')}: {exc}")

runs = store().query(
    "SELECT run_id, ticker, as_of, mode, created_at FROM analysis_runs "
    "ORDER BY created_at DESC LIMIT 50"
)
run = st.session_state.get("last_run")
if run is None and not runs.empty:
    sel = runs[runs["ticker"] == labels[choice].strip() + ".IS"]
    if not sel.empty:
        p = store().query(
            "SELECT payload FROM analysis_runs WHERE run_id = ?", [sel["run_id"].iloc[0]]
        )
        run = json.loads(p["payload"].iloc[0])

if run:
    st.subheader(f"{run['ticker']} · {run['as_of']} · {run['mode']} · {run['ablation']}")
    if run.get("audit"):
        audit_badge(run["audit"])
    st.subheader(t("ag_decision"))
    decision_card(run.get("decision") or run["lean_decision"])
    if run.get("risk_narrative"):
        with st.expander(t("ag_risk_report"), expanded=True):
            risk_report(run["risk_narrative"])
    if run.get("scenario_narrative"):
        with st.expander(t("ag_scenario_report"), expanded=True):
            scenario_report(run["scenario_narrative"])
    if run.get("bull"):
        with st.expander(t("ag_debate")):
            c1, c2 = st.columns(2)
            for col, key in ((c1, "bull"), (c2, "bear")):
                with col:
                    st.markdown(f"**{t('ag_' + key)}:** {run[key]['tez']}")
                    for g in run[key]["gerekceler"]:
                        st.markdown(f"- {g}")
    st.subheader(t("ag_usage"))
    tot = run["totals"]
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("İstek", tot.get("requests", 0))
    m2.metric("Girdi token", f"{tot['input_tokens']:,}".replace(",", "."))
    m3.metric("Çıktı token", f"{tot['output_tokens']:,}".replace(",", "."))
    m4.metric("LLM süresi (sn)", f"{tot['llm_latency_s']:.0f}")
    m5.metric("JSON hatası", tot["json_failures"])
    st.dataframe(pd.DataFrame(run["calls"]), hide_index=True, use_container_width=True)
    with st.expander(t("ag_inputs")):
        st.code(json.dumps(run["inputs"], ensure_ascii=False, indent=1), language="json")

st.subheader(t("ag_history"))
st.dataframe(runs, hide_index=True, use_container_width=True)
disclaimer_footer()
