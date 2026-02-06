"""
Unit tests for Telegram bot functionality.
"""

import pytest
import json
import time
from unittest.mock import patch, MagicMock, Mock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from telegram_bot import TelegramBot, RateLimiter, get_bot, set_bot


class TestRateLimiter:
    """Test rate limiting functionality."""

    def test_allows_first_request(self):
        """First request should always be allowed."""
        limiter = RateLimiter(window=60, max_requests=5)
        assert limiter.is_allowed("user123") is True

    def test_allows_requests_within_limit(self):
        """Requests within limit should be allowed."""
        limiter = RateLimiter(window=60, max_requests=5)
        for _ in range(5):
            assert limiter.is_allowed("user123") is True

    def test_blocks_requests_over_limit(self):
        """Requests over limit should be blocked."""
        limiter = RateLimiter(window=60, max_requests=3)
        for _ in range(3):
            limiter.is_allowed("user123")
        assert limiter.is_allowed("user123") is False

    def test_separate_limits_per_user(self):
        """Each user should have separate limits."""
        limiter = RateLimiter(window=60, max_requests=2)
        limiter.is_allowed("user1")
        limiter.is_allowed("user1")
        # user1 is now at limit
        assert limiter.is_allowed("user1") is False
        # user2 should still be allowed
        assert limiter.is_allowed("user2") is True

    def test_get_remaining(self):
        """Test getting remaining requests."""
        limiter = RateLimiter(window=60, max_requests=5)
        assert limiter.get_remaining("user123") == 5
        limiter.is_allowed("user123")
        assert limiter.get_remaining("user123") == 4
        limiter.is_allowed("user123")
        assert limiter.get_remaining("user123") == 3

    def test_window_expiry(self):
        """Requests should be allowed again after window expires."""
        limiter = RateLimiter(window=1, max_requests=1)  # 1 second window
        limiter.is_allowed("user123")
        assert limiter.is_allowed("user123") is False
        time.sleep(1.1)  # Wait for window to expire
        assert limiter.is_allowed("user123") is True


