"""
Core module for TelegramTradingBot

This package provides the core trading bot functionality including:
- TelegramTradingBot: Main trading bot class
- ProfileManager: Configuration profile management
- EnhancedRiskManager: Advanced risk management with margin tracking
- PositionManager: Position monitoring and TP/SL management
- TelegramForwarder: Signal relay via Telegram
"""

from .bot import (
    TelegramTradingBot,
    ProfileManager,
    EnhancedRiskManager,
    PositionManager,
    TelegramForwarder,
    set_logger,
    set_socketio
)

__all__ = [
    'TelegramTradingBot',
    'ProfileManager',
    'EnhancedRiskManager',
    'PositionManager',
    'TelegramForwarder',
    'set_logger',
    'set_socketio'
]

__version__ = '1.0.0'
__author__ = 'Trading Bot Team'
