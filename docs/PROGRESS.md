# Progress

## P0 · Setup: ✅ done (2026-11-16)
- uv project (Python 3.12), ruff and pytest config, `.env.example`, `.gitignore`.
- `config/settings.yaml` (dates incl. `selection_date`, LLM training cutoff), `config/regimes.yaml`.
- `pusula.config` (typed settings, secrets as `SecretStr`), `pusula.logging_setup`.
- Streamlit entry `src/pusula/app/Home.py` (`st.navigation`), Turkish strings in `app/i18n_tr.py`, disclaimer footer.
- Docs: Turkish README, `DECISIONS.md` (D-001…D-012), `LIMITATIONS.md`, this file.
- Verified: `uv run pytest` (7 passed), `ruff check` clean, the Streamlit home page renders with the disclaimer.
