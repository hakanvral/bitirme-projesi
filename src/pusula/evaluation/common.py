"""Shared helpers for the experiments: run folders, tables (CSV + LaTeX), figures (PNG + SVG).

Every experiment writes to ``results/<experiment>/<timestamp>/`` together with a copy of the
configuration it used (CLAUDE.md §2.3), and ``results/<experiment>/latest.txt`` points to the
newest run so the dashboard and ``paper_results`` can find it.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from pusula.config import CONFIG_DIR, get_settings, load_yaml

CONFIG_FILES = [
    "settings.yaml",
    "regimes.yaml",
    "scenarios.yaml",
    "universe.yaml",
    "energy_selected.yaml",
    "corporate_actions.yaml",
]


def results_root() -> Path:
    return get_settings().paths.results_dir


def new_run_dir(experiment: str, params: dict | None = None) -> Path:
    root = results_root() / experiment
    out = root / datetime.now().strftime("%Y%m%d_%H%M%S")
    (out / "config").mkdir(parents=True, exist_ok=True)
    cfg_dir = CONFIG_DIR
    for name in CONFIG_FILES:
        if (cfg_dir / name).exists():
            shutil.copy2(cfg_dir / name, out / "config" / name)
    if params is not None:
        (out / "config" / "run_params.json").write_text(
            json.dumps(params, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
        )
    return out


def mark_latest(out: Path) -> None:
    (out.parent / "latest.txt").write_text(out.name, encoding="utf-8")


def latest_run(experiment: str) -> Path | None:
    root = results_root() / experiment
    marker = root / "latest.txt"
    if marker.exists():
        p = root / marker.read_text(encoding="utf-8").strip()
        if p.exists():
            return p
    runs = sorted(p for p in root.glob("2*") if p.is_dir()) if root.exists() else []
    return runs[-1] if runs else None


def save_table(
    df: pd.DataFrame,
    out: Path,
    name: str,
    floatfmt: str = "{:.3f}",
    index: bool = False,
    caption: str | None = None,
) -> None:
    """CSV (full precision) + LaTeX (rounded) copy of one result table."""
    df.to_csv(out / f"{name}.csv", index=index)
    fmt = {
        c: (lambda x, f=floatfmt: "" if pd.isna(x) else f.format(x))
        for c in df.columns
        if pd.api.types.is_float_dtype(df[c])
    }
    tex = df.to_latex(
        index=index, formatters=fmt, escape=True, caption=caption, label=f"tab:{name}"
    )
    (out / f"{name}.tex").write_text(tex, encoding="utf-8")


def save_fig(fig, out: Path, name: str) -> list[str]:
    """PNG (200 dpi) + SVG of a matplotlib figure; returns the file names."""
    files = [f"{name}.png", f"{name}.svg"]
    fig.savefig(out / files[0], dpi=200, bbox_inches="tight")
    fig.savefig(out / files[1], bbox_inches="tight")
    import matplotlib.pyplot as plt

    plt.close(fig)
    return files


def regime_of(dates: pd.Series | pd.DatetimeIndex) -> pd.Series:
    """Regime id for each date (config/regimes.yaml, inclusive start, exclusive end)."""
    cfg = load_yaml("regimes.yaml")
    d = pd.Series(pd.to_datetime(dates))
    out = pd.Series(None, index=d.index, dtype=object)
    for r in cfg["regimes"]:
        lo = pd.Timestamp(r["start"])
        hi = pd.Timestamp(r["end"]) if r.get("end") else pd.Timestamp.max
        out[(d >= lo) & (d < hi)] = r["id"]
    return out
