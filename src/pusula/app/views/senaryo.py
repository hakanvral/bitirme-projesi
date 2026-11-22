"""Senaryo Laboratuvarı (CLAUDE.md §7): macro shocks -> stock return distributions. No LLM."""

from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from pusula.app.components.data_access import latest_session, store
from pusula.app.components.layout import disclaimer_footer
from pusula.app.components.macro_ui import missing_input_warnings
from pusula.app.components.theme import COLORS
from pusula.app.i18n_tr import t
from pusula.macro.analogues import find_analogues
from pusula.macro.context import build_context, current_passthrough, make_engine
from pusula.macro.scenarios import HORIZONS, load_presets, to_factor_shocks, universe_summary

st.title(f"🧪 {t('sc_title')}")


@st.cache_resource(show_spinner=False, max_entries=4)
def _ctx(as_of: date):
    return build_context(store(), as_of)


@st.cache_resource(show_spinner=False, max_entries=8)
def _engine(as_of: date, cov: str):
    return make_engine(_ctx(as_of), cov)


@st.cache_data(show_spinner=False, max_entries=64)
def _run(as_of: date, shocks: tuple, horizon: str, mode: str, cov: str, basis: str):
    ctx, eng = _ctx(as_of), _engine(as_of, cov)
    spec = to_factor_shocks(dict(shocks), eng.factors, current_passthrough(ctx))
    if not spec.factor_shocks:
        return spec, None
    return spec, eng.run(spec, horizon, mode, basis)


# ----------------------------------------------------------------------------- controls
as_of = latest_session()
ctx = _ctx(as_of)
c1, c2, c3, c4 = st.columns(4)
horizon = c1.radio(t("sc_horizon"), list(HORIZONS), index=1, format_func=lambda h: t(f"sc_h_{h}"))
mode = c2.radio(t("sc_mode"), ["propagated", "isolated"], format_func=lambda m: t(f"sc_mode_{m}"))
cov = c3.radio(t("sc_cov"), ["current", "full"], format_func=lambda c: t(f"sc_cov_{c}"))
basis = c4.radio(t("sc_basis"), ["TRY", "USD", "REAL"], format_func=lambda k: t(f"basis_{k}"))
missing_input_warnings(ctx.fp.missing)
if basis == "REAL":
    if ctx.infl_exp_annual is None:
        st.info(t("sc_real_na"))
        disclaimer_footer()
        st.stop()
    st.caption(t("sc_real_note").format(pi=ctx.infl_exp_annual))
if basis == "USD":
    st.caption(t("sc_usd_note"))

presets = load_presets()
kind = st.radio("", [t("sc_preset"), t("sc_custom")], horizontal=True, label_visibility="collapsed")
if kind == t("sc_preset"):
    sc = st.selectbox(t("sc_preset"), presets, format_func=lambda s: s.name_tr)
    shocks = dict(sc.shocks)
else:
    avail = set(ctx.fp.X.columns)
    a, b, c = st.columns(3)
    rate_mode = a.radio(
        t("sc_rate_mode"),
        ["policy", "market"],
        format_func=lambda m: t(f"sc_rate_{m}"),
        horizontal=True,
    )
    rate_bp = a.slider(t(f"sc_rate_{rate_mode}"), -1000, 1000, 0, 25)
    shocks = {"policy_rate_bp" if rate_mode == "policy" else "market_rate_bp": rate_bp}
    shocks["usdtry_pct"] = b.slider(t("sc_usdtry"), -30, 50, 0, 1)
    shocks["brent_pct"] = b.slider(t("sc_brent"), -60, 100, 0, 5)
    shocks["ttf_pct"] = b.slider(t("sc_ttf"), -60, 150, 0, 5)
    shocks["cds_bp"] = c.slider(t("sc_cds"), -300, 500, 0, 25, disabled="cds" not in avail)
    shocks["vix_pts"] = c.slider(t("sc_vix"), -20, 40, 0, 1)
    shocks["us10y_bp"] = c.slider(t("sc_us10y"), -200, 200, 0, 10)

