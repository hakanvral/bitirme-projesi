"""Rendering helpers for agent outputs (shared by the agent, risk and scenario pages)."""

from __future__ import annotations

import streamlit as st

from pusula.app.i18n_tr import t

KARAR_COLOR = {"AL": "#2E8B57", "ALMA": "#C0392B", "BEKLE": "#D68910"}


def bullets(items: list[str]) -> None:
    for x in items or []:
        st.markdown(f"- {x}")


def risk_report(r: dict) -> None:
    st.markdown(f"**{t('ag_summary')}:** {r['ozet']}")
    st.markdown(f"**{t('ag_level_expl')}:** {r['risk_duzeyi_aciklamasi']}")
    st.markdown(f"**{t('ag_drivers')}:**")
    bullets(r["ana_risk_kaynaklari"])
    st.markdown(f"**{t('ag_meaning')}** {r['metriklerin_anlami']}")
    if r.get("veri_kisitlari"):
        st.markdown(f"**{t('ag_limits')}:**")
        bullets(r["veri_kisitlari"])
    st.caption(r["uyari"])


def scenario_report(r: dict) -> None:
    st.markdown(f"**{t('ag_summary')}:** {r['ozet']}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{t('ag_hurt')}:**")
        bullets(r["zarar_veren_senaryolar"])
    with c2:
        st.markdown(f"**{t('ag_help')}:**")
        bullets(r["fayda_saglayan_senaryolar"])
    st.markdown(f"**{t('ag_sensitive')}:** {r['en_hassas_faktor']}")
    st.markdown(f"**{t('ag_contrast')}:** {r['bist30_enerji_karsilastirmasi']}")
    if r.get("veri_kisitlari"):
        st.markdown(f"**{t('ag_limits')}:**")
        bullets(r["veri_kisitlari"])
    st.caption(r["uyari"])


def decision_card(d: dict) -> None:
    color = KARAR_COLOR.get(d["karar"], "#555")
    st.markdown(
        f"<div style='border:2px solid {color};border-radius:10px;padding:14px 18px'>"
        f"<div style='font-size:2rem;font-weight:700;color:{color}'>{d['karar']}</div>"
        f"<div>{t('ag_confidence')}: <b>{d['guven']:.2f}</b> · {t('ag_horizon')}: "
        f"<b>{d.get('vade', '—')}</b></div></div>",
        unsafe_allow_html=True,
    )
    if "lehte_gerekceler" in d:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**{t('ag_for')}**")
            bullets(d["lehte_gerekceler"])
        with c2:
            st.markdown(f"**{t('ag_against')}**")
            bullets(d["aleyhte_gerekceler"])
        st.markdown(f"**{t('ag_risks')}**")
        bullets(d["temel_riskler"])
        st.markdown(f"**{t('ag_conditions')}**")
        bullets(d["karari_degistirecek_kosullar"])
        st.caption(d["uyari"])
    else:
        st.write(d.get("kisa_gerekce", ""))


def audit_badge(a: dict) -> None:
    bad = ", ".join(i["text"] for i in a["numeric_issues"]) or "—"
    msg = t("ag_audit_numbers").format(n=a["numbers_checked"], bad=bad)
    if a.get("consistency_issues"):
        msg += " · " + "; ".join(a["consistency_issues"])
    (st.success if a["passed"] else st.warning)(
        f"**{t('ag_audit_ok') if a['passed'] else t('ag_audit_fail')}** — {msg}"
    )
    if a.get("regenerated"):
        st.caption(f"{t('ag_regenerated')}: {', '.join(a['regenerated'])}")
