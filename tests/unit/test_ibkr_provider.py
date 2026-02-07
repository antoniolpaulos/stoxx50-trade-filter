"""
Unit tests for ibkr_provider.py - IBKR TWS API integration.
All tests use mocked ib_insync to avoid requiring actual TWS connection.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ibkr_provider import IBKRProvider, get_real_credit, IBKR_AVAILABLE


class MockTicker:
    """Mock ib_insync Ticker object."""

    def __init__(self, bid=None, ask=None, last=None, market_price=None):
        self.bid = bid
        self.ask = ask
        self.last = last
        self._market_price = market_price
        self.modelGreeks = None

    def marketPrice(self):
        return self._market_price


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        'ibkr': {
            'enabled': True,
            'host': '127.0.0.1',
            'port': 7497,
            'client_id': 1,
            'timeout': 10
        },
        'portfolio': {
            'credit': 2.50
        },
        'strikes': {
            'otm_percent': 1.0,
            'wing_width': 50
        }
    }


@pytest.fixture
def disabled_config():
    """Config with IBKR disabled."""
    return {
        'ibkr': {
            'enabled': False
        },
        'portfolio': {
            'credit': 2.50
        },
        'strikes': {
            'otm_percent': 1.0,
            'wing_width': 50
        }
    }


class TestIBKRProviderInit:
    """Test IBKRProvider initialization."""

    def test_default_parameters(self):
        """Test default initialization parameters."""
        provider = IBKRProvider()

        assert provider.host == '127.0.0.1'
        assert provider.port == 7496
        assert provider.client_id == 1
        assert provider.timeout == 10
        assert provider._connected is False

    def test_custom_parameters(self):
        """Test custom initialization parameters."""
        provider = IBKRProvider(
            host='192.168.1.100',
            port=7496,
            client_id=5,
            timeout=30
        )

        assert provider.host == '192.168.1.100'
        assert provider.port == 7496
        assert provider.client_id == 5
        assert provider.timeout == 30

    def test_contract_specs(self):
        """Test contract specifications."""
        assert IBKRProvider.SYMBOL == 'ESTX50'
        assert IBKRProvider.EXCHANGE == 'EUREX'
        assert IBKRProvider.CURRENCY == 'EUR'
        assert IBKRProvider.MULTIPLIER == 10


class TestIBKRProviderConnection:
    """Test connection functionality."""

    def test_not_connected_by_default(self):
        """Test provider is not connected on init."""
        provider = IBKRProvider()
        assert provider.is_connected() is False

    def test_get_index_price_not_connected(self):
        """Test index price when not connected."""
        provider = IBKRProvider()
        provider._connected = False

        price = provider.get_index_price()

        assert price is None

    def test_get_option_price_not_connected(self):
        """Test option price when not connected."""
        provider = IBKRProvider()
        provider._connected = False

        result = provider.get_option_price(6000, 'C')

        assert result is None

    def test_get_iron_condor_credit_not_connected(self):
        """Test IC credit when not connected."""
        provider = IBKRProvider()
        provider._connected = False

        result = provider.get_iron_condor_credit(6000)

        assert result is None


class TestStrikeCalculation:
    """Test strike price calculations."""

    def test_strike_calculation_1_percent(self):
        """Test 1% OTM strike calculation."""
        index_price = 6000
        otm = 1.0

        short_call = round(index_price * (1 + otm / 100))
        short_put = round(index_price * (1 - otm / 100))

        assert short_call == 6060
        assert short_put == 5940

    def test_strike_calculation_05_percent(self):
        """Test 0.5% OTM strike calculation."""
        index_price = 6000
        otm = 0.5

        short_call = round(index_price * (1 + otm / 100))
        short_put = round(index_price * (1 - otm / 100))

        assert short_call == 6030
        assert short_put == 5970

    def test_wing_calculation(self):
        """Test wing strike calculation."""
        short_call = 6060
        short_put = 5940
        wing_width = 50

        long_call = short_call + wing_width
        long_put = short_put - wing_width

        assert long_call == 6110
        assert long_put == 5890

    def test_credit_calculation(self):
        """Test credit calculation from leg prices."""
        # Short call: bid=1.50, Short put: bid=1.20
        # Long call: ask=0.50, Long put: ask=0.40
        sc_bid = 1.50
        sp_bid = 1.20
        lc_ask = 0.50
        lp_ask = 0.40

        call_spread_credit = sc_bid - lc_ask
        put_spread_credit = sp_bid - lp_ask
        total_credit = call_spread_credit + put_spread_credit

        assert abs(call_spread_credit - 1.00) < 0.001
        assert abs(put_spread_credit - 0.80) < 0.001
        assert abs(total_credit - 1.80) < 0.001

    def test_credit_to_eur(self):
        """Test credit points to EUR conversion."""
        credit_points = 1.80
        multiplier = 10

        credit_eur = credit_points * multiplier

        assert credit_eur == 18.00


class TestGetRealCredit:
    """Test the get_real_credit helper function."""

    @patch('ibkr_provider._try_yahoo_fallback', return_value=(None, 'config'))
    def test_get_real_credit_disabled(self, mock_yahoo, disabled_config):
        """Test fallback when IBKR disabled in config."""
        credit, source = get_real_credit(disabled_config, 6000)

        assert credit == 2.50
        assert source == 'config'

    @patch('ibkr_provider._try_yahoo_fallback', return_value=(None, 'config'))
    def test_get_real_credit_no_config(self, mock_yahoo):
        """Test with empty config."""
        config = {}
        credit, source = get_real_credit(config, 6000)

        assert credit == 2.50  # Default fallback
        assert source == 'config'

    @patch('ibkr_provider._try_yahoo_fallback', return_value=(None, 'config'))
    def test_get_real_credit_custom_fallback(self, mock_yahoo):
        """Test with custom fallback credit."""
        config = {
            'ibkr': {'enabled': False},
            'portfolio': {'credit': 5.00}
        }
        credit, source = get_real_credit(config, 6000)

        assert credit == 5.00
        assert source == 'config'

    @patch('ibkr_provider._try_yahoo_fallback', return_value=(None, 'config'))
    @patch('ibkr_provider.IBKRProvider')
    def test_get_real_credit_connection_failure(self, mock_provider_class, mock_yahoo, sample_config):
        """Test fallback when connection fails."""
        mock_provider = Mock()
        mock_provider.connect.return_value = False
        mock_provider_class.return_value = mock_provider

        # Need IBKR_AVAILABLE to be True for this test
        with patch('ibkr_provider.IBKR_AVAILABLE', True):
            credit, source = get_real_credit(sample_config, 6000)

        assert credit == 2.50
        assert source == 'config'

    @patch('ibkr_provider.IBKRProvider')
    def test_get_real_credit_success(self, mock_provider_class, sample_config):
        """Test successful real credit fetch."""
        mock_provider = Mock()
        mock_provider.connect.return_value = True
        mock_provider.get_iron_condor_credit.return_value = {
            'credit_eur': 4.20,
            'credit_points': 0.42
        }
        mock_provider_class.return_value = mock_provider

        with patch('ibkr_provider.IBKR_AVAILABLE', True):
            credit, source = get_real_credit(sample_config, 6000)

        assert credit == 4.20
        assert source == 'ibkr'
        mock_provider.disconnect.assert_called_once()

    @patch('ibkr_provider._try_yahoo_fallback', return_value=(None, 'config'))
    @patch('ibkr_provider.IBKRProvider')
    def test_get_real_credit_no_result(self, mock_provider_class, mock_yahoo, sample_config):
        """Test fallback when IC credit returns None."""
        mock_provider = Mock()
        mock_provider.connect.return_value = True
        mock_provider.get_iron_condor_credit.return_value = None
        mock_provider_class.return_value = mock_provider

        with patch('ibkr_provider.IBKR_AVAILABLE', True):
            credit, source = get_real_credit(sample_config, 6000)

        assert credit == 2.50
        assert source == 'config'

    @patch('ibkr_provider._try_yahoo_fallback', return_value=(None, 'config'))
    @patch('ibkr_provider.IBKRProvider')
    def test_get_real_credit_exception(self, mock_provider_class, mock_yahoo, sample_config):
        """Test fallback when exception occurs."""
        mock_provider = Mock()
        mock_provider.connect.return_value = True
        mock_provider.get_iron_condor_credit.side_effect = Exception("API error")
        mock_provider_class.return_value = mock_provider

        with patch('ibkr_provider.IBKR_AVAILABLE', True):
            credit, source = get_real_credit(sample_config, 6000)

        assert credit == 2.50
        assert source == 'config'


class TestMockUtil:
    """Test the mock util class for when ib_insync not installed."""

    def test_isnan_with_none(self):
        """Test isNan with None value."""
        from ibkr_provider import util, IBKR_AVAILABLE
        if IBKR_AVAILABLE:
            # Real ib_insync util.isNan(None) returns False
            assert util.isNan(None) is False
        else:
            # Mock util treats None as NaN
            assert util.isNan(None) is True

    def test_isnan_with_nan(self):
        """Test isNan with NaN value."""
        import math
        from ibkr_provider import util
        assert util.isNan(float('nan')) is True

    def test_isnan_with_valid(self):
        """Test isNan with valid number."""
        from ibkr_provider import util
        assert util.isNan(5.5) is False

    def test_isnan_with_zero(self):
        """Test isNan with zero."""
        from ibkr_provider import util
        assert util.isNan(0.0) is False


class TestContextManager:
    """Test context manager functionality."""

    def test_context_manager_enter_exit(self):
        """Test context manager calls connect/disconnect."""
        provider = IBKRProvider()

        # Mock the connect/disconnect methods
        provider.connect = Mock(return_value=False)
        provider.disconnect = Mock()

        with provider as p:
            assert p is provider
            provider.connect.assert_called_once()

        provider.disconnect.assert_called_once()


class TestProviderWithMockedIB:
    """Tests that require mocking the IB class."""

    @pytest.fixture
    def mock_ib(self):
        """Create a mock IB instance."""
        mock = Mock()
        mock.isConnected.return_value = True
        return mock

    def test_disconnect_when_connected(self, mock_ib):
        """Test disconnect when connected."""
        provider = IBKRProvider()
        provider._connected = True
        provider._ib = mock_ib

        provider.disconnect()

        mock_ib.disconnect.assert_called_once()
        assert provider._connected is False

    def test_disconnect_when_not_connected(self):
        """Test disconnect when not connected."""
        provider = IBKRProvider()
        provider._connected = False
        provider._ib = None

        # Should not raise
        provider.disconnect()

        assert provider._connected is False

    def test_is_connected_true(self, mock_ib):
        """Test is_connected returns True when connected."""
        provider = IBKRProvider()
        provider._connected = True
        provider._ib = mock_ib

        assert provider.is_connected() is True

    def test_is_connected_false_no_ib(self):
        """Test is_connected returns False when no IB instance."""
        provider = IBKRProvider()
        provider._connected = True
        provider._ib = None

        assert provider.is_connected() is False

    def test_is_connected_false_ib_disconnected(self, mock_ib):
        """Test is_connected returns False when IB reports disconnected."""
        mock_ib.isConnected.return_value = False
        provider = IBKRProvider()
        provider._connected = True
        provider._ib = mock_ib

        assert provider.is_connected() is False
