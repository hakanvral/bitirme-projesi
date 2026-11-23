"""Genel Bakış (CLAUDE.md §7): macro snapshot and the risk heatmap of both universes. No LLM."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from pusula.app.components.data_access import latest_session, store
from pusula.app.components.layout import disclaimer_footer
from pusula.app.i18n_tr import t

st.title(f"🧭 {t('app_title')}: {t('nav_home')}")
st.caption(t("app_subtitle"))

# Series shown in the snapshot: (key, source, label key, unit, decimals)
SNAPSHOT = [
    ("policy_rate", "macro", "ov_policy", "%", 2),
    ("tlref", "macro", "ov_tlref", "%", 2),
    ("usdtry", "macro", "ov_usdtry", "", 4),
    ("cpi_yoy", "cpi", "ov_cpi", "%", 2),
    ("brent", "macro", "ov_brent", "$", 2),
    ("ttf", "macro", "ov_ttf", "€", 2),
    ("cds_5y", "macro", "ov_cds", "bp", 0),
    ("XU100.IS", "price", "ov_xu100", "", 0),
]


@st.cache_data(ttl=600, show_spinner=False)
def _snapshot(as_of: date) -> pd.DataFrame:
    """Latest value, value ~1 week earlier and the date of each snapshot series (only data
    available on ``as_of``; CPI only after its release date)."""
    db = store()
    ts = pd.Timestamp(as_of)
    macro = db.macro()
    macro = macro[macro["date"] <= ts]
    rows = []
    for key, src, label, unit, nd in SNAPSHOT:
        if src == "macro":
            s = macro[macro["series"] == key].set_index("date")["value"].sort_index()
        elif src == "price":
            p = db.prices(end=as_of)
            s = p[p["ticker"] == key].set_index("date")["adj_close"].sort_index()
        else:  # annual CPI inflation from the index, released prints only
            c = macro[(macro["series"] == "cpi") & (macro["release_date"] <= ts)]
            c = c.set_index("date")["value"].sort_index()
            s = (c / c.shift(12) - 1).dropna() * 100
        s = s.dropna()
        if s.empty:
            rows.append({"key": key, "label": t(label), "value": None})
            continue
        prev = s[s.index <= s.index[-1] - pd.Timedelta(days=7)]
        rows.append(
            {
                "key": key,
                "label": t(label),
                "value": float(s.iloc[-1]),
                "prev": float(prev.iloc[-1]) if not prev.empty and src != "cpi" else None,
                "date": s.index[-1].date(),
                "unit": unit,
                "nd": nd,
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=600, show_spinner=False)
def _risk_table(as_of: date) -> tuple[date | None, pd.DataFrame]:
    db = store()
    d = db.query(
        "SELECT max(as_of) AS d FROM risk_reports WHERE basis = 'TRY' AND as_of <= ?", [as_of]
    )["d"].iloc[0]
    if pd.isna(d):
        return None, pd.DataFrame()
    d = pd.Timestamp(d).date()
    tab = db.query(
        "SELECT ticker, universe, sub_sector, in_bist30, risk_level, risk_score, vol_ann, "
        "cvar99_1d, selected_model FROM risk_reports WHERE as_of = ? AND basis = 'TRY'",
        [d],
    )
    return d, tab


as_of = latest_session()
snap = _snapshot(as_of)
st.subheader(t("ov_macro"))
cols = st.columns(4)
for i, r in enumerate(snap.itertuples()):
    c = cols[i % 4]
    if r.value is None or (isinstance(r.value, float) and np.isnan(r.value)):
        c.metric(r.label, "—")
        continue
    fmt = f"{{:,.{int(r.nd)}f}}"
    val = fmt.format(r.value).replace(",", "X").replace(".", ",").replace("X", ".")
    shown = f"%{val}" if r.unit == "%" else (f"{val} {r.unit}" if r.unit else val)
    delta = None
    if r.prev is not None and not pd.isna(r.prev):
        if r.key in ("policy_rate", "tlref", "cds_5y"):
            delta = f"{r.value - r.prev:+.2f}".replace(".", ",") + (
                " bp" if r.unit == "bp" else " puan"
            )
        else:
            chg = (r.value / r.prev - 1) * 100
            delta = ("+" if chg >= 0 else "−") + f"%{abs(chg):.2f}".replace(".", ",")
    c.metric(r.label, shown, delta, delta_color="off", help=t("ov_as_of").format(d=r.date))
st.caption(t("ov_delta_note"))

# ----------------------------------------------------------------------------- risk heatmap
d, tab = _risk_table(as_of)
st.subheader(t("ov_heatmap"), help=t("risk_level_help"))
if tab.empty:
    st.info(t("risk_level_missing"))
else:
    st.caption(t("ov_heatmap_note").format(d=d))
    per_row = 6
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=["BIST30", t("universe_energy")],
        horizontal_spacing=0.04,
        column_widths=[0.62, 0.38],
    )
    groups = {
        "BIST30": tab[(tab["universe"] == "BIST30") | tab["in_bist30"]].drop_duplicates("ticker"),
        "Energy": tab[tab["universe"] == "Energy"],
    }
    for k, (u, g) in enumerate(groups.items(), start=1):
        g = g.sort_values("risk_score", ascending=False).reset_index(drop=True)
        n_cols = per_row if u == "BIST30" else 3
        n_rows = int(np.ceil(len(g) / n_cols))
        z = np.full((n_rows, n_cols), np.nan)
        txt = np.full((n_rows, n_cols), "", dtype=object)
        hover = np.full((n_rows, n_cols), "", dtype=object)
        for i, r in g.iterrows():
            rr, cc = divmod(i, n_cols)
            z[rr, cc] = r["risk_score"]
            name = r["ticker"].removesuffix(".IS")
            lvl = t(f"risk_level_{r['risk_level']}")
            txt[rr, cc] = f"<b>{name}</b><br>{lvl}"
            hover[rr, cc] = t("ov_hover").format(
                n=name,
                lvl=lvl,
                s=r["risk_score"],
                v=r["vol_ann"] * 100,
                c=r["cvar99_1d"] * 100,
                m=r["selected_model"],
            )
        fig.add_trace(
            go.Heatmap(
                z=z,
                text=txt,
                texttemplate="%{text}",
                hovertext=hover,
                hoverinfo="text",
                colorscale=[[0, "#2E9E5B"], [0.5, "#F2C14E"], [1, "#C0392B"]],
                zmin=0,
                zmax=100,
                xgap=3,
                ygap=3,
                showscale=k == 2,
                colorbar={"title": t("ov_score")},
            ),
            row=1,
            col=k,
        )
    fig.update_xaxes(showticklabels=False, showgrid=False, zeroline=False, ticks="")
    fig.update_yaxes(
        showticklabels=False, showgrid=False, zeroline=False, ticks="", autorange="reversed"
    )
    fig.update_layout(height=430, margin={"t": 40, "b": 10, "l": 10, "r": 10})
    st.plotly_chart(fig, use_container_width=True)
    st.caption(t("ov_overlap_note"))

with st.expander(t("ov_about")):
    st.markdown(t("home_intro"))
    st.markdown(t("home_universes"))

disclaimer_footer()
