"""
Test fixtures and sample data for SPX Trade Filter tests.
"""

import pandas as pd
from datetime import datetime, date, timedelta
import yaml

# Sample market data for testing
SAMPLE_VIX_DATA = pd.DataFrame({
    'Open': [18.5, 19.2, 20.1],
    'High': [19.0, 19.8, 20.5],
    'Low': [18.2, 18.9, 19.8],
    'Close': [18.8, 19.5, 20.2],
    'Volume': [1000000, 1100000, 1200000]
}, index=pd.to_datetime(['2026-01-01', '2026-01-02', '2026-01-03']))

SAMPLE_SPX_DATA = pd.DataFrame({
    'Open': [4800.0, 4850.0, 4900.0],
    'High': [4820.0, 4870.0, 4920.0],
    'Low': [4780.0, 4830.0, 4880.0],
    'Close': [4810.0, 4860.0, 4910.0],
    'Volume': [2000000, 2100000, 2200000]
}, index=pd.to_datetime(['2026-01-01', '2026-01-02', '2026-01-03']))

SAMPLE_VIX3M_DATA = pd.DataFrame({
    'Open': [19.5, 20.2, 21.1],
    'High': [20.0, 20.8, 21.5],
    'Low': [19.2, 19.9, 20.8],
    'Close': [19.8, 20.5, 21.2],
    'Volume': [500000, 550000, 600000]
}, index=pd.to_datetime(['2026-01-01', '2026-01-02', '2026-01-03']))

# Sample configuration
SAMPLE_CONFIG = {
    'rules': {
        'vix_max': 22,
        'intraday_change_max': 1.0
    },
    'strikes': {
        'otm_percent': 1.0,
        'wing_width': 25
    },
    'additional_filters': {
        'ma_deviation_max': 3.0,
        'prev_day_range_max': 2.0,
        'check_vix_term_structure': True
    },
    'calendar': {
        'always_watch': ['FOMC', 'CPI', 'NFP'],
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

# Sample economic calendar events
SAMPLE_CALENDAR_EVENTS = [
    {
        'date': '2026-01-03',
        'time': '14:30',
        'currency': 'USD',
        'impact': 'High',
        'event': 'FOMC Statement',
        'forecast': '',
        'previous': ''
    },
    {
        'date': '2026-01-05',
        'time': '08:30',
        'currency': 'USD',
        'impact': 'High',
        'event': 'Non-Farm Payrolls',
        'forecast': '150K',
        'previous': '120K'
    },
    {
        'date': '2026-01-07',
        'time': '08:30',
        'currency': 'USD',
        'impact': 'Medium',
        'event': 'Consumer Price Index',
        'forecast': '0.3%',
        'previous': '0.2%'
    }
]

# Sample ForexFactory API response
SAMPLE_FOREXFACTORY_RESPONSE = '''
{
    "events": [
        {
            "date": "2026-01-03",
            "time": "14:30",
            "currency": "USD",
            "impact": "High",
            "event": "FOMC Statement",
            "forecast": "",
            "previous": ""
        }
    ]
}
'''

# Sample Trading Economics API response
SAMPLE_TRADING_ECONOMICS_RESPONSE = '''
{
    "data": [
        {
            "Date": "2026-01-03T14:30:00",
            "Country": "United States",
            "Event": "FOMC Statement",
            "Importance": "High"
        }
    ]
}
'''

# Test scenarios data
TEST_SCENARIOS = {
    'go_conditions': {
        'vix': 16.5,
        'intraday_change': 0.5,
        'high_impact_events': False,
        'spx_current': 4800.0,
        'spx_open': 4776.0
    },
    'no_go_vix_high': {
        'vix': 25.0,
        'intraday_change': 0.5,
        'high_impact_events': False,
        'spx_current': 4800.0,
        'spx_open': 4776.0
    },
    'no_go_change_high': {
        'vix': 16.5,
        'intraday_change': 1.5,
        'high_impact_events': False,
        'spx_current': 4800.0,
        'spx_open': 4728.0
    },
    'no_go_events': {
        'vix': 16.5,
        'intraday_change': 0.5,
        'high_impact_events': True,
        'spx_current': 4800.0,
        'spx_open': 4776.0
    }
}

# Market holidays for testing
MARKET_HOLIDAYS = [
    date(2026, 1, 1),   # New Year's Day
    date(2026, 7, 4),   # Independence Day
    date(2026, 12, 25), # Christmas Day
]

# Invalid data samples for error testing
INVALID_MARKET_DATA = {
    'empty_df': pd.DataFrame(),
    'missing_columns': pd.DataFrame({'WrongColumn': [1, 2, 3]}),
    'negative_vix': pd.DataFrame({
        'Close': [-5.0, -10.0]
    }),
    'zero_spx': pd.DataFrame({
        'Close': [0.0, 0.0]
    })
}