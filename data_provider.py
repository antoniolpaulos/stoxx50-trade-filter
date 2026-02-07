"""
Multi-Source Data Provider for STOXX50 Trade Filter
Provides unified interface for fetching market data from multiple sources.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, date, timedelta

from exceptions import MarketDataError


@dataclass
class MarketData:
    """Unified market data container."""
    stoxx_current: float
    stoxx_open: float
    stoxx_high: Optional[float] = None
    stoxx_low: Optional[float] = None
    vix: Optional[float] = None
    prev_high: Optional[float] = None
    prev_low: Optional[float] = None
    prev_close: Optional[float] = None
    prev_range_pct: Optional[float] = None
    ma_20: Optional[float] = None
    source: str = "unknown"
    timestamp: Optional[datetime] = None


class DataProvider(ABC):
    """Abstract base class for data providers."""

    @abstractmethod
    def get_market_data(self, include_history: bool = False) -> MarketData:
        """Fetch current market data."""
        pass

    @abstractmethod
    def get_stoxx_data(self) -> Dict[str, float]:
        """Fetch STOXX50 data only."""
        pass

    @abstractmethod
    def get_vix_data(self) -> Optional[float]:
        """Fetch VIX data only."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available."""
        pass


class YahooFinanceProvider(DataProvider):
    """Yahoo Finance data provider (primary)."""

    STOXX_TICKER = "^STOXX50E"
    VIX_TICKER = "^VIX"

    def __init__(self):
        self._stoxx = yf.Ticker(self.STOXX_TICKER)
        self._vix = yf.Ticker(self.VIX_TICKER)

    @property
    def name(self) -> str:
        return "Yahoo Finance"

    @property
    def is_available(self) -> bool:
        try:
            yf.Ticker(self.STOXX_TICKER).info
            return True
        except Exception:
            return False

    def get_market_data(self, include_history: bool = False) -> MarketData:
        try:
            stoxx_data = self._stoxx.history(period="1d")
            vix_data = self._vix.history(period="5d")

            if stoxx_data.empty:
                raise MarketDataError("Unable to fetch STOXX50 data. Market may be closed.")

            result = MarketData(
                stoxx_current=stoxx_data['Close'].iloc[-1],
                stoxx_open=stoxx_data['Open'].iloc[-1],
                stoxx_high=stoxx_data['High'].iloc[-1] if 'High' in stoxx_data else None,
                stoxx_low=stoxx_data['Low'].iloc[-1] if 'Low' in stoxx_data else None,
                vix=vix_data['Close'].iloc[-1] if not vix_data.empty else None,
                source="Yahoo Finance",
                timestamp=datetime.now()
            )

            if include_history:
                stoxx_extended = self._stoxx.history(period="1mo")
                if len(stoxx_extended) >= 2:
                    prev_day = stoxx_extended.iloc[-2]
                    result.prev_high = prev_day['High']
                    result.prev_low = prev_day['Low']
                    result.prev_close = prev_day['Close']
                    result.prev_range_pct = ((prev_day['High'] - prev_day['Low']) / prev_day['Close']) * 100

                if len(stoxx_extended) >= 20:
                    result.ma_20 = stoxx_extended['Close'].tail(20).mean()
                elif len(stoxx_extended) >= 5:
                    result.ma_20 = stoxx_extended['Close'].mean()

            return result

        except Exception as e:
            raise MarketDataError(f"Yahoo Finance error: {e}")

    def get_stoxx_data(self) -> Dict[str, float]:
        data = self.get_market_data()
        return {
            'current': data.stoxx_current,
            'open': data.stoxx_open
        }

    def get_vix_data(self) -> Optional[float]:
        try:
            vix_data = self._vix.history(period="5d")
            return vix_data['Close'].iloc[-1] if not vix_data.empty else None
        except Exception:
            return None


