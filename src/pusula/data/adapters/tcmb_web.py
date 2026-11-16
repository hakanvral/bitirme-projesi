"""TCMB website adapter (www.tcmb.gov.tr), for data that EVDS does not carry.

* :func:`fetch_one_week_repo`: the official "1 Hafta Repo" table (date the rate took effect,
  borrowing rate, lending rate). The **lending rate** is the policy rate (D-018).
* :func:`fetch_ppk_meetings`: the yearly "Para Politikası Kurulu Kararları" pages. The first
  column of each table row is the decision date, linked to its press release.
* :func:`parse_decision_text`: reads "yüzde 42,5'ten yüzde 45 düzeyine yükseltilmesine" /
  "yüzde 45 düzeyinde sabit tutulmasına" from a press release, as a cross-check.
* :func:`build_ppk_decisions`: one row per meeting with the previous / new rate taken from the
  repo table (the official series), the text-parsed values as a check and the source URL.

All parsing works on plain HTML strings, so tests use saved snippets and never hit the network.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date

import httpx
import pandas as pd

log = logging.getLogger(__name__)

BASE = "https://www.tcmb.gov.tr"
REPO_URL = (
    BASE + "/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Temel+Faaliyetler/Para+Politikasi/"
    "Merkez+Bankasi+Faiz+Oranlari/1+Hafta+Repo"
)
PPK_YEAR_URL = (
    BASE + "/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Temel+Faaliyetler/Para+Politikasi/PPK/{year}"
)

TR_MONTHS = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6, "temmuz": 7,
    "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
}  # fmt: skip

_TAG = re.compile(r"<[^>]+>")


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub(" ", html).replace("&nbsp;", " ")).strip()


def _num(s: str) -> float:
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)


def parse_tr_date(s: str) -> date:
    """'25 Ocak 2024' (optionally with '*' or extra spaces) -> date."""
    parts = _text(s).replace("*", "").split()
    if len(parts) != 3 or parts[1].lower() not in TR_MONTHS:
        raise ValueError(f"Not a Turkish date: {s!r}")
    return date(int(parts[2]), TR_MONTHS[parts[1].lower()], int(parts[0]))


# --------------------------------------------------------------------------- 1-week repo
def parse_repo_table(html: str) -> pd.DataFrame:
    """Rows ``dd.mm.yyyy | borrowing | lending`` -> ``date, value`` (lending rate, %)."""
    cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", html, flags=re.S)]
    rows = []
    for i in range(len(cells) - 2):
        if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", cells[i]):
            lending = cells[i + 2]
            if re.fullmatch(r"\d+(?:[.,]\d+)?", lending):
                rows.append(
                    (pd.to_datetime(cells[i], format="%d.%m.%Y"), float(lending.replace(",", ".")))
                )
    if not rows:
        raise ValueError("No rows found in the TCMB one-week repo table")
    return pd.DataFrame(rows, columns=["date", "value"]).sort_values("date").reset_index(drop=True)


def fetch_one_week_repo(client: httpx.Client) -> pd.DataFrame:
    r = client.get(REPO_URL)
    r.raise_for_status()
    return parse_repo_table(r.text)


# --------------------------------------------------------------------------- PPK meetings
def parse_ppk_year_page(html: str) -> pd.DataFrame:
    """First cell of each table row = decision date + link to the press release."""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)
        if not tds:
            continue
        m = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', tds[0], flags=re.S)
        if not m:
            continue
        try:
            d = parse_tr_date(m.group(2))
        except ValueError:
            continue
        url = m.group(1)
        out.append(
            {
                "meeting_date": pd.Timestamp(d),
                "source_url": url if url.startswith("http") else BASE + url,
            }
        )
    return pd.DataFrame(out, columns=["meeting_date", "source_url"])


def fetch_ppk_meetings(client: httpx.Client, years: list[int], pause: float = 0.3) -> pd.DataFrame:
    frames = []
    for y in years:
        r = client.get(PPK_YEAR_URL.format(year=y))
        if r.status_code == 404:
            log.warning("No PPK page for %s", y)
            continue
        r.raise_for_status()
        frames.append(parse_ppk_year_page(r.text))
        time.sleep(pause)
    df = pd.concat(frames, ignore_index=True) if frames else parse_ppk_year_page("")
    return df.drop_duplicates("meeting_date").sort_values("meeting_date").reset_index(drop=True)


_RATE = r"yüzde\s*(\d+(?:,\d+)?)"


def parse_decision_text(html: str) -> dict:
    """Extract (previous, new) policy rate from a PPK press release, or ``{}`` if not found.

    Only the sentence about the one-week repo rate is used.
    """
    text = _text(html)
    m = re.search(r"[^.]*hafta vadeli repo[^.]*(?:\.\d[^.]*)*\.", text, flags=re.I)
    if not m:
        return {}
    sent = m.group(0)
    nums = [_num(x) for x in re.findall(_RATE, sent, flags=re.I)]
    if not nums:
        return {}
    if re.search(r"sabit", sent, flags=re.I):
        return {
            "text_previous_rate": nums[0],
            "text_new_rate": nums[0],
            "text_sentence": sent.strip(),
        }
    if len(nums) >= 2:
        return {
            "text_previous_rate": nums[0],
            "text_new_rate": nums[1],
            "text_sentence": sent.strip(),
        }
    return {"text_sentence": sent.strip()}


def fetch_decision_texts(client: httpx.Client, urls: list[str], pause: float = 0.3) -> list[dict]:
    out = []
    for u in urls:
        try:
            r = client.get(u)
            r.raise_for_status()
            out.append(parse_decision_text(r.text))
        except httpx.HTTPError as exc:
            log.warning("Could not read %s: %s", u, exc)
            out.append({})
        time.sleep(pause)
    return out


# --------------------------------------------------------------------------- combine
def build_ppk_decisions(
    meetings: pd.DataFrame,
    repo: pd.DataFrame,
    texts: list[dict] | None = None,
    max_lag_days: int = 7,
) -> pd.DataFrame:
    """One row per meeting. Rates come from the official repo table:

    * ``previous_rate`` = rate in effect on the meeting day,
    * ``new_rate`` = rate in effect ``max_lag_days`` calendar days later (decisions take effect
      the next business day), i.e. the change attributed to this meeting.
    The text-parsed rates are kept for checking; ``notes`` flags any disagreement.
    """
    r = repo.sort_values("date").set_index("date")["value"]

    def rate_on(d: pd.Timestamp) -> float:
        s = r[r.index <= d]
        return float(s.iloc[-1]) if len(s) else float("nan")

    rows = []
    for i, m in meetings.reset_index(drop=True).iterrows():
        d = pd.Timestamp(m["meeting_date"])
        prev, new = rate_on(d), rate_on(d + pd.Timedelta(days=max_lag_days))
        row = {
            "meeting_date": d,
            "previous_rate": prev,
            "new_rate": new,
            "change_bp": round((new - prev) * 100, 2),
            "expected_rate": float("nan"),
            "source_url": m["source_url"],
            "notes": "",
        }
        t = texts[i] if texts is not None else {}
        notes = []
        if t.get("text_new_rate") is not None:
            if abs(t["text_new_rate"] - new) > 1e-9 or abs(t["text_previous_rate"] - prev) > 1e-9:
                notes.append(
                    f"press release says {t['text_previous_rate']}->{t['text_new_rate']}; "
                    "check manually"
                )
        elif texts is not None:
            notes.append("rate sentence not parsed from press release")
        if d < pd.Timestamp("2018-06-01"):
            notes.append("before 2018-06-01 the late liquidity window (LON) was the active tool")
        row["notes"] = "; ".join(notes)
        rows.append(row)
    return pd.DataFrame(rows)
