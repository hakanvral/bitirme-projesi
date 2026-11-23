"""Regenerate every paper table and figure (CLAUDE.md §6.5).

    uv run python -m pusula.evaluation.paper_results              # E1–E5, asks before LLM work
    uv run python -m pusula.evaluation.paper_results --yes        # no confirmation prompts
    uv run python -m pusula.evaluation.paper_results --no-llm     # E1–E3 + E4 evaluation only
    uv run python -m pusula.evaluation.paper_results --collect-only

Steps: E1 (VaR backtest), E2 (factor model), E3 (event study), E4 (decision backtest; its LLM
stage reuses the response cache, so a repeat costs no requests), E5 (LLM reliability, also cached),
then the key CSV/LaTeX tables and PNG/SVG figures of the latest runs are copied into
``results/paper/<timestamp>/`` with an ``index.md``.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime

from pusula.config import get_settings
from pusula.evaluation.common import latest_run
from pusula.logging_setup import setup_logging

KEY_FILES = {
    "e1_var": ["e1_key_table", "e1_critic_comparison", "e1_model_selection_shares",
               "e1_exceedance_rates", "e1_rolling_exceedance_var99"],
    "e2_factor": ["e2_universe_comparison", "e2_by_subsector", "e2_beta_stability",
                  "e2_regime_sensitivities", "e2_beta_heatmap", "e2_r2_is_oos"],
    "e3_event": ["e3_scores", "e3_realised_by_direction", "e3_holds_realised",
                 "e3_pred_vs_realised", "e3_event_car_by_universe"],
    "e4_backtest": ["e4_stocks", "e4_performance", "e4_sharpe_diff_ci", "e4_decision_distribution",
                    "e4_long_sample_2019_2026", "e4_long_sample_sharpe_ci", "e4_equity_curves"],
    "e5_llm": ["e5_agreement_summary", "e5_pairwise_agreement", "e5_decision_distribution",
               "e5_full_mode_audit", "e5_usage_by_agent"],
}  # fmt: skip


def collect() -> str:
    out = get_settings().paths.results_dir / "paper" / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# Paper tables and figures", "", f"Collected {datetime.now():%Y-%m-%d %H:%M}.", ""]
    for exp, names in KEY_FILES.items():
        run = latest_run(exp)
        lines += [f"## {exp}", ""]
        if run is None:
            lines += ["(not run yet)", ""]
            continue
        lines.append(f"Source run: `{run}`")
        lines.append("")
        for n in names:
            for ext in (".csv", ".tex", ".png", ".svg"):
                f = run / f"{n}{ext}"
                if f.exists():
                    shutil.copy2(f, out / f.name)
                    lines.append(f"- `{f.name}`")
        lines.append("")
    (out / "index.md").write_text("\n".join(lines), encoding="utf-8")
    return str(out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="no confirmation before LLM batches")
    ap.add_argument("--no-llm", action="store_true", help="skip new LLM calls (E4 eval only)")
    ap.add_argument("--collect-only", action="store_true")
    a = ap.parse_args(argv)
    setup_logging("WARNING")
    if not a.collect_only:
        from pusula.evaluation import event_study, factor_eval, trading_backtest, var_backtest

        print("E1 …", var_backtest.run(), flush=True)
        print("E2 …", factor_eval.run(), flush=True)
        print("E3 …", event_study.run(), flush=True)
        stages = ["eval"] if a.no_llm else ["risk", "inputs", "llm", "eval"]
        trading_backtest.main(["--stages", *stages, *(["--yes"] if a.yes else [])])
        if not a.no_llm:
            from pusula.evaluation import llm_reliability

            llm_reliability.main(["--yes"] if a.yes else [])
    print("Collected:", collect())


if __name__ == "__main__":
    main()
