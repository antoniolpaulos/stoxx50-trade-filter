#!/usr/bin/env python3
"""
SPX 0DTE Iron Condor Trade Filter
Determines if market conditions are favorable for trading.
"""

import argparse
import sys
import yaml
import yfinance as yf
import requests
from datetime import datetime, date, timedelta
from termcolor import colored
from pathlib import Path
import logging

# Import custom exceptions
from exceptions import (
    TradeFilterError, ConfigurationError, MarketDataError,
    CalendarAPIError, TelegramError, ValidationError, NetworkError
)

# Setup logging
def setup_logging(log_level='INFO', log_file=None):
    """Setup logging configuration."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

# Default config path
DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"
EXAMPLE_CONFIG_PATH = Path(__file__).parent / "config.yaml.example"

# Default configuration (used if no config file)
DEFAULT_CONFIG = {
    'rules': {
        'vix_max': 22,
        'intraday_change_max': 1.0
    },
    'strikes': {
        'otm_percent': 1.0,
        'wing_width': 25
    },
    'additional_filters': {
        'ma_deviation_max': 3.0,
        'prev_day_range_max': 2.0,
        'check_vix_term_structure': True
    },
    'telegram': {
        'enabled': False,
        'bot_token': '',
        'chat_id': ''
    }
}


def validate_config(config):
    """Validate configuration values."""
    # Validate rules
    rules = config.get('rules', {})
    if 'vix_max' not in rules:
        raise ConfigurationError("Missing 'vix_max' in rules configuration")
    if rules['vix_max'] <= 0:
        raise ConfigurationError("VIX max must be positive")
    if 'intraday_change_max' not in rules:
        raise ConfigurationError("Missing 'intraday_change_max' in rules configuration")
    if not (0 <= rules['intraday_change_max'] <= 100):
        raise ConfigurationError("Intraday change max must be between 0 and 100")
    
    # Validate strikes
    strikes = config.get('strikes', {})
    if 'otm_percent' not in strikes:
        raise ConfigurationError("Missing 'otm_percent' in strikes configuration")
    if not (0.1 <= strikes['otm_percent'] <= 10):
        raise ConfigurationError("OTM percent must be between 0.1 and 10")
    if 'wing_width' not in strikes:
        raise ConfigurationError("Missing 'wing_width' in strikes configuration")
    if strikes['wing_width'] <= 0:
        raise ConfigurationError("Wing width must be positive")
    
    # Validate Telegram if enabled
    telegram = config.get('telegram', {})
    if telegram.get('enabled'):
        bot_token = telegram.get('bot_token', '')
        chat_id = telegram.get('chat_id', '')
        if not bot_token or bot_token == 'YOUR_BOT_TOKEN':
            raise ConfigurationError("Telegram bot_token required when enabled")
        if not chat_id or chat_id == 'YOUR_CHAT_ID':
            raise ConfigurationError("Telegram chat_id required when enabled")


def load_config(config_path=None):
    """Load configuration from YAML file."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    try:
        if path.exists():
            with open(path, 'r') as f:
                user_config = yaml.safe_load(f)
                # Merge with defaults
                config = DEFAULT_CONFIG.copy()
                for key, value in user_config.items():
                    if isinstance(value, dict) and key in config:
                        config[key].update(value)
                    else:
                        config[key] = value
                validate_config(config)
                return config
        else:
            logging.info(f"Config file {path} not found, using defaults")
            validate_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML syntax in config file: {e}")
    except Exception as e:
        raise ConfigurationError(f"Error loading config file: {e}")


def config_exists():
    """Check if config.yaml exists."""
    return DEFAULT_CONFIG_PATH.exists()


def telegram_needs_setup(config):
    """Check if Telegram is enabled but not properly configured."""
    tg = config.get('telegram', {})
    if not tg.get('enabled'):
        return False
    bot_token = tg.get('bot_token', '')
    chat_id = tg.get('chat_id', '')
    return (not bot_token or not chat_id or
            bot_token == 'YOUR_BOT_TOKEN' or chat_id == 'YOUR_CHAT_ID')


