"""
Real-time monitoring system for STOXX50 Trade Filter.
Provides continuous monitoring with state change detection and web dashboard.
"""

import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import json

from logger import get_logger
from exceptions import MarketDataError

# Lazy imports to avoid circular dependency
def _get_market_data(*args, **kwargs):
    from trade_filter import get_market_data as _gmd
    return _gmd(*args, **kwargs)

def _calculate_intraday_change(*args, **kwargs):
    from trade_filter import calculate_intraday_change as _cic
    return _cic(*args, **kwargs)


class TradeState(Enum):
    """Possible trade states."""
    GO = "GO"
    NO_GO = "NO_GO"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


@dataclass
class MonitoringState:
    """Current monitoring state."""
    timestamp: str
    trade_state: TradeState
    stoxx_price: Optional[float]
    stoxx_open: Optional[float]
    intraday_change: Optional[float]
    vix: Optional[float]
    rules_status: Dict[str, Any]
    reasons: list
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp,
            'trade_state': self.trade_state.value,
            'stoxx_price': self.stoxx_price,
            'stoxx_open': self.stoxx_open,
            'intraday_change': self.intraday_change,
            'vix': self.vix,
            'rules_status': self.rules_status,
            'reasons': self.reasons
        }


class StateChangeDetector:
    """Detects changes in trade state and individual rules."""
    
    def __init__(self):
        self.previous_state: Optional[MonitoringState] = None
        self.state_history: list = []
        self.max_history = 100
    
    def update(self, new_state: MonitoringState) -> Dict[str, Any]:
        """
        Update with new state and detect changes.
        
        Returns:
            Dict with 'changed', 'previous_state', 'current_state', 'changes'
        """
        changes = {
            'changed': False,
            'state_changed': False,
            'previous_state': None,
            'current_state': new_state,
            'changes': []
        }
        
        if self.previous_state is not None:
            # Check for state change
            if self.previous_state.trade_state != new_state.trade_state:
                changes['changed'] = True
                changes['state_changed'] = True
                changes['changes'].append({
                    'type': 'state_change',
                    'from': self.previous_state.trade_state.value,
                    'to': new_state.trade_state.value
                })
            
            # Check for rule changes
            prev_rules = self.previous_state.rules_status
            curr_rules = new_state.rules_status
            
            for rule_name in set(prev_rules.keys()) | set(curr_rules.keys()):
                prev_val = prev_rules.get(rule_name)
                curr_val = curr_rules.get(rule_name)
                
                if prev_val != curr_val:
                    changes['changed'] = True
                    changes['changes'].append({
                        'type': 'rule_change',
                        'rule': rule_name,
                        'from': prev_val,
                        'to': curr_val
                    })
            
            # Check for significant price moves (>0.5%)
            if (self.previous_state.stoxx_price and new_state.stoxx_price):
                price_change_pct = abs(
                    (new_state.stoxx_price - self.previous_state.stoxx_price) / 
                    self.previous_state.stoxx_price * 100
                )
                if price_change_pct > 0.5:
                    changes['changed'] = True
                    changes['changes'].append({
                        'type': 'price_move',
                        'magnitude': price_change_pct
                    })
        
        changes['previous_state'] = self.previous_state
        self.previous_state = new_state
        
        # Add to history
        self.state_history.append(new_state)
        if len(self.state_history) > self.max_history:
            self.state_history.pop(0)
        
        return changes
    
    def get_history(self, n: int = 10) -> list:
        """Get last N states from history."""
        return self.state_history[-n:]


