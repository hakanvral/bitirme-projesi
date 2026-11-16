Test fixtures. These are **synthetic** values in the providers' response *format*. They are not
real market data and must never be used as data.

* `evds_series_daily.json`, `evds_series_monthly.json`: EVDS `series=` response shape
  (`items[]` with `Tarih` plus the series code with `.` replaced by `_`).
