#!/usr/bin/env python3
"""
STOXX50 0DTE Iron Condor Trade Filter
Determines if market conditions are favorable for trading Euro Stoxx 50 options.
"""

import argparse
import sys
import yaml
import yfinance as yf
import requests
from datetime import datetime, date, timedelta
from termcolor import colored
from pathlib import Path
from exceptions import MarketDataError

# Default config path
DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"
EXAMPLE_CONFIG_PATH = Path(__file__).parent / "config.yaml.example"

# Default configuration (used if no config file)
DEFAULT_CONFIG = {
    'rules': {
        'vix_warn': 22,  # VIX warning threshold (not a blocking rule)
        'intraday_change_max': 1.0
    },
    'strikes': {
        'otm_percent': 1.0,
        'wing_width': 50  # Euro Stoxx 50 points
    },
    'additional_filters': {
        'ma_deviation_max': 3.0,
        'prev_day_range_max': 2.0,
        'check_vstoxx_term_structure': False  # VSTOXX term structure data limited
    },
    'telegram': {
        'enabled': False,
        'bot_token': '',
        'chat_id': ''
    }
}


def load_config(config_path=None):
    """Load configuration from YAML file."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

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
            return config
    return DEFAULT_CONFIG


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
    print(colored("  STOXX50 TRADE FILTER SETUP", "cyan", attrs=["bold"]))
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


def get_market_data(include_history=False):
    """Fetch current VIX and Euro Stoxx 50 data."""
    vix = yf.Ticker("^VIX")
    stoxx = yf.Ticker("^STOXX50E")

    vix_data = vix.history(period="5d")
    stoxx_data = stoxx.history(period="5d" if include_history else "1d")

    if stoxx_data.empty:
        raise MarketDataError("Unable to fetch market data. Market may be closed.")

    result = {
        'stoxx_current': stoxx_data['Close'].iloc[-1],
        'stoxx_open': stoxx_data['Open'].iloc[-1]
    }

    # VIX is optional (warning only)
    if not vix_data.empty:
        result['vix'] = vix_data['Close'].iloc[-1]

    if include_history and len(stoxx_data) >= 2:
        # Previous day data for additional filters
        prev_day = stoxx_data.iloc[-2]
        result['prev_high'] = prev_day['High']
        result['prev_low'] = prev_day['Low']
        result['prev_close'] = prev_day['Close']
        result['prev_range_pct'] = ((prev_day['High'] - prev_day['Low']) / prev_day['Close']) * 100

        # Calculate 20-day moving average (approximate with available data)
        if len(stoxx_data) >= 5:
            result['ma_20_approx'] = stoxx_data['Close'].mean()  # Use available data

        # Get more history for proper MA calculation
        stoxx_extended = yf.Ticker("^STOXX50E").history(period="1mo")
        if len(stoxx_extended) >= 20:
            result['ma_20'] = stoxx_extended['Close'].tail(20).mean()
        else:
            result['ma_20'] = stoxx_extended['Close'].mean()

    # VSTOXX term structure data is limited on yfinance
    # Skipping term structure check for Euro Stoxx 50

    return result


def calculate_intraday_change(current, open_price):
    """Calculate percentage change from open."""
    return ((current - open_price) / open_price) * 100


def calculate_strikes(stoxx_price, otm_percent=1.0, wing_width=50):
    """Calculate OTM call and put strikes (rounded to nearest integer)."""
    call_strike = stoxx_price * (1 + otm_percent / 100)
    put_strike = stoxx_price * (1 - otm_percent / 100)

    # Round to nearest integer (Euro Stoxx 50 options use 1-point increments)
    call_strike = round(call_strike)
    put_strike = round(put_strike)

    return call_strike, put_strike


def check_economic_calendar(config=None):
    """
    Check economic calendars for high-impact EUR events today.
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
        """Parse ForexFactory API response for EUR events."""
        high_impact_events = []
        all_eur_high = []

        for event in data:
            country = event.get('country', '')
            impact = event.get('impact', '')
            event_date = event.get('date', '')[:10]
            title = event.get('title', 'Unknown Event')

            if country == 'EUR' and impact == 'High':
                all_eur_high.append(f"{event_date}: {title}")

            # Match if: EUR + today + (High impact OR in watchlist)
            if country == 'EUR' and event_date == today:
                if impact == 'High' or is_watched_event(title):
                    event_time = event.get('date', '')[11:16]
                    high_impact_events.append({
                        'name': title,
                        'time': event_time or 'All Day',
                        'impact': impact if impact == 'High' else 'Watchlist'
                    })

        return high_impact_events, all_eur_high

    def fetch_forexfactory():
        """Fetch from ForexFactory API."""
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    def fetch_trading_economics():
        """Fetch from Trading Economics calendar page (scrape JSON from HTML)."""
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
                # Match Eurozone countries
                eurozone_countries = ['Euro Area', 'Germany', 'France', 'Italy', 'Spain', 'Netherlands']
                if item.get('Country') in eurozone_countries:
                    events.append({
                        'country': 'EUR',
                        'title': item.get('Event', ''),
                        'date': item.get('Date', ''),
                        'impact': 'High' if item.get('Importance', 0) >= 3 else 'Medium'
                    })
            return events
        return []

    # Try primary API (ForexFactory)
    try:
        data = fetch_forexfactory()
        high_impact_events, all_eur_high = parse_forexfactory(data)

        return {
            'has_high_impact': len(high_impact_events) > 0,
            'events': high_impact_events,
            'all_eur_high_this_week': all_eur_high,
            'source': 'ForexFactory',
            'error': None
        }

    except requests.exceptions.RequestException as primary_error:
        # Try backup API if enabled
        if use_backup:
            try:
                data = fetch_trading_economics()
                high_impact_events, all_eur_high = parse_forexfactory(data)

                return {
                    'has_high_impact': len(high_impact_events) > 0,
                    'events': high_impact_events,
                    'all_eur_high_this_week': all_eur_high,
                    'source': 'TradingEconomics (backup)',
                    'error': None
                }
            except Exception as backup_error:
                return {
                    'has_high_impact': None,
                    'events': [],
                    'all_eur_high_this_week': [],
                    'source': None,
                    'error': f"Both APIs failed: {str(primary_error)}"
                }

        return {
            'has_high_impact': None,
            'events': [],
            'all_eur_high_this_week': [],
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
        return

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(colored(f"  [WARN] Telegram notification failed: {e}", "yellow"))


def evaluate_trade(config, use_additional_filters=False):
    """Main function to evaluate trade conditions."""
    print("\n" + "=" * 60)
    print(colored("  STOXX50 0DTE IRON CONDOR TRADE FILTER", "cyan", attrs=["bold"]))
    print(colored(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "cyan"))
    if use_additional_filters:
        print(colored("  [Additional filters enabled]", "yellow"))
    print("=" * 60 + "\n")

    # Load thresholds from config
    vix_warn = config['rules'].get('vix_warn', 22)
    intraday_max = config['rules']['intraday_change_max']
    otm_percent = config['strikes']['otm_percent']
    wing_width = config['strikes']['wing_width']

    try:
        data = get_market_data(include_history=use_additional_filters)
    except Exception as e:
        print(colored(f"[ERROR] {e}", "red", attrs=["bold"]))
        return

    intraday_change = calculate_intraday_change(data['stoxx_current'], data['stoxx_open'])
    calendar = check_economic_calendar(config)

    # Display market data
    print(colored("MARKET DATA:", "white", attrs=["bold", "underline"]))
    if 'vix' in data:
        print(f"  VIX:              {data['vix']:.2f}")
    print(f"  STOXX Current:    {data['stoxx_current']:.2f}")
    print(f"  STOXX Open:       {data['stoxx_open']:.2f}")
    print(f"  Intraday Change:  {intraday_change:+.2f}%")

    if use_additional_filters:
        if 'ma_20' in data:
            ma_deviation = ((data['stoxx_current'] - data['ma_20']) / data['ma_20']) * 100
            print(f"  20 DMA:           {data['ma_20']:.2f} ({ma_deviation:+.2f}% from current)")
        if 'prev_range_pct' in data:
            print(f"  Prev Day Range:   {data['prev_range_pct']:.2f}%")
    print()

    # Evaluate rules
    status = "GO"
    reasons = []
    warnings = []

    print(colored("RULE EVALUATION:", "white", attrs=["bold", "underline"]))

    # VIX check (warning only, not a blocking rule)
    if 'vix' in data:
        if data['vix'] > vix_warn:
            warnings.append(f"VIX elevated ({data['vix']:.2f} > {vix_warn})")
            print(colored(f"  [WARN] VIX = {data['vix']:.2f} (> {vix_warn}) - elevated volatility", "yellow"))
        else:
            print(colored(f"  [INFO] VIX = {data['vix']:.2f} (<= {vix_warn})", "green"))

    # RULE 1: Intraday change check
    if abs(intraday_change) > intraday_max:
        status = "NO GO"
        direction = "up" if intraday_change > 0 else "down"
        reasons.append(f"Trend too strong ({intraday_change:+.2f}% {direction})")
        print(colored(f"  [FAIL] Rule 1: Intraday change = {intraday_change:+.2f}% (|change| > {intraday_max}%)", "red"))
    else:
        print(colored(f"  [PASS] Rule 1: Intraday change = {intraday_change:+.2f}% (|change| <= {intraday_max}%)", "green"))

    # RULE 2: Economic calendar check
    if calendar['error']:
        print(colored(f"  [WARN] Rule 2: {calendar['error']}", "yellow"))
        warnings.append(calendar['error'])
    elif calendar['has_high_impact']:
        status = "NO GO"
        event_names = ', '.join([e['name'] for e in calendar['events']])
        reasons.append(f"High-impact economic event(s): {event_names}")
        source = f" [{calendar.get('source', 'Unknown')}]" if calendar.get('source') else ""
        print(colored(f"  [FAIL] Rule 2: High-impact EUR event(s) today{source}:", "red"))
        for event in calendar['events']:
            impact_note = " (watchlist)" if event.get('impact') == 'Watchlist' else ""
            print(colored(f"         - {event['name']} @ {event['time']}{impact_note}", "red"))
    else:
        source = f" [{calendar.get('source', 'Unknown')}]" if calendar.get('source') else ""
        print(colored(f"  [PASS] Rule 2: No high-impact EUR events today{source}", "green"))
        # Debug: show what EUR high-impact events exist this week
        if calendar.get('all_eur_high_this_week'):
            print(colored(f"         (This week's EUR high-impact: {calendar['all_eur_high_this_week']})", "cyan"))

    # ADDITIONAL FILTERS (if enabled)
    if use_additional_filters:
        print()
        print(colored("ADDITIONAL FILTERS:", "white", attrs=["bold", "underline"]))
        af_config = config['additional_filters']

        # Filter A: MA deviation
        if 'ma_20' in data:
            ma_deviation = ((data['stoxx_current'] - data['ma_20']) / data['ma_20']) * 100
            ma_max = af_config['ma_deviation_max']
            if abs(ma_deviation) > ma_max:
                status = "NO GO"
                reasons.append(f"STOXX too far from 20 DMA ({ma_deviation:+.2f}%)")
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

    print()

    # Final verdict
    print(colored("VERDICT:", "white", attrs=["bold", "underline"]))
    print()

    # Build notification message
    notification_lines = [
        f"<b>STOXX50 0DTE Iron Condor - {datetime.now().strftime('%Y-%m-%d %H:%M')}</b>",
        "",
        f"VIX: {data.get('vix', 'N/A'):.2f}" if 'vix' in data else "VIX: N/A",
        f"STOXX: {data['stoxx_current']:.2f}",
        f"Intraday: {intraday_change:+.2f}%",
        ""
    ]

    if status == "GO":
        call_strike, put_strike = calculate_strikes(data['stoxx_current'], otm_percent, wing_width)

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
        description='STOXX50 0DTE Iron Condor Trade Filter (Euro Stoxx 50)',
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
