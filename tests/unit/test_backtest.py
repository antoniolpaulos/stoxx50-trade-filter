"""
Unit tests for backtest functions - testing real functions from backtest.py.
"""

import pytest
import pandas as pd
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest import evaluate_day, simulate_iron_condor, get_historical_data
from exceptions import MarketDataError


class TestEvaluateDay:
    """Test evaluate_day function from backtest.py.

    Note: VIX is used as warning-only (VSTOXX unavailable via yfinance).
    evaluate_day returns (should_trade, reason, intraday_change, vix_warning).
    """

    def test_evaluate_day_should_trade(self):
        """Test evaluate_day returns should_trade=True when conditions are met."""
        vix_close = 18.5  # Below 22 warning threshold
        stoxx_open = 5180.0
        stoxx_entry = 5185.0  # 0.1% change

        should_trade, reason, intraday_change, vix_warning = evaluate_day(vix_close, stoxx_open, stoxx_entry)

        assert should_trade is True
        assert reason == "Conditions met"
        assert abs(intraday_change - 0.1) < 0.01
        assert vix_warning is False

    def test_evaluate_day_vix_warning_only(self):
        """Test evaluate_day still trades when VIX is high (warning only, not blocking)."""
        vix_close = 28.0  # Above 22 warning threshold
        stoxx_open = 5180.0
        stoxx_entry = 5185.0  # Small change

        should_trade, reason, intraday_change, vix_warning = evaluate_day(vix_close, stoxx_open, stoxx_entry)

        # VIX is warning-only, so should still trade
        assert should_trade is True
        assert reason == "Conditions met"
        assert vix_warning is True  # Warning flag set

    def test_evaluate_day_trend_too_strong_up(self):
        """Test evaluate_day returns should_trade=False when trend is too strong (up)."""
        vix_close = 18.5
        stoxx_open = 5180.0
        stoxx_entry = 5260.0  # ~1.54% up

        should_trade, reason, intraday_change, vix_warning = evaluate_day(vix_close, stoxx_open, stoxx_entry)

        assert should_trade is False
        assert "Trend too strong" in reason
        assert "1.54%" in reason or "+1.54%" in reason

    def test_evaluate_day_trend_too_strong_down(self):
        """Test evaluate_day returns should_trade=False when trend is too strong (down)."""
        vix_close = 18.5
        stoxx_open = 5180.0
        stoxx_entry = 5102.0  # ~1.51% down

        should_trade, reason, intraday_change, vix_warning = evaluate_day(vix_close, stoxx_open, stoxx_entry)

        assert should_trade is False
        assert "Trend too strong" in reason
        assert "1.51%" in reason or "-1.51%" in reason

    def test_evaluate_day_exact_thresholds(self):
        """Test evaluate_day at exact threshold values."""
        # VIX at warning threshold (22) - should still pass (warning only)
        vix_close = 22.0
        stoxx_open = 5180.0
        stoxx_entry = 5180.0

        should_trade, reason, intraday_change, vix_warning = evaluate_day(vix_close, stoxx_open, stoxx_entry)
        assert should_trade is True
        assert vix_warning is False  # Not > 22, so no warning

        # Change just under threshold (~0.99%) - should pass
        vix_close = 18.5
        stoxx_open = 5180.0
        stoxx_entry = 5231.0  # ~0.98% up (avoiding floating point boundary)

        should_trade, reason, intraday_change, vix_warning = evaluate_day(vix_close, stoxx_open, stoxx_entry)
        assert should_trade is True  # |change| <= 1.0
        assert intraday_change < 1.0

    def test_evaluate_day_intraday_calculation(self):
        """Test that intraday change is calculated correctly."""
        stoxx_open = 5180.0

        test_cases = [
            (5180.0, 0.0),   # No change
            (5229.8, 0.96),  # ~0.96% up
            (5130.2, -0.96), # ~0.96% down
            (5231.8, 1.0),   # Exactly 1.0% up
        ]

        for stoxx_entry, expected_change in test_cases:
            _, _, intraday_change, _ = evaluate_day(18.5, stoxx_open, stoxx_entry)
            assert abs(intraday_change - expected_change) < 0.01


