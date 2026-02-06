#!/usr/bin/env python3
"""
Shadow Portfolio Tracking for STOXX50 Trade Filter.
Tracks two paper trading portfolios:
- always_trade: Enters every trading day regardless of filter
- filtered: Only trades when filter gives GO signal
"""

import json
from pathlib import Path
from datetime import date
from termcolor import colored
from exceptions import PortfolioError

# Default portfolio file path
DEFAULT_PORTFOLIO_PATH = Path(__file__).parent / "portfolio.json"

# Portfolio data structure version
PORTFOLIO_VERSION = 1


def create_empty_portfolio():
    """Create an empty portfolio data structure."""
    return {
        "version": PORTFOLIO_VERSION,
        "portfolios": {
            "always_trade": {
                "total_pnl": 0.0,
                "trade_count": 0,
                "win_count": 0,
                "open_trade": None,
                "history": []
            },
            "filtered": {
                "total_pnl": 0.0,
                "trade_count": 0,
                "win_count": 0,
                "open_trade": None,
                "history": []
            }
        }
    }


def load_portfolio(path=None):
    """Load portfolio data from JSON file. Create if missing."""
    path = Path(path) if path else DEFAULT_PORTFOLIO_PATH

    if not path.exists():
        data = create_empty_portfolio()
        save_portfolio(data, path)
        return data

    try:
        with open(path, 'r') as f:
            data = json.load(f)

        # Validate structure
        if "portfolios" not in data:
            raise PortfolioError("Invalid portfolio file: missing 'portfolios' key")

        return data
    except json.JSONDecodeError as e:
        raise PortfolioError(f"Corrupted portfolio file: {e}")


def save_portfolio(data, path=None):
    """Save portfolio data to JSON file."""
    path = Path(path) if path else DEFAULT_PORTFOLIO_PATH

    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        raise PortfolioError(f"Failed to save portfolio: {e}")


