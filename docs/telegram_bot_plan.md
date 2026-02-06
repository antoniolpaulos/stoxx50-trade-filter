# Telegram Bot Command Feature Plan

## Overview
Add interactive Telegram bot commands to query portfolio status, market data, and trade history via text messages.

## Architecture

```
User → Telegram → Webhook → Flask Endpoint → Command Router → Data Modules
                                                              ↓
                                                Portfolio, Monitor, Dashboard APIs
                                                              ↓
                                                Response → Telegram
```

## Required Components

### 1. Telegram Webhook Handler
- **File:** `telegram_bot.py`
- Endpoint: `/telegram/webhook`
- Validates Telegram signatures
- Parses incoming messages/commands

### 2. Command Router
- Routes commands to appropriate handlers
- Supports:
  - `/status` - Current market conditions
  - `/portfolio` - Shadow portfolio summary
  - `/history` - Recent trades
  - `/analytics` - P&L, Sharpe, drawdown
  - `/alerts` - Active monitoring alerts
  - `/help` - Available commands

### 3. Data Module APIs (extensions)
- `portfolio.py` - Add JSON export for bot
- `monitor.py` - Add current state API
- `trade_filter.py` - Add quick status endpoint

### 4. Dashboard Integration
- New API endpoint: `/api/telegram/status`
- Returns bot-friendly compact data

## Database/State
- No new database needed
- Reuse existing `portfolio.json`
- In-memory monitoring state

## Security
- Telegram bot token validation
- Optionally: whitelisted user IDs
- Rate limiting per user

## Example Commands

```
User: /portfolio
Bot:
📊 SHADOW PORTFOLIO

Always Trade:
  Trades: 12 | P&L: +€450 | Win Rate: 67%

Filtered (GO signals only):
  Trades: 8  | P&L: +€320 | Win Rate: 75%

Filter Edge: +€16.25/trade avg

User: /status
Bot:
🟢 STOXX50 STATUS

Last Check: 10:05 CET
VIX: 18.2 (< 22 ✓)
Intraday: +0.32% (|0.32%| < 1% ✓)
Events: None
─────────────────
VERDICT: ✅ GO - Trade today
```

## Files to Create/Modify

| File | Action |
|------|--------|
| `telegram_bot.py` | Create - Bot webhook handler |
| `dashboard.py` | Modify - Add bot-friendly API |
| `portfolio.py` | Modify - Add summary API |
| `trade_filter.py` | Modify - Add quick status endpoint |
| `config.yaml.example` | Modify - Add telegram webhook config |

## Implementation Steps

### Phase 1: Foundation
1. Create `telegram_bot.py` with webhook endpoint
2. Add command router skeleton
3. Configure Telegram webhook URL

### Phase 2: Data APIs
4. Extend `portfolio.py` with compact summary
5. Extend `monitor.py` with current state API
6. Add `/api/status/brief` endpoint

### Phase 3: Commands
7. Implement `/status` command
8. Implement `/portfolio` command
9. Implement `/history` command
10. Implement `/help` command

### Phase 4: Polish
11. Add rate limiting
12. Add user whitelisting
13. Add inline keyboard shortcuts
14. Add rich formatting (charts, tables)

## Estimated Effort
- Phase 1-3: 2-3 days
- Phase 4: 1-2 days
- **Total: ~1 week**

## Dependencies
- `python-telegram-bot>=20.0` (or `aiogram` for async)
- Existing: Flask, requests, yaml

## Cron Integration
- Keep existing `0 10 * * 1-5` for daily GO/NO-GO
- New webhook handles on-demand queries
- No additional cron needed

## Future Enhancements
- `/alert on|off` - Toggle monitoring alerts
- `/notify on|off` - Toggle daily notifications
- `/config` - View/edit settings
- `/backtest [days]` - Quick backtest results
- Natural language: "how's the portfolio?"
