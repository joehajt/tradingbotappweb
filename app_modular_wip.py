"""
Trading Bot Web Application - Restructured Version
===================================================

Main entry point for the trading bot application with modular architecture.
This file integrates all components from separate modules.

Author: Trading Bot Team
Version: 2.0 (Restructured)
"""

import os
import logging
import configparser
import asyncio
import threading
import urllib3
from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS
import queue

# Wyłącz ostrzeżenia SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===== CONFIGURATION CONSTANTS =====
CONFIG_FILE = "config.ini"
PROFILES_FILE = "trading_profiles.json"
RISK_TRACKING_FILE = "risk_tracking.json"
SESSIONS_DIR = "telegram_sessions"

# ===== LOGGING CONFIGURATION =====
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_trading.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== QUICK SETUP SCRIPT =====
def run_quick_setup():
    """Quick setup script - creates project structure"""
    print("\n🚀 Trading Bot Quick Setup")
    print("=" * 50)

    # Create templates directory
    if not os.path.exists('templates'):
        os.makedirs('templates')
        print("✅ Created templates/ directory")
    else:
        print("ℹ️  templates/ directory already exists")

    # Create sessions directory for Telegram
    if not os.path.exists(SESSIONS_DIR):
        os.makedirs(SESSIONS_DIR)
        print("✅ Created telegram_sessions/ directory for persistent sessions")
    else:
        print("ℹ️  telegram_sessions/ directory already exists")

    # Check if templates/index.html exists
    if not os.path.exists('templates/index.html'):
        print("❌ WARNING: templates/index.html not found!")
        print("\n📋 Please create templates/index.html with the frontend code")
        return False
    else:
        print("✅ templates/index.html found")
        return True

    print("\n📁 Project structure ready!")
    print("\n📋 Next steps:")
    print("1. Install dependencies: pip install -r requirements.txt")
    print("2. Make sure templates/index.html exists with actual frontend code")
    print("3. Run: python app.py")
    print("=" * 50 + "\n")

# Run setup check
setup_ok = run_quick_setup()

# ===== IMPORT REQUIRED LIBRARIES =====
try:
    from telegram import Bot, Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
    print("✅ Telegram bot library OK")
except ImportError as e:
    logger.error(f"❌ Błąd importu telegram: {e}")
    print("❌ Telegram bot library missing - install: pip install python-telegram-bot==20.4")

try:
    from pybit.unified_trading import HTTP
    print("✅ Bybit library OK")
except ImportError as e:
    logger.error(f"❌ Błąd importu pybit: {e}")
    print("❌ Bybit library missing - install: pip install pybit==5.7.0")

try:
    from telethon.sync import TelegramClient
    from telethon import TelegramClient as TelegramClientAsync, events
    from telethon.tl.types import Channel, Chat, User
    from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError, FloodWaitError
    TELETHON_AVAILABLE = True
    print("✅ Telethon library OK")
except ImportError as e:
    logger.warning(f"⚠️ Telethon not available: {e}")
    print("⚠️ Telethon library missing - Telegram forwarder will be limited")
    TELETHON_AVAILABLE = False

# ===== FLASK & SOCKETIO INITIALIZATION =====
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
CORS(app)

# Initialize SocketIO with proper async mode
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Message queue for processing
message_queue = queue.Queue()

# ===== IMPORT CUSTOM MODULES =====
from utils.logger import WebSocketLogger

# Import core bot module and set global dependencies
from core import bot as core_bot_module
from core.bot import TelegramTradingBot

# Import standalone modules (for setting globals)
from core import position_manager as position_manager_module
from telegram_integration import forwarder as forwarder_module

# Import console module
from console.console_manager import ConsoleManager

# Import API routes and handlers
from api.routes import register_routes
from api.socketio_handlers import register_socketio_handlers

# ===== GLOBAL INSTANCES =====
# Create WebSocket logger
ws_logger = WebSocketLogger(socketio, message_queue)

# Set global logger and socketio for all modules that need them
core_bot_module.set_logger(ws_logger)
core_bot_module.set_socketio(socketio)

# Set globals for position_manager module
position_manager_module.ws_logger = ws_logger
position_manager_module.socketio = socketio

# Set globals for forwarder module
forwarder_module.ws_logger = ws_logger
forwarder_module.socketio = socketio

# Create trading bot instance with dependencies
bot = TelegramTradingBot(ws_logger_instance=ws_logger, socketio_instance=socketio)

# Get references to managers from bot (they are created internally)
position_manager = bot.position_manager
forwarder = bot.forwarder
risk_manager = bot.risk_manager
profile_manager = bot.profile_manager

# Create console manager
console_manager = ConsoleManager(
    bot=bot,
    forwarder=forwarder,
    risk_manager=risk_manager,
    position_manager=position_manager
)

# ===== REGISTER ROUTES AND HANDLERS =====
# Register Flask routes
register_routes(
    app=app,
    bot=bot,
    profile_manager=profile_manager,
    risk_manager=risk_manager,
    forwarder=forwarder,
    position_manager=position_manager,
    console_manager=console_manager,
    ws_logger=ws_logger
)

# Register Socket.IO handlers
register_socketio_handlers(
    socketio=socketio,
    bot=bot,
    ws_logger=ws_logger
)

# ===== MESSAGE QUEUE PROCESSOR =====
def process_message_queue():
    """Process messages from the queue and emit via Socket.IO"""
    while True:
        try:
            message = message_queue.get(timeout=1)
            if message['type'] == 'console':
                socketio.emit('console_message', {
                    'message': message['message'],
                    'level': message.get('level', 'info'),
                    'timestamp': message.get('timestamp')
                })
            message_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Error processing message queue: {e}")

# Start message queue processor thread
queue_thread = threading.Thread(target=process_message_queue, daemon=True)
queue_thread.start()

# ===== MAIN ENTRY POINT =====
if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🚀 Trading Bot Application Starting...")
    print("=" * 60)
    print(f"📁 Config file: {CONFIG_FILE}")
    print(f"📊 Risk tracking: {RISK_TRACKING_FILE}")
    print(f"💾 Profiles file: {PROFILES_FILE}")
    print(f"📱 Telegram sessions: {SESSIONS_DIR}/")
    print("=" * 60)
    print("\n🌐 Starting web server...")
    print("📡 Access the web interface at: http://localhost:5000")
    print("🛑 Press Ctrl+C to stop\n")

    try:
        # Start the web server
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        print("\n\n⏹️  Shutting down gracefully...")

        # Stop all services
        if bot.telegram_bot_running:
            bot.stop_telegram_bot()
            print("✅ Telegram bot stopped")

        if forwarder.running:
            forwarder.stop_forwarder()
            print("✅ Forwarder stopped")

        if position_manager.monitoring:
            position_manager.stop_monitoring()
            print("✅ Position monitoring stopped")

        print("👋 Goodbye!\n")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error: {e}")
        print("Check bot_trading.log for details\n")
