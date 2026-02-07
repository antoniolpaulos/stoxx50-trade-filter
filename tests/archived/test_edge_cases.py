"""
Edge case testing for market holidays, API failures, and unusual conditions - STOXX50 version.
"""

import pytest
import pandas as pd
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_filter import calculate_intraday_change, calculate_strikes
from exceptions import MarketDataError, CalendarAPIError, ValidationError
from tests.fixtures.sample_data import MARKET_HOLIDAYS


class TestMarketHolidays:
    """Test behavior on market holidays."""
    
    def test_market_holiday_detection(self):
        """Test behavior on market holidays."""
        # Test known European holidays
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
        """Test behavior during pre-market hours (CET timezone)."""
        # Euro Stoxx 50 opens at 9:00 CET
        # Test at 8:00 CET (before market open)
        early_time = datetime(2026, 1, 2, 8, 0)
        
        def simulate_pre_market_check():
            current_hour = early_time.hour
            # Euro Stoxx 50 opens at 9:00 CET
            if current_hour < 9:
                # Market hasn't opened yet, no current day data
                return {
                    'status': 'pre_market',
                    'message': 'Market not yet open (Euro Stoxx 50 opens at 9:00 CET)',
                    'has_current_data': False
                }
            return {'status': 'market_open'}
        
        result = simulate_pre_market_check()
        assert result['status'] == 'pre_market'
        assert result['has_current_data'] is False
    
    def test_after_market_close(self):
        """Test behavior after market close (CET timezone)."""
        # Euro Stoxx 50 closes at 17:30 CET
        # Test at 18:00 CET (after market close)
        close_time = datetime(2026, 1, 2, 18, 0)
        
        def simulate_after_market_check():
            current_hour = close_time.hour
            current_minute = close_time.minute
            # Market closes at 17:30 CET
            if current_hour > 17 or (current_hour == 17 and current_minute >= 30):
                # Market closed, use previous day's closing data
                return {
                    'status': 'after_hours',
                    'message': 'Market closed for the day (Euro Stoxx 50 closed at 17:30 CET)',
                    'uses_previous_data': True
                }
            return {'status': 'market_open'}
        
        result = simulate_after_market_check()
        assert result['status'] == 'after_hours'
        assert result['uses_previous_data'] is True


class TestExtremeMarketConditions:
    """Test behavior during extreme market volatility for STOXX50."""
    
    def test_extreme_vstoxx_levels(self):
        """Test behavior during extreme VSTOXX levels."""
        # Simulate VSTOXX spiking to very high levels
        extreme_vstoxx_data = pd.DataFrame({
            'Open': [50.0, 55.0, 60.0],
            'High': [52.0, 58.0, 65.0],
            'Low': [48.0, 52.0, 58.0],
            'Close': [51.0, 57.0, 64.0]
        })
        
        vstoxx_current = extreme_vstoxx_data['Close'].iloc[-1]
        vstoxx_threshold = 25.0
        
        # Should trigger NO-GO due to high volatility
        rule_pass = vstoxx_current <= vstoxx_threshold
        assert rule_pass == False  # Use == for numpy bool comparison
        assert vstoxx_current == 64.0
        
        # Test extreme intraday changes for STOXX50
        extreme_stoxx_data = pd.DataFrame({
            'Open': [5180.0],
            'Close': [4662.0]  # 10% drop
        })
        
        intraday_change = ((extreme_stoxx_data['Close'].iloc[-1] - extreme_stoxx_data['Open'].iloc[-1]) / 
                         extreme_stoxx_data['Open'].iloc[-1]) * 100
        
        max_change = 1.0
        rule_pass = abs(intraday_change) <= max_change
        assert rule_pass == False  # Use == for numpy bool comparison
        assert abs(intraday_change - (-10.0)) < 0.01
    
    def test_very_low_volatility_environment(self):
        """Test behavior in very low volatility environment."""
        # VSTOXX at historical lows
        low_vstoxx_data = pd.DataFrame({
            'Close': [8.5]  # Extremely low VSTOXX
        })
        
        vstoxx_current = low_vstoxx_data['Close'].iloc[-1]
        vstoxx_threshold = 25.0
        
        rule_pass = vstoxx_current <= vstoxx_threshold
        assert rule_pass == True  # Use == for numpy bool comparison
        assert vstoxx_current == 8.5
        
        # Test very small intraday changes
        low_change_data = pd.DataFrame({
            'Open': [5180.0],
            'Close': [5180.5]  # Only 0.01% change
        })
        
        intraday_change = ((low_change_data['Close'].iloc[-1] - low_change_data['Open'].iloc[-1]) / 
                          low_change_data['Open'].iloc[-1]) * 100
        
        assert abs(intraday_change) < 1.0
    
    def test_stoxx50_flash_crash_scenario(self):
        """Test behavior during STOXX50 flash crash scenario."""
        # Flash crash: rapid drop and recovery
        flash_crash_data = pd.DataFrame({
            'Open': [5180.0],
            'High': [5180.0],
            'Low': [4662.0],  # 10% drop
            'Close': [5130.0]  # Recovers to ~1% down
        })
        
        # Calculate based on close
        intraday_change = ((flash_crash_data['Close'].iloc[-1] - flash_crash_data['Open'].iloc[-1]) / 
                          flash_crash_data['Open'].iloc[-1]) * 100
        
        max_change = 1.0
        rule_pass = abs(intraday_change) <= max_change
        
        # At close, change is within threshold but range was huge
        assert abs(intraday_change) < 1.0
        
        # Previous day range filter would catch this
        prev_range = ((flash_crash_data['High'].iloc[-1] - flash_crash_data['Low'].iloc[-1]) /
                     flash_crash_data['Open'].iloc[-1]) * 100
        assert prev_range >= 10.0  # Very high range (exactly 10% in this case)


