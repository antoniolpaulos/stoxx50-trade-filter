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
        
        .portfolio-card.always-trade {
            border-color: #666;
        }
        
        .portfolio-card.filtered {
            border-color: #00ff88;
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
                    <button class="btn btn-primary" onclick="runOnce()">Run Filter Now</button>
                    <button class="btn" onclick="runOnce(true)">Run with Filters</button>
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


def run_web_dashboard(host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
    """
    Run the web dashboard.
    
    Args:
        host: Host to bind to
        port: Port to listen on
        debug: Enable debug mode
    """
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
    
    print(colored("\n" + "=" * 60, "cyan"))
    print(colored("  STOXX50 TRADE FILTER - WEB DASHBOARD", "cyan", attrs=["bold"]))
    print(colored(f"  URL: http://localhost:{args.port}", "green", attrs=["bold"]))
    print(colored("=" * 60 + "\n", "cyan"))
    
    run_web_dashboard(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()
