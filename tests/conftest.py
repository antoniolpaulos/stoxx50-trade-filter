"""
Pytest configuration and shared fixtures for SPX Trade Filter tests.
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
    SAMPLE_SPX_DATA,
    SAMPLE_VIX3M_DATA,
    SAMPLE_CONFIG,
    SAMPLE_CALENDAR_EVENTS,
    TEST_SCENARIOS,
    INVALID_MARKET_DATA,
)


@pytest.fixture
def sample_config():
    """Provide sample configuration for tests."""
    return SAMPLE_CONFIG.copy()


@pytest.fixture
def sample_vix_data():
    """Provide sample VIX data."""
    return SAMPLE_VIX_DATA.copy()


@pytest.fixture
def sample_spx_data():
    """Provide sample SPX data."""
    return SAMPLE_SPX_DATA.copy()


@pytest.fixture
def sample_vix3m_data():
    """Provide sample VIX3M data."""
    return SAMPLE_VIX3M_DATA.copy()


@pytest.fixture
def go_scenario():
    """Provide GO conditions scenario."""
    return TEST_SCENARIOS['go_conditions'].copy()


@pytest.fixture
def no_go_vix_scenario():
    """Provide NO-GO VIX scenario."""
    return TEST_SCENARIOS['no_go_vix_high'].copy()


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
