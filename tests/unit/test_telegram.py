"""
Unit tests for Telegram functionality - testing real functions from trade_filter.py.
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_filter import send_telegram_message
from exceptions import TelegramError


class TestSendTelegramMessage:
    """Test send_telegram_message function from trade_filter.py."""
    
    @patch('telegram_api.requests.post')
    def test_send_message_success(self, mock_post, sample_telegram_config):
        """Test successful Telegram message sending."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        config = {
            'telegram': sample_telegram_config
        }
        message = "✅ Test message from STOXX50 Trade Filter"
        
        send_telegram_message(config, message)
        
        # Verify the API call was made
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Check URL contains bot token
        assert sample_telegram_config['bot_token'] in call_args[0][0]
        assert 'api.telegram.org' in call_args[0][0]
        
        # Check payload
        assert call_args[1]['json']['chat_id'] == sample_telegram_config['chat_id']
        assert call_args[1]['json']['text'] == message
        assert call_args[1]['json']['parse_mode'] == 'HTML'
    
    @patch('telegram_api.requests.post')
    def test_send_message_with_html(self, mock_post, sample_telegram_config):
        """Test sending message with HTML formatting."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        config = {
            'telegram': sample_telegram_config
        }
        message = """
        <b>STOXX50 0DTE Iron Condor</b>
        <pre>
        VSTOXX: 18.5
        STOXX: 5180.0
        Intraday: +0.5%
        </pre>
        """
        
        send_telegram_message(config, message)
        
        call_args = mock_post.call_args
        assert '<b>' in call_args[1]['json']['text']
        assert '<pre>' in call_args[1]['json']['text']
        assert call_args[1]['json']['parse_mode'] == 'HTML'
    
    @patch('telegram_api.requests.post')
    def test_send_go_notification(self, mock_post, sample_telegram_config):
        """Test sending GO notification with strike prices."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        config = {
            'telegram': sample_telegram_config
        }
        message = """
<b>STOXX50 0DTE Iron Condor - 2026-02-04 10:00</b>

VIX: 16.50
STOXX: 5180.00
Intraday: +0.50%

✅ <b>GO - CONDITIONS FAVORABLE</b>

Short Put: 5128
Short Call: 5232
Wings: 50 pts
"""
        
        send_telegram_message(config, message)
        
        call_args = mock_post.call_args
        assert 'GO - CONDITIONS FAVORABLE' in call_args[1]['json']['text']
        assert '5128' in call_args[1]['json']['text']
        assert '5232' in call_args[1]['json']['text']
    
    @patch('telegram_api.requests.post')
    def test_send_no_go_notification(self, mock_post, sample_telegram_config):
        """Test sending NO-GO notification."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        config = {
            'telegram': sample_telegram_config
        }
        message = """
<b>STOXX50 0DTE Iron Condor - 2026-02-04 10:00</b>

VIX: 16.50
STOXX: 5180.00
Intraday: +0.50%

🛑 <b>NO GO - DO NOT TRADE</b>

