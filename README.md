# STOXX50 0DTE Iron Condor Trade Filter

A Python tool that determines if market conditions are favorable for trading Euro Stoxx 50 0DTE (zero days to expiration) Iron Condors.

## Features

- **Rule-based Go/No-Go decision** with color-coded terminal output
- **VSTOXX check** - Avoids trading when volatility is too high
- **Intraday change check** - Avoids strong trending days
- **Economic calendar** - Automatically detects high-impact EUR events (ECB, CPI, GDP, etc.)
- **Additional filters** (optional):
  - 20-day moving average deviation
  - Previous day range
- **Telegram Bot** - Interactive commands for status, portfolio, charts, and backtesting
- **Telegram notifications** - Get GO/NO-GO alerts on your phone
- **Configurable thresholds** via YAML config file
- **Backtesting** - Test the strategy on historical data

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/stoxx50-trade-filter.git
cd stoxx50-trade-filter

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create config from template
cp config.yaml.example config.yaml
```

## Configuration

Edit `config.yaml` to customize thresholds:

```yaml
rules:
  vstoxx_max: 25                 # Max VSTOXX level
  intraday_change_max: 1.0       # Max intraday change (%)

strikes:
  otm_percent: 1.0               # How far OTM for short strikes (%)
  wing_width: 50                 # Wing width in points

additional_filters:
  ma_deviation_max: 3.0          # Max % deviation from 20 DMA
  prev_day_range_max: 2.0        # Max previous day range (%)
```

### Telegram Setup

Run the setup wizard:

```bash
python trade_filter.py --setup
```

Or manually edit `config.yaml`:

```yaml
telegram:
  enabled: true
  bot_token: "your_bot_token"    # Get from @BotFather
  chat_id: "your_chat_id"        # Get by messaging your bot, then run --setup
```

### Telegram Bot Commands

Once configured, the bot supports these interactive commands:

| Command | Description |
|---------|-------------|
| `/help` | Show all available commands |
| `/status` | Current market status and GO/NO-GO verdict |
| `/portfolio` | Shadow portfolio performance summary |
| `/chart` | P&L comparison chart (Always Trade vs Filtered) |
| `/filter` | Run the trade filter and get results |
| `/config` | Show current configuration settings |
| `/alerts [on\|off]` | Toggle real-time market alerts |
| `/backtest [days]` | Run historical backtest (max 365 days) |

**Example:**
```
/backtest 30
```
Returns a summary of strategy performance over the last 30 days.

### Running the Bot as a Service

For persistent operation, run the bot as a systemd user service:

```bash
# Create service file
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/stoxx50-bot.service << 'EOF'
[Unit]
Description=STOXX50 Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/stoxx50-trade-filter
ExecStart=/path/to/stoxx50-trade-filter/venv/bin/python telegram_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

# Enable and start
systemctl --user daemon-reload
systemctl --user enable stoxx50-bot
systemctl --user start stoxx50-bot

# Check status
systemctl --user status stoxx50-bot
```

## Usage

```bash
# Basic rules only
python trade_filter.py

# Include additional filters
python trade_filter.py -a

# Use custom config file
python trade_filter.py -c /path/to/config.yaml

# Run setup wizard
python trade_filter.py --setup
```

### Example Output

```
============================================================
  STOXX50 0DTE IRON CONDOR TRADE FILTER
  2026-02-03 10:00:00
============================================================

MARKET DATA:
  VSTOXX:           18.45
  STOXX Current:    5124.32
  STOXX Open:       5098.76
  Intraday Change:  +0.50%

RULE EVALUATION:
  [PASS] Rule 1: VSTOXX = 18.45 (<= 25)
  [PASS] Rule 2: Intraday change = +0.50% (|change| <= 1.0%)
  [PASS] Rule 3: No high-impact EUR events today

VERDICT:

   ██████╗  ██████╗
  ██╔════╝ ██╔═══██╗
  ██║  ███╗██║   ██║
  ██║   ██║██║   ██║
  ╚██████╔╝╚██████╔╝
   ╚═════╝  ╚═════╝

  [GO] CONDITIONS FAVORABLE FOR IRON CONDOR

  RECOMMENDED STRIKES (1.0% OTM):
    Short Call: 5175
    Short Put:  5073

  Suggested structure:
    Buy Put   @ 5023
    Sell Put  @ 5073
    Sell Call @ 5175
    Buy Call  @ 5225
```

## Scheduled Runs (Cron)

To run automatically at **10:00 CET** (1 hour after Euro Stoxx 50 market open) every weekday:

```bash
# Edit crontab
crontab -e

