"""Pre-fill manual input files from official websites, for the user to review (D-028).

    uv run python -m pusula.data.prefill ppk     # data/manual/ppk_decisions.csv (TCMB)

* ``ppk``: every PPK decision since ``data_start`` from TCMB's yearly "Para Politikası Kurulu
  Kararları" pages, with ``source_url`` = the decision's press release. Rates come from TCMB's
  official one-week repo table; the press-release text is parsed as a cross-check and any
  disagreement is written to ``notes``. An existing file is never overwritten: the output then
  goes to ``ppk_decisions.prefill.csv`` for comparison.

(BIST30 lists: ``python -m pusula.universe.bist_index``.)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import httpx

from pusula.config import get_settings
from pusula.data.adapters import tcmb_web
from pusula.logging_setup import setup_logging


def _target(manual_dir: Path, name: str) -> Path:
    p = manual_dir / name
    return p if not p.exists() else p.with_suffix(".prefill.csv")


def prefill_ppk(client: httpx.Client, out: Path, first_year: int, last_year: int) -> int:
    repo = tcmb_web.fetch_one_week_repo(client)
    meetings = tcmb_web.fetch_ppk_meetings(client, list(range(first_year, last_year + 1)))
    texts = tcmb_web.fetch_decision_texts(client, meetings["source_url"].tolist())
    df = tcmb_web.build_ppk_decisions(meetings, repo, texts)
    df.to_csv(out, index=False, date_format="%Y-%m-%d")
    return len(df)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("what", choices=["ppk"])
    args = p.parse_args(argv)
    setup_logging()
    from pusula.config import assert_data_not_frozen

    assert_data_not_frozen("PPK prefill")
    s = get_settings()
    s.paths.manual_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60, follow_redirects=True) as c:
        if args.what == "ppk":
            out = _target(s.paths.manual_dir, "ppk_decisions.csv")
            n = prefill_ppk(c, out, s.project.data_start.year, s.project.reference_date.year)
            print(f"Wrote {n} PPK decisions to {out}")


if __name__ == "__main__":
    main()
