# IBKR Integration Plan

## Overview

Add Interactive Brokers TWS API integration to fetch real-time Euro Stoxx 50 option prices, replacing the fixed credit assumption with actual market data.

---

## Goals

1. **Real-time credit** - Fetch actual bid/ask for iron condor at 10:00 CET
2. **Graceful fallback** - Use fixed credit when IBKR unavailable
3. **Commission tracking** - Account for €6 round-trip (4 legs × €1.50)
4. **Minimal disruption** - Integrate as optional module, existing flow unchanged

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     trade_filter.py                         │
│                                                             │
│  get_real_credit() ──► IBKRProvider (if available)         │
│         │                    │                              │
│         │                    ▼                              │
│         │              ib_insync API                        │
│         │                    │                              │
│         ▼                    ▼                              │
│  fallback: config.credit   TWS/Gateway                      │
└─────────────────────────────────────────────────────────────┘
```

---

## New Files

| File | Purpose |
|------|---------|
| `ibkr_provider.py` | IBKR connection, option chain fetching |
| `tests/unit/test_ibkr_provider.py` | Unit tests with mocked ib_insync |

---

## Implementation

### Phase 1: IBKR Provider Module

**ibkr_provider.py:**

```python
"""
IBKR TWS API provider for Euro Stoxx 50 options data.
Requires: pip install ib_insync
Requires: Eurex (DTB) Level 1 market data subscription (~€2/mo)
"""

from typing import Optional, Tuple, Dict
from datetime import datetime, date
import logging

try:
    from ib_insync import IB, Index, Option, util
    IBKR_AVAILABLE = True
except ImportError:
    IBKR_AVAILABLE = False


