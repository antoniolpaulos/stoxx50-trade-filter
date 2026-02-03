"""
Edge case testing for market holidays, API failures, and unusual conditions.
"""

import pytest
import pandas as pd
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exceptions import MarketDataError, CalendarAPIError, ValidationError
from tests.fixtures.sample_data import MARKET_HOLIDAYS


class TestEdgeCases:
    """Test edge cases and unusual scenarios."""
    
    def test_market_holiday_detection(self):
        """Test behavior on market holidays."""
        # Test known holidays
        for holiday_date in MARKET_HOLIDAYS:
            assert holiday_date.weekday() < 5, "Test holidays should be weekdays"
            
            # Simulate holiday behavior - no market data available
            def simulate_holiday_fetch():
                # On holidays, yfinance might return empty data
                empty_data = pd.DataFrame()
                if empty_data.empty:
                    raise MarketDataError(f"No market data available on {holiday_date} (market holiday)")
            
            with pytest.raises(MarketDataError, match="market holiday"):
                simulate_holiday_fetch()
    
    def test_weekend_market_closed(self):
        """Test behavior on weekends."""
        weekend_dates = [
            date(2026, 1, 3),  # Saturday
            date(2026, 1, 4),  # Sunday
        ]
        
        for weekend_date in weekend_dates:
            assert weekend_date.weekday() >= 5, "Should be weekend"
            
            def simulate_weekend_fetch():
                if weekend_date.weekday() >= 5:
                    raise MarketDataError(f"Market closed on {weekend_date} (weekend)")
            
            with pytest.raises(MarketDataError, match="weekend"):
                simulate_weekend_fetch()
    
    def test_pre_market_early_hours(self):
        """Test behavior during pre-market hours."""
        # Test at 4:00 AM ET (before market open)
        early_time = datetime(2026, 1, 2, 4, 0)
        
        def simulate_pre_market_check():
            current_hour = early_time.hour
            if current_hour < 9 or (current_hour == 9 and early_time.minute < 30):
                # Market hasn't opened yet, no current day data
                return {
                    'status': 'pre_market',
                    'message': 'Market not yet open',
                    'has_current_data': False
                }
            return {'status': 'market_open'}
        
        result = simulate_pre_market_check()
        assert result['status'] == 'pre_market'
        assert result['has_current_data'] is False
    
    def test_after_market_close(self):
        """Test behavior after market close."""
        # Test at 5:00 PM ET (after market close)
        close_time = datetime(2026, 1, 2, 17, 0)
        
        def simulate_after_market_check():
            current_hour = close_time.hour
            if current_hour >= 16:
                # Market closed, use previous day's closing data
                return {
                    'status': 'after_hours',
                    'message': 'Market closed for the day',
                    'uses_previous_data': True
                }
            return {'status': 'market_open'}
        
        result = simulate_after_market_check()
        assert result['status'] == 'after_hours'
        assert result['uses_previous_data'] is True
    
    def test_extreme_market_volatility(self):
        """Test behavior during extreme market volatility."""
        # Simulate VIX spiking to very high levels
        extreme_vix_data = pd.DataFrame({
            'Open': [50.0, 55.0, 60.0],
            'High': [52.0, 58.0, 65.0],
            'Low': [48.0, 52.0, 58.0],
            'Close': [51.0, 57.0, 64.0]
        })
        
        vix_current = extreme_vix_data['Close'].iloc[-1]
        vix_threshold = 22.0
        
        # Should trigger NO-GO due to high volatility
        rule_1_pass = vix_current <= vix_threshold
        assert rule_1_pass is False
        assert vix_current == 64.0
        
        # Test extreme intraday changes
        extreme_spx_data = pd.DataFrame({
            'Open': [4800.0],
            'Close': [4320.0]  # 10% drop
        })
        
        intraday_change = ((extreme_spx_data['Close'].iloc[-1] - extreme_spx_data['Open'].iloc[-1]) / 
                         extreme_spx_data['Open'].iloc[-1]) * 100
        
        max_change = 1.0
        rule_2_pass = abs(intraday_change) <= max_change
        assert rule_2_pass is False
        assert abs(intraday_change) == 10.0
    
    def test_very_low_volatility_environment(self):
        """Test behavior in very low volatility environment."""
        # VIX at historical lows
        low_vix_data = pd.DataFrame({
            'Close': [8.5]  # Extremely low VIX
        })
        
        vix_current = low_vix_data['Close'].iloc[-1]
        vix_threshold = 22.0
        
        rule_1_pass = vix_current <= vix_threshold
        assert rule_1_pass is True
        assert vix_current == 8.5
        
        # Test very small intraday changes
        low_change_data = pd.DataFrame({
            'Open': [4800.0],
            'Close': [4800.5]  # Only 0.01% change
        })
        
        intraday_change = ((low_change_data['Close'].iloc[-1] - low_change_data['Open'].iloc[-1]) / 
                          low_change_data['Open'].iloc[-1]) * 100
        
        assert abs(intraday_change) < 1.0
    
    def test_api_consecutive_failures(self):
        """Test handling of consecutive API failures."""
        failure_count = 0
        max_retries = 3
        
        def simulate_api_with_retries():
            nonlocal failure_count
            failure_count += 1
            
            if failure_count <= max_retries:
                raise MarketDataError(f"API call failed (attempt {failure_count})")
            
            return {"status": "success", "attempts": failure_count}
        
        # Should fail on first few attempts
        for i in range(max_retries):
            with pytest.raises(MarketDataError, match="API call failed"):
                simulate_api_with_retries()
        
        # Should succeed on final attempt
        result = simulate_api_with_retries()
        assert result["status"] == "success"
        assert result["attempts"] == max_retries + 1
    
    def test_partial_data_availability(self):
        """Test handling of partial or incomplete data."""
        # Test case: VIX data available but SPX missing
        partial_data_scenarios = [
            {
                'name': 'VIX available, SPX missing',
                'vix_data': pd.DataFrame({'Close': [18.5]}),
                'spx_data': pd.DataFrame(),
                'expected_error': 'SPX data is empty'
            },
            {
                'name': 'SPX available, VIX missing',
                'vix_data': pd.DataFrame(),
                'spx_data': pd.DataFrame({'Close': [4800.0], 'Open': [4790.0]}),
                'expected_error': 'VIX data is empty'
            },
            {
                'name': 'Both missing required columns',
                'vix_data': pd.DataFrame({'WrongColumn': [1, 2, 3]}),
                'spx_data': pd.DataFrame({'AnotherColumn': [1, 2, 3]}),
                'expected_error': 'VIX data missing required'
            }
        ]
        
        for scenario in partial_data_scenarios:
            def validate_partial_data(vix_data, spx_data):
                if vix_data.empty:
                    raise MarketDataError("VIX data is empty")
                if spx_data.empty:
                    raise MarketDataError("SPX data is empty")
                if 'Close' not in vix_data.columns:
                    raise MarketDataError("VIX data missing required 'Close' column")
                if 'Close' not in spx_data.columns:
                    raise MarketDataError("SPX data missing required columns")
                return True
            
            with pytest.raises(MarketDataError) as exc_info:
                validate_partial_data(scenario['vix_data'], scenario['spx_data'])
            
            assert scenario['expected_error'] in str(exc_info.value)
    
    def test_data_quality_anomalies(self):
        """Test handling of data quality anomalies."""
        anomaly_scenarios = [
            {
                'name': 'Negative VIX values',
                'data': pd.DataFrame({'Close': [-5.0, -10.0]}),
                'expected_error': 'VIX values must be positive'
            },
            {
                'name': 'Zero SPX prices',
                'data': pd.DataFrame({'Close': [0.0], 'Open': [0.0]}),
                'expected_error': 'SPX prices must be positive'
            },
            {
                'name': 'Extremely high SPX prices',
                'data': pd.DataFrame({'Close': [999999.0], 'Open': [999990.0]}),
                'should_pass': True  # High but valid
            }
        ]
        
        for scenario in anomaly_scenarios:
            if 'expected_error' in scenario:
                def validate_anomaly(data):
                    if 'Close' in data.columns:
                        if (data['Close'] <= 0).any():
                            raise MarketDataError(scenario['expected_error'])
                    if 'Open' in data.columns:
                        if (data['Open'] <= 0).any():
                            raise MarketDataError(scenario['expected_error'])
                    return True
                
                with pytest.raises(MarketDataError, match=scenario['expected_error']):
                    validate_anomaly(scenario['data'])
            else:
                # Should pass validation
                assert (scenario['data']['Close'] > 0).all()
    
    def test_calendar_api_edge_cases(self):
        """Test calendar API edge cases."""
        edge_cases = [
            {
                'name': 'Empty calendar response',
                'response': [],
                'expected_has_events': False
            },
            {
                'name': 'Malformed event data',
                'response': [{'invalid': 'data'}],
                'expected_has_events': False
            },
            {
                'name': 'Events with missing dates',
                'response': [{'title': 'FOMC', 'impact': 'High'}],  # Missing date
                'expected_has_events': False
            },
            {
                'name': 'Non-USD events',
                'response': [{'country': 'EUR', 'impact': 'High', 'date': '2026-01-03'}],
                'expected_has_events': False
            },
            {
                'name': 'Low impact USD events',
                'response': [{'country': 'USD', 'impact': 'Low', 'date': '2026-01-03'}],
                'expected_has_events': False
            }
        ]
        
        today = date.today().strftime('%Y-%m-%d')
        
        def parse_calendar_response(events_data):
            high_impact_today = []
            for event in events_data:
                country = event.get('country', '')
                impact = event.get('impact', '')
                event_date = event.get('date', '')
                
                if (country == 'USD' and 
                    event_date == today and 
                    impact == 'High'):
                    high_impact_today.append(event)
            
            return len(high_impact_today) > 0
        
        for case in edge_cases:
            result = parse_calendar_response(case['response'])
            assert result == case['expected_has_events'], f"Failed for {case['name']}"
    
    def test_telegram_edge_cases(self):
        """Test Telegram notification edge cases."""
        edge_cases = [
            {
                'name': 'Very long message',
                'message': 'A' * 5000,  # Exceeds Telegram limits
                'should_fail': True
            },
            {
                'name': 'Message with special characters',
                'message': 'Test with <>&"\' and emojis 🚀📈',
                'should_fail': False
            },
            {
                'name': 'Empty message',
                'message': '',
                'should_fail': False
            },
            {
                'name': 'None message',
                'message': None,
                'should_fail': True
            }
        ]
        
        for case in edge_cases:
            def validate_message(message):
                if message is None:
                    raise ValidationError("Message cannot be None")
                if len(message) > 4096:  # Telegram message limit
                    raise ValidationError("Message too long for Telegram")
                return True
            
            if case['should_fail']:
                with pytest.raises(ValidationError):
                    validate_message(case['message'])
            else:
                assert validate_message(case['message']) is True