class TestTelegramBotInit:
    """Test bot initialization."""

    def test_init_with_config(self):
        """Test bot initialization with valid config."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': 'test_token_123',
                'chat_id': '12345'
            }
        }
        bot = TelegramBot(config)

        assert bot.enabled is True
        assert bot.bot_token == 'test_token_123'
        assert bot.is_configured() is True

    def test_init_disabled(self):
        """Test bot initialization when disabled."""
        config = {
            'telegram': {
                'enabled': False,
                'bot_token': 'test_token',
                'chat_id': '12345'
            }
        }
        bot = TelegramBot(config)

        assert bot.enabled is False
        assert bot.is_configured() is False

    def test_init_placeholder_token(self):
        """Test bot initialization with placeholder token."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': 'YOUR_BOT_TOKEN',
                'chat_id': '12345'
            }
        }
        bot = TelegramBot(config)

        assert bot.is_configured() is False

    def test_init_empty_token(self):
        """Test bot initialization with empty token."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': '',
                'chat_id': '12345'
            }
        }
        bot = TelegramBot(config)

        assert bot.is_configured() is False

    def test_whitelist(self):
        """Test whitelist configuration."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': 'test_token'
            },
            'telegram_bot': {
                'allowed_user_ids': [123, 456, '789']
            }
        }
        bot = TelegramBot(config)

        assert bot.is_user_allowed(123) is True
        assert bot.is_user_allowed(456) is True
        assert bot.is_user_allowed(789) is True
        assert bot.is_user_allowed(999) is False

    def test_empty_whitelist_allows_all(self):
        """Empty whitelist should allow all users."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': 'test_token'
            },
            'telegram_bot': {
                'allowed_user_ids': []
            }
        }
        bot = TelegramBot(config)

        assert bot.is_user_allowed(123) is True
        assert bot.is_user_allowed(999999) is True


class TestBotCommands:
    """Test bot command handlers."""

    @pytest.fixture
    def bot(self):
        """Create a test bot instance."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': 'test_token'
            },
            'rules': {
                'vix_warn': 22,
                'intraday_change_max': 1.0
            }
        }
        return TelegramBot(config)

    @patch('telegram_api.requests.post')
    def test_cmd_start(self, mock_post, bot):
        """Test /start command."""
        mock_post.return_value.raise_for_status = Mock()

        user = {'first_name': 'TestUser', 'id': 123}
        response = bot._cmd_start('12345', user, [])

        assert 'Welcome' in response
        assert 'TestUser' in response
        mock_post.assert_called_once()

    @patch('telegram_api.requests.post')
    def test_cmd_help(self, mock_post, bot):
        """Test /help command."""
        mock_post.return_value.raise_for_status = Mock()

        response = bot._cmd_help('12345', {}, [])

        assert '/status' in response
        assert '/portfolio' in response
        assert '/history' in response
        assert '/analytics' in response

    @patch('telegram_api.requests.post')
    @patch.object(TelegramBot, '_get_market_status')
    def test_cmd_status_go(self, mock_status, mock_post, bot):
        """Test /status command with GO state."""
        mock_post.return_value.raise_for_status = Mock()
        mock_status.return_value = {
            'trade_state': 'GO',
            'stoxx_price': 5200.0,
            'stoxx_open': 5180.0,
            'intraday_change': 0.38,
            'vix': 18.5,
            'reasons': []
        }

        response = bot._cmd_status('12345', {}, [])

        assert 'GO' in response
        assert '5200' in response
        mock_post.assert_called_once()

    @patch('telegram_api.requests.post')
    @patch.object(TelegramBot, '_get_market_status')
    def test_cmd_status_no_go(self, mock_status, mock_post, bot):
        """Test /status command with NO_GO state."""
        mock_post.return_value.raise_for_status = Mock()
        mock_status.return_value = {
            'trade_state': 'NO_GO',
            'stoxx_price': 5200.0,
            'stoxx_open': 5100.0,
            'intraday_change': 1.96,
            'vix': 25.0,
            'reasons': ['Trend too strong (+1.96% up)']
        }

        response = bot._cmd_status('12345', {}, [])

        assert 'NO GO' in response
        assert 'Trend too strong' in response

    @patch('telegram_api.requests.post')
    @patch.object(TelegramBot, '_get_portfolio_summary')
    def test_cmd_portfolio(self, mock_summary, mock_post, bot):
        """Test /portfolio command."""
        mock_post.return_value.raise_for_status = Mock()
        mock_summary.return_value = {
            'always_trade': {
                'total_pnl': 150.0,
                'trade_count': 10,
                'win_rate': 70.0
            },
            'filtered': {
                'total_pnl': 200.0,
                'trade_count': 6,
                'win_rate': 83.3
            },
            'filter_edge': 50.0
        }

        response = bot._cmd_portfolio('12345', {}, [])

        assert 'SHADOW PORTFOLIO' in response
        assert '+150' in response
        assert '+200' in response
        assert '+50' in response

    @patch('telegram_api.requests.post')
    @patch.object(TelegramBot, '_get_trade_history')
    def test_cmd_history(self, mock_history, mock_post, bot):
        """Test /history command."""
        mock_post.return_value.raise_for_status = Mock()
        mock_history.return_value = {
            'trades': [
                {'date': '2026-02-05', 'pnl': 25.0, 'stoxx_close': 5200, 'portfolio': 'always_trade'},
                {'date': '2026-02-04', 'pnl': -35.0, 'stoxx_close': 5150, 'portfolio': 'filtered'}
            ]
        }

        response = bot._cmd_history('12345', {}, [])

        assert 'RECENT TRADES' in response
        assert '2026-02-05' in response
        assert '+25' in response

    @patch('telegram_api.requests.post')
    @patch.object(TelegramBot, '_get_trade_history')
    def test_cmd_history_with_arg(self, mock_history, mock_post, bot):
        """Test /history command with argument."""
        mock_post.return_value.raise_for_status = Mock()
        mock_history.return_value = {'trades': []}

        bot._cmd_history('12345', {}, ['10'])

        mock_history.assert_called_once_with(10)

    @patch('telegram_api.requests.post')
    @patch.object(TelegramBot, '_get_analytics')
    def test_cmd_analytics(self, mock_analytics, mock_post, bot):
        """Test /analytics command."""
        mock_post.return_value.raise_for_status = Mock()
        mock_analytics.return_value = {
            'always_trade': {
                'total_pnl': 100.0,
                'win_rate': 65.0,
                'avg_win': 30.0,
                'avg_loss': -45.0,
                'profit_factor': 1.5
            },
            'filtered': {
                'total_pnl': 150.0,
                'win_rate': 80.0,
                'avg_win': 35.0,
                'avg_loss': -40.0,
                'profit_factor': 2.0
            },
            'filter_edge': 50.0,
            'edge_per_trade': 8.33
        }

        response = bot._cmd_analytics('12345', {}, [])

        assert 'PERFORMANCE ANALYTICS' in response
        assert 'Profit Factor' in response
        assert 'Filter Effectiveness' in response