# Add this line (adjust paths as needed):
# STOXX50 0DTE Iron Condor filter - runs 10:00 CET Mon-Fri
0 10 * * 1-5 /path/to/stoxx50-trade-filter/venv/bin/python /path/to/stoxx50-trade-filter/trade_filter.py -a >> /path/to/stoxx50-trade-filter/trade_filter.log 2>&1
```

**Example with absolute paths:**

```bash
0 10 * * 1-5 /home/projects/stoxx50-trade-filter/venv/bin/python /home/projects/stoxx50-trade-filter/trade_filter.py -a >> /home/projects/stoxx50-trade-filter/trade_filter.log 2>&1
```

### Time Zone Notes

| CET | Event |
|-----|-------|
| 09:00 | Euro Stoxx 50 market opens |
| 10:00 | **Cron runs here** |
| 17:30 | Euro Stoxx 50 market closes |

Ensure your server's timezone is set correctly:

```bash
timedatectl set-timezone Europe/Amsterdam
```

## Backtesting

Test the strategy on historical data:

```bash
# Backtest a full year
python backtest.py --start 2024-01-01 --end 2024-12-31

# With custom parameters
python backtest.py -s 2024-06-01 -e 2024-12-31 --credit 3.00 --wing-width 75

# Summary only (no daily details)
python backtest.py -s 2024-01-01 -e 2024-12-31 --quiet
```

**Notes:**
- Backtesting uses open-to-close change as a proxy for trending days (since intraday data at 10:00 CET is unavailable)
- Economic calendar (Rule 3) is not applied in backtests as historical event data is unavailable
- 12-month backtest shows filter edge of ~€1,800 by avoiding all losing trades

### Parameter Optimization

Find optimal strategy parameters using grid search with walk-forward validation:

```bash
# Standard 2-year optimization
python optimize.py -s 2023-01-01 -e 2024-12-31

# Quick test with reduced parameter grid
python optimize.py -s 2024-01-01 -e 2024-12-31 --quick

# Custom parameter ranges
python optimize.py -s 2023-01-01 -e 2024-12-31 \
    --otm-range 0.5,0.75,1.0,1.25 \
    --wing-range 25,50 \
    --intraday-range 0.75,1.0,1.25 \
    --credit-range 2.0,2.5,3.0

# Walk-forward validation (6-month train, 2-month test windows)
python optimize.py -s 2023-01-01 -e 2024-12-31 \
    --train-months 6 --test-months 2

# Export results
python optimize.py -s 2024-01-01 -e 2024-12-31 -o results.csv

# Parallel workers for faster execution
python optimize.py -s 2023-01-01 -e 2024-12-31 --workers 4
```

**Optimizable Parameters:**

| Parameter | Default | Search Range |
|-----------|---------|--------------|
| OTM Percent | 1.0% | 0.5% - 2.0% |
| Wing Width | 50 pts | 25 - 100 pts |
| Intraday Change Max | 1.0% | 0.5% - 2.0% |
| Credit | €2.50 | €1.50 - €4.00 |

**Output:**

The optimizer ranks parameter sets by out-of-sample Sortino ratio and provides:
- In-sample vs out-of-sample performance comparison
- Robustness score (out-of-sample / in-sample ratio)
- Recommended parameters with YAML-formatted config snippet
- Overfitting warnings based on robustness score

**Tips:**
- Run with `--quick` first to validate your parameter ranges
- Use walk-forward validation (`--train-months 6 --test-months 2`) to detect overfitting
- Robustness score < 0.5 indicates likely overfitting
- Re-run optimizer quarterly with new data

## Market Data

| Data | Yahoo Finance Ticker |
|------|---------------------|
| Euro Stoxx 50 | `^STOXX50E` |
| VSTOXX | `^V2TX` |

## Files

| File | Description |
|------|-------------|
| `trade_filter.py` | Main trade filter script |
| `backtest.py` | Backtesting script |
| `optimize.py` | Parameter optimization tool |
| `telegram_api.py` | Telegram API client |
| `calendar_provider.py` | Economic calendar providers |
| `config.yaml` | Your configuration (gitignored) |
| `config.yaml.example` | Configuration template |
| `requirements.txt` | Python dependencies |

## License

MIT

---

# Web Dashboard & Position Sizing Guide

## Overview

The dashboard provides a complete graphical interface for the STOXX50 Trade Filter. It includes:

- **Control Panel** - Run the filter once or control the monitoring daemon
- **Shadow Portfolio** - Track paper trading performance for Always Trade vs Filtered strategies
- **P&L Charts** - Interactive Chart.js visualization comparing cumulative P&L
- **Position Sizing Calculator** - Calculate optimal position size based on risk parameters
- **Real-time Monitoring** - Background daemon with state change detection
- **Risk Metrics** - Kelly criterion, profit factor, expected value

---

## Quick Start

### Launch the Dashboard

```bash
# Standalone (recommended)
python3 dashboard.py

