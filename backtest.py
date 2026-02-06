#!/usr/bin/env python3
"""
STOXX50 0DTE Iron Condor Backtest
Tests the trade_filter strategy over a historical time period for Euro Stoxx 50.
"""

import argparse
import os
import yaml
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from termcolor import colored
from trade_filter import calculate_strikes


def load_config_defaults():
    """Load defaults from config.yaml if available."""
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    defaults = {
        'wing_width': 50,
        'credit': 2.50,  # Realistic default
        'otm_percent': 1.0
    }

    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
            defaults['wing_width'] = config.get('strikes', {}).get('wing_width', 50)
            defaults['credit'] = config.get('portfolio', {}).get('credit', 2.50)
            defaults['otm_percent'] = config.get('strikes', {}).get('otm_percent', 1.0)
        except Exception:
            pass  # Use defaults if config can't be loaded

    return defaults


def get_historical_data(start_date, end_date):
    """Fetch historical VIX and Euro Stoxx 50 data.

    Note: VSTOXX (V2TX.DE) is unavailable via yfinance, so we use VIX as a proxy.
    VIX is used as a warning indicator only, not a blocking rule.
    """
    # Add buffer days to ensure we have data for the full range
    buffer_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=5)).strftime('%Y-%m-%d')
    buffer_end = (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=5)).strftime('%Y-%m-%d')

    vix = yf.Ticker("^VIX")
    stoxx = yf.Ticker("^STOXX50E")

    vix_data = vix.history(start=buffer_start, end=buffer_end)
    stoxx_data = stoxx.history(start=buffer_start, end=buffer_end)

    return vix_data, stoxx_data


def evaluate_day(vix_close, stoxx_open, stoxx_close):
    """
    Evaluate if we would trade on this day.
    Returns (should_trade, reason, intraday_change, vix_warning) tuple.

    Note: VIX is used as warning-only (VSTOXX unavailable via yfinance).
    Uses open-to-close change as proxy for trending days (since intraday data unavailable).
    """
    # Calculate open-to-close change as proxy for trending days
    intraday_change = ((stoxx_close - stoxx_open) / stoxx_open) * 100

    # VIX warning (non-blocking) - threshold 22
    vix_warning = vix_close > 22 if vix_close is not None else False

    # Rule 1: Intraday change check (blocking)
    if abs(intraday_change) > 1.0:
        return False, f"Trend too strong ({intraday_change:+.2f}%)", intraday_change, vix_warning

    # Rule 2: Economic calendar - skipped for backtest (data not available historically)

    return True, "Conditions met", intraday_change, vix_warning


def simulate_iron_condor(entry_price, stoxx_close, call_strike, put_strike, wing_width=50, credit=2.50):
    """
    Simulate Iron Condor P&L.

    Args:
        entry_price: STOXX price at entry
        stoxx_close: STOXX closing price (0DTE expiration)
        call_strike: Short call strike
        put_strike: Short put strike
        wing_width: Width of wings in points (default 50)
        credit: Estimated credit received per spread (default €2.50)

    Returns:
        P&L in euros (per 1-lot, assuming €10 multiplier)
    """
    multiplier = 10  # Euro Stoxx 50 options multiplier

    if stoxx_close <= put_strike:
        # Put side breached
        intrinsic = put_strike - stoxx_close
        loss = min(intrinsic, wing_width) - credit
        return -loss * multiplier
    elif stoxx_close >= call_strike:
        # Call side breached
        intrinsic = stoxx_close - call_strike
        loss = min(intrinsic, wing_width) - credit
        return -loss * multiplier
    else:
        # Price within range - max profit
        return credit * multiplier


