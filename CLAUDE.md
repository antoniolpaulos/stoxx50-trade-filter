# STOXX50 Trade Filter - Project Memory

## Overview

Euro Stoxx 50 0DTE Iron Condor trade filter with GO/NO-GO signals, shadow portfolio tracking, web dashboard, and real-time monitoring.

## Architecture

| Module | Purpose |
|--------|---------|
| `trade_filter.py` | Main entry point, rule evaluation |
| `telegram_api.py` | Unified Telegram API client |
| `calendar_provider.py` | Economic calendar (ForexFactory, TradingEconomics) |
| `portfolio.py` | Shadow portfolio (Always Trade vs Filtered) |
| `logger.py` | Logging with rotation (app/trades/errors) |
| `monitor.py` | Real-time monitoring daemon |
| `dashboard.py` | Flask web dashboard |
| `config_validator.py` | Schema-based config validation |
| `position_sizing.py` | Risk management, Kelly criterion |
| `data_provider.py` | Market data abstraction |
| `backtest.py` | Historical backtesting |
| `telegram_bot.py` | Interactive Telegram bot commands |

## Rules

1. **Intraday Change**: |change| ≤ 1% (blocking)
2. **Economic Calendar**: No high-impact EUR events (blocking)
3. **VIX**: Warning only if > 22 (non-blocking)

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

# Config
python trade_filter.py --validate-config
python trade_filter.py --setup      # Telegram setup wizard

# Telegram Bot
python telegram_bot.py --polling    # Run bot in polling mode (dev)
python telegram_bot.py --webhook-url https://your-domain/telegram/webhook
```

## Test Status

304 tests (run with `pytest tests/ -v`)

## Key Files

- `config.yaml` - User config (gitignored)
- `portfolio.json` - Portfolio data (gitignored)
- `HANDOVER.md` - Detailed documentation
- `templates/dashboard.html` - Dashboard UI

## Telegram Bot

Interactive bot commands for querying status on the go:
- `/status` - Current market conditions and GO/NO-GO verdict
- `/portfolio` - Shadow portfolio summary with filter edge
- `/history [n]` - Recent trade history
- `/analytics` - P&L analytics and performance metrics
- `/help` - Available commands

Features: Rate limiting, user whitelisting, inline keyboards.

## Current State

- Branch: `main` (stable)
- Feature-complete with dashboard, monitoring, position sizing, Telegram bot
- Refactored: telegram_api.py, calendar_provider.py extracted
- 304 tests passing
