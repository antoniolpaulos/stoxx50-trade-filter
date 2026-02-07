"""
Unit tests for the real-time monitoring system.
"""

import pytest
import time
import threading
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor import (
    TradeState, MonitoringState, StateChangeDetector,
    TradeMonitor, AlertManager, start_monitoring_daemon
)


class TestTradeState:
    """Test TradeState enum."""

    def test_state_values(self):
        """Test state enum values."""
        assert TradeState.GO.value == "GO"
        assert TradeState.NO_GO.value == "NO_GO"
        assert TradeState.UNKNOWN.value == "UNKNOWN"
        assert TradeState.ERROR.value == "ERROR"


class TestMonitoringState:
    """Test MonitoringState dataclass."""

    def test_state_creation(self):
        """Test creating monitoring state."""
        state = MonitoringState(
            timestamp=datetime.now().isoformat(),
            trade_state=TradeState.GO,
            stoxx_price=5180.0,
            stoxx_open=5170.0,
            intraday_change=0.19,
            vix=18.5,
            rules_status={'vix': 'PASS', 'intraday_change': 'PASS'},
            reasons=[]
        )

        assert state.trade_state == TradeState.GO
        assert state.stoxx_price == 5180.0

    def test_state_to_dict(self):
        """Test conversion to dictionary."""
        state = MonitoringState(
            timestamp="2026-02-05T10:00:00",
            trade_state=TradeState.GO,
            stoxx_price=5180.0,
            stoxx_open=5170.0,
            intraday_change=0.19,
            vix=18.5,
            rules_status={'vix': 'PASS'},
            reasons=[]
        )

        d = state.to_dict()
        assert d['trade_state'] == 'GO'
        assert d['stoxx_price'] == 5180.0


class TestStateChangeDetector:
    """Test state change detection."""

    def test_initial_update(self):
        """Test first update (no previous state)."""
        detector = StateChangeDetector()
        state = MonitoringState(
            timestamp="2026-02-05T10:00:00",
            trade_state=TradeState.GO,
            stoxx_price=5180.0,
            stoxx_open=5170.0,
            intraday_change=0.19,
            vix=18.5,
            rules_status={'vix': 'PASS'},
            reasons=[]
        )

        changes = detector.update(state)

        assert changes['changed'] is False  # First update, no changes
        assert changes['previous_state'] is None

    def test_state_change_detection(self):
        """Test detecting state changes."""
        detector = StateChangeDetector()

        # First state
        state1 = MonitoringState(
            timestamp="2026-02-05T10:00:00",
            trade_state=TradeState.GO,
            stoxx_price=5180.0,
            stoxx_open=5170.0,
            intraday_change=0.19,
            vix=18.5,
            rules_status={'vix': 'PASS'},
            reasons=[]
        )
        detector.update(state1)

        # Second state - different
        state2 = MonitoringState(
            timestamp="2026-02-05T10:05:00",
            trade_state=TradeState.NO_GO,
            stoxx_price=5220.0,
            stoxx_open=5170.0,
            intraday_change=0.97,
            vix=18.5,
            rules_status={'vix': 'PASS', 'intraday_change': 'FAIL'},
            reasons=['Trend too strong']
        )
        changes = detector.update(state2)

        assert changes['changed'] is True
        assert changes['state_changed'] is True
        assert any(c['type'] == 'state_change' for c in changes['changes'])

    def test_rule_change_detection(self):
        """Test detecting individual rule changes."""
        detector = StateChangeDetector()

        state1 = MonitoringState(
            timestamp="2026-02-05T10:00:00",
            trade_state=TradeState.GO,
            stoxx_price=5180.0,
            stoxx_open=5170.0,
            intraday_change=0.19,
            vix=18.5,
            rules_status={'vix': 'PASS'},
            reasons=[]
        )
        detector.update(state1)

        state2 = MonitoringState(
            timestamp="2026-02-05T10:05:00",
            trade_state=TradeState.GO,
            stoxx_price=5180.0,
            stoxx_open=5170.0,
            intraday_change=0.19,
            vix=25.0,
            rules_status={'vix': 'WARN'},
            reasons=[]
        )
        changes = detector.update(state2)

        assert changes['changed'] is True
        assert any(c['type'] == 'rule_change' and c['rule'] == 'vix'
                   for c in changes['changes'])

    def test_price_move_detection(self):
        """Test detecting significant price moves."""
        detector = StateChangeDetector()

        state1 = MonitoringState(
            timestamp="2026-02-05T10:00:00",
            trade_state=TradeState.GO,
            stoxx_price=5180.0,
            stoxx_open=5170.0,
            intraday_change=0.19,
            vix=18.5,
            rules_status={'vix': 'PASS'},
            reasons=[]
        )
        detector.update(state1)

        state2 = MonitoringState(
            timestamp="2026-02-05T10:05:00",
            trade_state=TradeState.GO,
            stoxx_price=5250.0,  # Big move
            stoxx_open=5170.0,
            intraday_change=1.55,
            vix=18.5,
            rules_status={'vix': 'PASS'},
            reasons=[]
        )
        changes = detector.update(state2)

        assert changes['changed'] is True
        assert any(c['type'] == 'price_move' for c in changes['changes'])

    def test_history_management(self):
        """Test history storage."""
        detector = StateChangeDetector()
        detector.max_history = 5

        for i in range(10):
            state = MonitoringState(
                timestamp=f"2026-02-05T10:{i:02d}:00",
                trade_state=TradeState.GO,
                stoxx_price=5180.0 + i,
                stoxx_open=5170.0,
                intraday_change=0.19,
                vix=18.5,
                rules_status={'vix': 'PASS'},
                reasons=[]
            )
            detector.update(state)

        history = detector.get_history()
        assert len(history) == 5
        assert history[-1].stoxx_price == 5189.0


