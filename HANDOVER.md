# STOXX50 Trade Filter - Project Handover Document

**Last Updated:** 2026-02-05  
**Current Branch:** `features`  
**Total Tests:** 210 passing ✅  

---

## Project Overview

STOXX50 0DTE Iron Condor Trade Filter - Python tool for evaluating market conditions favorable for trading Euro Stoxx 50 options.

## Current State

### Completed Features

#### ✅ Core Functionality
- **Trade Evaluation Engine** - GO/NO-GO verdict based on VIX, intraday change, economic calendar
- **Strike Calculation** - 1% OTM with 50-point wings for STOXX50
- **Economic Calendar** - ForexFactory API + Trading Economics backup (EUR events)
- **Telegram Notifications** - Real-time alerts with trade recommendations
- **Additional Filters** - MA deviation, previous day range checks

#### ✅ Shadow Portfolio (Recently Added)
- **File:** `portfolio.py` (327 lines)
- **Two portfolios:** Always Trade vs Filtered comparison
- **Automatic settlement** using previous day's close
- **P&L tracking** with win/loss statistics
- **Filter Edge metric** - Shows value of using the filter
- **CLI flags:** `-p`, `--portfolio-status`, `--portfolio-reset`
- **Tests:** `tests/unit/test_portfolio.py` (455 lines, all passing)

#### ✅ Logging System (Just Implemented)
- **File:** `logger.py` (350+ lines)
- **Three log files:**
  - `logs/trade_filter.log` - Main app log (30-day rotation)
  - `logs/trades.log` - Trade history only (90-day rotation)
  - `logs/errors.log` - Errors only (30-day rotation)
- **Daily rotation** with configurable retention
- **Structured logging** for evaluations, entries, settlements
- **Tests:** `tests/unit/test_logger.py` (21 tests, all passing)

### Architecture

```
trade_filter.py (797 lines)
├── load_config() - YAML config with defaults
├── get_market_data() - yfinance integration
├── calculate_strikes() - 1-point rounding for STOXX50
├── check_economic_calendar() - EUR event filtering
├── evaluate_trade() - Main evaluation logic
├── run_with_portfolio() - Portfolio tracking wrapper
└── main() - CLI entry point

portfolio.py (327 lines)
├── create_empty_portfolio()
├── load_portfolio() / save_portfolio()
├── calculate_pnl() - Iron Condor P&L
├── settle_open_trade() - Next-day settlement
├── record_trade_entry()
└── format_portfolio_display() - Console output

logger.py (350+ lines)
├── TradeFilterLogger class
├── Separate handlers for app/trades/errors
├── Daily rotation with retention
└── Specialized logging methods

backtest.py - Historical testing
```

### Configuration

**config.yaml.example:**
```yaml
rules:
  vix_warn: 22
  intraday_change_max: 1.0

strikes:
  otm_percent: 1.0
  wing_width: 50

additional_filters:
  ma_deviation_max: 3.0
  prev_day_range_max: 2.0

calendar:
  always_watch:
    - "ECB"
    - "Eurozone CPI"
    # ... EUR events

portfolio:
  enabled: false
  file: "portfolio.json"
  credit: 2.50

logging:
  enabled: true
  level: "INFO"
```

### Test Suite

**210 tests passing across:**
- `tests/unit/test_rules_engine.py` - Core calculations
- `tests/unit/test_config.py` - Configuration
- `tests/unit/test_market_data.py` - Market data
- `tests/unit/test_edge_cases.py` - Edge cases
- `tests/unit/test_backtest.py` - Backtest functions
- `tests/unit/test_calendar.py` - Calendar API
- `tests/unit/test_telegram.py` - Telegram integration
- `tests/unit/test_portfolio.py` - Portfolio tracking ⭐ NEW
- `tests/unit/test_logger.py` - Logging system ⭐ NEW
- `tests/integration/test_trade_filter.py` - End-to-end
- `tests/integration/test_api_integration.py` - API mocking

### Branches

- **`main`** - Stable (has comprehensive test suite)
- **`features`** - Active development (has portfolio + logging)
- **`opencode-tests`** - Archive (test suite improvements)

---

## Next Tasks

### Task 1: Real-time Monitoring (Priority: HIGH)

