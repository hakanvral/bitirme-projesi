"""TCMB EVDS adapter (EVDS3, 2025+).

* Base URL: ``https://evds3.tcmb.gov.tr/igmevdsms-dis/`` (``config/data_sources.yaml``).
  ``evds2.tcmb.gov.tr`` redirects there.
* Authentication: API key in the HTTP header ``key`` (a request without it returns
  ``403 Required request header 'key' is not present``, checked 2026-11-16).
* Parameters are path-style, separated by ``&``, e.g.
  ``series=CODE1-CODE2&startDate=01-01-2018&endDate=31-12-2018&type=json``.
* Response: ``{"items": [{"Tarih": "02-01-2018", "CODE1_WITH_UNDERSCORES": "3.77", ...}]}``.
  Dates are ``dd-mm-yyyy`` for daily data and ``yyyy-m`` for monthly data.

Metadata endpoints (for verifying series codes): ``categories/``, ``datagroups/``,
``serieList/``. See :func:`search_series`.

The HTTP client is injectable (``httpx.Client``), so tests use ``httpx.MockTransport``.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import httpx
import pandas as pd

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60.0
# EVDS returns at most ~1000 items per request (found 2026-11-16: a 2018-2026 daily request
# returned only the last ~1000 calendar days). Daily series are therefore requested in windows.
MAX_WINDOW_DAYS = 900


class EvdsError(RuntimeError):
    pass


class EvdsClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        # Send the key only if configured. In the cloud environment a network proxy injects it.
        headers = {"key": api_key} if api_key else {}
        self._client = client or httpx.Client(timeout=DEFAULT_TIMEOUT, headers=headers)
        if client is not None and api_key:
            self._client.headers.update(headers)

    # ------------------------------------------------------------------ low level
    def _get(self, path: str) -> object:
        url = self.base_url + path
        resp = self._client.get(url)
        if resp.status_code != 200:
            # Never log headers (they contain the key).
            raise EvdsError(f"EVDS {resp.status_code} for {path.split('&')[0]}: {resp.text[:200]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise EvdsError(f"EVDS returned non-JSON for {path.split('&')[0]}") from exc

    # ------------------------------------------------------------------ data
    def series(self, code: str, start: date, end: date) -> pd.DataFrame:
        """One series as ``date, value`` (float), requested in windows of MAX_WINDOW_DAYS."""
        frames = []
        s = start
        while s <= end:
            e = min(s + timedelta(days=MAX_WINDOW_DAYS - 1), end)
            path = f"series={code}&startDate={s:%d-%m-%Y}&endDate={e:%d-%m-%Y}&type=json"
            frames.append(parse_series(self._get(path), code))
            s = e + timedelta(days=1)
        out = pd.concat(frames, ignore_index=True)
        return out.drop_duplicates("date").sort_values("date").reset_index(drop=True)

    # ------------------------------------------------------------------ metadata
    def categories(self) -> list[dict]:
        return list(self._get("categories/type=json"))  # type: ignore[arg-type]

    def datagroups(self, category_id: int | None = None) -> list[dict]:
        path = (
            "datagroups/mode=0&type=json"
            if category_id is None
            else f"datagroups/mode=2&code={category_id}&type=json"
        )
        return list(self._get(path))  # type: ignore[arg-type]

    def serie_list(self, datagroup_code: str) -> list[dict]:
        return list(self._get(f"serieList/type=json&code={datagroup_code}"))  # type: ignore[arg-type]


def _parse_dates(raw: pd.Series) -> pd.Series:
    daily = pd.to_datetime(raw, format="%d-%m-%Y", errors="coerce")
    monthly = pd.to_datetime(raw, format="%Y-%m", errors="coerce")
    return daily.fillna(monthly)


def parse_series(payload: object, code: str) -> pd.DataFrame:
    """Parse an EVDS ``series=`` JSON payload into ``date, value``."""
    if not isinstance(payload, dict) or "items" not in payload:
        raise EvdsError("Unexpected EVDS payload (no 'items')")
    items = payload["items"]
    col = code.replace(".", "_")
    if not items:
        return pd.DataFrame(columns=["date", "value"])
    df = pd.DataFrame(items)
    if col not in df.columns:
        raise EvdsError(f"Series column {col!r} not in EVDS response (columns: {list(df.columns)})")
    out = pd.DataFrame(
        {"date": _parse_dates(df["Tarih"]), "value": pd.to_numeric(df[col], errors="coerce")}
    )
    if out["date"].isna().any():
        raise EvdsError(f"Unparseable EVDS dates, e.g. {df['Tarih'].iloc[0]!r}")
    return out.dropna(subset=["value"]).reset_index(drop=True)


def search_series(client: EvdsClient, *patterns: str) -> pd.DataFrame:
    """Search all EVDS data groups and their series for case-insensitive ``patterns``.

    Used by ``python -m pusula.data.evds_lookup`` to verify codes instead of guessing them.
    """
    rows = []
    groups = client.datagroups()
    pats = [p.lower() for p in patterns]
    for g in groups:
        text = f"{g.get('DATAGROUP_NAME_ENG', '')} {g.get('DATAGROUP_NAME', '')}".lower()
        if not any(p in text for p in pats):
            continue
        for s in client.serie_list(g["DATAGROUP_CODE"]):
            rows.append(
                {
                    "datagroup": g["DATAGROUP_CODE"],
                    "datagroup_name": g.get("DATAGROUP_NAME_ENG"),
                    "serie_code": s.get("SERIE_CODE"),
                    "serie_name": s.get("SERIE_NAME_ENG") or s.get("SERIE_NAME"),
                    "frequency": s.get("FREQUENCY_STR"),
                    "start": s.get("START_DATE"),
                    "end": s.get("END_DATE"),
                }
            )
    return pd.DataFrame(rows)
