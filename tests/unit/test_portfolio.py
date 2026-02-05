"""
Unit tests for shadow portfolio tracking.
"""

import pytest
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import portfolio as pf
from exceptions import PortfolioError


class TestCalculatePnl:
    """Test P&L calculation logic."""

    def test_max_profit_within_range(self):
        """Test max profit when price stays within strikes."""
        pnl = pf.calculate_pnl(
            stoxx_close=5200,
            call_strike=5250,
            put_strike=5150,
            wing_width=50,
            credit=2.50
        )
        # Max profit = credit * multiplier = 2.50 * 10 = 25
        assert pnl == 25.0

    def test_put_breach_partial(self):
        """Test partial put side breach."""
        pnl = pf.calculate_pnl(
            stoxx_close=5130,  # 20 points below put strike
            call_strike=5250,
            put_strike=5150,
            wing_width=50,
            credit=2.50
        )
        # intrinsic = 5150 - 5130 = 20
        # loss = min(20, 50) - 2.50 = 17.50
        # pnl = -17.50 * 10 = -175
        assert pnl == -175.0

    def test_put_breach_max_loss(self):
        """Test max loss when put fully breached beyond wing."""
        pnl = pf.calculate_pnl(
            stoxx_close=5050,  # 100 points below put strike
            call_strike=5250,
            put_strike=5150,
            wing_width=50,
            credit=2.50
        )
        # intrinsic = 5150 - 5050 = 100, capped at wing_width 50
        # loss = min(100, 50) - 2.50 = 47.50
        # pnl = -47.50 * 10 = -475
        assert pnl == -475.0

    def test_call_breach_partial(self):
        """Test partial call side breach."""
        pnl = pf.calculate_pnl(
            stoxx_close=5270,  # 20 points above call strike
            call_strike=5250,
            put_strike=5150,
            wing_width=50,
            credit=2.50
        )
        # intrinsic = 5270 - 5250 = 20
        # loss = min(20, 50) - 2.50 = 17.50
        # pnl = -17.50 * 10 = -175
        assert pnl == -175.0

    def test_call_breach_max_loss(self):
        """Test max loss when call fully breached beyond wing."""
        pnl = pf.calculate_pnl(
            stoxx_close=5350,  # 100 points above call strike
            call_strike=5250,
            put_strike=5150,
            wing_width=50,
            credit=2.50
        )
        # intrinsic = 5350 - 5250 = 100, capped at wing_width 50
        # loss = min(100, 50) - 2.50 = 47.50
        # pnl = -47.50 * 10 = -475
        assert pnl == -475.0

    def test_exactly_at_put_strike(self):
        """Test when price exactly at put strike."""
        pnl = pf.calculate_pnl(
            stoxx_close=5150,  # Exactly at put strike
            call_strike=5250,
            put_strike=5150,
            wing_width=50,
            credit=2.50
        )
        # intrinsic = 5150 - 5150 = 0
        # loss = min(0, 50) - 2.50 = -2.50 (negative loss = profit)
        # pnl = 2.50 * 10 = 25 (breakeven edge case)
        assert pnl == 25.0

    def test_exactly_at_call_strike(self):
        """Test when price exactly at call strike."""
        pnl = pf.calculate_pnl(
            stoxx_close=5250,  # Exactly at call strike
            call_strike=5250,
            put_strike=5150,
            wing_width=50,
            credit=2.50
        )
        # intrinsic = 5250 - 5250 = 0
        # loss = min(0, 50) - 2.50 = -2.50 (negative loss = profit)
        # pnl = 2.50 * 10 = 25 (breakeven edge case)
        assert pnl == 25.0

    def test_different_credit(self):
        """Test with different credit amount."""
        pnl = pf.calculate_pnl(
            stoxx_close=5200,
            call_strike=5250,
            put_strike=5150,
            wing_width=50,
            credit=3.00
        )
        assert pnl == 30.0  # 3.00 * 10

    def test_different_wing_width(self):
        """Test with different wing width."""
        pnl = pf.calculate_pnl(
            stoxx_close=5080,  # Breach put by 70 points
            call_strike=5250,
            put_strike=5150,
            wing_width=25,  # Smaller wing
            credit=2.50
        )
        # intrinsic = 5150 - 5080 = 70, capped at wing_width 25
        # loss = min(70, 25) - 2.50 = 22.50
        # pnl = -22.50 * 10 = -225
        assert pnl == -225.0


