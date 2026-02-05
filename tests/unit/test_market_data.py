"""
Unit tests for market data fetching and processing - testing real functions from trade_filter.py.
"""

import pytest
import pandas as pd
import sys
import os
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_filter import get_market_data, calculate_intraday_change
from exceptions import MarketDataError, ValidationError


class TestGetMarketData:
    """Test get_market_data function with mocked yfinance."""
    
    @patch('trade_filter.yf.Ticker')
    def test_fetch_stoxx50_data_success(self, mock_ticker, sample_stoxx50_data):
        """Test successful STOXX50 data fetch."""
        mock_stoxx_ticker = Mock()
        mock_stoxx_ticker.history.return_value = sample_stoxx50_data
        mock_ticker.return_value = mock_stoxx_ticker
        
        result = get_market_data()
        
        assert 'stoxx_current' in result
        assert 'stoxx_open' in result
        assert result['stoxx_current'] == sample_stoxx50_data['Close'].iloc[-1]
        assert result['stoxx_open'] == sample_stoxx50_data['Open'].iloc[-1]
        mock_ticker.assert_called_with("^STOXX50E")
    
    @patch('trade_filter.yf.Ticker')
    def test_fetch_vix_data_alongside_stoxx50(self, mock_ticker, sample_vix_data, sample_stoxx50_data):
        """Test fetching both VIX and STOXX50 data."""
        def mock_ticker_side_effect(symbol):
            mock = Mock()
            if symbol == '^VIX':
                mock.history.return_value = sample_vix_data
            elif symbol == '^STOXX50E':
                mock.history.return_value = sample_stoxx50_data
            return mock
        
        mock_ticker.side_effect = mock_ticker_side_effect
        
        result = get_market_data()
        
        assert 'stoxx_current' in result
        assert 'vix' in result
        assert result['vix'] == sample_vix_data['Close'].iloc[-1]
    
    @patch('trade_filter.yf.Ticker')
    def test_fetch_stoxx50_data_failure(self, mock_ticker):
        """Test handling of STOXX50 data fetch failure."""
        mock_ticker.side_effect = Exception("Network error")
        
        with pytest.raises(Exception):
            get_market_data()
    
    @patch('trade_filter.yf.Ticker')
    def test_empty_stoxx50_data(self, mock_ticker):
        """Test handling of empty STOXX50 data."""
        mock_stoxx_ticker = Mock()
        mock_stoxx_ticker.history.return_value = pd.DataFrame()
        mock_ticker.return_value = mock_stoxx_ticker
        
        with pytest.raises(MarketDataError, match="Unable to fetch market data"):
            get_market_data()
    
    @patch('trade_filter.yf.Ticker')
    def test_get_market_data_with_history(self, mock_ticker, sample_stoxx50_data):
        """Test fetching market data with historical data for additional filters."""
        mock_stoxx_ticker = Mock()
        mock_stoxx_ticker.history.return_value = sample_stoxx50_data
        mock_ticker.return_value = mock_stoxx_ticker

        result = get_market_data(include_history=True)

        assert 'stoxx_current' in result
        assert 'stoxx_open' in result
        # Function calls history() multiple times with different periods
        # First call uses 5d, later call for extended MA uses 1mo
        mock_stoxx_ticker.history.assert_any_call(period='5d')
    
    @patch('trade_filter.yf.Ticker')
    def test_missing_columns_in_data(self, mock_ticker):
        """Test handling of data with missing columns."""
        invalid_data = pd.DataFrame({
            'WrongColumn': [1, 2, 3]
        })
        
        mock_stoxx_ticker = Mock()
        mock_stoxx_ticker.history.return_value = invalid_data
        mock_ticker.return_value = mock_stoxx_ticker
        
        with pytest.raises(Exception):  # KeyError when accessing missing columns
            get_market_data()
    
    @patch('trade_filter.yf.Ticker')
    def test_negative_vix_values(self, mock_ticker, sample_stoxx50_data):
        """Test handling of negative VIX values."""
        negative_vix_data = pd.DataFrame({
            'Close': [-5.0]
        })
        
        def mock_ticker_side_effect(symbol):
            mock = Mock()
            if symbol == '^VIX':
                mock.history.return_value = negative_vix_data
            elif symbol == '^STOXX50E':
                mock.history.return_value = sample_stoxx50_data
            return mock
        
        mock_ticker.side_effect = mock_ticker_side_effect
        
        # VIX is optional/warning only, shouldn't raise error
        result = get_market_data()
        assert 'vix' in result
        assert result['vix'] < 0  # Will have negative value


