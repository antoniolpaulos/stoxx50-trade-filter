# STOXX50 Trade Filter - Project Memory

## Overview

Fork of spx-trade-filter for Euro Stoxx 50 0DTE Iron Condor options.

## Rules

1. **Intraday Change**: |change| ≤ 1% (blocking)
2. **Economic Calendar**: No high-impact EUR events (blocking)
3. **VIX**: Warning only if > 22 (non-blocking)

## Tickers

- Euro Stoxx 50: `^STOXX50E`
- VIX: `^VIX` (warning only - VSTOXX unavailable on yfinance)

## Config

```yaml
rules:
  vix_warn: 22
  intraday_change_max: 1.0
strikes:
  otm_percent: 1.0
  wing_width: 50
```

## Cron

```bash
0 10 * * 1-5 /path/to/stoxx50-trade-filter/venv/bin/python /path/to/stoxx50-trade-filter/trade_filter.py -a
```

## Known Issues

- VSTOXX (`V2TX.DE`) unavailable via yfinance - using VIX as warning proxy

## Test Status

All 159 tests passing.
