#!/usr/bin/env python3
"""
Telegram Bot for STOXX50 Trade Filter.
Provides interactive commands to query portfolio, market data, and trade history.

Commands:
    /status     - Current market conditions and GO/NO-GO status
    /portfolio  - Shadow portfolio summary
    /history    - Recent trade history
    /analytics  - P&L analytics and metrics
    /help       - Show available commands
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from functools import wraps
from collections import defaultdict

from flask import Flask, request, jsonify

from logger import get_logger
from exceptions import TelegramError
from telegram_api import TelegramClient

# Rate limiting settings
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX_REQUESTS = 10  # max requests per window


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, window: int = RATE_LIMIT_WINDOW, max_requests: int = RATE_LIMIT_MAX_REQUESTS):
        self.window = window
        self.max_requests = max_requests
        self.requests: Dict[str, list] = defaultdict(list)

    def is_allowed(self, user_id: str) -> bool:
        """Check if user is within rate limit."""
        now = time.time()

        # Clean old requests
        self.requests[user_id] = [
            t for t in self.requests[user_id]
            if now - t < self.window
        ]

        if len(self.requests[user_id]) >= self.max_requests:
            return False

        self.requests[user_id].append(now)
        return True

    def get_remaining(self, user_id: str) -> int:
        """Get remaining requests in window."""
        now = time.time()
        recent = [t for t in self.requests[user_id] if now - t < self.window]
        return max(0, self.max_requests - len(recent))


class TelegramBot:
    """Telegram bot handler for STOXX50 Trade Filter."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize bot with configuration.

        Args:
            config: Application configuration dict
        """
        self.config = config
        self.logger = get_logger()

        telegram_config = config.get('telegram', {})
        self.bot_token = telegram_config.get('bot_token', '')
        self.enabled = telegram_config.get('enabled', False)

        # Initialize Telegram API client
        self._client = TelegramClient(self.bot_token, self.logger)

        # Whitelist (if empty, allow all)
        bot_config = config.get('telegram_bot', {})
        self.whitelist = set(bot_config.get('allowed_user_ids', []))

        # Rate limiting (can be disabled in config)
        self.rate_limit_enabled = bot_config.get('rate_limit_enabled', True)
        self.rate_limiter = RateLimiter(
            window=bot_config.get('rate_limit_window', RATE_LIMIT_WINDOW),
            max_requests=bot_config.get('rate_limit_max_requests', RATE_LIMIT_MAX_REQUESTS)
        )

        # Per-user alert settings
        self.user_alert_settings: Dict[str, bool] = {}

        # Command handlers
        self.commands: Dict[str, Callable] = {
            'start': self._cmd_start,
            'help': self._cmd_help,
            'status': self._cmd_status,
            'portfolio': self._cmd_portfolio,
            'history': self._cmd_history,
            'analytics': self._cmd_analytics,
            'alerts': self._cmd_alerts,
            'backtest': self._cmd_backtest,
        }

    def is_configured(self) -> bool:
        """Check if bot is properly configured."""
        return bool(self.enabled and self.bot_token and self.bot_token != 'YOUR_BOT_TOKEN')

    def is_user_allowed(self, user_id: int) -> bool:
        """Check if user is allowed to use the bot."""
        if not self.whitelist:
            return True  # No whitelist = allow all
        return str(user_id) in self.whitelist or user_id in self.whitelist

    def send_message(self, chat_id: str, text: str, parse_mode: str = 'HTML',
                     reply_markup: Optional[Dict] = None) -> bool:
        """
        Send message to chat.

        Args:
            chat_id: Telegram chat ID
            text: Message text
            parse_mode: HTML or Markdown
            reply_markup: Optional inline keyboard

        Returns:
            True if sent successfully
        """
        if not self.is_configured():
            self.logger.warning("Telegram bot not configured")
            return False

        return self._client.send_message(chat_id, text, parse_mode, reply_markup)

    def handle_update(self, update: Dict[str, Any]) -> Optional[str]:
        """
        Handle incoming Telegram update.

        Args:
            update: Telegram update object

        Returns:
            Response text if any
        """
        if not self.is_configured():
            return None

        # Extract message
        message = update.get('message') or update.get('edited_message')
        if not message:
            # Handle callback queries (inline buttons)
            callback = update.get('callback_query')
            if callback:
                return self._handle_callback(callback)
            return None

        # Get user info
        user = message.get('from', {})
        user_id = user.get('id')
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '')

        if not user_id or not chat_id:
            return None

        # Check whitelist
        if not self.is_user_allowed(user_id):
            self.logger.warning(f"Unauthorized bot access attempt from user {user_id}")
            self.send_message(chat_id, "Sorry, you are not authorized to use this bot.")
            return None

        # Check rate limit (if enabled)
        if self.rate_limit_enabled and not self.rate_limiter.is_allowed(str(user_id)):
            remaining_time = RATE_LIMIT_WINDOW
            self.send_message(
                chat_id,
                f"Rate limit exceeded. Please wait {remaining_time} seconds."
            )
            return None

        # Handle commands
        if text.startswith('/'):
            return self._handle_command(text, chat_id, user)

        return None

    def _handle_command(self, text: str, chat_id: str, user: Dict) -> Optional[str]:
        """Handle a command message."""
        # Parse command
        parts = text.split()
        command = parts[0][1:].split('@')[0].lower()  # Remove / and @botname
        args = parts[1:] if len(parts) > 1 else []

        handler = self.commands.get(command)
        if handler:
            try:
                response = handler(chat_id, user, args)
                return response
            except Exception as e:
                self.logger.exception(f"Error handling command {command}: {e}")
                self.send_message(chat_id, f"Error: {str(e)}")
                return None
        else:
            self.send_message(chat_id, f"Unknown command: /{command}\nUse /help for available commands.")
            return None

    def _handle_callback(self, callback: Dict) -> Optional[str]:
        """Handle callback query from inline button."""
        callback_id = callback.get('id')
        data = callback.get('data', '')
        chat_id = callback.get('message', {}).get('chat', {}).get('id')
        user = callback.get('from', {})

        if not chat_id:
            return None

        # Check authorization
        if not self.is_user_allowed(user.get('id')):
            return None

        # Answer callback to remove loading state
        self._answer_callback(callback_id)

        # Route callback data to appropriate handler
        if data == 'refresh_status':
            self._cmd_status(chat_id, user, [])
        elif data == 'refresh_portfolio':
            self._cmd_portfolio(chat_id, user, [])
        elif data == 'show_history':
            self._cmd_history(chat_id, user, [])
        elif data == 'show_analytics':
            self._cmd_analytics(chat_id, user, [])

        return None

    def _answer_callback(self, callback_id: str):
        """Answer callback query."""
        self._client.answer_callback_query(callback_id)

    # ========== Command Handlers ==========

    def _cmd_start(self, chat_id: str, user: Dict, args: list) -> str:
        """Handle /start command."""
        name = user.get('first_name', 'there')

        text = (
            f"Hi {name}! Welcome to STOXX50 Trade Filter Bot.\n\n"
            "I can help you monitor market conditions and track your shadow portfolio.\n\n"
            "Available commands:\n"
            "/status - Current market status\n"
            "/portfolio - Shadow portfolio summary\n"
            "/history - Recent trades\n"
            "/analytics - Performance metrics\n"
            "/help - Show this help"
        )

        self.send_message(chat_id, text)
        return text

    def _cmd_help(self, chat_id: str, user: Dict, args: list) -> str:
        """Handle /help command."""
        text = (
            "<b>STOXX50 Trade Filter Bot</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Commands:</b>\n\n"
            "/status\n"
            "Shows current market conditions:\n"
            "• VIX level and warning status\n"
            "• STOXX50 intraday change\n"
            "• GO/NO-GO verdict\n\n"
            "/portfolio\n"
            "Shadow portfolio summary:\n"
            "• Always Trade vs Filtered P&L\n"
            "• Win rates and trade counts\n"
            "• Filter edge calculation\n\n"
            "/history [n]\n"
            "Recent trade history:\n"
            "• Last N trades (default: 5)\n"
            "• Shows P&L for each trade\n\n"
            "/analytics\n"
            "Performance analytics:\n"
            "• Total P&L and win rate\n"
            "• Average win/loss amounts\n"
            "• Filter effectiveness\n\n"
            "/alerts [on|off]\n"
            "Toggle real-time market alerts:\n"
            "• Check current alert status\n"
            "• Enable or disable notifications\n\n"
            "/backtest [days]\n"
            "Run historical backtest:\n"
            "• Test strategy for last N days\n"
            "• Shows trades, win rate, P&L\n"
            "• Max 365 days\n\n"
            "<i>Bot checks are rate-limited to prevent abuse.</i>"
        )

        self.send_message(chat_id, text)
        return text

    def _cmd_status(self, chat_id: str, user: Dict, args: list) -> str:
        """Handle /status command - show current market status."""
        try:
            status = self._get_market_status()

            if status.get('error'):
                text = f"Error fetching market data: {status['error']}"
                self.send_message(chat_id, text)
                return text

            # Build status message
            trade_state = status.get('trade_state', 'UNKNOWN')
            state_emoji = "" if trade_state == 'GO' else "" if trade_state == 'NO_GO' else ""

            vix = status.get('vix')
            vix_display = f"{vix:.2f}" if vix else "N/A"
            vix_status = ""
            if vix:
                vix_warn = self.config.get('rules', {}).get('vix_warn', 22)
                if vix > vix_warn:
                    vix_status = f" (&gt; {vix_warn} ⚠)"
                else:
                    vix_status = f" (&lt; {vix_warn} ✓)"

            intraday = status.get('intraday_change', 0)
            intraday_display = f"{intraday:+.2f}%"
            intraday_max = self.config.get('rules', {}).get('intraday_change_max', 1.0)
            intraday_status = ""
            if abs(intraday) <= intraday_max:
                intraday_status = f" (|{abs(intraday):.2f}%| &lt; {intraday_max}% ✓)"
            else:
                intraday_status = f" (|{abs(intraday):.2f}%| &gt; {intraday_max}% ✗)"

            stoxx = status.get('stoxx_price')
            stoxx_display = f"{stoxx:.2f}" if stoxx else "N/A"

            text = (
                f"{state_emoji} <b>STOXX50 STATUS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"<b>Last Check:</b> {datetime.now().strftime('%H:%M CET')}\n"
                f"<b>VIX:</b> {vix_display}{vix_status}\n"
                f"<b>STOXX:</b> {stoxx_display}\n"
                f"<b>Intraday:</b> {intraday_display}{intraday_status}\n"
            )

            # Add reasons if NO_GO
            reasons = status.get('reasons', [])
            if reasons:
                text += f"\n<b>Blockers:</b>\n"
                for reason in reasons:
                    text += f"• {reason}\n"

            text += f"\n━━━━━━━━━━━━━━━━━━━━━\n"

            if trade_state == 'GO':
                text += f"<b>VERDICT:</b>  GO - Trade today"
            else:
                text += f"<b>VERDICT:</b>  NO GO - Skip today"

            # Add inline keyboard
            keyboard = {
                'inline_keyboard': [
                    [
                        {'text': ' Refresh', 'callback_data': 'refresh_status'},
                        {'text': ' Portfolio', 'callback_data': 'refresh_portfolio'}
                    ]
                ]
            }

            self.send_message(chat_id, text, reply_markup=keyboard)
            return text

        except Exception as e:
            self.logger.exception(f"Error in /status: {e}")
            error_text = f"Failed to get market status: {str(e)}"
            self.send_message(chat_id, error_text)
            return error_text

    def _cmd_portfolio(self, chat_id: str, user: Dict, args: list) -> str:
        """Handle /portfolio command - show portfolio summary."""
        try:
            summary = self._get_portfolio_summary()

            if summary.get('error'):
                text = f"Error loading portfolio: {summary['error']}"
                self.send_message(chat_id, text)
                return text

            always = summary.get('always_trade', {})
            filtered = summary.get('filtered', {})
            edge = summary.get('filter_edge', 0)

            always_pnl = always.get('total_pnl', 0)
            filtered_pnl = filtered.get('total_pnl', 0)

            always_pnl_emoji = "" if always_pnl >= 0 else ""
            filtered_pnl_emoji = "" if filtered_pnl >= 0 else ""
            edge_emoji = "" if edge > 0 else "" if edge < 0 else ""

            text = (
                f" <b>SHADOW PORTFOLIO</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"<b>Always Trade:</b>\n"
                f"  {always_pnl_emoji} P&L: {always_pnl:+.0f}\n"
                f"  Trades: {always.get('trade_count', 0)}\n"
                f"  Win Rate: {always.get('win_rate', 0):.0f}%\n\n"
                f"<b>Filtered (GO only):</b>\n"
                f"  {filtered_pnl_emoji} P&L: {filtered_pnl:+.0f}\n"
                f"  Trades: {filtered.get('trade_count', 0)}\n"
                f"  Win Rate: {filtered.get('win_rate', 0):.0f}%\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Filter Edge:</b> {edge_emoji} {edge:+.0f}\n"
            )

            if always.get('trade_count', 0) > 0 and filtered.get('trade_count', 0) > 0:
                trades_saved = always['trade_count'] - filtered['trade_count']
                text += f"<b>Trades Avoided:</b> {trades_saved}\n"

            # Inline keyboard
            keyboard = {
                'inline_keyboard': [
                    [
                        {'text': ' Refresh', 'callback_data': 'refresh_portfolio'},
                        {'text': ' History', 'callback_data': 'show_history'}
                    ],
                    [
                        {'text': ' Analytics', 'callback_data': 'show_analytics'}
                    ]
                ]
            }

            self.send_message(chat_id, text, reply_markup=keyboard)
            return text

        except Exception as e:
            self.logger.exception(f"Error in /portfolio: {e}")
            error_text = f"Failed to load portfolio: {str(e)}"
            self.send_message(chat_id, error_text)
            return error_text

    def _cmd_history(self, chat_id: str, user: Dict, args: list) -> str:
        """Handle /history command - show recent trades."""
        try:
            # Parse argument for number of trades
            n = 5
            if args:
                try:
                    n = min(int(args[0]), 20)  # Max 20
                except ValueError:
                    pass

            history = self._get_trade_history(n)

            if history.get('error'):
                text = f"Error loading history: {history['error']}"
                self.send_message(chat_id, text)
                return text

            trades = history.get('trades', [])

            if not trades:
                text = "No trade history yet."
                self.send_message(chat_id, text)
                return text

            text = (
                f" <b>RECENT TRADES</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            )

            for trade in trades:
                pnl = trade.get('pnl', 0)
                pnl_emoji = "" if pnl >= 0 else ""
                portfolio_type = trade.get('portfolio', 'unknown')
                portfolio_label = "A" if portfolio_type == 'always_trade' else "F"

                text += (
                    f"[{portfolio_label}] {trade.get('date', 'N/A')}\n"
                    f"     {pnl_emoji} {pnl:+.0f}  |  STOXX: {trade.get('stoxx_close', 'N/A')}\n\n"
                )

            text += "<i>A = Always Trade, F = Filtered</i>"

            self.send_message(chat_id, text)
            return text

        except Exception as e:
            self.logger.exception(f"Error in /history: {e}")
            error_text = f"Failed to load history: {str(e)}"
            self.send_message(chat_id, error_text)
            return error_text

    def _cmd_analytics(self, chat_id: str, user: Dict, args: list) -> str:
        """Handle /analytics command - show performance metrics."""
        try:
            analytics = self._get_analytics()

            if analytics.get('error'):
                text = f"Error calculating analytics: {analytics['error']}"
                self.send_message(chat_id, text)
                return text

            always = analytics.get('always_trade', {})
            filtered = analytics.get('filtered', {})

            text = (
                f" <b>PERFORMANCE ANALYTICS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"<b>Always Trade:</b>\n"
                f"  Total P&L: {always.get('total_pnl', 0):+.0f}\n"
                f"  Win Rate: {always.get('win_rate', 0):.1f}%\n"
                f"  Avg Win: {always.get('avg_win', 0):+.0f}\n"
                f"  Avg Loss: {always.get('avg_loss', 0):.0f}\n"
                f"  Profit Factor: {always.get('profit_factor', 0):.2f}\n\n"
                f"<b>Filtered (GO only):</b>\n"
                f"  Total P&L: {filtered.get('total_pnl', 0):+.0f}\n"
                f"  Win Rate: {filtered.get('win_rate', 0):.1f}%\n"
                f"  Avg Win: {filtered.get('avg_win', 0):+.0f}\n"
                f"  Avg Loss: {filtered.get('avg_loss', 0):.0f}\n"
                f"  Profit Factor: {filtered.get('profit_factor', 0):.2f}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Filter Effectiveness:</b>\n"
                f"  Edge: {analytics.get('filter_edge', 0):+.0f}\n"
                f"  Edge per Trade: {analytics.get('edge_per_trade', 0):+.2f}\n"
            )

            self.send_message(chat_id, text)
            return text

        except Exception as e:
            self.logger.exception(f"Error in /analytics: {e}")
            error_text = f"Failed to calculate analytics: {str(e)}"
            self.send_message(chat_id, error_text)
            return error_text

    def _cmd_alerts(self, chat_id: str, user: Dict, args: list) -> str:
        """Handle /alerts command - toggle real-time alerts."""
        user_id = str(user.get('id'))

        if not args:
            # Show current status
            enabled = self.user_alert_settings.get(user_id, True)
            status = "ON ✓" if enabled else "OFF"
            text = (
                f"🔔 <b>Alert Settings</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"Alerts are currently: <b>{status}</b>\n\n"
                f"Use /alerts on or /alerts off to change."
            )
            self.send_message(chat_id, text)
            return text

        action = args[0].lower()
        if action == 'on':
            self.user_alert_settings[user_id] = True
            text = "🔔 Alerts <b>enabled</b>\n\nYou will receive market alerts."
            self.send_message(chat_id, text)
            return text
        elif action == 'off':
            self.user_alert_settings[user_id] = False
            text = "🔕 Alerts <b>disabled</b>\n\nYou will not receive market alerts."
            self.send_message(chat_id, text)
            return text
        else:
            text = "Usage: /alerts [on|off]"
            self.send_message(chat_id, text)
            return text

    def _cmd_backtest(self, chat_id: str, user: Dict, args: list) -> str:
        """Handle /backtest command - run historical backtest."""
        if not args:
            text = (
                "📊 <b>Backtest Command</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Usage: /backtest [days]\n"
                "Example: /backtest 30\n\n"
                "Runs strategy backtest for last N days.\n"
                "Maximum: 365 days"
            )
            self.send_message(chat_id, text)
            return text

        try:
            days = int(args[0])
            if days < 1:
                text = "Days must be at least 1"
                self.send_message(chat_id, text)
                return text
            if days > 365:
                text = "Maximum 365 days allowed"
                self.send_message(chat_id, text)
                return text

            # Send "running" message
            self.send_message(chat_id, f"⏳ Running backtest for {days} days...")

            from datetime import datetime, timedelta
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            from backtest import run_backtest
            results = run_backtest(start_date, end_date, verbose=False)

            # Analyze results
            trades = [r for r in results if r.get('traded')]
            if not trades:
                text = f"📊 <b>Backtest Results</b>\n\nNo trades found in the last {days} days."
                self.send_message(chat_id, text)
                return text

            wins = [r for r in trades if r.get('pnl', 0) > 0]
            losses = [r for r in trades if r.get('pnl', 0) < 0]
            total_pnl = sum(r.get('pnl', 0) for r in trades)
            win_rate = (len(wins) / len(trades) * 100) if trades else 0

            text = (
                f"📊 <b>Backtest Results</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"<b>Period:</b> {start_date} to {end_date}\n"
                f"<b>Trades:</b> {len(trades)}\n"
                f"<b>Wins:</b> {len(wins)} ({win_rate:.0f}%)\n"
                f"<b>Losses:</b> {len(losses)}\n\n"
                f"<b>Total P&L:</b> €{total_pnl:,.0f}\n"
                f"<b>Avg P&L:</b> €{total_pnl/len(trades):.0f}/trade"
            )

            self.send_message(chat_id, text)
            return text

        except ValueError:
            text = "Invalid number of days. Use: /backtest 30"
            self.send_message(chat_id, text)
            return text
        except Exception as e:
            self.logger.exception(f"Error in /backtest: {e}")
            error_text = f"Backtest error: {str(e)}"
            self.send_message(chat_id, error_text)
            return error_text

    # ========== Data Fetching ==========

    def _get_market_status(self) -> Dict[str, Any]:
        """Get current market status."""
        try:
            from monitor import get_monitor
            from trade_filter import get_market_data, calculate_intraday_change

            # Try to get from monitor first
            monitor = get_monitor()
            if monitor and monitor.current_state:
                state = monitor.current_state
                return {
                    'trade_state': state.trade_state.value,
                    'stoxx_price': state.stoxx_price,
                    'stoxx_open': state.stoxx_open,
                    'intraday_change': state.intraday_change,
                    'vix': state.vix,
                    'reasons': state.reasons
                }

            # Otherwise fetch fresh data
            data = get_market_data(include_history=False)
            intraday = calculate_intraday_change(data['stoxx_current'], data['stoxx_open'])

            # Determine state
            intraday_max = self.config.get('rules', {}).get('intraday_change_max', 1.0)
            trade_state = 'GO' if abs(intraday) <= intraday_max else 'NO_GO'

            reasons = []
            if abs(intraday) > intraday_max:
                direction = "up" if intraday > 0 else "down"
                reasons.append(f"Trend too strong ({intraday:+.2f}% {direction})")

            return {
                'trade_state': trade_state,
                'stoxx_price': data['stoxx_current'],
                'stoxx_open': data['stoxx_open'],
                'intraday_change': intraday,
                'vix': data.get('vix'),
                'reasons': reasons
            }

        except Exception as e:
            return {'error': str(e)}

    def _get_portfolio_summary(self) -> Dict[str, Any]:
        """Get portfolio summary."""
        try:
            from portfolio import load_portfolio, get_portfolio_summary

            data = load_portfolio()
            summary = get_portfolio_summary(data)

            return summary

        except Exception as e:
            return {'error': str(e)}

    def _get_trade_history(self, n: int = 5) -> Dict[str, Any]:
        """Get recent trade history."""
        try:
            from portfolio import load_portfolio

            data = load_portfolio()
            portfolios = data.get('portfolios', {})

            # Combine history from both portfolios
            trades = []

            for name in ['always_trade', 'filtered']:
                history = portfolios.get(name, {}).get('history', [])
                for trade in history:
                    trades.append({
                        'portfolio': name,
                        'date': trade.get('date'),
                        'stoxx_close': trade.get('stoxx_close'),
                        'pnl': trade.get('pnl', 0),
                        'outcome': trade.get('outcome')
                    })

            # Sort by date and get most recent
            trades.sort(key=lambda x: x.get('date', ''), reverse=True)

            return {'trades': trades[:n]}

        except Exception as e:
            return {'error': str(e)}

    def _get_analytics(self) -> Dict[str, Any]:
        """Get performance analytics."""
        try:
            from portfolio import load_portfolio

            data = load_portfolio()
            portfolios = data.get('portfolios', {})

            result = {}

            for name in ['always_trade', 'filtered']:
                portfolio = portfolios.get(name, {})
                history = portfolio.get('history', [])

                total_pnl = portfolio.get('total_pnl', 0)
                trade_count = portfolio.get('trade_count', 0)
                win_count = portfolio.get('win_count', 0)

                # Calculate averages
                wins = [t['pnl'] for t in history if t.get('pnl', 0) > 0]
                losses = [t['pnl'] for t in history if t.get('pnl', 0) <= 0]

                avg_win = sum(wins) / len(wins) if wins else 0
                avg_loss = sum(losses) / len(losses) if losses else 0

                # Profit factor
                total_wins = sum(wins) if wins else 0
                total_losses = abs(sum(losses)) if losses else 0
                profit_factor = total_wins / total_losses if total_losses > 0 else float('inf') if total_wins > 0 else 0

                result[name] = {
                    'total_pnl': total_pnl,
                    'trade_count': trade_count,
                    'win_count': win_count,
                    'win_rate': (win_count / trade_count * 100) if trade_count > 0 else 0,
                    'avg_win': avg_win,
                    'avg_loss': avg_loss,
                    'profit_factor': profit_factor
                }

            # Calculate filter edge
            always_pnl = result.get('always_trade', {}).get('total_pnl', 0)
            filtered_pnl = result.get('filtered', {}).get('total_pnl', 0)
            result['filter_edge'] = filtered_pnl - always_pnl

            # Edge per trade
            filtered_count = result.get('filtered', {}).get('trade_count', 0)
            result['edge_per_trade'] = result['filter_edge'] / filtered_count if filtered_count > 0 else 0

            return result

        except Exception as e:
            return {'error': str(e)}


# Flask app for webhook
app = Flask(__name__)
_bot_instance: Optional[TelegramBot] = None


def get_bot() -> Optional[TelegramBot]:
    """Get global bot instance."""
    return _bot_instance


def set_bot(bot: TelegramBot):
    """Set global bot instance."""
    global _bot_instance
    _bot_instance = bot


@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """Handle incoming Telegram webhook updates."""
    bot = get_bot()
    if not bot:
        return jsonify({'error': 'Bot not initialized'}), 503

    try:
        update = request.get_json()
        if not update:
            return jsonify({'error': 'No update data'}), 400

        bot.handle_update(update)
        return jsonify({'ok': True})

    except Exception as e:
        get_logger().exception(f"Webhook error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/telegram/status', methods=['GET'])
def telegram_status():
    """Get bot status."""
    bot = get_bot()
    return jsonify({
        'configured': bot.is_configured() if bot else False,
        'enabled': bot.enabled if bot else False,
        'whitelist_count': len(bot.whitelist) if bot else 0
    })


def setup_webhook(bot_token: str, webhook_url: str) -> bool:
    """
    Set up Telegram webhook.

    Args:
        bot_token: Telegram bot token
        webhook_url: Public URL for webhook (must be HTTPS)

    Returns:
        True if successful
    """
    client = TelegramClient(bot_token, get_logger())
    return client.set_webhook(webhook_url)


def delete_webhook(bot_token: str) -> bool:
    """Delete Telegram webhook (for polling mode)."""
    client = TelegramClient(bot_token)
    return client.delete_webhook()


def run_polling(config: Dict[str, Any]):
    """
    Run bot in polling mode (for development/testing).

    Args:
        config: Application configuration
    """
    bot = TelegramBot(config)
    set_bot(bot)

    if not bot.is_configured():
        print("Bot not configured. Set telegram.enabled=true and bot_token in config.")
        return

    # Delete any existing webhook
    bot._client.delete_webhook()

    print("Starting bot in polling mode...")
    get_logger().info("Starting Telegram bot in polling mode")

    offset = 0

    while True:
        try:
            updates = bot._client.get_updates(offset=offset, timeout=30)

            for update in updates:
                offset = update['update_id'] + 1
                bot.handle_update(update)

        except KeyboardInterrupt:
            print("\nBot stopped.")
            break
        except Exception as e:
            get_logger().error(f"Polling error: {e}")
            time.sleep(5)


def main():
    """Main entry point for standalone bot."""
    import argparse
    from trade_filter import load_config

    parser = argparse.ArgumentParser(description='STOXX50 Telegram Bot')
    parser.add_argument('--polling', action='store_true',
                        help='Run in polling mode (no webhook)')
    parser.add_argument('--webhook-url', type=str,
                        help='Set webhook URL')
    parser.add_argument('--delete-webhook', action='store_true',
                        help='Delete existing webhook')

    args = parser.parse_args()
    config = load_config()

    bot_token = config.get('telegram', {}).get('bot_token', '')

    if args.delete_webhook:
        if delete_webhook(bot_token):
            print("Webhook deleted.")
        else:
            print("Failed to delete webhook.")
        return

    if args.webhook_url:
        if setup_webhook(bot_token, args.webhook_url):
            print(f"Webhook set to {args.webhook_url}")
        else:
            print("Failed to set webhook.")
        return

    if args.polling:
        run_polling(config)
    else:
        print("Use --polling for development or --webhook-url to set up webhook")
        print("For production, integrate with dashboard.py")


if __name__ == '__main__':
    main()
