# Manual data files (`data/manual/`)

Files here are **inputs you provide**. The program never edits them, except for
`ppk_detected_changes.csv`, which is a helper the program writes for you. They are git-ignored;
only this README and `templates/` are tracked.

General rules: UTF-8, comma-separated, header row exactly as shown (lower case), dates
`YYYY-MM-DD`, months `YYYY-MM`, decimal point `.` (not `,`), no thousands separators.
Empty templates are in `templates/`.

| File | Columns | Needed? | Where to get it |
|---|---|---|---|
| `cds_tr_5y.csv` | `date,value` (bp) | **core** (no free API) | Historical daily data for "Turkey 5 Year CDS", e.g. investing.com → Turkey 5Y CDS → Historical Data (daily, 2018-01-01 → today). Keep the "Price/Close" column as `value`. |
| `ptf.csv` | `date,ptf_try_mwh` (optional `hour`) | **core** (D-005) | EPİAŞ Transparency Platform (seffaflik.epias.com.tr) → Elektrik → Gün Öncesi Piyasası → PTF (Piyasa Takas Fiyatı). Export (Excel/CSV) 2018-01-01 → today, hourly or daily. Rename the date column to `date` (`YYYY-MM-DD`) and the PTF TL/MWh column to `ptf_try_mwh`. Hourly rows are averaged per day. |
| `ppk_decisions.csv` | `meeting_date,previous_rate,new_rate,change_bp[,expected_rate,source_url,notes]` | **core** (E3) | TCMB website → Para Politikası → PPK karar metinleri (press releases), one row per meeting since 2018, **including "no change" meetings**. `change_bp` must equal `(new_rate − previous_rate) × 100`. `expected_rate` (optional): survey median if you have it. Start from `ppk_detected_changes.csv` (written by the update command), which lists every date the policy rate changed. |
| `cpi_release_dates.csv` | `period,release_date` | **core** (point-in-time CPI, D-003) | TÜİK release calendar / bulletin dates for "Tüketici Fiyat Endeksi", one row per month since 2018-01 (e.g. `2024-05,2024-06-03`). |
| `cpi_exp_12m_release_dates.csv` | `period,release_date` | core for using expectations point-in-time | TCMB "Piyasa Katılımcıları Anketi" publication dates (one per survey month). |
| `cpi.csv` | `period,value[,release_date]` | only if EVDS fails | CPI 2003=100 from EVDS / TÜİK. |
| `cpi_exp_12m.csv` | `period,value` | only if EVDS fails | Survey of Market Participants, 12-month CPI expectation (%). |
| `policy_rate.csv` | `date,value` (%) | only if EVDS fails | TCMB one-week repo rate. One row per change date is enough (step fill). |
| `tlref.csv` | `date,value` (%) | only if not in EVDS | Borsa Istanbul → TLREF data. |
| `tr_2y_yield.csv`, `tr_10y_yield.csv` | `date,value` (%) | only if not in EVDS | e.g. investing.com → Turkey 2Y / 10Y bond yield → Historical Data. |
| `usdtry.csv`, `eurtry.csv` | `date,value` | only if EVDS fails | TCMB indicative rates. |
| `index_XU030.csv`, `index_XELKT.csv`, `index_XU100.csv` | `date,open,high,low,close[,adj_close],volume` | only if Yahoo lacks the index | Borsa Istanbul data / investing.com historical data. |
| `prices_<TICKER>.csv` | same as index files | only if Yahoo lacks a stock | e.g. `prices_TUPRS.csv`. |

Check a file: run `uv run python -m pusula.data.update --only macro events`; schema errors are
printed with the file name and the offending value.
