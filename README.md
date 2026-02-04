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

**Note:** Backtesting does not include Rule 3 (economic calendar) as historical event data is not available.

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
| `config.yaml` | Your configuration (gitignored) |
| `config.yaml.example` | Configuration template |
| `requirements.txt` | Python dependencies |

## License

MIT