def calculate_pnl(stoxx_close, call_strike, put_strike, wing_width=50, credit=10.0):
    """
    Calculate Iron Condor P&L at expiration.

    Args:
        stoxx_close: STOXX closing price at expiration
        call_strike: Short call strike
        put_strike: Short put strike
        wing_width: Width of wings in points (default 50)
        credit: Credit received per spread (default 10.00)

    Returns:
        P&L in euros (per 1-lot, assuming EUR10 multiplier)
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


def settle_open_trade(portfolio_name, stoxx_close, data, wing_width=50, credit=10.0):
    """
    Settle an open trade by calculating P&L and moving to history.

    Args:
        portfolio_name: 'always_trade' or 'filtered'
        stoxx_close: STOXX closing price at expiration
        data: Portfolio data dict
        wing_width: Width of wings in points
        credit: Credit received per spread

    Returns:
        P&L of the settled trade, or None if no open trade
    """
    portfolio = data["portfolios"][portfolio_name]
    open_trade = portfolio["open_trade"]

    if open_trade is None:
        return None

    # Calculate P&L
    pnl = calculate_pnl(
        stoxx_close,
        open_trade["call_strike"],
        open_trade["put_strike"],
        open_trade.get("wing_width", wing_width),
        open_trade.get("credit", credit)
    )

    # Create history entry
    history_entry = {
        "date": open_trade["date"],
        "stoxx_entry": open_trade["stoxx_entry"],
        "stoxx_close": stoxx_close,
        "call_strike": open_trade["call_strike"],
        "put_strike": open_trade["put_strike"],
        "pnl": pnl,
        "outcome": "win" if pnl > 0 else "loss",
        "credit": open_trade.get("credit", credit),
        "credit_source": open_trade.get("credit_source", "config")
    }

    # Update portfolio
    portfolio["history"].append(history_entry)
    portfolio["total_pnl"] += pnl
    portfolio["trade_count"] += 1
    if pnl > 0:
        portfolio["win_count"] += 1
    portfolio["open_trade"] = None

    return pnl


def record_trade_entry(portfolio_name, trade_info, data):
    """
    Record a new trade entry.

    Args:
        portfolio_name: 'always_trade' or 'filtered'
        trade_info: Dict with date, stoxx_entry, call_strike, put_strike, wing_width, credit
        data: Portfolio data dict

    Returns:
        True if recorded, False if trade already exists for today
    """
    portfolio = data["portfolios"][portfolio_name]

    # Check for duplicate (same date)
    if portfolio["open_trade"] is not None:
        if portfolio["open_trade"]["date"] == trade_info["date"]:
            return False  # Already recorded for today

    portfolio["open_trade"] = trade_info
    return True


def has_open_trade(portfolio_name, data):
    """Check if portfolio has an open trade."""
    return data["portfolios"][portfolio_name]["open_trade"] is not None


def get_portfolio_summary(data):
    """
    Generate summary statistics for both portfolios.

    Returns:
        Dict with summary stats for each portfolio
    """
    summary = {}

    for name in ["always_trade", "filtered"]:
        portfolio = data["portfolios"][name]
        trade_count = portfolio["trade_count"]
        win_count = portfolio["win_count"]

        summary[name] = {
            "total_pnl": portfolio["total_pnl"],
            "trade_count": trade_count,
            "win_count": win_count,
            "loss_count": trade_count - win_count,
            "win_rate": (win_count / trade_count * 100) if trade_count > 0 else 0,
            "has_open_trade": portfolio["open_trade"] is not None,
            "open_trade": portfolio["open_trade"]
        }

    # Calculate filter edge
    summary["filter_edge"] = summary["filtered"]["total_pnl"] - summary["always_trade"]["total_pnl"]

    return summary


def format_portfolio_display(data):
    """Format portfolio data for console output."""
    summary = get_portfolio_summary(data)

    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append(colored("  SHADOW PORTFOLIO STATUS", "cyan", attrs=["bold"]))
    lines.append("=" * 60)
    lines.append("")

    for name, label in [("always_trade", "ALWAYS TRADE"), ("filtered", "FILTERED")]:
        s = summary[name]
        lines.append(colored(f"  {label} PORTFOLIO", "white", attrs=["bold", "underline"]))

        # Format P&L with color
        pnl = s["total_pnl"]
        pnl_str = f"{pnl:+.0f} EUR"
        pnl_color = "green" if pnl >= 0 else "red"
        lines.append(f"    Total P&L:      {colored(pnl_str, pnl_color)}")

        lines.append(f"    Trades:         {s['trade_count']}")

        if s["trade_count"] > 0:
            lines.append(f"    Win Rate:       {s['win_rate']:.1f}% ({s['win_count']}W / {s['loss_count']}L)")

        if s["has_open_trade"]:
            ot = s["open_trade"]
            lines.append(colored(f"    Open Trade:     {ot['date']} @ {ot['stoxx_entry']:.0f} (P:{ot['put_strike']} / C:{ot['call_strike']})", "yellow"))
        else:
            lines.append("    Open Trade:     None")

        lines.append("")

    # Filter edge
    edge = summary["filter_edge"]
    edge_str = f"{edge:+.0f} EUR"
    edge_color = "green" if edge >= 0 else "red"
    lines.append(colored("  COMPARISON", "white", attrs=["bold", "underline"]))
    lines.append(f"    Filter Edge:    {colored(edge_str, edge_color)}")

    if summary["always_trade"]["trade_count"] > 0 and summary["filtered"]["trade_count"] > 0:
        trades_saved = summary["always_trade"]["trade_count"] - summary["filtered"]["trade_count"]
        pct_saved = (trades_saved / summary["always_trade"]["trade_count"]) * 100
        lines.append(f"    Trades Avoided: {trades_saved} ({pct_saved:.0f}% fewer)")

    lines.append("")
    lines.append("=" * 60)
    lines.append("")

    return "\n".join(lines)


def format_portfolio_telegram(data):
    """Format portfolio data for Telegram notification."""
    summary = get_portfolio_summary(data)

    always = summary["always_trade"]
    filtered = summary["filtered"]
    edge = summary["filter_edge"]

    lines = [
        "",
        "<b>Portfolio Update</b>",
        f"Always: {always['total_pnl']:+.0f} ({always['trade_count']} trades, {always['win_rate']:.0f}% WR)",
        f"Filtered: {filtered['total_pnl']:+.0f} ({filtered['trade_count']} trades, {filtered['win_rate']:.0f}% WR)",
        f"Edge: {edge:+.0f}"
    ]

    return "\n".join(lines)


def reset_portfolio(data, portfolio_name=None):
    """
    Reset one or both portfolios.

    Args:
        data: Portfolio data dict
        portfolio_name: 'always_trade', 'filtered', or None for both
    """
    empty = create_empty_portfolio()

    if portfolio_name:
        data["portfolios"][portfolio_name] = empty["portfolios"][portfolio_name]
    else:
        data["portfolios"] = empty["portfolios"]


def get_previous_close(include_buffer=True):
    """
    Fetch previous trading day's closing price for STOXX50.
    Used to settle open trades.

    Returns:
        Previous day's close price, or None if unavailable
    """
    import yfinance as yf

    stoxx = yf.Ticker("^STOXX50E")
    data = stoxx.history(period="5d")

    if len(data) >= 2:
        # Return second-to-last close (previous trading day)
        return data['Close'].iloc[-2]
    elif len(data) == 1:
        # Only one day of data, return it
        return data['Close'].iloc[-1]

    return None
