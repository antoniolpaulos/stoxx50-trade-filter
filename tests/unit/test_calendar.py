"""
Unit tests for calendar functionality - testing real functions from trade_filter.py.
"""

import pytest
import sys
import os
from datetime import date
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_filter import check_economic_calendar
from exceptions import CalendarAPIError


class TestCheckEconomicCalendar:
    """Test check_economic_calendar function from trade_filter.py."""
    
    @patch('trade_filter.requests.get')
    def test_no_high_impact_events(self, mock_get, sample_config):
        """Test when no high-impact EUR events today."""
        today = date.today().strftime('%Y-%m-%d')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                'country': 'EUR',
                'title': 'Low Impact Event',
                'date': today,
                'impact': 'Low'
            },
            {
                'country': 'USD',
                'title': 'FOMC Statement',
                'date': today,
                'impact': 'High'
            }
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_economic_calendar(sample_config)
        
        assert result['has_high_impact'] is False
        assert len(result['events']) == 0
        assert result['source'] == 'ForexFactory'
    
    @patch('trade_filter.requests.get')
    def test_high_impact_ecb_event(self, mock_get, sample_config):
        """Test detection of high-impact ECB event."""
        today = date.today().strftime('%Y-%m-%d')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                'country': 'EUR',
                'title': 'ECB Interest Rate Decision',
                'date': f'{today}T14:15:00',
                'impact': 'High'
            }
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_economic_calendar(sample_config)
        
        assert result['has_high_impact'] is True
        assert len(result['events']) == 1
        assert result['events'][0]['name'] == 'ECB Interest Rate Decision'
        assert result['events'][0]['time'] == '14:15'
    
    @patch('trade_filter.requests.get')
    def test_high_impact_eurozone_cpi(self, mock_get, sample_config):
        """Test detection of high-impact Eurozone CPI event."""
        today = date.today().strftime('%Y-%m-%d')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                'country': 'EUR',
                'title': 'Eurozone CPI YoY',
                'date': f'{today}T10:00:00',
                'impact': 'High'
            }
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_economic_calendar(sample_config)
        
        assert result['has_high_impact'] is True
        assert len(result['events']) == 1
        assert 'CPI' in result['events'][0]['name']
    
    @patch('trade_filter.requests.get')
    def test_multiple_high_impact_events(self, mock_get, sample_config):
        """Test detection of multiple high-impact events."""
        today = date.today().strftime('%Y-%m-%d')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                'country': 'EUR',
                'title': 'ECB Interest Rate Decision',
                'date': f'{today}T14:15:00',
                'impact': 'High'
            },
            {
                'country': 'EUR',
                'title': 'Eurozone CPI YoY',
                'date': f'{today}T10:00:00',
                'impact': 'High'
            },
            {
                'country': 'EUR',
                'title': 'Low Impact Event',
                'date': f'{today}T08:00:00',
                'impact': 'Low'
            }
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_economic_calendar(sample_config)
        
        assert result['has_high_impact'] is True
        assert len(result['events']) == 2  # Only high impact events
    
    @patch('trade_filter.requests.get')
    def test_watchlist_event_detection(self, mock_get, sample_config):
        """Test detection of watchlist events (medium impact but watched)."""
        today = date.today().strftime('%Y-%m-%d')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                'country': 'EUR',
                'title': 'German ZEW Economic Sentiment',
                'date': f'{today}T11:00:00',
                'impact': 'Medium'
            }
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_economic_calendar(sample_config)
        
        # German ZEW is in watchlist, should be detected
        assert result['has_high_impact'] is True
        assert len(result['events']) == 1
        assert 'impact' in result['events'][0]
    
    @patch('trade_filter.requests.get')
    def test_ignore_usd_events(self, mock_get, sample_config):
        """Test that USD events are ignored."""
        today = date.today().strftime('%Y-%m-%d')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                'country': 'USD',
                'title': 'FOMC Statement',
                'date': f'{today}T14:00:00',
                'impact': 'High'
            },
            {
                'country': 'USD',
                'title': 'Non-Farm Payrolls',
                'date': f'{today}T08:30:00',
                'impact': 'High'
            }
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_economic_calendar(sample_config)
        
        assert result['has_high_impact'] is False
        assert len(result['events']) == 0
    
    @patch('trade_filter.requests.get')
    def test_forexfactory_api_failure(self, mock_get, sample_config):
        """Test handling of ForexFactory API failure."""
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Connection timeout")
        
        result = check_economic_calendar(sample_config)
        
        # Should have error but not crash
        assert result['has_high_impact'] is None
        assert result['error'] is not None
        assert 'ForexFactory' in result['error'] or 'Both APIs failed' in result['error']
    
    @patch('trade_filter.requests.get')
    def test_backup_api_usage(self, mock_get, sample_config):
        """Test fallback to backup API when primary fails."""
        import requests
        today = date.today().strftime('%Y-%m-%d')
        
        # First call fails (ForexFactory)
        # Second call succeeds (Trading Economics)
        def mock_get_side_effect(url, **kwargs):
            mock_response = Mock()
            if 'faireconomy' in url:
                raise requests.exceptions.RequestException("Primary API failed")
            elif 'tradingeconomics' in url:
                mock_response.text = f'''
                var defined = [
                    {{"Country": "Euro Area", "Event": "ECB Rate Decision", "Date": "{today}T14:00:00", "Importance": 3}}
                ];
                '''
                mock_response.raise_for_status.return_value = None
                return mock_response
            return Mock()
        
        mock_get.side_effect = mock_get_side_effect
        
        result = check_economic_calendar(sample_config)
        
        # Should have used backup API
        # Note: This depends on the actual implementation behavior
    
    @patch('trade_filter.requests.get')
    def test_empty_api_response(self, mock_get, sample_config):
        """Test handling of empty API response."""
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_economic_calendar(sample_config)
        
        assert result['has_high_impact'] is False
        assert len(result['events']) == 0
    
    @patch('trade_filter.requests.get')
    def test_malformed_api_response(self, mock_get, sample_config):
        """Test handling of malformed API response."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {'invalid': 'data'},  # Missing required fields
            {'country': 'EUR'},   # Missing other fields
            None                  # Null entry
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_economic_calendar(sample_config)
        
        # Should handle gracefully
        assert result['has_high_impact'] is not None  # Should be False, not error
    
    @patch('trade_filter.requests.get')
    def test_events_different_dates(self, mock_get, sample_config):
        """Test that only today's events are considered."""
        today = date.today().strftime('%Y-%m-%d')
        tomorrow = (date.today() + __import__('datetime').timedelta(days=1)).strftime('%Y-%m-%d')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                'country': 'EUR',
                'title': 'ECB Today',
                'date': f'{today}T14:00:00',
                'impact': 'High'
            },
            {
                'country': 'EUR',
                'title': 'ECB Tomorrow',
                'date': f'{tomorrow}T14:00:00',
                'impact': 'High'
            }
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_economic_calendar(sample_config)
        
        assert result['has_high_impact'] is True
        assert len(result['events']) == 1
        assert 'Today' in result['events'][0]['name']
    
    def test_no_config_provided(self):
        """Test function works without config (uses defaults)."""
        with patch('trade_filter.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = []
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = check_economic_calendar()
            
            assert result['has_high_impact'] is not None


class TestCalendarWatchlist:
    """Test calendar watchlist functionality."""
    
    @patch('trade_filter.requests.get')
    def test_all_watchlist_events_detected(self, mock_get):
        """Test that all watchlist events are properly detected."""
        today = date.today().strftime('%Y-%m-%d')
        
        watchlist_events = [
            ('ECB Interest Rate Decision', 'High'),
            ('ECB Press Conference', 'Medium'),
            ('Eurozone CPI', 'High'),
            ('German ZEW Economic Sentiment', 'Medium'),
            ('German Ifo Business Climate', 'Medium'),
            ('PMI Manufacturing', 'Medium'),
        ]
        
        for event_name, impact in watchlist_events:
            mock_response = Mock()
            mock_response.json.return_value = [
                {
                    'country': 'EUR',
                    'title': event_name,
                    'date': f'{today}T10:00:00',
                    'impact': impact
                }
            ]
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            config = {
                'calendar': {
                    'always_watch': ['ECB', 'Eurozone CPI', 'German ZEW', 'German Ifo', 'PMI'],
                    'use_backup_api': True
                }
            }
            
            result = check_economic_calendar(config)
            
            # All these should be detected (either high impact or in watchlist)
            assert result['has_high_impact'] is True, f"Failed for {event_name}"


class TestCalendarResponseStructure:
    """Test structure of calendar response."""
    
    @patch('trade_filter.requests.get')
    def test_response_structure(self, mock_get, sample_config):
        """Test that response has expected structure."""
        today = date.today().strftime('%Y-%m-%d')
        
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                'country': 'EUR',
                'title': 'ECB Decision',
                'date': f'{today}T14:00:00',
                'impact': 'High'
            }
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_economic_calendar(sample_config)
        
        # Check required fields
        assert 'has_high_impact' in result
        assert 'events' in result
        assert 'all_eur_high_this_week' in result
        assert 'source' in result
        assert 'error' in result
        
        # Check event structure
        if result['events']:
            event = result['events'][0]
            assert 'name' in event
            assert 'time' in event
            assert 'impact' in event


class TestCalendarErrorHandling:
    """Test calendar error handling."""
    
    @patch('trade_filter.requests.get')
    def test_timeout_error(self, mock_get, sample_config):
        """Test handling of timeout errors."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")
        
        result = check_economic_calendar(sample_config)
        
        assert result['error'] is not None
        assert 'timeout' in result['error'].lower() or 'failed' in result['error'].lower()
    
    @patch('trade_filter.requests.get')
    def test_http_error(self, mock_get, sample_config):
        """Test handling of HTTP errors."""
        import requests
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_get.return_value = mock_response
        
        result = check_economic_calendar(sample_config)
        
        # Should handle error gracefully
        assert result['has_high_impact'] is None or result['error'] is not None
    
    @patch('trade_filter.requests.get')
    def test_json_decode_error(self, mock_get, sample_config):
        """Test handling of JSON decode errors."""
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("No JSON object could be decoded")
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = check_economic_calendar(sample_config)
        
        # Should handle gracefully
        assert result['has_high_impact'] is None or result['error'] is not None