def run_backtest(start_date, end_date, wing_width=50, credit=2.50, verbose=True):
    """Run backtest over the specified date range."""

    print("\n" + "=" * 70)
    print(colored("  STOXX50 0DTE IRON CONDOR BACKTEST", "cyan", attrs=["bold"]))
    print(colored(f"  Period: {start_date} to {end_date}", "cyan"))
    print("=" * 70 + "\n")

    # Fetch data
    print("Fetching historical data...")
    vix_data, stoxx_data = get_historical_data(start_date, end_date)

    # Filter to date range
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')

    # Results tracking
    results = []
    total_pnl = 0
    trades_taken = 0
    trades_skipped = 0
    wins = 0
    losses = 0

    print("Running backtest...\n")

    if verbose:
        print(colored("DATE        VIX     STOXX OPEN ENTRY    CHANGE   TRADE?   STRIKES        CLOSE     P&L", "white", attrs=["bold"]))
        print("-" * 95)

    # Iterate through trading days
    for date in stoxx_data.index:
        date_str = date.strftime('%Y-%m-%d')
        date_only = date.replace(tzinfo=None)

        if date_only < start_dt or date_only > end_dt:
            continue

        # Get day's data
        try:
            stoxx_row = stoxx_data.loc[date]
        except KeyError:
            continue

        # VIX data may not be available for all days (different market hours)
        try:
            vix_row = vix_data.loc[date]
            vix_close = vix_row['Close']
        except KeyError:
            vix_close = None

        stoxx_open = stoxx_row['Open']
        stoxx_high = stoxx_row['High']
        stoxx_low = stoxx_row['Low']
        stoxx_close = stoxx_row['Close']

        # Estimate price at 10:00 CET entry (roughly 1 hour after market open)
        # Using weighted average: 70% open + 30% towards midpoint
        stoxx_entry = stoxx_open + (((stoxx_high + stoxx_low) / 2) - stoxx_open) * 0.3

        # Evaluate rules (using open-to-close as proxy for trending days)
        should_trade, reason, intraday_change, vix_warning = evaluate_day(vix_close, stoxx_open, stoxx_close)

        if should_trade:
            trades_taken += 1
            call_strike, put_strike = calculate_strikes(stoxx_entry)
            pnl = simulate_iron_condor(stoxx_entry, stoxx_close, call_strike, put_strike, wing_width, credit)
            total_pnl += pnl

            if pnl > 0:
                wins += 1
                pnl_color = "green"
            else:
                losses += 1
                pnl_color = "red"

            results.append({
                'date': date_str,
                'vix': vix_close,
                'vix_warning': vix_warning,
                'stoxx_open': stoxx_open,
                'stoxx_entry': stoxx_entry,
                'stoxx_close': stoxx_close,
                'intraday_change': intraday_change,
                'traded': True,
                'call_strike': call_strike,
                'put_strike': put_strike,
                'pnl': pnl
            })

            vix_str = f"{vix_close:6.2f}" if vix_close is not None else "  N/A "
            warn_marker = colored("!", "yellow") if vix_warning else " "
            if verbose:
                print(f"{date_str}  {vix_str}{warn_marker} {stoxx_open:8.2f}  {stoxx_entry:8.2f}  {intraday_change:+5.2f}%   "
                      f"{colored('YES', 'green')}      {put_strike:.0f}/{call_strike:.0f}      {stoxx_close:8.2f}  "
                      f"{colored(f'€{pnl:+.0f}', pnl_color)}")
        else:
            trades_skipped += 1
            results.append({
                'date': date_str,
                'vix': vix_close,
                'vix_warning': vix_warning,
                'stoxx_open': stoxx_open,
                'stoxx_entry': stoxx_entry,
                'stoxx_close': stoxx_close,
                'intraday_change': intraday_change,
                'traded': False,
                'reason': reason,
                'pnl': 0
            })

            vix_str = f"{vix_close:6.2f}" if vix_close is not None else "  N/A "
            warn_marker = colored("!", "yellow") if vix_warning else " "
            if verbose:
                print(f"{date_str}  {vix_str}{warn_marker} {stoxx_open:8.2f}  {stoxx_entry:8.2f}  {intraday_change:+5.2f}%   "
                      f"{colored('NO', 'yellow')}       {reason}")

    # Summary
    print("\n" + "=" * 70)
    print(colored("  BACKTEST SUMMARY", "cyan", attrs=["bold"]))
    print("=" * 70 + "\n")

    total_days = trades_taken + trades_skipped
    win_rate = (wins / trades_taken * 100) if trades_taken > 0 else 0
    avg_pnl = total_pnl / trades_taken if trades_taken > 0 else 0

    print(f"  Period:              {start_date} to {end_date}")
    print(f"  Trading Days:        {total_days}")
    print(f"  Trades Taken:        {trades_taken} ({trades_taken/total_days*100:.1f}% of days)" if total_days > 0 else "  Trades Taken:        0")
    print(f"  Trades Skipped:      {trades_skipped}")
    print()
    print(f"  Wins:                {wins}")
    print(f"  Losses:              {losses}")
    print(f"  Win Rate:            {colored(f'{win_rate:.1f}%', 'green' if win_rate >= 50 else 'red')}")
    print()
    print(f"  Total P&L:           {colored(f'€{total_pnl:,.0f}', 'green' if total_pnl >= 0 else 'red')}")
    print(f"  Avg P&L per Trade:   {colored(f'€{avg_pnl:,.0f}', 'green' if avg_pnl >= 0 else 'red')}")
    print()

    # Risk metrics
    if trades_taken > 0:
        winning_trades = [r['pnl'] for r in results if r.get('traded') and r['pnl'] > 0]
        losing_trades = [r['pnl'] for r in results if r.get('traded') and r['pnl'] < 0]

        avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else 0
        max_win = max(winning_trades) if winning_trades else 0
        max_loss = min(losing_trades) if losing_trades else 0

        print(f"  Avg Win:             €{avg_win:,.0f}")
        print(f"  Avg Loss:            €{avg_loss:,.0f}")
        print(f"  Max Win:             €{max_win:,.0f}")
        print(f"  Max Loss:            €{max_loss:,.0f}")

        if avg_loss != 0:
            profit_factor = abs(sum(winning_trades) / sum(losing_trades)) if losing_trades else float('inf')
            print(f"  Profit Factor:       {profit_factor:.2f}")

    print()
    print(colored("  Note: VIX shown as warning only (! marker) - not a blocking rule.", "yellow"))
    print(colored("  Note: Economic calendar not applied - historical data unavailable.", "yellow"))
    print(colored("  Actual results may differ on high-impact EUR news days.", "yellow"))
    print()
    print("=" * 70 + "\n")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Backtest STOXX50 0DTE Iron Condor strategy (Euro Stoxx 50)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backtest.py --start 2024-01-01 --end 2024-12-31
  python backtest.py --start 2024-06-01 --end 2024-06-30 --credit 5.00  # Aggressive preset
  python backtest.py --start 2024-01-01 --end 2024-03-31 --quiet

Note: Defaults are loaded from config.yaml (portfolio.credit, strikes.wing_width)
        """
    )

    # Load defaults from config.yaml
    config_defaults = load_config_defaults()

    parser.add_argument('--start', '-s', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', '-e', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--wing-width', '-w', type=float, default=config_defaults['wing_width'],
                        help=f"Wing width in points (default: {config_defaults['wing_width']} from config)")
    parser.add_argument('--credit', '-c', type=float, default=config_defaults['credit'],
                        help=f"Credit per spread in EUR (default: {config_defaults['credit']:.2f} from config)")
    parser.add_argument('--quiet', '-q', action='store_true', help='Only show summary, not daily details')

    args = parser.parse_args()

    # Validate dates
    try:
        start_dt = datetime.strptime(args.start, '%Y-%m-%d')
        end_dt = datetime.strptime(args.end, '%Y-%m-%d')
        if start_dt > end_dt:
            print(colored("Error: Start date must be before end date", "red"))
            return
    except ValueError:
        print(colored("Error: Invalid date format. Use YYYY-MM-DD", "red"))
        return

    run_backtest(
        args.start,
        args.end,
        wing_width=args.wing_width,
        credit=args.credit,
        verbose=not args.quiet
    )


if __name__ == "__main__":
    main()
