#!/usr/bin/env python3
"""
SPX 0DTE Iron Condor Trade Filter
Determines if market conditions are favorable for trading.
"""

import yfinance as yf
import requests
from datetime import datetime, date
from termcolor import colored


def get_market_data():
    """Fetch current VIX and S&P 500 data."""
    vix = yf.Ticker("^VIX")
    spx = yf.Ticker("^GSPC")

    vix_data = vix.history(period="1d")
    spx_data = spx.history(period="1d")

    if vix_data.empty or spx_data.empty:
        raise ValueError("Unable to fetch market data. Market may be closed.")

    vix_current = vix_data['Close'].iloc[-1]
    spx_current = spx_data['Close'].iloc[-1]
    spx_open = spx_data['Open'].iloc[-1]

    return {
        'vix': vix_current,
        'spx_current': spx_current,
        'spx_open': spx_open
    }


def calculate_intraday_change(current, open_price):
    """Calculate percentage change from open."""
    return ((current - open_price) / open_price) * 100


def calculate_strikes(spx_price, otm_percent=1.0):
    """Calculate 1% OTM call and put strikes (rounded to 5-point increments)."""
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
    Returns dict with 'has_high_impact', 'events' list, and 'error' if any.
    """
    today = date.today().strftime('%Y-%m-%d')

    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Filter for USD high-impact events today
        high_impact_events = []
        for event in data:
            country = event.get('country', '')
            impact = event.get('impact', '')
            event_date = event.get('date', '')[:10]  # Extract YYYY-MM-DD

            # We care about USD high-impact events on today's date
            if country == 'USD' and impact == 'High' and event_date == today:
                event_time = event.get('date', '')[11:16]  # Extract HH:MM
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


def evaluate_trade():
    """Main function to evaluate trade conditions."""
    print("\n" + "=" * 60)
    print(colored("  SPX 0DTE IRON CONDOR TRADE FILTER", "cyan", attrs=["bold"]))
    print(colored(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "cyan"))
    print("=" * 60 + "\n")

    try:
        data = get_market_data()
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
    print()

    # Evaluate rules
    status = "GO"
    reasons = []

    # RULE 1: VIX check
    print(colored("RULE EVALUATION:", "white", attrs=["bold", "underline"]))
    if data['vix'] > 22:
        status = "NO GO"
        reasons.append("Volatility too high (VIX > 22)")
        print(colored(f"  [FAIL] Rule 1: VIX = {data['vix']:.2f} (> 22)", "red"))
    else:
        print(colored(f"  [PASS] Rule 1: VIX = {data['vix']:.2f} (<= 22)", "green"))

    # RULE 2: Intraday change check
    if abs(intraday_change) > 1.0:
        status = "NO GO"
        direction = "up" if intraday_change > 0 else "down"
        reasons.append(f"Trend too strong ({intraday_change:+.2f}% {direction})")
        print(colored(f"  [FAIL] Rule 2: Intraday change = {intraday_change:+.2f}% (|change| > 1%)", "red"))
    else:
        print(colored(f"  [PASS] Rule 2: Intraday change = {intraday_change:+.2f}% (|change| <= 1%)", "green"))

    # RULE 3: Economic calendar check
    if calendar['error']:
        print(colored(f"  [WARN] Rule 3: {calendar['error']}", "yellow"))
    elif calendar['has_high_impact']:
        status = "NO GO"
        event_names = ', '.join([e['name'] for e in calendar['events']])
        reasons.append(f"High-impact economic event(s): {event_names}")
        print(colored(f"  [FAIL] Rule 3: High-impact USD event(s) today:", "red"))
        for event in calendar['events']:
            print(colored(f"         - {event['name']} @ {event['time']}", "red"))
    else:
        print(colored("  [PASS] Rule 3: No high-impact USD events today", "green"))
    print()

    # Final verdict
    print(colored("VERDICT:", "white", attrs=["bold", "underline"]))
    print()

    if status == "GO":
        call_strike, put_strike = calculate_strikes(data['spx_current'])

        print(colored("   ██████╗  ██████╗ ", "green", attrs=["bold"]))
        print(colored("  ██╔════╝ ██╔═══██╗", "green", attrs=["bold"]))
        print(colored("  ██║  ███╗██║   ██║", "green", attrs=["bold"]))
        print(colored("  ██║   ██║██║   ██║", "green", attrs=["bold"]))
        print(colored("  ╚██████╔╝╚██████╔╝", "green", attrs=["bold"]))
        print(colored("   ╚═════╝  ╚═════╝ ", "green", attrs=["bold"]))
        print()
        print(colored("  [GO] CONDITIONS FAVORABLE FOR IRON CONDOR", "green", attrs=["bold"]))
        print()
        print(colored("  RECOMMENDED STRIKES (1% OTM):", "white", attrs=["bold"]))
        print(colored(f"    Short Call: {call_strike:.0f}", "cyan"))
        print(colored(f"    Short Put:  {put_strike:.0f}", "cyan"))
        print()
        print(colored("  Suggested structure:", "white"))
        print(f"    Buy Put   @ {put_strike - 25:.0f}")
        print(f"    Sell Put  @ {put_strike:.0f}")
        print(f"    Sell Call @ {call_strike:.0f}")
        print(f"    Buy Call  @ {call_strike + 25:.0f}")
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

    print()
    print("=" * 60)
    print()


if __name__ == "__main__":
    evaluate_trade()
