"""Rule-based, reproducible selection of 10 energy stocks (CLAUDE.md §4.2, D-002, D-016).

Only data up to ``settings.project.selection_date`` is used.

Steps
1. Eligibility: first price at least ``min_history_years`` before the selection date, and no
   trading gap (vs the XU100 calendar) longer than ``max_gap_days`` in that history window.
2. Liquidity: median daily traded value (close x volume, TRY) over the last ``liquidity_window``
   trading days before the selection date.
3. Size: no reliable historical market cap is available for free -> liquidity only (logged).
4. Composite score = average of the ranks (here: the liquidity rank).
5. Sub-sector quotas (>= 2 refining_petroleum, >= 2 natural_gas) are filled first with the best
   ranked names of each sub-sector; the remaining slots go to the best remaining names
   (in practice mostly electricity). Unmet quotas are reported.
6. Overlap with BIST30 (list at the selection date) is allowed and flagged.

Run:  uv run python -m pusula.universe.select_energy
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import yaml

from pusula.config import CONFIG_DIR, ROOT_DIR, get_settings
from pusula.data.panel import trading_calendar
from pusula.data.store import Store
from pusula.logging_setup import setup_logging
from pusula.universe.load import load_bist30, load_energy_candidates, to_yahoo

log = logging.getLogger(__name__)

DEFAULT_QUOTAS = {"refining_petroleum": 2, "natural_gas": 2}


@dataclass
class SelectionResult:
    scores: pd.DataFrame  # every candidate with metrics, ranks and selection flag
    selected: pd.DataFrame
    notes: list[str] = field(default_factory=list)


def _longest_gap(dates: pd.DatetimeIndex, calendar: pd.DatetimeIndex) -> int:
    """Longest run of consecutive calendar trading days without a price."""
    have = calendar.isin(dates)
    longest = cur = 0
    for h in have:
        cur = 0 if h else cur + 1
        longest = max(longest, cur)
    return longest


def select_energy(
    prices: pd.DataFrame,
    candidates: pd.DataFrame,
    selection_date: date,
    bist30: list[str],
    n: int = 10,
    quotas: dict[str, int] | None = None,
    min_history_years: int = 3,
    max_gap_days: int = 20,
    liquidity_window: int = 252,
    calendar_method: str = "xist",
) -> SelectionResult:
    quotas = DEFAULT_QUOTAS if quotas is None else quotas
    notes: list[str] = []
    cutoff = pd.Timestamp(selection_date)
    prices = prices[pd.to_datetime(prices["date"]) <= cutoff]  # point-in-time: nothing after
    calendar = trading_calendar(prices, method=calendar_method)
    hist_start = cutoff - pd.DateOffset(years=min_history_years)

    rows = []
    for _, c in candidates.iterrows():
        sym = to_yahoo(c["ticker"])
        p = prices[prices["ticker"] == sym].sort_values("date")
        row = {
            "ticker": c["ticker"],
            "name": c["name"],
            "sub_sector": c["sub_sector"],
            "verified": bool(c.get("verified", False)),
            "in_bist30": c["ticker"] in bist30,
            "first_date": None,
            "longest_gap": None,
            "median_traded_value_try": None,
            "eligible": False,
            "reason": "",
        }
        if p.empty:
            row["reason"] = "no price data"
            rows.append(row)
            continue
        dates = pd.DatetimeIndex(pd.to_datetime(p["date"]))
        row["first_date"] = dates.min().date()
        window_cal = calendar[calendar >= max(hist_start, dates.min())]
        row["longest_gap"] = _longest_gap(dates, window_cal)
        last = p.tail(liquidity_window)
        row["median_traded_value_try"] = float((last["close"] * last["volume"]).median())
        if dates.min() > hist_start:
            row["reason"] = f"history < {min_history_years}y"
        elif row["longest_gap"] > max_gap_days:
            row["reason"] = f"trading gap {row['longest_gap']}d > {max_gap_days}d"
        else:
            row["eligible"] = True
        rows.append(row)

    scores = pd.DataFrame(rows)
    elig = scores["eligible"]
    scores["rank_liquidity"] = scores.loc[elig, "median_traded_value_try"].rank(ascending=False)
    notes.append(
        "Size criterion skipped: no reliable point-in-time market cap -> "
        "composite = liquidity rank."
    )
    scores["composite_score"] = scores["rank_liquidity"]  # average of available ranks
    scores = scores.sort_values(["eligible", "composite_score"], ascending=[False, True])

    chosen: list[str] = []
    for sub, q in quotas.items():
        pool = scores[elig.loc[scores.index] & (scores["sub_sector"] == sub)]
        take = pool.head(q)["ticker"].tolist()
        if len(take) < q:
            notes.append(f"Quota not met: {sub} needs {q}, only {len(take)} eligible.")
        chosen += take
    rest = scores[elig.loc[scores.index] & ~scores["ticker"].isin(chosen)]
    chosen += rest.head(max(n - len(chosen), 0))["ticker"].tolist()
    if len(chosen) < n:
        notes.append(f"Only {len(chosen)} eligible candidates; target was {n}.")

    scores["selected"] = scores["ticker"].isin(chosen)
    if (~scores.loc[scores["selected"], "verified"]).any():
        notes.append("WARNING: some selected candidates are not verified (verified: false).")
    selected = scores[scores["selected"]].sort_values("composite_score")
    return SelectionResult(
        scores=scores.reset_index(drop=True), selected=selected.reset_index(drop=True), notes=notes
    )


# --------------------------------------------------------------------------- outputs
def write_outputs(res: SelectionResult, selection_date: date) -> None:
    out = {
        "selection_date": selection_date.isoformat(),
        "generated_by": "pusula.universe.select_energy",
        "notes": res.notes,
        "selected": [
            {
                "ticker": r.ticker,
                "name": r.name,
                "sub_sector": r.sub_sector,
                "in_bist30": bool(r.in_bist30),
                "verified": bool(r.verified),
            }
            for r in res.selected.itertuples()
        ],
    }
    (CONFIG_DIR / "energy_selected.yaml").write_text(
        "# GENERATED - do not edit by hand.\n"
        "# Re-run: uv run python -m pusula.universe.select_energy\n"
        + yaml.safe_dump(out, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    cols = [
        "ticker",
        "name",
        "sub_sector",
        "verified",
        "in_bist30",
        "first_date",
        "longest_gap",
        "median_traded_value_try",
        "rank_liquidity",
        "eligible",
        "reason",
        "selected",
    ]
    tbl = res.scores[cols].copy()
    tbl["median_traded_value_try"] = (tbl["median_traded_value_try"] / 1e6).round(1)
    tbl = tbl.rename(columns={"median_traded_value_try": "median_value_mn_try"})
    md = [
        "# Energy universe selection",
        "",
        f"Selection date: **{selection_date}** (only data up to this date is used; D-002).",
        "Generated by `uv run python -m pusula.universe.select_energy`.",
        "",
        "## Rules",
        "Eligibility: >= 3 years of history and no trading gap > 20 days. Liquidity: median "
        "close x volume over the last 252 trading days. Composite = average rank. Quotas: >= 2 "
        "refining_petroleum, >= 2 natural_gas.",
        "",
        "## Notes",
        *[f"- {n}" for n in res.notes],
        "",
        "## Score table",
        "",
        tbl.to_markdown(index=False),
        "",
    ]
    (ROOT_DIR / "docs" / "universe_selection.md").write_text("\n".join(md), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    setup_logging()
    s = get_settings()
    store = Store(s.paths.db_path, s.paths.raw_dir)
    prices = store.prices(end=s.project.selection_date)
    res = select_energy(
        prices, load_energy_candidates(), s.project.selection_date, load_bist30("selection")
    )
    write_outputs(res, s.project.selection_date)
    store.replace_universe(
        "energy",
        s.project.selection_date,
        res.selected.assign(ticker=res.selected["ticker"]),
    )
    for n in res.notes:
        log.info(n)
    print(
        res.scores[
            ["ticker", "sub_sector", "eligible", "reason", "rank_liquidity", "selected"]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
