"""Hisse Risk Analizi (CLAUDE.md §7): deterministic risk engine, no LLM in P2."""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pusula.app.components.data_access import latest_session, members, store, ticker_label
from pusula.app.components.layout import disclaimer_footer
from pusula.app.components.theme import COLORS, NEUTRAL
from pusula.app.i18n_tr import t
from pusula.config import get_settings
from pusula.features.returns import to_basis
from pusula.risk.engine import (
    InsufficientHistoryError,
    compute_risk_report,
    daily_returns,
    load_inputs,
)

BASIS_KEYS = ["TRY", "REAL", "USD"]

st.title(f"📉 {t('risk_title')}")
settings = get_settings()


@st.cache_data(show_spinner=False, max_entries=8)
def _inputs(as_of: date):
    return load_inputs(store(), as_of)


@st.cache_data(show_spinner=False, max_entries=200)
def _report(symbol: str, as_of: date, basis: str) -> dict | None:
    try:
        rep = compute_risk_report(
            _inputs(as_of), symbol, basis, settings.risk, settings.project.random_seed
        )
    except InsufficientHistoryError:
        return None
    return rep.model_dump(mode="json")


@st.cache_data(show_spinner=False, max_entries=200)
def _history(symbol: str, as_of: date, basis: str) -> tuple[pd.Series, pd.Series]:
    inp = _inputs(as_of)
    from pusula.features.returns import session_prices

    px = to_basis(
        session_prices(inp.prices, symbol, inp.sessions),
        basis,
        inp.usdtry,
        inp.cpi_monthly,
        inp.as_of,
    )
    return px.dropna(), daily_returns(inp, symbol, basis, settings.risk.max_gap_sessions)


def _stored_level(symbol: str, as_of: date):
    df = store().query(
        "SELECT risk_level, risk_score FROM risk_reports WHERE as_of = ? AND ticker = ? "
        "AND basis = 'TRY'",
        [as_of, symbol],
    )
    return None if df.empty else df.iloc[0]


# ----------------------------------------------------------------------------- controls
c1, c2, c3, c4 = st.columns([1.2, 2, 1.6, 1.2])
as_of = c4.date_input(t("as_of"), value=latest_session(), max_value=latest_session())
mem = members(as_of)
grp = c1.radio(t("universe_label"), [t("universe_all"), t("universe_bist30"), t("universe_energy")])
if grp == t("universe_bist30"):
    mem = mem[mem["universe"] == "BIST30"]
elif grp == t("universe_energy"):
    mem = mem[mem["universe"] == "Energy"]
labels = {ticker_label(r): r.symbol for r in mem.itertuples()}
choice = c2.selectbox(t("stock"), list(labels))
basis = c3.radio(
    t("basis_label"), BASIS_KEYS, format_func=lambda k: t(f"basis_{k}"), horizontal=True
)
symbol = labels[choice]
color = COLORS["Energy"] if "(Enerji)" in choice else COLORS["BIST30"]

with st.spinner("Monte Carlo…"):
    rep = _report(symbol, as_of, basis)
if rep is None:
    st.warning(t("risk_insufficient"))
    disclaimer_footer()
    st.stop()

# ----------------------------------------------------------------------------- headline
lvl = _stored_level(symbol, date.fromisoformat(rep["as_of"]))
h1, h2, h3, h4, h5 = st.columns(5)
if lvl is not None:
    h1.metric(t("risk_level_label"), t(f"risk_level_{lvl.risk_level}"), help=t("risk_level_help"))
else:
    h1.info(t("risk_level_missing"))
    if h1.button(t("risk_level_run")):
        from pusula.risk.run_universe import run as run_universe

        with st.spinner("…"):
            run_universe(as_of, bases=("TRY",))
        st.rerun()
h2.metric(t("risk_vol"), f"{rep['vol_ann_realized']:.1%}")
h3.metric(t("risk_cvar99"), f"{rep['horizon_1d']['cvar99']:.2%}", help=t("risk_var_help"))
h4.metric(t("risk_beta"), "—" if rep["beta_xu100"] is None else f"{rep['beta_xu100']:.2f}")
h5.metric(t("risk_ploss"), f"{rep['p_loss_10pct_1m']:.1%}")
st.caption(
    f"{t('risk_selected')}: **{rep['selected_model']}** · {t('risk_window')}: "
    f"{rep['window_start']} → {rep['window_end']} ({rep['n_window']}) · "
    f"{t('risk_vol_model')}: {rep['vol_ann_model']:.1%} · "
    f"{t('risk_timing')}: {rep['seconds_total']:.2f} s"
)

px, rets = _history(symbol, as_of, basis)

# ----------------------------------------------------------------------------- price + fan
left, right = st.columns(2)
with left:
    st.subheader(t("risk_price_header"))
    fig = go.Figure(go.Scatter(x=px.index, y=px.values, line={"color": color}, name=symbol))
    fig.update_layout(height=320, margin={"l": 10, "r": 10, "t": 10, "b": 10})
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader(t("risk_fan_header"))
    fan = rep["fan_chart"]
    last = float(px.iloc[-1])
    days = np.arange(1, len(fan["p50"]) + 1)
    fig = go.Figure()
    for lo, hi, op in (("p5", "p95", 0.15), ("p25", "p75", 0.3)):
        fig.add_trace(
            go.Scatter(
                x=days,
                y=np.array(fan[hi]) * last,
                line={"width": 0},
                showlegend=False,
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=days,
                y=np.array(fan[lo]) * last,
                fill="tonexty",
                fillcolor=f"rgba(46,111,186,{op})",
                line={"width": 0},
                name=f"{lo[1:]}–{hi[1:]}%",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=days, y=np.array(fan["p50"]) * last, line={"color": color}, name=t("risk_fan_median")
        )
    )
    fig.update_layout(height=320, margin={"l": 10, "r": 10, "t": 10, "b": 10})
    st.plotly_chart(fig, use_container_width=True)