def setup_config():
    """Interactive setup wizard for config.yaml."""
    print("\n" + "=" * 60)
    print(colored("  TRADE FILTER SETUP", "cyan", attrs=["bold"]))
    print("=" * 60 + "\n")

    # Check if config exists
    if not config_exists():
        if EXAMPLE_CONFIG_PATH.exists():
            print("No config.yaml found. Creating from template...")
            with open(EXAMPLE_CONFIG_PATH, 'r') as f:
                config_content = f.read()
            with open(DEFAULT_CONFIG_PATH, 'w') as f:
                f.write(config_content)
            print(colored("Created config.yaml from template.\n", "green"))
        else:
            print("Creating default config.yaml...")
            with open(DEFAULT_CONFIG_PATH, 'w') as f:
                yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
            print(colored("Created config.yaml with defaults.\n", "green"))

    # Load current config
    config = load_config()

    # Telegram setup
    print(colored("TELEGRAM SETUP", "white", attrs=["bold", "underline"]))
    print()
    print("To receive notifications, you need:")
    print("  1. A Telegram bot token (from @BotFather)")
    print("  2. Your chat ID (send a message to your bot, then we'll fetch it)")
    print()

    setup_telegram = input("Set up Telegram notifications? [y/N]: ").strip().lower()

    if setup_telegram == 'y':
        print()
        bot_token = input("Enter your bot token from @BotFather: ").strip()

        if not bot_token:
            print(colored("No token provided. Skipping Telegram setup.", "yellow"))
        else:
            print()
            print("Now send any message to your bot in Telegram...")
            input("Press Enter when done...")

            # Fetch chat ID from bot updates
            try:
                url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
                response = requests.get(url, timeout=10)
                data = response.json()

                if data.get('ok') and data.get('result'):
                    chat_id = str(data['result'][-1]['message']['chat']['id'])
                    user_name = data['result'][-1]['message']['from'].get('first_name', 'User')

                    print(colored(f"\nFound chat ID for {user_name}: {chat_id}", "green"))

                    # Update config
                    config['telegram']['enabled'] = True
                    config['telegram']['bot_token'] = bot_token
                    config['telegram']['chat_id'] = chat_id

                    # Write updated config
                    with open(DEFAULT_CONFIG_PATH, 'r') as f:
                        config_content = f.read()

                    # Update the telegram section
                    import re
                    config_content = re.sub(
                        r'telegram:\s*\n\s*enabled:.*\n\s*bot_token:.*\n\s*chat_id:.*',
                        f'telegram:\n  enabled: true\n  bot_token: "{bot_token}"\n  chat_id: "{chat_id}"',
                        config_content
                    )

                    with open(DEFAULT_CONFIG_PATH, 'w') as f:
                        f.write(config_content)

                    # Send test message
                    print("\nSending test message...")
                    test_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    payload = {
                        'chat_id': chat_id,
                        'text': '✅ Trade Filter notifications enabled!',
                        'parse_mode': 'HTML'
                    }
                    requests.post(test_url, json=payload, timeout=10)
                    print(colored("Test message sent! Check your Telegram.", "green"))

                else:
                    print(colored("\nNo messages found. Make sure you messaged your bot.", "red"))

            except Exception as e:
                print(colored(f"\nError fetching chat ID: {e}", "red"))

    print()
    print(colored("Setup complete!", "green", attrs=["bold"]))
    print(f"Config saved to: {DEFAULT_CONFIG_PATH}")
    print()


def check_and_prompt_setup(config):
    """Check if setup is needed and prompt user."""
    if not config_exists():
        print(colored("\nNo config.yaml found.", "yellow"))
        response = input("Run setup wizard? [Y/n]: ").strip().lower()
        if response != 'n':
            setup_config()
            return load_config()
        else:
            print("Using default configuration.\n")
    elif telegram_needs_setup(config):
        print(colored("\nTelegram is enabled but not configured.", "yellow"))
        response = input("Run setup wizard? [Y/n]: ").strip().lower()
        if response != 'n':
            setup_config()
            return load_config()

    return config


