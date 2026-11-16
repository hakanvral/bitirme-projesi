"""Data source adapters. Each returns tidy pandas DataFrames in a common long format.

* prices: ``date, ticker, open, high, low, close, adj_close, volume``
* macro : ``date, series, value[, release_date]``
"""
