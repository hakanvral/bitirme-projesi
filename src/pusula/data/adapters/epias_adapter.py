"""EPİAŞ Transparency Platform adapter (optional; D-005, D-022).

Documented at https://seffaflik.epias.com.tr/electricity-service/technical/en/index.html
(API v1.16.4, checked 2026-11-16):

1. TGT: ``POST https://giris.epias.com.tr/cas/v1/tickets`` with form fields ``username`` and
   ``password`` -> ``201 Created``, body ``TGT-...`` (valid for 2 hours).
2. PTF (market clearing price, TRY/MWh, hourly):
   ``POST https://seffaflik.epias.com.tr/electricity-service/v1/markets/dam/data/mcp``,
   header ``TGT``, JSON body ``{"startDate": "2024-01-01T00:00:00+03:00", "endDate": ...}``,
   response ``{"items": [{"date": ..., "hour": "00:00", "price": 1234.5}, ...]}``.

Because the login takes the credentials in the request **body**, a network proxy cannot inject
them; the adapter needs ``EPIAS_USERNAME`` / ``EPIAS_PASSWORD`` in the local ``.env``. Without
them the update falls back to ``data/manual/ptf.csv``.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import httpx
import pandas as pd

log = logging.getLogger(__name__)

TICKET_URL = "https://giris.epias.com.tr/cas/v1/tickets"
MCP_URL = "https://seffaflik.epias.com.tr/electricity-service/v1/markets/dam/data/mcp"
CHUNK_DAYS = 31  # one request per ~month keeps responses small


class EpiasError(RuntimeError):
    pass


def get_tgt(client: httpx.Client, username: str, password: str) -> str:
    r = client.post(
        TICKET_URL,
        data={"username": username, "password": password},
        headers={"Accept": "text/plain"},
    )
    if r.status_code != 201 or not r.text.startswith("TGT-"):
        raise EpiasError(f"EPİAŞ login failed (HTTP {r.status_code})")  # never log the body
    return r.text.strip()


def _iso(d: date) -> str:
    return f"{d:%Y-%m-%d}T00:00:00+03:00"


def parse_mcp(payload: dict) -> pd.DataFrame:
    items = payload.get("items") or []
    if not items:
        return pd.DataFrame(columns=["date", "hour", "price"])
    df = pd.DataFrame(items)
    ts = pd.to_datetime(df["date"], utc=True).dt.tz_convert("Europe/Istanbul")
    return pd.DataFrame(
        {"date": ts.dt.tz_localize(None).dt.normalize(), "hour": df.get("hour"),
         "price": pd.to_numeric(df["price"], errors="coerce")}
    )  # fmt: skip


def fetch_ptf_daily(
    client: httpx.Client, tgt: str, start: date, end: date, pause: float = 0.3
) -> pd.DataFrame:
    """Daily mean PTF (TRY/MWh) as ``date, series='ptf', value``."""
    frames = []
    d = start
    while d <= end:
        e = min(d + timedelta(days=CHUNK_DAYS - 1), end)
        r = client.post(
            MCP_URL, json={"startDate": _iso(d), "endDate": _iso(e)}, headers={"TGT": tgt}
        )
        if r.status_code != 200:
            raise EpiasError(f"EPİAŞ MCP request failed for {d}..{e} (HTTP {r.status_code})")
        frames.append(parse_mcp(r.json()))
        d = e + timedelta(days=1)
        time.sleep(pause)
    hourly = pd.concat(frames, ignore_index=True) if frames else parse_mcp({})
    daily = hourly.groupby("date", as_index=False)["price"].mean()
    return pd.DataFrame({"date": daily["date"], "series": "ptf", "value": daily["price"]})
