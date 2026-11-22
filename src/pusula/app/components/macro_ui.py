"""Shared UI pieces for the macro pages."""

from __future__ import annotations

import streamlit as st

from pusula.app.i18n_tr import t

KNOWN = ("cds", "ptf", "tr_2y")


def missing_input_warnings(missing: list[str]) -> None:
    """Clear warning for optional inputs that are not present (user requirement, D-046)."""
    msgs = [t(f"missing_{m}") for m in KNOWN if m in missing]
    if msgs:
        st.warning(
            f"**{t('missing_header')}**\n\n- " + "\n- ".join(msgs) + f"\n\n{t('missing_fix')}"
        )
