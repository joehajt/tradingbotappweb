# Telegram Integration Module

This module contains the extracted `TelegramForwarder` class from `app.py`, providing complete Telegram message forwarding and monitoring functionality.

## Files

- **forwarder.py** - Contains the complete `TelegramForwarder` class (802 lines)
- **__init__.py** - Package initialization and exports

## Overview

The `TelegramForwarder` class provides:

- **Persistent Session Management**: Maintains Telegram sessions across restarts in the `telegram_sessions/` directory
- **Multi-Channel Monitoring**: Monitor multiple Telegram channels and groups simultaneously
- **Trading Signal Detection**: Automatically detects and parses trading signals from channel messages
- **Message Forwarding**: Forwards detected signals to a target Telegram chat
- **Auto-Trading Integration**: Optional automatic execution of detected trading signals via Bybit API
- **Async/Await Support**: Efficient async implementation using Telethon

## Key Methods

- `__init__(bot)` - Initialize forwarder with bot instance
- `load_forwarder_config()` - Load configuration from config.ini
- `save_forwarder_config()` - Save configuration to config.ini
- `initialize_telethon_client()` - Set up Telethon client with persistent sessions
- `get_channels_list()` - Fetch available channels from Telegram account
- `start_forwarder()` - Begin monitoring channels for messages
- `stop_forwarder()` - Stop the monitoring process
- `process_message()` - Parse and process individual messages
- `send_to_target_chat()` - Forward messages to target chat ID
- `get_session_path()` - Generate persistent session file path

## Dependencies

- **telethon** - Telegram client library
- **flask-socketio** - WebSocket communication
- **asyncio** - Async/await support
- **threading** - Multi-threaded monitoring

## Configuration

The class reads/writes configuration from `config.ini` under the `[Forwarder]` section:

```ini
[Forwarder]
api_id = YOUR_API_ID
api_hash = YOUR_API_HASH
phone_number = +1234567890
target_chat_id = CHAT_ID
forward_all_messages = False
monitored_channels = [{"id": "123456", "name": "Channel1"}]
```

## Session Management

Sessions are stored in the `telegram_sessions/` directory as:
- `session_[phone_digits].session` - Main session
- `session_[phone_digits]_worker.session` - Worker session for polling

This allows the bot to reuse authenticated sessions without requiring re-authentication.

## Usage Example

```python
from telegram_integration.forwarder import TelegramForwarder

# Initialize with bot instance
forwarder = TelegramForwarder(bot)

# Fetch available channels
channels = forwarder.get_channels_list()

# Update monitored channels
forwarder.monitored_channels = [{"id": "123", "name": "Trading Channel"}]
forwarder.save_forwarder_config()

# Start monitoring
forwarder.start_forwarder()

# Stop monitoring when done
forwarder.stop_forwarder()
```

## Global Dependencies

The module expects these global objects to be set before use:

- `ws_logger` - WebSocket logger instance
- `socketio` - Flask-SocketIO instance
- `auth_queue` - Queue for authentication callbacks (imported from main app)

These should be configured in your main app.py file.

## Notes

- The module preserves all original code exactly as extracted from app.py
- All 50+ methods and properties are included
- Authentication callbacks support both phone code and 2FA password verification
- Message polling runs every 3 seconds
- Session files are automatically cleaned up on connection errors
