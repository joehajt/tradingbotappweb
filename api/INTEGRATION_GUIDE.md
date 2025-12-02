# API Integration Guide

## Quick Start

This guide explains how to integrate the extracted Flask routes and Socket.IO handlers back into your main `app.py`.

## Structure

```
api/
├── __init__.py                 # Package initialization and exports
├── routes.py                   # 32 Flask @app.route() endpoints
├── socketio_handlers.py        # 3 Socket.IO @socketio.on() handlers
└── INTEGRATION_GUIDE.md        # This file
```

## Step-by-Step Integration

### Step 1: Import the Registration Functions

Add these imports to your main `app.py`:

```python
from api import register_routes, register_socketio_handlers
```

### Step 2: Register Routes

After creating your Flask app instance, register all routes:

```python
# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# Initialize CORS
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Initialize SocketIO
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
    transports=['websocket', 'polling']
)

# REGISTER ALL ROUTES
register_routes(app, bot, console_manager, ws_logger, logger, auth_queue)
```

### Step 3: Register Socket.IO Handlers

Register all Socket.IO handlers after initializing socketio:

```python
# REGISTER ALL SOCKET.IO HANDLERS
register_socketio_handlers(socketio, bot, ws_logger, logger)
```

### Step 4: Remove Original Route Definitions

In your `app.py`, remove or comment out:
- All `@app.route()` decorated functions (lines 3754-4571 in original)
- All `@socketio.on()` decorated functions (lines 3715-3750 in original)

### Complete Integration Example

```python
import os
import logging
from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS

# ... other imports ...

from api import register_routes, register_socketio_handlers

# Initialize logging
logging.basicConfig(...)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# Initialize CORS
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Initialize SocketIO
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
    transports=['websocket', 'polling']
)

# Global instances
bot = TelegramTradingBot()
console_manager = ConsoleManager(bot)
ws_logger = WebSocketLogger(socketio, message_queue)

# ====== REGISTER API MODULES ======
register_routes(app, bot, console_manager, ws_logger, logger, auth_queue)
register_socketio_handlers(socketio, bot, ws_logger, logger)

# Error handlers (keep from original)
@app.errorhandler(404)
def not_found(error):
    # ... error handler code ...
    pass

# Background tasks (keep from original)
def process_message_queue():
    # ... background task code ...
    pass

# Main execution
if __name__ == '__main__':
    # ... initialization code ...
    socketio.run(app, debug=False, host='0.0.0.0', port=5001)
```

## What Gets Registered?

### Routes (32 Endpoints)

**Core** (1)
- `/` - Main page

**API Endpoints** (31)
- `/api/health`
- `/api/config`
- `/api/test-connection`
- `/api/subaccounts`
- `/api/profiles`
- `/api/profiles/<name>/load`
- `/api/profiles/<name>`
- `/api/trading-settings`
- `/api/balance`
- `/api/risk-stats`
- `/api/analyze-signal`
- `/api/execute-trade`
- `/api/telegram/start`
- `/api/telegram/stop`
- `/api/telegram/chat-id`
- `/api/forwarder/config`
- `/api/forwarder/channels`
- `/api/forwarder/monitor`
- `/api/forwarder/monitor/<int:index>`
- `/api/forwarder/monitored`
- `/api/forwarder/start`
- `/api/forwarder/stop`
- `/api/console/command`
- `/api/positions`
- `/api/positions/monitoring/start`
- `/api/positions/monitoring/stop`
- `/api/positions/breakeven`
- `/api/positions/<symbol>`
- `/api/logs`
- `/api/logs` (DELETE)
- `/api/auth/submit`

### Socket.IO Handlers (3 Events)

- `connect` - New client connection
- `disconnect` - Client disconnection
- `request_status` - Status request from client

## Required Global Objects

The registration functions require these objects to be available in `app.py`:

```python
# Required for register_routes()
bot                    # TelegramTradingBot instance
console_manager        # ConsoleManager instance
ws_logger             # WebSocketLogger instance
logger                # Python logging instance
auth_queue            # Queue for authentication

# Required for register_socketio_handlers()
bot                   # TelegramTradingBot instance
ws_logger             # WebSocketLogger instance
logger                # Python logging instance
socketio              # SocketIO instance
```

## Advantages of This Approach

1. **Modular Code**: Cleaner separation of concerns
2. **Easier Testing**: Can test routes independently
3. **Better Maintainability**: Routes are in dedicated file
4. **Easier Debugging**: Socket.IO handlers are separate
5. **Scalability**: Can easily add more handlers
6. **Reusability**: Can import in other projects
7. **Code Organization**: Main app.py is cleaner

## Maintaining Original Functionality

All original functionality is preserved:
- Same error handling
- Same response formats
- Same status codes
- Same logging behavior
- Same Socket.IO emissions
- Same async/await support

## Common Issues & Solutions

### Issue: Routes not registering
**Solution**: Make sure you call `register_routes()` AFTER creating the Flask app and BEFORE running it.

### Issue: Socket.IO handlers not working
**Solution**: Ensure you call `register_socketio_handlers()` AFTER creating the SocketIO instance.

### Issue: Missing global objects
**Solution**: Verify all required objects (bot, logger, etc.) are created before calling registration functions.

### Issue: Port already in use
**Solution**: Change the port in the `socketio.run()` call (default is 5001).

## Testing the Integration

After integration, test the following:

```bash
# Test health endpoint
curl http://localhost:5001/api/health

# Test configuration endpoint
curl http://localhost:5001/api/config

# Check console for Socket.IO client connections
# Should see "Socket.IO client connected" messages
```

## Need Help?

Refer to:
- `API_EXTRACTION_SUMMARY.md` - Full overview of extracted code
- `routes.py` - Implementation details of Flask routes
- `socketio_handlers.py` - Implementation details of Socket.IO handlers

## Reverting Changes

If you need to revert to the original structure:
1. Remove the import statements for the api module
2. Restore the original route definitions from `app.py`
3. Restore the original Socket.IO handler definitions from `app.py`
4. Remove the `api/` directory if no longer needed