Reasons:
• High-impact economic event(s): ECB Interest Rate Decision
"""
        
        send_telegram_message(config, message)
        
        call_args = mock_post.call_args
        assert 'NO GO - DO NOT TRADE' in call_args[1]['json']['text']
        assert 'ECB Interest Rate Decision' in call_args[1]['json']['text']
    
    @patch('telegram_api.requests.post')
    def test_telegram_disabled(self, mock_post, sample_telegram_config):
        """Test that no message is sent when Telegram is disabled."""
        config = {
            'telegram': {
                'enabled': False,
                'bot_token': sample_telegram_config['bot_token'],
                'chat_id': sample_telegram_config['chat_id']
            }
        }
        
        send_telegram_message(config, "Test message")
        
        # Should not make any API calls when disabled
        mock_post.assert_not_called()
    
    @patch('telegram_api.requests.post')
    def test_missing_bot_token(self, mock_post):
        """Test behavior when bot_token is missing."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': '',
                'chat_id': '123456789'
            }
        }
        
        send_telegram_message(config, "Test message")
        
        # Should not make API call with empty token
        mock_post.assert_not_called()
    
    @patch('telegram_api.requests.post')
    def test_missing_chat_id(self, mock_post):
        """Test behavior when chat_id is missing."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11',
                'chat_id': ''
            }
        }
        
        send_telegram_message(config, "Test message")
        
        # Should not make API call with empty chat_id
        mock_post.assert_not_called()
    
    @patch('telegram_api.requests.post')
    def test_placeholder_token(self, mock_post):
        """Test behavior when using placeholder token."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': 'YOUR_BOT_TOKEN',
                'chat_id': '123456789'
            }
        }
        
        send_telegram_message(config, "Test message")
        
        # Should not make API call with placeholder
        mock_post.assert_not_called()
    
    @patch('telegram_api.requests.post')
    def test_telegram_api_failure(self, mock_post, sample_telegram_config):
        """Test handling of Telegram API failure."""
        import requests
        mock_post.side_effect = requests.exceptions.RequestException("Connection error")
        
        config = {
            'telegram': sample_telegram_config
        }
        
        # Should not raise exception, just silently fail
        send_telegram_message(config, "Test message")
    
    @patch('telegram_api.requests.post')
    def test_telegram_timeout(self, mock_post, sample_telegram_config):
        """Test handling of Telegram API timeout."""
        import requests
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")
        
        config = {
            'telegram': sample_telegram_config
        }
        
        # Should not raise exception, just silently fail
        send_telegram_message(config, "Test message")
    
    @patch('telegram_api.requests.post')
    def test_telegram_invalid_token(self, mock_post, sample_telegram_config):
        """Test handling of invalid bot token."""
        import requests as req
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = req.exceptions.HTTPError("Unauthorized")
        mock_post.return_value = mock_response

        config = {
            'telegram': sample_telegram_config
        }

        # Should not raise exception, just silently fail
        send_telegram_message(config, "Test message")
    
    @patch('telegram_api.requests.post')
    def test_long_message(self, mock_post, sample_telegram_config):
        """Test sending long messages."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        config = {
            'telegram': sample_telegram_config
        }
        
        # Message under 4096 limit
        message = "A" * 4000
        
        send_telegram_message(config, message)
        
        # Should be called with long message
        mock_post.assert_called_once()
    
    @patch('telegram_api.requests.post')
    def test_message_with_emojis(self, mock_post, sample_telegram_config):
        """Test sending message with emojis."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        config = {
            'telegram': sample_telegram_config
        }
        message = "✅ 🛑 📈 📉 🚀 📊"
        
        send_telegram_message(config, message)
        
        call_args = mock_post.call_args
        assert '✅' in call_args[1]['json']['text']


class TestTelegramConfiguration:
    """Test Telegram configuration handling."""
    
    def test_valid_telegram_config(self, sample_telegram_config):
        """Test valid Telegram configuration."""
        assert sample_telegram_config['enabled'] is True
        assert sample_telegram_config['bot_token'] != ''
        assert sample_telegram_config['chat_id'] != ''
        
        # Token should follow Telegram format
        assert ':' in sample_telegram_config['bot_token']
        
        # Chat ID should be numeric or start with -
        chat_id = sample_telegram_config['chat_id']
        assert chat_id.isdigit() or chat_id.startswith('-')
    
    @patch('telegram_api.requests.post')
    def test_no_telegram_section(self, mock_post):
        """Test behavior when Telegram section is missing."""
        config = {}  # No telegram section
        
        send_telegram_message(config, "Test message")
        
        # Should not make API call
        mock_post.assert_not_called()
    
    @patch('telegram_api.requests.post')
    def test_incomplete_telegram_section(self, mock_post):
        """Test behavior when Telegram section is incomplete."""
        config = {
            'telegram': {
                'enabled': True
                # Missing bot_token and chat_id
            }
        }
        
        send_telegram_message(config, "Test message")
        
        # Should not make API call
        mock_post.assert_not_called()