class TestSimulateIronCondor:
    """Test simulate_iron_condor function from backtest.py."""
    
    def test_simulate_profitable_trade(self):
        """Test profitable trade when price stays within range."""
        entry_price = 5180.0
        stoxx_close = 5195.0  # Within range
        call_strike = 5232
        put_strike = 5128
        wing_width = 50
        credit = 2.50
        
        pnl = simulate_iron_condor(entry_price, stoxx_close, call_strike, put_strike, wing_width, credit)
        
        # Max profit: credit * multiplier
        expected_pnl = 2.50 * 10  # €25
        assert pnl == expected_pnl
    
    def test_simulate_put_side_breach(self):
        """Test loss when put side is breached."""
        entry_price = 5180.0
        stoxx_close = 5100.0  # Below put strike (5128)
        call_strike = 5232
        put_strike = 5128
        wing_width = 50
        credit = 2.50
        
        pnl = simulate_iron_condor(entry_price, stoxx_close, call_strike, put_strike, wing_width, credit)
        
        # Loss calculation: (5128 - 5100) - credit = 28 - 2.50 = 25.50
        # Then capped at wing_width - credit = 50 - 2.50 = 47.50
        # Since 25.50 < 47.50, loss is 25.50
        # P&L = -25.50 * 10 = -255.0
        expected_pnl = -255.0
        assert pnl == expected_pnl
    
    def test_simulate_call_side_breach(self):
        """Test loss when call side is breached."""
        entry_price = 5180.0
        stoxx_close = 5260.0  # Above call strike (5232)
        call_strike = 5232
        put_strike = 5128
        wing_width = 50
        credit = 2.50
        
        pnl = simulate_iron_condor(entry_price, stoxx_close, call_strike, put_strike, wing_width, credit)
        
        # Loss calculation: (5260 - 5232) - credit = 28 - 2.50 = 25.50
        # Since 25.50 < 47.50, loss is 25.50
        # P&L = -25.50 * 10 = -255.0
        expected_pnl = -255.0
        assert pnl == expected_pnl
    
    def test_simulate_max_loss_put_side(self):
        """Test maximum loss when put side is fully breached."""
        entry_price = 5180.0
        stoxx_close = 5000.0  # Far below put strike
        call_strike = 5232
        put_strike = 5128
        wing_width = 50
        credit = 2.50
        
        pnl = simulate_iron_condor(entry_price, stoxx_close, call_strike, put_strike, wing_width, credit)
        
        # Max loss: wing_width - credit = 50 - 2.50 = 47.50
        # P&L = -47.50 * 10 = -475.0
        expected_pnl = -475.0
        assert pnl == expected_pnl
    
    def test_simulate_max_loss_call_side(self):
        """Test maximum loss when call side is fully breached."""
        entry_price = 5180.0
        stoxx_close = 5400.0  # Far above call strike
        call_strike = 5232
        put_strike = 5128
        wing_width = 50
        credit = 2.50
        
        pnl = simulate_iron_condor(entry_price, stoxx_close, call_strike, put_strike, wing_width, credit)
        
        # Max loss: wing_width - credit = 50 - 2.50 = 47.50
        # P&L = -47.50 * 10 = -475.0
        expected_pnl = -475.0
        assert pnl == expected_pnl
    
    def test_simulate_different_credits(self):
        """Test simulation with different credit amounts."""
        entry_price = 5180.0
        stoxx_close = 5195.0  # Within range
        call_strike = 5232
        put_strike = 5128
        wing_width = 50
        
        test_credits = [2.00, 2.50, 3.00, 3.50]
        
        for credit in test_credits:
            pnl = simulate_iron_condor(entry_price, stoxx_close, call_strike, put_strike, wing_width, credit)
            expected_pnl = credit * 10  # €10 multiplier
            assert pnl == expected_pnl
    
    def test_simulate_different_wing_widths(self):
        """Test simulation with different wing widths."""
        entry_price = 5180.0
        stoxx_close = 5400.0  # Far above call strike
        call_strike = 5232
        put_strike = 5128
        credit = 2.50
        
        test_widths = [25, 50, 75, 100]
        
        for wing_width in test_widths:
            pnl = simulate_iron_condor(entry_price, stoxx_close, call_strike, put_strike, wing_width, credit)
            # Max loss: wing_width - credit
            expected_pnl = -(wing_width - credit) * 10
            assert pnl == expected_pnl
    
    def test_simulate_price_at_strike(self):
        """Test when price closes exactly at strike."""
        entry_price = 5180.0
        stoxx_close = 5232.0  # Exactly at call strike
        call_strike = 5232
        put_strike = 5128
        wing_width = 50
        credit = 2.50

        pnl = simulate_iron_condor(entry_price, stoxx_close, call_strike, put_strike, wing_width, credit)

        # At exactly the call strike, intrinsic = 0
        # Code treats >= as breach, but with 0 intrinsic:
        # loss = min(0, 50) - 2.50 = -2.50
        # return -(-2.50) * 10 = 25.0 (keeps full credit)
        expected_pnl = 25.0
        assert pnl == expected_pnl