# ----------------------------------------------------------------------------- VaR + dist
left, right = st.columns(2)
with left:
    st.subheader(t("risk_var_header"), help=t("risk_var_help"))
    vt = pd.DataFrame(
        {
            t("risk_horizon"): [t("risk_1d"), t("risk_10d")],
            "VaR %95": [rep["horizon_1d"]["var95"], rep["horizon_10d"]["var95"]],
            "CVaR %95": [rep["horizon_1d"]["cvar95"], rep["horizon_10d"]["cvar95"]],
            "VaR %99": [rep["horizon_1d"]["var99"], rep["horizon_10d"]["var99"]],
            "CVaR %99": [rep["horizon_1d"]["cvar99"], rep["horizon_10d"]["cvar99"]],
        }
    )
    st.dataframe(
        vt.style.format({c: "{:.2%}" for c in vt.columns[1:]}),
        hide_index=True,
        use_container_width=True,
    )
    st.subheader(t("risk_dd_header"))
    d1, d3 = rep["drawdown_1m"], rep["drawdown_3m"]
    st.dataframe(
        pd.DataFrame(
            {
                "": ["Ortalama", "Medyan", "%75", "%95"],
                t("risk_dd_1m"): [d1["mean"], d1["p50"], d1["p75"], d1["p95"]],
                t("risk_dd_3m"): [d3["mean"], d3["p50"], d3["p75"], d3["p95"]],
            }
        ).style.format({t("risk_dd_1m"): "{:.1%}", t("risk_dd_3m"): "{:.1%}"}),
        hide_index=True,
        use_container_width=True,
    )
    h = rep["drawdown_3m_hist"]
    mid = (np.array(h["edges"][:-1]) + np.array(h["edges"][1:])) / 2
    fig = go.Figure(go.Bar(x=mid * 100, y=h["density"], marker_color=color))
    fig.update_layout(
        height=220,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        xaxis_title="3 aylık azami düşüş (%)",
    )
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader(t("risk_dist_header"))
    win = rets.loc[pd.Timestamp(rep["window_start"]) :]
    sh = rep["sim_1d_hist"]
    mid = (np.array(sh["edges"][:-1]) + np.array(sh["edges"][1:])) / 2
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=win.values,
            histnorm="probability density",
            nbinsx=60,
            marker_color=NEUTRAL,
            opacity=0.6,
            name=t("risk_dist_hist"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=mid,
            y=sh["density"],
            line={"color": color},
            name=f"{t('risk_dist_model')} ({rep['selected_model']})",
        )
    )
    fig.update_layout(
        height=420,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
        xaxis_title="log getiri",
        legend={"orientation": "h", "y": 1.08},
    )
    st.plotly_chart(fig, use_container_width=True)

# ----------------------------------------------------------------------------- critic
st.subheader(t("risk_critic_header"), help=t("risk_critic_help"))
rows = []
for mres in rep["models"]:
    row = {
        "Model": mres["name"],
        "Puan": mres["score"],
        "VaR %99 (1g)": mres["var99_1d"],
        "CVaR %99 (1g)": mres["cvar99_1d"],
    }
    for k in ("ks_1d", "wasserstein_1d", "q01_1d", "ks_10d", "wasserstein_10d", "kurt_10d"):
        row[k] = mres["critic"].get(k)
    rows.append(row)
ct = pd.DataFrame(rows).sort_values("Puan", na_position="last")


def _hl(r):
    sel = r["Model"] == rep["selected_model"]
    return ["background-color: rgba(46,111,186,0.25); font-weight: 600" if sel else ""] * len(r)


st.dataframe(
    ct.style.apply(_hl, axis=1).format(
        {"Puan": "{:.2f}", "VaR %99 (1g)": "{:.2%}", "CVaR %99 (1g)": "{:.2%}"}
        | {k: "{:.3f}" for k in ct.columns[4:]},
        na_rep="—",
    ),
    hide_index=True,
    use_container_width=True,
)
c1, c2 = st.columns(2)
c1.write(
    f"**{t('risk_sensitivity')}:** "
    + ", ".join(f"{k}: {v}" for k, v in rep["selection_by_scheme"].items())
)
failed = [f"{x['name']}: {x['failure_reason']}" for x in rep["models"] if not x["fitted"]]
if failed:
    c2.warning(f"**{t('risk_failed')}:** " + "; ".join(failed))

# ----------------------------------------------------------------------------- EVT
st.subheader(t("risk_evt_header"))
evt = rep["evt"]
if evt.get("fitted"):
    st.write(
        f"{t('risk_evt_xi')}: **{evt['xi']:.3f}** · eşik (kayıp): {evt['threshold']:.2%} · "
        f"aşım: {evt['n_exceedances']} · küme: {evt['n_clusters']} · "
        f"gözlem: {evt['n_obs']}"
    )
else:
    st.info(f"{t('risk_evt_none')} ({evt.get('reason', '')})")

with st.expander("RiskReport (JSON)"):
    st.code(json.dumps(rep, ensure_ascii=False, indent=1)[:20000], language="json")

disclaimer_footer()
