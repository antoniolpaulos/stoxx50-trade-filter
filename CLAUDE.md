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

## Shadow Portfolio

Two paper trading accounts tracked via `-p` flag:
- **Always Trade**: Enters every trading day
- **Filtered**: Only trades on GO signals

```bash
python trade_filter.py -p              # Run with portfolio tracking
python trade_filter.py --portfolio-status  # View portfolio
python trade_filter.py --portfolio-reset   # Reset data
```

Settlement: Next-day (previous close used to calculate P&L)

Data stored in `portfolio.json` (gitignored)

## Cron

```bash
# Without portfolio
0 10 * * 1-5 /path/to/venv/bin/python /path/to/trade_filter.py -a

# With portfolio tracking
0 10 * * 1-5 /path/to/venv/bin/python /path/to/trade_filter.py -a -p
```

## Known Issues

- VSTOXX (`V2TX.DE`) unavailable via yfinance - using VIX as warning proxy

## Test Status

All 189 tests passing.