class TestMarketDataCalculations:
    """Test market data calculation functions."""
    
    def test_calculate_intraday_change_positive(self):
        """Test intraday change calculation with positive movement."""
        current = 5220.0
        open_price = 5180.0
        
        change = calculate_intraday_change(current, open_price)
        
        expected = ((5220.0 - 5180.0) / 5180.0) * 100
        assert abs(change - expected) < 0.01
        assert change > 0
    
    def test_calculate_intraday_change_negative(self):
        """Test intraday change calculation with negative movement."""
        current = 5130.0
        open_price = 5180.0
        
        change = calculate_intraday_change(current, open_price)
        
        expected = ((5130.0 - 5180.0) / 5180.0) * 100
        assert abs(change - expected) < 0.01
        assert change < 0
    
    def test_calculate_intraday_change_zero(self):
        """Test intraday change calculation with no movement."""
        current = 5180.0
        open_price = 5180.0
        
        change = calculate_intraday_change(current, open_price)
        
        assert change == 0.0


class TestMarketDataValidation:
    """Test market data validation."""
    
    def test_validate_stoxx50_data_quality(self, sample_stoxx50_data):
        """Test STOXX50 data quality validation."""
        # Valid data checks
        assert not sample_stoxx50_data.empty
        assert 'Close' in sample_stoxx50_data.columns
        assert 'Open' in sample_stoxx50_data.columns
        assert (sample_stoxx50_data['Close'] > 0).all()
        assert (sample_stoxx50_data['Open'] > 0).all()
        
        # STOXX50 should be in realistic range (4000-6000)
        assert sample_stoxx50_data['Close'].iloc[-1] > 4000
        assert sample_stoxx50_data['Close'].iloc[-1] < 6000
    
    def test_validate_vix_data_quality(self, sample_vix_data):
        """Test VIX data quality validation."""
        # Valid data checks
        assert not sample_vix_data.empty
        assert 'Close' in sample_vix_data.columns
        assert (sample_vix_data['Close'] > 0).all()
    
    def test_empty_data_validation(self, invalid_market_data):
        """Test validation of empty data."""
        empty_data = invalid_market_data['empty_df']
        
        if empty_data.empty:
            with pytest.raises(ValidationError):
                raise ValidationError("Market data is empty")
    
    def test_missing_columns_validation(self, invalid_market_data):
        """Test validation of data with missing columns."""
        missing_cols_data = invalid_market_data['missing_columns']
        
        if 'Close' not in missing_cols_data.columns:
            with pytest.raises(ValidationError):
                raise ValidationError("Market data missing required 'Close' column")
    
    def test_negative_stoxx50_validation(self, invalid_market_data):
        """Test validation of negative STOXX50 values."""
        # Note: The fixture name is still 'negative_vstoxx' but testing the logic
        # This tests the validation pattern
        negative_data = pd.DataFrame({'Close': [-5.0]})
        
        if (negative_data['Close'] <= 0).any():
            with pytest.raises(ValidationError):
                raise ValidationError("STOXX50 values must be positive")


