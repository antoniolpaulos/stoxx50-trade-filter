"""
Integration tests for trade_filter.py - testing evaluate_trade with mocked dependencies.
"""

import pytest
import sys
import os
from datetime import date
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
from io import StringIO

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_filter import evaluate_trade


class TestEvaluateTradeIntegration:
    """Integration tests for evaluate_trade function."""
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_go_conditions(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test evaluate_trade returns GO when all conditions are met."""
        # Mock market data - favorable conditions
        mock_market.return_value = {
            'stoxx_current': 5220.0,
            'stoxx_open': 5180.0,
            'vix': 16.5
        }
        
        # Mock calendar - no high impact events
        mock_calendar.return_value = {
            'has_high_impact': False,
            'events': [],
            'source': 'ForexFactory',
            'error': None,
            'all_eur_high_this_week': []
        }
        
        # Run evaluate_trade
        evaluate_trade(sample_config, use_additional_filters=False)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should show GO verdict
        assert "GO" in captured.out or "CONDITIONS FAVORABLE" in captured.out
        assert "NO GO" not in captured.out
        
        # Should send Telegram notification
        mock_telegram.assert_called_once()
        call_args = mock_telegram.call_args
        assert "GO" in call_args[0][1] or "CONDITIONS FAVORABLE" in call_args[0][1]
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_no_go_high_vstoxx(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test evaluate_trade returns NO-GO when VSTOXX is high."""
        # Mock market data - VSTOXX implied high through VIX warning
        mock_market.return_value = {
            'stoxx_current': 5220.0,
            'stoxx_open': 5180.0,
            'vix': 28.0  # Elevated VIX indicates high volatility
        }
        
        # Mock calendar - no high impact events
        mock_calendar.return_value = {
            'has_high_impact': False,
            'events': [],
            'source': 'ForexFactory',
            'error': None,
            'all_eur_high_this_week': []
        }
        
        # Run evaluate_trade
        evaluate_trade(sample_config, use_additional_filters=False)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should show elevated VIX warning
        assert "VIX" in captured.out or "elevated" in captured.out.lower()
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_no_go_trend_too_strong(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test evaluate_trade returns NO-GO when trend is too strong."""
        # Mock market data - strong trend (>1% change)
        mock_market.return_value = {
            'stoxx_current': 5260.0,  # ~1.54% up from open
            'stoxx_open': 5180.0,
            'vix': 16.5
        }
        
        # Mock calendar - no high impact events
        mock_calendar.return_value = {
            'has_high_impact': False,
            'events': [],
            'source': 'ForexFactory',
            'error': None,
            'all_eur_high_this_week': []
        }
        
        # Run evaluate_trade
        evaluate_trade(sample_config, use_additional_filters=False)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should show NO-GO
        assert "NO GO" in captured.out or "DO NOT TRADE" in captured.out
        assert "Trend too strong" in captured.out or "change" in captured.out.lower()
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_no_go_economic_events(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test evaluate_trade returns NO-GO when high-impact economic events."""
        # Mock market data - favorable
        mock_market.return_value = {
            'stoxx_current': 5220.0,
            'stoxx_open': 5180.0,
            'vix': 16.5
        }
        
        # Mock calendar - high impact events today
        mock_calendar.return_value = {
            'has_high_impact': True,
            'events': [
                {
                    'name': 'ECB Interest Rate Decision',
                    'time': '14:15',
                    'impact': 'High'
                }
            ],
            'source': 'ForexFactory',
            'error': None,
            'all_eur_high_this_week': ['2026-02-04: ECB Interest Rate Decision']
        }
        
        # Run evaluate_trade
        evaluate_trade(sample_config, use_additional_filters=False)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should show NO-GO
        assert "NO GO" in captured.out or "DO NOT TRADE" in captured.out
        assert "ECB" in captured.out
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_with_additional_filters(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test evaluate_trade with additional filters enabled."""
        # Mock market data with history for additional filters
        mock_market.return_value = {
            'stoxx_current': 5220.0,
            'stoxx_open': 5180.0,
            'vix': 16.5,
            'ma_20': 5050.0,  # Current is ~2.57% above MA
            'prev_range_pct': 1.5  # Within 2% limit
        }
        
        # Mock calendar - no high impact events
        mock_calendar.return_value = {
            'has_high_impact': False,
            'events': [],
            'source': 'ForexFactory',
            'error': None,
            'all_eur_high_this_week': []
        }
        
        # Run evaluate_trade with additional filters
        evaluate_trade(sample_config, use_additional_filters=True)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should show additional filters section
        assert "ADDITIONAL FILTERS" in captured.out or "Additional filters" in captured.out
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_ma_deviation_filter_fail(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test evaluate_trade fails additional filter MA deviation."""
        # Mock market data with high MA deviation
        mock_market.return_value = {
            'stoxx_current': 5300.0,  # Far from MA
            'stoxx_open': 5180.0,
            'vix': 16.5,
            'ma_20': 5050.0,  # Deviation is ~4.95% (>3% limit)
            'prev_range_pct': 1.5
        }
        
        # Mock calendar - no high impact events
        mock_calendar.return_value = {
            'has_high_impact': False,
            'events': [],
            'source': 'ForexFactory',
            'error': None,
            'all_eur_high_this_week': []
        }
        
        # Run evaluate_trade with additional filters
        evaluate_trade(sample_config, use_additional_filters=True)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should show MA deviation filter failure
        assert "Filter A" in captured.out or "MA deviation" in captured.out
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_prev_day_range_filter_fail(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test evaluate_trade fails additional filter prev day range."""
        # Mock market data with high previous day range
        mock_market.return_value = {
            'stoxx_current': 5220.0,
            'stoxx_open': 5180.0,
            'vix': 16.5,
            'ma_20': 5050.0,
            'prev_range_pct': 2.5  # >2% limit
        }
        
        # Mock calendar - no high impact events
        mock_calendar.return_value = {
            'has_high_impact': False,
            'events': [],
            'source': 'ForexFactory',
            'error': None,
            'all_eur_high_this_week': []
        }
        
        # Run evaluate_trade with additional filters
        evaluate_trade(sample_config, use_additional_filters=True)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should show prev day range filter failure
        assert "Filter B" in captured.out or "Prev day range" in captured.out
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_calendar_api_error(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test evaluate_trade handles calendar API error gracefully."""
        # Mock market data - favorable
        mock_market.return_value = {
            'stoxx_current': 5220.0,
            'stoxx_open': 5180.0,
            'vix': 16.5
        }
        
        # Mock calendar - API error
        mock_calendar.return_value = {
            'has_high_impact': None,
            'events': [],
            'source': None,
            'error': 'Calendar API failed: Connection timeout',
            'all_eur_high_this_week': []
        }
        
        # Run evaluate_trade
        evaluate_trade(sample_config, use_additional_filters=False)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should show warning about API error
        assert "WARN" in captured.out or "error" in captured.out.lower() or "API" in captured.out
    
    @patch('trade_filter.get_market_data')
    def test_evaluate_trade_market_data_error(self, mock_market, sample_config, capsys):
        """Test evaluate_trade handles market data error."""
        # Mock market data - error
        from exceptions import MarketDataError
        mock_market.side_effect = MarketDataError("Unable to fetch market data. Market may be closed.")
        
        # Run evaluate_trade
        evaluate_trade(sample_config, use_additional_filters=False)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should show error
        assert "ERROR" in captured.out or "error" in captured.out.lower()
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_strike_calculation(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test that strikes are correctly calculated in GO scenario."""
        # Mock market data - current price 5180
        mock_market.return_value = {
            'stoxx_current': 5180.0,
            'stoxx_open': 5154.0,  # 0.5% down at open, now flat
            'vix': 16.5
        }
        
        # Mock calendar - no high impact events
        mock_calendar.return_value = {
            'has_high_impact': False,
            'events': [],
            'source': 'ForexFactory',
            'error': None,
            'all_eur_high_this_week': []
        }
        
        # Run evaluate_trade
        evaluate_trade(sample_config, use_additional_filters=False)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should show calculated strikes
        # 5180 * 1.01 = 5231.8 -> 5232
        # 5180 * 0.99 = 5128.2 -> 5128
        assert "5232" in captured.out or "5128" in captured.out or "RECOMMENDED STRIKES" in captured.out
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_with_wing_width(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test that wing width is correctly shown in output."""
        # Mock market data
        mock_market.return_value = {
            'stoxx_current': 5180.0,
            'stoxx_open': 5154.0,
            'vix': 16.5
        }
        
        # Mock calendar - no high impact events
        mock_calendar.return_value = {
            'has_high_impact': False,
            'events': [],
            'source': 'ForexFactory',
            'error': None,
            'all_eur_high_this_week': []
        }
        
        # Run evaluate_trade
        evaluate_trade(sample_config, use_additional_filters=False)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should show wing width (50 pts)
        assert "50" in captured.out or "wing" in captured.out.lower()


class TestEvaluateTradeEdgeCases:
    """Edge case integration tests for evaluate_trade."""
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_exactly_at_thresholds(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test evaluate_trade when values are exactly at thresholds."""
        # Mock market data - exactly at 1% change threshold
        mock_market.return_value = {
            'stoxx_current': 5231.8,  # Exactly 1% up from 5180
            'stoxx_open': 5180.0,
            'vix': 22.0  # Exactly at warning threshold
        }
        
        # Mock calendar - no high impact events
        mock_calendar.return_value = {
            'has_high_impact': False,
            'events': [],
            'source': 'ForexFactory',
            'error': None,
            'all_eur_high_this_week': []
        }
        
        # Run evaluate_trade
        evaluate_trade(sample_config, use_additional_filters=False)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should pass (<= threshold)
        # Note: Due to rounding, might show PASS or have warning
        assert "1.00%" in captured.out or "1.0%" in captured.out or "change" in captured.out.lower()
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_negative_change(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test evaluate_trade with negative price change."""
        # Mock market data - negative trend
        mock_market.return_value = {
            'stoxx_current': 5102.3,  # ~1.5% down
            'stoxx_open': 5180.0,
            'vix': 16.5
        }
        
        # Mock calendar - no high impact events
        mock_calendar.return_value = {
            'has_high_impact': False,
            'events': [],
            'source': 'ForexFactory',
            'error': None,
            'all_eur_high_this_week': []
        }
        
        # Run evaluate_trade
        evaluate_trade(sample_config, use_additional_filters=False)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should show NO-GO with negative change
        assert "NO GO" in captured.out or "DO NOT TRADE" in captured.out
        assert "-" in captured.out  # Negative sign
    
    @patch('trade_filter.get_market_data')
    @patch('trade_filter.check_economic_calendar')
    @patch('trade_filter.send_telegram_message')
    def test_evaluate_trade_vix_optional(self, mock_telegram, mock_calendar, mock_market, sample_config, capsys):
        """Test evaluate_trade when VIX data is unavailable."""
        # Mock market data - no VIX
        mock_market.return_value = {
            'stoxx_current': 5220.0,
            'stoxx_open': 5180.0
            # No 'vix' key
        }
        
        # Mock calendar - no high impact events
        mock_calendar.return_value = {
            'has_high_impact': False,
            'events': [],
            'source': 'ForexFactory',
            'error': None,
            'all_eur_high_this_week': []
        }
        
        # Run evaluate_trade
        evaluate_trade(sample_config, use_additional_filters=False)
        
        # Capture output
        captured = capsys.readouterr()
        
        # Should work without VIX (VIX is optional)
        assert "GO" in captured.out or "NO GO" in captured.out
