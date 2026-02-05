"""
Unit tests for the logging system.
"""

import pytest
import logging
import json
import tempfile
from pathlib import Path
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger import TradeFilterLogger, get_logger, reset_logger


class TestTradeFilterLogger:
    """Test the TradeFilterLogger class."""

    def test_logger_creation(self):
        """Test logger instance creation."""
        logger = TradeFilterLogger()
        assert logger.name == "trade_filter"
        assert logger.logger is not None

    def test_logger_setup(self, tmp_path):
        """Test logger setup with configuration."""
        logger = TradeFilterLogger()
        config = {
            'logging': {
                'level': 'DEBUG',
                'log_dir': str(tmp_path)
            }
        }

        logger.setup(config, log_dir=tmp_path)

        # Check that log directory was created
        assert tmp_path.exists()

        # Check that handlers were added
        assert len(logger.logger.handlers) > 0

    def test_logging_levels(self, tmp_path):
        """Test different logging levels."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'DEBUG'}}
        logger.setup(config, log_dir=tmp_path)

        # These should not raise exceptions
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

    def test_log_evaluation(self, tmp_path):
        """Test evaluation logging."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'INFO'}}
        logger.setup(config, log_dir=tmp_path)

        data = {
            'stoxx_current': 5180.0,
            'stoxx_open': 5170.0,
            'vix': 18.5,
            'intraday_change': 0.19
        }

        logger.log_evaluation("GO", data)
        logger.log_evaluation("NO GO", data, reasons=["VIX too high", "Trend too strong"])

        # Should not raise exceptions

    def test_log_trade_entry(self, tmp_path):
        """Test trade entry logging."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'INFO'}}
        logger.setup(config, log_dir=tmp_path)

        trade_info = {
            'date': '2026-02-05',
            'stoxx_entry': 5180.0,
            'call_strike': 5232,
            'put_strike': 5128,
            'wing_width': 50,
            'credit': 2.50
        }

        logger.log_trade_entry("always_trade", trade_info)
        logger.log_trade_entry("filtered", trade_info)

    def test_log_trade_settlement(self, tmp_path):
        """Test trade settlement logging."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'INFO'}}
        logger.setup(config, log_dir=tmp_path)

        # Win
        logger.log_trade_settlement("always_trade", 25.0, 5200.0)

        # Loss
        logger.log_trade_settlement("filtered", -175.0, 5130.0)

    def test_log_market_data_fetch(self, tmp_path):
        """Test market data fetch logging."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'DEBUG'}}
        logger.setup(config, log_dir=tmp_path)

        # Success
        data = {'stoxx_current': 5180.0, 'vix': 18.5}
        logger.log_market_data_fetch(True, data)

        # Failure
        logger.log_market_data_fetch(False, error="Network timeout")

    def test_log_calendar_check(self, tmp_path):
        """Test calendar check logging."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'INFO'}}
        logger.setup(config, log_dir=tmp_path)

        # No events
        logger.log_calendar_check(False)

        # With events
        events = [{'name': 'ECB Rate Decision', 'time': '14:15'}]
        logger.log_calendar_check(True, events)

        # With error
        logger.log_calendar_check(False, error="API timeout")

    def test_log_telegram_notification(self, tmp_path):
        """Test Telegram notification logging."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'INFO'}}
        logger.setup(config, log_dir=tmp_path)

        # Success
        logger.log_telegram_notification(True)

        # Failure
        logger.log_telegram_notification(False, error="Invalid token")

    def test_log_portfolio_summary(self, tmp_path):
        """Test portfolio summary logging."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'INFO'}}
        logger.setup(config, log_dir=tmp_path)

        summary = {
            'always_trade': {
                'total_pnl': 100.0,
                'trade_count': 10,
                'win_count': 7
            },
            'filtered': {
                'total_pnl': 150.0,
                'trade_count': 5,
                'win_count': 4
            },
            'filter_edge': 50.0
        }

        logger.log_portfolio_summary(summary)

    def test_log_config_load(self, tmp_path):
        """Test config load logging."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'INFO'}}
        logger.setup(config, log_dir=tmp_path)

        # Success
        logger.log_config_load(tmp_path / "config.yaml", True)

        # Failure
        logger.log_config_load(tmp_path / "config.yaml", False, error="File not found")


class TestGlobalLogger:
    """Test global logger functions."""

    def setup_method(self):
        """Reset logger before each test."""
        reset_logger()

    def test_get_logger_singleton(self, tmp_path):
        """Test that get_logger returns singleton."""
        config = {'logging': {'level': 'INFO'}}

        logger1 = get_logger(config, tmp_path)
        logger2 = get_logger(config, tmp_path)

        assert logger1 is logger2

    def test_get_logger_without_config(self):
        """Test get_logger without config."""
        reset_logger()
        logger = get_logger()

        assert logger is not None

    def test_convenience_functions(self, tmp_path):
        """Test module-level convenience functions."""
        from logger import debug, info, warning, error

        config = {'logging': {'level': 'DEBUG'}}
        get_logger(config, tmp_path)

        # These should not raise exceptions
        debug("Debug test")
        info("Info test")
        warning("Warning test")
        error("Error test")


class TestLogFileOutput:
    """Test actual log file output."""

    def test_log_files_created(self, tmp_path):
        """Test that log files are created."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'DEBUG'}}
        logger.setup(config, log_dir=tmp_path)

        logger.info("Test message")

        # Check that main log file exists
        log_file = tmp_path / "trade_filter.log"
        assert log_file.exists()

        # Check content
        content = log_file.read_text()
        assert "Test message" in content

    def test_trade_log_separation(self, tmp_path):
        """Test that trade logs go to separate file."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'INFO'}}
        logger.setup(config, log_dir=tmp_path)

        # Regular log
        logger.info("Regular info message")

        # Trade log
        data = {'stoxx_current': 5180.0, 'intraday_change': 0.19}
        logger.log_evaluation("GO", data)

        # Check files
        app_log = tmp_path / "trade_filter.log"
        trade_log = tmp_path / "trades.log"

        assert app_log.exists()
        assert trade_log.exists()

    def test_error_log_separation(self, tmp_path):
        """Test that errors go to separate file."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'DEBUG'}}
        logger.setup(config, log_dir=tmp_path)

        logger.error("Test error message")

        error_log = tmp_path / "errors.log"
        assert error_log.exists()

        content = error_log.read_text()
        assert "Test error message" in content


class TestLoggerConfiguration:
    """Test logger configuration options."""

    def test_default_level(self, tmp_path):
        """Test default logging level."""
        logger = TradeFilterLogger()
        logger.setup(log_dir=tmp_path)

        assert logger.logger.level == logging.INFO

    def test_debug_level(self, tmp_path):
        """Test debug logging level."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'DEBUG'}}
        logger.setup(config, log_dir=tmp_path)

        assert logger.logger.level == logging.DEBUG

    def test_warning_level(self, tmp_path):
        """Test warning logging level."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'WARNING'}}
        logger.setup(config, log_dir=tmp_path)

        assert logger.logger.level == logging.WARNING

    def test_invalid_level_defaults_to_info(self, tmp_path):
        """Test that invalid level defaults to INFO."""
        logger = TradeFilterLogger()
        config = {'logging': {'level': 'INVALID'}}
        logger.setup(config, log_dir=tmp_path)

        assert logger.logger.level == logging.INFO
