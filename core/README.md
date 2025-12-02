# Core Trading Bot Module

This module contains the complete `TelegramTradingBot` class extracted from the main application, packaged as a standalone, reusable module.

## Contents

### Main Classes

1. **TelegramTradingBot** (Lines 324-1464 of bot.py)
   - ENHANCED Trading Bot with improved Bybit connection and risk management
   - Handles signal parsing, trade execution, and position management
   - Integrated with Telegram for signal reception
   - Support for both demo (testnet) and live (mainnet) trading

2. **ProfileManager** (Lines 72-108)
   - Manages trading profiles (configurations)
   - Save and load profile data to JSON
   - Support for multiple configuration profiles

3. **EnhancedRiskManager** (Lines 111-269)
   - Advanced risk management with margin level tracking
   - Daily and weekly loss limits
   - Consecutive loss tracking with cooling periods
   - Margin level safety checks to prevent liquidation

4. **PositionManager** (Lines 272-294)
   - Position monitoring and management
   - Automatic TP/SL handling
   - Position tracking thread

5. **TelegramForwarder** (Lines 297-302)
   - Signal relay via Telegram
   - Forwarding integration

## Key Methods

### TelegramTradingBot

#### Telegram Bot Methods
- `telegram_message_handler()` - Process incoming Telegram messages
- `send_telegram_message()` - Send messages via Telegram
- `start_telegram_bot()` - Start the Telegram bot service
- `stop_telegram_bot()` - Stop the Telegram bot service
- `get_telegram_chat_id()` - Auto-retrieve Chat ID

#### Configuration Methods
- `load_config()` - Load configuration from config.ini
- `save_config()` - Save configuration to file
- `save_current_as_profile()` - Save current config as named profile
- `load_profile()` - Load a named profile

#### Bybit API Methods
- `initialize_bybit_client()` - Connect to Bybit API
- `test_api_keys_simple()` - Validate API keys
- `get_wallet_balance()` - Fetch account balance
- `get_subaccounts()` - Get subaccount list
- `get_symbol_info()` - Get trading pair information

#### Trading Methods
- `parse_trading_signal()` - Parse Telegram message as trading signal
- `analyze_trading_signal()` - Calculate risk/reward ratios
- `execute_trade()` - Execute market order based on signal
- `format_quantity()` - Format quantity to symbol requirements
- `get_position_idx()` - Get position index for hedge/one-way mode

## Configuration

The bot uses a `config.ini` file with the following sections:

```ini
[Telegram]
token=YOUR_BOT_TOKEN
chat_id=YOUR_CHAT_ID

[Bybit]
api_key=YOUR_API_KEY
api_secret=YOUR_API_SECRET
subaccount=
platform=bybitglobal
position_mode=one_way

[Trading]
default_leverage=10
default_amount=100
use_percentage=False
use_demo_account=True
auto_tp_sl=True
auto_breakeven=True
breakeven_after_target=1
auto_execute_signals=False
max_position_size=1000
risk_percent=2

[RiskManagement]
enabled=True
daily_loss_limit=500
weekly_loss_limit=2000
max_consecutive_losses=3
min_margin_level=1.5

[Forwarder]
api_id=
api_hash=
phone_number=
target_chat_id=
forward_all_messages=False
monitored_channels=[]
```

## Usage

### Basic Initialization

```python
from core import TelegramTradingBot, set_logger, set_socketio

# Set up global logger and socketio if using web interface
set_logger(your_logger_instance)
set_socketio(your_socketio_instance)

# Create bot instance
bot = TelegramTradingBot()

# Initialize Bybit connection
bot.initialize_bybit_client()

# Start Telegram bot
bot.start_telegram_bot()
```

### Execute Trade Manually

```python
# Parse a signal
signal = bot.parse_trading_signal("BTCUSDT LONG Entry: 45000 TP1: 46000 TP2: 47000 SL: 44000")

if signal:
    # Execute trade
    result = bot.execute_trade(signal)
    print(result)
```

### Profile Management

```python
# Save current configuration as profile
bot.save_current_as_profile("conservative")

# Load profile
bot.load_profile("conservative")
```

## Dependencies

Required packages:
- `pybit==5.7.0` - Bybit trading API
- `python-telegram-bot==20.4` - Telegram bot integration
- `requests==2.31.0` - HTTP requests
- `configparser` - Configuration file parsing

Install with:
```bash
pip install -r requirements.txt
```

## Features

- **Signal Parsing**: Automatically recognizes trading signals from Telegram messages
  - Symbol detection (BTCUSDT, ETHUSDT, etc.)
  - Position type (LONG/SHORT)
  - Entry price (single or range)
  - Multiple take profit targets
  - Stop loss level

- **Risk Management**:
  - Daily loss limits
  - Weekly loss limits
  - Consecutive loss tracking
  - Margin level monitoring
  - Cooling periods after max losses

- **Trading Modes**:
  - Demo mode (testnet for testing)
  - Live mode (real trading)
  - One-way or hedge position mode
  - Leverage control
  - Position size limits

- **Auto Features**:
  - Auto TP/SL setup
  - Auto breakeven moves
  - Auto signal execution
  - Auto Chat ID detection

## Trading Signal Format

The bot recognizes signals in the following format:

```
BTCUSDT LONG
Entry: 45000 - 45100
Target1: 46000
Target2: 47000
Target3: 48000
Stop Loss: 44000
```

The parser is flexible and supports various keywords:
- Symbols: `BTCUSDT`, `#BTCUSDT`
- Positions: `LONG`, `SHORT`, `long`, `short`
- Entry: `Entry`, `Zone`, `entry`
- Targets: `Target`, `TP`, `Cel` (with numbers like TP1, TP2)
- Stop Loss: `SL`, `Stop Loss`, `STOP LOSS`

## Error Handling

The bot includes comprehensive error handling:
- API connection failures with helpful error messages
- Balance retrieval with fallback to demo balance
- Invalid symbol/order parameter detection
- Risk management checks before trade execution
- Margin level warnings

## Logging

All operations are logged via the global `ws_logger` instance which can emit to:
- Socket.IO for real-time web updates
- File logging
- Console output

## Notes

- All code is preserved exactly as in the original application
- No modifications or optimizations have been made
- The module is designed to be imported and used independently
- Global logger and socketio instances must be set before using features that require them
- Trading with real API keys should only be done in live mode with proper risk management enabled