# Or via trade_filter.py
python3 trade_filter.py --dashboard

# Custom port
python3 dashboard.py --port 8080
```

The dashboard will be available at **http://localhost:5000**

---

## Dashboard Sections

### 1. Control Panel

The top section provides quick access to common actions:

| Button | Description |
|--------|-------------|
| **Run Basic Filter** | Execute filter with Rules 1-2 only (intraday change + economic calendar) |
| **Run Full Filter** | Execute filter with all 5 rules (includes MA deviation + VIX structure) |
| **Start Daemon** | Begin continuous background monitoring |
| **Stop Daemon** | Stop the monitoring daemon |

**Quick Signal Display** shows the current GO/NO-GO state at a glance.

---

### 2. Shadow Portfolio

Compare two paper trading strategies side-by-side:

| Strategy | Description |
|----------|-------------|
| **Always Trade** | Enters every trading day regardless of filter |
| **Filtered** | Only enters on GO signal days |

Each card displays:
- **Total P&L** - Cumulative profit/loss in euros
- **Trades** - Number of trades taken
- **Win Rate** - Percentage of winning trades (with visual bar)
- **Wins/Losses** - Raw count
- **Daily P&L History** - Toggleable table showing each trade

**Filter Edge** - The bottom section shows the difference between strategies (Filtered - Always Trade). A positive edge means the filter is saving you money.

---

### 3. Position Sizing Calculator

Calculate how many Iron Condor spreads to trade based on your risk tolerance.

#### Interface

| Input | Description | Default |
|-------|-------------|---------|
| **Account Balance** | Total account size in € | €10,000 |
| **Credit Received** | Premium received per spread | €10.00 |
| **Wing Width** | Distance between strikes in points | 50 |
| **Risk % per Trade** | Max % of account to risk | 1.0% |

#### Using Kelly Criterion

Toggle **"Use Kelly Criterion"** to calculate optimal size based on your historical win rate and average win/loss:

```bash
# Example API call with Kelly
/api/position-size?balance=10000&credit=10.0&wing_width=50&kelly=true&win_rate=0.65&avg_win=250&avg_loss=-350
```

#### Output Metrics

| Metric | Description |
|--------|-------------|
| **Suggested Size** | Number of spreads to trade |
| **Max Loss** | Maximum potential loss in € |
| **Total Credit** | Premium received upfront |
| **Risk/Reward** | Ratio of max loss to credit received |
| **Kelly Criterion** | Optimal position % (if enabled) |
| **Quarter Kelly** | Conservative sizing recommendation |

#### Position Size Formula

```
Max Loss per Spread = (Wing Width - Credit) × Multiplier
                   = (50 - €10) × €10
                   = €400

Number of Spreads = Account Balance × Risk % / Max Loss per Spread
                  = €10,000 × 0.01 / €400
                  = 2.5 → 2 spreads (rounded down)
```

---

### 4. Market Status

Real-time market data:

| Metric | Description |
|--------|-------------|
| **Trade State** | Current GO/NO-GO status |
| **STOXX Current** | Real-time Euro Stoxx 50 price |
| **STOXX Open** | Today's opening price |
| **Intraday Change** | Price change from open (%) |
| **VIX** | Volatility index (warning indicator) |

---

### 5. Rules Status

Live evaluation of each filter rule:

| Status | Meaning |
|--------|---------|
| ✅ **PASS** | Rule passed |
| ❌ **FAIL** | Rule failed (blocks trading) |
| ⚠️ **WARN** | Warning (VIX elevated) |
| N/A | Rule not applicable |

---

### 6. Monitoring Statistics

Daemon performance metrics:

| Metric | Description |
|--------|-------------|
| **Checks** | Number of evaluations performed |
| **State Changes** | Times GO↔NO-GO switched |
| **Errors** | Data fetch or calculation errors |
| **Uptime** | Daemon runtime |

---

### 7. History

Recent state changes with timestamps.

---

## API Endpoints

The dashboard exposes REST APIs for programmatic access:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Current trade state and market data |
| `/api/portfolio` | GET | Shadow portfolio data with Filter Edge |
| `/api/position-size` | GET | Calculate position size |
| `/api/risk-metrics` | GET | Calculate risk metrics |
| `/api/history` | GET | State history (param: `n` = number of records) |
| `/api/daemon/status` | GET | Daemon running status |
| `/api/daemon/start` | POST | Start daemon (param: `interval` = seconds) |
| `/api/daemon/stop` | POST | Stop daemon |
| `/api/run-once` | POST | Execute filter once (param: `additional` = true/false) |
| `/api/force-check` | POST | Force immediate re-evaluation |

### Example API Calls

```bash
# Get current status
curl http://localhost:5000/api/status

