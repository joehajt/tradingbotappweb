"""
Telegram Integration Module

Provides Telegram functionality for the trading bot, including:
- Message forwarding from monitored channels
- Trading signal detection and parsing
- Session management with persistent sessions
"""

from .forwarder import TelegramForwarder, SESSIONS_DIR, TELETHON_AVAILABLE

__all__ = ['TelegramForwarder', 'SESSIONS_DIR', 'TELETHON_AVAILABLE']
