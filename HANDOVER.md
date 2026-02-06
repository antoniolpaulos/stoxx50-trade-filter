# STOXX50 Trade Filter - Project Handover Document

**Last Updated:** 2026-02-06
**Current Branch:** `features`
**Main Branch:** `main` (stable)
**Status:** Production-ready with verified backtest results

---

## Project Overview

STOXX50 0DTE Iron Condor Trade Filter - Python tool for evaluating market conditions favorable for trading Euro Stoxx 50 options.

---

## Current State

### Key Parameters
- **Credit:** €10.00 per spread (max profit €100, max loss €400)
- **Wing Width:** 50 points
- **OTM Percent:** 1%
- **Intraday Filter:** 1% open-to-close threshold

### 12-Month Backtest Results (2025-02 to 2026-02)

| Metric | Always Trade | Filtered |
|--------|--------------|----------|
| Trades | 253 | 208 |
| Win Rate | 92% | **100%** |
| Losses | 20 | **0** |
| Total P&L | €18,952 | €20,800 |
| **Filter Edge** | | **+€1,848** |

The filter correctly identifies trending days (>1% move) and avoided all 20 losses.

---

## Architecture

```
trade_filter.py          # Main entry point
backtest.py              # Historical testing (open-to-close filter)
portfolio.py             # Shadow portfolio tracking
dashboard.py             # Flask web dashboard (530 lines)
templates/dashboard.html # Dashboard UI (1,426 lines)
telegram_bot.py          # Telegram bot (8 commands)
monitor.py               # Real-time monitoring daemon
position_sizing.py       # Kelly criterion calculator
config_validator.py      # Config validation
logger.py                # Structured logging
```

### Recent Refactoring
- **Dashboard:** Moved 1,400 lines of embedded HTML to `templates/dashboard.html`
- **Backtest:** Changed filter from estimated entry price to open-to-close change
- **Defaults:** Credit €2.50 → €10.00 across all files

---

## Features

### ✅ Core
- Trade evaluation engine (GO/NO-GO verdict)
- Economic calendar (ForexFactory + Trading Economics)
- Strike calculation (1% OTM, 50-point wings)

### ✅ Telegram Bot (8 Commands)
| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/status` | Current market status |
| `/portfolio` | P&L summary |
| `/chart` | P&L comparison chart |
| `/filter` | Run trade filter |
| `/config` | Show configuration |
| `/alerts [on\|off]` | Toggle alerts |
| `/backtest [days]` | Run backtest (max 365) |

**Service:** `systemctl --user start stoxx50-bot`

### ✅ Web Dashboard
- Control panel (run filter, start/stop daemon)
- Shadow portfolio comparison (Always Trade vs Filtered)
- P&L charts (Chart.js)
- Real-time market status
- API endpoints for integration

### ✅ Shadow Portfolio
- Two portfolios: Always Trade vs Filtered
- Automatic P&L calculation
- Filter Edge metric
- JSON storage (`portfolio.json`)

---

## Configuration

**config.yaml:**
```yaml
rules:
  intraday_change_max: 1.0

strikes:
  otm_percent: 1.0
  wing_width: 50

portfolio:
  enabled: false
  credit: 10.00  # Changed from 2.50

telegram:
  enabled: true
  bot_token: "..."
  chat_id: "..."
```

---

## Development Workflow

```bash
# Work on features branch
git checkout features

# When ready, merge to main
git checkout main
git merge features
git push
git checkout features
```

---

## Commands

```bash
# Run filter
python trade_filter.py -a

# Backtest
python backtest.py -s 2025-01-01 -e 2025-12-31

# Dashboard
python dashboard.py

# Telegram bot
systemctl --user start stoxx50-bot

# Tests
python -m pytest tests/ -v
```

---

## Next Priorities

1. **Backtest Optimizer** (`optimize.py`)
   - Plan ready: `docs/backtest_optimizer_plan.md`
   - Grid search over parameters
   - Walk-forward validation
   - Sortino ratio ranking

---

## Files

```
/home/antonio/Playground/stoxx50-trade-filter/
├── trade_filter.py
├── backtest.py
├── portfolio.py
├── dashboard.py
├── telegram_bot.py
├── monitor.py
├── position_sizing.py
├── config_validator.py
├── logger.py
├── templates/
│   └── dashboard.html
├── docs/
│   └── backtest_optimizer_plan.md
├── tests/
│   ├── unit/
│   └── integration/
├── config.yaml (gitignored)
├── config.yaml.example
├── portfolio.json (gitignored)
└── HANDOVER.md
```

---

**Last Commit:** See `git log -1`
**Branch:** `features` (develop here, merge to `main` when stable)