class TestPortfolioStorage:
    """Test portfolio load/save operations."""

    def test_create_empty_portfolio(self):
        """Test creating empty portfolio structure."""
        data = pf.create_empty_portfolio()

        assert data["version"] == 1
        assert "portfolios" in data
        assert "always_trade" in data["portfolios"]
        assert "filtered" in data["portfolios"]

        for portfolio_name in ["always_trade", "filtered"]:
            p = data["portfolios"][portfolio_name]
            assert p["total_pnl"] == 0.0
            assert p["trade_count"] == 0
            assert p["win_count"] == 0
            assert p["open_trade"] is None
            assert p["history"] == []

    def test_load_creates_if_missing(self, tmp_path):
        """Test that load creates file if missing."""
        portfolio_path = tmp_path / "test_portfolio.json"
        assert not portfolio_path.exists()

        data = pf.load_portfolio(portfolio_path)

        assert portfolio_path.exists()
        assert data["version"] == 1

    def test_load_existing_file(self, tmp_path):
        """Test loading existing portfolio file."""
        portfolio_path = tmp_path / "test_portfolio.json"

        # Create a file with some data
        test_data = pf.create_empty_portfolio()
        test_data["portfolios"]["always_trade"]["total_pnl"] = 100.0

        with open(portfolio_path, 'w') as f:
            json.dump(test_data, f)

        data = pf.load_portfolio(portfolio_path)
        assert data["portfolios"]["always_trade"]["total_pnl"] == 100.0

    def test_load_corrupted_file(self, tmp_path):
        """Test loading corrupted JSON file."""
        portfolio_path = tmp_path / "test_portfolio.json"

        with open(portfolio_path, 'w') as f:
            f.write("not valid json {{{")

        with pytest.raises(PortfolioError, match="Corrupted"):
            pf.load_portfolio(portfolio_path)

    def test_load_invalid_structure(self, tmp_path):
        """Test loading file with invalid structure."""
        portfolio_path = tmp_path / "test_portfolio.json"

        with open(portfolio_path, 'w') as f:
            json.dump({"version": 1}, f)  # Missing portfolios key

        with pytest.raises(PortfolioError, match="missing 'portfolios'"):
            pf.load_portfolio(portfolio_path)

    def test_save_portfolio(self, tmp_path):
        """Test saving portfolio data."""
        portfolio_path = tmp_path / "test_portfolio.json"
        data = pf.create_empty_portfolio()
        data["portfolios"]["filtered"]["total_pnl"] = 250.0

        pf.save_portfolio(data, portfolio_path)

        with open(portfolio_path, 'r') as f:
            loaded = json.load(f)

        assert loaded["portfolios"]["filtered"]["total_pnl"] == 250.0


