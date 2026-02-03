#!/usr/bin/env python3
"""
SPX 0DTE Iron Condor Trade Filter
Determines if market conditions are favorable for trading.
"""

import argparse
import os
import yaml
import yfinance as yf
import requests
from datetime import datetime, date, timedelta
from termcolor import colored
from pathlib import Path

# Default config path
DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"

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


def get_market_data(include_history=False):
    """Fetch current VIX and S&P 500 data."""
    vix = yf.Ticker("^VIX")
    spx = yf.Ticker("^GSPC")

    vix_data = vix.history(period="5d")
    spx_data = spx.history(period="5d" if include_history else "1d")

    if vix_data.empty or spx_data.empty:
        raise ValueError("Unable to fetch market data. Market may be closed.")

    result = {
        'vix': vix_data['Close'].iloc[-1],
        'spx_current': spx_data['Close'].iloc[-1],
        'spx_open': spx_data['Open'].iloc[-1]
    }

    if include_history and len(spx_data) >= 2:
        # Previous day data for additional filters
        prev_day = spx_data.iloc[-2]
        result['prev_high'] = prev_day['High']
        result['prev_low'] = prev_day['Low']
        result['prev_close'] = prev_day['Close']
        result['prev_range_pct'] = ((prev_day['High'] - prev_day['Low']) / prev_day['Close']) * 100

        # Calculate 20-day moving average (approximate with available data)
        if len(spx_data) >= 5:
            result['ma_20_approx'] = spx_data['Close'].mean()  # Use available data

        # Get more history for proper MA calculation
        spx_extended = yf.Ticker("^GSPC").history(period="1mo")
        if len(spx_extended) >= 20:
            result['ma_20'] = spx_extended['Close'].tail(20).mean()
        else:
            result['ma_20'] = spx_extended['Close'].mean()

    # VIX term structure (VIX vs VIX3M)
    if include_history:
        try:
            vix3m = yf.Ticker("^VIX3M")
            vix3m_data = vix3m.history(period="1d")
            if not vix3m_data.empty:
                result['vix3m'] = vix3m_data['Close'].iloc[-1]
                result['vix_contango'] = result['vix3m'] > result['vix']
        except Exception:
            result['vix3m'] = None
            result['vix_contango'] = None

    return result


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


def check_economic_calendar():
    """
    Check ForexFactory calendar for high-impact USD events today.
    Uses free API from nfs.faireconomy.media (no API key required).
    """
    today = date.today().strftime('%Y-%m-%d')

    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        high_impact_events = []
        for event in data:
            country = event.get('country', '')
            impact = event.get('impact', '')
            event_date = event.get('date', '')[:10]

            if country == 'USD' and impact == 'High' and event_date == today:
                event_time = event.get('date', '')[11:16]
                high_impact_events.append({
                    'name': event.get('title', 'Unknown Event'),
                    'time': event_time or 'All Day',
                    'impact': impact
                })

        return {
            'has_high_impact': len(high_impact_events) > 0,
            'events': high_impact_events,
            'error': None
        }

    except requests.exceptions.RequestException as e:
        return {
            'has_high_impact': None,
            'events': [],
            'error': f"Calendar API failed: {str(e)}"
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
    calendar = check_economic_calendar()

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
        print(colored(f"  [FAIL] Rule 3: High-impact USD event(s) today:", "red"))
        for event in calendar['events']:
            print(colored(f"         - {event['name']} @ {event['time']}", "red"))
    else:
        print(colored("  [PASS] Rule 3: No high-impact USD events today", "green"))

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
        """
    )

    parser.add_argument('-a', '--additional', action='store_true',
                        help='Enable additional filters (MA deviation, prev day range, VIX structure)')
    parser.add_argument('-c', '--config', type=str, default=None,
                        help='Path to config file (default: config.yaml)')

    args = parser.parse_args()

    config = load_config(args.config)
    evaluate_trade(config, use_additional_filters=args.additional)


if __name__ == "__main__":
    main()
