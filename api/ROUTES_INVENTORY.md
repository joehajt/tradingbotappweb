# Complete Routes and Handlers Inventory

## Flask Routes Summary

**Total Routes: 32** (33 decorators - due to `/api/logs` having both GET and DELETE)

### 1. Main Page
| Method | Route | Function | Purpose |
|--------|-------|----------|---------|
| GET | `/` | `index()` | Render main application page from templates/index.html |

### 2. Health & Configuration (3 routes)
| Method | Route | Function | Purpose |
|--------|-------|----------|---------|
| GET | `/api/health` | `health_check()` | API health status check |
| GET/POST | `/api/config` | `handle_config()` | Get or update bot configuration |
| POST | `/api/test-connection` | `test_connection()` | Test Bybit API connection |

### 3. Trading Profiles (4 routes)
| Method | Route | Function | Purpose |
|--------|-------|----------|---------|
| GET/POST | `/api/profiles` | `handle_profiles()` | Get all profiles or save new profile |
| POST | `/api/profiles/<name>/load` | `load_profile(name)` | Load a specific trading profile |
| DELETE | `/api/profiles/<name>` | `delete_profile(name)` | Delete a trading profile |
| GET | `/api/subaccounts` | `get_subaccounts()` | Get list of Bybit subaccounts |

### 4. Trading Settings & Execution (5 routes)
| Method | Route | Function | Purpose |
|--------|-------|----------|---------|
| POST | `/api/trading-settings` | `update_trading_settings()` | Update leverage, amount, risk settings, etc. |
| GET | `/api/balance` | `get_balance()` | Get wallet balance from Bybit |
| GET | `/api/risk-stats` | `get_risk_stats()` | Get risk management statistics |
| POST | `/api/analyze-signal` | `analyze_signal()` | Analyze a trading signal |
| POST | `/api/execute-trade` | `execute_trade()` | Execute a trade from signal |

### 5. Telegram Bot Management (3 routes)
| Method | Route | Function | Purpose |
|--------|-------|----------|---------|
| POST | `/api/telegram/start` | `start_telegram()` | Start Telegram bot |
| POST | `/api/telegram/stop` | `stop_telegram()` | Stop Telegram bot |
| GET | `/api/telegram/chat-id` | `get_chat_id()` | Get Telegram chat ID |

### 6. Message Forwarder (Telethon) (7 routes)
| Method | Route | Function | Purpose |
|--------|-------|----------|---------|
| POST | `/api/forwarder/config` | `update_forwarder_config()` | Update Telethon API configuration |
| GET | `/api/forwarder/channels` | `get_forwarder_channels()` | Get available Telegram channels |
| POST | `/api/forwarder/monitor` | `add_channel_to_monitoring()` | Add channel to monitoring list |
| DELETE | `/api/forwarder/monitor/<int:index>` | `remove_channel_from_monitoring(index)` | Remove monitored channel |
| GET | `/api/forwarder/monitored` | `get_monitored_channels()` | Get currently monitored channels |
| POST | `/api/forwarder/start` | `start_forwarder()` | Start message forwarder |
| POST | `/api/forwarder/stop` | `stop_forwarder()` | Stop message forwarder |

### 7. Position Management (6 routes)
| Method | Route | Function | Purpose |
|--------|-------|----------|---------|
| GET | `/api/positions` | `get_positions()` | Get active trading positions |
| POST | `/api/positions/monitoring/start` | `start_position_monitoring()` | Start position monitoring |
| POST | `/api/positions/monitoring/stop` | `stop_position_monitoring()` | Stop position monitoring |
| POST | `/api/positions/breakeven` | `set_breakeven()` | Set position to breakeven |
| DELETE | `/api/positions/<symbol>` | `remove_position(symbol)` | Remove position from monitoring |
| POST | `/api/console/command` | `execute_console_command()` | Execute a console command |

### 8. Logging (2 routes)
| Method | Route | Function | Purpose |
|--------|-------|----------|---------|
| GET | `/api/logs` | `get_logs()` | Get application logs (last 500 lines) |
| DELETE | `/api/logs` | `clear_logs()` | Clear application logs |

