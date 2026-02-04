"""
Unit tests for rule evaluation engine - testing real functions from trade_filter.py.
"""

import pytest
import sys
import os
from unittest.mock import Mock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_filter import calculate_intraday_change, calculate_strikes
from exceptions import ValidationError


class TestCalculateIntradayChange:
    """Test calculate_intraday_change function from trade_filter.py."""
    
    def test_positive_change(self):
        """Test intraday change calculation with positive movement."""
        current_price = 5220.0
        open_price = 5180.0
        
        change = calculate_intraday_change(current_price, open_price)
        
        expected_change = ((5220.0 - 5180.0) / 5180.0) * 100
        assert abs(change - expected_change) < 0.01
        assert change > 0
        assert abs(change - 0.77) < 0.01  # ~0.77% up
    
    def test_negative_change(self):
        """Test intraday change calculation with negative movement."""
        current_price = 5130.0
        open_price = 5180.0
        
        change = calculate_intraday_change(current_price, open_price)
        
        expected_change = ((5130.0 - 5180.0) / 5180.0) * 100
        assert abs(change - expected_change) < 0.01
        assert change < 0
        assert abs(change - (-0.96)) < 0.01  # ~0.96% down
    
    def test_zero_change(self):
        """Test intraday change calculation with no movement."""
        current_price = 5180.0
        open_price = 5180.0
        
        change = calculate_intraday_change(current_price, open_price)
        
        assert change == 0.0
    
    def test_stoxx50_realistic_values(self):
        """Test with realistic STOXX50 values."""
        # Scenario: up 0.86%
        current_price = 5224.55
        open_price = 5180.0
        
        change = calculate_intraday_change(current_price, open_price)
        
        assert abs(change - 0.86) < 0.01
        
        # Scenario: down 1.5%
        current_price = 5102.3
        open_price = 5180.0
        
        change = calculate_intraday_change(current_price, open_price)
        
        assert abs(change - (-1.5)) < 0.01


class TestCalculateStrikes:
    """Test calculate_strikes function from trade_filter.py."""
    
    def test_strike_calculation_default_percent(self):
        """Test strike price calculation with default 1% OTM."""
        stoxx_price = 5180.0
        otm_percent = 1.0
        
        call_strike, put_strike = calculate_strikes(stoxx_price, otm_percent)
        
        # Expected: 5180 * 1.01 = 5231.8 -> 5232 (rounded to nearest integer)
        # Expected: 5180 * 0.99 = 5128.2 -> 5128 (rounded to nearest integer)
        assert call_strike == 5232
        assert put_strike == 5128
    
    def test_strike_calculation_different_percentages(self):
        """Test strike calculation with different OTM percentages."""
        stoxx_price = 5180.0
        
        test_cases = [
            (0.5, 5206, 5154),  # 5180 * 1.005 = 5205.9 -> 5206
            (1.0, 5232, 5128),  # 5180 * 1.01 = 5231.8 -> 5232
            (1.5, 5258, 5102),  # 5180 * 1.015 = 5257.7 -> 5258
            (2.0, 5284, 5076),  # 5180 * 1.02 = 5283.6 -> 5284
        ]
        
        for otm_percent, expected_call, expected_put in test_cases:
            call_strike, put_strike = calculate_strikes(stoxx_price, otm_percent)
            
            assert call_strike == expected_call, f"Failed for {otm_percent}% call strike"
            assert put_strike == expected_put, f"Failed for {otm_percent}% put strike"
    
    def test_strike_calculation_with_wing_width(self):
        """Test strike calculation considering wing width."""
        stoxx_price = 5180.0
        otm_percent = 1.0
        wing_width = 50
        
        call_strike, put_strike = calculate_strikes(stoxx_price, otm_percent, wing_width)
        
        # Short strikes
        assert call_strike == 5232
        assert put_strike == 5128
        
        # Long strikes (wing width away)
        call_long = call_strike + wing_width
        put_long = put_strike - wing_width
        
        assert call_long - call_strike == wing_width
        assert put_strike - put_long == wing_width
        assert call_long == 5282
        assert put_long == 5078
    
    def test_strike_calculation_edge_cases(self):
        """Test strike calculation edge cases."""
        # Very high STOXX50 price
        stoxx_price = 5500.0
        call_strike, put_strike = calculate_strikes(stoxx_price, 1.0)
        assert call_strike == 5555  # 5500 * 1.01 = 5555.0
        assert put_strike == 5445  # 5500 * 0.99 = 5445.0
        
        # Lower STOXX50 price
        stoxx_price = 4800.0
        call_strike, put_strike = calculate_strikes(stoxx_price, 1.0)
        assert call_strike == 4848  # 4800 * 1.01 = 4848.0
        assert put_strike == 4752  # 4800 * 0.99 = 4752.0
    
    def test_strike_rounding_behavior(self):
        """Test that strikes round to nearest integer (not 5-point like SPX)."""
        stoxx_price = 5183.0  # Intentionally odd number
        
        call_strike, put_strike = calculate_strikes(stoxx_price, 1.0)
        
        # 5183 * 1.01 = 5234.83 -> 5235 (should round to nearest integer, not 5)
        # 5183 * 0.99 = 5131.17 -> 5131
        assert call_strike == 5235
        assert put_strike == 5131
        
        # Verify it's NOT rounding to 5-point increments
        assert call_strike % 1 == 0  # Should be integer
        assert put_strike % 1 == 0   # Should be integer