spec, res = _run(as_of, tuple(sorted(shocks.items())), horizon, mode, cov, basis)
if spec.ignored:
    st.warning(f"{t('sc_ignored')}: {', '.join(spec.ignored)}")
pt = current_passthrough(ctx)
if spec.rate_band and spec.policy_bp is not None and pt is not None:
    lo, mid, hi = spec.rate_band
    st.info(
        f"**{t('sc_passthrough')}:** "
        + t("sc_passthrough_text").format(
            bp=spec.policy_bp,
            src=ctx.fp.rate_source.replace("_spliced", "").upper(),
            mid=mid,
            lo=lo,
            hi=hi,
            regime=pt.regime,
            beta=pt.beta,
        )
    )
if res is None:
    st.info(t("sc_no_shock"))
    disclaimer_footer()
    st.stop()

stocks = res["stocks"]
_zmax = max((abs(v) for v in res.get("shock_z_regime", {}).values()), default=0.0)
if res.get("extrapolation_guard"):
    st.warning(t("sc_guard").format(z=_zmax))
elif _zmax > 4:
    st.warning(t("sc_guard_iso").format(z=_zmax))
st.caption(
    f"as_of {as_of} · {res['horizon_weeks']} hafta · kovaryans: {res['cov_source']} · "
    f"{len(stocks['symbol'].unique())} hisse · 10.000 simülasyon"
)

# ----------------------------------------------------------------------------- summary
st.subheader(t("sc_summary"))
us = universe_summary(stocks)
us["sample"] = us["sample"].map({"all": t("sc_all"), "no_overlap": t("sc_no_overlap")})
us["universe"] = us["universe"].map({"BIST30": "BIST30", "Energy": t("universe_energy")})
us = us.rename(
    columns={
        "universe": "Evren",
        "sample": "Örneklem",
        "n": "N",
        "d_exp_ret": t("sc_d_exp"),
        "d_var99": t("sc_d_var"),
        "d_cvar99": t("sc_d_cvar"),
        "d_p_loss": t("sc_d_ploss"),
        "median_d_exp_ret": t("sc_median"),
    }
)
st.dataframe(
    us.style.format({c: "{:+.2%}" for c in us.columns[3:]}),
    hide_index=True,
    use_container_width=True,
)

# ----------------------------------------------------------------------------- per stock
st.subheader(t("sc_by_stock"))
fig = make_subplots(
    rows=1, cols=2, subplot_titles=["BIST30", t("universe_energy")], horizontal_spacing=0.12
)
for i, u in enumerate(["BIST30", "Energy"], start=1):
    g = stocks[stocks["universe"] == u].sort_values("d_exp_ret")
    err = None
    if "scen_exp_ret_low" in g:
        lo = g[["scen_exp_ret_low", "scen_exp_ret_high"]].min(axis=1) - g["base_exp_ret"]
        hi = g[["scen_exp_ret_low", "scen_exp_ret_high"]].max(axis=1) - g["base_exp_ret"]
        err = {
            "type": "data",
            "symmetric": False,
            "array": (hi - g["d_exp_ret"]) * 100,
            "arrayminus": (g["d_exp_ret"] - lo) * 100,
        }
    fig.add_trace(
        go.Bar(
            x=g["d_exp_ret"] * 100,
            y=g["ticker"],
            orientation="h",
            marker_color=COLORS[u],
            error_x=err,
            showlegend=False,
        ),
        row=1,
        col=i,
    )
fig.update_xaxes(title_text=f"{t('sc_d_exp')} (%)")
n_max = int(stocks["universe"].value_counts().max())
fig.update_yaxes(tickmode="linear")
fig.update_layout(height=22 * n_max + 140, margin={"t": 40, "b": 10})
st.plotly_chart(fig, use_container_width=True)

