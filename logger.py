"""
Logging system for STOXX50 Trade Filter.
Provides structured logging with rotation and trade history tracking.
"""

import logging
import logging.handlers
import json
from pathlib import Path
from datetime import datetime, date
from typing import Dict, Any, Optional
import sys

# Default paths
DEFAULT_LOG_PATH = Path(__file__).parent / "logs"
DEFAULT_TRADE_LOG = DEFAULT_LOG_PATH / "trades.log"
DEFAULT_APP_LOG = DEFAULT_LOG_PATH / "trade_filter.log"

# Log formatters
DETAILED_FORMATTER = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

SIMPLE_FORMATTER = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

TRADE_FORMATTER = logging.Formatter(
    '%(asctime)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class TradeFilterLogger:
    """Custom logger for trade filter with separate trade history tracking."""
    
    def __init__(self, name: str = "trade_filter"):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self._handlers = []
        
        # Prevent duplicate handlers
        if self.logger.handlers:
            self.logger.handlers.clear()
    
    def setup(self, config: Optional[Dict[str, Any]] = None, 
              log_dir: Optional[Path] = None,
              log_level: str = "INFO"):
        """
        Setup logging with configuration.
        
        Args:
            config: Configuration dict with logging settings
            log_dir: Directory for log files (default: ./logs)
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        # Get settings from config if provided
        if config and 'logging' in config:
            log_config = config['logging']
            log_level = log_config.get('level', log_level)
        
        # Set log directory
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = DEFAULT_LOG_PATH
        
        self.log_dir.mkdir(exist_ok=True)
        
        # Parse log level
        level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger.setLevel(level)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Setup handlers
        self._setup_file_handler(level)
        self._setup_console_handler(level)
        self._setup_trade_history_handler()
        self._setup_error_handler()
        
        self.logger.info(f"Logging initialized - Level: {log_level}, Dir: {self.log_dir}")
    
    def _setup_file_handler(self, level: int):
        """Setup main application log file with rotation."""
        log_file = self.log_dir / "trade_filter.log"
        
        # Rotate daily, keep 30 days
        handler = logging.handlers.TimedRotatingFileHandler(
            log_file,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        handler.setLevel(level)
        handler.setFormatter(DETAILED_FORMATTER)
        handler.suffix = "%Y-%m-%d"
        
        self.logger.addHandler(handler)
        self._handlers.append(handler)
    
    def _setup_console_handler(self, level: int):
        """Setup console output."""
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(SIMPLE_FORMATTER)
        self.logger.addHandler(handler)
        self._handlers.append(handler)
    
    def _setup_trade_history_handler(self):
        """Setup separate trade history log."""
        trade_log = self.log_dir / "trades.log"
        
        handler = logging.handlers.TimedRotatingFileHandler(
            trade_log,
            when='midnight',
            interval=1,
            backupCount=90,  # Keep 90 days of trade history
            encoding='utf-8'
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(TRADE_FORMATTER)
        handler.suffix = "%Y-%m-%d"
        
        # Create a filter to only log trade messages
        class TradeFilter(logging.Filter):
            def filter(self, record):
                return hasattr(record, 'is_trade_log') and record.is_trade_log
        
        handler.addFilter(TradeFilter())
        self.logger.addHandler(handler)
        self._handlers.append(handler)
    
    def _setup_error_handler(self):
        """Setup separate error log for easy monitoring."""
        error_log = self.log_dir / "errors.log"
        
        handler = logging.handlers.TimedRotatingFileHandler(
            error_log,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        handler.setLevel(logging.ERROR)
        handler.setFormatter(DETAILED_FORMATTER)
        handler.suffix = "%Y-%m-%d"
        
        self.logger.addHandler(handler)
        self._handlers.append(handler)
    
    # Logging methods
    def debug(self, msg: str, *args, **kwargs):
        """Log debug message."""
        self.logger.debug(msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        """Log info message."""
        self.logger.info(msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        """Log warning message."""
        self.logger.warning(msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        """Log error message."""
        self.logger.error(msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        """Log exception with traceback."""
        self.logger.exception(msg, *args, **kwargs)
    
    # Trade-specific logging
    def log_evaluation(self, result: str, data: Dict[str, Any], reasons: list = None):
        """
        Log trade evaluation result.
        
        Args:
            result: "GO" or "NO GO"
            data: Market data dict
            reasons: List of reasons for NO GO
        """
        trade_data = {
            'timestamp': datetime.now().isoformat(),
            'type': 'evaluation',
            'result': result,
            'stoxx_current': data.get('stoxx_current'),
            'stoxx_open': data.get('stoxx_open'),
            'vix': data.get('vix'),
            'intraday_change': data.get('intraday_change'),
            'reasons': reasons or []
        }
        
        # Log to trade history
        record = self.logger.makeRecord(
            self.name, logging.INFO, "", 0,
            json.dumps(trade_data), (), None
        )
        record.is_trade_log = True
        self.logger.handle(record)
        
        # Also log to main log
        self.info(f"Trade evaluation: {result} - STOXX: {data.get('stoxx_current')}, "
                 f"Change: {data.get('intraday_change'):.2f}%")
    
    def log_trade_entry(self, portfolio: str, trade_info: Dict[str, Any]):
        """
        Log trade entry.
        
        Args:
            portfolio: Portfolio name (always_trade/filtered)
            trade_info: Trade details
        """
        trade_data = {
            'timestamp': datetime.now().isoformat(),
            'type': 'entry',
            'portfolio': portfolio,
            'date': trade_info.get('date'),
            'stoxx_entry': trade_info.get('stoxx_entry'),
            'call_strike': trade_info.get('call_strike'),
            'put_strike': trade_info.get('put_strike'),
            'wing_width': trade_info.get('wing_width'),
            'credit': trade_info.get('credit')
        }
        
        record = self.logger.makeRecord(
            self.name, logging.INFO, "", 0,
            f"ENTRY | {portfolio} | {trade_info.get('date')} | "
            f"STOXX: {trade_info.get('stoxx_entry'):.0f} | "
            f"P:{trade_info.get('put_strike')} C:{trade_info.get('call_strike')} | "
            f"Credit: {trade_info.get('credit')}",
            (), None
        )
        record.is_trade_log = True
        self.logger.handle(record)
        
        self.info(f"Trade entry recorded for {portfolio}: {trade_info.get('date')}")
    
    def log_trade_settlement(self, portfolio: str, pnl: float, stoxx_close: float):
        """
        Log trade settlement.
        
        Args:
            portfolio: Portfolio name
            pnl: Profit/loss amount
            stoxx_close: Closing price
        """
        trade_data = {
            'timestamp': datetime.now().isoformat(),
            'type': 'settlement',
            'portfolio': portfolio,
            'pnl': pnl,
            'stoxx_close': stoxx_close,
            'outcome': 'win' if pnl > 0 else 'loss'
        }
        
        record = self.logger.makeRecord(
            self.name, logging.INFO, "", 0,
            f"SETTLE | {portfolio} | Close: {stoxx_close:.0f} | P&L: {pnl:+.0f} EUR",
            (), None
        )
        record.is_trade_log = True
        self.logger.handle(record)
        
        outcome = "WIN" if pnl > 0 else "LOSS"
        self.info(f"Trade settlement for {portfolio}: {outcome} - P&L: {pnl:+.0f} EUR")
    
    def log_market_data_fetch(self, success: bool, data: Dict[str, Any] = None, error: str = None):
        """Log market data fetch attempt."""
        if success:
            self.debug(f"Market data fetched - STOXX: {data.get('stoxx_current')}, "
                      f"VIX: {data.get('vix')}")
        else:
            self.error(f"Market data fetch failed: {error}")
    
    def log_calendar_check(self, has_events: bool, events: list = None, error: str = None):
        """Log economic calendar check."""
        if error:
            self.warning(f"Calendar check error: {error}")
        elif has_events:
            event_names = ', '.join([e.get('name', 'Unknown') for e in (events or [])])
            self.info(f"Calendar: High-impact events found - {event_names}")
        else:
            self.debug("Calendar: No high-impact events today")
    
    def log_telegram_notification(self, success: bool, error: str = None):
        """Log Telegram notification attempt."""
        if success:
            self.debug("Telegram notification sent successfully")
        else:
            self.warning(f"Telegram notification failed: {error}")
    
    def log_portfolio_summary(self, summary: Dict[str, Any]):
        """Log portfolio summary."""
        always = summary.get('always_trade', {})
        filtered = summary.get('filtered', {})
        edge = summary.get('filter_edge', 0)
        
        self.info(f"Portfolio Summary - Always: {always.get('total_pnl', 0):+.0f} EUR "
                 f"({always.get('trade_count', 0)} trades), "
                 f"Filtered: {filtered.get('total_pnl', 0):+.0f} EUR "
                 f"({filtered.get('trade_count', 0)} trades), "
                 f"Edge: {edge:+.0f} EUR")
    
    def log_config_load(self, config_path: Path, success: bool, error: str = None):
        """Log configuration load."""
        if success:
            self.debug(f"Configuration loaded from {config_path}")
        else:
            self.error(f"Configuration load failed: {error}")
    
    def get_logger(self) -> logging.Logger:
        """Get the underlying logger instance."""
        return self.logger


# Global logger instance
_logger: Optional[TradeFilterLogger] = None


def get_logger(config: Optional[Dict[str, Any]] = None, 
               log_dir: Optional[Path] = None) -> TradeFilterLogger:
    """
    Get or create the global logger instance.
    
    Args:
        config: Configuration dict
        log_dir: Directory for log files
        
    Returns:
        TradeFilterLogger instance
    """
    global _logger
    
    if _logger is None:
        _logger = TradeFilterLogger()
        if config:
            _logger.setup(config, log_dir)
    
    return _logger


def reset_logger():
    """Reset the global logger (useful for testing)."""
    global _logger
    _logger = None


# Convenience functions for module-level imports
def debug(msg: str, *args, **kwargs):
    """Log debug message using global logger."""
    if _logger:
        _logger.debug(msg, *args, **kwargs)


def info(msg: str, *args, **kwargs):
    """Log info message using global logger."""
    if _logger:
        _logger.info(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs):
    """Log warning message using global logger."""
    if _logger:
        _logger.warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs):
    """Log error message using global logger."""
    if _logger:
        _logger.error(msg, *args, **kwargs)


def exception(msg: str, *args, **kwargs):
    """Log exception using global logger."""
    if _logger:
        _logger.exception(msg, *args, **kwargs)