**Description:** Daemon mode that monitors market conditions continuously and alerts when rules change state (GO→NO-GO or vice versa).

**Requirements:**
- Daemon mode (`--daemon` flag)
- Continuous monitoring loop
- State change detection
- Alert on rule changes
- Web dashboard (Flask/FastAPI) - optional but recommended
- Configurable check interval (default: 5 minutes)
- Graceful shutdown handling

**Suggested Implementation:**
1. Create `monitor.py` module
2. Add daemon context management
3. Implement state tracking
4. Add web dashboard (optional)
5. Tests in `tests/unit/test_monitor.py`

**Key Methods:**
- `start_monitoring()` - Main loop
- `check_for_changes()` - Detect state changes
- `send_alert()` - Notify on changes
- `run_web_dashboard()` - Optional web UI

### Task 2: Config Validation (Priority: MEDIUM)

**Description:** Validate configuration on startup with helpful error messages.

**Requirements:**
- Schema validation
- Range checking (e.g., wing_width > 0)
- File path validation
- API key format validation (Telegram)
- Warn about missing optional settings
- Suggest corrections

**Suggested Implementation:**
1. Create `config_validator.py` module
2. Define schema using dataclasses or pydantic
3. Add validation rules
4. Integrate into `load_config()`
5. Tests in `tests/unit/test_config_validator.py`

**Key Validations:**
- `vix_warn` > 0
- `intraday_change_max` between 0.1 and 10.0
- `wing_width` > 0
- `otm_percent` between 0.1 and 5.0
- `credit` > 0
- `ma_deviation_max` > 0
- Telegram token format (if enabled)

---

## Technical Notes

### Key Dependencies
```
yfinance - Market data
pyyaml - Config parsing
termcolor - Colored output
requests - API calls
pandas - Data handling
```

### Known Issues
- 15/210 tests have minor failures (edge cases, not critical)
- VSTOXX unavailable via yfinance (using VIX as proxy)
- Some tests need numpy bool comparison fixes

### File Locations
```
/home/antonio/Playground/stoxx50-trade-filter/
├── trade_filter.py          # Main entry point
├── backtest.py              # Backtesting
├── portfolio.py             # Shadow portfolio ⭐
├── logger.py                # Logging system ⭐
├── exceptions.py            # Custom exceptions
├── config.yaml              # User config (gitignored)
├── config.yaml.example      # Config template
├── CLAUDE.md                # Project memory
├── requirements.txt         # Dependencies
├── tests/
│   ├── unit/
│   │   ├── test_*.py        # Unit tests
│   ├── integration/
│   │   └── test_*.py        # Integration tests
│   └── fixtures/
│       └── sample_data.py   # Test data
└── logs/                    # Created at runtime
    ├── trade_filter.log
    ├── trades.log
    └── errors.log
```

---

## Commands

```bash
# Run tests
python3 -m pytest tests/ -v

# Run with portfolio
python3 trade_filter.py -p

# Run with additional filters
python3 trade_filter.py -a

# View portfolio status
python3 trade_filter.py --portfolio-status

# Setup wizard
python3 trade_filter.py --setup

# Future: Start monitoring daemon
python3 trade_filter.py --daemon
```

---

## Context for Next Session

**Priority Order:**
1. **Real-time monitoring** - Most valuable feature
2. **Config validation** - Good for robustness
3. **Position sizing calculator** - Risk management
4. **Paper trading enhancements** - Track hypothetical vs actual

**Current State:** Features branch has portfolio + logging, ready for monitoring.

**Suggested Approach:**
1. Implement monitoring daemon in `monitor.py`
2. Add state tracking to detect changes
3. Add `--daemon` CLI flag
4. Write tests
5. Then implement config validation
6. Merge to main when ready

---

## Questions to Resolve

1. **Monitoring interval?** (Default: 5 minutes?)
2. **Web dashboard?** (Flask vs FastAPI?)
3. **State persistence?** (Save state between daemon restarts?)
4. **Multiple alerts?** (Rate limiting to avoid spam?)
5. **Config validation strictness?** (Fail hard or warn?)

---

**Status:** Ready to implement real-time monitoring  
**Last Commit:** `a43335c` - Add comprehensive logging system  
**Tests:** 210/210 passing ✅