def validate_market_data(vix_data, spx_data):
    """Validate fetched market data quality."""
    if vix_data.empty:
        raise MarketDataError("VIX data is empty - market may be closed")
    if spx_data.empty:
        raise MarketDataError("SPX data is empty - market may be closed")
    
    if 'Close' not in vix_data.columns:
        raise MarketDataError("VIX data missing required 'Close' column")
    if 'Close' not in spx_data.columns or 'Open' not in spx_data.columns:
        raise MarketDataError("SPX data missing required columns")
    
    # Check for invalid values
    if (vix_data['Close'] <= 0).any():
        raise MarketDataError("VIX values must be positive")
    if (spx_data['Close'] <= 0).any() or (spx_data['Open'] <= 0).any():
        raise MarketDataError("SPX prices must be positive")


def get_market_data(include_history=False):
    """Fetch current VIX and S&P 500 data."""
    try:
        logging.info("Fetching market data...")
        
        # Fetch VIX and SPX data with error handling
        vix = yf.Ticker("^VIX")
        spx = yf.Ticker("^GSPC")

        vix_data = vix.history(period="5d")
        spx_data = spx.history(period="5d" if include_history else "1d")
        
        # Validate data quality
        validate_market_data(vix_data, spx_data)

        result = {
            'vix': vix_data['Close'].iloc[-1],
            'spx_current': spx_data['Close'].iloc[-1],
            'spx_open': spx_data['Open'].iloc[-1]
        }
        
        logging.info(f"VIX: {result['vix']:.2f}, SPX: {result['spx_current']:.2f}")

        if include_history and len(spx_data) >= 2:
            # Previous day data for additional filters
            prev_day = spx_data.iloc[-2]
            result['prev_high'] = prev_day['High']
            result['prev_low'] = prev_day['Low']
            result['prev_close'] = prev_day['Close']
            result['prev_range_pct'] = ((prev_day['High'] - prev_day['Low']) / prev_day['Close']) * 100

            # Calculate 20-day moving average
            try:
                spx_extended = yf.Ticker("^GSPC").history(period="1mo")
                if not spx_extended.empty:
                    if len(spx_extended) >= 20:
                        result['ma_20'] = spx_extended['Close'].tail(20).mean()
                    else:
                        result['ma_20'] = spx_extended['Close'].mean()
                        logging.warning("Using available data for MA calculation (less than 20 days)")
                else:
                    raise MarketDataError("Extended SPX data is empty")
            except Exception as e:
                raise MarketDataError(f"Failed to fetch extended SPX data: {e}")

        # VIX term structure (VIX vs VIX3M)
        if include_history:
            try:
                vix3m = yf.Ticker("^VIX3M")
                vix3m_data = vix3m.history(period="1d")
                if not vix3m_data.empty:
                    result['vix3m'] = vix3m_data['Close'].iloc[-1]
                    result['vix_contango'] = result['vix3m'] > result['vix']
                else:
                    logging.warning("VIX3M data is empty")
                    result['vix3m'] = None
                    result['vix_contango'] = None
            except Exception as e:
                logging.warning(f"Could not fetch VIX3M data: {e}")
                result['vix3m'] = None
                result['vix_contango'] = None

        return result
        
    except Exception as e:
        if isinstance(e, MarketDataError):
            raise
        else:
            raise MarketDataError(f"Failed to fetch market data: {e}")


def calculate_intraday_change(current, open_price):
    """Calculate percentage change from open."""
    return ((current - open_price) / open_price) * 100


def calculate_strikes(spx_price, otm_percent=1.0, wing_width=25):
    """Calculate OTM call and put strikes (rounded to 5-point increments)."""
    call_strike = spx_price * (1 + otm_percent / 100)
    put_strike = spx_price * (1 - otm_percent / 100)

    # Round to nearest 5 (SPX options trade in 5-point increments)
    call_strike = round(call_strike / 5) * 5
    put_strike = round(put_strike / 5) * 5

    return call_strike, put_strike