### 9. Authentication (1 route)
| Method | Route | Function | Purpose |
|--------|-------|----------|---------|
| POST | `/api/auth/submit` | `submit_auth()` | Submit authentication data (for 2FA, etc.) |

---

## Socket.IO Handlers Summary

**Total Handlers: 3**

### Real-time Communication Events

| Event | Handler | Purpose | Direction |
|-------|---------|---------|-----------|
| `connect` | `handle_connect()` | Handle new WebSocket client connection | Client → Server |
| `disconnect` | `handle_disconnect()` | Handle client disconnection cleanup | Client → Server |
| `request_status` | `handle_status_request()` | Request current system status | Client → Server |

### Emitted Events (Server → Client)

| Event | Sent By | Data | Purpose |
|-------|---------|------|---------|
| `connected` | `handle_connect()` | `{'message': 'Connected to Socket.IO'}` | Acknowledge connection |
| `status_update` | `handle_status_request()` | `{'telegram_bot': bool, 'forwarder': bool, 'monitoring': bool, ...}` | Send current status |
| `console_message` | `ws_logger.log()` | `{'message': str, 'level': str, 'timestamp': str}` | Real-time console output |
| `message` | `process_message_queue()` | Queue message | General messages |
| `error` | `handle_status_request()` | `{'message': 'Failed to get status'}` | Error notification |
| `forwarder_channels_update` | Routes (not shown here) | Channel list | Update monitored channels |

---

## Response Format Standards

### Success Response (200 OK)
```json
{
  "success": true,
  "message": "Operation completed",
  "data": {}
}
```

### Error Response (400, 404, 500)
```json
{
  "success": false,
  "error": "Error description"
}
```

### Status Codes Used
- `200 OK` - Successful operation
- `400 Bad Request` - Invalid input or configuration
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

---

## Parameter Types

### Common Request Parameters
- `name` (string) - Profile name or identifier
- `symbol` (string) - Trading pair symbol (e.g., "BTCUSDT")
- `index` (integer) - List index for removal operations
- `channel_id` (string/int) - Telegram channel identifier
- `command` (string) - Console command to execute

### Common Response Fields
- `success` (boolean) - Operation success status
- `message` (string) - Human-readable message
- `error` (string) - Error description if failed
- `data` (object) - Response payload
- `timestamp` (string) - ISO format timestamp
- `status` (string) - Current operational status

---

## File Locations

- **Routes Module**: `C:\Users\rxosk\Desktop\tradingbotfinalversion22\api\routes.py` (845 lines)
- **Handlers Module**: `C:\Users\rxosk\Desktop\tradingbotfinalversion22\api\socketio_handlers.py` (63 lines)
- **Package Init**: `C:\Users\rxosk\Desktop\tradingbotfinalversion22\api\__init__.py` (14 lines)

---

## Integration Entry Points

### Registration Functions
```python
from api import register_routes, register_socketio_handlers

# Register Flask routes
register_routes(app, bot, console_manager, ws_logger, logger, auth_queue)

# Register Socket.IO handlers
register_socketio_handlers(socketio, bot, ws_logger, logger)
```

---

## Dependency Graph

```
routes.py depends on:
├── Flask (render_template, request, jsonify, etc.)
├── asyncio (for console commands)
├── datetime
└── bot, console_manager, ws_logger, logger, auth_queue (parameters)

socketio_handlers.py depends on:
├── flask_socketio (emit decorator)
└── bot, ws_logger, logger (parameters)

Both depend on:
└── Dependencies injected as parameters (loose coupling)
```

---

## Notes

1. **No Breaking Changes**: All code extracted verbatim from original
2. **Loose Coupling**: All dependencies passed as parameters
3. **Easy Testing**: Can mock/test individual routes and handlers
4. **Backward Compatible**: Can be imported and used in existing projects
5. **Comprehensive**: 100% of Flask and Socket.IO code extracted
6. **Well Documented**: Full docstrings in each module
