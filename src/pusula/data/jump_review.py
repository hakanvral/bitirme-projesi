"""Classify flagged stock price jumps and propose corrections (D-026).

    uv run python -m pusula.data.jump_review            # writes docs/price_jump_review.md
    uv run python -m pusula.data.jump_review --write    # also adds proposals to
                                                        # config/corporate_actions.yaml

Works on prices after the generic cleaning rules (D-025) but BEFORE any corporate action from the
YAML file, so every proposal is computed from vendor data only.

Classes (first match wins):

* ``market_event``: many stocks jump the same day, or XU100 moves >= 5% (e.g. the reopening on
  2023-02-15 after the earthquake closure, March 2020). Real moves, no correction.
* ``multi_day_gap``: the previous valid price is more than one session earlier, so the return
  covers several days and the daily limit does not apply. No correction.
* ``vendor_dividend_adjustment``: adjusted and unadjusted returns differ by more than 5pp, so
  Yahoo's dividend adjustment is wrong (typically an ex-dividend day adjusted in the wrong
  direction). Placeholder proposal: ``factor`` = (1+adj ret)/(1+XU100 ret), i.e. that day's
  total return is set to the market return. The exact factor is (P_cum - D)/P_cum with the
  dividend D per share from KAP.
* ``split_or_bonus_misadjustment``: |raw return| > 20.5%, beyond any BIST daily price band. The
  pre-date history is on a different share basis. Proposal: ``factor`` = (1+ret)/(1+XU100 ret),
  i.e. that day's return is replaced by the market return. Needs a KAP check (bonus / rights /
  split and its real ex-date).
* ``review``: 10.5% < |ret| <= 20.5%. Can be genuine (some segments had a ±20% band, IPO days,
  limit changes) or an error. No proposal; listed for the user.
"""

from __future__ import annotations

import argparse
from datetime import date

import pandas as pd
import yaml

from pusula.config import CONFIG_DIR, ROOT_DIR, get_settings
from pusula.data.cleaning import apply_generic_rules
from pusula.data.panel import trading_calendar
from pusula.data.quality import jump_flags
from pusula.data.store import Store
from pusula.logging_setup import setup_logging

MARKET_SHARE = 0.25  # share of stocks jumping the same day -> market event
MARKET_MOVE = 0.05
DIVIDEND_GAP = 0.05
BAND_MAX = 0.205
INDEX = "XU100.IS"


def classify(prices: pd.DataFrame, threshold: float = 0.105) -> pd.DataFrame:
    sessions = trading_calendar(prices)
    clean = apply_generic_rules(prices, sessions)
    stocks = clean[~clean["ticker"].str.startswith("X")]
    flags = jump_flags(stocks, threshold).rename(columns={"return": "ret"})
    if flags.empty:
        return flags.assign(cls=[], proposed_factor=[], market_return=[])

    xu = clean[clean["ticker"] == INDEX].dropna(subset=["adj_close"]).set_index("date")["adj_close"]
    xu_ret = xu / xu.shift() - 1
    n_trading = stocks.dropna(subset=["adj_close"]).groupby("date")["ticker"].nunique()
    n_flag = flags.groupby("date")["ticker"].nunique()

    out = []
    for r in flags.itertuples(index=False):
        mret = float(xu_ret.get(r.date, float("nan")))
        gap = int(((sessions > r.prev_date) & (sessions < r.date)).sum())
        share = n_flag.get(r.date, 0) / max(n_trading.get(r.date, 1), 1)
        factor = None
        if share >= MARKET_SHARE or abs(mret) >= MARKET_MOVE:
            cls = "market_event"
        elif gap > 0:
            cls = "multi_day_gap"
        elif abs(r.ret - r.raw_return) > DIVIDEND_GAP:
            cls = "vendor_dividend_adjustment"
            factor = (1 + r.ret) / (1 + (0.0 if pd.isna(mret) else mret))
        elif abs(r.raw_return) > BAND_MAX:
            cls = "split_or_bonus_misadjustment"
            factor = (1 + r.ret) / (1 + (0.0 if pd.isna(mret) else mret))
        else:
            cls = "review"
        out.append({**r._asdict(), "market_return": mret, "gap_sessions": gap,
                    "cls": cls, "proposed_factor": factor})  # fmt: skip
    return pd.DataFrame(out)


def to_proposals(df: pd.DataFrame) -> list[dict]:
    props = []
    for r in df[df["proposed_factor"].notna()].itertuples(index=False):
        props.append(
            {
                "ticker": r.ticker.removesuffix(".IS"),
                "date": pd.Timestamp(r.date).date().isoformat(),
                "type": "factor",
                "ratio": round(float(r.proposed_factor), 6),
                "status": "proposed",
                "source_url": "",
                "note": (
                    f"{r.cls}: adj return {r.ret:+.1%}, raw "
                    f"{r.raw_return:+.1%}, XU100 {r.market_return:+.1%}. "
                    + (
                        "Likely ex-dividend day with a wrong vendor adjustment; placeholder sets "
                        "the day's return to XU100's. Exact factor = (P_cum - D)/P_cum with "
                        "dividend D from KAP."
                        if r.cls == "vendor_dividend_adjustment"
                        else "Check KAP for a bonus/rights issue, split or share consolidation "
                        "and its real ex-date."
                    )
                ),
            }
        )
    return props


def merge_into_yaml(props: list[dict]) -> int:
    path = CONFIG_DIR / "corporate_actions.yaml"
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    actions = data.get("actions") or []
    have = {(a["ticker"], str(a["date"])) for a in actions}
    new = [p for p in props if (p["ticker"], p["date"]) not in have]
    if not new:
        return 0
    header = "".join(line + "\n" for line in text.splitlines() if line.startswith("#"))
    data["actions"] = actions + new
    path.write_text(header + "\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")  # fmt: skip
    return len(new)


def write_report(df: pd.DataFrame, generated: date) -> None:
    lines = [
        "# Price jump review",
        "",
        f"Generated {generated} by `uv run python -m pusula.data.jump_review` (D-026).",
        "Stocks, daily |adjusted return| > 10.5% after generic cleaning (D-025), before any "
        "corporate-action correction. Classes are explained in `src/pusula/data/jump_review.py`.",
        "",
        "## Summary",
        "",
        df.groupby("cls").size().rename("count").to_frame().to_markdown(),
        "",
    ]
    for cls in ["split_or_bonus_misadjustment", "vendor_dividend_adjustment", "review",
                "multi_day_gap", "market_event"]:  # fmt: skip
        sub = df[df["cls"] == cls]
        if sub.empty:
            continue
        t = sub.assign(
            date=sub["date"].dt.date,
            adj=(sub["ret"] * 100).round(1),
            raw=(sub["raw_return"] * 100).round(1),
            xu100=(sub["market_return"] * 100).round(1),
            factor=sub["proposed_factor"].round(4),
        )[["date", "ticker", "adj", "raw", "xu100", "gap_sessions", "factor"]]
        lines += [f"## {cls} ({len(sub)})", "", t.to_markdown(index=False), ""]
    (ROOT_DIR / "docs" / "price_jump_review.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--write", action="store_true", help="add proposals to corporate_actions.yaml")
    args = p.parse_args(argv)
    setup_logging()
    s = get_settings()
    store = Store(s.paths.db_path, s.paths.raw_dir)
    df = classify(store.prices(clean=False), s.data_quality.jump_thresholds["stock"])
    write_report(df, date.today())
    print(df.groupby("cls").size().to_string())
    if args.write:
        print(f"Added {merge_into_yaml(to_proposals(df))} proposals to corporate_actions.yaml")


if __name__ == "__main__":
    main()
