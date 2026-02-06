#!/usr/bin/env python3
"""
Yahoo Finance options data provider for Euro Stoxx 50 credit estimation.

Uses FEZ (SPDR Euro Stoxx 50 ETF) options IV from Yahoo Finance
to estimate Euro Stoxx 50 iron condor credits via Black-Scholes.

This is a FREE alternative to IBKR for live-ish credit estimates.
Not as accurate as real Eurex quotes, but better than a fixed assumption.

Usage:
    from yahoo_options import get_estimated_credit, YahooOptionsProvider

    credit, source = get_estimated_credit(index_price=6000)
    print(f"Estimated credit: €{credit:.2f} (source: {source})")
"""

import math
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, date
import logging

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def black_scholes_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Calculate call option price using Black-Scholes.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate
        sigma: Volatility (annualized)

    Returns:
        Call option price
    """
    if T <= 0:
        return max(S - K, 0)
    if sigma <= 0:
        return max(S - K, 0)

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)


def black_scholes_put(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Calculate put option price using Black-Scholes.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years)
        r: Risk-free rate
        sigma: Volatility (annualized)

    Returns:
        Put option price
    """
    if T <= 0:
        return max(K - S, 0)
    if sigma <= 0:
        return max(K - S, 0)

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


class YahooOptionsProvider:
    """
    Fetch implied volatility from VSTOXX and estimate Euro Stoxx 50 credits.
    Falls back to FEZ options if VSTOXX unavailable.
    """

    MULTIPLIER = 10  # Euro Stoxx 50 options multiplier
    RISK_FREE_RATE = 0.03  # ~3% EUR rate

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self._iv: Optional[float] = None

    def get_vstoxx(self) -> Optional[float]:
        """
        Get VSTOXX (Euro Stoxx 50 implied volatility index).

        Returns:
            Annualized IV as decimal (e.g., 0.20 for 20%), or None
        """
        if not YFINANCE_AVAILABLE:
            return None

        try:
            vstoxx = yf.Ticker('V2TX.DE')
            price = vstoxx.fast_info.get('lastPrice')

            if price and price > 0:
                iv = price / 100  # VSTOXX is in percentage points
                self.logger.info(f"VSTOXX: {price:.1f}% (IV: {iv:.1%})")
                return iv
        except Exception as e:
            self.logger.debug(f"VSTOXX fetch failed: {e}")

        return None

    def get_fez_iv(self) -> Optional[float]:
        """
        Get implied volatility from FEZ (Euro Stoxx 50 ETF) options.
        Used as fallback if VSTOXX unavailable.

        Returns:
            Annualized IV as decimal (e.g., 0.25 for 25%), or None
        """
        if not YFINANCE_AVAILABLE:
            self.logger.warning("yfinance not installed")
            return None

        try:
            fez = yf.Ticker('FEZ')
            expirations = fez.options

            if not expirations:
                self.logger.warning("No FEZ options expirations found")
                return None

            chain = fez.option_chain(expirations[0])
            fez_price = fez.fast_info.get('lastPrice', 50)

            # Find near-ATM options
            calls = chain.calls
            puts = chain.puts

            atm_calls = calls[abs(calls['strike'] - fez_price) <= 3]
            atm_puts = puts[abs(puts['strike'] - fez_price) <= 3]

            ivs = []
            if len(atm_calls) > 0:
                ivs.extend(atm_calls['impliedVolatility'].dropna().tolist())
            if len(atm_puts) > 0:
                ivs.extend(atm_puts['impliedVolatility'].dropna().tolist())

            if not ivs:
                return None

            avg_iv = sum(ivs) / len(ivs)
            avg_iv = max(0.12, min(avg_iv, 0.40))  # Cap to reasonable range

            self.logger.info(f"FEZ ATM IV: {avg_iv:.1%}")
            return avg_iv

        except Exception as e:
            self.logger.error(f"Failed to get FEZ IV: {e}")
            return None

    def get_iv(self) -> Optional[float]:
        """
        Get best available IV estimate.
        Priority: VSTOXX > FEZ options

        Returns:
            Annualized IV as decimal
        """
        # Try VSTOXX first (most accurate for Euro Stoxx 50)
        iv = self.get_vstoxx()
        if iv is not None:
            self._iv = iv
            return iv

        # Fall back to FEZ options
        iv = self.get_fez_iv()
        if iv is not None:
            self._iv = iv
            return iv

        return None

    def estimate_ic_credit(self, index_price: float,
                           otm_percent: float = 1.0,
                           wing_width: int = 50,
                           hours_to_expiry: float = 6.0) -> Optional[Dict[str, Any]]:
        """
        Estimate iron condor credit using FEZ IV and Black-Scholes.

        Args:
            index_price: Current Euro Stoxx 50 price
            otm_percent: How far OTM for short strikes (%)
            wing_width: Wing width in points
            hours_to_expiry: Hours until expiration (default 6 for 0DTE at 10am)

        Returns:
            Dict with credit details or None
        """
        iv = self._iv or self.get_iv()
        if iv is None:
            return None

        # Calculate strikes
        short_call = round(index_price * (1 + otm_percent / 100))
        short_put = round(index_price * (1 - otm_percent / 100))
        long_call = short_call + wing_width
        long_put = short_put - wing_width

        # Time to expiry in years
        T = hours_to_expiry / (365 * 24)
        r = self.RISK_FREE_RATE

        # Calculate option prices
        sc_price = black_scholes_call(index_price, short_call, T, r, iv)
        lc_price = black_scholes_call(index_price, long_call, T, r, iv)
        sp_price = black_scholes_put(index_price, short_put, T, r, iv)
        lp_price = black_scholes_put(index_price, long_put, T, r, iv)

        # Credit = sell short legs - buy long legs
        call_spread_credit = sc_price - lc_price
        put_spread_credit = sp_price - lp_price
        total_credit = call_spread_credit + put_spread_credit

        # Sanity check
        if total_credit < 0:
            self.logger.warning(f"Negative credit calculated: {total_credit}")
            return None

        return {
            'credit_points': total_credit,
            'credit_eur': total_credit * self.MULTIPLIER,
            'short_call': short_call,
            'short_put': short_put,
            'long_call': long_call,
            'long_put': long_put,
            'call_spread_credit': call_spread_credit,
            'put_spread_credit': put_spread_credit,
            'iv_used': iv,
            'source': 'yahoo_fez'
        }


