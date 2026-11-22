"""BIST30 vs Enerji (CLAUDE.md §7): beta heatmap, group comparison, scenario sensitivity."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from pusula.app.components.data_access import latest_session, store
from pusula.app.components.layout import disclaimer_footer
from pusula.app.components.macro_ui import missing_input_warnings
from pusula.app.components.theme import COLORS, SUBSECTOR_COLORS
from pusula.app.i18n_tr import t
from pusula.config import get_regimes
from pusula.macro.context import build_context, current_passthrough, make_engine
from pusula.macro.factor_model import regime_betas, rolling_betas, vif
from pusula.macro.scenarios import load_presets, to_factor_shocks, universe_summary

st.title(f"⚖️ {t('cmp_title')}")


@st.cache_resource(show_spinner=False, max_entries=4)
def _ctx(as_of: date):
    return build_context(store(), as_of)


@st.cache_data(show_spinner=False, max_entries=4)
def _sensitivity(as_of: date) -> pd.DataFrame:
    ctx = _ctx(as_of)
    eng = make_engine(ctx)
    pt = current_passthrough(ctx)
    rows = []
    for sc in load_presets():
        spec = to_factor_shocks(sc.shocks, eng.factors, pt)
        if not spec.factor_shocks:
            continue
        us = universe_summary(eng.run(spec, "3m", "propagated")["stocks"])
        rows.append(us.assign(scenario=sc.name_tr))
    return pd.concat(rows, ignore_index=True)


as_of = latest_session()
ctx = _ctx(as_of)
missing_input_warnings(ctx.fp.missing)
mem = ctx.members[ctx.members["symbol"].isin(ctx.fits_a)].copy()
mem["sub_sector"] = mem["sub_sector"].where(mem["sub_sector"].notna(), "")
mem = mem.sort_values(["universe", "sub_sector", "ticker"])
factors = [f for f in ctx.fp.X.columns]
sd = ctx.fp.X.std()

# ----------------------------------------------------------------------------- heatmap
st.subheader(t("cmp_heatmap"), help=t("cmp_heat_help"))
scale = st.radio(
    "",
    ["std", "raw"],
    format_func=lambda k: t(f"cmp_{k}"),
    horizontal=True,
    label_visibility="collapsed",
)
Z, txt, ylab = [], [], []
for r in mem.itertuples():
    f = ctx.fits_a[r.symbol]
    row, trow = [], []
    for c in factors:
        b = f.beta.get(c, np.nan)
        v = b * sd[c] if scale == "std" else b
        row.append(v * 100 if scale == "std" else v)
        star = "*" if f.pval.get(c, 1) < 0.05 else ""
        trow.append("" if np.isnan(v) else f"{(v * 100 if scale == 'std' else v):.2f}{star}")
    Z.append(row)
    txt.append(trow)
    grp = "Enerji · " + t(f"subsector_{r.sub_sector}") if r.universe == "Energy" else "BIST30"
    ylab.append(f"{r.ticker} ({grp})")
# robust colour scale: one extreme beta should not wash out the others
zmax = float(np.nanpercentile(np.abs(Z), 95)) if len(Z) else 1.0
fig = go.Figure(
    go.Heatmap(
        z=Z,
        x=[t(f"factor_{c}") for c in factors],
        y=ylab,
        text=txt,
        texttemplate="%{text}",
        colorscale="RdBu",
        zmid=0,
        zmin=-zmax,
        zmax=zmax,
        colorbar={"title": "% / 1σ" if scale == "std" else "β"},
    )
)
fig.update_layout(
    height=22 * len(ylab) + 120,
    margin={"l": 10, "r": 10, "t": 10, "b": 10},
    yaxis={"autorange": "reversed"},
)
st.plotly_chart(fig, use_container_width=True)

# ----------------------------------------------------------------------------- groups
st.subheader(t("cmp_group"))
rows = []
for r in mem.itertuples():
    f = ctx.fits_a[r.symbol]
    grp = "BIST30" if r.universe == "BIST30" else r.sub_sector
    for c in factors:
        rows.append({"group": grp, "factor": c, "std_beta": f.beta.get(c, np.nan) * sd[c] * 100})
g = pd.DataFrame(rows).groupby(["group", "factor"], as_index=False)["std_beta"].mean()
fig = go.Figure()
for grp, gg in g.groupby("group"):
    color = COLORS["BIST30"] if grp == "BIST30" else SUBSECTOR_COLORS.get(grp, COLORS["Energy"])
    name = grp if grp == "BIST30" else f"Enerji · {t('subsector_' + grp)}"
    fig.add_trace(
        go.Bar(
            x=[t(f"factor_{c}") for c in gg["factor"]],
            y=gg["std_beta"],
            name=name,
            marker_color=color,
        )
    )
fig.update_layout(
    barmode="group", height=360, yaxis_title="% / 1σ", margin={"l": 10, "r": 10, "t": 10, "b": 10}
)
st.plotly_chart(fig, use_container_width=True)

# ----------------------------------------------------------------------------- sensitivity
st.subheader(t("cmp_sens"))
sens = _sensitivity(as_of)
samp = st.radio(
    "",
    ["all", "no_overlap"],
    horizontal=True,
    label_visibility="collapsed",
    format_func=lambda k: t("sc_all") if k == "all" else t("sc_no_overlap"),
)
s2 = sens[sens["sample"] == samp]
fig = go.Figure()
for u in ["BIST30", "Energy"]:
    su = s2[s2["universe"] == u]
    fig.add_trace(
        go.Bar(
            y=su["scenario"],
            x=su["d_exp_ret"] * 100,
            orientation="h",
            name="BIST30" if u == "BIST30" else t("universe_energy"),
            marker_color=COLORS[u],
        )
    )
fig.update_layout(
    barmode="group",
    height=480,
    xaxis_title=f"{t('sc_d_exp')} (%)",
    margin={"l": 10, "r": 10, "t": 10, "b": 10},
)
st.plotly_chart(fig, use_container_width=True)

# ----------------------------------------------------------------------------- R2 + VIF
c1, c2 = st.columns(2)
with c1:
    st.subheader(t("cmp_r2"))
    r2 = pd.DataFrame(
        [
            {
                "Hisse": r.ticker,
                "Evren": "BIST30" if r.universe == "BIST30" else t("universe_energy"),
                "R² A": ctx.fits_a[r.symbol].r2,
                "R² B": ctx.fits_b[r.symbol].r2,
                "Hafta": ctx.fits_a[r.symbol].n,
            }
            for r in mem.itertuples()
        ]
    )
    st.dataframe(r2.groupby("Evren")[["R² A", "R² B"]].mean().style.format("{:.3f}"))
    st.dataframe(
        r2.style.format({"R² A": "{:.3f}", "R² B": "{:.3f}"}),
        hide_index=True,
        height=300,
        use_container_width=True,
    )
with c2:
    st.subheader(t("cmp_vif"))
    v = vif(ctx.fp.X.dropna())
    st.dataframe(
        pd.DataFrame(
            {"Faktör": [t(f"factor_{k}") for k in v], "VIF": list(v.values())}
        ).style.format({"VIF": "{:.2f}"}),
        hide_index=True,
    )
    st.caption("VIF > 5–10: faktör diğerleriyle güçlü örtüşüyor; tekil beta güvenilmez olabilir.")

# ----------------------------------------------------------------------------- per stock
st.subheader(t("cmp_rolling"))
c1, c2 = st.columns(2)
sym = c1.selectbox(t("stock"), list(dict.fromkeys(mem["symbol"])))
fac = c2.selectbox("Faktör", ctx.fits_a[sym].factors, format_func=lambda f: t(f"factor_{f}"))
fit = ctx.fits_a[sym]
rb = rolling_betas(ctx.fp.returns[sym], ctx.fp.X[fit.factors])
fig = go.Figure(go.Scatter(x=rb.index, y=rb[fac], line={"color": COLORS["BIST30"]}))
fig.add_hline(y=fit.beta[fac], line_dash="dash", annotation_text="tüm örneklem")
for rg in get_regimes().regimes:
    fig.add_vline(x=pd.Timestamp(rg.start), line_dash="dot", line_color="#999")
fig.update_layout(height=320, margin={"l": 10, "r": 10, "t": 10, "b": 10}, yaxis_title="β")
st.plotly_chart(fig, use_container_width=True)

c1, c2 = st.columns(2)
with c1:
    st.subheader(t("cmp_regime"))
    rbt = regime_betas(ctx.fp.returns[sym], ctx.fp.X[fit.factors], get_regimes(), sym)
    if rbt.empty:
        st.info(t("no_data"))
    else:
        piv = rbt.pivot_table(index="factor", columns="regime", values="beta")
        piv.index = [t(f"factor_{f}") for f in piv.index]
        st.dataframe(piv.style.format("{:.3f}"), use_container_width=True)
with c2:
    st.subheader(t("cmp_ridge"))
    rt = pd.DataFrame(
        {
            "Faktör": [t(f"factor_{c}") for c in fit.factors],
            "OLS β": [fit.beta[c] for c in fit.factors],
            "Newey–West p": [fit.pval[c] for c in fit.factors],
            "Ridge β": [fit.ridge_beta.get(c) for c in fit.factors],
            "VIF": [fit.vif.get(c) for c in fit.factors],
        }
    )
    st.dataframe(
        rt.style.format(
            {"OLS β": "{:.4f}", "Newey–West p": "{:.3f}", "Ridge β": "{:.4f}", "VIF": "{:.2f}"}
        ),
        hide_index=True,
    )
    st.caption(f"Ridge λ = {fit.ridge_lambda:.3g} (GCV) · Newey–West gecikme = {fit.hac_lags}")

disclaimer_footer()
