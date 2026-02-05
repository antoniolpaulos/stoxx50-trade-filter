"""
Custom exceptions for STOXX50 Trade Filter application.
Provides specific error types for better error handling and debugging.
"""

class TradeFilterError(Exception):
    """Base exception for trade filter errors."""
    pass


class ConfigurationError(TradeFilterError):
    """Raised when configuration is invalid or missing."""
    pass


class MarketDataError(TradeFilterError):
    """Raised when market data fetch fails or is invalid."""
    pass


class CalendarAPIError(TradeFilterError):
    """Raised when economic calendar API fails."""
    pass


class TelegramError(TradeFilterError):
    """Raised when Telegram notification fails."""
    pass


class ValidationError(TradeFilterError):
    """Raised when data validation fails."""
    pass


class NetworkError(TradeFilterError):
    """Raised when network connectivity issues occur."""
    pass


class PortfolioError(TradeFilterError):
    """Raised when portfolio operations fail."""
    pass