tbl = stocks[
    [
        "ticker",
        "universe",
        "sub_sector",
        "base_exp_ret",
        "scen_exp_ret",
        "d_exp_ret",
        "d_var99",
        "d_cvar99",
        "d_p_loss",
        "rank_change",
    ]
].copy()
tbl["universe"] = tbl["universe"].map({"BIST30": "BIST30", "Energy": t("universe_energy")})
tbl["sub_sector"] = tbl["sub_sector"].map(
    lambda x: t(f"subsector_{x}") if isinstance(x, str) and x else ""
)
tbl = tbl.rename(
    columns={
        "ticker": t("stock"),
        "universe": "Evren",
        "sub_sector": "Alt sektör",
        "base_exp_ret": "Taban E[getiri]",
        "scen_exp_ret": "Senaryo E[getiri]",
        "d_exp_ret": t("sc_d_exp"),
        "d_var99": t("sc_d_var"),
        "d_cvar99": t("sc_d_cvar"),
        "d_p_loss": t("sc_d_ploss"),
        "rank_change": t("sc_rank"),
    }
)
fmt = {c: "{:+.2%}" for c in tbl.columns[3:9]} | {t("sc_rank"): "{:+.0f}"}
st.dataframe(tbl.style.format(fmt), hide_index=True, use_container_width=True, height=420)

# ----------------------------------------------------------------------------- implied factors
st.subheader(t("sc_implied"))
imp = res["implied"].copy()
imp["factor"] = imp["factor"].map(lambda f: t(f"factor_{f}"))
imp = imp.rename(
    columns={
        "factor": "Faktör",
        "baseline_mean": t("sc_implied_base"),
        "scenario_mean": t("sc_implied_scen"),
    }
)
st.dataframe(
    imp.style.format({t("sc_implied_base"): "{:+.4f}", t("sc_implied_scen"): "{:+.4f}"}),
    hide_index=True,
)
st.caption("Faiz, VIX, ABD 10Y: puan değişimi; USD/TRY, Brent, TTF: log değişim.")

# ----------------------------------------------------------------------------- analogues
st.subheader(t("sc_analogues"), help=t("sc_analogues_help"))
win, realised = find_analogues(ctx.fp.X, ctx.fp.returns, spec.factor_shocks, HORIZONS[horizon])
if win.empty:
    st.info(t("no_data"))
else:
    grp = ctx.members.drop_duplicates(["symbol", "universe"])
    avg = {
        u: realised.reindex(grp[grp["universe"] == u]["symbol"]).mean()
        for u in ["BIST30", "Energy"]
    }
    w = win.copy()
    w["start"], w["end"] = w["start"].dt.date, w["end"].dt.date
    w["BIST30 ort. getiri"] = avg["BIST30"].to_numpy()
    w["Enerji ort. getiri"] = avg["Energy"].to_numpy()
    w["XU100"] = realised.loc["XU100.IS"].to_numpy() if "XU100.IS" in realised.index else None
    fmtw = {c: "{:+.4f}" for c in w.columns if c.startswith("move_")}
    fmtw |= {
        "distance": "{:.2f}",
        "BIST30 ort. getiri": "{:+.2%}",
        "Enerji ort. getiri": "{:+.2%}",
        "XU100": "{:+.2%}",
    }
    st.dataframe(w.style.format(fmtw, na_rep="—"), hide_index=True, use_container_width=True)

# ----------------------------------------------------------------------------- Agent 2
st.subheader(t("ag_scenario_report"))
pick = st.selectbox(t("stock"), sorted(stocks["ticker"].unique()), key="ag_stock")
if st.button(t("ag_button_scenario")):
    from pusula.app.components.agent_ui import audit_badge
    from pusula.app.components.agent_ui import scenario_report as _render
    from pusula.pipeline import run_agent_report

    with st.spinner(t("ag_running")):
        try:
            rep_llm, usage, aud = run_agent_report(pick, as_of, "scenario_analyst")
            audit_badge(aud.model_dump())
            _render(rep_llm.model_dump())
            st.caption(
                f"{usage.model} · {usage.latency_s:.0f} sn · "
                f"{usage.input_tokens}+{usage.output_tokens} token"
            )
        except Exception as exc:
            st.error(f"{t('ag_error')}: {exc}")

disclaimer_footer()