class TestTradeMonitor:
    """Test TradeMonitor class."""

    def test_monitor_creation(self):
        """Test monitor initialization."""
        config = {'rules': {'vix_warn': 22, 'intraday_change_max': 1.0}}
        monitor = TradeMonitor(config, check_interval=60)

        assert monitor.config == config
        assert monitor.check_interval == 60
        assert monitor.running is False

    @patch('monitor._get_market_data')
    def test_perform_check_success(self, mock_get_data):
        """Test successful check."""
        mock_get_data.return_value = {
            'stoxx_current': 5180.0,
            'stoxx_open': 5170.0,
            'vix': 18.5
        }

        config = {'rules': {'vix_warn': 22, 'intraday_change_max': 1.0}}
        monitor = TradeMonitor(config)

        state = monitor._perform_check()

        assert state.trade_state == TradeState.GO
        assert state.stoxx_price == 5180.0
        assert state.vix == 18.5
        assert monitor.stats['checks_performed'] == 1

    @patch('monitor._get_market_data')
    def test_perform_check_no_go(self, mock_get_data):
        """Test check resulting in NO_GO."""
        mock_get_data.return_value = {
            'stoxx_current': 5225.0,  # Big move
            'stoxx_open': 5170.0,
            'vix': 18.5
        }

        config = {'rules': {'vix_warn': 22, 'intraday_change_max': 1.0}}
        monitor = TradeMonitor(config)

        state = monitor._perform_check()

        assert state.trade_state == TradeState.NO_GO
        assert len(state.reasons) > 0

    @patch('monitor._get_market_data')
    def test_perform_check_error(self, mock_get_data):
        """Test check with market data error."""
        from exceptions import MarketDataError
        mock_get_data.side_effect = MarketDataError("Market closed")

        config = {'rules': {'vix_warn': 22, 'intraday_change_max': 1.0}}
        monitor = TradeMonitor(config)

        state = monitor._perform_check()

        assert state.trade_state == TradeState.ERROR
        assert monitor.stats['errors'] == 1

    def test_callback_registration(self):
        """Test adding callbacks."""
        config = {'rules': {'vix_warn': 22, 'intraday_change_max': 1.0}}
        monitor = TradeMonitor(config)

        callback_called = False
        def test_callback(changes):
            nonlocal callback_called
            callback_called = True

        monitor.add_callback(test_callback)
        assert len(monitor.callbacks) == 1

    def test_get_stats(self):
        """Test statistics retrieval."""
        config = {'rules': {'vix_warn': 22, 'intraday_change_max': 1.0}}
        monitor = TradeMonitor(config)

        stats = monitor.get_stats()

        assert 'checks_performed' in stats
        assert 'state_changes' in stats
        assert 'errors' in stats

    @patch('monitor._get_market_data')
    def test_force_check(self, mock_get_data):
        """Test forced check."""
        mock_get_data.return_value = {
            'stoxx_current': 5180.0,
            'stoxx_open': 5170.0,
            'vix': 18.5
        }

        config = {'rules': {'vix_warn': 22, 'intraday_change_max': 1.0}}
        monitor = TradeMonitor(config)

        state = monitor.force_check()

        assert state is not None
        assert state.trade_state == TradeState.GO