class TestTradeOperations:
    """Test trade recording and settlement."""

    def test_record_trade_entry(self):
        """Test recording a new trade entry."""
        data = pf.create_empty_portfolio()
        trade_info = {
            "date": "2026-02-05",
            "stoxx_entry": 5180.0,
            "call_strike": 5232,
            "put_strike": 5128,
            "wing_width": 50,
            "credit": 2.50
        }

        result = pf.record_trade_entry("always_trade", trade_info, data)

        assert result is True
        assert data["portfolios"]["always_trade"]["open_trade"] == trade_info

    def test_record_duplicate_trade(self):
        """Test that duplicate trade for same day returns False."""
        data = pf.create_empty_portfolio()
        trade_info = {
            "date": "2026-02-05",
            "stoxx_entry": 5180.0,
            "call_strike": 5232,
            "put_strike": 5128,
            "wing_width": 50,
            "credit": 2.50
        }

        pf.record_trade_entry("always_trade", trade_info, data)
        result = pf.record_trade_entry("always_trade", trade_info, data)

        assert result is False

    def test_settle_open_trade_win(self):
        """Test settling an open trade with a win."""
        data = pf.create_empty_portfolio()
        data["portfolios"]["always_trade"]["open_trade"] = {
            "date": "2026-02-05",
            "stoxx_entry": 5180.0,
            "call_strike": 5232,
            "put_strike": 5128,
            "wing_width": 50,
            "credit": 2.50
        }

        pnl = pf.settle_open_trade("always_trade", 5200.0, data)

        assert pnl == 25.0  # Max profit
        assert data["portfolios"]["always_trade"]["open_trade"] is None
        assert data["portfolios"]["always_trade"]["total_pnl"] == 25.0
        assert data["portfolios"]["always_trade"]["trade_count"] == 1
        assert data["portfolios"]["always_trade"]["win_count"] == 1
        assert len(data["portfolios"]["always_trade"]["history"]) == 1
        assert data["portfolios"]["always_trade"]["history"][0]["outcome"] == "win"

    def test_settle_open_trade_loss(self):
        """Test settling an open trade with a loss."""
        data = pf.create_empty_portfolio()
        data["portfolios"]["filtered"]["open_trade"] = {
            "date": "2026-02-05",
            "stoxx_entry": 5180.0,
            "call_strike": 5232,
            "put_strike": 5128,
            "wing_width": 50,
            "credit": 2.50
        }

        # Price breaches put side by 30 points
        pnl = pf.settle_open_trade("filtered", 5098.0, data)

        # intrinsic = 5128 - 5098 = 30
        # loss = 30 - 2.50 = 27.50
        # pnl = -27.50 * 10 = -275
        assert pnl == -275.0
        assert data["portfolios"]["filtered"]["total_pnl"] == -275.0
        assert data["portfolios"]["filtered"]["win_count"] == 0
        assert data["portfolios"]["filtered"]["history"][0]["outcome"] == "loss"

    def test_settle_no_open_trade(self):
        """Test settling when no open trade exists."""
        data = pf.create_empty_portfolio()

        pnl = pf.settle_open_trade("always_trade", 5200.0, data)

        assert pnl is None
        assert data["portfolios"]["always_trade"]["trade_count"] == 0

    def test_has_open_trade(self):
        """Test checking for open trades."""
        data = pf.create_empty_portfolio()

        assert pf.has_open_trade("always_trade", data) is False

        data["portfolios"]["always_trade"]["open_trade"] = {"date": "2026-02-05"}

        assert pf.has_open_trade("always_trade", data) is True


