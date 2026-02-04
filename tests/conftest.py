"""
Pytest configuration and shared fixtures for STOXX50 Trade Filter tests.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import fixtures from sample_data
from tests.fixtures.sample_data import (
    SAMPLE_VIX_DATA,
    SAMPLE_STOXX50_DATA,
    SAMPLE_VSTOXX_DATA,
    SAMPLE_VSTOXX3M_DATA,
    SAMPLE_CONFIG,
    SAMPLE_CALENDAR_EVENTS,
    TEST_SCENARIOS,
    INVALID_MARKET_DATA,
    TICKERS,
    BACKTEST_DEFAULTS,
    SAMPLE_TELEGRAM_CONFIG,
    SAMPLE_BACKTEST_RESULT,
)


@pytest.fixture
def sample_config():
    """Provide sample configuration for tests."""
    return SAMPLE_CONFIG.copy()


@pytest.fixture
def sample_vix_data():
    """Provide sample VIX data (for reference/backup)."""
    return SAMPLE_VIX_DATA.copy()


@pytest.fixture
def sample_stoxx50_data():
    """Provide sample STOXX50 data."""
    return SAMPLE_STOXX50_DATA.copy()


@pytest.fixture
def sample_vstoxx_data():
    """Provide sample VSTOXX data."""
    return SAMPLE_VSTOXX_DATA.copy()


@pytest.fixture
def sample_vstoxx3m_data():
    """Provide sample VSTOXX 3M data."""
    return SAMPLE_VSTOXX3M_DATA.copy()


@pytest.fixture
def go_scenario():
    """Provide GO conditions scenario."""
    return TEST_SCENARIOS['go_conditions'].copy()


@pytest.fixture
def no_go_vstoxx_scenario():
    """Provide NO-GO VSTOXX scenario."""
    return TEST_SCENARIOS['no_go_vstoxx_high'].copy()


@pytest.fixture
def no_go_change_scenario():
    """Provide NO-GO intraday change scenario."""
    return TEST_SCENARIOS['no_go_change_high'].copy()


@pytest.fixture
def no_go_events_scenario():
    """Provide NO-GO events scenario."""
    return TEST_SCENARIOS['no_go_events'].copy()


@pytest.fixture
def invalid_market_data():
    """Provide invalid market data samples."""
    return INVALID_MARKET_DATA.copy()


@pytest.fixture
def tickers():
    """Provide market data tickers."""
    return TICKERS.copy()


@pytest.fixture
def backtest_defaults():
    """Provide default backtest parameters."""
    return BACKTEST_DEFAULTS.copy()


@pytest.fixture
def sample_telegram_config():
    """Provide sample Telegram configuration."""
    return SAMPLE_TELEGRAM_CONFIG.copy()


@pytest.fixture
def sample_backtest_result():
    """Provide sample backtest result."""
    return SAMPLE_BACKTEST_RESULT.copy()
