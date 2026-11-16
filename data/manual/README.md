# Manual data files (`data/manual/`)

Files here are **inputs you provide**. The program never edits them, except for
`ppk_detected_changes.csv`, which is a helper the program writes for you. They are git-ignored;
only this README and `templates/` are tracked.

General rules: UTF-8, comma-separated, header row exactly as shown (lower case), dates
`YYYY-MM-DD`, months `YYYY-MM`, decimal point `.` (not `,`), no thousands separators.
Empty templates are in `templates/`.

| File | Columns | Needed? | Where to get it |
|---|---|---|---|
| `cds_tr_5y.csv` | `date,value` (bp) | **core, manual** (no free API) | See "CDS: step by step" below. |
| `tr_2y_yield.csv`, `tr_10y_yield.csv` | `date,value` (%) | needed only if we use the 2Y yield as the rate factor (decision in P3; else TLREF) | Daily historical yields, e.g. investing.com → "Turkey 2-Year Bond Yield" / "Turkey 10-Year Bond Yield" → Historical Data, same steps as CDS. |
| `ptf.csv` | `date,ptf_try_mwh` (optional `hour`) | only if the EPİAŞ API cannot run (cloud) | EPİAŞ Şeffaflık Platformu → Elektrik → Gün Öncesi Piyasası → Piyasa Takas Fiyatı (PTF) → export 2018-01-01 → today. Rename the date column to `date` (YYYY-MM-DD) and the TL/MWh column to `ptf_try_mwh`. Running locally with `EPIAS_USERNAME`/`EPIAS_PASSWORD` in `.env` downloads PTF automatically. |
| `ppk_decisions.csv` | `meeting_date,previous_rate,new_rate,change_bp[,expected_rate,source_url,notes]` | core (E3) | **Pre-filled automatically** (`python -m pusula.data.prefill ppk`, TCMB press releases). Please review, especially the rows with notes (before 2018-06-01). |
| `cpi_release_dates.csv` | `period,release_date` | optional | Official TÜİK release dates. Without this file a conservative rule is used (D-023). |
| `cpi_exp_12m_release_dates.csv` | `period,release_date` | optional | Official TCMB publication dates of the survey. Without it: rule (D-023). |
| `index_XELKT.csv` | `date,open,high,low,close[,adj_close],volume` | only if XELKT is used as a benchmark | Yahoo has no XELKT history. |
| `prices_<TICKER>.csv`, `index_<CODE>.csv`, `policy_rate.csv`, `usdtry.csv`, … | see schemas above | fallbacks only | Used automatically if the online source fails. |

### CDS: step by step
1. Open investing.com and search for **"Turkey CDS 5 Years USD"** (the Türkiye 5-year sovereign CDS
   in USD). Go to its **Historical Data** tab. (I could not open investing.com from the cloud
   session, so please check that the page title matches.)
2. Time frame **Daily**; date range **01/01/2018 → today**.
3. Click **Download** (needs a free investing.com account). You get a CSV with columns such as
   `Date, Price, Open, High, Low, Change %`.
4. Keep two columns and rename them: `Date` → `date`, `Price` → `value`. Convert the dates to
   `YYYY-MM-DD` (investing.com uses `MM/DD/YYYY`), and make sure decimals use `.`.
5. Save as `data/manual/cds_tr_5y.csv` and run `uv run python -m pusula.data.update --only macro`.

Check a file: run `uv run python -m pusula.data.update --only macro events`; schema errors are
printed with the file name and the offending value.