def check_economic_calendar(config=None):
    """
    Check economic calendars for high-impact USD events today.
    Uses ForexFactory API as primary, with backup from Trading Economics.
    Also checks against a configurable watchlist for important events.
    """
    today = date.today().strftime('%Y-%m-%d')

    # Get watchlist from config
    watchlist = []
    use_backup = True
    if config and 'calendar' in config:
        watchlist = [w.upper() for w in config['calendar'].get('always_watch', [])]
        use_backup = config['calendar'].get('use_backup_api', True)

    def is_watched_event(title):
        """Check if event title matches any watchlist item."""
        title_upper = title.upper()
        return any(watch in title_upper for watch in watchlist)

    def parse_forexfactory(data):
        """Parse ForexFactory API response."""
        high_impact_events = []
        all_usd_high = []

        for event in data:
            country = event.get('country', '')
            impact = event.get('impact', '')
            event_date = event.get('date', '')[:10]
            title = event.get('title', 'Unknown Event')

            if country == 'USD' and impact == 'High':
                all_usd_high.append(f"{event_date}: {title}")

            # Match if: USD + today + (High impact OR in watchlist)
            if country == 'USD' and event_date == today:
                if impact == 'High' or is_watched_event(title):
                    event_time = event.get('date', '')[11:16]
                    high_impact_events.append({
                        'name': title,
                        'time': event_time or 'All Day',
                        'impact': impact if impact == 'High' else 'Watchlist'
                    })

        return high_impact_events, all_usd_high

    def fetch_forexfactory():
        """Fetch from ForexFactory API."""
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise CalendarAPIError(f"ForexFactory API failed: {e}")
        except Exception as e:
            raise CalendarAPIError(f"Failed to parse ForexFactory data: {e}")

    def fetch_trading_economics():
        """Fetch from Trading Economics calendar page (scrape JSON from HTML)."""
        try:
            url = f"https://tradingeconomics.com/calendar"
            headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            # Try to find embedded JSON data
            import re
            json_match = re.search(r'var defined = (\[.*?\]);', response.text, re.DOTALL)
            if json_match:
                import json
                data = json.loads(json_match.group(1))
                events = []
                for item in data:
                    if item.get('Country') == 'United States':
                        events.append({
                            'country': 'USD',
                            'title': item.get('Event', ''),
                            'date': item.get('Date', ''),
                            'impact': 'High' if item.get('Importance', 0) >= 3 else 'Medium'
                        })
                return events
            return []
        except requests.RequestException as e:
            raise CalendarAPIError(f"Trading Economics API failed: {e}")
        except Exception as e:
            raise CalendarAPIError(f"Failed to parse Trading Economics data: {e}")

    # Try primary API (ForexFactory)
    try:
        data = fetch_forexfactory()
        high_impact_events, all_usd_high = parse_forexfactory(data)

        return {
            'has_high_impact': len(high_impact_events) > 0,
            'events': high_impact_events,
            'all_usd_high_this_week': all_usd_high,
            'source': 'ForexFactory',
            'error': None
        }

    except Exception as primary_error:
        # Try backup API if enabled
        if use_backup:
            try:
                data = fetch_trading_economics()
                high_impact_events, all_usd_high = parse_forexfactory(data)

                return {
                    'has_high_impact': len(high_impact_events) > 0,
                    'events': high_impact_events,
                    'all_usd_high_this_week': all_usd_high,
                    'source': 'TradingEconomics (backup)',
                    'error': None
                }
            except Exception as backup_error:
                logging.error(f"Both calendar APIs failed: Primary={primary_error}, Backup={backup_error}")
                return {
                    'has_high_impact': None,
                    'events': [],
                    'all_usd_high_this_week': [],
                    'source': None,
                    'error': f"Both APIs failed: {str(primary_error)}"
                }
        
        logging.error(f"Primary calendar API failed: {primary_error}")
        return {
            'has_high_impact': None,
            'events': [],
            'all_usd_high_this_week': [],
            'source': None,
            'error': f"Calendar API failed: {str(primary_error)}"
        }


