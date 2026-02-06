#!/usr/bin/env python3
"""
Economic Calendar Provider - Fetches high-impact events from financial calendars.

Supports multiple data sources:
- ForexFactory (primary)
- Trading Economics (backup)

Used to detect high-impact EUR events that might affect Iron Condor trades.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, List, Optional

import requests


class CalendarProvider(ABC):
    """Abstract base class for calendar data providers."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    @abstractmethod
    def fetch(self) -> List[Dict[str, Any]]:
        """Fetch calendar events. Returns list of event dicts."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        pass


class ForexFactoryProvider(CalendarProvider):
    """
    ForexFactory calendar API provider.

    Fetches this week's economic events from ForexFactory's JSON API.
    """

    URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    @property
    def name(self) -> str:
        return "ForexFactory"

    def fetch(self) -> List[Dict[str, Any]]:
        """
        Fetch calendar events from ForexFactory.

        Returns:
            List of event dicts with keys: country, title, date, impact
        """
        try:
            response = requests.get(self.URL, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Normalize to standard format
            events = []
            for event in data:
                if not event or not isinstance(event, dict):
                    continue
                events.append({
                    'country': event.get('country', ''),
                    'title': event.get('title', 'Unknown Event'),
                    'date': event.get('date', '')[:10],  # YYYY-MM-DD
                    'time': event.get('date', '')[11:16],  # HH:MM
                    'impact': event.get('impact', 'Low')
                })
            return events

        except requests.exceptions.RequestException as e:
            self.logger.error(f"ForexFactory API error: {e}")
            raise
        except (ValueError, KeyError) as e:
            self.logger.error(f"ForexFactory parse error: {e}")
            raise


class TradingEconomicsProvider(CalendarProvider):
    """
    Trading Economics calendar provider (backup).

    Scrapes embedded JSON from Trading Economics calendar page.
    """

    URL = "https://tradingeconomics.com/calendar"
    USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

    # Eurozone countries to monitor
    EUROZONE_COUNTRIES = [
        'Euro Area', 'Germany', 'France', 'Italy',
        'Spain', 'Netherlands', 'Belgium', 'Austria'
    ]

    @property
    def name(self) -> str:
        return "TradingEconomics"

    def fetch(self) -> List[Dict[str, Any]]:
        """
        Fetch calendar events from Trading Economics.

        Returns:
            List of event dicts normalized to ForexFactory format
        """
        try:
            headers = {'User-Agent': self.USER_AGENT}
            response = requests.get(self.URL, headers=headers, timeout=10)
            response.raise_for_status()

            # Extract embedded JSON
            json_match = re.search(r'var defined = (\[.*?\]);', response.text, re.DOTALL)
            if not json_match:
                self.logger.warning("No embedded JSON found in TradingEconomics page")
                return []

            data = json.loads(json_match.group(1))

            # Normalize to standard format, filter to Eurozone
            events = []
            for item in data:
                country = item.get('Country', '')
                if country not in self.EUROZONE_COUNTRIES:
                    continue

                importance = item.get('Importance', 0)
                events.append({
                    'country': 'EUR',  # Normalize to EUR for Eurozone
                    'title': item.get('Event', ''),
                    'date': item.get('Date', '')[:10],
                    'time': item.get('Date', '')[11:16] if len(item.get('Date', '')) > 10 else '',
                    'impact': 'High' if importance >= 3 else ('Medium' if importance >= 2 else 'Low')
                })
            return events

        except requests.exceptions.RequestException as e:
            self.logger.error(f"TradingEconomics API error: {e}")
            raise
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            self.logger.error(f"TradingEconomics parse error: {e}")
            raise


class EventFilter:
    """Filters and processes calendar events."""

    def __init__(self, watchlist: Optional[List[str]] = None):
        """
        Initialize event filter.

        Args:
            watchlist: List of event keywords to always flag (case-insensitive)
        """
        self.watchlist = [w.upper() for w in (watchlist or [])]

    def is_watched(self, title: str) -> bool:
        """Check if event title matches any watchlist item."""
        title_upper = title.upper()
        return any(watch in title_upper for watch in self.watchlist)

    def filter_events(
        self,
        events: List[Dict[str, Any]],
        target_date: Optional[str] = None,
        country: str = 'EUR'
    ) -> Dict[str, Any]:
        """
        Filter events for high-impact items.

        Args:
            events: List of event dicts from provider
            target_date: Date to filter (YYYY-MM-DD), defaults to today
            country: Country code to filter (default EUR)

        Returns:
            Dict with:
                - high_impact: List of high-impact events for target date
                - all_high_this_week: List of all high-impact events
        """
        target_date = target_date or date.today().strftime('%Y-%m-%d')

        high_impact_today = []
        all_high_this_week = []

        for event in events:
            event_country = event.get('country', '')
            event_impact = event.get('impact', '')
            event_date = event.get('date', '')
            event_title = event.get('title', '')

            # Track all high-impact EUR events this week
            if event_country == country and event_impact == 'High':
                all_high_this_week.append(f"{event_date}: {event_title}")

            # Filter for target date
            if event_country == country and event_date == target_date:
                # Include if high impact OR in watchlist
                if event_impact == 'High' or self.is_watched(event_title):
                    high_impact_today.append({
                        'name': event_title,
                        'time': event.get('time', '') or 'All Day',
                        'impact': event_impact if event_impact == 'High' else 'Watchlist'
                    })

        return {
            'high_impact': high_impact_today,
            'all_high_this_week': all_high_this_week
        }


def check_economic_calendar(config: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Check economic calendars for high-impact EUR events today.

    Uses ForexFactory API as primary, with backup from Trading Economics.
    Also checks against a configurable watchlist for important events.

    Args:
        config: Optional config dict with 'calendar' section containing:
            - always_watch: List of event keywords to flag
            - use_backup_api: Whether to use backup API on failure (default True)

    Returns:
        Dict with:
            - has_high_impact: bool or None if API failed
            - events: List of high-impact event dicts
            - all_eur_high_this_week: List of all high-impact EUR events
            - source: Provider name
            - error: Error message if any
    """
    # Parse config
    watchlist = []
    use_backup = True
    if config and 'calendar' in config:
        watchlist = config['calendar'].get('always_watch', [])
        use_backup = config['calendar'].get('use_backup_api', True)

    # Create filter with watchlist
    event_filter = EventFilter(watchlist)

    # Define providers to try
    providers: List[CalendarProvider] = [ForexFactoryProvider()]
    if use_backup:
        providers.append(TradingEconomicsProvider())

    # Try each provider in order
    last_error = None
    for provider in providers:
        try:
            events = provider.fetch()
            result = event_filter.filter_events(events)

            return {
                'has_high_impact': len(result['high_impact']) > 0,
                'events': result['high_impact'],
                'all_eur_high_this_week': result['all_high_this_week'],
                'source': provider.name,
                'error': None
            }

        except Exception as e:
            last_error = str(e)
            continue

    # All providers failed
    return {
        'has_high_impact': None,
        'events': [],
        'all_eur_high_this_week': [],
        'source': None,
        'error': f"Calendar API failed: {last_error}"
    }
