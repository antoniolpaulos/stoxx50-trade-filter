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


app = Flask(__name__)
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


# HTML Template with central control interface
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>STOXX50 Trade Filter - Central Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            line-height: 1.6;
        }
        
        .header {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 20px;
            border-bottom: 2px solid #0f3460;
        }
        
        .header h1 {
            font-size: 24px;
            color: #00d4ff;
            margin-bottom: 5px;
        }
        
        .header-subtitle {
            color: #888;
            font-size: 14px;
        }
        
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        
        .status-go {
            background: #00ff88;
            box-shadow: 0 0 10px #00ff88;
        }
        
        .status-no-go {
            background: #ff4757;
            box-shadow: 0 0 10px #ff4757;
        }
        
        .status-unknown {
            background: #ffa502;
        }
        
        .status-offline {
            background: #666;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .card {
            background: #1a1a1a;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #333;
        }
        
        .card h2 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        /* Control Panel Styles */
        .control-panel {
            background: linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%);
            border: 2px solid #00d4ff;
        }
        
        .control-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 15px;
        }
        
        .control-section {
            background: rgba(0, 0, 0, 0.3);
            padding: 15px;
            border-radius: 6px;
            border: 1px solid #333;
        }
        
        .control-section h3 {
            color: #888;
            font-size: 12px;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        
        .btn {
            background: #0f3460;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin: 5px;
            transition: all 0.3s ease;
        }
        
        .btn:hover {
            background: #1a4a7a;
            transform: translateY(-1px);
        }
        
        .btn:disabled {
            background: #333;
            color: #666;
            cursor: not-allowed;
            transform: none;
        }
        
        .btn-primary {
            background: #00d4ff;
            color: #000;
            font-weight: bold;
        }
        
        .btn-primary:hover {
            background: #33ddff;
        }
        
        .btn-success {
            background: #00ff88;
            color: #000;
        }
        
        .btn-success:hover {
            background: #33ff99;
        }
        
        .btn-danger {
            background: #ff4757;
        }
        
        .btn-danger:hover {
            background: #ff6b7a;
        }
        
        .daemon-status {
            display: flex;
            align-items: center;
            padding: 10px 15px;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 4px;
            margin-top: 10px;
        }
        
        .daemon-status-text {
            margin-left: 10px;
            font-weight: bold;
        }
        
        .daemon-running {
            color: #00ff88;
        }
        
        .daemon-stopped {
            color: #ff4757;
        }
        
        /* Portfolio Styles */
        .portfolio-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            margin-bottom: 20px;
        }
        
        .portfolio-card {
            background: #252525;
            padding: 20px;
            border-radius: 8px;
            border: 2px solid #333;
        }
        
        .portfolio-card h3 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 16px;
            text-transform: uppercase;
        }
        
        .portfolio-card {
            border-color: #444;
        }
        
        .portfolio-card.always-trade:hover {
            border-color: #666;
        }
        
        .portfolio-card.filtered:hover {
            border-color: #00d4ff;
        }
        
        .pnl-large {
            font-size: 36px;
            font-weight: bold;
            margin: 10px 0;
        }
        
        .filter-edge {
            background: linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%);
            padding: 20px;
            border-radius: 8px;
            margin-top: 20px;
            text-align: center;
            border: 2px solid #00d4ff;
        }
        
        .filter-edge-label {
            color: #888;
            font-size: 14px;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        
        .filter-edge-value {
            font-size: 42px;
            font-weight: bold;
        }
        
        .trades-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        
        .trades-table th,
        .trades-table td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #333;
            font-size: 12px;
        }
        
        .trades-table th {
            color: #00d4ff;
            font-weight: 600;
        }
        
        .stats-row {
            display: flex;
            justify-content: space-between;
            margin: 10px 0;
            padding: 10px;
            background: #1a1a1a;
            border-radius: 4px;
        }
        
        .stats-label {
            color: #888;
        }
        
        .stats-value {
            font-weight: bold;
        }
        
        .win-rate-bar {
            height: 8px;
            background: #333;
            border-radius: 4px;
            margin-top: 5px;
            overflow: hidden;
        }
        
        .win-rate-fill {
            height: 100%;
            background: linear-gradient(90deg, #00ff88, #00d4ff);
            border-radius: 4px;
            transition: width 0.3s ease;
        }
        
        /* Trade History Toggle */
        .toggle-btn {
            background: #1a4a7a;
            color: #00d4ff;
            border: 1px solid #00d4ff;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            margin-top: 15px;
            width: 100%;
            transition: all 0.3s ease;
        }
        
        .toggle-btn:hover {
            background: #0f3460;
        }
        
        .trade-history-container {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out;
            margin-top: 10px;
        }
        
        .trade-history-container.open {
            max-height: 300px;
            overflow-y: auto;
        }
        
        .trade-history-container::-webkit-scrollbar {
            width: 8px;
        }
        
        .trade-history-container::-webkit-scrollbar-track {
            background: #1a1a1a;
            border-radius: 4px;
        }
        
        .trade-history-container::-webkit-scrollbar-thumb {
            background: #333;
            border-radius: 4px;
        }
        
        .trade-history-container::-webkit-scrollbar-thumb:hover {
            background: #444;
        }
        
        /* Position Sizing Styles */
        .position-sizing {
            background: linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%);
            border: 2px solid #00d4ff;
        }
        
        .position-inputs {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .input-group {
            display: flex;
            flex-direction: column;
        }
        
        .input-group label {
            font-size: 11px;
            color: #888;
            text-transform: uppercase;
            margin-bottom: 5px;
        }
        
        .input-group input {
            background: #1a1a1a;
            border: 1px solid #333;
            color: #e0e0e0;
            padding: 10px;
            border-radius: 4px;
            font-size: 14px;
        }
        
        .input-group input:focus {
            outline: none;
            border-color: #00d4ff;
        }
        
        .calc-btn {
            background: #00d4ff;
            color: #000;
            border: none;
            padding: 12px 24px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            margin-right: 10px;
            transition: all 0.3s ease;
        }
        
        .calc-btn:hover {
            background: #33ddff;
            transform: translateY(-1px);
        }
        
        .kelly-btn {
            background: transparent;
            color: #00d4ff;
            border: 1px solid #00d4ff;
        }
        
        .kelly-btn:hover {
            background: rgba(0, 212, 255, 0.1);
        }
        
        .kelly-btn.active {
            background: #00d4ff;
            color: #000;
        }
        
        .position-results {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        
        .position-result-card {
            background: rgba(0, 0, 0, 0.3);
            padding: 15px;
            border-radius: 6px;
            border: 1px solid #333;
            text-align: center;
        }
        
        .position-result-card.highlight {
            border-color: #00ff88;
            background: rgba(0, 255, 136, 0.1);
        }
        
        .position-result-card.warning {
            border-color: #ffa502;
            background: rgba(255, 165, 2, 0.1);
        }
        
        .position-result-value {
            font-size: 28px;
            font-weight: bold;
            color: #00d4ff;
            margin: 5px 0;
        }
        
        .position-result-value.green {
            color: #00ff88;
        }
        
        .position-result-value.red {
            color: #ff4757;
        }
        
        .position-result-label {
            font-size: 11px;
            color: #888;
            text-transform: uppercase;
        }
        
        .kelly-bar {
            height: 6px;
            background: #333;
            border-radius: 3px;
            margin-top: 10px;
            overflow: hidden;
        }
        
        .kelly-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #ff4757, #ffa502, #00ff88);
            border-radius: 3px;
            transition: width 0.3s ease;
        }
        
        /* Market Status Styles */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .metric {
            background: #252525;
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }
        
        .metric-value {
            font-size: 32px;
            font-weight: bold;
            margin: 10px 0;
        }
        
        .metric-label {
            font-size: 12px;
            color: #888;
            text-transform: uppercase;
        }
        
        .price-up {
            color: #00ff88;
        }
        
        .price-down {
            color: #ff4757;
        }
        
        .rules-list {
            list-style: none;
        }
        
        .rule-item {
            display: flex;
            justify-content: space-between;
            padding: 10px;
            margin: 5px 0;
            background: #252525;
            border-radius: 4px;
        }
        
        .rule-pass {
            color: #00ff88;
        }
        
        .rule-fail {
            color: #ff4757;
        }
        
        .rule-warn {
            color: #ffa502;
        }
        
        .history-table {
            width: 100%;
            border-collapse: collapse;
        }
        
        .history-table th,
        .history-table td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #333;
        }
        
        .history-table th {
            color: #00d4ff;
            font-weight: 600;
        }
        
        .refresh-btn {
            background: #0f3460;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        
        .refresh-btn:hover {
            background: #1a4a7a;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
        }
        
        @media (max-width: 768px) {
            .portfolio-grid,
            .metrics-grid,
            .stats-grid,
            .control-grid {
                grid-template-columns: 1fr;
            }
        }
        
        .timestamp {
            color: #666;
            font-size: 12px;
        }
        
        .error-message {
            color: #ff4757;
            padding: 20px;
            background: rgba(255, 71, 87, 0.1);
            border-radius: 4px;
            margin: 10px 0;
        }
        
        .loading {
            color: #888;
            font-style: italic;
        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="header">
        <h1>STOXX50 Trade Filter</h1>
        <div class="header-subtitle">Central Control Dashboard</div>
        <div id="connection-status" style="margin-top: 10px;">
            <span class="status-indicator status-unknown"></span>
            <span id="connection-text">Connecting...</span>
        </div>
    </div>
    
    <div class="container">
        <!-- CONTROL PANEL -->
        <div class="card control-panel">
            <h2>
                <span>Control Panel</span>
                <button class="refresh-btn" onclick="refreshAll()">Refresh All</button>
            </h2>
            <div class="control-grid">
                <div class="control-section">
                    <h3>Quick Actions</h3>
                    <button class="btn btn-primary" onclick="runOnce()" title="Basic rules: Intraday change + Economic calendar">Run Basic Filter</button>
                    <button class="btn" onclick="runOnce(true)" title="Additional filters: MA deviation + VIX structure + Prev day range">Run Full Filter</button>
                    <p style="margin-top: 10px; font-size: 11px; color: #666;">
                        Basic: Rules 1-2 | Full: All 5 filters
                    </p>
                </div>
                
                <div class="control-section">
                    <h3>Daemon Control</h3>
                    <button class="btn btn-success" id="btn-start-daemon" onclick="startDaemon()">Start Daemon</button>
                    <button class="btn btn-danger" id="btn-stop-daemon" onclick="stopDaemon()">Stop Daemon</button>
                    <div class="daemon-status">
                        <span class="status-indicator status-offline" id="daemon-indicator"></span>
                        <span class="daemon-status-text daemon-stopped" id="daemon-text">Daemon Offline</span>
                    </div>
                </div>
                
                <div class="control-section">
                    <h3>Current Trade Signal</h3>
                    <div id="quick-signal" class="loading">Loading...</div>
                </div>
            </div>
        </div>
        
        <!-- PORTFOLIO (Now at the top) -->
        <div class="card">
            <h2>
                <span>Shadow Portfolio</span>
                <button class="refresh-btn" onclick="refreshPortfolio()">Refresh</button>
            </h2>
            <div id="portfolio-content">
                <p class="loading">Loading portfolio data...</p>
            </div>
        </div>

        <!-- P&L CHART -->
        <div class="card">
            <h2>P&L History Chart</h2>
            <div style="position: relative; height: 300px; width: 100%;">
                <canvas id="pnl-chart"></canvas>
            </div>
        </div>
        
        <!-- POSITION SIZING -->
        <div class="card position-sizing">
            <h2>
                <span>Position Sizing Calculator</span>
                <button class="refresh-btn" onclick="calculatePositionSize()">Calculate</button>
            </h2>
            <div class="position-inputs">
                <div class="input-group">
                    <label>Account Balance (€)</label>
                    <input type="number" id="ps-balance" value="10000" min="1000" step="1000">
                </div>
                <div class="input-group">
                    <label>Credit Received (€)</label>
                    <input type="number" id="ps-credit" value="2.50" min="0.50" max="10.00" step="0.10">
                </div>
                <div class="input-group">
                    <label>Wing Width (pts)</label>
                    <input type="number" id="ps-wing" value="50" min="10" max="100" step="10">
                </div>
                <div class="input-group">
                    <label>Risk % per Trade</label>
                    <input type="number" id="ps-risk" value="1.0" min="0.1" max="5.0" step="0.1">
                </div>
            </div>
            <div class="input-group" style="margin-bottom: 20px;">
                <button class="calc-btn" onclick="calculatePositionSize()">Calculate Size</button>
                <button class="calc-btn kelly-btn" id="btn-kelly" onclick="toggleKelly()">Use Kelly Criterion</button>
            </div>
            <div id="position-results">
                <p class="loading">Enter parameters and click Calculate</p>
            </div>
        </div>
        
        <!-- MARKET STATUS -->
        <div class="card">
            <h2>
                <span>Market Status</span>
                <button class="refresh-btn" onclick="refreshStatus()">Refresh</button>
            </h2>
            <div id="market-content">
                <p class="loading">Loading market data...</p>
            </div>
        </div>
        
        <!-- RULES STATUS -->
        <div class="card">
            <h2>Rules Status</h2>
            <ul class="rules-list" id="rules-list">
                <li class="loading">Loading...</li>
            </ul>
        </div>
        
        <!-- MONITORING STATS -->
        <div class="card">
            <h2>Monitoring Statistics</h2>
            <div class="stats-grid" id="stats-grid">
                <div class="loading">Loading...</div>
            </div>
        </div>
        
        <!-- HISTORY -->
        <div class="card">
            <h2>Recent History</h2>
            <table class="history-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>State</th>
                        <th>STOXX</th>
                        <th>Change</th>
                        <th>VIX</th>
                    </tr>
                </thead>
                <tbody id="history-body">
                    <tr><td colspan="5" class="loading">Loading...</td></tr>
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        let autoRefresh = true;
        let refreshInterval = 5000; // 5 seconds
        
        function formatNumber(num) {
            return num ? num.toFixed(2) : 'N/A';
        }
        
        function formatTime(isoString) {
            if (!isoString) return 'N/A';
            const date = new Date(isoString);
            return date.toLocaleTimeString();
        }
        
        function getStateClass(state) {
            if (state === 'GO') return 'price-up';
            if (state === 'NO_GO') return 'price-down';
            return '';
        }
        
        function getStateIndicator(state) {
            if (state === 'GO') return '<span class="status-indicator status-go"></span>';
            if (state === 'NO_GO') return '<span class="status-indicator status-no-go"></span>';
            return '<span class="status-indicator status-unknown"></span>';
        }
        
        // CONTROL PANEL FUNCTIONS
        async function runOnce(additional = false) {
            try {
                const response = await fetch('/api/run-once', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({additional: additional})
                });
                const data = await response.json();
                
                if (data.success) {
                    alert(`Trade filter executed!\nResult: ${data.result}`);
                    refreshAll();
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                console.error('Error running filter:', error);
                alert('Failed to run trade filter');
            }
        }
        
        async function startDaemon() {
            try {
                const response = await fetch('/api/daemon/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({interval: 300})
                });
                const data = await response.json();
                
                if (data.success) {
                    updateDaemonStatus(true);
                    alert('Daemon started successfully');
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                console.error('Error starting daemon:', error);
                alert('Failed to start daemon');
            }
        }
        
        async function stopDaemon() {
            try {
                const response = await fetch('/api/daemon/stop', {
                    method: 'POST'
                });
                const data = await response.json();
                
                if (data.success) {
                    updateDaemonStatus(false);
                    alert('Daemon stopped');
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                console.error('Error stopping daemon:', error);
                alert('Failed to stop daemon');
            }
        }
        
        function updateDaemonStatus(running) {
            const indicator = document.getElementById('daemon-indicator');
            const text = document.getElementById('daemon-text');
            const btnStart = document.getElementById('btn-start-daemon');
            const btnStop = document.getElementById('btn-stop-daemon');
            
            if (running) {
                indicator.className = 'status-indicator status-go';
                text.textContent = 'Daemon Running';
                text.className = 'daemon-status-text daemon-running';
                btnStart.disabled = true;
                btnStop.disabled = false;
            } else {
                indicator.className = 'status-indicator status-offline';
                text.textContent = 'Daemon Offline';
                text.className = 'daemon-status-text daemon-stopped';
                btnStart.disabled = false;
                btnStop.disabled = true;
            }
        }
        
        async function checkDaemonStatus() {
            try {
                const response = await fetch('/api/daemon/status');
                const data = await response.json();
                updateDaemonStatus(data.running);
            } catch (error) {
                console.error('Error checking daemon status:', error);
                updateDaemonStatus(false);
            }
        }
        
        // DATA FETCHING FUNCTIONS
        async function fetchStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                updateMarketDisplay(data);
                updateRulesDisplay(data);
                updateQuickSignal(data);
                updateConnectionStatus(true);
                return data;
            } catch (error) {
                console.error('Error fetching status:', error);
                updateConnectionStatus(false);
                return null;
            }
        }
        
        async function fetchHistory() {
            try {
                const response = await fetch('/api/history?n=10');
                const data = await response.json();
                updateHistory(data.history);
            } catch (error) {
                console.error('Error fetching history:', error);
            }
        }
        
        async function fetchPortfolio() {
            try {
                const response = await fetch('/api/portfolio');
                const data = await response.json();
                updatePortfolio(data);
            } catch (error) {
                console.error('Error fetching portfolio:', error);
                document.getElementById('portfolio-content').innerHTML = 
                    '<p class="error-message">Failed to load portfolio data</p>';
            }
        }
        
        // DISPLAY UPDATE FUNCTIONS
        function updateMarketDisplay(data) {
            const content = document.getElementById('market-content');
            
            if (!data || !data.state) {
                content.innerHTML = '<p class="loading">No market data available</p>';
                return;
            }
            
            const changeClass = data.state.intraday_change >= 0 ? 'price-up' : 'price-down';
            
            content.innerHTML = `
                <div class="metrics-grid">
                    <div class="metric">
                        <div class="metric-label">Trade State</div>
                        <div class="metric-value ${getStateClass(data.state.trade_state)}">
                            ${data.state.trade_state}
                        </div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">STOXX Current</div>
                        <div class="metric-value">${formatNumber(data.state.stoxx_price)}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">STOXX Open</div>
                        <div class="metric-value">${formatNumber(data.state.stoxx_open)}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Intraday Change</div>
                        <div class="metric-value ${changeClass}">${formatNumber(data.state.intraday_change)}%</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">VIX</div>
                        <div class="metric-value">${formatNumber(data.state.vix)}</div>
                    </div>
                </div>
                ${data.state.reasons.length > 0 ? `
                    <div class="error-message">
                        <strong>Blockers:</strong><br>
                        ${data.state.reasons.join('<br>')}
                    </div>
                ` : ''}
            `;
        }
        
        function updateRulesDisplay(data) {
            const rulesList = document.getElementById('rules-list');
            
            if (!data || !data.state || !data.state.rules_status) {
                rulesList.innerHTML = '<li class="loading">No rules data</li>';
                return;
            }
            
            rulesList.innerHTML = Object.entries(data.state.rules_status)
                .map(([rule, status]) => {
                    const statusClass = status === 'PASS' ? 'rule-pass' : 
                                      status === 'FAIL' ? 'rule-fail' : 
                                      status === 'WARN' ? 'rule-warn' : '';
                    return `<li class="rule-item">
                        <span>${rule}</span>
                        <span class="${statusClass}">${status}</span>
                    </li>`;
                }).join('');
        }
        
        function updateQuickSignal(data) {
            const signalDiv = document.getElementById('quick-signal');
            
            if (!data || !data.state) {
                signalDiv.innerHTML = '<span class="loading">No signal</span>';
                return;
            }
            
            const stateClass = getStateClass(data.state.trade_state);
            signalDiv.innerHTML = `
                <div style="font-size: 24px; font-weight: bold;" class="${stateClass}">
                    ${getStateIndicator(data.state.trade_state)} ${data.state.trade_state}
                </div>
                <div class="timestamp">${formatTime(data.state.timestamp)}</div>
            `;
        }
        
        function updateStats(data) {
            const statsDiv = document.getElementById('stats-grid');
            
            if (!data || !data.stats) {
                statsDiv.innerHTML = '<div class="loading">No stats</div>';
                return;
            }
            
            const uptime = data.stats.uptime_seconds ? 
                Math.floor(data.stats.uptime_seconds / 60) + ' min' : 'N/A';
            
            statsDiv.innerHTML = `
                <div class="metric">
                    <div class="metric-label">Checks</div>
                    <div class="metric-value">${data.stats.checks_performed || 0}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">State Changes</div>
                    <div class="metric-value">${data.stats.state_changes || 0}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Errors</div>
                    <div class="metric-value">${data.stats.errors || 0}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Uptime</div>
                    <div class="metric-value">${uptime}</div>
                </div>
            `;
        }
        
        function updateHistory(history) {
            const tbody = document.getElementById('history-body');
            
            if (!history || history.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="loading">No history</td></tr>';
                return;
            }
            
            tbody.innerHTML = history.slice().reverse().map(state => {
                const stateClass = getStateClass(state.trade_state);
                const changeClass = state.intraday_change >= 0 ? 'price-up' : 'price-down';
                return `<tr>
                    <td>${formatTime(state.timestamp)}</td>
                    <td class="${stateClass}">${state.trade_state}</td>
                    <td>${formatNumber(state.stoxx_price)}</td>
                    <td class="${changeClass}">${formatNumber(state.intraday_change)}%</td>
                    <td>${formatNumber(state.vix)}</td>
                </tr>`;
            }).join('');
        }
        
        function updatePortfolio(data) {
            // Save toggle states before re-rendering
            const alwaysOpen = document.getElementById('always-history')?.classList.contains('open');
            const filteredOpen = document.getElementById('filtered-history')?.classList.contains('open');
            
            const content = document.getElementById('portfolio-content');
            
            if (data.error) {
                content.innerHTML = `<p class="error-message">${data.error}</p>`;
                return;
            }
            
            const alwaysTrade = data.always_trade || {};
            const filtered = data.filtered || {};
            const filterEdge = data.filter_edge || 0;
            
            const alwaysPnl = alwaysTrade.total_pnl || 0;
            const filteredPnl = filtered.total_pnl || 0;
            
            const alwaysClass = alwaysPnl >= 0 ? 'price-up' : 'price-down';
            const filteredClass = filteredPnl >= 0 ? 'price-up' : 'price-down';
            const edgeClass = filterEdge >= 0 ? 'price-up' : 'price-down';
            
            const alwaysBtnText = alwaysOpen ? '▲ Hide Daily P&L History' : '▼ Show Daily P&L History';
            const filteredBtnText = filteredOpen ? '▲ Hide Daily P&L History' : '▼ Show Daily P&L History';
            const alwaysContainerClass = alwaysOpen ? 'trade-history-container open' : 'trade-history-container';
            const filteredContainerClass = filteredOpen ? 'trade-history-container open' : 'trade-history-container';
            
            content.innerHTML = `
                <div class="portfolio-grid">
                    <div class="portfolio-card always-trade">
                        <h3>Always Trade</h3>
                        <div class="pnl-large ${alwaysClass}">€${alwaysPnl.toFixed(2)}</div>
                        <div class="stats-row">
                            <span class="stats-label">Trades</span>
                            <span class="stats-value">${alwaysTrade.trade_count || 0}</span>
                        </div>
                        <div class="stats-row">
                            <span class="stats-label">Win Rate</span>
                            <span class="stats-value">${alwaysTrade.win_rate || 0}%</span>
                        </div>
                        <div class="win-rate-bar">
                            <div class="win-rate-fill" style="width: ${alwaysTrade.win_rate || 0}%"></div>
                        </div>
                        <div class="stats-row">
                            <span class="stats-label">Wins/Losses</span>
                            <span class="stats-value">${alwaysTrade.win_count || 0}/${alwaysTrade.loss_count || 0}</span>
                        </div>
                        <button class="toggle-btn" id="always-history-btn" onclick="toggleTradeHistory('always-history')">
                            ${alwaysBtnText}
                        </button>
                        <div class="${alwaysContainerClass}" id="always-history">
                            ${renderTradeHistory(alwaysTrade.history || [])}
                        </div>
                    </div>
                    
                    <div class="portfolio-card filtered">
                        <h3>Filtered (GO Only)</h3>
                        <div class="pnl-large ${filteredClass}">€${filteredPnl.toFixed(2)}</div>
                        <div class="stats-row">
                            <span class="stats-label">Trades</span>
                            <span class="stats-value">${filtered.trade_count || 0}</span>
                        </div>
                        <div class="stats-row">
                            <span class="stats-label">Win Rate</span>
                            <span class="stats-value">${filtered.win_rate || 0}%</span>
                        </div>
                        <div class="win-rate-bar">
                            <div class="win-rate-fill" style="width: ${filtered.win_rate || 0}%"></div>
                        </div>
                        <div class="stats-row">
                            <span class="stats-label">Wins/Losses</span>
                            <span class="stats-value">${filtered.win_count || 0}/${filtered.loss_count || 0}</span>
                        </div>
                        <button class="toggle-btn" id="filtered-history-btn" onclick="toggleTradeHistory('filtered-history')">
                            ${filteredBtnText}
                        </button>
                        <div class="${filteredContainerClass}" id="filtered-history">
                            ${renderTradeHistory(filtered.history || [])}
                        </div>
                    </div>
                </div>
                
                <div class="filter-edge">
                    <div class="filter-edge-label">Filter Edge (Filtered - Always Trade)</div>
                    <div class="filter-edge-value ${edgeClass}">
                        ${filterEdge >= 0 ? '+' : ''}€${filterEdge.toFixed(2)}
                    </div>
                    <p style="margin-top: 10px; color: #888; font-size: 14px;">
                        ${filterEdge > 0 ? 'Using the filter saved you money!' : 
                          filterEdge < 0 ? 'Always Trade is currently ahead' : 
                          'No difference yet'}
                    </p>
                </div>
            `;

            // Update P&L chart
            updatePnlChart(alwaysTrade.history || [], filtered.history || []);
        }

        let pnlChart = null;

        function updatePnlChart(alwaysHistory, filteredHistory) {
            const ctx = document.getElementById('pnl-chart');
            if (!ctx) return;

            // Calculate cumulative P&L for each portfolio
            function calcCumulative(history) {
                if (!history || history.length === 0) return { dates: [], values: [] };
                const sorted = [...history].sort((a, b) => (a.date || '').localeCompare(b.date || ''));
                let cumulative = 0;
                return {
                    dates: sorted.map(t => t.date || ''),
                    values: sorted.map(t => { cumulative += (t.pnl || 0); return cumulative; })
                };
            }

            const alwaysData = calcCumulative(alwaysHistory);
            const filteredData = calcCumulative(filteredHistory);

            // Merge dates for consistent x-axis
            const allDates = [...new Set([...alwaysData.dates, ...filteredData.dates])].sort();

            if (allDates.length === 0) {
                if (pnlChart) {
                    pnlChart.destroy();
                    pnlChart = null;
                }
                return;
            }

            // Map cumulative values to merged dates
            function mapToAllDates(data) {
                let lastVal = 0;
                return allDates.map(date => {
                    const idx = data.dates.indexOf(date);
                    if (idx !== -1) {
                        lastVal = data.values[idx];
                    }
                    return lastVal;
                });
            }

            const alwaysValues = mapToAllDates(alwaysData);
            const filteredValues = mapToAllDates(filteredData);

            if (pnlChart) {
                pnlChart.destroy();
            }

            pnlChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: allDates,
                    datasets: [
                        {
                            label: 'Always Trade',
                            data: alwaysValues,
                            borderColor: '#00d4ff',
                            backgroundColor: 'rgba(0, 212, 255, 0.1)',
                            tension: 0.3,
                            fill: false
                        },
                        {
                            label: 'Filtered',
                            data: filteredValues,
                            borderColor: '#00ff88',
                            backgroundColor: 'rgba(0, 255, 136, 0.1)',
                            tension: 0.3,
                            fill: false
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            ticks: { color: '#888' },
                            grid: { color: '#333' },
                            title: { display: true, text: 'Cumulative P&L (€)', color: '#888' }
                        },
                        x: {
                            ticks: { color: '#888', maxRotation: 45 },
                            grid: { color: '#333' }
                        }
                    },
                    plugins: {
                        legend: {
                            labels: { color: '#e0e0e0' }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    return context.dataset.label + ': €' + context.parsed.y.toFixed(2);
                                }
                            }
                        }
                    }
                }
            });
        }

        function renderTradeHistory(history) {
            if (!history || history.length === 0) {
                return '<p style="color: #666; font-size: 12px; text-align: center; padding: 10px;">No trades yet</p>';
            }
            
            const rows = history.slice().reverse().map(trade => {
                const pnlClass = trade.pnl >= 0 ? 'price-up' : 'price-down';
                const pnlSign = trade.pnl >= 0 ? '+' : '';
                return `<tr>
                    <td>${trade.date}</td>
                    <td>${trade.stoxx_close}</td>
                    <td class="${pnlClass}">${pnlSign}€${trade.pnl.toFixed(2)}</td>
                </tr>`;
            }).join('');
            
            return `<table class="trades-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>STOXX Close</th>
                        <th>Daily P&L</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>`;
        }
        
        function toggleTradeHistory(id) {
            const container = document.getElementById(id);
            const btn = document.getElementById(id + '-btn');
            const isOpen = container.classList.contains('open');
            
            if (isOpen) {
                container.classList.remove('open');
                btn.textContent = '▼ Show Daily P&L History';
            } else {
                container.classList.add('open');
                btn.textContent = '▲ Hide Daily P&L History';
            }
        }
        
        function updateConnectionStatus(connected) {
            const indicator = document.querySelector('#connection-status .status-indicator');
            const text = document.getElementById('connection-text');
            
            if (connected) {
                indicator.className = 'status-indicator status-go';
                text.textContent = 'Connected';
            } else {
                indicator.className = 'status-indicator status-no-go';
                text.textContent = 'Disconnected';
            }
        }
        
        // REFRESH FUNCTIONS
        function refreshAll() {
            fetchStatus();
            fetchHistory();
            fetchPortfolio();
            checkDaemonStatus();
        }
        
        function refreshStatus() {
            fetchStatus().then(data => {
                if (data && data.stats) {
                    updateStats(data);
                }
            });
        }
        
        function refreshPortfolio() {
            fetchPortfolio();
        }
        
        let useKelly = false;
        
        function toggleKelly() {
            useKelly = !useKelly;
            const btn = document.getElementById('btn-kelly');
            if (useKelly) {
                btn.classList.add('active');
                btn.textContent = 'Kelly Active';
            } else {
                btn.classList.remove('active');
                btn.textContent = 'Use Kelly Criterion';
            }
        }
        
        async function calculatePositionSize() {
            const balance = document.getElementById('ps-balance').value;
            const credit = document.getElementById('ps-credit').value;
            const wing = document.getElementById('ps-wing').value;
            const risk = document.getElementById('ps-risk').value;
            
            try {
                const params = new URLSearchParams({
                    balance: balance,
                    credit: credit,
                    wing_width: wing,
                    risk_percent: risk,
                    kelly: useKelly
                });
                
                const response = await fetch(`/api/position-size?${params}`);
                const data = await response.json();
                
                if (data.success) {
                    updatePositionResults(data.position);
                } else {
                    document.getElementById('position-results').innerHTML = 
                        `<p class="error-message">Error: ${data.error}</p>`;
                }
            } catch (error) {
                console.error('Error calculating position size:', error);
                document.getElementById('position-results').innerHTML = 
                    `<p class="error-message">Failed to calculate position size</p>`;
            }
        }
        
        function updatePositionResults(position) {
            const resultsDiv = document.getElementById('position-results');
            
            const riskClass = position.total_max_loss <= 500 ? 'green' : '';
            const rrClass = position.risk_reward_ratio >= 10 ? 'green' : 
                           position.risk_reward_ratio >= 5 ? '' : 'red';
            
            resultsDiv.innerHTML = `
                <div class="position-result-card highlight">
                    <div class="position-result-label">Suggested Size</div>
                    <div class="position-result-value">${position.spreads} spreads</div>
                    <div class="position-result-label">${position.spreads * 2} contracts</div>
                </div>
                <div class="position-result-card ${riskClass}">
                    <div class="position-result-label">Max Loss</div>
                    <div class="position-result-value">€${position.total_max_loss.toFixed(2)}</div>
                    <div class="position-result-label">€${position.max_loss_per_spread.toFixed(2)} per spread</div>
                </div>
                <div class="position-result-card">
                    <div class="position-result-label">Total Credit</div>
                    <div class="position-result-value green">€${position.total_credit.toFixed(2)}</div>
                    <div class="position-result-label">Received upfront</div>
                </div>
                <div class="position-result-card ${rrClass}">
                    <div class="position-result-label">Risk/Reward</div>
                    <div class="position-result-value">1:${position.risk_reward_ratio.toFixed(1)}</div>
                    <div class="position-result-label">Max loss : Credit</div>
                </div>
                ${position.kelly_percent ? `
                <div class="position-result-card">
                    <div class="position-result-label">Kelly Criterion</div>
                    <div class="position-result-value">${position.kelly_percent.toFixed(1)}%</div>
                    <div class="kelly-bar">
                        <div class="kelly-bar-fill" style="width: ${Math.min(position.kelly_percent, 100)}%"></div>
                    </div>
                    <div class="position-result-label">Quarter Kelly: ${(position.kelly_percent / 4).toFixed(1)}%</div>
                </div>
                ` : `
                <div class="position-result-card">
                    <div class="position-result-label">Risk Amount</div>
                    <div class="position-result-value">€${position.risk_amount.toFixed(2)}</div>
                    <div class="position-result-label">${((position.risk_amount / position.account_balance) * 100).toFixed(1)}% of account</div>
                </div>
                `}
            `;
        }
        
        // AUTO REFRESH
        setInterval(() => {
            if (autoRefresh) {
                refreshAll();
            }
        }, refreshInterval);
        
        // INITIAL LOAD
        document.addEventListener('DOMContentLoaded', () => {
            refreshAll();
        });
    </script>
</body>
</html>
'''


@app.route('/dashboard.html')
def dashboard_html():
    """Serve dashboard HTML."""
    return DASHBOARD_HTML


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


# Create templates directory and save HTML
import os

def setup_templates():
    """Setup templates directory."""
    template_dir = Path(__file__).parent / 'templates'
    template_dir.mkdir(exist_ok=True)
    
    template_file = template_dir / 'dashboard.html'
    template_file.write_text(DASHBOARD_HTML)
    
    return template_dir


# Configure Flask to use templates
app.template_folder = str(setup_templates())


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
