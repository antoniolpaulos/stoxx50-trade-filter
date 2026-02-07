# STOXX50 Trade Filter - Project Memory

## Overview

Euro Stoxx 50 0DTE Iron Condor trade filter with GO/NO-GO signals, shadow portfolio tracking, web dashboard, and real-time monitoring.

## Architecture

| Module | Purpose |
|--------|---------|
| `trade_filter.py` | Main entry point, rule evaluation |
| `ibkr_provider.py` | IBKR TWS API for real option prices |
| `yahoo_options.py` | Yahoo Finance VSTOXX-based credit estimation |
| `telegram_api.py` | Unified Telegram API client |
| `calendar_provider.py` | Economic calendar (ForexFactory, TradingEconomics) |
| `portfolio.py` | Shadow portfolio (Always Trade vs Filtered) |
| `logger.py` | Logging with rotation (app/trades/errors) |
| `monitor.py` | Real-time monitoring daemon |
| `dashboard.py` | Flask web dashboard |
| `config_validator.py` | Schema-based config validation |
| `position_sizing.py` | Risk management, Kelly criterion |
| `data_provider.py` | Market data abstraction |
| `backtest.py` | Historical backtesting with dynamic credit |
| `telegram_bot.py` | Interactive Telegram bot commands |

## Rules

1. **Intraday Change**: |change| ≤ 1% (blocking)
2. **Economic Calendar**: No high-impact EUR events (blocking)
3. **VIX**: Warning only if > 22 (non-blocking)

## Credit Data Sources

Fallback chain for iron condor credit:

| Priority | Source | Requirement |
|----------|--------|-------------|
| 1 | IBKR Gateway | IB Gateway on port 4001 (or TWS on 7496) |
| 2 | Yahoo VSTOXX | None (free, uses V2TX.DE) |
| 3 | Config | None (fixed €2.50 default) |

```bash
# Test IBKR connection (requires Gateway or TWS running)
python -c "from ibkr_provider import IBKRProvider; p = IBKRProvider(port=4001); p.connect() and print(p.get_index_price())"

# Test Yahoo fallback
python yahoo_options.py
```

**IBKR Setup Notes:**
- Contract: conId=4356500, exchange=EUREX (not DTB)
- Delayed data enabled as fallback
- IB Gateway 10.37 at `~/ibgateway/`, managed by IBC 3.23.0 at `~/ibc/`
- Start: `~/ibc/gatewaystart.sh -inline` (approve 2FA on IBKR mobile app)
- API port: 4001 (Gateway live), 7496 (TWS live)

## Quick Commands

```bash
# Basic usage
python trade_filter.py              # Basic rules
python trade_filter.py -a           # All filters
python trade_filter.py -p           # With portfolio tracking

# Portfolio
python trade_filter.py --portfolio-status
python trade_filter.py --portfolio-reset

# Dashboard & Monitoring
python dashboard.py                 # Web UI at localhost:5000
python trade_filter.py --daemon     # Background monitoring

# Backtest
python backtest.py -s 2026-01-01 -e 2026-02-06        # Fixed credit
python backtest.py -s 2026-01-01 -e 2026-02-06 -d     # Dynamic credit (volatility-based)

# Config
python trade_filter.py --validate-config
python trade_filter.py --setup      # Telegram setup wizard

# Telegram Bot
python telegram_bot.py --polling    # Run bot in polling mode (dev)
python telegram_bot.py --webhook-url https://your-domain/telegram/webhook
```

## Test Status

357 tests (run with `./venv/bin/pytest tests/ -v`)

## Key Files

- `config.yaml` - User config (gitignored)
- `config.yaml.example` - Config template
- `portfolio.json` - Portfolio data (gitignored)
- `docs/ibkr_integration_plan.md` - IBKR setup notes

## Telegram Bot

| Command | Description |
|---------|-------------|
| `/status` | Current market conditions and GO/NO-GO |
| `/portfolio` | P&L summary with filter edge |
| `/chart` | P&L comparison chart |
| `/filter` | Run trade filter now |
| `/history [n]` | Recent trade history |
| `/backtest [days]` | Run backtest (max 365) |
| `/alerts [on\|off]` | Toggle notifications |
| `/help` | Show all commands |

**Service:** `systemctl --user start stoxx50-bot`

## Current State

- Feature-complete with dashboard, monitoring, position sizing, Telegram bot
- IBKR integration working via IB Gateway (port 4001) or TWS (port 7496)
- IBC automates Gateway login (just approve 2FA on mobile)
- Yahoo VSTOXX fallback for credit estimation when Gateway/TWS offline
- Dynamic credit backtest using historical volatility
- 357 tests passing (7 skipped — IBKR live tests need Gateway running)

## Branch Workflow

- **Develop on `features`** - all work happens here
- **Merge to `main`** - only when stable, main is production-ready
- Stay on `features` after merging

## Session Notes (2026-02-06)

### IBKR Integration
- Implemented `ibkr_provider.py` with real option quotes via Gateway/TWS
- Fixed contract spec: conId=4356500, exchange=EUREX, delayed data fallback
- IB Gateway 10.37 + IBC 3.23.0 working (standalone installer + symlinks in `~/Jts/ibgateway/1037/`)
- Ports: 4001 (Gateway live), 4002 (Gateway paper), 7496 (TWS live), 7497 (TWS paper)

### Yahoo Finance Fallback
- `yahoo_options.py` uses VSTOXX (V2TX.DE) for implied volatility
- Estimates credit via Black-Scholes when TWS not running
- Free alternative, no account needed

### Backtest Improvements
- `--dynamic-credit` flag estimates credit from 20-day realized volatility
- More realistic P&L than fixed €2.50 assumption
- Dynamic: ~€6/trade average vs Fixed: €25/trade

### Scripts Added
- `scripts/setup_ibc.sh` - IBC setup (incomplete, for reference)
- `scripts/setup_ibeam.sh` - IBeAM setup (wrong API, doesn't work with ib_insync)

### TODO
- [ ] Add historical VSTOXX data source for backtest (V2TX.DE has no history)
- [ ] Optionally run Gateway on Xvfb for truly hidden window
