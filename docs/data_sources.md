# Data sources

Declared in `config/data_sources.yaml`. Each series has an adapter and (where useful) a manual-CSV
fallback (`data/manual/README.md`).

## Verification status (2026-11-16)

| Source | Endpoint / symbol | Status |
|---|---|---|
| EVDS (TCMB) | `https://evds3.tcmb.gov.tr/igmevdsms-dis/`, header `key` | Endpoint and auth checked: `categories/` returns JSON with the key, and 403 `Required request header 'key' is not present` without it. evds2 redirects to evds3. **Series codes not verified yet** → `TODO_VERIFY` (see below). |
| Yahoo Finance | `query1/query2.finance.yahoo.com` via `yfinance` | Host reachable; symbols are validated by `python -m pusula.universe.validate`. |
| EPİAŞ | `seffaflik.epias.com.tr` (website export) | Reachable. PTF via manual export (D-005); live API optional. |
| Borsa Istanbul | `www.borsaistanbul.com` | Reachable; source of the BIST30 lists and TLREF. |
| CDS | none (manual CSV) | — |

## How EVDS codes are verified

```bash
uv run python -m pusula.data.evds_lookup "policy rate" "exchange rate" "consumer price" "market participants" "tlref" "benchmark"
```

The command searches EVDS data-group names through the metadata endpoints (`datagroups/`,
`serieList/`) and prints the series codes. Each verified code goes into
`config/data_sources.yaml`, with the lookup recorded in the table below.

| Series id | EVDS code | Data group | Verified on |
|---|---|---|---|
| policy_rate | TODO_VERIFY | | |
| tlref | TODO_VERIFY | | |
| tr_2y | TODO_VERIFY | | |
| tr_10y | TODO_VERIFY | | |
| usdtry | TODO_VERIFY | | |
| eurtry | TODO_VERIFY | | |
| cpi | TODO_VERIFY | | |
| cpi_exp_12m | TODO_VERIFY | | |
