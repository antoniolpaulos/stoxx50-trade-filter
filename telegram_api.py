#!/usr/bin/env python3
"""
Telegram API Client - Consolidated Telegram API wrapper.

Provides a unified interface for all Telegram API calls used in the project:
- Sending messages
- Answering callback queries
- Polling for updates
- Webhook management
"""

import json
import logging
import requests
from typing import Any, Dict, List, Optional


# API Base URL
TELEGRAM_API_BASE = "https://api.telegram.org/bot"


class TelegramClient:
    """
    Unified Telegram API client.

    Usage:
        client = TelegramClient(bot_token)
        client.send_message(chat_id, "Hello!")
    """

    def __init__(self, bot_token: str, logger: Optional[logging.Logger] = None):
        """
        Initialize Telegram client.

        Args:
            bot_token: Telegram bot token from @BotFather
            logger: Optional logger instance
        """
        self.bot_token = bot_token
        self.logger = logger or logging.getLogger(__name__)
        self._base_url = f"{TELEGRAM_API_BASE}{bot_token}"

    def is_configured(self) -> bool:
        """Check if client has a valid token."""
        return bool(self.bot_token) and self.bot_token != 'YOUR_BOT_TOKEN'

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """
        Make API request to Telegram.

        Args:
            method: HTTP method ('get' or 'post')
            endpoint: API endpoint (e.g., 'sendMessage')
            **kwargs: Additional arguments for requests

        Returns:
            Response JSON or None on error
        """
        url = f"{self._base_url}/{endpoint}"
        kwargs.setdefault('timeout', 10)

        try:
            if method.lower() == 'get':
                response = requests.get(url, **kwargs)
            else:
                response = requests.post(url, **kwargs)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            self.logger.error(f"Telegram API timeout: {endpoint}")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Telegram API error: {endpoint} - {e}")
            return None
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON response from Telegram: {endpoint}")
            return None

    def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = 'HTML',
        reply_markup: Optional[Dict] = None,
        disable_notification: bool = False
    ) -> bool:
        """
        Send a text message.

        Args:
            chat_id: Target chat ID
            text: Message text
            parse_mode: 'HTML' or 'Markdown'
            reply_markup: Optional inline keyboard
            disable_notification: Send silently

        Returns:
            True if sent successfully
        """
        if not self.is_configured():
            self.logger.warning("Telegram client not configured")
            return False

        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode,
            'disable_notification': disable_notification
        }

        if reply_markup:
            payload['reply_markup'] = json.dumps(reply_markup)

        result = self._request('post', 'sendMessage', json=payload)
        return result is not None and result.get('ok', False)

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
    ) -> bool:
        """
        Answer a callback query from inline keyboard.

        Args:
            callback_query_id: ID of the callback query
            text: Optional notification text
            show_alert: Show as alert popup instead of toast

        Returns:
            True if answered successfully
        """
        payload = {'callback_query_id': callback_query_id}

        if text:
            payload['text'] = text
            payload['show_alert'] = show_alert

        result = self._request('post', 'answerCallbackQuery', json=payload, timeout=5)
        return result is not None and result.get('ok', False)

    def get_updates(
        self,
        offset: int = 0,
        timeout: int = 30,
        allowed_updates: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Get updates (messages, callbacks, etc.) via long polling.

        Args:
            offset: Update ID offset (to acknowledge previous updates)
            timeout: Long polling timeout in seconds
            allowed_updates: List of update types to receive

        Returns:
            List of update objects
        """
        params = {
            'offset': offset,
            'timeout': timeout
        }

        if allowed_updates:
            params['allowed_updates'] = json.dumps(allowed_updates)

        result = self._request('get', 'getUpdates', params=params, timeout=timeout + 5)

        if result and result.get('ok'):
            return result.get('result', [])
        return []

    def set_webhook(self, webhook_url: str, secret_token: Optional[str] = None) -> bool:
        """
        Set webhook URL for receiving updates.

        Args:
            webhook_url: HTTPS URL for webhook
            secret_token: Optional secret for verification

        Returns:
            True if webhook set successfully
        """
        payload = {'url': webhook_url}

        if secret_token:
            payload['secret_token'] = secret_token

        result = self._request('post', 'setWebhook', json=payload)

        if result and result.get('ok'):
            self.logger.info(f"Webhook set to {webhook_url}")
            return True

        self.logger.error(f"Failed to set webhook: {result}")
        return False

    def delete_webhook(self) -> bool:
        """
        Delete webhook (switch to polling mode).

        Returns:
            True if webhook deleted successfully
        """
        result = self._request('post', 'deleteWebhook')
        return result is not None and result.get('ok', False)

    def get_me(self) -> Optional[Dict]:
        """
        Get bot information.

        Returns:
            Bot user object or None
        """
        result = self._request('get', 'getMe')

        if result and result.get('ok'):
            return result.get('result')
        return None


# ============================================================
# Convenience Functions (for backward compatibility)
# ============================================================

def send_notification(config: Dict, message: str) -> bool:
    """
    Send a notification message using config settings.

    This is a convenience function for simple notifications from
    trade_filter.py and other modules that don't need full bot functionality.

    Args:
        config: Application config with telegram section
        message: Message text to send

    Returns:
        True if sent successfully, False otherwise
    """
    telegram_config = config.get('telegram', {})

    if not telegram_config.get('enabled'):
        return False

    bot_token = telegram_config.get('bot_token', '')
    chat_id = telegram_config.get('chat_id', '')

    if not bot_token or not chat_id:
        return False

    client = TelegramClient(bot_token)
    return client.send_message(chat_id, message)


def get_chat_id_from_updates(bot_token: str) -> Optional[Dict[str, str]]:
    """
    Get chat ID from recent bot updates (for setup wizard).

    Args:
        bot_token: Telegram bot token

    Returns:
        Dict with 'chat_id' and 'user_name', or None if no messages found
    """
    client = TelegramClient(bot_token)
    updates = client.get_updates(timeout=0)

    if updates:
        last_update = updates[-1]
        message = last_update.get('message', {})
        chat_id = str(message.get('chat', {}).get('id', ''))
        user_name = message.get('from', {}).get('first_name', 'User')

        if chat_id:
            return {'chat_id': chat_id, 'user_name': user_name}

    return None
