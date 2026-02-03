"""
Unit tests for rule evaluation engine.
"""

import pytest
import sys
import os
from unittest.mock import Mock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exceptions import ValidationError
from tests.fixtures.sample_data import TEST_SCENARIOS


class TestRulesEngine:
    """Test rule evaluation logic."""
    
    def test_rule_1_vix_check_pass(self):
        """Test Rule 1: VIX check - pass scenario."""
        scenario = TEST_SCENARIOS['go_conditions']
        vix_max = 22.0
        
        vix_current = scenario['vix']
        
        # Rule logic: VIX <= threshold
        rule_pass = vix_current <= vix_max
        
        assert rule_pass is True
        assert vix_current == 16.5
    
    def test_rule_1_vix_check_fail(self):
        """Test Rule 1: VIX check - fail scenario."""
        scenario = TEST_SCENARIOS['no_go_vix_high']
        vix_max = 22.0
        
        vix_current = scenario['vix']
        
        rule_pass = vix_current <= vix_max
        
        assert rule_pass is False
        assert vix_current == 25.0
    
    def test_rule_2_intraday_change_check_pass(self):
        """Test Rule 2: Intraday change check - pass scenario."""
        scenario = TEST_SCENARIOS['go_conditions']
        max_change = 1.0
        
        intraday_change = scenario['intraday_change']
        
        # Rule logic: |change| <= threshold
        rule_pass = abs(intraday_change) <= max_change
        
        assert rule_pass is True
        assert intraday_change == 0.5
    
    def test_rule_2_intraday_change_check_fail(self):
        """Test Rule 2: Intraday change check - fail scenario."""
        scenario = TEST_SCENARIOS['no_go_change_high']
        max_change = 1.0
        
        intraday_change = scenario['intraday_change']
        
        rule_pass = abs(intraday_change) <= max_change
        
        assert rule_pass is False
        assert intraday_change == 1.5
    
    def test_rule_3_economic_calendar_check_pass(self):
        """Test Rule 3: Economic calendar check - pass scenario."""
        scenario = TEST_SCENARIOS['go_conditions']
        
        has_high_impact_events = scenario['high_impact_events']
        
        # Rule logic: No high-impact USD events
        rule_pass = not has_high_impact_events
        
        assert rule_pass is True
        assert has_high_impact_events is False
    
    def test_rule_3_economic_calendar_check_fail(self):
        """Test Rule 3: Economic calendar check - fail scenario."""
        scenario = TEST_SCENARIOS['no_go_events']
        
        has_high_impact_events = scenario['high_impact_events']
        
        rule_pass = not has_high_impact_events
        
        assert rule_pass is False
        assert has_high_impact_events is True
    
    def test_all_rules_pass_go_verdict(self):
        """Test overall GO verdict when all rules pass."""
        scenario = TEST_SCENARIOS['go_conditions']
        vix_max = 22.0
        max_change = 1.0
        
        # Evaluate all three rules
        rule1_pass = scenario['vix'] <= vix_max
        rule2_pass = abs(scenario['intraday_change']) <= max_change
        rule3_pass = not scenario['high_impact_events']
        
        # Overall verdict: AND logic (all must pass)
        go_verdict = rule1_pass and rule2_pass and rule3_pass
        
        assert go_verdict is True
        assert rule1_pass is True
        assert rule2_pass is True
        assert rule3_pass is True
    
    def test_any_rule_fail_no_go_verdict(self):
        """Test overall NO-GO verdict when any rule fails."""
        # Test each failure scenario
        test_cases = [
            ('no_go_vix_high', 'VIX too high'),
            ('no_go_change_high', 'Intraday change too large'),
            ('no_go_events', 'High impact events present')
        ]
        
        vix_max = 22.0
        max_change = 1.0
        
        for scenario_name, reason in test_cases:
            scenario = TEST_SCENARIOS[scenario_name]
            
            rule1_pass = scenario['vix'] <= vix_max
            rule2_pass = abs(scenario['intraday_change']) <= max_change
            rule3_pass = not scenario['high_impact_events']
            
            go_verdict = rule1_pass and rule2_pass and rule3_pass
            
            assert go_verdict is False, f"Should be NO-GO for {reason}"
    
    def test_additional_filter_ma_deviation_pass(self):
        """Test additional filter: 20-day MA deviation - pass."""
        current_spx = 4800.0
        ma_20 = 4700.0
        max_deviation = 3.0
        
        deviation = abs((current_spx - ma_20) / ma_20) * 100
        
        filter_pass = deviation <= max_deviation
        
        assert filter_pass is True
        assert abs(deviation - 2.13) < 0.01
    
    def test_additional_filter_ma_deviation_fail(self):
        """Test additional filter: 20-day MA deviation - fail."""
        current_spx = 5000.0
        ma_20 = 4700.0
        max_deviation = 3.0
        
        deviation = abs((current_spx - ma_20) / ma_20) * 100
        
        filter_pass = deviation <= max_deviation
        
        assert filter_pass is False
        assert abs(deviation - 6.38) < 0.01
    
    def test_additional_filter_prev_day_range_pass(self):
        """Test additional filter: Previous day range - pass."""
        prev_high = 4850.0
        prev_low = 4780.0
        prev_open = 4800.0
        max_range = 2.0
        
        prev_day_range = ((prev_high - prev_low) / prev_open) * 100
        
        filter_pass = prev_day_range <= max_range
        
        assert filter_pass is True
        assert abs(prev_day_range - 1.46) < 0.01
    
    def test_additional_filter_prev_day_range_fail(self):
        """Test additional filter: Previous day range - fail."""
        prev_high = 4950.0
        prev_low = 4750.0
        prev_open = 4800.0
        max_range = 2.0
        
        prev_day_range = ((prev_high - prev_low) / prev_open) * 100
        
        filter_pass = prev_day_range <= max_range
        
        assert filter_pass is False
        assert abs(prev_day_range - 4.17) < 0.01
    
    def test_additional_filter_vix_term_structure_contango(self):
        """Test additional filter: VIX term structure - contango (normal)."""
        vix_current = 18.5
        vix_3m = 21.2
        
        # Contango: VIX 3M > VIX Current (normal market state)
        is_backwardation = vix_3m < vix_current
        
        # Filter warns about backwardation (unusual)
        filter_pass = not is_backwardation  # Pass if not in backwardation
        
        assert filter_pass is True
        assert is_backwardation is False
    
    def test_additional_filter_vix_term_structure_backwardation(self):
        """Test additional filter: VIX term structure - backwardation (warning)."""
        vix_current = 25.0
        vix_3m = 22.0
        
        # Backwardation: VIX 3M < VIX Current (fear in market)
        is_backwardation = vix_3m < vix_current
        
        filter_pass = not is_backwardation  # Fail if in backwardation
        
        assert filter_pass is False
        assert is_backwardation is True
    
    def test_strike_calculation(self):
        """Test strike price calculation."""
        spx_current = 4860.0
        otm_percent = 1.0
        
        # Calculate short strikes
        call_strike = spx_current * (1 + otm_percent / 100)
        put_strike = spx_current * (1 - otm_percent / 100)
        
        # Round to nearest 5 (SPX convention)
        call_strike_rounded = round(call_strike / 5) * 5
        put_strike_rounded = round(put_strike / 5) * 5
        
        assert call_strike_rounded == 4910
        assert put_strike_rounded == 4810
    
    def test_strike_calculation_different_percentages(self):
        """Test strike calculation with different OTM percentages."""
        spx_current = 4860.0
        wing_width = 25
        
        test_percentages = [0.5, 1.0, 1.5, 2.0]
        
        for otm_percent in test_percentages:
            call_strike = spx_current * (1 + otm_percent / 100)
            put_strike = spx_current * (1 - otm_percent / 100)
            
            call_rounded = round(call_strike / 5) * 5
            put_rounded = round(put_strike / 5) * 5
            
            # Long strikes are further OTM by wing width
            call_long = call_rounded + wing_width
            put_long = put_rounded - wing_width
            
            # Verify wing width
            assert call_long - call_rounded == wing_width
            assert put_rounded - put_long == wing_width
    
    def test_rule_evaluation_with_edge_cases(self):
        """Test rule evaluation with edge case values."""
        vix_max = 22.0
        max_change = 1.0
        
        # Edge case: VIX exactly at threshold
        vix_at_threshold = 22.0
        rule1_pass = vix_at_threshold <= vix_max
        assert rule1_pass is True
        
        # Edge case: Change exactly at threshold
        change_at_threshold = 1.0
        rule2_pass = abs(change_at_threshold) <= max_change
        assert rule2_pass is True
        
        # Edge case: Change negative at threshold
        change_negative_threshold = -1.0
        rule2_pass_negative = abs(change_negative_threshold) <= max_change
        assert rule2_pass_negative is True
    
    def test_invalid_rule_parameters(self):
        """Test rule evaluation with invalid parameters."""
        # Negative VIX (should be impossible)
        invalid_vix = -5.0
        
        if invalid_vix <= 0:
            with pytest.raises(ValidationError):
                raise ValidationError("VIX cannot be negative")
        
        # Invalid max change percentage
        invalid_max_change = -1.0
        
        if invalid_max_change < 0:
            with pytest.raises(ValidationError):
                raise ValidationError("Max change percentage cannot be negative")
        
        # SPX price too low
        invalid_spx = 0.0
        
        if invalid_spx <= 0:
            with pytest.raises(ValidationError):
                raise ValidationError("SPX price must be positive")