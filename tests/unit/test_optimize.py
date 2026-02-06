"""
Unit tests for optimize.py - Backtest optimizer functionality.
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from optimize import (
    ParameterSet,
    BacktestResult,
    ParameterGrid,
    WalkForwardValidator,
    ResultsAnalyzer,
    evaluate_day,
    simulate_iron_condor,
    combine_results,
)


class TestParameterSet:
    """Test ParameterSet dataclass."""

    def test_create_params(self):
        """Test creating a parameter set."""
        params = ParameterSet(
            otm_percent=1.0,
            wing_width=50,
            intraday_change_max=1.0,
            credit=2.5
        )
        assert params.otm_percent == 1.0
        assert params.wing_width == 50
        assert params.intraday_change_max == 1.0
        assert params.credit == 2.5

    def test_params_equality(self):
        """Test parameter equality."""
        p1 = ParameterSet(1.0, 50, 1.0, 2.5)
        p2 = ParameterSet(1.0, 50, 1.0, 2.5)
        assert p1 == p2


class TestBacktestResult:
    """Test BacktestResult dataclass."""

    def test_create_result(self):
        """Test creating a backtest result."""
        params = ParameterSet(1.0, 50, 1.0, 2.5)
        result = BacktestResult(
            params=params,
            total_pnl=1000.0,
            trades=10,
            win_rate=70.0,
            profit_factor=1.5,
            max_drawdown=200.0,
            sharpe_ratio=1.2,
            sortino_ratio=1.8
        )
        assert result.total_pnl == 1000.0
        assert result.trades == 10
        assert result.win_rate == 70.0
        assert result.is_train is True

    def test_result_with_trades(self):
        """Test result with trade list."""
        params = ParameterSet(1.0, 50, 1.0, 2.5)
        trades = [
            {'date': '2024-01-02', 'pnl': 100, 'stoxx_close': 4500},
            {'date': '2024-01-03', 'pnl': -50, 'stoxx_close': 4520},
        ]
        result = BacktestResult(
            params=params,
            total_pnl=50,
            trades=2,
            win_rate=50.0,
            profit_factor=2.0,
            max_drawdown=50.0,
            sharpe_ratio=0.5,
            sortino_ratio=0.8,
            trades_list=trades
        )
        assert len(result.trades_list) == 2


class TestParameterGrid:
    """Test ParameterGrid class."""

    def test_generate_all_combinations(self):
        """Test generating all parameter combinations."""
        grid = ParameterGrid(
            otm_range=[0.5, 1.0],
            wing_range=[25, 50],
            intraday_range=[0.75, 1.0],
            credit_range=[2.0, 2.5]
        )
        params = grid.generate()

        assert len(params) == 16  # 2 * 2 * 2 * 2
        assert all(isinstance(p, ParameterSet) for p in params)

    def test_single_value_each(self):
        """Test grid with single value per parameter."""
        grid = ParameterGrid(
            otm_range=[1.0],
            wing_range=[50],
            intraday_range=[1.0],
            credit_range=[2.5]
        )
        params = grid.generate()

        assert len(params) == 1
        assert params[0].otm_percent == 1.0
        assert params[0].wing_width == 50

    def test_count_combinations(self):
        """Test counting combinations without generating."""
        grid = ParameterGrid(
            otm_range=[0.5, 0.75, 1.0, 1.25],
            wing_range=[25, 50, 75],
            intraday_range=[0.75, 1.0, 1.25],
            credit_range=[2.0, 2.5, 3.0]
        )
        assert grid.count() == 108  # 4 * 3 * 3 * 3


class TestEvaluateDay:
    """Test evaluate_day function."""

    def test_trade_allowed_low_change(self):
        """Test when intraday change is within threshold."""
        should_trade, reason, change, vix_warning = evaluate_day(
            vix_close=20.0,
            stoxx_open=4500.0,
            stoxx_close=4520.0,
            intraday_change_max=1.0
        )
        assert should_trade is True
        assert "Conditions met" in reason
        assert abs(change - 0.44) < 0.01
        assert vix_warning is False

    def test_trade_blocked_high_change(self):
        """Test when intraday change exceeds threshold."""
        should_trade, reason, change, vix_warning = evaluate_day(
            vix_close=20.0,
            stoxx_open=4500.0,
            stoxx_close=4600.0,
            intraday_change_max=1.0
        )
        assert should_trade is False
        assert "Trend too strong" in reason
        assert abs(change - 2.22) < 0.01

    def test_vix_warning_threshold(self):
        """Test VIX warning threshold."""
        _, _, _, warning_below = evaluate_day(
            vix_close=21.0, stoxx_open=4500, stoxx_close=4510, intraday_change_max=1.0
        )
        _, _, _, warning_above = evaluate_day(
            vix_close=23.0, stoxx_open=4500, stoxx_close=4510, intraday_change_max=1.0
        )
        assert warning_below is False
        assert warning_above is True

    def test_custom_threshold(self):
        """Test with custom intraday change threshold."""
        should_trade, _, change, _ = evaluate_day(
            vix_close=20.0,
            stoxx_open=4500.0,
            stoxx_close=4550.0,
            intraday_change_max=1.5
        )
        assert should_trade is True  # 1.11% < 1.5%

    def test_negative_change(self):
        """Test with negative intraday change."""
        should_trade, reason, change, _ = evaluate_day(
            vix_close=20.0,
            stoxx_open=4500.0,
            stoxx_close=4450.0,
            intraday_change_max=1.0
        )
        assert should_trade is False
        assert change < 0
        assert "Trend too strong" in reason


class TestSimulateIronCondor:
    """Test simulate_iron_condor function."""

    def test_max_profit(self):
        """Test when price stays within wings."""
        pnl = simulate_iron_condor(
            stoxx_close=4500,
            put_strike=4450,
            call_strike=4550,
            wing_width=50,
            credit=2.5
        )
        assert pnl == 25.0  # 2.5 * 10 multiplier

    def test_put_side_breach(self):
        """Test when put side is breached."""
        pnl = simulate_iron_condor(
            stoxx_close=4400,
            put_strike=4450,
            call_strike=4550,
            wing_width=50,
            credit=2.5
        )
        # Max loss: wing_width - credit = 50 - 2.5 = 47.5
        # But price at 4400, so intrinsic = 4450 - 4400 = 50
        # Loss = min(50, 47.5) = 47.5, so P&L = -47.5 * 10 = -475
        assert pnl == -475.0

    def test_call_side_breach(self):
        """Test when call side is breached."""
        pnl = simulate_iron_condor(
            stoxx_close=4600,
            put_strike=4450,
            call_strike=4550,
            wing_width=50,
            credit=2.5
        )
        # Intrinsic = 4600 - 4550 = 50, loss = 47.5 * 10 = -475
        assert pnl == -475.0

    def test_at_lower_strike(self):
        """Test at exactly the lower strike boundary - within range, max profit."""
        pnl = simulate_iron_condor(
            stoxx_close=4450,
            put_strike=4450,
            call_strike=4550,
            wing_width=50,
            credit=2.5
        )
        # At strike, not breached, max profit = credit * multiplier
        assert pnl == 25.0

    def test_at_upper_strike(self):
        """Test at exactly the upper strike boundary - within range, max profit."""
        pnl = simulate_iron_condor(
            stoxx_close=4550,
            put_strike=4450,
            call_strike=4550,
            wing_width=50,
            credit=2.5
        )
        # At strike, not breached, max profit = credit * multiplier
        assert pnl == 25.0


class TestCombineResults:
    """Test combine_results function."""

    def test_combine_single_result(self):
        """Test combining a single result."""
        params = ParameterSet(1.0, 50, 1.0, 2.5)
        result = BacktestResult(
            params=params,
            total_pnl=100,
            trades=5,
            win_rate=60.0,
            profit_factor=1.5,
            max_drawdown=50.0,
            sharpe_ratio=1.0,
            sortino_ratio=1.5,
            trades_list=[{'date': '2024-01-02', 'pnl': 20, 'stoxx_close': 4500}]
        )
        combined = combine_results([result])
        assert combined.total_pnl == 100
        assert combined.trades == 5

    def test_combine_multiple_results(self):
        """Test combining multiple window results."""
        params = ParameterSet(1.0, 50, 1.0, 2.5)
        r1 = BacktestResult(
            params=params, total_pnl=100, trades=3, win_rate=66.7,
            profit_factor=2.0, max_drawdown=30, sharpe_ratio=1.0,
            sortino_ratio=1.5,
            trades_list=[
                {'date': '2024-01-02', 'pnl': 25, 'stoxx_close': 4500},
                {'date': '2024-01-03', 'pnl': 25, 'stoxx_close': 4510},
                {'date': '2024-01-04', 'pnl': 50, 'stoxx_close': 4520}
            ]
        )
        r2 = BacktestResult(
            params=params, total_pnl=50, trades=2, win_rate=50.0,
            profit_factor=1.0, max_drawdown=40, sharpe_ratio=0.8,
            sortino_ratio=1.0,
            trades_list=[
                {'date': '2024-02-01', 'pnl': 25, 'stoxx_close': 4550},
                {'date': '2024-02-02', 'pnl': 25, 'stoxx_close': 4560}
            ]
        )
        combined = combine_results([r1, r2])
        assert combined.total_pnl == 150
        assert combined.trades == 5
        assert len(combined.trades_list) == 5

    def test_combine_max_drawdown(self):
        """Test max drawdown calculation."""
        params = ParameterSet(1.0, 50, 1.0, 2.5)
        r1 = BacktestResult(
            params=params, total_pnl=100, trades=2, win_rate=100.0,
            profit_factor=float('inf'), max_drawdown=0, sharpe_ratio=2.0,
            sortino_ratio=3.0,
            trades_list=[
                {'date': '2024-01-02', 'pnl': 100, 'stoxx_close': 4500},
                {'date': '2024-01-03', 'pnl': 0, 'stoxx_close': 4500}
            ]
        )
        combined = combine_results([r1])
        # After first trade: peak=100, drawdown=0
        # After second trade: cumulative=100, peak=100, drawdown=0
        assert combined.max_drawdown == 0


class TestResultsAnalyzer:
    """Test ResultsAnalyzer class."""

    def test_rank_by_sortino(self):
        """Test ranking by out-of-sample Sortino."""
        results = []

        for i, sortino in enumerate([1.5, 2.0, 0.5, 1.0]):
            params = ParameterSet(1.0, 50, 1.0, 2.5)
            train_res = BacktestResult(
                params=params, total_pnl=100, trades=10, win_rate=70.0,
                profit_factor=1.5, max_drawdown=50, sharpe_ratio=1.0,
                sortino_ratio=sortino * 1.2,
                trades_list=[]
            )
            test_res = BacktestResult(
                params=params, total_pnl=80, trades=8, win_rate=75.0,
                profit_factor=1.8, max_drawdown=40, sharpe_ratio=1.2,
                sortino_ratio=sortino,
                trades_list=[]
            )
            results.append((train_res, test_res))

        analyzer = ResultsAnalyzer(results)
        ranked = analyzer.rank()

        assert len(ranked) == 4
        assert ranked[0]['oos_sortino'] == 2.0  # Best
        assert ranked[0]['rank'] == 1
        assert ranked[-1]['oos_sortino'] == 0.5  # Worst
        assert ranked[-1]['rank'] == 4

    def test_robustness_calculation(self):
        """Test robustness score calculation."""
        params = ParameterSet(1.0, 50, 1.0, 2.5)
        train_res = BacktestResult(
            params=params, total_pnl=100, trades=10, win_rate=70.0,
            profit_factor=1.5, max_drawdown=50, sharpe_ratio=1.0,
            sortino_ratio=1.0,
            trades_list=[]
        )
        test_res = BacktestResult(
            params=params, total_pnl=80, trades=8, win_rate=75.0,
            profit_factor=1.8, max_drawdown=40, sharpe_ratio=1.2,
            sortino_ratio=0.8,
            trades_list=[]
        )
        analyzer = ResultsAnalyzer([(train_res, test_res)])
        ranked = analyzer.rank()

        # robustness = oos_sortino / is_sortino = 0.8 / 1.0 = 0.8
        assert abs(ranked[0]['robustness'] - 0.8) < 0.01


class TestWalkForwardValidator:
    """Test WalkForwardValidator class."""

    def test_validator_creation(self):
        """Test creating validator with custom windows."""
        validator = WalkForwardValidator(train_months=6, test_months=3)
        assert validator.train_months == 6
        assert validator.test_months == 3

    def test_default_windows(self):
        """Test default window sizes."""
        validator = WalkForwardValidator()
        assert validator.train_months == 6
        assert validator.test_months == 2