class TestHandleUpdate:
    """Test handling Telegram updates."""

    @pytest.fixture
    def bot(self):
        """Create a test bot instance."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': 'test_token'
            }
        }
        return TelegramBot(config)

    @patch('telegram_api.requests.post')
    def test_handle_message_command(self, mock_post, bot):
        """Test handling a command message."""
        mock_post.return_value.raise_for_status = Mock()

        update = {
            'message': {
                'from': {'id': 123, 'first_name': 'Test'},
                'chat': {'id': 456},
                'text': '/help'
            }
        }

        bot.handle_update(update)

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert 'sendMessage' in call_args[0][0]

    @patch('telegram_api.requests.post')
    def test_handle_unknown_command(self, mock_post, bot):
        """Test handling unknown command."""
        mock_post.return_value.raise_for_status = Mock()

        update = {
            'message': {
                'from': {'id': 123},
                'chat': {'id': 456},
                'text': '/unknowncommand'
            }
        }

        bot.handle_update(update)

        # Should send "Unknown command" message
        call_args = mock_post.call_args[1]
        assert 'Unknown command' in call_args['json']['text']

    def test_handle_empty_update(self, bot):
        """Test handling empty update."""
        result = bot.handle_update({})
        assert result is None

    @patch('telegram_api.requests.post')
    def test_rate_limiting(self, mock_post, bot):
        """Test rate limiting in update handling."""
        mock_post.return_value.raise_for_status = Mock()
        bot.rate_limiter = RateLimiter(window=60, max_requests=2)

        update = {
            'message': {
                'from': {'id': 123},
                'chat': {'id': 456},
                'text': '/help'
            }
        }

        # First two requests should work
        bot.handle_update(update)
        bot.handle_update(update)

        # Third request should be rate limited
        bot.handle_update(update)

        # Check last call was rate limit message
        calls = mock_post.call_args_list
        last_call = calls[-1][1]
        assert 'Rate limit' in last_call['json']['text']

    @patch('telegram_api.requests.post')
    def test_whitelist_rejection(self, mock_post, bot):
        """Test whitelist rejection."""
        mock_post.return_value.raise_for_status = Mock()
        bot.whitelist = {999}  # Only allow user 999

        update = {
            'message': {
                'from': {'id': 123},  # Not in whitelist
                'chat': {'id': 456},
                'text': '/help'
            }
        }

        bot.handle_update(update)

        # Should send unauthorized message
        call_args = mock_post.call_args[1]
        assert 'not authorized' in call_args['json']['text']


class TestSendMessage:
    """Test message sending."""

    @pytest.fixture
    def bot(self):
        """Create a test bot instance."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': 'test_token'
            }
        }
        return TelegramBot(config)

    @patch('telegram_api.requests.post')
    def test_send_simple_message(self, mock_post, bot):
        """Test sending a simple message."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {'ok': True, 'result': {'message_id': 123}}
        mock_post.return_value = mock_response

        result = bot.send_message('12345', 'Hello world')

        assert result is True
        mock_post.assert_called_once()

        call_args = mock_post.call_args[1]
        assert call_args['json']['chat_id'] == '12345'
        assert call_args['json']['text'] == 'Hello world'
        assert call_args['json']['parse_mode'] == 'HTML'

    @patch('telegram_api.requests.post')
    def test_send_message_with_keyboard(self, mock_post, bot):
        """Test sending message with inline keyboard."""
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json.return_value = {'ok': True, 'result': {'message_id': 123}}
        mock_post.return_value = mock_response

        keyboard = {
            'inline_keyboard': [
                [{'text': 'Button', 'callback_data': 'test'}]
            ]
        }

        result = bot.send_message('12345', 'Test', reply_markup=keyboard)

        assert result is True
        call_args = mock_post.call_args[1]
        assert 'reply_markup' in call_args['json']

    @patch('telegram_api.requests.post')
    def test_send_message_failure(self, mock_post, bot):
        """Test sending message failure."""
        import requests
        mock_post.side_effect = requests.exceptions.RequestException("Network error")

        result = bot.send_message('12345', 'Test')

        assert result is False

    def test_send_message_not_configured(self):
        """Test sending when bot not configured."""
        config = {'telegram': {'enabled': False}}
        bot = TelegramBot(config)

        result = bot.send_message('12345', 'Test')

        assert result is False


class TestCallbackHandling:
    """Test callback query handling."""

    @pytest.fixture
    def bot(self):
        """Create a test bot instance."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': 'test_token'
            },
            'rules': {
                'vix_warn': 22,
                'intraday_change_max': 1.0
            }
        }
        return TelegramBot(config)

    @patch('telegram_api.requests.post')
    @patch.object(TelegramBot, '_get_market_status')
    def test_refresh_status_callback(self, mock_status, mock_post, bot):
        """Test refresh_status callback."""
        mock_post.return_value.raise_for_status = Mock()
        mock_status.return_value = {
            'trade_state': 'GO',
            'stoxx_price': 5200.0,
            'intraday_change': 0.5,
            'vix': 18.0,
            'reasons': []
        }

        callback = {
            'id': 'callback123',
            'data': 'refresh_status',
            'from': {'id': 123},
            'message': {'chat': {'id': 456}}
        }

        bot._handle_callback(callback)

        # Should call answer callback and send status
        assert mock_post.call_count >= 1


