"""Shared UI pieces for the macro pages."""

from __future__ import annotations

import streamlit as st

from pusula.app.i18n_tr import TR, t

KNOWN = ("cds", "ptf", "tr_2y")


def missing_input_warnings(missing: list[str]) -> None:
    """Clear warning for optional inputs that are absent or too short (D-046, D-049)."""
    msgs = []
    for m in missing:
        base, short = m.split("(")[0], m.endswith("(short)")
        if base == "cds_5y":
            base = "cds"
        if base not in KNOWN:
            continue
        key = (
            f"missing_{base}_short"
            if short and f"missing_{base}_short" in TR
            else f"missing_{base}"
        )
        msgs.append(t(key))
    if msgs:
        body = "\n- ".join(dict.fromkeys(msgs))
        st.warning(f"**{t('missing_header')}**\n\n- {body}\n\n{t('missing_fix')}")