def send_telegram_message(config, message):
    """Send a message via Telegram bot."""
    if not config['telegram'].get('enabled'):
        return

    bot_token = config['telegram'].get('bot_token', '')
    chat_id = config['telegram'].get('chat_id', '')

    if not bot_token or not chat_id or bot_token == 'YOUR_BOT_TOKEN':
        logging.warning("Telegram not properly configured - skipping notification")
        return

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        logging.info(f"Sending Telegram message to chat_id: {chat_id}")
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        logging.info("Telegram message sent successfully")
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Telegram API request failed: {e}"
        logging.error(error_msg)
        raise TelegramError(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error sending Telegram message: {e}"
        logging.error(error_msg)
        raise TelegramError(error_msg)


def evaluate_trade(config, use_additional_filters=False):
    """Main function to evaluate trade conditions."""
    print("\n" + "=" * 60)
    print(colored("  SPX 0DTE IRON CONDOR TRADE FILTER", "cyan", attrs=["bold"]))
    print(colored(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "cyan"))
    if use_additional_filters:
        print(colored("  [Additional filters enabled]", "yellow"))
    print("=" * 60 + "\n")

    # Load thresholds from config
    vix_max = config['rules']['vix_max']
    intraday_max = config['rules']['intraday_change_max']
    otm_percent = config['strikes']['otm_percent']
    wing_width = config['strikes']['wing_width']

    try:
        data = get_market_data(include_history=use_additional_filters)
    except Exception as e:
        print(colored(f"[ERROR] {e}", "red", attrs=["bold"]))
        return

    intraday_change = calculate_intraday_change(data['spx_current'], data['spx_open'])
    calendar = check_economic_calendar(config)

    # Display market data
    print(colored("MARKET DATA:", "white", attrs=["bold", "underline"]))
    print(f"  VIX:              {data['vix']:.2f}")
    print(f"  SPX Current:      {data['spx_current']:.2f}")
    print(f"  SPX Open:         {data['spx_open']:.2f}")
    print(f"  Intraday Change:  {intraday_change:+.2f}%")

    if use_additional_filters:
        if 'ma_20' in data:
            ma_deviation = ((data['spx_current'] - data['ma_20']) / data['ma_20']) * 100
            print(f"  20 DMA:           {data['ma_20']:.2f} ({ma_deviation:+.2f}% from current)")
        if 'prev_range_pct' in data:
            print(f"  Prev Day Range:   {data['prev_range_pct']:.2f}%")
        if 'vix3m' in data and data['vix3m']:
            structure = "Contango" if data['vix_contango'] else "Backwardation"
            print(f"  VIX3M:            {data['vix3m']:.2f} ({structure})")
    print()

    # Evaluate rules
    status = "GO"
    reasons = []
    warnings = []

    # RULE 1: VIX check
    print(colored("RULE EVALUATION:", "white", attrs=["bold", "underline"]))
    if data['vix'] > vix_max:
        status = "NO GO"
        reasons.append(f"Volatility too high (VIX > {vix_max})")
        print(colored(f"  [FAIL] Rule 1: VIX = {data['vix']:.2f} (> {vix_max})", "red"))
    else:
        print(colored(f"  [PASS] Rule 1: VIX = {data['vix']:.2f} (<= {vix_max})", "green"))

    # RULE 2: Intraday change check
    if abs(intraday_change) > intraday_max:
        status = "NO GO"
        direction = "up" if intraday_change > 0 else "down"
        reasons.append(f"Trend too strong ({intraday_change:+.2f}% {direction})")
        print(colored(f"  [FAIL] Rule 2: Intraday change = {intraday_change:+.2f}% (|change| > {intraday_max}%)", "red"))
    else:
        print(colored(f"  [PASS] Rule 2: Intraday change = {intraday_change:+.2f}% (|change| <= {intraday_max}%)", "green"))

    # RULE 3: Economic calendar check
    if calendar['error']:
        print(colored(f"  [WARN] Rule 3: {calendar['error']}", "yellow"))
        warnings.append(calendar['error'])
    elif calendar['has_high_impact']:
        status = "NO GO"
        event_names = ', '.join([e['name'] for e in calendar['events']])
        reasons.append(f"High-impact economic event(s): {event_names}")
        source = f" [{calendar.get('source', 'Unknown')}]" if calendar.get('source') else ""
        print(colored(f"  [FAIL] Rule 3: High-impact USD event(s) today{source}:", "red"))
        for event in calendar['events']:
            impact_note = " (watchlist)" if event.get('impact') == 'Watchlist' else ""
            print(colored(f"         - {event['name']} @ {event['time']}{impact_note}", "red"))
    else:
        source = f" [{calendar.get('source', 'Unknown')}]" if calendar.get('source') else ""
        print(colored(f"  [PASS] Rule 3: No high-impact USD events today{source}", "green"))
        # Debug: show what USD high-impact events exist this week
        if calendar.get('all_usd_high_this_week'):
            print(colored(f"         (This week's USD high-impact: {calendar['all_usd_high_this_week']})", "cyan"))

    # ADDITIONAL FILTERS (if enabled)
    if use_additional_filters:
        print()
        print(colored("ADDITIONAL FILTERS:", "white", attrs=["bold", "underline"]))
        af_config = config['additional_filters']

        # Filter A: MA deviation
        if 'ma_20' in data:
            ma_deviation = ((data['spx_current'] - data['ma_20']) / data['ma_20']) * 100
            ma_max = af_config['ma_deviation_max']
            if abs(ma_deviation) > ma_max:
                status = "NO GO"
                reasons.append(f"SPX too far from 20 DMA ({ma_deviation:+.2f}%)")
                print(colored(f"  [FAIL] Filter A: MA deviation = {ma_deviation:+.2f}% (|dev| > {ma_max}%)", "red"))
            else:
                print(colored(f"  [PASS] Filter A: MA deviation = {ma_deviation:+.2f}% (|dev| <= {ma_max}%)", "green"))

        # Filter B: Previous day range
        if 'prev_range_pct' in data:
            range_max = af_config['prev_day_range_max']
            if data['prev_range_pct'] > range_max:
                status = "NO GO"
                reasons.append(f"Previous day range too high ({data['prev_range_pct']:.2f}%)")
                print(colored(f"  [FAIL] Filter B: Prev day range = {data['prev_range_pct']:.2f}% (> {range_max}%)", "red"))
            else:
                print(colored(f"  [PASS] Filter B: Prev day range = {data['prev_range_pct']:.2f}% (<= {range_max}%)", "green"))

        # Filter C: VIX term structure
        if af_config.get('check_vix_term_structure') and 'vix_contango' in data:
            if data['vix_contango'] is not None:
                if data['vix_contango']:
                    print(colored("  [PASS] Filter C: VIX in contango (normal)", "green"))
                else:
                    warnings.append("VIX in backwardation - elevated fear")
                    print(colored("  [WARN] Filter C: VIX in backwardation (elevated fear)", "yellow"))

    print()

    # Final verdict
    print(colored("VERDICT:", "white", attrs=["bold", "underline"]))
    print()

    # Build notification message
    notification_lines = [
        f"<b>SPX 0DTE Iron Condor - {datetime.now().strftime('%Y-%m-%d %H:%M')}</b>",
        "",
        f"VIX: {data['vix']:.2f}",
        f"SPX: {data['spx_current']:.2f}",
        f"Intraday: {intraday_change:+.2f}%",
        ""
    ]

    if status == "GO":
        call_strike, put_strike = calculate_strikes(data['spx_current'], otm_percent, wing_width)

        print(colored("   ██████╗  ██████╗ ", "green", attrs=["bold"]))
        print(colored("  ██╔════╝ ██╔═══██╗", "green", attrs=["bold"]))
        print(colored("  ██║  ███╗██║   ██║", "green", attrs=["bold"]))
        print(colored("  ██║   ██║██║   ██║", "green", attrs=["bold"]))
        print(colored("  ╚██████╔╝╚██████╔╝", "green", attrs=["bold"]))
        print(colored("   ╚═════╝  ╚═════╝ ", "green", attrs=["bold"]))
        print()
        print(colored("  [GO] CONDITIONS FAVORABLE FOR IRON CONDOR", "green", attrs=["bold"]))
        print()
        print(colored(f"  RECOMMENDED STRIKES ({otm_percent}% OTM):", "white", attrs=["bold"]))
        print(colored(f"    Short Call: {call_strike:.0f}", "cyan"))
        print(colored(f"    Short Put:  {put_strike:.0f}", "cyan"))
        print()
        print(colored("  Suggested structure:", "white"))
        print(f"    Buy Put   @ {put_strike - wing_width:.0f}")
        print(f"    Sell Put  @ {put_strike:.0f}")
        print(f"    Sell Call @ {call_strike:.0f}")
        print(f"    Buy Call  @ {call_strike + wing_width:.0f}")

        notification_lines.extend([
            "✅ <b>GO - CONDITIONS FAVORABLE</b>",
            "",
            f"Short Put: {put_strike:.0f}",
            f"Short Call: {call_strike:.0f}",
            f"Wings: {wing_width} pts"
        ])

        if warnings:
            print()
            print(colored("  WARNINGS:", "yellow", attrs=["bold"]))
            for warning in warnings:
                print(colored(f"    - {warning}", "yellow"))
    else:
        print(colored("  ███╗   ██╗ ██████╗     ██████╗  ██████╗ ", "red", attrs=["bold"]))
        print(colored("  ████╗  ██║██╔═══██╗   ██╔════╝ ██╔═══██╗", "red", attrs=["bold"]))
        print(colored("  ██╔██╗ ██║██║   ██║   ██║  ███╗██║   ██║", "red", attrs=["bold"]))
        print(colored("  ██║╚██╗██║██║   ██║   ██║   ██║██║   ██║", "red", attrs=["bold"]))
        print(colored("  ██║ ╚████║╚██████╔╝   ╚██████╔╝╚██████╔╝", "red", attrs=["bold"]))
        print(colored("  ╚═╝  ╚═══╝ ╚═════╝     ╚═════╝  ╚═════╝ ", "red", attrs=["bold"]))
        print()
        print(colored("  [NO GO] DO NOT TRADE TODAY", "red", attrs=["bold"]))
        print()
        print(colored("  REASONS:", "white", attrs=["bold"]))
        for reason in reasons:
            print(colored(f"    - {reason}", "red"))

        notification_lines.extend([
            "🛑 <b>NO GO - DO NOT TRADE</b>",
            "",
            "Reasons:"
        ])
        for reason in reasons:
            notification_lines.append(f"• {reason}")

    print()
    print("=" * 60)
    print()

    # Send Telegram notification
    send_telegram_message(config, "\n".join(notification_lines))


def main():
    parser = argparse.ArgumentParser(
        description='SPX 0DTE Iron Condor Trade Filter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python trade_filter.py                    # Basic rules only
  python trade_filter.py -a                 # Include additional filters
  python trade_filter.py -c myconfig.yaml   # Use custom config file
  python trade_filter.py --setup            # Run setup wizard
        """
    )

    parser.add_argument('-a', '--additional', action='store_true',
                        help='Enable additional filters (MA deviation, prev day range, VIX structure)')
    parser.add_argument('-c', '--config', type=str, default=None,
                        help='Path to config file (default: config.yaml)')
    parser.add_argument('--setup', action='store_true',
                        help='Run the setup wizard for config and Telegram')

    args = parser.parse_args()

    # Run setup wizard if requested
    if args.setup:
        setup_config()
        return

    config = load_config(args.config)

    # Check if setup is needed (only in interactive mode)
    if sys.stdin.isatty():
        config = check_and_prompt_setup(config)

    evaluate_trade(config, use_additional_filters=args.additional)


if __name__ == "__main__":
    main()
