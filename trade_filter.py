#!/usr/bin/env python3
"""
STOXX50 0DTE Iron Condor Trade Filter
Determines if market conditions are favorable for trading Euro Stoxx 50 options.
"""

import argparse
import sys
import time
import yaml
from datetime import datetime, date, timedelta
from termcolor import colored
from pathlib import Path
from exceptions import MarketDataError, PortfolioError, ConfigurationError
import portfolio as pf
from logger import TradeFilterLogger, get_logger
from monitor import start_monitoring_daemon, set_monitor
from config_validator import validate_config, check_config
from data_provider import get_market_data as fetch_market_data
from telegram_api import send_notification, get_chat_id_from_updates, TelegramClient
from calendar_provider import check_economic_calendar
from ibkr_provider import get_real_credit, IBKR_AVAILABLE

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
    },
    'portfolio': {
        'enabled': False,
        'file': 'portfolio.json',
        'credit': 10.0,
        'include_in_telegram': True
    },
    'logging': {
        'enabled': True,
        'file': 'logs/trade_filter.log',
        'level': 'INFO',
        'log_dir': 'logs'
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

            # Fetch chat ID from bot updates using telegram_api
            result = get_chat_id_from_updates(bot_token)

            if result:
                chat_id = result['chat_id']
                user_name = result['user_name']

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

                # Send test message using telegram_api
                print("\nSending test message...")
                client = TelegramClient(bot_token)
                if client.send_message(chat_id, '✅ Trade Filter notifications enabled!'):
                    print(colored("Test message sent! Check your Telegram.", "green"))
                else:
                    print(colored("Failed to send test message.", "yellow"))

            else:
                print(colored("\nNo messages found. Make sure you messaged your bot.", "red"))

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
    """Fetch current VIX and Euro Stoxx 50 data using data provider pool."""
    logger = get_logger()
    logger.debug("Fetching market data...")

    try:
        data = fetch_market_data(include_history=include_history)

        if data.stoxx_current is None:
            error_msg = "Unable to fetch market data. Market may be closed."
            logger.error(error_msg)
            raise MarketDataError(error_msg)

        result = {
            'stoxx_current': data.stoxx_current,
            'stoxx_open': data.stoxx_open,
            'source': data.source
        }

        if data.vix is not None:
            result['vix'] = data.vix

        if include_history:
            if data.prev_high is not None:
                result['prev_high'] = data.prev_high
            if data.prev_low is not None:
                result['prev_low'] = data.prev_low
            if data.prev_close is not None:
                result['prev_close'] = data.prev_close
            if data.prev_range_pct is not None:
                result['prev_range_pct'] = data.prev_range_pct
            if data.ma_20 is not None:
                result['ma_20'] = data.ma_20

        logger.log_market_data_fetch(True, result)
        return result

    except Exception as e:
        logger.log_market_data_fetch(False, error=str(e))
        raise


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


def send_telegram_message(config, message):
    """Send a message via Telegram bot."""
    if not send_notification(config, message):
        # Only warn if telegram is enabled but failed
        if config.get('telegram', {}).get('enabled'):
            print(colored("  [WARN] Telegram notification failed", "yellow"))


def evaluate_trade(config, use_additional_filters=False, track_portfolio=False):
    """Main function to evaluate trade conditions.

    Returns:
        dict with 'status', 'data', 'call_strike', 'put_strike' if track_portfolio=True
        None otherwise
    """
    logger = get_logger()

    print("\n" + "=" * 60)
    print(colored("  STOXX50 0DTE IRON CONDOR TRADE FILTER", "cyan", attrs=["bold"]))
    print(colored(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "cyan"))
    if use_additional_filters:
        print(colored("  [Additional filters enabled]", "yellow"))
    print("=" * 60 + "\n")

    logger.info(f"Starting trade evaluation (additional_filters={use_additional_filters})")

    # Load thresholds from config
    vix_warn = config['rules'].get('vix_warn', 22)
    intraday_max = config['rules']['intraday_change_max']
    otm_percent = config['strikes']['otm_percent']
    wing_width = config['strikes']['wing_width']

    try:
        data = get_market_data(include_history=use_additional_filters)
    except Exception as e:
        logger.error(f"Failed to fetch market data: {e}")
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

    # Log evaluation result
    logger.log_evaluation(status, {**data, 'intraday_change': intraday_change}, reasons)

    # Send Telegram notification
    send_telegram_message(config, "\n".join(notification_lines))

    # Return results for portfolio tracking
    if track_portfolio:
        call_strike, put_strike = calculate_strikes(data['stoxx_current'], otm_percent, wing_width)
        return {
            'status': status,
            'data': data,
            'call_strike': call_strike,
            'put_strike': put_strike,
            'intraday_change': intraday_change,
            'wing_width': wing_width
        }


def show_portfolio_status(config):
    """Display current portfolio status."""
    portfolio_config = config.get('portfolio', {})
    portfolio_file = portfolio_config.get('file', 'portfolio.json')
    portfolio_path = Path(__file__).parent / portfolio_file

    try:
        data = pf.load_portfolio(portfolio_path)
        print(pf.format_portfolio_display(data))
    except PortfolioError as e:
        print(colored(f"[ERROR] {e}", "red"))


def reset_portfolio_data(config):
    """Reset portfolio data with confirmation."""
    portfolio_config = config.get('portfolio', {})
    portfolio_file = portfolio_config.get('file', 'portfolio.json')
    portfolio_path = Path(__file__).parent / portfolio_file

    if not portfolio_path.exists():
        print(colored("No portfolio file exists.", "yellow"))
        return

    print(colored("\nWARNING: This will reset all portfolio data!", "red", attrs=["bold"]))
    confirm = input("Type 'RESET' to confirm: ").strip()

    if confirm == 'RESET':
        data = pf.create_empty_portfolio()
        pf.save_portfolio(data, portfolio_path)
        print(colored("Portfolio reset successfully.", "green"))
    else:
        print("Reset cancelled.")


def switch_preset(preset_name, config_path=None):
    """Switch between strategy presets by updating config.yaml."""
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    presets = {
        'conservative': {
            'otm_percent': 1.0,
            'credit': 2.50,
            'description': 'Conservative: 1% OTM, €2.50 credit (~€25/win, 1:19 R/R)'
        },
        'aggressive': {
            'otm_percent': 0.5,
            'credit': 5.00,
            'description': 'Aggressive: 0.5% OTM, €5.00 credit (~€50/win, 1:9 R/R)'
        }
    }

    if preset_name not in presets:
        print(colored(f"Unknown preset: {preset_name}", "red"))
        return False

    preset = presets[preset_name]

    # Load current config
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Update values
    if 'strikes' not in config:
        config['strikes'] = {}
    if 'portfolio' not in config:
        config['portfolio'] = {}

    config['strikes']['otm_percent'] = preset['otm_percent']
    config['portfolio']['credit'] = preset['credit']

    # Save updated config
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(colored(f"\n✓ Switched to {preset_name.upper()} preset", "green", attrs=["bold"]))
    print(f"  {preset['description']}")
    print(colored("\nUpdated config.yaml:", "cyan"))
    print(f"  strikes.otm_percent: {preset['otm_percent']}")
    print(f"  portfolio.credit: {preset['credit']}")
    print(colored("\nNote: Run --recalculate-portfolio to update historical P&L", "yellow"))
    return True


def recalculate_portfolio(config):
    """Recalculate all historical P&L with current credit setting."""
    portfolio_config = config.get('portfolio', {})
    portfolio_file = portfolio_config.get('file', 'portfolio.json')
    portfolio_path = Path(__file__).parent / portfolio_file
    credit = portfolio_config.get('credit', 2.50)
    wing_width = config.get('strikes', {}).get('wing_width', 50)

    if not portfolio_path.exists():
        print(colored("No portfolio file exists.", "yellow"))
        return

    print(colored(f"\nRecalculating portfolio P&L with credit=€{credit:.2f}, wing_width={wing_width}", "cyan"))

    data = pf.load_portfolio(portfolio_path)
    multiplier = 10  # Euro Stoxx 50 options multiplier

    for portfolio_name in ["always_trade", "filtered"]:
        portfolio = data["portfolios"][portfolio_name]
        total_pnl = 0
        win_count = 0

        for trade in portfolio.get("history", []):
            stoxx_close = trade.get("stoxx_close")
            call_strike = trade.get("call_strike")
            put_strike = trade.get("put_strike")

            # Recalculate P&L
            if stoxx_close <= put_strike:
                intrinsic = put_strike - stoxx_close
                loss = min(intrinsic, wing_width) - credit
                pnl = -loss * multiplier
            elif stoxx_close >= call_strike:
                intrinsic = stoxx_close - call_strike
                loss = min(intrinsic, wing_width) - credit
                pnl = -loss * multiplier
            else:
                pnl = credit * multiplier

            trade["pnl"] = pnl
            trade["outcome"] = "win" if pnl > 0 else "loss"
            total_pnl += pnl
            if pnl > 0:
                win_count += 1

        portfolio["total_pnl"] = total_pnl
        portfolio["win_count"] = win_count

    pf.save_portfolio(data, portfolio_path)

    print(colored("✓ Portfolio recalculated successfully", "green"))
    print(pf.format_portfolio_display(data))


def run_with_portfolio(config, use_additional_filters=False):
    """Run trade evaluation with portfolio tracking."""
    logger = get_logger()
    logger.info("Running with portfolio tracking enabled")

    portfolio_config = config.get('portfolio', {})
    portfolio_file = portfolio_config.get('file', 'portfolio.json')
    portfolio_path = Path(__file__).parent / portfolio_file
    fallback_credit = portfolio_config.get('credit', 2.50)

    # Credit will be fetched after we have the index price
    credit = fallback_credit
    credit_source = 'config'

    # Load portfolio
    try:
        portfolio_data = pf.load_portfolio(portfolio_path)
        logger.info(f"Portfolio loaded from {portfolio_path}")
    except PortfolioError as e:
        logger.error(f"Portfolio error: {e}")
        print(colored(f"[ERROR] Portfolio error: {e}", "red"))
        return

    # Settle any open trades from previous day
    prev_close = pf.get_previous_close()
    settlements = []

    for portfolio_name in ["always_trade", "filtered"]:
        if pf.has_open_trade(portfolio_name, portfolio_data):
            if prev_close is not None:
                pnl = pf.settle_open_trade(portfolio_name, prev_close, portfolio_data, credit=credit)
                if pnl is not None:
                    settlements.append((portfolio_name, pnl))
                    logger.log_trade_settlement(portfolio_name, pnl, prev_close)
            else:
                logger.warning(f"Could not fetch previous close to settle {portfolio_name}")
                print(colored(f"  [WARN] Could not fetch previous close to settle {portfolio_name}", "yellow"))

    if settlements:
        print(colored("\nSETTLED TRADES:", "white", attrs=["bold", "underline"]))
        for name, pnl in settlements:
            pnl_color = "green" if pnl >= 0 else "red"
            label = "Always Trade" if name == "always_trade" else "Filtered"
            print(colored(f"  {label}: {pnl:+.0f} EUR", pnl_color))
        print()

    # Run evaluation
    result = evaluate_trade(config, use_additional_filters=use_additional_filters, track_portfolio=True)

    if result is None:
        # Evaluation failed (e.g., market closed)
        pf.save_portfolio(portfolio_data, portfolio_path)
        return

    # Get real credit from IBKR if available, otherwise use config
    index_price = result['data']['stoxx_current']
    credit, credit_source = get_real_credit(config, index_price, logger)

    # Log credit source
    if credit_source == 'ibkr':
        logger.info(f"Using real IBKR credit: €{credit:.2f}")
        print(colored(f"\n  💰 Real credit from IBKR: €{credit:.2f}", "cyan"))
    else:
        logger.info(f"Using config credit: €{credit:.2f}")

    # Record new trades
    today = date.today().strftime('%Y-%m-%d')
    trade_info = {
        "date": today,
        "stoxx_entry": result['data']['stoxx_current'],
        "call_strike": result['call_strike'],
        "put_strike": result['put_strike'],
        "wing_width": result['wing_width'],
        "credit": credit,
        "credit_source": credit_source
    }

    # Always record to always_trade portfolio
    if pf.record_trade_entry("always_trade", trade_info, portfolio_data):
        logger.log_trade_entry("always_trade", trade_info)

    # Only record to filtered if GO
    if result['status'] == "GO":
        if pf.record_trade_entry("filtered", trade_info, portfolio_data):
            logger.log_trade_entry("filtered", trade_info)

    # Save portfolio
    pf.save_portfolio(portfolio_data, portfolio_path)
    logger.info(f"Portfolio saved to {portfolio_path}")

    # Show portfolio status
    print(pf.format_portfolio_display(portfolio_data))

    # Log portfolio summary
    summary = pf.get_portfolio_summary(portfolio_data)
    logger.log_portfolio_summary(summary)

    # Add to Telegram notification if configured
    if portfolio_config.get('include_in_telegram', True):
        telegram_summary = pf.format_portfolio_telegram(portfolio_data)
        send_telegram_message(config, telegram_summary)


def main():
    parser = argparse.ArgumentParser(
        description='STOXX50 0DTE Iron Condor Trade Filter (Euro Stoxx 50)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python trade_filter.py                    # Basic rules only
  python trade_filter.py -a                 # Include additional filters
  python trade_filter.py -p                 # Enable portfolio tracking
  python trade_filter.py --portfolio-status # View portfolio status
  python trade_filter.py --preset conservative  # Switch to conservative (1% OTM, €2.50)
  python trade_filter.py --preset aggressive    # Switch to aggressive (0.5% OTM, €5.00)
  python trade_filter.py --recalculate-portfolio # Recalc P&L with current credit
  python trade_filter.py --setup            # Run setup wizard
        """
    )

    parser.add_argument('-a', '--additional', action='store_true',
                        help='Enable additional filters (MA deviation, prev day range, VIX structure)')
    parser.add_argument('-p', '--portfolio', action='store_true',
                        help='Enable shadow portfolio tracking')
    parser.add_argument('--portfolio-status', action='store_true',
                        help='Display portfolio status only (no trade evaluation)')
    parser.add_argument('--portfolio-reset', action='store_true',
                        help='Reset portfolio data')
    parser.add_argument('-c', '--config', type=str, default=None,
                        help='Path to config file (default: config.yaml)')
    parser.add_argument('--setup', action='store_true',
                        help='Run the setup wizard for config and Telegram')
    parser.add_argument('--validate-config', action='store_true',
                        help='Validate configuration and exit')
    parser.add_argument('--daemon', action='store_true',
                        help='Run monitoring daemon (continuous monitoring)')
    parser.add_argument('--monitor-interval', type=int, default=300,
                        help='Monitoring check interval in seconds (default: 300)')
    parser.add_argument('--dashboard', action='store_true',
                        help='Launch web dashboard for monitoring')
    parser.add_argument('--dashboard-port', type=int, default=5000,
                        help='Web dashboard port (default: 5000)')
    parser.add_argument('--preset', type=str, choices=['conservative', 'aggressive'],
                        help='Switch strategy preset (updates config.yaml)')
    parser.add_argument('--recalculate-portfolio', action='store_true',
                        help='Recalculate portfolio P&L with current credit setting')

    args = parser.parse_args()

    # Load config first for portfolio commands
    config = load_config(args.config)

    # Validate configuration (non-strict mode - print warnings but continue)
    if not args.validate_config:  # Skip validation if only validating
        is_valid = validate_config(config, strict=False)
        if not is_valid:
            print(colored("\n⚠️  Configuration has errors! Fix them or use --validate-config to see details.\n", "yellow"))
            # Continue anyway in non-strict mode, but user is warned

    # Initialize logging
    log_config = config.get('logging', {})
    if log_config.get('enabled', True):
        logger = get_logger(config)
        logger.info("=" * 60)
        logger.info("STOXX50 Trade Filter Started")
        logger.info("=" * 60)

    # Handle portfolio commands
    if args.portfolio_status:
        show_portfolio_status(config)
        return

    if args.portfolio_reset:
        reset_portfolio_data(config)
        return

    # Handle preset switching
    if args.preset:
        switch_preset(args.preset, args.config or DEFAULT_CONFIG_PATH)
        return

    # Handle portfolio recalculation
    if getattr(args, 'recalculate_portfolio', False):
        recalculate_portfolio(config)
        return

    # Handle monitoring commands
    if args.daemon:
        run_monitoring_daemon_mode(config, args.monitor_interval)
        return

    if args.dashboard:
        run_dashboard_mode(config, args.monitor_interval, args.dashboard_port)
        return

    # Run setup wizard if requested
    if args.setup:
        setup_config()
        return

    # Handle validate config command
    if args.validate_config:
        is_valid = validate_config(config, strict=False)
        sys.exit(0 if is_valid else 1)

    # Check if setup is needed (only in interactive mode)
    if sys.stdin.isatty():
        config = check_and_prompt_setup(config)

    # Run with or without portfolio tracking
    if args.portfolio:
        run_with_portfolio(config, use_additional_filters=args.additional)
    else:
        evaluate_trade(config, use_additional_filters=args.additional)


def run_monitoring_daemon_mode(config, interval):
    """Run monitoring daemon mode."""
    import signal
    from monitor import TradeMonitor

    logger = get_logger()
    logger.info(f"Starting monitoring daemon (interval: {interval}s)")

    print(colored("\n" + "=" * 60, "cyan"))
    print(colored("  MONITORING DAEMON STARTED", "cyan", attrs=["bold"]))
    print(colored(f"  Check interval: {interval} seconds", "cyan"))
    print(colored("  Press Ctrl+C to stop", "yellow"))
    print(colored("=" * 60 + "\n", "cyan"))

    # Create and start monitor
    monitor = TradeMonitor(config, check_interval=interval)

    # Setup graceful shutdown
    def signal_handler(signum, frame):
        print(colored("\n\nShutting down daemon...", "yellow"))
        monitor.stop()
        print(colored("Daemon stopped.", "green"))
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start monitoring
    monitor.start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)


def run_dashboard_mode(config, interval, port):
    """Run web dashboard mode."""
    logger = get_logger()
    logger.info(f"Starting web dashboard on port {port}")

    print(colored("\n" + "=" * 60, "cyan"))
    print(colored("  WEB DASHBOARD STARTING", "cyan", attrs=["bold"]))
    print(colored(f"  URL: http://localhost:{port}", "green", attrs=["bold"]))
    print(colored(f"  Check interval: {interval}s", "cyan"))
    print(colored("=" * 60 + "\n", "cyan"))

    # Start monitoring in background
    monitor = start_monitoring_daemon(config, interval, enable_alerts=True)
    set_monitor(monitor)

    # Run web dashboard
    from dashboard import run_web_dashboard
    run_web_dashboard(host='0.0.0.0', port=port, debug=False)


if __name__ == "__main__":
    main()