class TestGetHistoricalData:
    """Test get_historical_data function with mocked yfinance.

    Note: Uses VIX (^VIX) instead of VSTOXX as VSTOXX is unavailable via yfinance.
    """

    @patch('backtest.yf.Ticker')
    def test_fetch_historical_data_success(self, mock_ticker):
        """Test successful historical data fetch."""
        # Create sample data
        dates = pd.date_range(start='2026-01-01', periods=30, freq='D')
        vix_data = pd.DataFrame({
            'Open': [18.0] * 30,
            'High': [19.0] * 30,
            'Low': [17.0] * 30,
            'Close': [18.5] * 30
        }, index=dates)

        stoxx_data = pd.DataFrame({
            'Open': [5180.0] * 30,
            'High': [5200.0] * 30,
            'Low': [5160.0] * 30,
            'Close': [5180.0] * 30
        }, index=dates)

        def mock_ticker_side_effect(symbol):
            mock = Mock()
            if symbol == '^VIX':
                mock.history.return_value = vix_data
            elif symbol == '^STOXX50E':
                mock.history.return_value = stoxx_data
            return mock

        mock_ticker.side_effect = mock_ticker_side_effect

        vix_result, stoxx_result = get_historical_data('2026-01-01', '2026-01-30')

        assert not vix_result.empty
        assert not stoxx_result.empty
        assert 'Close' in vix_result.columns
        assert 'Close' in stoxx_result.columns
    
    @patch('backtest.yf.Ticker')
    def test_fetch_historical_data_failure(self, mock_ticker):
        """Test handling of historical data fetch failure."""
        mock_ticker.side_effect = Exception("Network error")
        
        with pytest.raises(Exception):
            get_historical_data('2026-01-01', '2026-01-30')


