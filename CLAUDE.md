# STOXX50 Trade Filter - Project Memory

## Project Overview

**STOXX50 0DTE Iron Condor Trade Filter** - A Python decision support tool that evaluates market conditions for trading Euro Stoxx 50 (STOXX50) 0DTE Iron Condor options. Provides GO/NO-GO verdicts with optional Telegram notifications.

## Architecture

| File | Purpose |
|------|---------|
| `trade_filter.py` | Main engine - rule evaluation, market data, Telegram notifications, setup wizard |
| `backtest.py` | Historical strategy testing with P&L simulation |
| `config.yaml` | User settings (gitignored, contains secrets) |
| `config.yaml.example` | Configuration template |

## Core Rules (AND logic - all must pass)

1. **Rule 1 - VSTOXX Check**: VSTOXX ≤ threshold (default 25)
2. **Rule 2 - Intraday Change**: |change| ≤ threshold (default 1%)
3. **Rule 3 - Economic Calendar**: No high-impact EUR events today

## Additional Filters (`-a` flag)

- Filter A: 20-day MA deviation check
- Filter B: Previous day range check

## Key Dependencies

- `yfinance` - Market data (VSTOXX, Euro Stoxx 50)
- `pyyaml` - Config parsing
- `termcolor` - Color-coded output
- `requests` - Telegram API, economic calendar APIs

## External APIs

- **Telegram Bot API** - Notifications
- **ForexFactory Calendar** - Primary economic events source (EUR filter)
- **Trading Economics** - Backup calendar API (Eurozone countries)
- **Yahoo Finance** - Real-time/historical OHLC data

## Market Data Tickers

| Data | Yahoo Finance Ticker |
|------|---------------------|
| Euro Stoxx 50 | `^STOXX50E` |
| VSTOXX | `^V2TX` |

## Configuration Structure (config.yaml)

```yaml
rules:          # vstoxx_max, intraday_change_max
strikes:        # otm_percent, wing_width
additional_filters:  # ma_deviation_max, prev_day_range_max
calendar:       # always_watch list (EUR events), use_backup_api
telegram:       # enabled, bot_token, chat_id
logging:        # file, level
```

## Conventions

- Strikes round to nearest integer (Euro Stoxx 50 options use 1-point increments)
- Option multiplier: €10 per point
- Color output: green=PASS, red=FAIL, yellow=WARNING, cyan=headers
- Cron runs at 10:00 CET (1 hour after Euro Stoxx 50 market open, Mon-Fri)
- Stateless per-run (no database)

## Common Commands

```bash
python trade_filter.py --setup    # One-time Telegram setup
python trade_filter.py -a         # Run with all filters
python backtest.py --start 2024-01-01 --end 2024-12-31
```

## Cron Setup

```bash
# Run at 10:00 CET, Monday-Friday (1 hour after market open)
0 10 * * 1-5 /path/to/venv/bin/python /path/to/trade_filter.py -a >> /path/to/trade_filter.log 2>&1
```

## Notes

<!-- Add session notes, decisions, or ongoing work below -->