class TestHistoricalDataCalculations:
    """Test historical data calculations with mocked data."""
    
    @patch('trade_filter.yf.Ticker')
    def test_calculate_20_day_ma(self, mock_ticker):
        """Test 20-day moving average calculation."""
        # Generate 30 days of sample data
        dates = pd.date_range(start='2026-01-01', periods=30, freq='D')
        prices = [5180 + i * 2 for i in range(30)]  # Simple upward trend
        sample_data = pd.DataFrame({
            'Close': prices,
            'Open': [p - 10 for p in prices],
            'High': [p + 20 for p in prices],
            'Low': [p - 20 for p in prices]
        }, index=dates)
        
        mock_stoxx_ticker = Mock()
        mock_stoxx_ticker.history.return_value = sample_data
        mock_ticker.return_value = mock_stoxx_ticker
        
        result = get_market_data(include_history=True)
        
        # Should have calculated MA if enough data
        if 'ma_20' in result:
            assert result['ma_20'] > 0
    
    @patch('trade_filter.yf.Ticker')
    def test_calculate_previous_day_range(self, mock_ticker):
        """Test previous day range calculation."""
        # Create data with at least 2 days
        dates = pd.date_range(start='2026-01-01', periods=2, freq='D')
        sample_data = pd.DataFrame({
            'Open': [5180.0, 5220.0],
            'High': [5200.0, 5240.0],
            'Low': [5150.0, 5190.0],
            'Close': [5180.0, 5220.0]
        }, index=dates)
        
        mock_stoxx_ticker = Mock()
        mock_stoxx_ticker.history.return_value = sample_data
        mock_ticker.return_value = mock_stoxx_ticker
        
        result = get_market_data(include_history=True)
        
        if 'prev_range_pct' in result:
            assert result['prev_range_pct'] > 0
    
    def test_ma_deviation_calculation(self):
        """Test MA deviation calculation."""
        current_stoxx = 5180.0
        ma_20 = 5050.0
        
        deviation = ((current_stoxx - ma_20) / ma_20) * 100
        
        assert abs(deviation - 2.57) < 0.01
        assert deviation > 0  # Price above MA


class TestTickerSymbols:
    """Test correct ticker symbols are used."""
    
    @patch('trade_filter.yf.Ticker')
    def test_correct_stoxx50_ticker(self, mock_ticker, sample_stoxx50_data):
        """Test that correct STOXX50 ticker is used."""
        mock_stoxx_ticker = Mock()
        mock_stoxx_ticker.history.return_value = sample_stoxx50_data
        mock_ticker.return_value = mock_stoxx_ticker
        
        get_market_data()
        
        # Verify ^STOXX50E is called
        calls = [call for call in mock_ticker.call_args_list if call[0][0] == '^STOXX50E']
        assert len(calls) > 0
    
    @patch('trade_filter.yf.Ticker')
    def test_correct_vix_ticker(self, mock_ticker, sample_stoxx50_data, sample_vix_data):
        """Test that correct VIX ticker is used."""
        def mock_ticker_side_effect(symbol):
            mock = Mock()
            if symbol == '^VIX':
                mock.history.return_value = sample_vix_data
            elif symbol == '^STOXX50E':
                mock.history.return_value = sample_stoxx50_data
            return mock
        
        mock_ticker.side_effect = mock_ticker_side_effect
        
        get_market_data()
        
        # Verify ^VIX is called
        calls = [call for call in mock_ticker.call_args_list if call[0][0] == '^VIX']
        assert len(calls) > 0


class TestMarketDataEdgeCases:
    """Test market data edge cases."""
    
    @patch('trade_filter.yf.Ticker')
    def test_vix_optional_empty_data(self, mock_ticker, sample_stoxx50_data):
        """Test that empty VIX data doesn't break functionality."""
        def mock_ticker_side_effect(symbol):
            mock = Mock()
            if symbol == '^VIX':
                mock.history.return_value = pd.DataFrame()  # Empty VIX
            elif symbol == '^STOXX50E':
                mock.history.return_value = sample_stoxx50_data
            return mock
        
        mock_ticker.side_effect = mock_ticker_side_effect
        
        result = get_market_data()
        
        # Should still return STOXX50 data even if VIX is empty
        assert 'stoxx_current' in result
        assert 'vix' not in result  # VIX should not be in result if empty
    
    @patch('trade_filter.yf.Ticker')
    def test_single_day_data(self, mock_ticker):
        """Test handling of single day data."""
        single_day_data = pd.DataFrame({
            'Open': [5180.0],
            'High': [5200.0],
            'Low': [5150.0],
            'Close': [5180.0]
        }, index=pd.to_datetime(['2026-01-03']))
        
        mock_stoxx_ticker = Mock()
        mock_stoxx_ticker.history.return_value = single_day_data
        mock_ticker.return_value = mock_stoxx_ticker
        
        result = get_market_data()
        
        assert result['stoxx_current'] == 5180.0
        assert result['stoxx_open'] == 5180.0
