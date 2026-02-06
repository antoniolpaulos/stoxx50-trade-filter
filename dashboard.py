"""
Web dashboard for STOXX50 Trade Filter - Central Control Interface.
Run the trade filter, control daemon, and monitor everything from one place.
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import json
import threading
import time

from monitor import get_monitor, TradeMonitor, set_monitor
from logger import get_logger
from portfolio import load_portfolio
from position_sizing import PositionSizingCalculator


app = Flask(__name__, template_folder='templates')
logger = get_logger()

# Global state for daemon control
daemon_state = {
    'running': False,
    'monitor': None,
    'thread': None,
    'config': None,
    'start_time': None
}


@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('dashboard.html')


@app.route('/api/status')
def api_status():
    """Get current monitoring status."""
    monitor = get_monitor()

    if monitor is None:
        return jsonify({
            'running': False,
            'error': 'Monitor not running'
        })

    state = monitor.get_current_state()
    stats = monitor.get_stats()

    if state is None:
        return jsonify({
            'running': monitor.running,
            'state': None,
            'stats': stats
        })

    return jsonify({
        'running': monitor.running,
        'state': state.to_dict(),
        'stats': stats
    })


@app.route('/api/history')
def api_history():
    """Get state history."""
    monitor = get_monitor()

    if monitor is None:
        return jsonify({'error': 'Monitor not running'})

    n = request.args.get('n', 20, type=int)
    history = monitor.detector.get_history(n)

    return jsonify({
        'history': [state.to_dict() for state in history]
    })


@app.route('/api/stats')
def api_stats():
    """Get monitoring statistics."""
    monitor = get_monitor()

    if monitor is None:
        return jsonify({'error': 'Monitor not running'})

    return jsonify(monitor.get_stats())


@app.route('/api/force-check', methods=['POST'])
def api_force_check():
    """Force immediate check."""
    monitor = get_monitor()

    if monitor is None:
        return jsonify({'error': 'Monitor not running'}), 503

    state = monitor.force_check()
    return jsonify(state.to_dict())


@app.route('/api/portfolio')
def api_portfolio():
    """Get shadow portfolio data."""
    try:
        portfolio_data = load_portfolio()

        # Calculate derived metrics
        portfolios = portfolio_data.get('portfolios', {})

        result = {}
        for name, data in portfolios.items():
            total_pnl = data.get('total_pnl', 0.0)
            trade_count = data.get('trade_count', 0)
            win_count = data.get('win_count', 0)

            win_rate = (win_count / trade_count * 100) if trade_count > 0 else 0
            avg_pnl = (total_pnl / trade_count) if trade_count > 0 else 0

            result[name] = {
                'total_pnl': total_pnl,
                'trade_count': trade_count,
                'win_count': win_count,
                'loss_count': trade_count - win_count,
                'win_rate': round(win_rate, 2),
                'avg_pnl': round(avg_pnl, 2),
                'open_trade': data.get('open_trade'),
                'history': data.get('history', [])[-10:]  # Last 10 trades
            }

        # Calculate Filter Edge
        if 'always_trade' in result and 'filtered' in result:
            always_pnl = result['always_trade']['total_pnl']
            filtered_pnl = result['filtered']['total_pnl']
            result['filter_edge'] = round(filtered_pnl - always_pnl, 2)

        return jsonify(result)
    except Exception as e:
        logger.error(f"Error loading portfolio: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/run-once', methods=['POST'])
def api_run_once():
    """Run trade filter once."""
    try:
        from trade_filter import load_config, evaluate_trade

        config = load_config()
        use_additional = request.json.get('additional', False) if request.json else False

        # Run evaluation
        result = evaluate_trade(config, use_additional_filters=use_additional)

        return jsonify({
            'success': True,
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error running trade filter: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/daemon/status')
def api_daemon_status():
    """Get daemon status."""
    return jsonify({
        'running': daemon_state['running'],
        'start_time': daemon_state['start_time'].isoformat() if daemon_state['start_time'] else None,
        'monitor_running': daemon_state['monitor'].running if daemon_state['monitor'] else False
    })


@app.route('/api/daemon/start', methods=['POST'])
def api_daemon_start():
    """Start the monitoring daemon."""
    if daemon_state['running']:
        return jsonify({'success': False, 'error': 'Daemon already running'}), 400

    try:
        from trade_filter import load_config

        config = load_config()
        interval = request.json.get('interval', 300) if request.json else 300

        # Create and start monitor
        monitor = TradeMonitor(config, check_interval=interval)
        set_monitor(monitor)

        daemon_state['monitor'] = monitor
        daemon_state['config'] = config
        daemon_state['running'] = True
        daemon_state['start_time'] = datetime.now()

        monitor.start()

        logger.info(f"Dashboard started daemon with {interval}s interval")

        return jsonify({
            'success': True,
            'message': f'Daemon started with {interval}s interval',
            'start_time': daemon_state['start_time'].isoformat()
        })
    except Exception as e:
        logger.error(f"Error starting daemon: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/daemon/stop', methods=['POST'])
def api_daemon_stop():
    """Stop the monitoring daemon."""
    if not daemon_state['running']:
        return jsonify({'success': False, 'error': 'Daemon not running'}), 400

    try:
        if daemon_state['monitor']:
            daemon_state['monitor'].stop()

        daemon_state['running'] = False
        daemon_state['monitor'] = None
        daemon_state['start_time'] = None

        logger.info("Dashboard stopped daemon")

        return jsonify({
            'success': True,
            'message': 'Daemon stopped'
        })
    except Exception as e:
        logger.error(f"Error stopping daemon: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/position-size')
def api_position_size():
    """Calculate position size based on risk parameters."""
    try:
        account_balance = request.args.get('balance', 10000.0, type=float)
        credit = request.args.get('credit', 2.50, type=float)
        wing_width = request.args.get('wing_width', 50, type=int)
        risk_percent = request.args.get('risk_percent', 1.0, type=float)
        use_kelly = request.args.get('kelly', False, type=lambda x: x.lower() == 'true')

        calculator = PositionSizingCalculator(account_balance)
        position = calculator.calculate_position_size(
            credit=credit,
            wing_width=wing_width,
            risk_percent=risk_percent,
            use_kelly=use_kelly
        )

        return jsonify({
            'success': True,
            'position': {
                'spreads': position.spreads,
                'max_loss_per_spread': position.max_loss_per_spread,
                'total_max_loss': position.total_max_loss,
                'total_credit': position.total_credit,
                'risk_reward_ratio': position.risk_reward_ratio,
                'kelly_percent': position.kelly_percent,
                'risk_amount': position.risk_amount,
                'account_balance': account_balance
            }
        })
    except Exception as e:
        logger.error(f"Error calculating position size: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/risk-metrics')
def api_risk_metrics():
    """Calculate risk metrics for a trading strategy."""
    try:
        win_rate = request.args.get('win_rate', 0.65, type=float)
        avg_win = request.args.get('avg_win', 250.0, type=float)
        avg_loss = request.args.get('avg_loss', -350.0, type=float)

        calculator = PositionSizingCalculator(10000)
        metrics = calculator.calculate_risk_metrics(
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss
        )

        return jsonify({
            'success': True,
            'metrics': {
                'win_rate': metrics.win_rate,
                'avg_win': metrics.avg_win,
                'avg_loss': metrics.avg_loss,
                'profit_factor': metrics.profit_factor,
                'kelly_percent': metrics.kelly_percent,
                'kelly_half': metrics.kelly_half,
                'kelly_quarter': metrics.kelly_quarter,
                'expected_value': metrics.expected_value
            }
        })
    except Exception as e:
        logger.error(f"Error calculating risk metrics: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/portfolio/pnl-chart')
def api_pnl_chart():
    """Get cumulative P&L data for charting."""
    try:
        portfolio_data = load_portfolio()
        portfolios = portfolio_data.get('portfolios', {})

        result = {}

        for name in ['always_trade', 'filtered']:
            if name not in portfolios:
                continue

            portfolio = portfolios[name]
            history = portfolio.get('history', [])

            if not history:
                result[name] = {'dates': [], 'pnl': [], 'cumulative': []}
                continue

            # Sort by date
            sorted_history = sorted(history, key=lambda x: x.get('date', ''))

            dates = []
            daily_pnl = []
            cumulative = []
            running_total = 0.0

            for trade in sorted_history:
                trade_date = trade.get('date', '')
                pnl = trade.get('pnl', 0.0)

                dates.append(trade_date)
                daily_pnl.append(pnl)
                running_total += pnl
                cumulative.append(running_total)

            result[name] = {
                'dates': dates,
                'daily_pnl': daily_pnl,
                'cumulative': cumulative
            }

        return jsonify({
            'success': True,
            'data': result
        })
    except Exception as e:
        logger.error(f"Error loading P&L chart data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/status/brief')
def api_status_brief():
    """Get brief status for Telegram bot and other integrations."""
    try:
        from trade_filter import load_config, get_market_data, calculate_intraday_change

        config = load_config()
        monitor = get_monitor()

        # Try to get from monitor first
        if monitor and monitor.current_state:
            state = monitor.current_state
            return jsonify({
                'trade_state': state.trade_state.value,
                'stoxx_price': state.stoxx_price,
                'stoxx_open': state.stoxx_open,
                'intraday_change': state.intraday_change,
                'vix': state.vix,
                'reasons': state.reasons,
                'timestamp': state.timestamp,
                'source': 'monitor'
            })

        # Otherwise fetch fresh data
        data = get_market_data(include_history=False)
        intraday = calculate_intraday_change(data['stoxx_current'], data['stoxx_open'])

        intraday_max = config.get('rules', {}).get('intraday_change_max', 1.0)
        trade_state = 'GO' if abs(intraday) <= intraday_max else 'NO_GO'

        reasons = []
        if abs(intraday) > intraday_max:
            direction = "up" if intraday > 0 else "down"
            reasons.append(f"Trend too strong ({intraday:+.2f}% {direction})")

        return jsonify({
            'trade_state': trade_state,
            'stoxx_price': data['stoxx_current'],
            'stoxx_open': data['stoxx_open'],
            'intraday_change': intraday,
            'vix': data.get('vix'),
            'reasons': reasons,
            'timestamp': datetime.now().isoformat(),
            'source': 'fresh'
        })

    except Exception as e:
        logger.error(f"Error getting brief status: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio/summary')
def api_portfolio_summary():
    """Get compact portfolio summary for bot."""
    try:
        from portfolio import load_portfolio, get_portfolio_summary

        data = load_portfolio()
        summary = get_portfolio_summary(data)

        return jsonify(summary)
    except Exception as e:
        logger.error(f"Error getting portfolio summary: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """Handle incoming Telegram webhook updates."""
    try:
        from telegram_bot import get_bot

        bot = get_bot()
        if not bot:
            return jsonify({'error': 'Bot not initialized'}), 503

        update = request.get_json()
        if not update:
            return jsonify({'error': 'No update data'}), 400

        bot.handle_update(update)
        return jsonify({'ok': True})

    except Exception as e:
        logger.exception(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/telegram/status')
def api_telegram_status():
    """Get Telegram bot status."""
    try:
        from telegram_bot import get_bot

        bot = get_bot()
        return jsonify({
            'configured': bot.is_configured() if bot else False,
            'enabled': bot.enabled if bot else False,
            'whitelist_count': len(bot.whitelist) if bot else 0
        })
    except Exception as e:
        return jsonify({'configured': False, 'error': str(e)})


def run_web_dashboard(host: str = '0.0.0.0', port: int = 5000, debug: bool = False,
                      config: Optional[Dict[str, Any]] = None):
    """
    Run the web dashboard.

    Args:
        host: Host to bind to
        port: Port to listen on
        debug: Enable debug mode
        config: Optional configuration dict
    """
    # Initialize Telegram bot if configured
    if config:
        try:
            from telegram_bot import TelegramBot, set_bot
            bot = TelegramBot(config)
            if bot.is_configured():
                set_bot(bot)
                logger.info("Telegram bot initialized for webhook handling")
        except Exception as e:
            logger.warning(f"Failed to initialize Telegram bot: {e}")

    logger.info(f"Starting web dashboard on {host}:{port}")
    app.run(host=host, port=port, debug=debug)


def main():
    """Main entry point for standalone dashboard."""
    import argparse
    from termcolor import colored

    parser = argparse.ArgumentParser(
        description='STOXX50 Trade Filter - Web Dashboard',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python dashboard.py                    # Run dashboard on port 5000
  python dashboard.py --port 8080        # Run on custom port
  python dashboard.py --host 127.0.0.1   # Bind to localhost only
        """
    )

    parser.add_argument('--port', type=int, default=5000,
                        help='Port to run dashboard on (default: 5000)')
    parser.add_argument('--host', type=str, default='0.0.0.0',
                        help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug mode')

    args = parser.parse_args()

    # Load config for Telegram bot
    from trade_filter import load_config
    config = load_config()

    print(colored("\n" + "=" * 60, "cyan"))
    print(colored("  STOXX50 TRADE FILTER - WEB DASHBOARD", "cyan", attrs=["bold"]))
    print(colored(f"  URL: http://localhost:{args.port}", "green", attrs=["bold"]))
    if config.get('telegram', {}).get('enabled'):
        print(colored("  Telegram Bot: Enabled", "green"))
    print(colored("=" * 60 + "\n", "cyan"))

    run_web_dashboard(host=args.host, port=args.port, debug=args.debug, config=config)


if __name__ == '__main__':
    main()
