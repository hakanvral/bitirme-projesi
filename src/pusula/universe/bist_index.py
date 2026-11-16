"""BIST index constituents from Borsa Istanbul's official sources (D-021).

* Current constituents: ``https://www.borsaistanbul.com/datum/hisse_endeks_ds.csv``
  (``;``-separated, two header rows TR/EN, one row per constituent-index pair, the file's own
  date in the last column). Codes end in ``.E`` (equity), e.g. ``AKBNK.E``.
* Past constituents are not published as a file. They are **reconstructed backwards** from the
  current list using the quarterly announcements "BIST Pay Endeksleri Dönemsel Değişiklikleri":
  each announcement lists, per index, the shares to be added ("ALINACAK PAYLAR") and removed
  ("ÇIKARILACAK PAYLAR") at the start of a period. Undoing the announcements from newest to
  oldest gives the list at an earlier date.

Limitation: changes *within* a period (e.g. delisting, merger, ticker change) are not in these
announcements, so a reconstructed list must be checked by the user (see PROGRESS.md).

    uv run python -m pusula.universe.bist_index          # prints both lists and the evidence
"""

from __future__ import annotations

import argparse
import html as htmllib
import re
from dataclasses import dataclass
from datetime import date

import httpx

BASE = "https://www.borsaistanbul.com"
CONSTITUENTS_URL = BASE + "/datum/hisse_endeks_ds.csv"

# Announcements of periodic changes (id, slug). Found via borsaistanbul.com/duyurular.
ANNOUNCEMENTS: dict[int, str] = {
    15220: "2025-yili-dorduncu-uc-aylik-donemi-icin-bist-pay-endeksleri-kapsaminda-yer-alacak-paylar-belirlenmistir",  # noqa: E501
    15293: "2026-yili-birinci-uc-aylik-donemi-icin-bist-pay-endeksleri-kapsaminda-yer-alacak-paylar-belirlenmistir",  # noqa: E501
    15392: "2026-yili-ikinci-uc-aylik-donemi-icin-bist-pay-endeksleri-kapsaminda-yer-alacak-paylar-belirlenmistir",  # noqa: E501
    15483: "bist-pay-endeksleri-donemsel-degisiklikleri",
    15598: "bist-pay-endeksleri-donemsel-degisiklikleri",
}  # fmt: skip


@dataclass
class PeriodChange:
    announcement_id: int
    url: str
    period_start: date
    period_end: date
    added: list[str]
    removed: list[str]


# --------------------------------------------------------------------------- parsing
def parse_constituents_csv(text: str, index_code: str = "XU030") -> tuple[list[str], date]:
    """Return (sorted tickers without '.E', file date) for ``index_code``."""
    tickers, file_date = [], None
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 6 or parts[2] != index_code:
            continue
        tickers.append(parts[0].removesuffix(".E"))
        d, m, y = parts[5].split("/")
        file_date = date(int(y), int(m), int(d))
    if not tickers or file_date is None:
        raise ValueError(f"No rows for index {index_code} in constituents file")
    return sorted(set(tickers)), file_date


def _cells(row_html: str) -> list[str]:
    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, flags=re.S)
    return [re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", c))).strip() for c in cells]


def parse_change_announcement(page: str, index_title: str = "BIST 30 ENDEKS") -> dict:
    """Period and the added / removed tickers for one index from an announcement page."""
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})\s*-\s*(\d{2})\.(\d{2})\.(\d{4})", page)
    if not m:
        raise ValueError("No period (dd.mm.yyyy-dd.mm.yyyy) found in announcement")
    g = [int(x) for x in m.groups()]
    start, end = date(g[2], g[1], g[0]), date(g[5], g[4], g[3])
    body = page[page.find("<body") :]
    i = body.find(index_title)
    if i < 0:
        raise ValueError(f"Section {index_title!r} not found")
    t0 = body.find("<table", i)
    t1 = body.find("</table>", t0)
    added, removed = [], []
    code = re.compile(r"^[A-Z0-9]{3,6}$")
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body[t0:t1], flags=re.S):
        c = _cells(row)
        if len(c) >= 6:
            if code.match(c[1]):
                added.append(c[1])
            if code.match(c[4]):
                removed.append(c[4])
    return {"period_start": start, "period_end": end, "added": added, "removed": removed}


# --------------------------------------------------------------------------- reconstruction
def reconstruct(
    current: list[str], current_date: date, changes: list[PeriodChange], target: date
) -> tuple[list[str], list[str]]:
    """List in force on ``target``, undoing every change with target < period_start <= current_date.

    Returns (tickers, log lines).
    """
    members = set(current)
    log = []
    for ch in sorted(changes, key=lambda c: c.period_start, reverse=True):
        if not (target < ch.period_start <= current_date):
            continue
        for t in ch.added:
            if t not in members:
                raise ValueError(f"{t} added on {ch.period_start} but not in the later list")
            members.discard(t)
        for t in ch.removed:
            members.add(t)
        log.append(
            f"undo {ch.period_start} (#{ch.announcement_id}): "
            f"-{ch.added or '[]'} +{ch.removed or '[]'}"
        )
    return sorted(members), log


def check_against(members: list[str], ch: PeriodChange) -> list[str]:
    """Consistency check for the period that contains the target date."""
    problems = [f"{t} should be in (added {ch.period_start})" for t in ch.added if t not in members]
    problems += [
        f"{t} should be out (removed {ch.period_start})" for t in ch.removed if t in members
    ]
    return problems


# --------------------------------------------------------------------------- network
def fetch_all(client: httpx.Client) -> tuple[list[str], date, list[PeriodChange]]:
    r = client.get(CONSTITUENTS_URL)
    r.raise_for_status()
    current, file_date = parse_constituents_csv(r.content.decode("utf-8", errors="replace"))
    changes = []
    for aid, slug in ANNOUNCEMENTS.items():
        url = f"{BASE}/duyuru/{aid}/{slug}"
        p = client.get(url)
        p.raise_for_status()
        info = parse_change_announcement(p.text)
        changes.append(PeriodChange(aid, url, **info))
    return current, file_date, changes


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", action="append", default=[], help="YYYY-MM-DD (repeatable)")
    args = p.parse_args(argv)
    from pusula.config import get_settings

    s = get_settings()
    targets = [date.fromisoformat(t) for t in args.target] or [
        s.project.reference_date,
        s.project.selection_date,
    ]
    with httpx.Client(timeout=60, follow_redirects=True) as c:
        current, file_date, changes = fetch_all(c)
    print(f"Current XU030 list ({file_date}, {CONSTITUENTS_URL}): {len(current)}")
    for t in targets:
        members, log = reconstruct(current, file_date, changes, t)
        period = [c for c in changes if c.period_start <= t <= c.period_end]
        problems = check_against(members, period[0]) if period else ["no announcement covers date"]
        print(f"\n== {t}: {len(members)} names")
        print(" ".join(members))
        print("\n".join(log) or "(no changes undone)")
        print("consistency:", problems or "OK")


if __name__ == "__main__":
    main()