# Get portfolio data
curl http://localhost:5000/api/portfolio

# Calculate position size (€10,000 account, 1% risk)
curl "http://localhost:5000/api/position-size?balance=10000&credit=10.0&risk_percent=1.0"

# Calculate with Kelly criterion
curl "http://localhost:5000/api/position-size?balance=10000&credit=10.0&kelly=true&win_rate=0.65&avg_win=250&avg_loss=-350"

# Get risk metrics
curl "http://localhost:5000/api/risk-metrics?win_rate=0.65&avg_win=250&avg_loss=-350"
```

### API Response Examples

**Position Size Response:**
```json
{
  "success": true,
  "position": {
    "spreads": 2,
    "max_loss_per_spread": 475.0,
    "total_max_loss": 950.0,
    "total_credit": 50.0,
    "risk_reward_ratio": 19.0,
    "kelly_percent": 16.0,
    "risk_amount": 100.0,
    "account_balance": 10000.0
  }
}
```

**Risk Metrics Response:**
```json
{
  "success": true,
  "metrics": {
    "win_rate": 65.0,
    "avg_win": 250.0,
    "avg_loss": -350.0,
    "profit_factor": 1.33,
    "kelly_percent": 16.0,
    "kelly_half": 8.0,
    "kelly_quarter": 4.0,
    "expected_value": 40.0
  }
}
```

---

## Position Sizing Deep Dive

### Why Position Sizing Matters

Professional traders know that **how much you risk** is more important than **when you trade**. Proper position sizing:

1. **Prevents Ruin** - Even great strategies fail without proper sizing
2. **Compounds Returns** - Lets winners run while keeping losers small
3. **Provides Discipline** - Removes emotion from trade sizing

### Kelly Criterion Explained

The Kelly Criterion calculates the optimal position size based on your edge:

```
Kelly % = W - [(1-W) / R]
```

Where:
- **W** = Win rate (e.g., 65% = 0.65)
- **R** = Win/Loss ratio (Avg Win / |Avg Loss|)

**Example:**
- Win rate: 65%
- Avg Win: €250
- Avg Loss: -€350
- R = 250/350 = 0.71

```
Kelly = 0.65 - [(1-0.65) / 0.71]
     = 0.65 - 0.35 / 0.71
     = 0.65 - 0.49
     = 0.16 (16%)
```

**Warning:** Full Kelly is aggressive. Most traders use **Half Kelly** (8%) or **Quarter Kelly** (4%) for reduced volatility.

### Iron Condor Risk/Reward

For a typical Iron Condor:

| Parameter | Value |
|-----------|-------|
| Wing Width | 50 points |
| Credit Received | €10.00 |
| Max Loss | €400 per spread |
| Risk/Reward | 1:4 |

This means for every €1 of max profit, you risk €4 (if the trade loses).

---

## Running the Daemon

For continuous background monitoring:

```bash
# Start with default 5-minute interval
python3 trade_filter.py --daemon

# Or with custom interval (e.g., 1 minute)
python3 trade_filter.py --daemon --monitor-interval 60

# From dashboard
# Click "Start Daemon" in the Control Panel
```

The daemon will:
- Check market conditions every N seconds
- Log state changes to `logs/trade_filter.log`
- Send Telegram alerts on state transitions
- Track history for analysis

---

## Files

| File | Description |
|------|-------------|
| `dashboard.py` | Web dashboard server (Flask) |
| `telegram_bot.py` | Interactive Telegram bot |
| `position_sizing.py` | Position sizing calculator |
| `monitor.py` | Real-time monitoring daemon |
| `portfolio.py` | Shadow portfolio tracking |
| `logger.py` | Structured logging system |
| `config_validator.py` | Configuration validation |
| `trade_filter.py` | Main trade filter script |
| `backtest.py` | Historical backtesting |