class TestPortfolioSummary:
    """Test portfolio summary generation."""

    def test_get_portfolio_summary_empty(self):
        """Test summary with empty portfolios."""
        data = pf.create_empty_portfolio()
        summary = pf.get_portfolio_summary(data)

        assert summary["always_trade"]["total_pnl"] == 0.0
        assert summary["always_trade"]["win_rate"] == 0
        assert summary["filter_edge"] == 0.0

    def test_get_portfolio_summary_with_trades(self):
        """Test summary with trades."""
        data = pf.create_empty_portfolio()
        data["portfolios"]["always_trade"]["total_pnl"] = 100.0
        data["portfolios"]["always_trade"]["trade_count"] = 10
        data["portfolios"]["always_trade"]["win_count"] = 7
        data["portfolios"]["filtered"]["total_pnl"] = 175.0
        data["portfolios"]["filtered"]["trade_count"] = 5
        data["portfolios"]["filtered"]["win_count"] = 4

        summary = pf.get_portfolio_summary(data)

        assert summary["always_trade"]["win_rate"] == 70.0
        assert summary["filtered"]["win_rate"] == 80.0
        assert summary["filter_edge"] == 75.0  # 175 - 100

    def test_format_portfolio_display(self):
        """Test console display formatting."""
        data = pf.create_empty_portfolio()
        data["portfolios"]["always_trade"]["total_pnl"] = 150.0
        data["portfolios"]["always_trade"]["trade_count"] = 10
        data["portfolios"]["always_trade"]["win_count"] = 7

        output = pf.format_portfolio_display(data)

        assert "SHADOW PORTFOLIO STATUS" in output
        assert "ALWAYS TRADE" in output
        assert "FILTERED" in output
        assert "+150" in output
        assert "70.0%" in output

    def test_format_portfolio_telegram(self):
        """Test Telegram message formatting."""
        data = pf.create_empty_portfolio()
        data["portfolios"]["always_trade"]["total_pnl"] = 100.0
        data["portfolios"]["always_trade"]["trade_count"] = 5
        data["portfolios"]["always_trade"]["win_count"] = 3
        data["portfolios"]["filtered"]["total_pnl"] = 150.0
        data["portfolios"]["filtered"]["trade_count"] = 3
        data["portfolios"]["filtered"]["win_count"] = 2

        output = pf.format_portfolio_telegram(data)

        assert "Portfolio Update" in output
        assert "Always:" in output
        assert "Filtered:" in output
        assert "Edge: +50" in output


class TestResetPortfolio:
    """Test portfolio reset functionality."""

    def test_reset_single_portfolio(self):
        """Test resetting a single portfolio."""
        data = pf.create_empty_portfolio()
        data["portfolios"]["always_trade"]["total_pnl"] = 500.0
        data["portfolios"]["filtered"]["total_pnl"] = 300.0

        pf.reset_portfolio(data, "always_trade")

        assert data["portfolios"]["always_trade"]["total_pnl"] == 0.0
        assert data["portfolios"]["filtered"]["total_pnl"] == 300.0  # Unchanged

    def test_reset_both_portfolios(self):
        """Test resetting both portfolios."""
        data = pf.create_empty_portfolio()
        data["portfolios"]["always_trade"]["total_pnl"] = 500.0
        data["portfolios"]["filtered"]["total_pnl"] = 300.0

        pf.reset_portfolio(data)

        assert data["portfolios"]["always_trade"]["total_pnl"] == 0.0
        assert data["portfolios"]["filtered"]["total_pnl"] == 0.0


class TestGetPreviousClose:
    """Test fetching previous day's close price."""

    @patch('yfinance.Ticker')
    def test_get_previous_close_success(self, mock_ticker):
        """Test successful fetch of previous close."""
        import pandas as pd

        mock_stoxx = MagicMock()
        mock_stoxx.history.return_value = pd.DataFrame({
            'Close': [5150.0, 5180.0, 5200.0]
        })
        mock_ticker.return_value = mock_stoxx

        prev_close = pf.get_previous_close()

        assert prev_close == 5180.0  # Second to last

    @patch('yfinance.Ticker')
    def test_get_previous_close_single_day(self, mock_ticker):
        """Test when only one day of data available."""
        import pandas as pd

        mock_stoxx = MagicMock()
        mock_stoxx.history.return_value = pd.DataFrame({
            'Close': [5200.0]
        })
        mock_ticker.return_value = mock_stoxx

        prev_close = pf.get_previous_close()

        assert prev_close == 5200.0

    @patch('yfinance.Ticker')
    def test_get_previous_close_no_data(self, mock_ticker):
        """Test when no data available."""
        import pandas as pd

        mock_stoxx = MagicMock()
        mock_stoxx.history.return_value = pd.DataFrame()
        mock_ticker.return_value = mock_stoxx

        prev_close = pf.get_previous_close()

        assert prev_close is None