class TestGlobalBotInstance:
    """Test global bot instance management."""

    def test_set_and_get_bot(self):
        """Test setting and getting global bot."""
        config = {'telegram': {'enabled': False}}
        bot = TelegramBot(config)

        set_bot(bot)
        retrieved = get_bot()

        assert retrieved is bot


class TestDataFetching:
    """Test data fetching methods."""

    @pytest.fixture
    def bot(self):
        """Create a test bot instance."""
        config = {
            'telegram': {
                'enabled': True,
                'bot_token': 'test_token'
            },
            'rules': {
                'vix_warn': 22,
                'intraday_change_max': 1.0
            }
        }
        return TelegramBot(config)

    @patch('monitor.get_monitor')
    def test_get_market_status_from_monitor(self, mock_get_monitor, bot):
        """Test getting market status from monitor."""
        mock_monitor = MagicMock()
        mock_state = MagicMock()
        mock_state.trade_state.value = 'GO'
        mock_state.stoxx_price = 5200.0
        mock_state.stoxx_open = 5180.0
        mock_state.intraday_change = 0.38
        mock_state.vix = 18.5
        mock_state.reasons = []
        mock_monitor.current_state = mock_state
        mock_get_monitor.return_value = mock_monitor

        status = bot._get_market_status()

        assert status['trade_state'] == 'GO'
        assert status['stoxx_price'] == 5200.0

    @patch('portfolio.load_portfolio')
    @patch('portfolio.get_portfolio_summary')
    def test_get_portfolio_summary(self, mock_summary, mock_load, bot):
        """Test getting portfolio summary."""
        mock_load.return_value = {'portfolios': {}}
        mock_summary.return_value = {
            'always_trade': {'total_pnl': 100.0},
            'filtered': {'total_pnl': 150.0},
            'filter_edge': 50.0
        }

        summary = bot._get_portfolio_summary()

        assert summary['filter_edge'] == 50.0

    @patch('portfolio.load_portfolio')
    def test_get_trade_history(self, mock_load, bot):
        """Test getting trade history."""
        mock_load.return_value = {
            'portfolios': {
                'always_trade': {
                    'history': [
                        {'date': '2026-02-05', 'pnl': 25.0, 'stoxx_close': 5200}
                    ]
                },
                'filtered': {
                    'history': [
                        {'date': '2026-02-04', 'pnl': -35.0, 'stoxx_close': 5150}
                    ]
                }
            }
        }

        history = bot._get_trade_history(5)

        assert len(history['trades']) == 2
        # Should be sorted by date descending
        assert history['trades'][0]['date'] == '2026-02-05'

    @patch('portfolio.load_portfolio')
    def test_get_analytics(self, mock_load, bot):
        """Test getting analytics."""
        mock_load.return_value = {
            'portfolios': {
                'always_trade': {
                    'total_pnl': 100.0,
                    'trade_count': 10,
                    'win_count': 7,
                    'history': [
                        {'pnl': 25.0}, {'pnl': 30.0}, {'pnl': -40.0}
                    ]
                },
                'filtered': {
                    'total_pnl': 150.0,
                    'trade_count': 6,
                    'win_count': 5,
                    'history': [
                        {'pnl': 25.0}, {'pnl': 30.0}
                    ]
                }
            }
        }

        analytics = bot._get_analytics()

        assert 'always_trade' in analytics
        assert 'filtered' in analytics
        assert 'filter_edge' in analytics
        assert analytics['filter_edge'] == 50.0
