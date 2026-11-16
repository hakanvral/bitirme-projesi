"""Parsers for official web sources, tested on small HTML/CSV snippets in the real formats."""

from datetime import date

import httpx
import pandas as pd
import pytest

from pusula.data.adapters import epias_adapter, tcmb_web
from pusula.universe import bist_index

# ----------------------------------------------------------------------------- TCMB
REPO_HTML = """<table><tr><td width="91">Tarih</td><td>Borç Alma</td><td>Borç Verme</td></tr>
<tr><td>22.12.2023</td><td>-</td><td>42.50</td></tr>
<tr><td>26.01.2024</td><td>-</td><td>45.00</td></tr>
<tr><td>22.03.2024</td><td>-</td><td>50.00</td></tr></table>"""

PPK_HTML = """<table><thead><tr><td><h2>Para Politikası Kurulu Toplantı Kararı</h2></td>
<td><h2>Özet</h2></td></tr></thead><tbody>
<tr><td style="x"><a href="/wps/a/duy2024-01" target="_blank" >25 Ocak 2024</a></td>
<td><a href="/wps/a/duy2024-03">1 Şubat 2024</a></td></tr>
<tr><td><a href="/wps/a/duy2024-09">22 Şubat 2024</a></td><td></td></tr>
<tr><td><a href="/wps/a/duy2024-14">21 Mart&nbsp;2024*</a></td><td></td></tr>
</tbody></table>"""


def test_repo_table_and_ppk_page():
    repo = tcmb_web.parse_repo_table(REPO_HTML)
    assert list(repo["value"]) == [42.5, 45.0, 50.0]
    m = tcmb_web.parse_ppk_year_page(PPK_HTML)
    assert list(m["meeting_date"]) == [
        pd.Timestamp(d) for d in ["2024-01-25", "2024-02-22", "2024-03-21"]
    ]
    assert m["source_url"].iloc[0] == "https://www.tcmb.gov.tr/wps/a/duy2024-01"


@pytest.mark.parametrize(
    "text,prev,new",
    [
        (
            "politika faizi olan bir hafta vadeli repo ihale faiz oranının yüzde 42,5’ten yüzde 45 "
            "düzeyine yükseltilmesine karar vermiştir.",
            42.5,
            45.0,
        ),
        (
            "bir hafta vadeli repo ihale faiz oranının yüzde 45 düzeyinde sabit tutulmasına karar "
            "vermiştir.",
            45.0,
            45.0,
        ),
    ],
)
def test_decision_text(text, prev, new):
    d = tcmb_web.parse_decision_text(f"<p>{text}</p>")
    assert d["text_previous_rate"] == prev and d["text_new_rate"] == new


def test_build_ppk_decisions_uses_repo_table_and_flags_text_mismatch():
    repo = tcmb_web.parse_repo_table(REPO_HTML)
    m = tcmb_web.parse_ppk_year_page(PPK_HTML)
    texts = [
        {"text_previous_rate": 42.5, "text_new_rate": 45.0},
        {"text_previous_rate": 45.0, "text_new_rate": 45.0},
        {"text_previous_rate": 45.0, "text_new_rate": 47.5},
    ]  # wrong on purpose
    df = tcmb_web.build_ppk_decisions(m, repo, texts)
    assert list(df["change_bp"]) == [250.0, 0.0, 500.0]
    assert df["notes"].iloc[0] == "" and "check manually" in df["notes"].iloc[2]


# ----------------------------------------------------------------------------- BIST
CSV = (
    (
        "BILESEN KODU;BULTEN_ADI;ENDEKS KODU;ENDEKS ADI;ENDEKS INGILIZCE ADI;TARIH(GG/AA/YYYY)\n"
        "CONSTITUENT CODE;CONSTITUENT NAME;INDEX CODE;INDEX NAME IN TURKISH;"
        "INDEX NAME IN ENGLISH;DATE(DD/MM/YYYY)\n"
    )
    + """AAA.E;A;XU030;BIST 30;BIST 30;16/11/2026
NEW.E;N;XU030;BIST 30;BIST 30;16/11/2026
BBB.E;B;XU100;BIST 100;BIST 100;16/11/2026
"""
)


def _ann(period: str, added: str, removed: str) -> str:
    return (
        f"<html><body><p>{period}</p><p><strong>BIST 30 ENDEKSİ</strong></p><table>"
        "<tr><td colspan=3>ALINACAK PAYLAR</td><td colspan=3>ÇIKARILACAK PAYLAR</td>"
        "<td colspan=3>YEDEK PAYLAR</td></tr>"
        f"<tr><td>1</td><td>{added}</td><td>x</td><td>1</td><td>{removed}</td><td>y</td>"
        "<td>1</td><td>RES</td><td>z</td></tr></table>"
        "<p>BIST 50 ENDEKSİ</p><table><tr><td>1</td><td>ZZZ</td></tr></table></body></html>"
    )


def test_bist_constituents_and_backward_reconstruction():
    cur, d = bist_index.parse_constituents_csv(CSV)
    assert cur == ["AAA", "NEW"] and d == date(2026, 11, 16)
    info = bist_index.parse_change_announcement(_ann("01.10.2026-31.12.2026", "NEW", "OLD"))
    assert info["added"] == ["NEW"] and info["removed"] == ["OLD"]
    ch = bist_index.PeriodChange(1, "u", **info)
    members, log = bist_index.reconstruct(cur, d, [ch], date(2026, 9, 1))
    assert members == ["AAA", "OLD"] and len(log) == 1
    same, _ = bist_index.reconstruct(cur, d, [ch], date(2026, 11, 1))  # inside the period
    assert same == ["AAA", "NEW"]
    assert bist_index.check_against(same, ch) == []


def test_bist_announcement_with_no_changes():
    info = bist_index.parse_change_announcement(_ann("01.07.2026-30.09.2026", "--", "--"))
    assert info["added"] == [] and info["removed"] == []


# ----------------------------------------------------------------------------- EPİAŞ
def test_epias_login_and_mcp_daily_mean():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "giris.epias.com.tr":
            seen["form"] = req.content.decode()
            return httpx.Response(201, text="TGT-abc")
        seen["tgt"] = req.headers.get("TGT")
        return httpx.Response(
            200,
            json={
                "items": [
                    {"date": "2024-01-02T00:00:00+03:00", "hour": "00:00", "price": 100.0},
                    {"date": "2024-01-02T01:00:00+03:00", "hour": "01:00", "price": 200.0},
                    {"date": "2024-01-03T00:00:00+03:00", "hour": "00:00", "price": 50.0},
                ]
            },
        )

    c = httpx.Client(transport=httpx.MockTransport(handler))
    tgt = epias_adapter.get_tgt(c, "u@example.com", "pw")
    df = epias_adapter.fetch_ptf_daily(c, tgt, date(2024, 1, 2), date(2024, 1, 3), pause=0)
    assert "username=u%40example.com" in seen["form"] and seen["tgt"] == "TGT-abc"
    assert list(df["value"]) == [150.0, 50.0]


def test_epias_login_failure_does_not_leak_body():
    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, text="secret")))
    with pytest.raises(epias_adapter.EpiasError) as e:
        epias_adapter.get_tgt(c, "u", "p")
    assert "secret" not in str(e.value)