class AlphaVantageProvider(DataProvider):
    """Alpha Vantage data provider (backup, free tier: 25 requests/day)."""

    BASE_URL = "https://www.alphavantage.co/query"

    STOXX_SYMBOL = "STOXX50"
    VIX_SYMBOL = "VIXCLS"

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or "demo"
        if api_key is None:
            self._api_key = "demo"

    @property
    def name(self) -> str:
        return "Alpha Vantage"

    @property
    def is_available(self) -> bool:
        try:
            response = requests.get(
                self.BASE_URL,
                params={
                    "function": "TIME_SERIES_DAILY",
                    "symbol": self.STOXX_SYMBOL,
                    "apikey": self._api_key
                },
                timeout=10
            )
            data = response.json()
            return "Time Series (Daily)" in data or "Note" not in data
        except Exception:
            return False

    def _parse_alpha_vantage_response(self, data: Dict[str, Any]) -> Dict[str, float]:
        """Parse Alpha Vantage daily response."""
        time_series = data.get("Time Series (Daily)", {})
        if not time_series:
            raise MarketDataError("No data returned from Alpha Vantage")

        latest_date = sorted(time_series.keys())[-1]
        day_data = time_series[latest_date]

        return {
            'date': latest_date,
            'open': float(day_data['1. open']),
            'high': float(day_data['2. high']),
            'low': float(day_data['3. low']),
            'close': float(day_data['4. close']),
            'volume': int(day_data['5. volume'])
        }

    def get_market_data(self, include_history: bool = False) -> MarketData:
        try:
            stoxx_response = requests.get(
                self.BASE_URL,
                params={
                    "function": "TIME_SERIES_DAILY",
                    "symbol": self.STOXX_SYMBOL,
                    "apikey": self._api_key
                },
                timeout=10
            )
            stoxx_data = stoxx_response.json()

            if "Note" in stoxx_data:
                raise MarketDataError("Alpha Vantage API rate limit reached")
            if "Error Message" in stoxx_data:
                raise MarketDataError("Alpha Vantage: invalid symbol")

            parsed_stoxx = self._parse_alpha_vantage_response(stoxx_data)

            result = MarketData(
                stoxx_current=parsed_stoxx['close'],
                stoxx_open=parsed_stoxx['open'],
                stoxx_high=parsed_stoxx['high'],
                stoxx_low=parsed_stoxx['low'],
                source="Alpha Vantage",
                timestamp=datetime.now()
            )

            if include_history:
                time_series = stoxx_data.get("Time Series (Daily)", {})
                dates = sorted(time_series.keys())

                if len(dates) >= 2:
                    prev_day_data = time_series[dates[-2]]
                    result.prev_high = float(prev_day_data['2. high'])
                    result.prev_low = float(prev_day_data['3. low'])
                    result.prev_close = float(prev_day_data['4. close'])
                    result.prev_range_pct = (
                        (result.prev_high - result.prev_low) / result.prev_close * 100
                    )

                closes = [
                    float(time_series[d]['4. close'])
                    for d in dates[-20:]
                    if d in time_series
                ]
                if len(closes) >= 20:
                    result.ma_20 = sum(closes[-20:]) / 20
                elif closes:
                    result.ma_20 = sum(closes) / len(closes)

            vix_response = requests.get(
                self.BASE_URL,
                params={
                    "function": "GLOBAL_QUOTE",
                    "symbol": self.VIX_SYMBOL,
                    "apikey": self._api_key
                },
                timeout=10
            )
            vix_data = vix_response.json()
            if "Global Quote" in vix_data and vix_data["Global Quote"]:
                result.vix = float(vix_data["Global Quote"]["05. price"])

            return result

        except requests.exceptions.RequestException as e:
            raise MarketDataError(f"Alpha Vantage network error: {e}")
        except (KeyError, ValueError) as e:
            raise MarketDataError(f"Alpha Vantage parsing error: {e}")

    def get_stoxx_data(self) -> Dict[str, float]:
        data = self.get_market_data()
        return {
            'current': data.stoxx_current,
            'open': data.stoxx_open
        }

    def get_vix_data(self) -> Optional[float]:
        try:
            response = requests.get(
                self.BASE_URL,
                params={
                    "function": "GLOBAL_QUOTE",
                    "symbol": self.VIX_SYMBOL,
                    "apikey": self._api_key
                },
                timeout=10
            )
            data = response.json()
            if "Global Quote" in data and data["Global Quote"]:
                return float(data["Global Quote"]["05. price"])
            return None
        except Exception:
            return None


def get_historical_data(start_date: str, end_date: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch historical VIX and Euro Stoxx 50 data.

    Note: VSTOXX (V2TX.DE) is unavailable via yfinance, so we use VIX as a proxy.
    VIX is used as a warning indicator only, not a blocking rule.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Tuple of (vix_data, stoxx_data) DataFrames
    """
    buffer_start = (datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=5)).strftime('%Y-%m-%d')
    buffer_end = (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=5)).strftime('%Y-%m-%d')

    vix = yf.Ticker("^VIX")
    stoxx = yf.Ticker("^STOXX50E")

    vix_data = vix.history(start=buffer_start, end=buffer_end)
    stoxx_data = stoxx.history(start=buffer_start, end=buffer_end)

    return vix_data, stoxx_data


def get_market_data(
    include_history: bool = False,
    provider: Optional[DataProvider] = None,
    api_key: Optional[str] = None
) -> MarketData:
    """Fetch market data, trying Yahoo Finance first then Alpha Vantage.

    Args:
        include_history: Include historical data (MA, previous day, etc.)
        provider: Specific provider to use (if None, tries Yahoo then Alpha Vantage)
        api_key: Alpha Vantage API key (optional)

    Returns:
        MarketData object with all available data
    """
    if provider is not None:
        return provider.get_market_data(include_history)

    # Try Yahoo Finance first
    try:
        return YahooFinanceProvider().get_market_data(include_history)
    except MarketDataError:
        pass

    # Fall back to Alpha Vantage
    try:
        return AlphaVantageProvider(api_key).get_market_data(include_history)
    except MarketDataError:
        pass

    raise MarketDataError("All data providers failed")