def get_estimated_credit(index_price: float,
                         otm_percent: float = 1.0,
                         wing_width: int = 50,
                         logger: Optional[logging.Logger] = None) -> Tuple[float, str]:
    """
    Get estimated credit from Yahoo Finance FEZ options.

    Args:
        index_price: Current Euro Stoxx 50 price
        otm_percent: How far OTM (%)
        wing_width: Wing width in points
        logger: Optional logger

    Returns:
        Tuple of (credit_eur, source)
    """
    logger = logger or logging.getLogger(__name__)

    if not YFINANCE_AVAILABLE:
        logger.warning("yfinance not available")
        return 2.50, 'config'

    try:
        provider = YahooOptionsProvider(logger)
        result = provider.estimate_ic_credit(index_price, otm_percent, wing_width)

        if result and result.get('credit_eur', 0) > 0:
            return result['credit_eur'], 'yahoo_fez'

        return 2.50, 'config'

    except Exception as e:
        logger.error(f"Yahoo options error: {e}")
        return 2.50, 'config'


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # Test
    import yfinance as yf
    stoxx = yf.Ticker('^STOXX50E')
    price = stoxx.fast_info['lastPrice']

    print(f"Euro Stoxx 50: {price:.2f}")
    print()

    provider = YahooOptionsProvider()
    result = provider.estimate_ic_credit(price, otm_percent=1.0, wing_width=50)

    if result:
        print(f"IV used: {result['iv_used']:.1%}")
        print(f"Short Call {result['short_call']}: {result['call_spread_credit']:.2f} pts")
        print(f"Short Put  {result['short_put']}: {result['put_spread_credit']:.2f} pts")
        print(f"Total credit: {result['credit_points']:.2f} pts = €{result['credit_eur']:.2f}")
    else:
        print("Failed to estimate credit")
