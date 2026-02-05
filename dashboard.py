"""
Web dashboard for STOXX50 Trade Filter monitoring.
Real-time web interface showing current state and history.
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime
from typing import Dict, Any
from pathlib import Path
import json

from monitor import get_monitor, TradeState
from logger import get_logger


app = Flask(__name__)
logger = get_logger()


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


# HTML Template (embedded to avoid file dependencies)
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>STOXX50 Trade Filter - Monitor</title>
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
        }
        
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
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-left: 10px;
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
            .metrics-grid,
            .stats-grid {
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
    </style>
</head>
<body>
    <div class="header">
        <h1>STOXX50 Trade Filter Monitor</h1>
        <div id="connection-status">
            <span class="status-indicator status-unknown"></span>
            Connecting...
        </div>
    </div>
    
    <div class="container">
        <div class="card">
            <h2>
                Current Status
                <button class="refresh-btn" onclick="refreshData()">Refresh</button>
                <button class="refresh-btn" onclick="forceCheck()">Force Check</button>
            </h2>
            <div id="current-status">
                <p>Loading...</p>
            </div>
        </div>
        
        <div class="card">
            <h2>Market Data</h2>
            <div class="metrics-grid" id="market-metrics">
                <p>Loading...</p>
            </div>
        </div>
        
        <div class="card">
            <h2>Rules Status</h2>
            <ul class="rules-list" id="rules-list">
                <p>Loading...</p>
            </ul>
        </div>
        
        <div class="card">
            <h2>Statistics</h2>
            <div class="stats-grid" id="stats-grid">
                <p>Loading...</p>
            </div>
        </div>
        
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
                    <tr><td colspan="5">Loading...</td></tr>
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
        
        async function fetchStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                updateDisplay(data);
                updateConnectionStatus(true);
            } catch (error) {
                console.error('Error fetching status:', error);
                updateConnectionStatus(false);
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
        
        function updateDisplay(data) {
            // Current status
            const statusDiv = document.getElementById('current-status');
            if (data.state) {
                const stateClass = getStateClass(data.state.trade_state);
                const indicator = getStateIndicator(data.state.trade_state);
                statusDiv.innerHTML = `
                    <div class="metric">
                        ${indicator}
                        <div class="metric-value ${stateClass}">${data.state.trade_state}</div>
                        <div class="timestamp">Last check: ${formatTime(data.state.timestamp)}</div>
                    </div>
                    ${data.state.reasons.length > 0 ? `
                        <div class="error-message">
                            <strong>Reasons:</strong><br>
                            ${data.state.reasons.join('<br>')}
                        </div>
                    ` : ''}
                `;
            } else {
                statusDiv.innerHTML = '<p>No state available</p>';
            }
            
            // Market metrics
            const metricsDiv = document.getElementById('market-metrics');
            if (data.state) {
                const changeClass = data.state.intraday_change >= 0 ? 'price-up' : 'price-down';
                metricsDiv.innerHTML = `
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
                `;
            }
            
            // Rules list
            const rulesList = document.getElementById('rules-list');
            if (data.state && data.state.rules_status) {
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
            
            // Stats
            const statsDiv = document.getElementById('stats-grid');
            if (data.stats) {
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
        }
        
        function updateHistory(history) {
            const tbody = document.getElementById('history-body');
            if (history && history.length > 0) {
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
            } else {
                tbody.innerHTML = '<tr><td colspan="5">No history available</td></tr>';
            }
        }
        
        function updateConnectionStatus(connected) {
            const statusDiv = document.getElementById('connection-status');
            if (connected) {
                statusDiv.innerHTML = '<span class="status-indicator status-go"></span> Connected';
            } else {
                statusDiv.innerHTML = '<span class="status-indicator status-no-go"></span> Disconnected';
            }
        }
        
        async function forceCheck() {
            try {
                const response = await fetch('/api/force-check', { method: 'POST' });
                const data = await response.json();
                refreshData();
            } catch (error) {
                console.error('Error forcing check:', error);
                alert('Failed to force check');
            }
        }
        
        function refreshData() {
            fetchStatus();
            fetchHistory();
        }
        
        // Auto refresh
        setInterval(() => {
            if (autoRefresh) {
                refreshData();
            }
        }, refreshInterval);
        
        // Initial load
        refreshData();
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


if __name__ == '__main__':
    run_web_dashboard(debug=True)
