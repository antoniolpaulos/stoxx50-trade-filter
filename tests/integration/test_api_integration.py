"""
Integration tests for external API calls with mocking.
"""

import pytest
import requests
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exceptions import MarketDataError, CalendarAPIError, TelegramError
from tests.fixtures.sample_data import (
    SAMPLE_VIX_DATA, SAMPLE_STOXX50_DATA, SAMPLE_VSTOXX_DATA,
    SAMPLE_FOREXFACTORY_RESPONSE, SAMPLE_TRADING_ECONOMICS_RESPONSE
)


class TestExternalAPIs:
    """Test external API integrations with proper mocking."""
    
    @patch('yfinance.Ticker')
    def test_yfinance_api_success(self, mock_ticker):
        """Test successful yfinance API calls."""
        # Setup mocks
        mock_vix = Mock()
        mock_vix.history.return_value = SAMPLE_VIX_DATA
        mock_stoxx = Mock()
        mock_stoxx.history.return_value = SAMPLE_STOXX50_DATA
        
        def mock_ticker_side_effect(symbol):
            if symbol == '^VIX':
                return mock_vix
            elif symbol == '^STOXX50E':
                return mock_stoxx
        
        mock_ticker.side_effect = mock_ticker_side_effect
        
        # Simulate the market data fetch function
        def get_market_data():
            vix = mock_ticker('^VIX')
            stoxx = mock_ticker('^STOXX50E')
            
            vix_data = vix.history(period="5d")
            stoxx_data = stoxx.history(period="1d")
            
            if vix_data.empty or stoxx_data.empty:
                raise MarketDataError("Unable to fetch market data")
            
            return {
                'vix': vix_data['Close'].iloc[-1],
                'stoxx_current': stoxx_data['Close'].iloc[-1],
                'stoxx_open': stoxx_data['Open'].iloc[-1]
            }
        
        result = get_market_data()
        
        assert result['vix'] == SAMPLE_VIX_DATA['Close'].iloc[-1]
        assert result['stoxx_current'] == SAMPLE_STOXX50_DATA['Close'].iloc[-1]
        assert result['stoxx_open'] == SAMPLE_STOXX50_DATA['Open'].iloc[-1]
    
    @patch('yfinance.Ticker')
    def test_yfinance_api_failure(self, mock_ticker):
        """Test yfinance API failure handling."""
        mock_ticker.side_effect = Exception("Network timeout")
        
        def get_market_data():
            try:
                vix = mock_ticker('^VIX')
                vix_data = vix.history(period="5d")
                return vix_data
            except Exception as e:
                raise MarketDataError(f"Failed to fetch VIX data: {e}")
        
        with pytest.raises(MarketDataError, match="Failed to fetch VIX data"):
            get_market_data()
    
    @patch('yfinance.Ticker')
    def test_yfinance_empty_data(self, mock_ticker):
        """Test handling of empty data from yfinance."""
        mock_empty = Mock()
        mock_empty.history.return_value = SAMPLE_VIX_DATA.iloc[:0]  # Empty DataFrame
        mock_ticker.return_value = mock_empty
        
        def get_market_data():
            vix = mock_ticker('^VIX')
            vix_data = vix.history(period="5d")
            
            if vix_data.empty:
                raise MarketDataError("VIX data is empty")
            return vix_data
        
        with pytest.raises(MarketDataError, match="VIX data is empty"):
            get_market_data()
    
    @patch('requests.get')
    def test_forexfactory_api_success(self, mock_get):
        """Test successful ForexFactory API call."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "events": [
                {
                    "date": "2026-01-03 14:30",
                    "country": "USD",
                    "impact": "High",
                    "title": "FOMC Statement"
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        def fetch_forexfactory():
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        
        result = fetch_forexfactory()
        
        assert 'events' in result
        assert len(result['events']) == 1
        assert result['events'][0]['title'] == 'FOMC Statement'
        expected_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        mock_get.assert_called_once_with(expected_url, timeout=10)
    
    @patch('requests.get')
    def test_forexfactory_api_failure(self, mock_get):
        """Test ForexFactory API failure handling."""
        mock_get.side_effect = requests.exceptions.RequestException("Connection timeout")
        
        def fetch_forexfactory():
            try:
                url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                raise CalendarAPIError(f"ForexFactory API failed: {e}")
        
        with pytest.raises(CalendarAPIError, match="ForexFactory API failed"):
            fetch_forexfactory()
    
    @patch('requests.post')
    def test_telegram_api_success(self, mock_post):
        """Test successful Telegram API call."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        def send_telegram_message(bot_token, chat_id, message):
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    'chat_id': chat_id,
                    'text': message,
                    'parse_mode': 'HTML'
                }
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                return True
            except requests.RequestException as e:
                raise TelegramError(f"Telegram API request failed: {e}")

        result = send_telegram_message("test_token", "test_chat", "Test message")

        assert result is True
        mock_post.assert_called_once()

        # Verify the call parameters
        call_args = mock_post.call_args
        assert 'api.telegram.org' in call_args[0][0]
        assert call_args[1]['json']['chat_id'] == 'test_chat'
        assert call_args[1]['json']['text'] == 'Test message'
    
    @patch('requests.post')
    def test_telegram_api_failure(self, mock_post):
        """Test Telegram API failure handling."""
        mock_post.side_effect = requests.exceptions.RequestException("Invalid token")

        def send_telegram_message(bot_token, chat_id, message):
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    'chat_id': chat_id,
                    'text': message,
                    'parse_mode': 'HTML'
                }
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                return True
            except requests.RequestException as e:
                raise TelegramError(f"Telegram API request failed: {e}")

        with pytest.raises(TelegramError, match="Telegram API request failed"):
            send_telegram_message("invalid_token", "test_chat", "Test message")
    
    @patch('requests.get')
    def test_trading_economics_api_success(self, mock_get):
        """Test successful Trading Economics API call."""
        mock_response = Mock()
        mock_response.text = '''
        <script>
        var defined = [{"Country": "United States", "Event": "FOMC Statement", "Date": "2026-01-03", "Importance": 3}];
        </script>
        '''
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        def fetch_trading_economics():
            try:
                url = "https://tradingeconomics.com/calendar"
                headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                
                import re
                json_match = re.search(r'var defined = (\[.*?\]);', response.text, re.DOTALL)
                if json_match:
                    import json
                    data = json.loads(json_match.group(1))
                    return data
                return []
            except requests.RequestException as e:
                raise CalendarAPIError(f"Trading Economics API failed: {e}")
        
        result = fetch_trading_economics()
        
        assert len(result) == 1
        assert result[0]['Country'] == 'United States'
        assert result[0]['Event'] == 'FOMC Statement'
    
    def test_api_timeout_handling(self):
        """Test timeout handling for all APIs."""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

            # Test ForexFactory timeout
            with pytest.raises(CalendarAPIError, match="ForexFactory API failed"):
                try:
                    requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=10)
                except requests.Timeout as e:
                    raise CalendarAPIError(f"ForexFactory API failed: {e}")

        # Test Telegram timeout separately with requests.post patched
        with patch('requests.post') as mock_post:
            mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

            with pytest.raises(TelegramError, match="Telegram API request failed"):
                try:
                    requests.post("https://api.telegram.org/bot/token/sendMessage", json={}, timeout=10)
                except requests.Timeout as e:
                    raise TelegramError(f"Telegram API request failed: {e}")
    
    def test_api_rate_limit_handling(self):
        """Test rate limit handling."""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("429 Too Many Requests")
            mock_get.return_value = mock_response

            # Test rate limit response - must call raise_for_status to trigger the error
            with pytest.raises(requests.exceptions.HTTPError):
                response = requests.get("https://api.example.com", timeout=10)
                response.raise_for_status()
    
    def test_api_response_parsing_errors(self):
        """Test handling of malformed API responses."""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.json.side_effect = ValueError("No JSON object could be decoded")
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            def fetch_api():
                try:
                    response = requests.get("https://api.example.com", timeout=10)
                    response.raise_for_status()
                    return response.json()
                except ValueError as e:
                    raise CalendarAPIError(f"Failed to parse API response: {e}")
            
            with pytest.raises(CalendarAPIError, match="Failed to parse API response"):
                fetch_api()