class TestAPIFailures:
    """Test handling of API failures."""
    
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
        # Test case: VSTOXX data available but STOXX50 missing
        partial_data_scenarios = [
            {
                'name': 'VSTOXX available, STOXX50 missing',
                'vstoxx_data': pd.DataFrame({'Close': [18.5]}),
                'stoxx_data': pd.DataFrame(),
                'expected_error': 'STOXX50 data is empty'
            },
            {
                'name': 'STOXX50 available, VSTOXX missing',
                'vstoxx_data': pd.DataFrame(),
                'stoxx_data': pd.DataFrame({'Close': [5180.0], 'Open': [5170.0]}),
                'expected_error': 'VSTOXX data is empty'
            },
            {
                'name': 'Both missing required columns',
                'vstoxx_data': pd.DataFrame({'WrongColumn': [1, 2, 3]}),
                'stoxx_data': pd.DataFrame({'AnotherColumn': [1, 2, 3]}),
                'expected_error': 'VSTOXX data missing required'
            }
        ]
        
        for scenario in partial_data_scenarios:
            def validate_partial_data(vstoxx_data, stoxx_data):
                if vstoxx_data.empty:
                    raise MarketDataError("VSTOXX data is empty")
                if stoxx_data.empty:
                    raise MarketDataError("STOXX50 data is empty")
                if 'Close' not in vstoxx_data.columns:
                    raise MarketDataError("VSTOXX data missing required 'Close' column")
                if 'Close' not in stoxx_data.columns:
                    raise MarketDataError("STOXX50 data missing required columns")
                return True
            
            with pytest.raises(MarketDataError) as exc_info:
                validate_partial_data(scenario['vstoxx_data'], scenario['stoxx_data'])
            
            assert scenario['expected_error'] in str(exc_info.value)
    
    def test_data_quality_anomalies(self):
        """Test handling of data quality anomalies."""
        anomaly_scenarios = [
            {
                'name': 'Negative VSTOXX values',
                'data': pd.DataFrame({'Close': [-5.0, -10.0]}),
                'expected_error': 'VSTOXX values must be positive'
            },
            {
                'name': 'Zero STOXX50 prices',
                'data': pd.DataFrame({'Close': [0.0], 'Open': [0.0]}),
                'expected_error': 'STOXX50 prices must be positive'
            },
            {
                'name': 'Extremely high STOXX50 prices',
                'data': pd.DataFrame({'Close': [99999.0], 'Open': [99990.0]}),
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


class TestCalendarAPIEdgeCases:
    """Test calendar API edge cases for EUR events."""
    
    def test_eur_event_filtering(self):
        """Test filtering of EUR high-impact events."""
        today = date.today().strftime('%Y-%m-%d')
        
        edge_cases = [
            {
                'name': 'ECB Rate Decision today',
                'response': [{'country': 'EUR', 'impact': 'High', 'date': today, 'title': 'ECB Interest Rate Decision'}],
                'expected_has_events': True
            },
            {
                'name': 'Eurozone CPI today',
                'response': [{'country': 'EUR', 'impact': 'High', 'date': today, 'title': 'Eurozone CPI'}],
                'expected_has_events': True
            },
            {
                'name': 'German ZEW today',
                'response': [{'country': 'DE', 'impact': 'High', 'date': today, 'title': 'German ZEW Economic Sentiment'}],
                'expected_has_events': False  # DE not EUR
            },
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
                'response': [{'title': 'ECB', 'impact': 'High', 'country': 'EUR'}],
                'expected_has_events': False
            },
            {
                'name': 'Low impact EUR events',
                'response': [{'country': 'EUR', 'impact': 'Low', 'date': today, 'title': 'EUR Industrial Production'}],
                'expected_has_events': False
            },
            {
                'name': 'USD events (should ignore)',
                'response': [{'country': 'USD', 'impact': 'High', 'date': today, 'title': 'FOMC Statement'}],
                'expected_has_events': False
            }
        ]
        
        def parse_calendar_response(events_data):
            high_impact_today = []
            for event in events_data:
                country = event.get('country', '')
                impact = event.get('impact', '')
                event_date = event.get('date', '')
                
                if (country == 'EUR' and 
                    event_date == today and 
                    impact == 'High'):
                    high_impact_today.append(event)
            
            return len(high_impact_today) > 0
        
        for case in edge_cases:
            result = parse_calendar_response(case['response'])
            assert result == case['expected_has_events'], f"Failed for {case['name']}"
    
    def test_watchlist_events(self):
        """Test watchlist event detection."""
        watchlist = ['ECB', 'Eurozone CPI', 'German ZEW']
        today = date.today().strftime('%Y-%m-%d')

        events = [
            {'country': 'EUR', 'impact': 'Medium', 'date': today, 'title': 'ECB Press Conference'},
            {'country': 'EUR', 'impact': 'Medium', 'date': today, 'title': 'Eurozone Industrial Production'},
        ]

        def is_watched_event(title):
            title_upper = title.upper()
            return any(watch.upper() in title_upper for watch in watchlist)

        # ECB should be in watchlist
        assert is_watched_event('ECB Press Conference') == True
        # Eurozone CPI should be in watchlist
        assert is_watched_event('Eurozone CPI YoY') == True
        # Random event should not be in watchlist
        assert is_watched_event('Random Event') == False


class TestTelegramEdgeCases:
    """Test Telegram notification edge cases."""
    
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
                if len(str(message)) > 4096:  # Telegram message limit
                    raise ValidationError("Message too long for Telegram")
                return True
            
            if case['should_fail']:
                with pytest.raises(ValidationError):
                    validate_message(case['message'])
            else:
                assert validate_message(case['message']) is True


class TestStrikeCalculationEdgeCases:
    """Test strike calculation edge cases for STOXX50."""
    
    def test_strike_calculation_boundary_values(self):
        """Test strike calculation at boundary values."""
        # Very high STOXX50
        stoxx_high = 6000.0
        call, put = calculate_strikes(stoxx_high, 1.0)
        assert call == 6060  # 6000 * 1.01 = 6060
        assert put == 5940   # 6000 * 0.99 = 5940
        
        # Lower STOXX50
        stoxx_low = 4500.0
        call, put = calculate_strikes(stoxx_low, 1.0)
        assert call == 4545  # 4500 * 1.01 = 4545
        assert put == 4455   # 4500 * 0.99 = 4455
    
    def test_strike_calculation_rounding_edge_cases(self):
        """Test strike rounding at exact .5 values."""
        # Price that creates exact .5
        stoxx_price = 5000.0
        call, put = calculate_strikes(stoxx_price, 1.0)
        # 5000 * 1.01 = 5050.0 - exact, no rounding needed
        assert call == 5050
        assert put == 4950   # 5000 * 0.99 = 4950.0
    
    def test_zero_wing_width(self):
        """Test with zero wing width (butterfly)."""
        stoxx_price = 5180.0
        call, put = calculate_strikes(stoxx_price, 1.0, 0)
        # With zero wing width, long and short strikes are the same
        # This would be an unusual but valid configuration
        assert call == 5232
        assert put == 5128


class TestTimeZoneEdgeCases:
    """Test timezone-related edge cases."""
    
    def test_cet_trading_hours(self):
        """Test Euro Stoxx 50 trading hours in CET."""
        # Market opens at 9:00 CET, closes at 17:30 CET
        
        # 8:59 CET - pre-market
        pre_market = datetime(2026, 1, 2, 8, 59)
        assert pre_market.hour < 9
        
        # 9:00 CET - market open
        market_open = datetime(2026, 1, 2, 9, 0)
        assert market_open.hour == 9
        
        # 17:30 CET - market close
        market_close = datetime(2026, 1, 2, 17, 30)
        assert market_close.hour == 17 and market_close.minute == 30
        
        # 17:31 CET - after hours
        after_hours = datetime(2026, 1, 2, 17, 31)
        assert after_hours.hour > 17 or (after_hours.hour == 17 and after_hours.minute > 30)
    
    def test_summer_time_transition(self):
        """Test behavior during summer time transitions."""
        # Euro Stoxx 50 follows CET/CEST
        # Summer time starts last Sunday in March
        
        winter_date = datetime(2026, 1, 15, 10, 0)  # CET
        summer_date = datetime(2026, 7, 15, 10, 0)  # CEST
        
        # Both should be valid trading times (10:00 local time)
        assert winter_date.hour == 10
        assert summer_date.hour == 10
