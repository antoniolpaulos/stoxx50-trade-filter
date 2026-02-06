"""
Integration tests for IBKR provider - requires TWS/Gateway running.

These tests connect to a real TWS/Gateway instance and are skipped
if the connection is not available.

Run manually with:
    pytest tests/integration/test_ibkr_live.py -v

Prerequisites:
    1. TWS or IB Gateway running
    2. API connections enabled in TWS (File > Global Configuration > API > Settings)
    3. Eurex (DTB) Level 1 market data subscription (~EUR2/month)
    4. pip install ib_insync
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ibkr_provider import IBKRProvider, IBKR_AVAILABLE


# Skip all tests if ib_insync not installed
pytestmark = pytest.mark.skipif(
    not IBKR_AVAILABLE,
    reason="ib_insync not installed"
)


def is_tws_available(host='127.0.0.1', port=7497, timeout=5):
    """Check if TWS/Gateway is running and accessible."""
    if not IBKR_AVAILABLE:
        return False

    provider = IBKRProvider(host=host, port=port, timeout=timeout)
    connected = provider.connect()
    if connected:
        provider.disconnect()
    return connected


# Skip all tests in this file if TWS not running
TWS_AVAILABLE = is_tws_available() if IBKR_AVAILABLE else False


@pytest.mark.skipif(not TWS_AVAILABLE, reason="TWS/Gateway not running")
class TestIBKRLiveConnection:
    """Live connection tests - require TWS running."""

    @pytest.fixture
    def provider(self):
        """Create a connected provider."""
        p = IBKRProvider(port=7497, timeout=10)
        connected = p.connect()
        assert connected, "Failed to connect to TWS"
        yield p
        p.disconnect()

    def test_connection(self, provider):
        """Test basic connection."""
        assert provider.is_connected()

    def test_get_index_price(self, provider):
        """Test fetching Euro Stoxx 50 index price."""
        price = provider.get_index_price()

        assert price is not None, "Failed to get index price"
        assert 3000 < price < 8000, f"Index price {price} outside reasonable range"

        print(f"\nEuro Stoxx 50 price: {price:.2f}")

    def test_get_option_price_call(self, provider):
        """Test fetching a call option price."""
        # Get current index price first
        index_price = provider.get_index_price()
        assert index_price is not None

        # Calculate OTM strike
        strike = round(index_price * 1.01)  # 1% OTM

        result = provider.get_option_price(strike, 'C')

        # May be None if no 0DTE options available today
        if result is not None:
            print(f"\nCall {strike}: bid={result.get('bid')}, ask={result.get('ask')}")
            if result.get('bid') and result.get('ask'):
                assert result['bid'] >= 0
                assert result['ask'] >= result['bid']

    def test_get_option_price_put(self, provider):
        """Test fetching a put option price."""
        index_price = provider.get_index_price()
        assert index_price is not None

        # Calculate OTM strike
        strike = round(index_price * 0.99)  # 1% OTM

        result = provider.get_option_price(strike, 'P')

        if result is not None:
            print(f"\nPut {strike}: bid={result.get('bid')}, ask={result.get('ask')}")
            if result.get('bid') and result.get('ask'):
                assert result['bid'] >= 0
                assert result['ask'] >= result['bid']

    def test_get_iron_condor_credit(self, provider):
        """Test fetching full iron condor credit."""
        index_price = provider.get_index_price()
        assert index_price is not None

        result = provider.get_iron_condor_credit(
            index_price,
            otm_percent=1.0,
            wing_width=50
        )

        # May be None outside trading hours or if no 0DTE options
        if result is not None:
            print(f"\nIron Condor Credit:")
            print(f"  Index: {index_price:.2f}")
            print(f"  Short Put: {result['short_put']}")
            print(f"  Short Call: {result['short_call']}")
            print(f"  Credit: {result['credit_points']:.2f} pts (EUR{result['credit_eur']:.2f})")

            assert result['credit_points'] >= 0
            assert result['credit_eur'] == result['credit_points'] * 10


@pytest.mark.skipif(not TWS_AVAILABLE, reason="TWS/Gateway not running")
class TestIBKRLiveContextManager:
    """Test context manager with live connection."""

    def test_context_manager_usage(self):
        """Test using provider as context manager."""
        with IBKRProvider(port=7497, timeout=10) as provider:
            assert provider.is_connected()
            price = provider.get_index_price()
            print(f"\nIndex price via context manager: {price}")

        # After exiting context, should be disconnected
        assert not provider.is_connected()


@pytest.mark.skipif(not TWS_AVAILABLE, reason="TWS/Gateway not running")
class TestIBKRLiveStressTests:
    """Stress tests for live connection."""

    @pytest.fixture
    def provider(self):
        """Create a connected provider."""
        p = IBKRProvider(port=7497, timeout=15)
        connected = p.connect()
        assert connected, "Failed to connect to TWS"
        yield p
        p.disconnect()

    def test_multiple_option_requests(self, provider):
        """Test fetching multiple options in sequence."""
        index_price = provider.get_index_price()
        assert index_price is not None

        strikes_fetched = 0
        for otm_pct in [0.5, 1.0, 1.5]:
            call_strike = round(index_price * (1 + otm_pct / 100))
            put_strike = round(index_price * (1 - otm_pct / 100))

            call_result = provider.get_option_price(call_strike, 'C')
            put_result = provider.get_option_price(put_strike, 'P')

            if call_result:
                strikes_fetched += 1
            if put_result:
                strikes_fetched += 1

        print(f"\nFetched {strikes_fetched} option prices")


if __name__ == '__main__':
    # Run tests directly
    print(f"IBKR_AVAILABLE: {IBKR_AVAILABLE}")
    print(f"TWS_AVAILABLE: {TWS_AVAILABLE}")

    if TWS_AVAILABLE:
        pytest.main([__file__, '-v'])
    else:
        print("\nTWS not running. Start TWS/Gateway and try again.")
