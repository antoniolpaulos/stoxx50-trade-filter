"""Tests for data_provider.py"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from data_provider import (
    MarketData,
    DataProvider,
    YahooFinanceProvider,
    AlphaVantageProvider,
    DataProviderPool,
    get_market_data
)


class TestMarketData:
    """Tests for MarketData dataclass."""

    def test_default_values(self):
        data = MarketData(stoxx_current=5000.0, stoxx_open=4990.0)
        assert data.stoxx_current == 5000.0
        assert data.stoxx_open == 4990.0
        assert data.vix is None
        assert data.prev_high is None
        assert data.source == "unknown"

    def test_with_all_values(self):
        now = datetime.now()
        data = MarketData(
            stoxx_current=5000.0,
            stoxx_open=4990.0,
            stoxx_high=5010.0,
            stoxx_low=4980.0,
            vix=18.5,
            prev_high=5020.0,
            prev_low=4970.0,
            prev_close=4995.0,
            prev_range_pct=1.0,
            ma_20=4980.0,
            source="Test Provider",
            timestamp=now
        )
        assert data.vix == 18.5
        assert data.prev_range_pct == 1.0
        assert data.ma_20 == 4980.0


class TestYahooFinanceProvider:
    """Tests for YahooFinanceProvider."""

    def test_name(self):
        provider = YahooFinanceProvider()
        assert provider.name == "Yahoo Finance"


class TestAlphaVantageProvider:
    """Tests for AlphaVantageProvider."""

    def test_name(self):
        provider = AlphaVantageProvider(api_key="test_key")
        assert provider.name == "Alpha Vantage"

    @patch('data_provider.requests.get')
    def test_get_stoxx_data(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "Time Series (Daily)": {
                "2026-02-05": {
                    "1. open": "4990.0",
                    "2. high": "5010.0",
                    "3. low": "4980.0",
                    "4. close": "5000.0",
                    "5. volume": "1000000"
                }
            }
        }
        mock_get.return_value = mock_response

        provider = AlphaVantageProvider(api_key="test_key")
        result = provider.get_stoxx_data()

        assert 'current' in result
        assert 'open' in result
        assert result['current'] == 5000.0
        assert result['open'] == 4990.0

    @patch('data_provider.requests.get')
    def test_get_vix_data(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "Global Quote": {
                "05. price": "18.5"
            }
        }
        mock_get.return_value = mock_response

        provider = AlphaVantageProvider(api_key="test_key")
        result = provider.get_vix_data()

        assert result == 18.5

    @patch('data_provider.requests.get')
    def test_rate_limit_handling(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "Note": "API rate limit reached"
        }
        mock_get.return_value = mock_response

        provider = AlphaVantageProvider(api_key="test_key")

        with pytest.raises(Exception):
            provider.get_market_data()


class TestDataProviderPool:
    """Tests for DataProviderPool."""

    @patch('data_provider.YahooFinanceProvider')
    @patch('data_provider.AlphaVantageProvider')
    def test_pool_with_providers(self, mock_av_class, mock_yf_class):
        mock_yf = Mock()
        mock_yf.is_available = True
        mock_yf_class.return_value = mock_yf

        mock_av = Mock()
        mock_av.is_available = True
        mock_av_class.return_value = mock_av

        pool = DataProviderPool()
        assert len(pool.providers) >= 1

    def test_get_best_provider(self):
        provider = YahooFinanceProvider()
        pool = DataProviderPool()
        pool._providers = [provider]

        best = pool.get_best_provider()
        assert best is not None

    @patch('data_provider.YahooFinanceProvider')
    @patch('data_provider.AlphaVantageProvider')
    def test_get_all_providers_status(self, mock_av_class, mock_yf_class):
        mock_yf = Mock()
        mock_yf.is_available = True
        type(mock_yf).name = property(lambda self: "Yahoo Finance")
        mock_yf_class.return_value = mock_yf

        mock_av = Mock()
        mock_av.is_available = False
        type(mock_av).name = property(lambda self: "Alpha Vantage")
        mock_av_class.return_value = mock_av

        pool = DataProviderPool()
        pool._providers = [mock_yf, mock_av]
        status = pool.get_all_providers_status()

        assert len(status) == 2
        assert status[0]["name"] == "Yahoo Finance"
        assert status[0]["available"] is True


class TestGetMarketDataFunction:
    """Tests for the convenience function."""

    @patch('data_provider.DataProviderPool')
    def test_get_market_data_with_provider(self, mock_pool_class):
        mock_provider = Mock()
        mock_data = MarketData(
            stoxx_current=5000.0,
            stoxx_open=4990.0,
            source="Test"
        )
        mock_provider.get_market_data.return_value = mock_data
        mock_pool_class.return_value.get_market_data.return_value = mock_data

        result = get_market_data(provider=mock_provider)

        assert result.stoxx_current == 5000.0

    @patch('data_provider.DataProviderPool')
    def test_get_market_data_with_history(self, mock_pool_class):
        mock_data = MarketData(
            stoxx_current=5000.0,
            stoxx_open=4990.0,
            prev_close=4985.0,
            ma_20=4970.0,
            source="Test"
        )
        mock_pool = Mock()
        mock_pool.get_market_data.return_value = mock_data
        mock_pool_class.return_value = mock_pool

        result = get_market_data(include_history=True)

        assert result.prev_close == 4985.0


class TestIntegration:
    """Integration tests with mocked external services."""

    @patch('data_provider.requests.get')
    def test_alpha_vantage_provider_integration(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = {
            "Time Series (Daily)": {
                "2026-02-05": {
                    "1. open": "4990.0",
                    "2. high": "5010.0",
                    "3. low": "4980.0",
                    "4. close": "5000.0",
                    "5. volume": "1000000"
                },
                "2026-02-04": {
                    "1. open": "4970.0",
                    "2. high": "4990.0",
                    "3. low": "4960.0",
                    "4. close": "4985.0",
                    "5. volume": "900000"
                }
            }
        }
        mock_get.return_value = mock_response

        provider = AlphaVantageProvider(api_key="demo")
        result = provider.get_market_data(include_history=True)

        assert result.stoxx_current == 5000.0
        assert result.prev_close == 4985.0
        assert result.prev_range_pct is not None
        assert result.source == "Alpha Vantage"
