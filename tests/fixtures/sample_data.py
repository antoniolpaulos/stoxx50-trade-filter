"""
Test fixtures and sample data for STOXX50 Trade Filter tests.
"""

import pandas as pd
from datetime import datetime, date, timedelta
import yaml

# Sample VIX data for testing (still used as reference/backup)
SAMPLE_VIX_DATA = pd.DataFrame({
    'Open': [18.5, 19.2, 20.1],
    'High': [19.0, 19.8, 20.5],
    'Low': [18.2, 18.9, 19.8],
    'Close': [18.8, 19.5, 20.2],
    'Volume': [1000000, 1100000, 1200000]
}, index=pd.to_datetime(['2026-01-01', '2026-01-02', '2026-01-03']))

# Sample STOXX50 data for testing (realistic Euro Stoxx 50 prices ~5180)
SAMPLE_STOXX50_DATA = pd.DataFrame({
    'Open': [5180.0, 5220.0, 5160.0],
    'High': [5200.0, 5240.0, 5190.0],
    'Low': [5150.0, 5190.0, 5130.0],
    'Close': [5180.0, 5220.0, 5160.0],
    'Volume': [1500000, 1600000, 1550000]
}, index=pd.to_datetime(['2026-01-01', '2026-01-02', '2026-01-03']))

# Sample VSTOXX data for testing (Euro Stoxx 50 volatility index)
SAMPLE_VSTOXX_DATA = pd.DataFrame({
    'Open': [18.5, 19.2, 20.1],
    'High': [19.0, 19.8, 20.5],
    'Low': [18.2, 18.9, 19.8],
    'Close': [18.8, 19.5, 20.2],
    'Volume': [500000, 550000, 600000]
}, index=pd.to_datetime(['2026-01-01', '2026-01-02', '2026-01-03']))

# Sample VSTOXX 3-month data for term structure
SAMPLE_VSTOXX3M_DATA = pd.DataFrame({
    'Open': [19.5, 20.2, 21.1],
    'High': [20.0, 20.8, 21.5],
    'Low': [19.2, 19.9, 20.8],
    'Close': [19.8, 20.5, 21.2],
    'Volume': [300000, 350000, 400000]
}, index=pd.to_datetime(['2026-01-01', '2026-01-02', '2026-01-03']))

# Sample configuration with STOXX50 specific settings
SAMPLE_CONFIG = {
    'rules': {
        'vstoxx_max': 25,  # VSTOXX max threshold (not VIX)
        'intraday_change_max': 1.0
    },
    'strikes': {
        'otm_percent': 1.0,
        'wing_width': 50  # Euro Stoxx 50 wing width
    },
    'additional_filters': {
        'ma_deviation_max': 3.0,
        'prev_day_range_max': 2.0,
        'check_vstoxx_term_structure': False
    },
    'calendar': {
        'always_watch': [
            'ECB',
            'ECB Interest Rate Decision',
            'ECB Press Conference',
            'Eurozone CPI',
            'Eurozone GDP',
            'German CPI',
            'German GDP',
            'German ZEW',
            'German Ifo',
            'French CPI',
            'Italian CPI',
            'PMI',
            'Eurozone Unemployment'
        ],
        'use_backup_api': True
    },
    'telegram': {
        'enabled': False,
        'bot_token': 'test_token',
        'chat_id': 'test_chat'
    },
    'logging': {
        'file': 'trade_filter.log',
        'level': 'INFO'
    }
}

# Sample economic calendar events - EUR/Eurozone focused
SAMPLE_CALENDAR_EVENTS = [
    {
        'date': '2026-01-03',
        'time': '14:30',
        'currency': 'EUR',
        'impact': 'High',
        'event': 'ECB Interest Rate Decision',
        'forecast': '',
        'previous': ''
    },
    {
        'date': '2026-01-05',
        'time': '10:00',
        'currency': 'EUR',
        'impact': 'High',
        'event': 'Eurozone CPI',
        'forecast': '2.2%',
        'previous': '2.1%'
    },
    {
        'date': '2026-01-07',
        'time': '11:00',
        'currency': 'EUR',
        'impact': 'Medium',
        'event': 'German ZEW Economic Sentiment',
        'forecast': '15.0',
        'previous': '10.3'
    }
]

