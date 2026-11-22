"""Ayarlar (CLAUDE.md §7): provider/model, key status (never the key), token usage."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pusula.app.components.data_access import store
from pusula.app.components.layout import disclaimer_footer
from pusula.app.i18n_tr import t
from pusula.config import get_secrets
from pusula.llm.factory import provider_info, shared_cache

st.title(f"⚙️ {t('set_title')}")
st.subheader(t("set_provider"))
info = provider_info()
st.dataframe(
    pd.DataFrame({"": list(info), "değer": [str(v) for v in info.values()]}), hide_index=True
)
st.subheader(t("set_keys"))
st.dataframe(
    pd.DataFrame(
        [
            {"anahtar": k, "durum": t("set_key_set") if v else t("set_key_missing")}
            for k, v in get_secrets().key_status().items()
        ]
    ),
    hide_index=True,
)
st.subheader(t("set_usage"))
u = store().query(
    "SELECT model, agent, count(*) AS cagri, sum(CASE WHEN cached THEN 0 ELSE 1 END) AS canli, "
    "sum(input_tokens) AS girdi_token, sum(output_tokens) AS cikti_token, "
    "round(avg(latency_s), 1) AS ort_sure_sn, sum(json_failures) AS json_hatasi, "
    "sum(cost_usd) AS maliyet_usd FROM llm_usage GROUP BY model, agent ORDER BY model, agent"
)
if u.empty:
    st.info(t("no_data"))
else:
    tot = u[["cagri", "canli", "girdi_token", "cikti_token", "json_hatasi"]].sum()
    c = st.columns(5)
    for col, (k, v) in zip(c, tot.items(), strict=True):
        col.metric(k, int(v))
    st.caption(t("set_usage_by"))
    st.dataframe(u, hide_index=True, use_container_width=True)
st.caption(t("set_cost_note"))
st.caption(t("set_cache").format(n=len(shared_cache())))
disclaimer_footer()
