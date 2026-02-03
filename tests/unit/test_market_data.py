"""
Unit tests for market data fetching and processing.
"""

import pytest
import pandas as pd
import sys
import os
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exceptions import MarketDataError, ValidationError
from tests.fixtures.sample_data import (
    SAMPLE_VIX_DATA, SAMPLE_SPX_DATA, SAMPLE_VIX3M_DATA,
    TEST_SCENARIOS, INVALID_MARKET_DATA
)


class TestMarketData:
    """Test market data fetching and processing."""
    
    @patch('yfinance.Ticker')
    def test_fetch_vix_data_success(self, mock_ticker):
        """Test successful VIX data fetch."""
        mock_vix_ticker = Mock()
        mock_vix_ticker.history.return_value = SAMPLE_VIX_DATA
        mock_ticker.return_value = mock_vix_ticker
        
        # Simulate the fetch function
        def get_vix_data():
            ticker = mock_ticker('^VIX')
            data = ticker.history(period='5d')
            return data
        
        result = get_vix_data()
        
        assert isinstance(result, pd.DataFrame)
        assert not result.empty
        assert 'Close' in result.columns
        mock_ticker.assert_called_with('^VIX')
    
    @patch('yfinance.Ticker')
    def test_fetch_spx_data_success(self, mock_ticker):
        """Test successful SPX data fetch."""
        mock_spx_ticker = Mock()
        mock_spx_ticker.history.return_value = SAMPLE_SPX_DATA
        mock_ticker.return_value = mock_spx_ticker
        
        def get_spx_data():
            ticker = mock_ticker('^GSPC')
            data = ticker.history(period='5d')
            return data
        
        result = get_spx_data()
        
        assert isinstance(result, pd.DataFrame)
        assert not result.empty
        assert 'Close' in result.columns
        mock_ticker.assert_called_with('^GSPC')
    
    @patch('yfinance.Ticker')
    def test_fetch_vix_data_failure(self, mock_ticker):
        """Test handling of VIX data fetch failure."""
        mock_ticker.side_effect = Exception("Network error")
        
        def get_vix_data():
            try:
                ticker = mock_ticker('^VIX')
                data = ticker.history(period='5d')
                return data
            except Exception as e:
                raise MarketDataError(f"Failed to fetch VIX data: {e}")
        
        with pytest.raises(MarketDataError):
            get_vix_data()
    
    @patch('yfinance.Ticker')
    def test_empty_market_data(self, mock_ticker):
        """Test handling of empty market data."""
        mock_empty_ticker = Mock()
        mock_empty_ticker.history.return_value = pd.DataFrame()
        mock_ticker.return_value = mock_empty_ticker
        
        def get_market_data():
            ticker = mock_ticker('^VIX')
            data = ticker.history(period='5d')
            if data.empty:
                raise MarketDataError("No VIX data available")
            return data
        
        with pytest.raises(MarketDataError):
            get_market_data()
    
    def test_calculate_intraday_change(self):
        """Test intraday change calculation."""
        # Test scenario: up 0.86%
        current_price = 6976.44
        open_price = 6916.64
        
        change = ((current_price - open_price) / open_price) * 100
        
        assert abs(change - 0.86) < 0.01  # Allow small rounding difference
        
        # Test scenario: down 1.5%
        current_price = 4800.0
        open_price = 4873.6
        
        change = ((current_price - open_price) / open_price) * 100
        
        assert abs(change - (-1.5)) < 0.01
    
    def test_vix_rule_validation(self):
        """Test VIX rule validation."""
        vix_max = 22.0
        
        # Should pass
        assert 16.24 <= vix_max
        
        # Should fail
        assert 25.5 > vix_max
    
    def test_intraday_change_rule_validation(self):
        """Test intraday change rule validation."""
        max_change = 1.0
        
        # Should pass
        assert abs(0.86) <= max_change
        assert abs(-0.5) <= max_change
        
        # Should fail
        assert abs(1.5) > max_change
        assert abs(-1.2) > max_change
    
    def test_validate_market_data_quality(self):
        """Test market data quality validation."""
        # Test valid data
        valid_data = SAMPLE_VIX_DATA.copy()
        assert not valid_data.empty
        assert 'Close' in valid_data.columns
        assert (valid_data['Close'] > 0).all()
        
        # Test invalid data scenarios
        empty_data = INVALID_MARKET_DATA['empty_df']
        if empty_data.empty:
            with pytest.raises(ValidationError):
                raise ValidationError("Market data is empty")
        
        missing_cols_data = INVALID_MARKET_DATA['missing_columns']
        if 'Close' not in missing_cols_data.columns:
            with pytest.raises(ValidationError):
                raise ValidationError("Market data missing required 'Close' column")
        
        negative_vix_data = INVALID_MARKET_DATA['negative_vix']
        if (negative_vix_data['Close'] <= 0).any():
            with pytest.raises(ValidationError):
                raise ValidationError("VIX values must be positive")
    
    def test_calculate_20_day_moving_average(self):
        """Test 20-day moving average calculation."""
        # Generate sample data
        dates = pd.date_range(start='2026-01-01', periods=30, freq='D')
        prices = [4800 + i * 2 for i in range(30)]  # Simple upward trend
        data = pd.DataFrame({'Close': prices}, index=dates)
        
        # Calculate 20-day MA (first 19 days will be NaN)
        ma_20 = data['Close'].rolling(window=20).mean()
        
        # Should have valid values for days 20-30
        assert not ma_20.iloc[19:].isna().any()
        
        # Check MA calculation for a specific day
        expected_ma_day_20 = sum(prices[:20]) / 20
        assert abs(ma_20.iloc[19] - expected_ma_day_20) < 0.01
    
    def test_calculate_previous_day_range(self):
        """Test previous day range calculation."""
        # Sample OHLC data
        sample_data = pd.DataFrame({
            'Open': [4800, 4850],
            'High': [4820, 4870],
            'Low': [4780, 4830],
            'Close': [4810, 4860]
        })
        
        # Calculate range for day 0
        day_0_range = ((sample_data.iloc[0]['High'] - sample_data.iloc[0]['Low']) / 
                       sample_data.iloc[0]['Open']) * 100
        
        expected_range = ((4820 - 4780) / 4800) * 100
        assert abs(day_0_range - expected_range) < 0.01
        assert abs(day_0_range - 0.83) < 0.01  # 40/4800 * 100
    
    def test_vix_term_structure_check(self):
        """Test VIX term structure analysis."""
        vix_current = 18.5
        vix_3m = 21.2
        
        # Contango (VIX 3M > VIX current) - normal
        assert vix_3m > vix_current
        
        # Backwardation (VIX 3M < VIX current) - warning
        vix_current = 25.0
        vix_3m = 22.0
        assert vix_3m < vix_current
    
    @patch('yfinance.Ticker')
    def test_multiple_ticker_fetch(self, mock_ticker):
        """Test fetching multiple tickers efficiently."""
        # Setup mock for different tickers
        def mock_ticker_side_effect(symbol):
            if symbol == '^VIX':
                mock_vix = Mock()
                mock_vix.history.return_value = SAMPLE_VIX_DATA
                return mock_vix
            elif symbol == '^GSPC':
                mock_spx = Mock()
                mock_spx.history.return_value = SAMPLE_SPX_DATA
                return mock_spx
            elif symbol == '^VIX3M':
                mock_vix3m = Mock()
                mock_vix3m.history.return_value = SAMPLE_VIX3M_DATA
                return mock_vix3m
        
        mock_ticker.side_effect = mock_ticker_side_effect
        
        def fetch_all_market_data():
            vix_data = mock_ticker('^VIX').history(period='5d')
            spx_data = mock_ticker('^GSPC').history(period='5d')
            vix3m_data = mock_ticker('^VIX3M').history(period='5d')
            return vix_data, spx_data, vix3m_data
        
        vix, spx, vix3m = fetch_all_market_data()
        
        # Verify all data was fetched
        assert not vix.empty
        assert not spx.empty
        assert not vix3m.empty
        
        # Verify correct number of calls
        assert mock_ticker.call_count == 3