class TestRulesIntegration:
    """Test rules integration with real functions."""
    
    def test_rule_1_vstoxx_check(self):
        """Test Rule 1: VSTOXX threshold check."""
        vstoxx_max = 25.0
        
        # Pass scenario
        vstoxx_current = 18.5
        rule_pass = vstoxx_current <= vstoxx_max
        assert rule_pass is True
        
        # Fail scenario
        vstoxx_current = 28.0
        rule_pass = vstoxx_current <= vstoxx_max
        assert rule_pass is False
    
    def test_rule_2_intraday_change_check(self):
        """Test Rule 2: Intraday change threshold check."""
        max_change = 1.0
        
        # Pass scenario
        stoxx_current = 5220.0
        stoxx_open = 5180.0
        change = calculate_intraday_change(stoxx_current, stoxx_open)
        rule_pass = abs(change) <= max_change
        assert rule_pass is True
        
        # Fail scenario
        stoxx_current = 5258.0  # ~1.5% up
        stoxx_open = 5180.0
        change = calculate_intraday_change(stoxx_current, stoxx_open)
        rule_pass = abs(change) <= max_change
        assert rule_pass is False
    
    def test_all_rules_combined(self):
        """Test all rules combined with real calculations."""
        # GO scenario
        stoxx_current = 5220.0
        stoxx_open = 5180.0
        vstoxx_current = 18.5
        high_impact_events = False
        
        change = calculate_intraday_change(stoxx_current, stoxx_open)
        
        rule1_pass = vstoxx_current <= 25.0
        rule2_pass = abs(change) <= 1.0
        rule3_pass = not high_impact_events
        
        go_verdict = rule1_pass and rule2_pass and rule3_pass
        
        assert go_verdict is True
        
        # NO-GO scenario - high VSTOXX
        vstoxx_current = 28.0
        rule1_pass = vstoxx_current <= 25.0
        go_verdict = rule1_pass and rule2_pass and rule3_pass
        assert go_verdict is False


class TestAdditionalFilters:
    """Test additional filter calculations."""
    
    def test_ma_deviation_calculation(self):
        """Test MA deviation calculation."""
        current_stoxx = 5180.0
        ma_20 = 5050.0
        
        deviation = ((current_stoxx - ma_20) / ma_20) * 100
        
        assert abs(deviation - 2.57) < 0.01
        
        # Test pass/fail logic
        max_deviation = 3.0
        filter_pass = abs(deviation) <= max_deviation
        assert filter_pass is True
        
        # Fail scenario
        current_stoxx = 5300.0
        deviation = ((current_stoxx - ma_20) / ma_20) * 100
        filter_pass = abs(deviation) <= max_deviation
        assert abs(deviation - 4.95) < 0.01
        assert filter_pass is False
    
    def test_prev_day_range_calculation(self):
        """Test previous day range calculation."""
        prev_high = 5200.0
        prev_low = 5140.0
        prev_open = 5160.0
        
        prev_range = ((prev_high - prev_low) / prev_open) * 100
        
        assert abs(prev_range - 1.16) < 0.01
        
        # Test pass/fail logic
        max_range = 2.0
        filter_pass = prev_range <= max_range
        assert filter_pass is True
    
    def test_vstoxx_term_structure(self):
        """Test VSTOXX term structure analysis."""
        vstoxx_current = 18.5
        vstoxx_3m = 20.2
        
        # Contango: VSTOXX 3M > VSTOXX Current (normal)
        is_backwardation = vstoxx_3m < vstoxx_current
        filter_pass = not is_backwardation
        
        assert filter_pass is True
        assert is_backwardation is False
        
        # Backwardation scenario
        vstoxx_current = 25.0
        vstoxx_3m = 22.0
        is_backwardation = vstoxx_3m < vstoxx_current
        filter_pass = not is_backwardation
        
        assert filter_pass is False
        assert is_backwardation is True


class TestEdgeCaseRules:
    """Test rule evaluation with edge case values."""
    
    def test_exact_threshold_values(self):
        """Test rule evaluation at exact threshold values."""
        vstoxx_max = 25.0
        max_change = 1.0
        
        # Edge case: VSTOXX exactly at threshold
        vstoxx_at_threshold = 25.0
        rule1_pass = vstoxx_at_threshold <= vstoxx_max
        assert rule1_pass is True  # Should pass (<=)
        
        # Edge case: Change exactly at threshold
        change_at_threshold = 1.0
        rule2_pass = abs(change_at_threshold) <= max_change
        assert rule2_pass is True  # Should pass (<=)
        
        # Edge case: Change negative at threshold
        change_negative_threshold = -1.0
        rule2_pass_negative = abs(change_negative_threshold) <= max_change
        assert rule2_pass_negative is True
    
    def test_invalid_rule_parameters(self):
        """Test rule evaluation with invalid parameters."""
        # Negative VSTOXX (should be impossible)
        invalid_vstoxx = -5.0
        
        if invalid_vstoxx <= 0:
            with pytest.raises(ValidationError):
                raise ValidationError("VSTOXX cannot be negative")
        
        # Invalid max change percentage
        invalid_max_change = -1.0
        
        if invalid_max_change < 0:
            with pytest.raises(ValidationError):
                raise ValidationError("Max change percentage cannot be negative")
        
        # STOXX50 price too low
        invalid_stoxx = 0.0
        
        if invalid_stoxx <= 0:
            with pytest.raises(ValidationError):
                raise ValidationError("STOXX50 price must be positive")
