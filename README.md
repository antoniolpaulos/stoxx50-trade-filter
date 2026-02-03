# SPX 0DTE Iron Condor Trade Filter

A Python tool that determines if market conditions are favorable for trading SPX 0DTE (zero days to expiration) Iron Condors.

## Features

- **Rule-based Go/No-Go decision** with color-coded terminal output
- **VIX check** - Avoids trading when volatility is too high
- **Intraday change check** - Avoids strong trending days
- **Economic calendar** - Automatically detects high-impact USD events (FOMC, CPI, NFP, etc.)
- **Additional filters** (optional):
  - 20-day moving average deviation
  - Previous day range
  - VIX term structure (contango/backwardation)
- **Telegram notifications** - Get GO/NO-GO alerts on your phone
- **Configurable thresholds** via YAML config file
- **Backtesting** - Test the strategy on historical data

## Installation

```bash
# Clone the repository
git clone https://github.com/antoniolpaulos/spx-trade-filter.git
cd spx-trade-filter

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
  vix_max: 22                    # Max VIX level
  intraday_change_max: 1.0       # Max intraday change (%)

strikes:
  otm_percent: 1.0               # How far OTM for short strikes (%)
  wing_width: 25                 # Wing width in points

additional_filters:
  ma_deviation_max: 3.0          # Max % deviation from 20 DMA
  prev_day_range_max: 2.0        # Max previous day range (%)
  check_vix_term_structure: true
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
  SPX 0DTE IRON CONDOR TRADE FILTER
  2026-02-03 16:30:00
============================================================

MARKET DATA:
  VIX:              16.24
  SPX Current:      6976.44
  SPX Open:         6916.64
  Intraday Change:  +0.86%

RULE EVALUATION:
  [PASS] Rule 1: VIX = 16.24 (<= 22)
  [PASS] Rule 2: Intraday change = +0.86% (|change| <= 1.0%)
  [PASS] Rule 3: No high-impact USD events today

VERDICT:

   ██████╗  ██████╗
  ██╔════╝ ██╔═══██╗
  ██║  ███╗██║   ██║
  ██║   ██║██║   ██║
  ╚██████╔╝╚██████╔╝
   ╚═════╝  ╚═════╝

  [GO] CONDITIONS FAVORABLE FOR IRON CONDOR

  RECOMMENDED STRIKES (1.0% OTM):
    Short Call: 7045
    Short Put:  6905

  Suggested structure:
    Buy Put   @ 6880
    Sell Put  @ 6905
    Sell Call @ 7045
    Buy Call  @ 7070
```

## Scheduled Runs (Cron)

To run automatically at **16:30 Amsterdam time** (10:30 ET, 1 hour after US market open) every weekday:

```bash
# Edit crontab
crontab -e

# Add this line (adjust paths as needed):
# SPX 0DTE Iron Condor filter - runs 16:30 Amsterdam (10:30 ET) Mon-Fri
30 16 * * 1-5 /path/to/spx-trade-filter/venv/bin/python /path/to/spx-trade-filter/trade_filter.py -a >> /path/to/spx-trade-filter/trade_filter.log 2>&1
```

**Example with absolute paths:**

```bash
30 16 * * 1-5 /home/projects/spx-trade-filter/venv/bin/python /home/projects/spx-trade-filter/trade_filter.py -a >> /home/projects/spx-trade-filter/trade_filter.log 2>&1
```

### Time Zone Notes

| Amsterdam | US Eastern | Event |
|-----------|------------|-------|
| 15:30 | 09:30 | US market opens |
| 16:30 | 10:30 | **Cron runs here** |
| 22:00 | 16:00 | US market closes |

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
python backtest.py -s 2024-06-01 -e 2024-12-31 --credit 3.00 --wing-width 30

# Summary only (no daily details)
python backtest.py -s 2024-01-01 -e 2024-12-31 --quiet
```

**Note:** Backtesting does not include Rule 3 (economic calendar) as historical event data is not available.

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