# Sample ForexFactory API response - EUR focused
SAMPLE_FOREXFACTORY_RESPONSE = [
    {
        "country": "EUR",
        "title": "ECB Interest Rate Decision",
        "date": "2026-01-03T14:30:00",
        "impact": "High"
    },
    {
        "country": "EUR",
        "title": "Eurozone CPI",
        "date": "2026-01-05T10:00:00",
        "impact": "High"
    },
    {
        "country": "DE",
        "title": "German ZEW Economic Sentiment",
        "date": "2026-01-07T11:00:00",
        "impact": "Medium"
    }
]

# Sample Trading Economics API response - Eurozone focused
SAMPLE_TRADING_ECONOMICS_RESPONSE = '''
{
    "data": [
        {
            "Date": "2026-01-03T14:30:00",
            "Country": "Euro Area",
            "Event": "ECB Interest Rate Decision",
            "Importance": 3
        },
        {
            "Date": "2026-01-05T10:00:00",
            "Country": "Germany",
            "Event": "German ZEW Economic Sentiment",
            "Importance": 3
        }
    ]
}
'''

# Test scenarios data - updated for STOXX50
TEST_SCENARIOS = {
    'go_conditions': {
        'vstoxx': 18.5,  # VSTOXX (not VIX)
        'vix': 16.5,  # Keep VIX for reference
        'intraday_change': 0.5,
        'high_impact_events': False,
        'stoxx_current': 5180.0,
        'stoxx_open': 5154.0
    },
    'no_go_vstoxx_high': {
        'vstoxx': 28.0,  # Above 25 threshold
        'vix': 25.0,
        'intraday_change': 0.5,
        'high_impact_events': False,
        'stoxx_current': 5180.0,
        'stoxx_open': 5154.0
    },
    'no_go_change_high': {
        'vstoxx': 18.5,
        'vix': 16.5,
        'intraday_change': 1.5,  # Above 1% threshold
        'high_impact_events': False,
        'stoxx_current': 5180.0,
        'stoxx_open': 5102.3  # ~1.5% down
    },
    'no_go_events': {
        'vstoxx': 18.5,
        'vix': 16.5,
        'intraday_change': 0.5,
        'high_impact_events': True,
        'stoxx_current': 5180.0,
        'stoxx_open': 5154.0
    }
}

# Market holidays for testing (European holidays - weekdays only)
MARKET_HOLIDAYS = [
    date(2026, 1, 1),   # New Year's Day (Thursday)
    date(2026, 4, 3),   # Good Friday
    date(2026, 12, 25), # Christmas Day (Friday)
]

# Invalid data samples for error testing
INVALID_MARKET_DATA = {
    'empty_df': pd.DataFrame(),
    'missing_columns': pd.DataFrame({'WrongColumn': [1, 2, 3]}),
    'negative_vstoxx': pd.DataFrame({
        'Close': [-5.0, -10.0]
    }),
    'zero_stoxx50': pd.DataFrame({
        'Close': [0.0, 0.0]
    })
}

# Market data tickers for STOXX50
TICKERS = {
    'vstoxx': '^V2TX',
    'stoxx50': '^STOXX50E',
    'vix': '^VIX'
}

# Default backtest parameters
BACKTEST_DEFAULTS = {
    'wing_width': 50,
    'credit': 2.50,
    'vstoxx_threshold': 25,
    'intraday_change_threshold': 1.0
}

# Sample Telegram test data
SAMPLE_TELEGRAM_CONFIG = {
    'enabled': True,
    'bot_token': '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11',
    'chat_id': '123456789'
}

# Sample backtest results for testing
SAMPLE_BACKTEST_RESULT = {
    'date': '2026-01-03',
    'vstoxx': 18.5,
    'stoxx_open': 5180.0,
    'stoxx_entry': 5182.0,
    'stoxx_close': 5195.0,
    'intraday_change': 0.5,
    'traded': True,
    'call_strike': 5232,
    'put_strike': 5128,
    'pnl': 25.0
}
