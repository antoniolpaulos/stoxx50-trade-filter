#!/usr/bin/env python3
"""
IBKR TWS API provider for Euro Stoxx 50 options data.

Requires:
    pip install ib_insync

Requires IBKR account with:
    - Eurex (DTB) Level 1 market data subscription (~€2/month)
    - TWS or IB Gateway running with API enabled

Usage:
    from ibkr_provider import IBKRProvider, get_real_credit

    # Direct usage
    provider = IBKRProvider(port=7496)  # Live trading port
    if provider.connect():
        result = provider.get_iron_condor_credit(6000, otm_percent=1.0)
        print(f"Credit: €{result['credit_eur']:.2f}")
        provider.disconnect()

    # With fallback (recommended)
    credit, source = get_real_credit(config, index_price=6000)
    print(f"Credit: €{credit:.2f} (source: {source})")
"""

from typing import Optional, Tuple, Dict, Any
from datetime import date
import logging

# Try to import ib_insync - gracefully handle if not installed
try:
    from ib_insync import IB, Index, Option, Contract, util
    IBKR_AVAILABLE = True
except ImportError:
    IBKR_AVAILABLE = False
    IB = None
    Index = None
    Option = None
    Contract = None

    # Mock util for when ib_insync not installed
    class _MockUtil:
        @staticmethod
        def isNan(val):
            import math
            return val is None or (isinstance(val, float) and math.isnan(val))

    util = _MockUtil()