class TestAlertManager:
    """Test AlertManager class."""

    def test_should_alert_first_time(self):
        """Test first alert should always send."""
        config = {}
        manager = AlertManager(config)

        assert manager.should_alert() is True

    def test_should_alert_cooldown(self):
        """Test alert cooldown."""
        config = {}
        manager = AlertManager(config)
        manager.alert_cooldown = 1  # 1 second for testing

        manager.last_alert_time = datetime.now()
        assert manager.should_alert() is False

        time.sleep(1.1)
        assert manager.should_alert() is True

    @patch('trade_filter.send_telegram_message')
    def test_send_alert_state_change(self, mock_send):
        """Test alert on state change."""
        config = {'telegram': {'enabled': False}}
        manager = AlertManager(config)

        changes = {
            'state_changed': True,
            'previous_state': MonitoringState(
                timestamp="2026-02-05T10:00:00",
                trade_state=TradeState.GO,
                stoxx_price=5180.0,
                stoxx_open=5170.0,
                intraday_change=0.19,
                vix=18.5,
                rules_status={},
                reasons=[]
            ),
            'current_state': MonitoringState(
                timestamp="2026-02-05T10:05:00",
                trade_state=TradeState.NO_GO,
                stoxx_price=5225.0,
                stoxx_open=5170.0,
                intraday_change=1.06,
                vix=18.5,
                rules_status={'intraday_change': 'FAIL'},
                reasons=['Trend too strong']
            ),
            'changes': [
                {'type': 'state_change', 'from': 'GO', 'to': 'NO_GO'}
            ]
        }

        manager.send_alert(changes)

        # Should update last_alert_time
        assert manager.last_alert_time is not None


class TestStartMonitoringDaemon:
    """Test daemon startup function."""

    @patch('monitor.TradeMonitor')
    @patch('monitor.AlertManager')
    def test_start_daemon(self, mock_alert_class, mock_monitor_class):
        """Test starting monitoring daemon."""
        mock_monitor = MagicMock()
        mock_monitor_class.return_value = mock_monitor

        config = {'rules': {'vix_warn': 22, 'intraday_change_max': 1.0}}
        monitor = start_monitoring_daemon(config, check_interval=60)

        mock_monitor_class.assert_called_once_with(config, 60)
        mock_monitor.start.assert_called_once()
        assert monitor == mock_monitor


class TestIntegration:
    """Integration tests for monitoring system."""

    @patch('monitor._get_market_data')
    def test_full_monitoring_cycle(self, mock_get_data):
        """Test complete monitoring cycle."""
        config = {'rules': {'vix_warn': 22, 'intraday_change_max': 1.0}}
        monitor = TradeMonitor(config, check_interval=1)

        def stop_after_first_call(*args, **kwargs):
            monitor.running = False
            return {
                'stoxx_current': 5180.0,
                'stoxx_open': 5170.0,
                'vix': 18.5
            }

        mock_get_data.side_effect = stop_after_first_call

        callback_count = 0
        def callback(changes):
            nonlocal callback_count
            callback_count += 1

        monitor.add_callback(callback)

        # Start loop — will exit after first check
        monitor.running = True
        monitor._monitor_loop()

        assert monitor.stats['checks_performed'] >= 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