class TradeMonitor:
    """Main monitoring class for continuous trade evaluation."""
    
    def __init__(self, config: Dict[str, Any], check_interval: int = 300):
        """
        Initialize monitor.
        
        Args:
            config: Configuration dictionary
            check_interval: Seconds between checks (default 5 minutes)
        """
        self.config = config
        self.check_interval = check_interval
        self.logger = get_logger()
        self.detector = StateChangeDetector()
        self.current_state: Optional[MonitoringState] = None
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.callbacks: list = []
        self.last_check_time: Optional[datetime] = None
        self.stats = {
            'checks_performed': 0,
            'state_changes': 0,
            'errors': 0,
            'start_time': None
        }
    
    def add_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Add callback for state changes."""
        self.callbacks.append(callback)
    
    def _perform_check(self) -> MonitoringState:
        """Perform single evaluation check."""
        try:
            # Get market data
            data = _get_market_data(include_history=False)
            
            # Calculate intraday change
            intraday_change = _calculate_intraday_change(
                data['stoxx_current'], 
                data['stoxx_open']
            )
            
            # Get thresholds
            vix_warn = self.config['rules'].get('vix_warn', 22)
            intraday_max = self.config['rules']['intraday_change_max']
            
            # Evaluate rules
            rules_status = {}
            reasons = []
            
            # VIX check (warning only)
            if 'vix' in data:
                vix_ok = data['vix'] <= vix_warn
                rules_status['vix'] = 'PASS' if vix_ok else 'WARN'
                if not vix_ok:
                    reasons.append(f"VIX elevated ({data['vix']:.2f})")
            else:
                rules_status['vix'] = 'N/A'
            
            # Intraday change check (blocking)
            change_ok = abs(intraday_change) <= intraday_max
            rules_status['intraday_change'] = 'PASS' if change_ok else 'FAIL'
            if not change_ok:
                direction = "up" if intraday_change > 0 else "down"
                reasons.append(f"Trend too strong ({intraday_change:+.2f}% {direction})")
            
            # Determine state
            if not change_ok:
                state = TradeState.NO_GO
            else:
                state = TradeState.GO
            
            # Create state object
            monitoring_state = MonitoringState(
                timestamp=datetime.now().isoformat(),
                trade_state=state,
                stoxx_price=data['stoxx_current'],
                stoxx_open=data['stoxx_open'],
                intraday_change=intraday_change,
                vix=data.get('vix'),
                rules_status=rules_status,
                reasons=reasons
            )
            
            self.stats['checks_performed'] += 1
            self.last_check_time = datetime.now()
            
            return monitoring_state
            
        except MarketDataError as e:
            self.logger.error(f"Market data error during monitoring: {e}")
            self.stats['errors'] += 1
            return MonitoringState(
                timestamp=datetime.now().isoformat(),
                trade_state=TradeState.ERROR,
                stoxx_price=None,
                stoxx_open=None,
                intraday_change=None,
                vix=None,
                rules_status={'error': str(e)},
                reasons=[str(e)]
            )
        except Exception as e:
            self.logger.exception(f"Unexpected error during monitoring: {e}")
            self.stats['errors'] += 1
            return MonitoringState(
                timestamp=datetime.now().isoformat(),
                trade_state=TradeState.ERROR,
                stoxx_price=None,
                stoxx_open=None,
                intraday_change=None,
                vix=None,
                rules_status={'error': str(e)},
                reasons=[str(e)]
            )
    
    def _monitor_loop(self):
        """Main monitoring loop (runs in thread)."""
        self.logger.info("Monitor loop started")
        
        while self.running:
            try:
                # Perform check
                new_state = self._perform_check()
                self.current_state = new_state
                
                # Detect changes
                changes = self.detector.update(new_state)
                
                if changes['changed']:
                    self.stats['state_changes'] += 1
                    self.logger.info(f"State change detected: {changes}")
                    
                    # Notify callbacks
                    for callback in self.callbacks:
                        try:
                            callback(changes)
                        except Exception as e:
                            self.logger.error(f"Callback error: {e}")
                    
                    # Log significant changes
                    if changes['state_changed']:
                        prev = changes['previous_state'].trade_state.value if changes['previous_state'] else 'None'
                        curr = changes['current_state'].trade_state.value
                        self.logger.warning(f"TRADE STATE CHANGE: {prev} -> {curr}")
                
                # Sleep until next check
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.exception(f"Error in monitor loop: {e}")
                time.sleep(10)  # Short sleep on error
    
    def start(self):
        """Start monitoring in background thread."""
        if self.running:
            self.logger.warning("Monitor already running")
            return
        
        self.running = True
        self.stats['start_time'] = datetime.now()
        self.logger.info(f"Starting trade monitor (interval: {self.check_interval}s)")
        
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop(self):
        """Stop monitoring."""
        if not self.running:
            return
        
        self.logger.info("Stopping trade monitor")
        self.running = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
    
    def get_current_state(self) -> Optional[MonitoringState]:
        """Get current monitoring state."""
        return self.current_state
    
    def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        stats = self.stats.copy()
        if stats['start_time']:
            stats['uptime_seconds'] = (datetime.now() - stats['start_time']).total_seconds()
        return stats
    
    def force_check(self) -> MonitoringState:
        """Force immediate check (useful for testing)."""
        return self._perform_check()


class AlertManager:
    """Manages alerts for state changes."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = get_logger()
        self.last_alert_time: Optional[datetime] = None
        self.alert_cooldown = 300  # 5 minutes between alerts
    
    def should_alert(self) -> bool:
        """Check if enough time has passed since last alert."""
        if self.last_alert_time is None:
            return True
        
        elapsed = (datetime.now() - self.last_alert_time).total_seconds()
        return elapsed >= self.alert_cooldown
    
    def send_alert(self, changes: Dict[str, Any]):
        """Send alert for state change."""
        if not self.should_alert():
            return
        
        self.last_alert_time = datetime.now()
        
        # Build alert message
        state = changes['current_state']
        messages = []
        
        if changes.get('state_changed'):
            prev = changes['previous_state'].trade_state.value if changes['previous_state'] else 'Unknown'
            curr = state.trade_state.value
            messages.append(f"🚨 STATE CHANGE: {prev} → {curr}")
        
        for change in changes.get('changes', []):
            if change['type'] == 'rule_change':
                messages.append(f"• Rule '{change['rule']}': {change['from']} → {change['to']}")
            elif change['type'] == 'price_move':
                messages.append(f"• Significant price move: {change['magnitude']:.2f}%")
        
        messages.append(f"\nCurrent: STOXX {state.stoxx_price:.0f} ({state.intraday_change:+.2f}%)")
        if state.vix:
            messages.append(f"VIX: {state.vix:.2f}")
        
        alert_msg = "\n".join(messages)
        
        # Log alert
        self.logger.warning(f"ALERT: {alert_msg}")
        
        # Send Telegram if configured
        self._send_telegram_alert(alert_msg)
    
    def _send_telegram_alert(self, message: str):
        """Send alert via Telegram."""
        try:
            from trade_filter import send_telegram_message
            send_telegram_message(self.config, f"<b>MONITOR ALERT</b>\n\n{message}")
        except Exception as e:
            self.logger.error(f"Failed to send Telegram alert: {e}")


def start_monitoring_daemon(config: Dict[str, Any], 
                           check_interval: int = 300,
                           enable_alerts: bool = True) -> TradeMonitor:
    """
    Start monitoring daemon.
    
    Args:
        config: Configuration dictionary
        check_interval: Seconds between checks
        enable_alerts: Whether to send alerts on changes
        
    Returns:
        TradeMonitor instance
    """
    monitor = TradeMonitor(config, check_interval)
    
    if enable_alerts:
        alert_manager = AlertManager(config)
        monitor.add_callback(alert_manager.send_alert)
    
    monitor.start()
    return monitor


# Global monitor instance for web dashboard
_global_monitor: Optional[TradeMonitor] = None


def get_monitor() -> Optional[TradeMonitor]:
    """Get global monitor instance (for web dashboard)."""
    return _global_monitor


def set_monitor(monitor: TradeMonitor):
    """Set global monitor instance."""
    global _global_monitor
    _global_monitor = monitor