class IBKRProvider:
    """Fetch real-time Euro Stoxx 50 option prices from IBKR."""

    # Euro Stoxx 50 contract specs
    SYMBOL = 'ESTX50'
    EXCHANGE = 'DTB'  # Eurex
    CURRENCY = 'EUR'
    MULTIPLIER = 10

    def __init__(self, host: str = '127.0.0.1', port: int = 7497,
                 client_id: int = 1, timeout: int = 10,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize IBKR provider.

        Args:
            host: TWS/Gateway host (default localhost)
            port: 7497=TWS Paper, 7496=TWS Live, 4002=Gateway Paper, 4001=Gateway Live
            client_id: Unique client ID for this connection
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.client_id = client_id
        self.timeout = timeout
        self.logger = logger or logging.getLogger(__name__)
        self._ib: Optional[IB] = None
        self._connected = False

    def connect(self) -> bool:
        """Connect to TWS/Gateway. Returns True if successful."""
        if not IBKR_AVAILABLE:
            self.logger.warning("ib_insync not installed")
            return False

        try:
            self._ib = IB()
            self._ib.connect(self.host, self.port, clientId=self.client_id,
                            timeout=self.timeout)
            self._connected = True
            self.logger.info(f"Connected to IBKR at {self.host}:{self.port}")
            return True
        except Exception as e:
            self.logger.error(f"IBKR connection failed: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from TWS/Gateway."""
        if self._ib and self._connected:
            self._ib.disconnect()
            self._connected = False
            self.logger.info("Disconnected from IBKR")

    def is_connected(self) -> bool:
        """Check if connected to IBKR."""
        return self._connected and self._ib and self._ib.isConnected()

    def get_index_price(self) -> Optional[float]:
        """Get current Euro Stoxx 50 index price."""
        if not self.is_connected():
            return None

        try:
            index = Index(self.SYMBOL, self.EXCHANGE, self.CURRENCY)
            self._ib.qualifyContracts(index)
            ticker = self._ib.reqMktData(index, '', False, False)
            self._ib.sleep(2)  # Wait for data

            price = ticker.marketPrice()
            self._ib.cancelMktData(index)

            if price and price > 0:
                return price
            return None
        except Exception as e:
            self.logger.error(f"Failed to get index price: {e}")
            return None

    def get_option_price(self, strike: float, right: str,
                         expiry: Optional[str] = None) -> Optional[Dict]:
        """
        Get option price for a specific strike.

        Args:
            strike: Strike price
            right: 'C' for call, 'P' for put
            expiry: Expiration date YYYYMMDD (default: today for 0DTE)

        Returns:
            Dict with bid, ask, mid, iv or None if unavailable
        """
        if not self.is_connected():
            return None

        if expiry is None:
            expiry = date.today().strftime('%Y%m%d')

        try:
            # For daily options use OEXP, for monthly use OESX
            # Daily options symbol format may differ - verify with IBKR
            option = Option(self.SYMBOL, expiry, strike, right, self.EXCHANGE)
            qualified = self._ib.qualifyContracts(option)

            if not qualified:
                self.logger.warning(f"Could not qualify option {strike}{right}")
                return None

            ticker = self._ib.reqMktData(option, '', False, False)
            self._ib.sleep(2)

            result = {
                'bid': ticker.bid if ticker.bid > 0 else None,
                'ask': ticker.ask if ticker.ask > 0 else None,
                'mid': (ticker.bid + ticker.ask) / 2 if ticker.bid > 0 and ticker.ask > 0 else None,
                'last': ticker.last if ticker.last > 0 else None,
                'iv': ticker.modelGreeks.impliedVol if ticker.modelGreeks else None
            }

            self._ib.cancelMktData(option)
            return result

        except Exception as e:
            self.logger.error(f"Failed to get option price: {e}")
            return None

    def get_iron_condor_credit(self, index_price: float,
                                otm_percent: float = 1.0,
                                wing_width: int = 50) -> Optional[Dict]:
        """
        Calculate real credit for an iron condor.

        Args:
            index_price: Current index price
            otm_percent: How far OTM for short strikes (%)
            wing_width: Wing width in points

        Returns:
            Dict with credit details or None if unavailable
        """
        if not self.is_connected():
            return None

        # Calculate strikes
        short_call = round(index_price * (1 + otm_percent / 100))
        short_put = round(index_price * (1 - otm_percent / 100))
        long_call = short_call + wing_width
        long_put = short_put - wing_width

        try:
            # Fetch all 4 legs
            sc = self.get_option_price(short_call, 'C')
            sp = self.get_option_price(short_put, 'P')
            lc = self.get_option_price(long_call, 'C')
            lp = self.get_option_price(long_put, 'P')

            if not all([sc, sp, lc, lp]):
                self.logger.warning("Could not fetch all option legs")
                return None

            # Calculate credit (sell short, buy long)
            # Use bid for selling, ask for buying
            if not all([sc.get('bid'), sp.get('bid'), lc.get('ask'), lp.get('ask')]):
                self.logger.warning("Missing bid/ask data")
                return None

            call_spread_credit = sc['bid'] - lc['ask']
            put_spread_credit = sp['bid'] - lp['ask']
            total_credit = call_spread_credit + put_spread_credit

            return {
                'credit_points': total_credit,
                'credit_eur': total_credit * self.MULTIPLIER,
                'short_call': short_call,
                'short_put': short_put,
                'long_call': long_call,
                'long_put': long_put,
                'call_spread_credit': call_spread_credit,
                'put_spread_credit': put_spread_credit,
                'legs': {
                    'short_call': sc,
                    'short_put': sp,
                    'long_call': lc,
                    'long_put': lp
                }
            }

        except Exception as e:
            self.logger.error(f"Failed to calculate IC credit: {e}")
            return None


def get_real_credit(config: dict, index_price: float) -> Tuple[float, str]:
    """
    Get real credit from IBKR, falling back to config value.

    Args:
        config: Application config dict
        index_price: Current index price

    Returns:
        Tuple of (credit_eur, source) where source is 'ibkr' or 'config'
    """
    ibkr_config = config.get('ibkr', {})
    portfolio_config = config.get('portfolio', {})
    strikes_config = config.get('strikes', {})

    fallback_credit = portfolio_config.get('credit', 2.50)

    # Check if IBKR integration is enabled
    if not ibkr_config.get('enabled', False):
        return fallback_credit, 'config'

    # Try to get real credit
    provider = IBKRProvider(
        host=ibkr_config.get('host', '127.0.0.1'),
        port=ibkr_config.get('port', 7497),
        client_id=ibkr_config.get('client_id', 1)
    )

    if not provider.connect():
        return fallback_credit, 'config'

    try:
        result = provider.get_iron_condor_credit(
            index_price,
            otm_percent=strikes_config.get('otm_percent', 1.0),
            wing_width=strikes_config.get('wing_width', 50)
        )

        if result and result.get('credit_eur'):
            return result['credit_eur'], 'ibkr'

        return fallback_credit, 'config'

    finally:
        provider.disconnect()
```

### Phase 2: Config Updates

**Add to config.yaml.example:**

```yaml
# IBKR Integration (optional)
# Requires: pip install ib_insync
# Requires: Eurex (DTB) Level 1 subscription in IBKR account
ibkr:
  enabled: false
  host: "127.0.0.1"
  port: 7497              # 7497=TWS Paper, 7496=TWS Live, 4002=Gateway Paper, 4001=Gateway Live
  client_id: 1
  timeout: 10             # Connection timeout (seconds)

# Trading costs
costs:
  commission_per_leg: 1.50   # EUR per option leg
  total_commission: 6.00     # 4 legs round-trip
```

### Phase 3: Integration with trade_filter.py

**Update evaluate_trade() to use real credit:**

```python
# In trade_filter.py

from ibkr_provider import get_real_credit, IBKR_AVAILABLE

def evaluate_trade(config, ...):
    # ... existing code to get market data ...

    # Get credit (real or fallback)
    credit, credit_source = get_real_credit(config, stoxx_current)

    # Account for commission
    costs = config.get('costs', {})
    commission = costs.get('total_commission', 6.0)
    net_credit = credit - commission

    # Log the source
    if credit_source == 'ibkr':
        logger.info(f"Using real IBKR credit: €{credit:.2f} (net: €{net_credit:.2f})")
    else:
        logger.info(f"Using config credit: €{credit:.2f} (net: €{net_credit:.2f})")

    # ... rest of evaluation ...
```

### Phase 4: Portfolio Tracking Updates

**Update portfolio.py to track real vs estimated:**

```python
# Trade info now includes credit source
trade_info = {
    "date": today,
    "stoxx_entry": result['data']['stoxx_current'],
    "call_strike": result['call_strike'],
    "put_strike": result['put_strike'],
    "wing_width": result['wing_width'],
    "credit": credit,
    "credit_source": credit_source,  # 'ibkr' or 'config'
    "commission": commission
}
```

---

## Testing Strategy

### Unit Tests (mocked)

```python
# tests/unit/test_ibkr_provider.py

@patch('ibkr_provider.IB')
def test_get_iron_condor_credit(mock_ib):
    """Test IC credit calculation with mocked IBKR."""
    # Setup mock ticker responses
    mock_ib.return_value.reqMktData.return_value = MockTicker(bid=2.5, ask=3.0)

    provider = IBKRProvider()
    provider.connect()

    result = provider.get_iron_condor_credit(6000, otm_percent=1.0)

    assert result is not None
    assert 'credit_eur' in result
```

### Integration Tests (requires TWS)

```python
# tests/integration/test_ibkr_live.py
# Run manually with: pytest tests/integration/test_ibkr_live.py -v

@pytest.mark.skipif(not TWS_AVAILABLE, reason="TWS not running")
def test_real_connection():
    """Test real IBKR connection (requires TWS running)."""
    provider = IBKRProvider(port=7497)  # Paper trading
    assert provider.connect()

    price = provider.get_index_price()
    assert price is not None
    assert 4000 < price < 8000  # Sanity check

    provider.disconnect()
```

---

## Rollout Plan

### Step 1: Install & Configure
```bash
pip install ib_insync
# Add to requirements.txt: ib_insync>=0.9.0
```

### Step 2: Enable in config.yaml
```yaml
ibkr:
  enabled: true
  port: 7497  # Start with paper trading
```

### Step 3: Test with TWS Paper
```bash
# Start TWS Paper Trading
# Enable API in TWS: File > Global Configuration > API > Settings
#   - Enable ActiveX and Socket Clients
#   - Socket port: 7497
#   - Disable "Read-Only API"

python trade_filter.py -a -p
# Should show "Using real IBKR credit: €X.XX"
```

### Step 4: Switch to Live
```yaml
ibkr:
  port: 7496  # TWS Live
```

---

## Limitations

1. **No historical option data** - IBKR doesn't provide historical option prices, so `optimize.py` still uses theoretical Black-Scholes values

2. **TWS dependency** - Must have TWS/Gateway running at 10:00 CET for live credit

3. **Market hours only** - Option prices only available during Eurex trading hours (09:00-17:30 CET)

4. **Subscription required** - Eurex Level 1 data costs ~€2/month

---

## Future Enhancements

1. **Cache option chains** - Reduce API calls by caching strikes for the day
2. **Greeks tracking** - Log delta, gamma, theta for analysis
3. **Auto-reconnect** - Handle TWS restarts gracefully
4. **IB Gateway** - Document headless setup for server deployment

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `ibkr_provider.py` | Create | IBKR connection and option data |
| `requirements.txt` | Modify | Add ib_insync>=0.9.0 |
| `config.yaml.example` | Modify | Add ibkr and costs sections |
| `trade_filter.py` | Modify | Integrate get_real_credit() |
| `portfolio.py` | Modify | Track credit_source |
| `tests/unit/test_ibkr_provider.py` | Create | Unit tests |
| `tests/integration/test_ibkr_live.py` | Create | Live integration tests |

---

## Timeline

| Phase | Description |
|-------|-------------|
| Phase 1 | Create ibkr_provider.py with core functionality |
| Phase 2 | Update config structure |
| Phase 3 | Integrate with trade_filter.py |
| Phase 4 | Update portfolio tracking |
| Phase 5 | Testing and documentation |