class IBKRProvider:
    """
    Fetch real-time Euro Stoxx 50 option prices from Interactive Brokers.

    Ports:
        7497 - TWS Paper Trading
        7496 - TWS Live Trading
        4002 - IB Gateway Paper Trading
        4001 - IB Gateway Live Trading
    """

    # Euro Stoxx 50 contract specifications
    SYMBOL = 'ESTX50'
    EXCHANGE = 'EUREX'
    CURRENCY = 'EUR'
    MULTIPLIER = 10
    INDEX_CONID = 4356500  # Euro Stoxx 50 index conId

    def __init__(self, host: str = '127.0.0.1', port: int = 7496,
                 client_id: int = 1, timeout: int = 10,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize IBKR provider.

        Args:
            host: TWS/Gateway host (default localhost)
            port: API port (see class docstring for port numbers)
            client_id: Unique client ID for this connection
            timeout: Connection timeout in seconds
            logger: Optional logger instance
        """
        self.host = host
        self.port = port
        self.client_id = client_id
        self.timeout = timeout
        self.logger = logger or logging.getLogger(__name__)
        self._ib: Optional[Any] = None
        self._connected = False
        self._index_contract = None

    def connect(self) -> bool:
        """
        Connect to TWS/Gateway.

        Returns:
            True if connection successful, False otherwise
        """
        if not IBKR_AVAILABLE:
            self.logger.warning("ib_insync not installed. Run: pip install ib_insync")
            return False

        try:
            self._ib = IB()
            self._ib.connect(
                self.host,
                self.port,
                clientId=self.client_id,
                timeout=self.timeout
            )
            self._connected = True
            self.logger.info(f"Connected to IBKR at {self.host}:{self.port}")

            # Enable delayed market data as fallback (3 = delayed, 4 = delayed-frozen)
            self._ib.reqMarketDataType(3)

            # Pre-qualify the index contract using conId for reliability
            self._index_contract = Contract(conId=self.INDEX_CONID)
            self._ib.qualifyContracts(self._index_contract)
            self.logger.info(f"Index contract: {self._index_contract.symbol} on {self._index_contract.exchange}")

            return True

        except Exception as e:
            self.logger.error(f"IBKR connection failed: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from TWS/Gateway."""
        if self._ib and self._connected:
            try:
                self._ib.disconnect()
            except Exception:
                pass
            self._connected = False
            self.logger.info("Disconnected from IBKR")

    def is_connected(self) -> bool:
        """Check if connected to IBKR."""
        return self._connected and self._ib is not None and self._ib.isConnected()

    def get_index_price(self) -> Optional[float]:
        """
        Get current Euro Stoxx 50 index price.

        Returns:
            Current index price or None if unavailable
        """
        if not self.is_connected():
            self.logger.warning("Not connected to IBKR")
            return None

        try:
            ticker = self._ib.reqMktData(self._index_contract, '', False, False)
            self._ib.sleep(2)  # Wait for data to arrive

            price = ticker.marketPrice()
            self._ib.cancelMktData(self._index_contract)

            if price and price > 0 and not util.isNan(price):
                self.logger.debug(f"Index price: {price}")
                return float(price)

            # Try last price if market price unavailable
            if ticker.last and ticker.last > 0:
                return float(ticker.last)

            self.logger.warning("Could not get valid index price")
            return None

        except Exception as e:
            self.logger.error(f"Failed to get index price: {e}")
            return None

    def get_option_price(self, strike: float, right: str,
                         expiry: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get option price for a specific strike.

        Args:
            strike: Strike price (will be rounded to nearest integer)
            right: 'C' for call, 'P' for put
            expiry: Expiration date YYYYMMDD (default: today for 0DTE)

        Returns:
            Dict with bid, ask, mid, last, iv or None if unavailable
        """
        if not self.is_connected():
            return None

        if expiry is None:
            expiry = date.today().strftime('%Y%m%d')

        strike = round(strike)

        try:
            option = Option(
                self.SYMBOL,
                expiry,
                strike,
                right,
                self.EXCHANGE,
                currency=self.CURRENCY
            )

            qualified = self._ib.qualifyContracts(option)
            if not qualified:
                self.logger.warning(f"Could not qualify option {strike}{right} exp:{expiry}")
                return None

            ticker = self._ib.reqMktData(option, '', False, False)
            self._ib.sleep(1.5)  # Wait for data

            bid = ticker.bid if ticker.bid and ticker.bid > 0 and not util.isNan(ticker.bid) else None
            ask = ticker.ask if ticker.ask and ticker.ask > 0 and not util.isNan(ticker.ask) else None
            last = ticker.last if ticker.last and ticker.last > 0 and not util.isNan(ticker.last) else None

            result = {
                'strike': strike,
                'right': right,
                'expiry': expiry,
                'bid': bid,
                'ask': ask,
                'mid': (bid + ask) / 2 if bid and ask else None,
                'last': last,
                'iv': None
            }

            # Try to get implied volatility from model greeks
            if ticker.modelGreeks and ticker.modelGreeks.impliedVol:
                result['iv'] = ticker.modelGreeks.impliedVol

            self._ib.cancelMktData(option)

            self.logger.debug(f"Option {strike}{right}: bid={bid}, ask={ask}")
            return result

        except Exception as e:
            self.logger.error(f"Failed to get option price for {strike}{right}: {e}")
            return None

    def get_iron_condor_credit(self, index_price: float,
                                otm_percent: float = 1.0,
                                wing_width: int = 50,
                                expiry: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Calculate real credit for an iron condor.

        Args:
            index_price: Current index price
            otm_percent: How far OTM for short strikes (%)
            wing_width: Wing width in points
            expiry: Expiration date YYYYMMDD (default: today for 0DTE)

        Returns:
            Dict with credit details or None if unavailable:
            {
                'credit_points': float,  # Credit in index points
                'credit_eur': float,     # Credit in EUR (points × 10)
                'short_call': int,
                'short_put': int,
                'long_call': int,
                'long_put': int,
                'call_spread_credit': float,
                'put_spread_credit': float,
                'legs': {...}            # Individual leg details
            }
        """
        if not self.is_connected():
            self.logger.warning("Not connected to IBKR")
            return None

        # Calculate strikes
        short_call = round(index_price * (1 + otm_percent / 100))
        short_put = round(index_price * (1 - otm_percent / 100))
        long_call = short_call + wing_width
        long_put = short_put - wing_width

        self.logger.info(f"Fetching IC prices: SC={short_call}, SP={short_put}, "
                        f"LC={long_call}, LP={long_put}")

        try:
            # Fetch all 4 legs
            sc = self.get_option_price(short_call, 'C', expiry)
            sp = self.get_option_price(short_put, 'P', expiry)
            lc = self.get_option_price(long_call, 'C', expiry)
            lp = self.get_option_price(long_put, 'P', expiry)

            # Check if we got all legs
            if not all([sc, sp, lc, lp]):
                missing = []
                if not sc: missing.append('short_call')
                if not sp: missing.append('short_put')
                if not lc: missing.append('long_call')
                if not lp: missing.append('long_put')
                self.logger.warning(f"Missing option legs: {missing}")
                return None

            # Check if we have bid/ask for all legs
            # For selling: use bid (what we receive)
            # For buying: use ask (what we pay)
            sc_bid = sc.get('bid')
            sp_bid = sp.get('bid')
            lc_ask = lc.get('ask')
            lp_ask = lp.get('ask')

            if not all([sc_bid, sp_bid, lc_ask, lp_ask]):
                self.logger.warning("Missing bid/ask data for some legs")
                # Try using mid prices as fallback
                sc_bid = sc_bid or sc.get('mid') or sc.get('last')
                sp_bid = sp_bid or sp.get('mid') or sp.get('last')
                lc_ask = lc_ask or lc.get('mid') or lc.get('last')
                lp_ask = lp_ask or lp.get('mid') or lp.get('last')

                if not all([sc_bid, sp_bid, lc_ask, lp_ask]):
                    self.logger.error("Cannot calculate credit - insufficient price data")
                    return None

            # Calculate credit (sell short legs, buy long legs)
            call_spread_credit = sc_bid - lc_ask
            put_spread_credit = sp_bid - lp_ask
            total_credit = call_spread_credit + put_spread_credit

            result = {
                'credit_points': total_credit,
                'credit_eur': total_credit * self.MULTIPLIER,
                'short_call': short_call,
                'short_put': short_put,
                'long_call': long_call,
                'long_put': long_put,
                'call_spread_credit': call_spread_credit,
                'put_spread_credit': put_spread_credit,
                'index_price': index_price,
                'otm_percent': otm_percent,
                'wing_width': wing_width,
                'legs': {
                    'short_call': sc,
                    'short_put': sp,
                    'long_call': lc,
                    'long_put': lp
                }
            }

            self.logger.info(f"IC credit: {total_credit:.2f} pts = €{total_credit * self.MULTIPLIER:.2f}")
            return result

        except Exception as e:
            self.logger.error(f"Failed to calculate IC credit: {e}")
            return None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False


def _try_yahoo_fallback(index_price: float, strikes_config: Dict,
                        logger: logging.Logger) -> Tuple[Optional[float], str]:
    """Try Yahoo Finance FEZ options as fallback."""
    try:
        from yahoo_options import get_estimated_credit
        credit, source = get_estimated_credit(
            index_price,
            otm_percent=strikes_config.get('otm_percent', 1.0),
            wing_width=strikes_config.get('wing_width', 50),
            logger=logger
        )
        if source == 'yahoo_fez':
            return credit, source
    except ImportError:
        logger.debug("yahoo_options module not available")
    except Exception as e:
        logger.debug(f"Yahoo fallback failed: {e}")
    return None, 'config'


def get_real_credit(config: Dict[str, Any], index_price: float,
                    logger: Optional[logging.Logger] = None) -> Tuple[float, str]:
    """
    Get real credit from IBKR, falling back to Yahoo FEZ estimation, then config.

    Priority:
        1. IBKR real quotes (if enabled and connected)
        2. Yahoo FEZ options IV estimation (free, no TWS needed)
        3. Config fallback (fixed credit)

    This is the main entry point for trade_filter.py integration.

    Args:
        config: Application config dict
        index_price: Current index price
        logger: Optional logger instance

    Returns:
        Tuple of (credit_eur, source) where source is 'ibkr', 'yahoo_fez', or 'config'
    """
    logger = logger or logging.getLogger(__name__)

    ibkr_config = config.get('ibkr', {})
    portfolio_config = config.get('portfolio', {})
    strikes_config = config.get('strikes', {})

    fallback_credit = portfolio_config.get('credit', 2.50)

    # Check if IBKR integration is enabled
    if not ibkr_config.get('enabled', False):
        logger.debug("IBKR disabled, trying Yahoo fallback")
        credit, source = _try_yahoo_fallback(index_price, strikes_config, logger)
        if credit is not None:
            return credit, source
        return fallback_credit, 'config'

    if not IBKR_AVAILABLE:
        logger.warning("ib_insync not installed, trying Yahoo fallback")
        credit, source = _try_yahoo_fallback(index_price, strikes_config, logger)
        if credit is not None:
            return credit, source
        return fallback_credit, 'config'

    # Try to get real credit from IBKR
    provider = IBKRProvider(
        host=ibkr_config.get('host', '127.0.0.1'),
        port=ibkr_config.get('port', 7496),
        client_id=ibkr_config.get('client_id', 1),
        timeout=ibkr_config.get('timeout', 10),
        logger=logger
    )

    try:
        if not provider.connect():
            logger.warning("Could not connect to IBKR, trying Yahoo fallback")
            credit, source = _try_yahoo_fallback(index_price, strikes_config, logger)
            if credit is not None:
                return credit, source
            return fallback_credit, 'config'

        result = provider.get_iron_condor_credit(
            index_price,
            otm_percent=strikes_config.get('otm_percent', 1.0),
            wing_width=strikes_config.get('wing_width', 50)
        )

        if result and result.get('credit_eur') is not None:
            credit = result['credit_eur']
            logger.info(f"Got real IBKR credit: €{credit:.2f}")
            return credit, 'ibkr'

        logger.warning("Could not get IBKR credit, trying Yahoo fallback")
        credit, source = _try_yahoo_fallback(index_price, strikes_config, logger)
        if credit is not None:
            return credit, source
        return fallback_credit, 'config'

    except Exception as e:
        logger.error(f"IBKR error: {e}, trying Yahoo fallback")
        credit, source = _try_yahoo_fallback(index_price, strikes_config, logger)
        if credit is not None:
            return credit, source
        return fallback_credit, 'config'

    finally:
        provider.disconnect()


def get_real_credit_with_details(config: Dict[str, Any], index_price: float,
                                  logger: Optional[logging.Logger] = None) -> Tuple[float, str, Optional[Dict]]:
    """
    Get real credit from IBKR with full details, falling back to config value.

    Args:
        config: Application config dict
        index_price: Current index price
        logger: Optional logger instance

    Returns:
        Tuple of (credit_eur, source, details) where:
        - credit_eur: Credit amount in EUR
        - source: 'ibkr' or 'config'
        - details: Full IC details dict or None
    """
    logger = logger or logging.getLogger(__name__)

    ibkr_config = config.get('ibkr', {})
    portfolio_config = config.get('portfolio', {})
    strikes_config = config.get('strikes', {})

    fallback_credit = portfolio_config.get('credit', 2.50)

    if not ibkr_config.get('enabled', False) or not IBKR_AVAILABLE:
        return fallback_credit, 'config', None

    provider = IBKRProvider(
        host=ibkr_config.get('host', '127.0.0.1'),
        port=ibkr_config.get('port', 7496),
        client_id=ibkr_config.get('client_id', 1),
        timeout=ibkr_config.get('timeout', 10),
        logger=logger
    )

    try:
        if not provider.connect():
            return fallback_credit, 'config', None

        result = provider.get_iron_condor_credit(
            index_price,
            otm_percent=strikes_config.get('otm_percent', 1.0),
            wing_width=strikes_config.get('wing_width', 50)
        )

        if result and result.get('credit_eur') is not None:
            return result['credit_eur'], 'ibkr', result

        return fallback_credit, 'config', None

    finally:
        provider.disconnect()


if __name__ == '__main__':
    # Quick test - requires TWS running
    import sys

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    if not IBKR_AVAILABLE:
        print("ib_insync not installed. Run: pip install ib_insync")
        sys.exit(1)

    print("Testing IBKR connection...")
    print("Make sure TWS/Gateway is running with API enabled on port 7496 (live) or 7497 (paper)")
    print()

    with IBKRProvider(port=7496, logger=logger) as provider:
        if not provider.is_connected():
            print("Failed to connect to IBKR")
            sys.exit(1)

        # Get index price
        price = provider.get_index_price()
        if price:
            print(f"Euro Stoxx 50: {price:.2f}")

            # Get IC credit
            result = provider.get_iron_condor_credit(price, otm_percent=1.0, wing_width=50)
            if result:
                print(f"\nIron Condor (1% OTM, 50pt wings):")
                print(f"  Short Call: {result['short_call']}")
                print(f"  Short Put:  {result['short_put']}")
                print(f"  Long Call:  {result['long_call']}")
                print(f"  Long Put:   {result['long_put']}")
                print(f"  Credit:     {result['credit_points']:.2f} pts = €{result['credit_eur']:.2f}")
            else:
                print("Could not calculate IC credit")
        else:
            print("Could not get index price")
