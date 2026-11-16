# Data sources

Declared in `config/data_sources.yaml`. Each series has an adapter and, where useful, a manual-CSV
fallback (`data/manual/README.md`). Status as of 2026-11-16.

## EVDS (TCMB): verified series codes

API: `https://evds3.tcmb.gov.tr/igmevdsms-dis/`, header `key`, ≤1000 items per request (we use
≤900-day windows). Codes were found with `python -m pusula.data.evds_lookup` (metadata endpoints
`datagroups/` and `serieList/`) on 2026-11-16 and checked by downloading them.

| Series id | EVDS code | Data group | Name in EVDS | Check |
|---|---|---|---|---|
| usdtry | `TP.DK.USD.A.YTL` | bie_dkdovytl | (USD) US Dollar (Buying), daily | 2228 obs 2018-01-01 → 2026-11-16; median gap to Yahoo TRY=X 0.24% |
| eurtry | `TP.DK.EUR.A.YTL` | bie_dkdovytl | (EUR) Euro (Buying), daily | 2228 obs |
| tlref | `TP.BISTTLREF.ORAN` | bie_bisttlref | BIST TLREF – Turkish Lira Overnight Reference Rate | starts 2018-12-28 |
| interbank_on | `TP.AOFO` | bie_onrepof | Over/Night Interbank Interest Rates – Weighted Average (Archive) | 2018-01-02 → 2019-02-08 (D-019) |
| cpi | `TP.TUKFIY2025.GENEL` | bie_tukfiy2025 | CPI (2025=100) General Index, monthly | annual inflation Oct-2022 85.5%, Dec-2023 64.8%, Dec-2024 44.4% (matches TÜİK) |
| cpi_exp_12m | `TP.ENFBEK.PKA12ENF` | bie_enfbek | Annual inflation expectations of market participants (12-month ahead, %) | 2018-01 → 2026-10 |

Not in EVDS (checked): daily policy rate (only monthly BIS `TP.BISPOLFAIZ.TUR`) → TCMB website
(D-018); benchmark 2Y/10Y yields (`bie_pydibs` = per-ISIN values only) → manual (D-020).

## Other sources

| Source | Endpoint | Used for | Status |
|---|---|---|---|
| TCMB website | `…/Para+Politikasi/Merkez+Bankasi+Faiz+Oranlari/1+Hafta+Repo` | policy rate | automated |
| TCMB website | `…/Para+Politikasi/PPK/<year>` + press releases | `ppk_decisions.csv` prefill | automated, user review |
| Borsa Istanbul | `/datum/hisse_endeks_ds.csv`, period-change announcements | BIST30 lists | automated, user review |
| Yahoo Finance | `yfinance` | stock and index prices, Brent, TTF, VIX, US10Y, DXY, TRY=X | automated |
| EPİAŞ | `giris.epias.com.tr` (TGT), `seffaflik.epias.com.tr/electricity-service/v1/markets/dam/data/mcp` | PTF | needs local `.env` credentials; else `ptf.csv` |
| TÜİK | `veriportali.tuik.gov.tr` | CPI release dates | portal API answered "access denied" → rule (D-023) or user file |
| KAP | `www.kap.org.tr` | corporate-action verification | manual by the user |
| CDS, 2Y/10Y yields | — | country risk, rate factor | manual CSV |