class TestBacktestIntegration:
    """Test backtest integration scenarios."""

    def test_full_day_evaluation_profit(self):
        """Test full day evaluation with profitable outcome."""
        # Day parameters
        vix_close = 18.5
        stoxx_open = 5180.0
        stoxx_entry = 5185.0
        stoxx_close = 5190.0

        # Evaluate trading decision
        should_trade, reason, intraday_change, vix_warning = evaluate_day(vix_close, stoxx_open, stoxx_entry)

        assert should_trade is True

        # Calculate strikes
        from trade_filter import calculate_strikes
        call_strike, put_strike = calculate_strikes(stoxx_entry, 1.0, 50)

        # Simulate P&L
        pnl = simulate_iron_condor(stoxx_entry, stoxx_close, call_strike, put_strike, 50, 2.50)

        assert pnl == 25.0  # Max profit

    def test_full_day_evaluation_loss(self):
        """Test full day evaluation with loss outcome."""
        # Day parameters
        vix_close = 18.5
        stoxx_open = 5180.0
        stoxx_entry = 5185.0
        stoxx_close = 5100.0  # Put side breached

        # Evaluate trading decision
        should_trade, reason, intraday_change, vix_warning = evaluate_day(vix_close, stoxx_open, stoxx_entry)

        assert should_trade is True  # Would still trade

        # Calculate strikes
        from trade_filter import calculate_strikes
        call_strike, put_strike = calculate_strikes(stoxx_entry, 1.0, 50)

        # Simulate P&L
        pnl = simulate_iron_condor(stoxx_entry, stoxx_close, call_strike, put_strike, 50, 2.50)

        assert pnl < 0  # Loss

    def test_full_day_no_trade_trend_too_strong(self):
        """Test full day evaluation when no trade is taken due to trend."""
        # Day parameters - trend too strong (change > 1%)
        vix_close = 18.0
        stoxx_open = 5180.0
        stoxx_entry = 5260.0  # ~1.54% change - too strong
        stoxx_close = 5190.0

        # Evaluate trading decision
        should_trade, reason, intraday_change, vix_warning = evaluate_day(vix_close, stoxx_open, stoxx_entry)

        assert should_trade is False
        assert "Trend too strong" in reason
        # No trade taken, so no P&L to calculate
        assert intraday_change is not None  # But we still calculated the change


class TestBacktestEdgeCases:
    """Test backtest edge cases.

    Note: VIX is warning-only, not a blocking rule.
    """

    def test_evaluate_day_extreme_vix(self):
        """Test evaluate_day with extreme VIX values (warning only)."""
        # Very high VIX - still trades but with warning
        should_trade, reason, _, vix_warning = evaluate_day(100.0, 5180.0, 5185.0)
        assert should_trade is True  # VIX is warning-only
        assert vix_warning is True

        # Very low VIX - trades without warning
        should_trade, reason, _, vix_warning = evaluate_day(5.0, 5180.0, 5185.0)
        assert should_trade is True
        assert vix_warning is False

    def test_evaluate_day_extreme_price_changes(self):
        """Test evaluate_day with extreme price changes."""
        # Extreme up move
        should_trade, reason, _, _ = evaluate_day(18.5, 5180.0, 5700.0)
        assert should_trade is False
        assert "Trend too strong" in reason

        # Extreme down move
        should_trade, reason, _, _ = evaluate_day(18.5, 5180.0, 4662.0)
        assert should_trade is False
        assert "Trend too strong" in reason

    def test_simulate_zero_wing_width(self):
        """Test simulation with zero wing width."""
        # Price within range - keeps full credit
        pnl = simulate_iron_condor(5180.0, 5195.0, 5232, 5128, 0, 2.50)
        expected_pnl = 25.0  # credit * 10
        assert pnl == expected_pnl
    
    def test_simulate_zero_credit(self):
        """Test simulation with zero credit."""
        pnl = simulate_iron_condor(5180.0, 5195.0, 5232, 5128, 50, 0)
        # No credit, so profit is 0
        assert pnl == 0.0
    
    def test_simulate_large_wing_width(self):
        """Test simulation with large wing width hitting max loss."""
        # Close far enough beyond call strike to hit max loss
        # call_strike + wing_width = 5232 + 200 = 5432
        pnl = simulate_iron_condor(5180.0, 5500.0, 5232, 5128, 200, 2.50)
        # Max loss: 200 - 2.50 = 197.50
        expected_pnl = -1975.0  # -197.50 * 10
        assert pnl == expected_pnl
