# STOXX50 Trade Filter - Project Memory

## Overview

Euro Stoxx 50 0DTE Iron Condor trade filter with GO/NO-GO signals, shadow portfolio tracking, web dashboard, and real-time monitoring.

## Architecture

| Module | Purpose |
|--------|---------|
| `trade_filter.py` | Main entry point, rule evaluation |
| `portfolio.py` | Shadow portfolio (Always Trade vs Filtered) |
| `logger.py` | Logging with rotation (app/trades/errors) |
| `monitor.py` | Real-time monitoring daemon |
| `dashboard.py` | Flask web dashboard |
| `config_validator.py` | Schema-based config validation |
| `position_sizing.py` | Risk management, Kelly criterion |
| `data_provider.py` | Market data abstraction |
| `backtest.py` | Historical backtesting |

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
```

## Test Status

269 tests (run with `pytest tests/ -v`)

## Key Files

- `config.yaml` - User config (gitignored)
- `portfolio.json` - Portfolio data (gitignored)
- `HANDOVER.md` - Detailed documentation
- `templates/dashboard.html` - Dashboard UI

## Current State

- Branch: `features`
- Feature-complete with dashboard, monitoring, position sizing
- Ready for merge to main
