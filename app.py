import os
import re
import json
import time
import logging
import configparser
import asyncio
import threading
from datetime import datetime, timedelta
import urllib3
import sys
from flask import Flask, render_template, render_template_string, request, jsonify, send_file
import io
from contextlib import redirect_stdout, redirect_stderr
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import queue

# Wyłącz ostrzeżenia SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Ścieżki plików
CONFIG_FILE = "config.ini"
PROFILES_FILE = "trading_profiles.json"
RISK_TRACKING_FILE = "risk_tracking.json"
SESSIONS_DIR = "telegram_sessions"  # NEW: Directory for persistent Telegram sessions

# === QUICK SETUP SCRIPT ===
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
        print("   You can find it in the 'trading-bot-webapp' artifact\n")
        return False
    else:
        print("✅ templates/index.html found")
        return True
    
    # Create requirements.txt if it doesn't exist
    if not os.path.exists('requirements.txt'):
        requirements = """# Core Web Framework
flask==2.3.2
flask-socketio==5.3.4
flask-cors==4.0.0

# Trading & APIs - Updated versions
pybit==5.7.0
python-telegram-bot==20.4
telethon==1.30.3

# HTTP & Security
requests==2.31.0
urllib3==2.0.4

# Async Support
python-engineio==4.7.1
python-socketio==5.9.0

# Additional Dependencies
configparser==5.3.0"""
        
        with open('requirements.txt', 'w', encoding='utf-8') as f:
            f.write(requirements)
        print("✅ Created requirements.txt")
    
    print("\n📁 Project structure ready!")
    print("\n📋 Next steps:")
    print("1. Install dependencies: pip install -r requirements.txt")
    print("2. Make sure templates/index.html exists with actual frontend code")
    print("3. Run: python app.py")
    print("=" * 50 + "\n")

# Run setup check
setup_ok = run_quick_setup()

# Import wymaganych bibliotek
try:
    from telegram import Bot, Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
    print("✅ Telegram bot library OK")
except ImportError as e:
    print(f"❌ Błąd importu Telegram: {e}")
    print("💡 Zainstaluj: pip install python-telegram-bot")

try:
    from pybit.unified_trading import HTTP
    print("✅ Pybit library OK")
except ImportError as e:
    print(f"❌ Błąd importu Pybit: {e}")
    print("💡 Zainstaluj: pip install pybit==5.7.0")

try:
    import requests
    import hmac
    import hashlib
    print("✅ Biblioteki HTTP OK")
except ImportError as e:
    print(f"❌ Błąd importu HTTP: {e}")

# NOWY IMPORT - Telethon dla forwardowania
TELETHON_AVAILABLE = False
try:
    from telethon.sync import TelegramClient
    from telethon import TelegramClient as AsyncTelegramClient, events
    from telethon.tl.types import Channel, Chat, User
    from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError, FloodWaitError
    print("✅ Telethon library OK")
    TELETHON_AVAILABLE = True
except ImportError as e:
    print(f"❌ Błąd importu Telethon: {e}")
    print("💡 Zainstaluj: pip install telethon")
    print("⚠️  Forwarder będzie niedostępny bez Telethon!")

# Konfiguracja logowania
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot_trading.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flask app setup with explicit configuration
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# Initialize CORS with explicit configuration
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Initialize SocketIO with proper configuration for Socket.IO
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    async_mode='threading',
    logger=False,  # Disable SocketIO logging to reduce noise
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
    transports=['websocket', 'polling']
)

# Global message queue for real-time communication
message_queue = queue.Queue()

# Global auth queue for Telethon authentication
auth_queue = queue.Queue()
auth_response_queue = queue.Queue()


class WebSocketLogger:
    """Logger that sends messages to Socket.IO clients"""
    def __init__(self, socketio_instance, message_queue):
        self.socketio = socketio_instance
        self.message_queue = message_queue
        self.clients_connected = 0
    
    def log(self, message, level='info'):
        timestamp = datetime.now().strftime('%H:%M:%S')
        formatted_message = f"[{timestamp}] {message}"
        
        # Add to queue for potential processing
        self.message_queue.put({
            'type': 'console',
            'message': formatted_message,
            'level': level,
            'timestamp': timestamp
        })
        
        # Emit via Socket.IO if clients are connected
        try:
            if self.clients_connected > 0:
                self.socketio.emit('console_message', {
                    'message': formatted_message,
                    'level': level,
                    'timestamp': timestamp
                })
        except Exception as e:
            logger.error(f"Error emitting to Socket.IO: {e}")
        
        # Also log to file/console
        getattr(logger, level.lower(), logger.info)(message)
    
    def update_client_count(self, count):
        """Update connected client count"""
        self.clients_connected = count


# Global WebSocket logger instance
ws_logger = WebSocketLogger(socketio, message_queue)


class EnhancedRiskManager:
    """ENHANCED Risk Management with margin level tracking"""
    
    def __init__(self):
        self.tracking_file = RISK_TRACKING_FILE
        self.load_tracking()
    
    def load_tracking(self):
        """Wczytaj dane śledzenia ryzyka"""
        try:
            if os.path.exists(self.tracking_file):
                with open(self.tracking_file, 'r', encoding='utf-8') as f:
                    self.tracking = json.load(f)
            else:
                self.tracking = {
                    'daily_losses': {},
                    'weekly_losses': {},
                    'consecutive_losses': 0,
                    'total_trades_today': 0,
                    'last_trade_date': None,
                    'cooling_until': None,
                    'trade_history': [],
                    'margin_alerts': [],  # NEW
                    'last_margin_check': None  # NEW
                }
                self.save_tracking()
        except Exception as e:
            logger.error(f"❌ Błąd wczytywania tracking: {e}")
            self.tracking = {
                'daily_losses': {},
                'weekly_losses': {},
                'consecutive_losses': 0,
                'total_trades_today': 0,
                'last_trade_date': None,
                'cooling_until': None,
                'trade_history': [],
                'margin_alerts': [],
                'last_margin_check': None
            }
    
    def save_tracking(self):
        """Zapisz dane śledzenia ryzyka"""
        try:
            with open(self.tracking_file, 'w', encoding='utf-8') as f:
                json.dump(self.tracking, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"❌ Błąd zapisu tracking: {e}")
            return False
    
    def check_margin_level(self, balance_info, min_margin_level=1.5):
        """NEW: Check margin level to prevent liquidation"""
        try:
            if not balance_info:
                return False, "No balance info"
            
            total_wallet = balance_info.get('totalWalletBalance', 0)
            total_margin = balance_info.get('totalMarginBalance', 0)
            available_balance = balance_info.get('totalAvailableBalance', 0)
            
            # Calculate margin level
            if total_margin > 0:
                margin_level = total_wallet / total_margin
            else:
                margin_level = 999  # No positions
            
            # Update tracking
            self.tracking['last_margin_check'] = {
                'timestamp': datetime.now().isoformat(),
                'margin_level': margin_level,
                'total_wallet': total_wallet,
                'total_margin': total_margin
            }
            
            # Check if margin level is safe
            if margin_level < min_margin_level:
                alert_msg = f"⚠️ LOW MARGIN LEVEL: {margin_level:.2f} (Min: {min_margin_level})"
                ws_logger.log(alert_msg, 'error')
                
                # Add to alerts
                self.tracking['margin_alerts'].append({
                    'timestamp': datetime.now().isoformat(),
                    'margin_level': margin_level,
                    'message': alert_msg
                })
                
                # Keep only last 100 alerts
                if len(self.tracking['margin_alerts']) > 100:
                    self.tracking['margin_alerts'] = self.tracking['margin_alerts'][-100:]
                
                self.save_tracking()
                return False, f"Margin level too low: {margin_level:.2f}"
            
            return True, f"Margin level safe: {margin_level:.2f}"
            
        except Exception as e:
            ws_logger.log(f"❌ Error checking margin level: {e}", 'error')
            return False, str(e)
    
    def can_trade(self, daily_limit, weekly_limit, max_consecutive_losses, balance_info=None, min_margin_level=1.5):
        """ENHANCED: Check if trading is allowed based on risk limits and margin"""
        today = datetime.now().strftime('%Y-%m-%d')
        week = datetime.now().strftime('%Y-W%U')
        
        # NEW: Check margin level first
        if balance_info:
            margin_safe, margin_msg = self.check_margin_level(balance_info, min_margin_level)
            if not margin_safe:
                ws_logger.log(f"🛑 Trading blocked: {margin_msg}", 'error')
                return False, f"Margin protection: {margin_msg}"
        
        # Check cooling period
        if self.tracking.get('cooling_until'):
            cooling_until = datetime.fromisoformat(self.tracking['cooling_until'])
            if datetime.now() < cooling_until:
                remaining = (cooling_until - datetime.now()).total_seconds() / 60
                ws_logger.log(f"❄️ Cooling period aktywny jeszcze przez {remaining:.0f} minut", 'warning')
                return False, f"Cooling period aktywny jeszcze przez {remaining:.0f} minut"
        
        # Check daily loss limit
        daily_loss = self.tracking['daily_losses'].get(today, 0)
        if abs(daily_loss) >= daily_limit:
            ws_logger.log(f"🛑 Osiągnięto dzienny limit strat: ${abs(daily_loss):.2f} / ${daily_limit:.2f}", 'error')
            return False, f"Osiągnięto dzienny limit strat: ${abs(daily_loss):.2f}"
        
        # Check weekly loss limit
        weekly_loss = self.tracking['weekly_losses'].get(week, 0)
        if abs(weekly_loss) >= weekly_limit:
            ws_logger.log(f"🛑 Osiągnięto tygodniowy limit strat: ${abs(weekly_loss):.2f} / ${weekly_limit:.2f}", 'error')
            return False, f"Osiągnięto tygodniowy limit strat: ${abs(weekly_loss):.2f}"
        
        # Check consecutive losses
        if self.tracking['consecutive_losses'] >= max_consecutive_losses:
            ws_logger.log(f"🛑 Zbyt wiele strat z rzędu: {self.tracking['consecutive_losses']}", 'error')
            # Set cooling period for 1 hour
            self.tracking['cooling_until'] = (datetime.now() + timedelta(hours=1)).isoformat()
            self.save_tracking()
            return False, f"Zbyt wiele strat z rzędu ({self.tracking['consecutive_losses']}). Cooling period 1h."
        
        return True, "OK"
    
    def record_trade(self, profit_loss, symbol):
        """Zapisz wynik transakcji"""
        today = datetime.now().strftime('%Y-%m-%d')
        week = datetime.now().strftime('%Y-W%U')
        
        # Update daily losses
        if today not in self.tracking['daily_losses']:
            self.tracking['daily_losses'][today] = 0
        self.tracking['daily_losses'][today] += profit_loss
        
        # Update weekly losses
        if week not in self.tracking['weekly_losses']:
            self.tracking['weekly_losses'][week] = 0
        self.tracking['weekly_losses'][week] += profit_loss
        
        # Update consecutive losses
        if profit_loss < 0:
            self.tracking['consecutive_losses'] += 1
        else:
            self.tracking['consecutive_losses'] = 0
        
        # Add to history
        self.tracking['trade_history'].append({
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'profit_loss': profit_loss,
            'consecutive_losses': self.tracking['consecutive_losses']
        })
        
        # Keep only last 100 trades
        if len(self.tracking['trade_history']) > 100:
            self.tracking['trade_history'] = self.tracking['trade_history'][-100:]
        
        self.tracking['last_trade_date'] = today
        self.tracking['total_trades_today'] = len([t for t in self.tracking['trade_history'] 
                                                    if t['timestamp'].startswith(today)])
        
        self.save_tracking()
        
        # Log status
        ws_logger.log(f"📊 Trade recorded: {symbol} P/L: ${profit_loss:.2f}", 'info')
        ws_logger.log(f"📈 Daily P/L: ${self.tracking['daily_losses'][today]:.2f}", 'info')
        ws_logger.log(f"📅 Weekly P/L: ${self.tracking['weekly_losses'][week]:.2f}", 'info')
        
        return True
    
    def get_stats(self):
        """Get enhanced risk statistics"""
        today = datetime.now().strftime('%Y-%m-%d')
        week = datetime.now().strftime('%Y-W%U')
        
        stats = {
            'daily_loss': self.tracking['daily_losses'].get(today, 0),
            'weekly_loss': self.tracking['weekly_losses'].get(week, 0),
            'consecutive_losses': self.tracking['consecutive_losses'],
            'total_trades_today': self.tracking['total_trades_today'],
            'cooling_until': self.tracking.get('cooling_until'),
            'last_trade': self.tracking.get('last_trade_date'),
            'last_margin_check': self.tracking.get('last_margin_check', {}),
            'recent_margin_alerts': self.tracking.get('margin_alerts', [])[-5:]  # Last 5 alerts
        }
        
        return stats
    
    def reset_daily_limits(self):
        """Reset daily limits (to be called at midnight)"""
        # Remove old days (older than 7 days)
        cutoff_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        self.tracking['daily_losses'] = {
            date: loss for date, loss in self.tracking['daily_losses'].items()
            if date >= cutoff_date
        }
        self.save_tracking()
    
    def reset_weekly_limits(self):
        """Reset weekly limits"""
        # Remove old weeks (older than 4 weeks)
        current_week = int(datetime.now().strftime('%U'))
        current_year = int(datetime.now().strftime('%Y'))
        
        self.tracking['weekly_losses'] = {
            week: loss for week, loss in self.tracking['weekly_losses'].items()
            if self._parse_week(week)[0] == current_year and 
               abs(self._parse_week(week)[1] - current_week) < 4
        }
        self.save_tracking()
    
    def _parse_week(self, week_str):
        """Parse week string format YYYY-WNN"""
        parts = week_str.split('-W')
        return int(parts[0]), int(parts[1])


class ProfileManager:
    """Zarządzanie profilami handlowymi"""
    
    def __init__(self):
        self.profiles = self.load_profiles()
    
    def load_profiles(self):
        """Wczytaj profile z pliku"""
        try:
            if os.path.exists(PROFILES_FILE):
                with open(PROFILES_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"❌ Błąd wczytywania profili: {e}")
            return {}
    
    def save_profiles(self):
        """Zapisz profile do pliku"""
        try:
            with open(PROFILES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.profiles, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"❌ Błąd zapisu profili: {e}")
            return False
    
    def save_profile(self, name, config_data):
        """Zapisz profil"""
        self.profiles[name] = {
            'timestamp': datetime.now().isoformat(),
            'config': config_data
        }
        return self.save_profiles()
    
    def load_profile(self, name):
        """Wczytaj profil"""
        return self.profiles.get(name, {}).get('config', {})
    
    def delete_profile(self, name):
        """Usuń profil"""
        if name in self.profiles:
            del self.profiles[name]
            return self.save_profiles()
        return False


class TelegramForwarder:
    """ENHANCED Telegram Forwarder with persistent sessions"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Configuration
        self.api_id = None
        self.api_hash = None
        self.phone_number = None
        self.target_chat_id = None
        self.forward_all_messages = False
        
        # Client management
        self.telethon_client = None
        self.forwarder_running = False
        self.forwarder_thread = None
        
        # Channels
        self.monitored_channels = []
        self.available_channels = []
        
        # Console integration
        self.console_connection_status = "disconnected"
        self.console_last_command = None
        self.console_session_info = {}
        
        # Auth management
        self.auth_callback = None
        self._auth_lock = threading.Lock()
        
        # Channels cache
        self.channels_cache = {
            'channels': [],
            'last_update': None,
            'is_loading': False
        }
        
        # ENHANCED: Persistent session management
        self.session_name = None  # Will be set based on phone number
        self._client_lock = threading.Lock()
        self._session_authorized = False
        
        # Load configuration
        self.load_forwarder_config()
    
    def get_session_path(self, phone_number=None):
        """Get session file path based on phone number"""
        if not phone_number:
            phone_number = self.phone_number
        
        if not phone_number:
            return None
        
        # Clean phone number for filename
        clean_phone = re.sub(r'[^\d]', '', phone_number)
        session_name = f"session_{clean_phone}"
        
        # Ensure sessions directory exists
        if not os.path.exists(SESSIONS_DIR):
            os.makedirs(SESSIONS_DIR)
        
        return os.path.join(SESSIONS_DIR, session_name)
    
    def check_existing_session(self):
        """Check if a valid session already exists"""
        try:
            session_path = self.get_session_path()
            if not session_path:
                return False
            
            session_file = f"{session_path}.session"
            if os.path.exists(session_file):
                ws_logger.log(f"📂 Found existing session for {self.phone_number}", 'info')
                return True
            
            return False
        except Exception as e:
            ws_logger.log(f"Error checking session: {e}", 'error')
            return False
    
    def load_forwarder_config(self):
        """Load forwarder configuration"""
        try:
            config = self.bot.config
            if config.has_section('Forwarder'):
                # Safely load API ID
                api_id_str = config.get('Forwarder', 'api_id', fallback='')
                if api_id_str and api_id_str.isdigit():
                    self.api_id = int(api_id_str)
                else:
                    self.api_id = None
                
                self.api_hash = config.get('Forwarder', 'api_hash', fallback='')
                self.phone_number = config.get('Forwarder', 'phone_number', fallback='')
                self.target_chat_id = config.get('Forwarder', 'target_chat_id', fallback='')
                self.forward_all_messages = config.get('Forwarder', 'forward_all_messages', fallback='False').lower() == 'true'
                
                # Load monitored channels as JSON
                channels_json = config.get('Forwarder', 'monitored_channels', fallback='[]')
                try:
                    self.monitored_channels = json.loads(channels_json)
                except:
                    self.monitored_channels = []
                
                # Update session name if phone number is available
                if self.phone_number:
                    self.session_name = self.get_session_path()
                    self._session_authorized = self.check_existing_session()
            
            ws_logger.log(f"📱 Forwarder config loaded: API ID: {bool(self.api_id)}, Session exists: {self._session_authorized}")
        except Exception as e:
            ws_logger.log(f"❌ Error loading forwarder config: {e}", 'error')
    
    def save_forwarder_config(self):
        """Save forwarder configuration"""
        try:
            config = self.bot.config
            
            if not config.has_section('Forwarder'):
                config.add_section('Forwarder')
            
            config.set('Forwarder', 'api_id', str(self.api_id) if self.api_id else '')
            config.set('Forwarder', 'api_hash', str(self.api_hash) if self.api_hash else '')
            config.set('Forwarder', 'phone_number', str(self.phone_number) if self.phone_number else '')
            config.set('Forwarder', 'target_chat_id', str(self.target_chat_id) if self.target_chat_id else '')
            config.set('Forwarder', 'forward_all_messages', str(self.forward_all_messages))
            config.set('Forwarder', 'monitored_channels', json.dumps(self.monitored_channels))
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                config.write(configfile)
            
            self.bot.save_config()
            
            ws_logger.log("✅ Forwarder configuration saved", 'success')
            return True
            
        except Exception as e:
            ws_logger.log(f"❌ Error saving forwarder config: {e}", 'error')
            return False
    
    def initialize_telethon_client(self):
        """Initialize Telethon client with persistent session"""
        try:
            if not TELETHON_AVAILABLE:
                ws_logger.log("❌ Telethon not installed!", 'error')
                return False
            
            if not self.api_id or not self.api_hash:
                ws_logger.log("❌ Missing API ID or API Hash.", 'error')
                return False
            
            if not self.phone_number:
                ws_logger.log("❌ Missing phone number.", 'error')
                return False
            
            with self._client_lock:
                # Clean up existing client if any
                if self.telethon_client:
                    try:
                        self.telethon_client = None
                    except:
                        pass
                
                # Update session path
                self.session_name = self.get_session_path()
                
                ws_logger.log("🔄 Initializing Telethon client...")
                ws_logger.log(f"   📱 Phone number: {self.phone_number}")
                ws_logger.log(f"   📁 Session path: {self.session_name}")
                ws_logger.log(f"   🔐 Existing session: {self._session_authorized}")
                
                # Create new client with persistent session
                self.telethon_client = AsyncTelegramClient(
                    self.session_name,
                    self.api_id, 
                    self.api_hash.strip()
                )
                
                ws_logger.log("✅ Telethon client initialized successfully", 'success')
                return True
                
        except Exception as e:
            ws_logger.log(f"❌ Telethon initialization error: {e}", 'error')
            self.telethon_client = None
            return False
    
    async def _auth_code_callback(self):
        """Callback for phone code authentication"""
        try:
            # Send auth request via Socket.IO
            socketio.emit('auth_required', {'auth_type': 'code'})
            
            # Wait for response with timeout
            timeout = 120  # 2 minutes
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if not auth_queue.empty():
                    auth_data = auth_queue.get()
                    if auth_data.get('type') == 'code':
                        return auth_data.get('value')
                await asyncio.sleep(0.5)
            
            raise TimeoutError("Timeout waiting for auth code")
            
        except Exception as e:
            ws_logger.log(f"❌ Auth code callback error: {e}", 'error')
            raise
    
    async def _auth_password_callback(self):
        """Callback for 2FA password authentication"""
        try:
            # Send auth request via Socket.IO
            socketio.emit('auth_required', {'auth_type': 'password'})
            
            # Wait for response with timeout
            timeout = 120  # 2 minutes
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if not auth_queue.empty():
                    auth_data = auth_queue.get()
                    if auth_data.get('type') == 'password':
                        return auth_data.get('value')
                await asyncio.sleep(0.5)
            
            raise TimeoutError("Timeout waiting for 2FA password")
            
        except Exception as e:
            ws_logger.log(f"❌ Auth password callback error: {e}", 'error')
            raise
    
    async def connect_and_get_channels(self):
        """Connect and get channels list with session reuse"""
        try:
            if not self.telethon_client:
                ws_logger.log("❌ Telethon client not initialized", 'error')
                return False
            
            ws_logger.log("🔄 Connecting to Telegram...", 'info')
            
            # Update channels cache status
            self.channels_cache['is_loading'] = True
            socketio.emit('forwarder_channels_loading', {'loading': True})
            
            try:
                # Check if session exists
                session_file = f"{self.session_name}.session"
                session_exists = os.path.exists(session_file)
                
                if session_exists:
                    ws_logger.log("📂 Found existing session, attempting connection...", 'info')
                    
                    # Try to connect with existing session
                    try:
                        await self.telethon_client.connect()
                        if await self.telethon_client.is_user_authorized():
                            ws_logger.log("✅ Connected using existing session! No 2FA needed.", 'success')
                            self._session_authorized = True
                        else:
                            ws_logger.log("⚠️ Session expired, re-authorization required", 'warning')
                            await self.telethon_client.start(
                                phone=self.phone_number,
                                code_callback=self._auth_code_callback,
                                password=self._auth_password_callback
                            )
                            self._session_authorized = True
                    except Exception as e:
                        # If existing session fails, start fresh
                        ws_logger.log(f"⚠️ Session error: {e}, creating new session...", 'warning')
                        await self.telethon_client.start(
                            phone=self.phone_number,
                            code_callback=self._auth_code_callback,
                            password=self._auth_password_callback
                        )
                        self._session_authorized = True
                else:
                    ws_logger.log("📱 No existing session, authorization required", 'info')
                    # Start client with proper auth callbacks
                    await self.telethon_client.start(
                        phone=self.phone_number,
                        code_callback=self._auth_code_callback,
                        password=self._auth_password_callback
                    )
                    self._session_authorized = True
                
                ws_logger.log("✅ Connected to Telegram", 'success')
                
            except SessionPasswordNeededError:
                ws_logger.log("🔐 2FA password required", 'warning')
                password = await self._auth_password_callback()
                await self.telethon_client.start(
                    phone=self.phone_number,
                    password=password
                )
                self._session_authorized = True
                ws_logger.log("✅ Logged in with 2FA", 'success')
                
            except PhoneCodeInvalidError:
                ws_logger.log("❌ Invalid verification code", 'error')
                self.channels_cache['is_loading'] = False
                socketio.emit('forwarder_channels_loading', {'loading': False})
                return False
                
            except PhoneCodeExpiredError:
                ws_logger.log("❌ Verification code expired. Try again.", 'error')
                self.channels_cache['is_loading'] = False
                socketio.emit('forwarder_channels_loading', {'loading': False})
                return False
                
            except FloodWaitError as e:
                ws_logger.log(f"❌ Too many attempts. Wait {e.seconds} seconds.", 'error')
                self.channels_cache['is_loading'] = False
                socketio.emit('forwarder_channels_loading', {'loading': False})
                return False
                
            except Exception as e:
                ws_logger.log(f"❌ Authorization error: {e}", 'error')
                self.channels_cache['is_loading'] = False
                socketio.emit('forwarder_channels_loading', {'loading': False})
                return False
            
            # Save session info
            self.console_connection_status = "connected"
            me = await self.telethon_client.get_me()
            self.console_session_info = {
                'user_id': me.id,
                'username': me.username or 'No username',
                'first_name': me.first_name or 'Unknown',
                'phone': me.phone or 'Unknown'
            }
            
            ws_logger.log(f"✅ Logged in as: {self.console_session_info['first_name']} (@{self.console_session_info['username']})")
            
            # Get channels and groups
            ws_logger.log("📋 Fetching channels list...", 'info')
            channels = []
            
            async for dialog in self.telethon_client.iter_dialogs():
                if dialog.is_channel or dialog.is_group:
                    channel_info = {
                        'name': dialog.name,
                        'id': str(dialog.id),
                        'username': dialog.entity.username if hasattr(dialog.entity, 'username') and dialog.entity.username else None,
                        'type': 'Channel' if dialog.is_channel and not dialog.is_group else 'Group',
                        'participants': getattr(dialog.entity, 'participants_count', 'Unknown'),
                        'is_monitored': any(ch['id'] == str(dialog.id) for ch in self.monitored_channels)
                    }
                    channels.append(channel_info)
                    ws_logger.log(f"   📺 {channel_info['name']} ({channel_info['type']})")
            
            self.available_channels = channels
            self.channels_cache = {
                'channels': channels,
                'last_update': datetime.now().isoformat(),
                'is_loading': False
            }
            
            # Emit channels update
            socketio.emit('forwarder_channels_update', {
                'channels': channels,
                'monitored': self.monitored_channels
            })
            
            ws_logger.log(f"✅ Fetched {len(channels)} channels/groups", 'success')
            
            # Keep connection alive for reuse
            ws_logger.log("📡 Keeping session active for future use", 'info')
            
            return True
            
        except Exception as e:
            ws_logger.log(f"❌ Error in connect_and_get_channels: {e}", 'error')
            self.console_connection_status = "error"
            self.channels_cache['is_loading'] = False
            socketio.emit('forwarder_channels_loading', {'loading': False})
            return False
    
    def get_channels_list(self):
        """Get channels list synchronously"""
        try:
            ws_logger.log("📱 Starting channels fetch...", 'info')
            
            # Clear previous channels
            self.available_channels = []
            
            # Initialize client if needed
            if not self.initialize_telethon_client():
                ws_logger.log("❌ Failed to initialize client", 'error')
                return None
            
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                success = loop.run_until_complete(self.connect_and_get_channels())
                if success:
                    ws_logger.log(f"✅ Successfully fetched {len(self.available_channels)} channels", 'success')
                    return self.available_channels
                else:
                    ws_logger.log("❌ Failed to fetch channels", 'error')
                    return None
            finally:
                loop.close()
                asyncio.set_event_loop(None)
                
        except Exception as e:
            ws_logger.log(f"❌ Error in get_channels_list: {e}", 'error')
            import traceback
            ws_logger.log(f"   Traceback: {traceback.format_exc()}", 'error')
            return None
    
    def get_cached_channels(self):
        """Get channels from cache or return current status"""
        return self.channels_cache
    
    def start_forwarder(self):
        """Start forwarder in separate thread"""
        try:
            if self.forwarder_running:
                ws_logger.log("⚠️ Forwarder already running", 'warning')
                return True
            
            # Check if Telethon is available
            if not TELETHON_AVAILABLE:
                ws_logger.log("❌ Telethon not installed - forwarder cannot run", 'error')
                return False
            
            # Validate configuration
            if not self.api_id or not self.api_hash:
                ws_logger.log("❌ Missing API ID or API Hash - configure Telethon data first", 'error')
                return False
            
            if not self.phone_number:
                ws_logger.log("❌ Missing phone number - enter phone number", 'error')
                return False
            
            if not self.monitored_channels:
                ws_logger.log("❌ No channels selected for monitoring", 'error')
                return False
            
            if not self.target_chat_id:
                ws_logger.log("⚠️ No target Chat ID - using bot's Chat ID", 'warning')
                self.target_chat_id = self.bot.telegram_chat_id
            
            if not self.target_chat_id:
                ws_logger.log("❌ No target Chat ID for forwarding messages", 'error')
                return False
            
            self.forwarder_running = True
            self.forwarder_thread = threading.Thread(
                target=self._run_forwarder_thread,
                daemon=True
            )
            self.forwarder_thread.start()
            
            # Emit status update via Socket.IO
            socketio.emit('status_update', {'forwarder': True})
            
            ws_logger.log(f"✅ Forwarder started - forwarding to Chat ID: {self.target_chat_id}", 'success')
            return True
            
        except Exception as e:
            ws_logger.log(f"❌ Error starting forwarder: {e}", 'error')
            self.forwarder_running = False
            return False
    
    def _run_forwarder_thread(self):
        """Run forwarder in a separate thread with its own event loop"""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                loop.run_until_complete(self._async_forwarder())
            finally:
                loop.close()
                asyncio.set_event_loop(None)
                
        except Exception as e:
            ws_logger.log(f"❌ Error in forwarder thread: {e}", 'error')
            self.forwarder_running = False
            # Emit status update
            socketio.emit('status_update', {'forwarder': False})
    
    async def _async_forwarder(self):
        """Asynchronous forwarder with session reuse"""
        forwarder_client = None
        try:
            # Use existing session or create new one
            session_path = f'{self.session_name}_worker'
            
            # Check if worker session exists
            worker_session_file = f"{session_path}.session"
            worker_session_exists = os.path.exists(worker_session_file)
            
            forwarder_client = AsyncTelegramClient(
                session_path,
                self.api_id,
                self.api_hash.strip()
            )
            
            # Connect client
            ws_logger.log("🔄 Connecting forwarder to Telegram...", 'info')
            
            if worker_session_exists:
                ws_logger.log("📂 Using existing forwarder session", 'info')
                await forwarder_client.connect()
                if not await forwarder_client.is_user_authorized():
                    ws_logger.log("⚠️ Session expired, re-authorizing", 'warning')
                    await forwarder_client.start(
                        phone=self.phone_number,
                        code_callback=self._auth_code_callback,
                        password=self._auth_password_callback
                    )
                else:
                    ws_logger.log("✅ Forwarder connected with existing session", 'success')
            else:
                ws_logger.log("📱 Creating new forwarder session", 'info')
                await forwarder_client.start(
                    phone=self.phone_number,
                    code_callback=self._auth_code_callback,
                    password=self._auth_password_callback
                )
                ws_logger.log("✅ Forwarder connected", 'success')
            
            # Channels monitoring data
            monitored_channels_data = {}
            
            # Convert channel IDs to int for Telethon
            for ch in self.monitored_channels:
                try:
                    channel_id = int(ch['id'])
                    # Get last message from channel as starting point
                    last_messages = await forwarder_client.get_messages(channel_id, limit=1)
                    last_message_id = last_messages[0].id if last_messages else 0
                    
                    monitored_channels_data[channel_id] = {
                        'name': ch['name'],
                        'last_message_id': last_message_id
                    }
                    ws_logger.log(f"📺 Channel {ch['name']}: starting message_id = {last_message_id}")
                except Exception as e:
                    ws_logger.log(f"❌ Error initializing channel {ch.get('name', 'Unknown')}: {e}", 'error')
                    continue
            
            if not monitored_channels_data:
                ws_logger.log("❌ No channels available for monitoring", 'error')
                await forwarder_client.disconnect()
                return
            
            ws_logger.log(f"🔍 POLLING: Monitoring {len(monitored_channels_data)} channels...")
            ws_logger.log(f"📤 Forwarding to Chat ID: {self.target_chat_id}")
            ws_logger.log("🔄 Checking for new messages every 3 seconds...")
            
            # Emit forwarder stats
            socketio.emit('forwarder_stats', {
                'monitoring': len(monitored_channels_data),
                'target_chat_id': self.target_chat_id,
                'forward_all': self.forward_all_messages
            })
            
            # MAIN POLLING LOOP
            while self.forwarder_running:
                try:
                    # Check each monitored channel
                    for channel_id, channel_data in monitored_channels_data.items():
                        try:
                            channel_name = channel_data['name']
                            last_message_id = channel_data['last_message_id']
                            
                            # Get new messages since last check
                            new_messages = await forwarder_client.get_messages(
                                channel_id, 
                                min_id=last_message_id, 
                                limit=10  # Limit to prevent too many messages at once
                            )
                            
                            # Process new messages (from oldest to newest)
                            for message in reversed(new_messages):
                                if message.id > last_message_id:  # Only process newer messages
                                    if message.text:  # Only text messages
                                        await self.process_message(message, channel_name, forwarder_client)
                                    
                                    # Update last message_id
                                    monitored_channels_data[channel_id]['last_message_id'] = message.id
                            
                            # Log new messages
                            if new_messages and len(new_messages) > 0:
                                actual_new = len([m for m in new_messages if m.id > last_message_id])
                                if actual_new > 0:
                                    ws_logger.log(f"📨 {actual_new} new messages from {channel_name}")
                        
                        except Exception as e:
                            ws_logger.log(f"❌ Error checking channel {channel_data.get('name', 'Unknown')}: {e}", 'error')
                            continue
                    
                    # Wait before next check
                    await asyncio.sleep(3)
                    
                except Exception as e:
                    ws_logger.log(f"❌ Error in main polling loop: {e}", 'error')
                    await asyncio.sleep(10)  # Longer wait on error
                    continue
            
            ws_logger.log("🛑 Polling forwarder stopped")
            
        except Exception as e:
            ws_logger.log(f"❌ Error in async forwarder: {e}", 'error')
        finally:
            # Clean up
            if forwarder_client:
                try:
                    await forwarder_client.disconnect()
                except:
                    pass
            self.forwarder_running = False
            socketio.emit('status_update', {'forwarder': False})
    
    async def process_message(self, message, channel_name, client=None):
        """Process single message"""
        try:
            message_text = message.text
            
            if not message_text:
                return
            
            ws_logger.log(f"📨 New message from {channel_name}: {message_text[:50]}...")
            
            # Emit message event
            socketio.emit('forwarder_message', {
                'channel': channel_name,
                'preview': message_text[:100] + '...' if len(message_text) > 100 else message_text,
                'timestamp': datetime.now().isoformat()
            })
            
            # Try to parse as trading signal
            signal = self.bot.parse_trading_signal(message_text)
            
            if signal:
                # THIS IS A TRADING SIGNAL
                ws_logger.log(f"✅ Signal recognized from {channel_name}: {signal['symbol']} {signal['position_type']}", 'success')
                
                # Send signal to target Chat ID
                await self.send_to_target_chat(
                    f"🔄 FORWARDER → SIGNAL\n"
                    f"📺 Channel: {channel_name}\n"
                    f"✅ Recognized: {signal['symbol']} {signal['position_type'].upper()}\n"
                    f"💰 Entry: {signal['entry_price']}\n"
                    f"🎯 Targets: {len(signal['targets'])}\n"
                    f"🛑 SL: {signal['stop_loss'] or 'None'}\n\n"
                    f"📋 Original signal:\n{message_text[:500]}{'...' if len(message_text) > 500 else ''}"
                )
                
                # Auto-execute if enabled
                if self.bot.auto_execute_signals:
                    try:
                        if self.bot.bybit_client:
                            result = self.bot.execute_trade(signal)
                            ws_logger.log(f"🤖 Auto-trade from {channel_name}: {result}")
                            
                            # Send execution notification
                            await self.send_to_target_chat(
                                f"🤖 AUTO-TRADE EXECUTED\n"
                                f"📺 Channel: {channel_name}\n"
                                f"📊 Signal: {signal['symbol']} {signal['position_type'].upper()}\n"
                                f"🤖 Result: {result[:200]}{'...' if len(result) > 200 else ''}"
                            )
                        else:
                            ws_logger.log("❌ No Bybit API connection", 'error')
                            await self.send_to_target_chat(
                                f"❌ AUTO-TRADE ERROR\n"
                                f"📺 Channel: {channel_name}\n"
                                f"🚫 No Bybit API connection"
                            )
                    except Exception as e:
                        error_msg = f"❌ Auto-trade error from {channel_name}: {str(e)}"
                        ws_logger.log(error_msg, 'error')
                        await self.send_to_target_chat(error_msg)
                else:
                    # Just notification about recognized signal
                    ws_logger.log(f"ℹ️ Signal recognized from {channel_name} (auto-trade disabled)")
            
            elif self.forward_all_messages:
                # NOT A SIGNAL, BUT "FORWARD ALL" OPTION IS ENABLED
                ws_logger.log(f"📨 Forwarding all messages from {channel_name}")
                
                await self.send_to_target_chat(
                    f"📄 Content: {message_text[:800]}{'...' if len(message_text) > 800 else ''}"
                )
            
            else:
                # NOT A SIGNAL AND "FORWARD ALL" DISABLED
                ws_logger.log(f"ℹ️ Message from {channel_name} is not a trading signal (skipping)")
        
        except Exception as e:
            ws_logger.log(f"❌ Error processing message from {channel_name}: {e}", 'error')
    
    async def send_to_target_chat(self, message):
        """Send message to target Chat ID"""
        try:
            if not self.bot.telegram_bot or not self.target_chat_id:
                ws_logger.log("⚠️ No Telegram bot or target Chat ID", 'warning')
                return False
            
            await self.bot.telegram_bot.send_message(
                chat_id=self.target_chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            ws_logger.log(f"📤 Message sent to Chat ID: {self.target_chat_id}", 'success')
            return True
            
        except Exception as e:
            ws_logger.log(f"❌ Error sending to target chat: {e}", 'error')
            return False
    
    def stop_forwarder(self):
        """Stop forwarder"""
        try:
            if not self.forwarder_running:
                return True
            
            ws_logger.log("🛑 Stopping forwarder...")
            self.forwarder_running = False
            
            # Emit status update
            socketio.emit('status_update', {'forwarder': False})
            
            # Wait for thread to finish
            if self.forwarder_thread and self.forwarder_thread.is_alive():
                self.forwarder_thread.join(timeout=5)
            
            ws_logger.log("✅ Forwarder stopped", 'success')
            return True
            
        except Exception as e:
            ws_logger.log(f"❌ Error stopping forwarder: {e}", 'error')
            return False
    
    def __del__(self):
        """Cleanup on object deletion"""
        try:
            # Stop forwarder if running
            if self.forwarder_running:
                self.forwarder_running = False
        except:
            pass


class PositionManager:
    """ENHANCED Position Management with customizable breakeven targets"""
    
    def __init__(self, bot):
        self.bot = bot
        self.active_positions = {}  # Symbol -> position info
        self.monitoring_active = False
        self.monitor_thread = None
    
    def add_position(self, symbol, signal, order_id):
        """Add position to monitoring"""
        try:
            position_info = {
                'symbol': symbol,
                'signal': signal,
                'order_id': order_id,
                'entry_price': signal['entry_price'],
                'position_type': signal['position_type'],
                'targets': signal.get('targets', {}),
                'stop_loss': signal.get('stop_loss'),
                'filled_targets': set(),
                'sl_moved_to_breakeven': False,
                'created_at': datetime.now(),
                'tp_orders': {},
                'sl_order_id': None,
                'last_price_check': None,
                'target_check_count': 0,
                'breakeven_target': self.bot.breakeven_after_target  # Configurable target
            }
            
            self.active_positions[symbol] = position_info
            ws_logger.log(f"✅ Position {symbol} added to monitoring", 'success')
            ws_logger.log(f"💡 Breakeven will be activated after TP{self.bot.breakeven_after_target}", 'info')
            
            # Emit position update via Socket.IO
            socketio.emit('message', {
                'type': 'position',
                'action': 'added',
                'position': self._position_to_dict(position_info)
            })
            
            # Auto setup TP and SL with delay
            time.sleep(2)  # Wait 2 seconds
            self.setup_tp_sl_orders(symbol)
            
            return True
        except Exception as e:
            ws_logger.log(f"❌ Error adding position to monitoring: {e}", 'error')
            return False
    
    def _position_to_dict(self, position_info):
        """Convert position info to dictionary for Socket.IO"""
        return {
            'symbol': position_info['symbol'],
            'type': position_info['position_type'],
            'entry': position_info['entry_price'],
            'targets': f"{len(position_info['filled_targets'])}/{len(position_info['targets'])}",
            'sl_breakeven': position_info['sl_moved_to_breakeven'],
            'created': position_info['created_at'].strftime('%H:%M:%S'),
            'last_price': position_info.get('last_price_check', 'Unknown'),
            'checks': position_info.get('target_check_count', 0),
            'breakeven_trigger': f"TP{position_info.get('breakeven_target', 1)}"
        }
    
    def check_target_reached_by_price(self, symbol):
        """Check if targets have been reached based on current price"""
        try:
            if symbol not in self.active_positions:
                return False
            
            position = self.active_positions[symbol]
            targets = position.get('targets', {})
            filled_targets = position.get('filled_targets', set())
            position_type = position['position_type'].lower()
            entry_price = position['entry_price']
            breakeven_target = position.get('breakeven_target', 1)
            
            if not targets:
                return False
            
            # Get current price
            current_price = self.get_current_price(symbol)
            if not current_price:
                ws_logger.log(f"⚠️ Cannot get current price for {symbol}", 'warning')
                return False
            
            # Update price check info
            position['last_price_check'] = current_price
            position['target_check_count'] += 1
            
            ws_logger.log(f"💹 Checking targets for {symbol}:")
            ws_logger.log(f"   📊 Position: {position_type.upper()}")
            ws_logger.log(f"   💰 Entry: {entry_price}")
            ws_logger.log(f"   💹 Current price: {current_price}")
            ws_logger.log(f"   🎯 Check #{position['target_check_count']}")
            
            newly_filled = []
            
            # Check each target
            for target_num, target_price in sorted(targets.items()):
                if target_num in filled_targets:
                    continue  # Target already reached
                
                # Check if target reached based on position type
                target_reached = False
                
                if position_type == "long":
                    # For LONG: target reached when price >= target_price
                    if current_price >= target_price:
                        target_reached = True
                        ws_logger.log(f"🎯 LONG TP{target_num} REACHED! Price {current_price} >= Target {target_price}", 'success')
                elif position_type == "short":
                    # For SHORT: target reached when price <= target_price
                    if current_price <= target_price:
                        target_reached = True
                        ws_logger.log(f"🎯 SHORT TP{target_num} REACHED! Price {current_price} <= Target {target_price}", 'success')
                
                if target_reached:
                    filled_targets.add(target_num)
                    newly_filled.append(target_num)
                    ws_logger.log(f"✅ Target {target_num} added to reached for {symbol}", 'success')
                else:
                    if position_type == "long":
                        distance = ((target_price - current_price) / current_price) * 100
                        ws_logger.log(f"⏳ TP{target_num}: Need +{distance:.2f}% to {target_price}")
                    else:
                        distance = ((current_price - target_price) / current_price) * 100
                        ws_logger.log(f"⏳ TP{target_num}: Need -{distance:.2f}% to {target_price}")
            
            # If new targets reached
            if newly_filled:
                ws_logger.log(f"🎉 NEW TARGETS REACHED for {symbol}: {newly_filled}", 'success')
                
                # Emit position update via Socket.IO
                socketio.emit('message', {
                    'type': 'position',
                    'action': 'targets_hit',
                    'symbol': symbol,
                    'targets': newly_filled,
                    'current_price': current_price
                })
                
                # Check if breakeven target is reached
                if breakeven_target in newly_filled and not position['sl_moved_to_breakeven'] and self.bot.auto_breakeven:
                    ws_logger.log(f"💡 Target {breakeven_target} reached for {symbol} - initiating breakeven", 'info')
                    breakeven_success = self.move_sl_to_breakeven(symbol)
                    if breakeven_success:
                        ws_logger.log(f"🎉 BREAKEVEN ACTIVATED for {symbol} after TP{breakeven_target}!", 'success')
                    else:
                        ws_logger.log(f"❌ Error activating breakeven for {symbol}", 'error')
                
                return True
            
            return False
            
        except Exception as e:
            ws_logger.log(f"❌ Error checking targets for {symbol}: {e}", 'error')
            return False
    
    def move_sl_to_breakeven(self, symbol):
        """Move SL to breakeven point"""
        try:
            if symbol not in self.active_positions:
                ws_logger.log(f"❌ Position {symbol} not in monitoring", 'error')
                return False
            
            position = self.active_positions[symbol]
            
            if position['sl_moved_to_breakeven']:
                ws_logger.log(f"ℹ️ SL already moved to breakeven for {symbol}")
                return True
            
            entry_price = position['entry_price']
            position_type = position['position_type'].lower()
            
            ws_logger.log(f"💡 Moving SL to breakeven for {symbol}")
            ws_logger.log(f"   📊 Position: {position_type.upper()}")
            ws_logger.log(f"   💰 Entry price (breakeven): {entry_price}")
            
            # STEP 1: Cancel old SL if exists
            if position['sl_order_id']:
                ws_logger.log(f"🗑️ Canceling old SL: {position['sl_order_id']}")
                cancel_success = self.cancel_sl_order(symbol, position['sl_order_id'])
                if cancel_success:
                    ws_logger.log(f"✅ Old SL canceled for {symbol}", 'success')
                else:
                    ws_logger.log(f"⚠️ Failed to cancel old SL for {symbol}, continuing...", 'warning')
                
                # Clear old SL ID
                position['sl_order_id'] = None
            
            # STEP 2: Set new SL at breakeven level
            ws_logger.log(f"📤 Setting new SL at breakeven: {entry_price}")
            success = self.set_stop_loss(symbol, entry_price)
            
            if success:
                position['sl_moved_to_breakeven'] = True
                ws_logger.log(f"🎉 SUCCESS! SL moved to breakeven for {symbol} at level {entry_price}", 'success')
                
                # Emit position update via Socket.IO
                socketio.emit('message', {
                    'type': 'position',
                    'action': 'breakeven',
                    'symbol': symbol,
                    'entry_price': entry_price
                })
                
                # Send Telegram notification
                if hasattr(self.bot, 'telegram_bot') and self.bot.telegram_bot and self.bot.telegram_chat_id:
                    try:
                        message = (
                            f"💡 BREAKEVEN ACTIVATED!\n"
                            f"📊 Symbol: {symbol}\n"
                            f"📈 Position: {position_type.upper()}\n"
                            f"🎯 Target {position.get('breakeven_target', 1)} reached!\n"
                            f"🛡️ Stop Loss moved to breakeven: {entry_price}\n"
                            f"✅ Position is now safe!"
                        )
                        
                        # Run in new event loop
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.bot.send_telegram_message(message))
                        loop.close()
                        
                        ws_logger.log(f"📱 Breakeven notification sent for {symbol}", 'success')
                    except Exception as e:
                        ws_logger.log(f"⚠️ Failed to send breakeven notification: {e}", 'warning')
                
                return True
            else:
                ws_logger.log(f"❌ ERROR! Failed to set new SL at breakeven for {symbol}", 'error')
                return False
                
        except Exception as e:
            ws_logger.log(f"❌ Error moving SL to breakeven for {symbol}: {e}", 'error')
            return False
    
    def setup_tp_sl_orders(self, symbol):
        """Setup TP and SL orders for position"""
        try:
            if symbol not in self.active_positions:
                ws_logger.log(f"❌ Position {symbol} not in monitoring", 'error')
                return False
            
            position = self.active_positions[symbol]
            signal = position.get('signal', {})
            
            ws_logger.log(f"🔧 Setting up TP/SL for {symbol}...")
            
            # Check if position actually exists
            current_size = self.get_current_position_size(symbol)
            if current_size <= 0:
                ws_logger.log(f"❌ No active position for {symbol} - cannot set TP/SL", 'error')
                return False
            
            success_count = 0
            total_orders = 0
            
            # Set Take Profit orders
            targets = signal.get('targets', {})
            if targets:
                ws_logger.log(f"🎯 Setting {len(targets)} targets for {symbol}")
                
                # Sort targets by number
                sorted_targets = sorted(targets.items())
                
                for target_num, target_price in sorted_targets:
                    total_orders += 1
                    try:
                        success = self.set_take_profit(symbol, target_num, target_price)
                        if success:
                            success_count += 1
                            ws_logger.log(f"✅ TP{target_num} set for {symbol} @ {target_price}", 'success')
                        else:
                            ws_logger.log(f"❌ Error setting TP{target_num} for {symbol}", 'error')
                    except Exception as e:
                        ws_logger.log(f"❌ Exception TP{target_num} for {symbol}: {e}", 'error')
            
            # Set Stop Loss
            stop_loss = signal.get('stop_loss')
            if stop_loss:
                total_orders += 1
                try:
                    success = self.set_stop_loss(symbol, stop_loss)
                    if success:
                        success_count += 1
                        ws_logger.log(f"✅ SL set for {symbol} @ {stop_loss}", 'success')
                    else:
                        ws_logger.log(f"❌ Error setting SL for {symbol}", 'error')
                except Exception as e:
                    ws_logger.log(f"❌ Exception SL for {symbol}: {e}", 'error')
            
            # Report results
            if total_orders > 0:
                success_rate = (success_count / total_orders) * 100
                ws_logger.log(f"📊 TP/SL for {symbol}: {success_count}/{total_orders} ({success_rate:.0f}%)")
                return success_count > 0
            else:
                ws_logger.log(f"⚠️ No targets and SL to set for {symbol}", 'warning')
                return True
                
        except Exception as e:
            ws_logger.log(f"❌ Error setup_tp_sl_orders for {symbol}: {e}", 'error')
            return False
    
    def set_take_profit(self, symbol, target_num, target_price):
        """Set Take Profit order"""
        try:
            if not self.bot.bybit_client:
                ws_logger.log("❌ No Bybit client", 'error')
                return False
            
            position = self.active_positions.get(symbol)
            if not position:
                ws_logger.log(f"❌ No position {symbol} in monitoring", 'error')
                return False
            
            # Validate Take Profit
            entry_price = position['entry_price']
            position_type = position['position_type'].lower()
            
            ws_logger.log(f"🔍 Validating TP{target_num} for {symbol}:")
            ws_logger.log(f"   📊 Position: {position_type.upper()}")
            ws_logger.log(f"   💰 Entry: {entry_price}")
            ws_logger.log(f"   🎯 TP{target_num}: {target_price}")
            
            # Logical validation
            if position_type == "long":
                if target_price <= entry_price:
                    error_msg = f"❌ ERROR TP{target_num} for LONG {symbol}: TP ({target_price}) <= Entry ({entry_price})"
                    ws_logger.log(error_msg, 'error')
                    ws_logger.log("💡 For LONG: Take Profit must be ABOVE entry price!", 'warning')
                    return False
            elif position_type == "short":
                if target_price >= entry_price:
                    error_msg = f"❌ ERROR TP{target_num} for SHORT {symbol}: TP ({target_price}) >= Entry ({entry_price})"
                    ws_logger.log(error_msg, 'error')
                    ws_logger.log("💡 For SHORT: Take Profit must be BELOW entry price!", 'warning')
                    return False
            
            ws_logger.log(f"✅ TP{target_num} validation PASSED for {position_type.upper()} {symbol}", 'success')
            
            # Get current position size
            current_position_size = self.get_current_position_size(symbol)
            if not current_position_size or current_position_size <= 0:
                ws_logger.log(f"❌ No current position for {symbol}", 'error')
                return False
            
            # Calculate size for this target
            total_targets = len(position['targets'])
            if total_targets == 0:
                ws_logger.log(f"❌ No targets for {symbol}", 'error')
                return False
            
            tp_qty = current_position_size / total_targets
            
            # Get symbol info for formatting
            symbol_info = self.bot.get_symbol_info(symbol)
            if not symbol_info:
                ws_logger.log(f"❌ Cannot get symbol info for {symbol}", 'error')
                return False
            
            # Format quantity according to requirements
            tp_qty_formatted = self.bot.format_quantity(tp_qty, symbol_info)
            if not tp_qty_formatted:
                ws_logger.log(f"❌ Error formatting quantity {tp_qty}", 'error')
                return False
            
            side = "Sell" if position_type == "long" else "Buy"
            
            # Format price with full precision
            target_price_str = f"{target_price:.8f}".rstrip('0').rstrip('.')
            
            # TP order parameters
            tp_params = {
                'category': "linear",
                'symbol': symbol,
                'side': side,
                'orderType': "Limit",
                'qty': str(tp_qty_formatted),
                'price': target_price_str,
                'positionIdx': self.bot.get_position_idx(position['position_type']),
                'reduceOnly': True,
                'timeInForce': "GTC"
            }
            
            ws_logger.log(f"📤 Setting TP{target_num} for {symbol}: {tp_params}")
            
            if self.bot.use_demo_account:
                ws_logger.log(f"🎮 DEMO: TP{target_num} {symbol} @ {target_price_str}")
                tp_response = {
                    'retCode': 0,
                    'retMsg': 'Demo TP order simulated',
                    'result': {
                        'orderId': f'DEMO_TP{target_num}_{symbol}_{int(time.time())}',
                        'orderLinkId': f'demo_tp_{target_num}'
                    }
                }
            else:
                ws_logger.log(f"💰 LIVE: TP{target_num} {symbol} @ {target_price_str}")
                tp_response = self.bot.bybit_client.place_order(**tp_params)
            
            if tp_response.get('retCode') == 0:
                tp_order_id = tp_response.get('result', {}).get('orderId')
                position['tp_orders'][target_num] = tp_order_id
                ws_logger.log(f"✅ TP{target_num} set for {symbol}: Order ID {tp_order_id}", 'success')
                return True
            else:
                error_msg = tp_response.get('retMsg', 'Unknown error')
                ws_logger.log(f"❌ Error TP{target_num} for {symbol}: {error_msg}", 'error')
                return False
                
        except Exception as e:
            ws_logger.log(f"❌ Error set_take_profit for {symbol} TP{target_num}: {e}", 'error')
            return False
    
    def set_stop_loss(self, symbol, sl_price):
        """Set Stop Loss order"""
        try:
            if not self.bot.bybit_client:
                ws_logger.log("❌ No Bybit client", 'error')
                return False
            
            position = self.active_positions.get(symbol)
            if not position:
                ws_logger.log(f"❌ No position {symbol} in monitoring", 'error')
                return False
            
            # Validate SL
            entry_price = position['entry_price']
            position_type = position['position_type'].lower()
            
            ws_logger.log(f"🔍 Validating SL for {symbol}:")
            ws_logger.log(f"   📊 Position: {position_type.upper()}")
            ws_logger.log(f"   💰 Entry: {entry_price}")
            ws_logger.log(f"   🛑 SL: {sl_price}")
            
            # Logical validation
            if position_type == "long":
                if sl_price >= entry_price:
                    error_msg = f"❌ ERROR SL for LONG {symbol}: SL ({sl_price}) >= Entry ({entry_price})"
                    ws_logger.log(error_msg, 'error')
                    ws_logger.log("💡 For LONG: Stop Loss must be BELOW entry price!", 'warning')
                    return False
            elif position_type == "short":
                if sl_price <= entry_price:
                    error_msg = f"❌ ERROR SL for SHORT {symbol}: SL ({sl_price}) <= Entry ({entry_price})"
                    ws_logger.log(error_msg, 'error')
                    ws_logger.log("💡 For SHORT: Stop Loss must be ABOVE entry price!", 'warning')
                    return False
            
            ws_logger.log(f"✅ SL validation PASSED for {position_type.upper()} {symbol}", 'success')
            
            # Get current position size
            current_position_size = self.get_current_position_size(symbol)
            if not current_position_size or current_position_size <= 0:
                ws_logger.log(f"❌ No current position for {symbol}", 'error')
                return False
            
            # METHOD 1: Set Trading Stop (recommended for SL)
            success = self.set_trading_stop(symbol, sl_price, position_type)
            if success:
                return True
            
            # METHOD 2: Fallback - conditional order "Stop"  
            ws_logger.log(f"🔄 Fallback: conditional Stop order for {symbol}", 'warning')
            return self.set_conditional_stop(symbol, sl_price, current_position_size, position_type)
                
        except Exception as e:
            ws_logger.log(f"❌ Error set_stop_loss for {symbol}: {e}", 'error')
            return False
    
    def set_trading_stop(self, symbol, sl_price, position_type):
        """Set Trading Stop"""
        try:
            # Format price with full precision
            sl_price_str = f"{sl_price:.8f}".rstrip('0').rstrip('.')
            
            trading_stop_params = {
                'category': "linear",
                'symbol': symbol,
                'stopLoss': sl_price_str,
                'positionIdx': self.bot.get_position_idx(position_type)
            }
            
            ws_logger.log(f"📤 Set Trading Stop for {symbol}: {trading_stop_params}")
            
            if self.bot.use_demo_account:
                ws_logger.log(f"🎮 DEMO: Trading Stop {symbol} @ {sl_price_str}")
                response = {
                    'retCode': 0,
                    'retMsg': 'Demo trading stop set',
                    'result': {}
                }
            else:
                ws_logger.log(f"💰 LIVE: Trading Stop {symbol} @ {sl_price_str}")
                response = self.bot.bybit_client.set_trading_stop(**trading_stop_params)
            
            if response.get('retCode') == 0:
                position = self.active_positions[symbol]
                position['sl_order_id'] = f'TRADING_STOP_{symbol}'
                ws_logger.log(f"✅ Trading Stop set for {symbol} @ {sl_price_str}", 'success')
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                ws_logger.log(f"❌ Trading Stop error for {symbol}: {error_msg}", 'error')
                return False
                
        except Exception as e:
            ws_logger.log(f"❌ Error set_trading_stop for {symbol}: {e}", 'error')
            return False
    
    def set_conditional_stop(self, symbol, sl_price, position_size, position_type):
        """Conditional Stop Order (fallback)"""
        try:
            side = "Sell" if position_type == "long" else "Buy"
            
            # Format price with full precision
            sl_price_str = f"{sl_price:.8f}".rstrip('0').rstrip('.')
            position_size_str = str(position_size)
            
            # Parameters for Bybit Linear
            stop_params = {
                'category': "linear",
                'symbol': symbol,
                'side': side,
                'orderType': "Stop",
                'qty': position_size_str,
                'stopPrice': sl_price_str,
                'positionIdx': self.bot.get_position_idx(position_type),
                'reduceOnly': True,
                'timeInForce': "GTC",
                'triggerDirection': 1 if position_type == "long" else 2
            }
            
            ws_logger.log(f"📤 Conditional Stop for {symbol}: {stop_params}")
            
            if self.bot.use_demo_account:
                ws_logger.log(f"🎮 DEMO: Conditional Stop {symbol} @ {sl_price_str}")
                response = {
                    'retCode': 0,
                    'retMsg': 'Demo conditional stop simulated',
                    'result': {'orderId': f'DEMO_STOP_{symbol}_{int(time.time())}'}
                }
            else:
                ws_logger.log(f"💰 LIVE: Conditional Stop {symbol} @ {sl_price_str}")
                response = self.bot.bybit_client.place_order(**stop_params)
            
            if response.get('retCode') == 0:
                sl_order_id = response.get('result', {}).get('orderId', 'CONDITIONAL_STOP')
                position = self.active_positions[symbol]
                position['sl_order_id'] = sl_order_id
                ws_logger.log(f"✅ Conditional Stop set for {symbol}: {sl_order_id}", 'success')
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                ws_logger.log(f"❌ Conditional Stop error for {symbol}: {error_msg}", 'error')
                return False
                
        except Exception as e:
            ws_logger.log(f"❌ Error set_conditional_stop for {symbol}: {e}", 'error')
            return False
    
    def cancel_sl_order(self, symbol, order_id):
        """Cancel Stop Loss order"""
        try:
            if not self.bot.bybit_client:
                ws_logger.log("❌ No Bybit client", 'error')
                return False
            
            # Check if it's trading stop or conditional order
            if order_id.startswith('TRADING_STOP_'):
                ws_logger.log(f"🗑️ Canceling Trading Stop for {symbol}")
                return self.cancel_trading_stop(symbol)
            else:
                ws_logger.log(f"🗑️ Canceling conditional order: {order_id}")
                return self.cancel_order(symbol, order_id)
                
        except Exception as e:
            ws_logger.log(f"❌ Error cancel_sl_order for {symbol}: {e}", 'error')
            return False
    
    def cancel_trading_stop(self, symbol):
        """Cancel Trading Stop"""
        try:
            position = self.active_positions.get(symbol)
            if not position:
                return False
            
            position_type = position['position_type']
            
            # Remove trading stop by setting empty stopLoss
            trading_stop_params = {
                'category': "linear",
                'symbol': symbol,
                'stopLoss': "",  # Empty string removes SL
                'positionIdx': self.bot.get_position_idx(position_type)
            }
            
            ws_logger.log(f"📤 Removing Trading Stop for {symbol}")
            
            if self.bot.use_demo_account:
                ws_logger.log(f"🎮 DEMO: Removing Trading Stop {symbol}")
                response = {
                    'retCode': 0,
                    'retMsg': 'Demo trading stop removed',
                    'result': {}
                }
            else:
                ws_logger.log(f"💰 LIVE: Removing Trading Stop {symbol}")
                response = self.bot.bybit_client.set_trading_stop(**trading_stop_params)
            
            if response.get('retCode') == 0:
                ws_logger.log(f"✅ Trading Stop removed for {symbol}", 'success')
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                ws_logger.log(f"❌ Error removing Trading Stop for {symbol}: {error_msg}", 'error')
                return False
                
        except Exception as e:
            ws_logger.log(f"❌ Error cancel_trading_stop for {symbol}: {e}", 'error')
            return False
    
    def cancel_order(self, symbol, order_id):
        """Cancel order"""
        try:
            if not self.bot.bybit_client:
                return False
            
            if self.bot.use_demo_account:
                ws_logger.log(f"🎮 DEMO: Simulating cancel {order_id}")
                return True
            
            cancel_params = {
                'category': "linear",
                'symbol': symbol,
                'orderId': order_id
            }
            
            ws_logger.log(f"📤 Canceling order {order_id} for {symbol}")
            response = self.bot.bybit_client.cancel_order(**cancel_params)
            
            if response.get('retCode') == 0:
                ws_logger.log(f"✅ Order {order_id} canceled", 'success')
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                ws_logger.log(f"⚠️ Cancel {order_id}: {error_msg}", 'warning')
                return True
                
        except Exception as e:
            ws_logger.log(f"❌ Error cancel_order: {e}", 'error')
            return False
    
    def get_current_position_size(self, symbol):
        """Get current position size"""
        try:
            if not self.bot.bybit_client:
                ws_logger.log(f"❌ No Bybit client for {symbol}", 'error')
                return 0
            
            if self.bot.use_demo_account:
                # For demo return simulated size
                position = self.active_positions.get(symbol)
                if position:
                    # Calculate based on entry price and trading parameters
                    entry_price = position['entry_price']
                    amount_to_use = self.bot.default_amount
                    
                    if self.bot.use_percentage:
                        # Get balance and calculate
                        balance_info = self.bot.get_wallet_balance()
                        if balance_info and balance_info.get('success'):
                            available = balance_info.get('totalAvailableBalance', 0)
                            amount_to_use = available * (self.bot.default_amount / 100.0)
                    
                    # Calculate position size
                    position_value_usdt = amount_to_use * self.bot.default_leverage
                    qty = position_value_usdt / entry_price
                    
                    # Format according to symbol requirements
                    symbol_info = self.bot.get_symbol_info(symbol)
                    if symbol_info:
                        qty_formatted = self.bot.format_quantity(qty, symbol_info)
                        return qty_formatted if qty_formatted else 0
                    
                    return round(qty, 6)
                return 0
            
            # Get real position from API
            try:
                positions_response = self.bot.bybit_client.get_positions(
                    category="linear",
                    symbol=symbol
                )
                
                if positions_response.get('retCode') == 0:
                    position_list = positions_response.get('result', {}).get('list', [])
                    
                    for pos in position_list:
                        if pos.get('symbol') == symbol:
                            size = float(pos.get('size', '0'))
                            if size > 0:
                                ws_logger.log(f"📊 Current position {symbol}: {size}")
                                return size
                    
                    ws_logger.log(f"⚠️ No active position for {symbol}", 'warning')
                    return 0
                else:
                    error_msg = positions_response.get('retMsg', 'Unknown error')
                    ws_logger.log(f"❌ Error getting position {symbol}: {error_msg}", 'error')
                    return 0
                    
            except Exception as e:
                ws_logger.log(f"❌ API error get_positions for {symbol}: {e}", 'error')
                return 0
                
        except Exception as e:
            ws_logger.log(f"❌ Error get_current_position_size for {symbol}: {e}", 'error')
            return 0
    
    def get_current_price(self, symbol):
        """Get current symbol price"""
        try:
            if not self.bot.bybit_client:
                return None
            
            if self.bot.use_demo_account:
                # In demo mode simulate price close to entry price
                position = self.active_positions.get(symbol)
                if position:
                    entry_price = position['entry_price']
                    # Simulate slight fluctuations (±2%)
                    import random
                    variation = random.uniform(-0.02, 0.02)
                    simulated_price = entry_price * (1 + variation)
                    return round(simulated_price, 8)
                return None
            
            # Get real price from API
            try:
                ticker_response = self.bot.bybit_client.get_tickers(
                    category="linear",
                    symbol=symbol
                )
                
                if ticker_response.get('retCode') == 0:
                    ticker_list = ticker_response.get('result', {}).get('list', [])
                    
                    if ticker_list:
                        ticker = ticker_list[0]
                        last_price = float(ticker.get('lastPrice', '0'))
                        return last_price
                    
                return None
                
            except Exception as e:
                ws_logger.log(f"❌ API error get_tickers for {symbol}: {e}", 'error')
                return None
                
        except Exception as e:
            ws_logger.log(f"❌ Error get_current_price for {symbol}: {e}", 'error')
            return None
    
    def check_filled_orders(self, symbol):
        """Check filled orders"""
        try:
            if symbol not in self.active_positions:
                return
            
            position = self.active_positions[symbol]
            
            # Check targets based on current price
            price_check_result = self.check_target_reached_by_price(symbol)
            if price_check_result:
                ws_logger.log(f"✅ New targets detected by price check for {symbol}", 'success')
            
            # Check TP orders (as backup)
            for target_num, order_id in position['tp_orders'].items():
                if target_num not in position['filled_targets']:
                    if self.is_order_filled(symbol, order_id):
                        position['filled_targets'].add(target_num)
                        ws_logger.log(f"🎯 TP{target_num} reached for {symbol} (by order status)!", 'success')
                        
                        # If it's trigger target, move SL to breakeven
                        breakeven_target = position.get('breakeven_target', 1)
                        if target_num == breakeven_target and not position['sl_moved_to_breakeven'] and self.bot.auto_breakeven:
                            ws_logger.log(f"💡 Target {breakeven_target} by order - activating breakeven for {symbol}")
                            self.move_sl_to_breakeven(symbol)
            
            # Check SL
            if position['sl_order_id']:
                if self.is_order_filled(symbol, position['sl_order_id']):
                    ws_logger.log(f"🛑 Stop Loss executed for {symbol}")
                    self.remove_position(symbol)
                    
        except Exception as e:
            ws_logger.log(f"❌ Error check_filled_orders for {symbol}: {e}", 'error')
    
    def is_order_filled(self, symbol, order_id):
        """Check if order is filled"""
        try:
            if not self.bot.bybit_client:
                return False
            
            if self.bot.use_demo_account:
                # For demo check price
                return self.simulate_order_fill_improved(symbol, order_id)
            
            # Check order status in live
            try:
                order_history = self.bot.bybit_client.get_order_history(
                    category="linear",
                    symbol=symbol,
                    orderId=order_id
                )
                
                if order_history.get('retCode') == 0:
                    orders = order_history.get('result', {}).get('list', [])
                    for order in orders:
                        if order.get('orderId') == order_id:
                            status = order.get('orderStatus')
                            if status in ['Filled', 'PartiallyFilled']:
                                ws_logger.log(f"✅ Order {order_id} filled (status: {status})", 'success')
                                return True
                            else:
                                ws_logger.log(f"⏳ Order {order_id} status: {status}")
                                return False
                
                return False
                
            except Exception as e:
                ws_logger.log(f"❌ Error checking order status {order_id}: {e}", 'error')
                return False
            
        except Exception as e:
            ws_logger.log(f"❌ Error is_order_filled: {e}", 'error')
            return False
    
    def simulate_order_fill_improved(self, symbol, order_id):
        """Improved order fill simulation for demo"""
        try:
            if symbol not in self.active_positions:
                return False
            
            position = self.active_positions[symbol]
            targets = position.get('targets', {})
            current_price = self.get_current_price(symbol)
            
            if not current_price:
                return False
            
            # Check if it's TP order
            for target_num, tp_order_id in position['tp_orders'].items():
                if tp_order_id == order_id:
                    target_price = targets.get(target_num)
                    if target_price:
                        position_type = position['position_type'].lower()
                        
                        # Check if target reached
                        if position_type == "long" and current_price >= target_price:
                            ws_logger.log(f"🎮 DEMO: TP{target_num} simulated fill @ {current_price}")
                            return True
                        elif position_type == "short" and current_price <= target_price:
                            ws_logger.log(f"🎮 DEMO: TP{target_num} simulated fill @ {current_price}")
                            return True
            
            # Check if it's SL
            if position['sl_order_id'] == order_id and position.get('stop_loss'):
                sl_price = position['stop_loss']
                position_type = position['position_type'].lower()
                
                if position_type == "long" and current_price <= sl_price:
                    ws_logger.log(f"🎮 DEMO: SL simulated fill @ {current_price}")
                    return True
                elif position_type == "short" and current_price >= sl_price:
                    ws_logger.log(f"🎮 DEMO: SL simulated fill @ {current_price}")
                    return True
            
            return False
            
        except Exception as e:
            ws_logger.log(f"❌ Error simulate_order_fill_improved: {e}", 'error')
            return False
    
    def remove_position(self, symbol):
        """Remove position from monitoring"""
        try:
            if symbol in self.active_positions:
                del self.active_positions[symbol]
                ws_logger.log(f"✅ Position {symbol} removed from monitoring", 'success')
                
                # Emit position update via Socket.IO
                socketio.emit('message', {
                    'type': 'position',
                    'action': 'removed',
                    'symbol': symbol
                })
        except Exception as e:
            ws_logger.log(f"❌ Error remove_position: {e}", 'error')
    
    def start_monitoring(self):
        """Start position monitoring"""
        if not self.monitoring_active:
            self.monitoring_active = True
            self.monitor_thread = threading.Thread(target=self._monitor_positions, daemon=True)
            self.monitor_thread.start()
            ws_logger.log("✅ Position monitoring started", 'success')
            
            # Emit status update
            socketio.emit('status_update', {'monitoring': True})
    
    def stop_monitoring(self):
        """Stop position monitoring"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
        ws_logger.log("🛑 Position monitoring stopped")
        
        # Emit status update
        socketio.emit('status_update', {'monitoring': False})
    
    def _monitor_positions(self):
        """Position monitoring thread"""
        ws_logger.log("🔄 Position monitoring thread started")
        
        while self.monitoring_active:
            try:
                active_symbols = list(self.active_positions.keys())
                
                if active_symbols:
                    ws_logger.log(f"👀 Monitoring {len(active_symbols)} positions: {', '.join(active_symbols)}")
                    
                    for symbol in active_symbols:
                        try:
                            self.check_filled_orders(symbol)
                            
                            # Additional logging for debugging
                            position = self.active_positions.get(symbol)
                            if position:
                                filled_count = len(position.get('filled_targets', set()))
                                total_targets = len(position.get('targets', {}))
                                breakeven_status = "✅" if position.get('sl_moved_to_breakeven') else "❌"
                                breakeven_trigger = position.get('breakeven_target', 1)
                                
                                ws_logger.log(f"📊 {symbol}: Targets {filled_count}/{total_targets}, Breakeven {breakeven_status} (trigger: TP{breakeven_trigger})")
                                
                        except Exception as e:
                            ws_logger.log(f"❌ Monitoring error {symbol}: {e}", 'error')
                            continue
                else:
                    ws_logger.log("💤 No positions to monitor")
                
                # Check every 15 seconds
                time.sleep(15)
                
            except Exception as e:
                ws_logger.log(f"❌ Error in main monitoring loop: {e}", 'error')
                time.sleep(60)  # Wait longer on error
        
        ws_logger.log("🛑 Position monitoring thread ended")
    
    def get_positions_summary(self):
        """Get positions summary"""
        summary = []
        for symbol, position in self.active_positions.items():
            filled_targets = len(position['filled_targets'])
            total_targets = len(position['targets'])
            
            # Additional info
            last_price = position.get('last_price_check', 'Unknown')
            check_count = position.get('target_check_count', 0)
            breakeven_trigger = position.get('breakeven_target', 1)
            
            summary.append({
                'symbol': symbol,
                'type': position['position_type'],
                'entry': position['entry_price'],
                'targets': f"{filled_targets}/{total_targets}",
                'sl_breakeven': position['sl_moved_to_breakeven'],
                'created': position['created_at'].strftime('%H:%M:%S'),
                'last_price': last_price,
                'checks': check_count,
                'breakeven_trigger': f"TP{breakeven_trigger}"
            })
        
        return summary


class TelegramTradingBot:
    """ENHANCED Trading Bot with improved Bybit connection and risk management"""
    
    def __init__(self):
        print("🚀 Initializing bot...")
        self.config = self.load_config()
        self.profile_manager = ProfileManager()
        self.risk_manager = EnhancedRiskManager()  # Enhanced version
        self.position_manager = PositionManager(self)
        self.forwarder = TelegramForwarder(self)
        
        # Telegram
        self.telegram_token = self.config.get('Telegram', 'token', fallback='')
        self.telegram_chat_id = self.config.get('Telegram', 'chat_id', fallback='')
        
        # Bybit API
        self.bybit_api_key = self.config.get('Bybit', 'api_key', fallback='')
        self.bybit_api_secret = self.config.get('Bybit', 'api_secret', fallback='')
        self.bybit_subaccount = self.config.get('Bybit', 'subaccount', fallback='')
        self.bybit_platform = self.config.get('Bybit', 'platform', fallback='bybitglobal')
        self.position_mode = self.config.get('Bybit', 'position_mode', fallback='one_way')
        
        # Trading settings
        self.default_leverage = int(self.config.get('Trading', 'default_leverage', fallback='10'))
        self.default_amount = float(self.config.get('Trading', 'default_amount', fallback='100'))
        self.use_percentage = self.config.get('Trading', 'use_percentage', fallback='False').lower() == 'true'
        self.use_demo_account = self.config.get('Trading', 'use_demo_account', fallback='True').lower() == 'true'
        
        # Trading settings with risk control
        self.max_position_size = float(self.config.get('Trading', 'max_position_size', fallback='1000'))
        self.risk_percent = float(self.config.get('Trading', 'risk_percent', fallback='2'))
        
        # TP/SL settings - ENHANCED
        self.auto_tp_sl = self.config.get('Trading', 'auto_tp_sl', fallback='True').lower() == 'true'
        self.auto_breakeven = self.config.get('Trading', 'auto_breakeven', fallback='True').lower() == 'true'
        self.breakeven_after_target = int(self.config.get('Trading', 'breakeven_after_target', fallback='1'))
        
        # Risk Management Settings - ENHANCED
        self.daily_loss_limit = float(self.config.get('RiskManagement', 'daily_loss_limit', fallback='500'))
        self.weekly_loss_limit = float(self.config.get('RiskManagement', 'weekly_loss_limit', fallback='2000'))
        self.max_consecutive_losses = int(self.config.get('RiskManagement', 'max_consecutive_losses', fallback='3'))
        self.risk_management_enabled = self.config.get('RiskManagement', 'enabled', fallback='True').lower() == 'true'
        self.min_margin_level = float(self.config.get('RiskManagement', 'min_margin_level', fallback='1.5'))  # NEW
        
        # Telegram Bot settings
        self.auto_execute_signals = self.config.get('Trading', 'auto_execute_signals', fallback='False').lower() == 'true'
        
        # Initialize clients
        self.bybit_client = None
        self.telegram_bot = None
        self.telegram_app = None
        self.telegram_thread = None
        
        # State
        self.last_signal = None
        self.telegram_running = False
        
        print("✅ Bot initialized")
    
    # === TELEGRAM BOT METHODS ===
    
    async def telegram_message_handler(self, update: Update, context: CallbackContext):
        """Handle Telegram messages"""
        try:
            if not update.message or not update.message.text:
                return
            
            message_text = update.message.text
            chat_id = str(update.message.chat_id)
            
            # Check if message is from allowed chat_id
            if self.telegram_chat_id and chat_id != self.telegram_chat_id:
                ws_logger.log(f"🚫 Message from unauthorized chat_id: {chat_id}", 'warning')
                return
            
            ws_logger.log(f"📨 Received message from Telegram (Chat ID: {chat_id})")
            ws_logger.log(f"📋 Content: {message_text[:100]}...")
            
            # Try to parse as trading signal
            signal = self.parse_trading_signal(message_text)
            
            if signal:
                ws_logger.log(f"✅ Signal recognized: {signal['symbol']} {signal['position_type']}", 'success')
                
                # Auto-execute if enabled
                if self.auto_execute_signals:
                    try:
                        if not self.bybit_client:
                            await self.send_telegram_message(f"❌ No Bybit API connection")
                            return
                        
                        # Execute trade
                        result = self.execute_trade(signal)
                        await self.send_telegram_message(f"🤖 Auto-trade:\n{result}")
                        
                    except Exception as e:
                        error_msg = f"❌ Auto-trade error: {str(e)}"
                        ws_logger.log(error_msg, 'error')
                        await self.send_telegram_message(error_msg)
                else:
                    # Just notification about recognized signal
                    await self.send_telegram_message(
                        f"✅ Signal recognized:\n"
                        f"📊 {signal['symbol']} {signal['position_type'].upper()}\n"
                        f"💰 Entry: {signal['entry_price']}\n"
                        f"🎯 Targets: {len(signal['targets'])}\n"
                        f"🛑 SL: {signal['stop_loss'] or 'None'}\n\n"
                        f"⚠️ Auto-trade disabled - execute manually"
                    )
            else:
                ws_logger.log(f"ℹ️ Message is not a trading signal")
                
        except Exception as e:
            ws_logger.log(f"❌ Error handling Telegram message: {e}", 'error')

    async def send_telegram_message(self, text):
        """Send message via Telegram"""
        try:
            if not self.telegram_bot or not self.telegram_chat_id:
                ws_logger.log("⚠️ No Telegram configuration", 'warning')
                return False
            
            await self.telegram_bot.send_message(
                chat_id=self.telegram_chat_id,
                text=text,
                parse_mode='Markdown'
            )
            return True
            
        except Exception as e:
            ws_logger.log(f"❌ Error sending message: {e}", 'error')
            return False

    def start_telegram_bot(self):
        """Start Telegram bot"""
        try:
            if not self.telegram_token:
                ws_logger.log("⚠️ No Telegram token - bot won't start", 'warning')
                return False
            
            if self.telegram_running:
                ws_logger.log("⚠️ Telegram bot already running", 'warning')
                return True
            
            ws_logger.log("🤖 Starting Telegram bot...")
            
            # Create Telegram application
            self.telegram_app = Application.builder().token(self.telegram_token).build()
            
            # Add message handler
            message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, self.telegram_message_handler)
            self.telegram_app.add_handler(message_handler)
            
            # Create bot instance for forwarder
            self.telegram_bot = Bot(self.telegram_token)
            
            # Run in separate thread
            self.telegram_thread = threading.Thread(
                target=self._run_telegram_bot,
                daemon=True
            )
            self.telegram_thread.start()
            
            self.telegram_running = True
            
            # Emit status update via Socket.IO
            socketio.emit('status_update', {'telegram_bot': True})
            
            ws_logger.log("✅ Telegram bot started", 'success')
            return True
            
        except Exception as e:
            ws_logger.log(f"❌ Error starting Telegram bot: {e}", 'error')
            return False

    def _run_telegram_bot(self):
        """Run bot in event loop"""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run polling
            self.telegram_app.run_polling(
                poll_interval=1.0,
                timeout=10,
                drop_pending_updates=True
            )
            
        except Exception as e:
            ws_logger.log(f"❌ Error in Telegram thread: {e}", 'error')
            self.telegram_running = False
            # Emit status update
            socketio.emit('status_update', {'telegram_bot': False})

    def stop_telegram_bot(self):
        """Stop Telegram bot"""
        try:
            if not self.telegram_running:
                return True
            
            ws_logger.log("🛑 Stopping Telegram bot...")
            
            self.telegram_running = False
            
            if self.telegram_app:
                # Stop application
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Stop the application properly
                    loop.run_until_complete(self.telegram_app.stop())
                    loop.run_until_complete(self.telegram_app.shutdown())
                except Exception as e:
                    ws_logger.log(f"⚠️ Error during stop: {e}", 'warning')
                finally:
                    loop.close()
            
            # Wait for thread to finish
            if self.telegram_thread and self.telegram_thread.is_alive():
                self.telegram_thread.join(timeout=5)
            
            self.telegram_bot = None
            self.telegram_app = None
            
            # Emit status update via Socket.IO
            socketio.emit('status_update', {'telegram_bot': False})
            
            ws_logger.log("✅ Telegram bot stopped", 'success')
            return True
            
        except Exception as e:
            ws_logger.log(f"❌ Error stopping bot: {e}", 'error')
            return False

    def get_telegram_chat_id(self):
        """Automatically get Chat ID"""
        try:
            if not self.telegram_token:
                return None
            
            # Get updates
            url = f"https://api.telegram.org/bot{self.telegram_token}/getUpdates"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('result'):
                    # Take last chat_id
                    last_update = data['result'][-1]
                    chat_id = last_update.get('message', {}).get('chat', {}).get('id')
                    
                    if chat_id:
                        ws_logger.log(f"📱 Found Chat ID: {chat_id}", 'success')
                        return str(chat_id)
            
            return None
            
        except Exception as e:
            ws_logger.log(f"❌ Error getting Chat ID: {e}", 'error')
            return None
    
    # === CONFIGURATION METHODS ===
        
    def load_config(self):
        """Load configuration from file"""
        config = configparser.ConfigParser()
        
        if os.path.exists(CONFIG_FILE):
            try:
                config.read(CONFIG_FILE, encoding='utf-8')
                print("✅ Configuration loaded")
            except Exception as e:
                print(f"⚠️ Error loading configuration: {e}")
        else:
            print("🔄 Creating new configuration...")
            config['Telegram'] = {
                'token': '',
                'chat_id': ''
            }
            config['Bybit'] = {
                'api_key': '',
                'api_secret': '',
                'subaccount': '',
                'platform': 'bybitglobal',
                'position_mode': 'one_way'
            }
            config['Trading'] = {
                'default_leverage': '10',
                'default_amount': '100',
                'use_percentage': 'False',
                'use_demo_account': 'True',
                'auto_tp_sl': 'True',
                'auto_breakeven': 'True',
                'breakeven_after_target': '1',
                'auto_execute_signals': 'False',
                'max_position_size': '1000',
                'risk_percent': '2'
            }
            config['RiskManagement'] = {
                'enabled': 'True',
                'daily_loss_limit': '500',
                'weekly_loss_limit': '2000', 
                'max_consecutive_losses': '3',
                'min_margin_level': '1.5'
            }
            config['Forwarder'] = {
                'api_id': '',
                'api_hash': '',
                'phone_number': '',
                'target_chat_id': '',
                'forward_all_messages': 'False',
                'monitored_channels': '[]'
            }
            
            try:
                with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                    config.write(configfile)
                print("✅ New configuration created")
            except Exception as e:
                print(f"❌ Error creating configuration: {e}")
        
        return config
    
    def save_config(self):
        """Save configuration to file"""
        try:
            # Save values to config sections
            self.config['Telegram']['token'] = self.telegram_token
            self.config['Telegram']['chat_id'] = self.telegram_chat_id
            self.config['Bybit']['api_key'] = self.bybit_api_key
            self.config['Bybit']['api_secret'] = self.bybit_api_secret
            self.config['Bybit']['subaccount'] = self.bybit_subaccount
            self.config['Bybit']['platform'] = self.bybit_platform
            self.config['Bybit']['position_mode'] = self.position_mode
            self.config['Trading']['default_leverage'] = str(self.default_leverage)
            self.config['Trading']['default_amount'] = str(self.default_amount)
            self.config['Trading']['use_percentage'] = str(self.use_percentage)
            self.config['Trading']['use_demo_account'] = str(self.use_demo_account)
            self.config['Trading']['auto_tp_sl'] = str(self.auto_tp_sl)
            self.config['Trading']['auto_breakeven'] = str(self.auto_breakeven)
            self.config['Trading']['breakeven_after_target'] = str(self.breakeven_after_target)
            self.config['Trading']['auto_execute_signals'] = str(self.auto_execute_signals)
            self.config['Trading']['max_position_size'] = str(self.max_position_size)
            self.config['Trading']['risk_percent'] = str(self.risk_percent)
            
            # Risk Management
            if not self.config.has_section('RiskManagement'):
                self.config.add_section('RiskManagement')
            self.config['RiskManagement']['enabled'] = str(self.risk_management_enabled)
            self.config['RiskManagement']['daily_loss_limit'] = str(self.daily_loss_limit)
            self.config['RiskManagement']['weekly_loss_limit'] = str(self.weekly_loss_limit)
            self.config['RiskManagement']['max_consecutive_losses'] = str(self.max_consecutive_losses)
            self.config['RiskManagement']['min_margin_level'] = str(self.min_margin_level)
            
            # Save to file
            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                self.config.write(configfile)
            
            ws_logger.log("✅ Configuration saved", 'success')
            return True
        except Exception as e:
            ws_logger.log(f"❌ Error saving configuration: {e}", 'error')
            return False
    
    def save_current_as_profile(self, profile_name):
        """Save current configuration as profile"""
        try:
            profile_data = {
                'telegram_token': self.telegram_token,
                'telegram_chat_id': self.telegram_chat_id,
                'bybit_api_key': self.bybit_api_key,
                'bybit_api_secret': self.bybit_api_secret,
                'bybit_subaccount': self.bybit_subaccount,
                'bybit_platform': self.bybit_platform,
                'position_mode': self.position_mode,
                'default_leverage': self.default_leverage,
                'default_amount': self.default_amount,
                'use_percentage': self.use_percentage,
                'use_demo_account': self.use_demo_account,
                'auto_tp_sl': self.auto_tp_sl,
                'auto_breakeven': self.auto_breakeven,
                'breakeven_after_target': self.breakeven_after_target,
                'auto_execute_signals': self.auto_execute_signals,
                'max_position_size': self.max_position_size,
                'risk_percent': self.risk_percent,
                'risk_management_enabled': self.risk_management_enabled,
                'daily_loss_limit': self.daily_loss_limit,
                'weekly_loss_limit': self.weekly_loss_limit,
                'max_consecutive_losses': self.max_consecutive_losses,
                'min_margin_level': self.min_margin_level
            }
            
            return self.profile_manager.save_profile(profile_name, profile_data)
        except Exception as e:
            ws_logger.log(f"❌ Error saving profile: {e}", 'error')
            return False
    
    def load_profile(self, profile_name):
        """Load profile"""
        try:
            profile_data = self.profile_manager.load_profile(profile_name)
            if not profile_data:
                return False
            
            self.telegram_token = profile_data.get('telegram_token', '')
            self.telegram_chat_id = profile_data.get('telegram_chat_id', '')
            self.bybit_api_key = profile_data.get('bybit_api_key', '')
            self.bybit_api_secret = profile_data.get('bybit_api_secret', '')
            self.bybit_subaccount = profile_data.get('bybit_subaccount', '')
            self.bybit_platform = profile_data.get('bybit_platform', 'bybitglobal')
            self.position_mode = profile_data.get('position_mode', 'one_way')
            self.default_leverage = profile_data.get('default_leverage', 10)
            self.default_amount = profile_data.get('default_amount', 100)
            self.use_percentage = profile_data.get('use_percentage', False)
            self.use_demo_account = profile_data.get('use_demo_account', True)
            self.auto_tp_sl = profile_data.get('auto_tp_sl', True)
            self.auto_breakeven = profile_data.get('auto_breakeven', True)
            self.breakeven_after_target = profile_data.get('breakeven_after_target', 1)
            self.auto_execute_signals = profile_data.get('auto_execute_signals', False)
            self.max_position_size = profile_data.get('max_position_size', 1000)
            self.risk_percent = profile_data.get('risk_percent', 2)
            self.risk_management_enabled = profile_data.get('risk_management_enabled', True)
            self.daily_loss_limit = profile_data.get('daily_loss_limit', 500)
            self.weekly_loss_limit = profile_data.get('weekly_loss_limit', 2000)
            self.max_consecutive_losses = profile_data.get('max_consecutive_losses', 3)
            self.min_margin_level = profile_data.get('min_margin_level', 1.5)
            
            # Reset client after loading profile
            self.bybit_client = None
            
            return True
        except Exception as e:
            ws_logger.log(f"❌ Error loading profile: {e}", 'error')
            return False
    
    def test_api_keys_simple(self):
        """Simple API keys test"""
        try:
            api_key = self.bybit_api_key.strip()
            api_secret = self.bybit_api_secret.strip()
            
            if not api_key or not api_secret:
                ws_logger.log("❌ No API keys", 'error')
                return False
            
            timestamp = str(int(time.time() * 1000))
            param_str = f"{timestamp}GET/v5/market/time"
            
            signature = hmac.new(
                api_secret.encode('utf-8'),
                param_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            headers = {
                'X-BAPI-API-KEY': api_key,
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-SIGN': signature
            }
            
            ws_logger.log("🧪 Running simple HTTP test...")
            response = requests.get('https://api.bybit.com/v5/market/time', headers=headers, timeout=10)
            result = response.json()
            
            if result.get('retCode') == 0:
                ws_logger.log("✅ Simple HTTP test successful", 'success')
                return True
            else:
                ws_logger.log(f"❌ Simple HTTP test failed: {result.get('retMsg', 'Unknown error')}", 'error')
                return False
                
        except Exception as e:
            ws_logger.log(f"❌ HTTP test failed: {e}", 'error')
            return False
    
    def initialize_bybit_client(self):
        try:
            ws_logger.log("🚀 Starting Bybit client initialization...")
        
        # DEBUG: Log configuration state
            ws_logger.log(f"DEBUG: API key exists: {bool(self.bybit_api_key)}")
            ws_logger.log(f"DEBUG: API secret exists: {bool(self.bybit_api_secret)}")
            ws_logger.log(f"DEBUG: Demo mode: {self.use_demo_account}")
        
            if not self.bybit_api_key or not self.bybit_api_secret:
                ws_logger.log("❌ Missing Bybit API keys", 'error')
                self.bybit_client = None
                return False
        
            clean_api_key = self.bybit_api_key.strip()
            clean_api_secret = self.bybit_api_secret.strip()
        
        # CRITICAL FIX: Determine correct testnet setting based on use_demo_account
            use_testnet = self.use_demo_account
        
            ws_logger.log(f"🔧 Bybit Configuration:")
            ws_logger.log(f"   🎮 Demo Mode: {self.use_demo_account}")
            ws_logger.log(f"   🌐 Use Testnet: {use_testnet}")
            ws_logger.log(f"   🔐 Position Mode: {self.position_mode}")
        
        # Create HTTP client with CORRECT testnet parameter
            ws_logger.log("📡 Creating HTTP client...")
        
            try:
                if use_testnet:
                # TESTNET - for demo trading with testnet API keys
                    ws_logger.log("🎮 Connecting to Bybit TESTNET (api-testnet.bybit.com)")
                    self.bybit_client = HTTP(
                        api_key=clean_api_key,
                        api_secret=clean_api_secret,
                        testnet=True  # MUST be True for testnet keys
                    )
                else:
                # MAINNET - for live trading with mainnet API keys
                    ws_logger.log("💰 Connecting to Bybit MAINNET (api.bybit.com)")
                    self.bybit_client = HTTP(
                        api_key=clean_api_key,
                        api_secret=clean_api_secret,
                        testnet=False  # MUST be False for mainnet keys
                    )
            
            # Test connection with server time
                ws_logger.log("🧪 Testing Bybit connection...")
                server_time = self.bybit_client.get_server_time()
            
                ws_logger.log(f"DEBUG: Server time response: {server_time}")
            
                if server_time.get('retCode') == 0:
                    endpoint = "api-testnet.bybit.com" if use_testnet else "api.bybit.com"
                    mode = "DEMO (Testnet)" if use_testnet else "LIVE (Mainnet)"
                
                    ws_logger.log(f"✅ Connected to Bybit API", 'success')
                    ws_logger.log(f"   🌐 Endpoint: {endpoint}")
                    ws_logger.log(f"   🎯 Mode: {mode}")
                
                # Try to get balance - don't fail if it doesn't work
                    try:
                        ws_logger.log("💰 Attempting to fetch balance...")
                        balance_response = self.bybit_client.get_wallet_balance(
                        accountType="UNIFIED"
                        )
                    
                        ws_logger.log(f"DEBUG: Balance response code: {balance_response.get('retCode')}")
                    
                        if balance_response.get('retCode') == 0:
                            balance_list = balance_response.get('result', {}).get('list', [])
                            if balance_list:
                                account = balance_list[0]
                                available = float(account.get('totalAvailableBalance', '0'))
                                wallet = float(account.get('totalWalletBalance', '0'))
                                ws_logger.log(f"💰 Wallet Balance: {wallet:.2f} USDT", 'success')
                                ws_logger.log(f"💵 Available Balance: {available:.2f} USDT", 'success')
                            else:
                                ws_logger.log("⚠️ Balance data empty but connection OK", 'warning')
                        elif balance_response.get('retCode') == 10001:
                        # Common error for new testnet accounts
                            ws_logger.log("⚠️ Account not activated or no balance (normal for new testnet)", 'warning')
                            ws_logger.log("💡 For testnet: Get free USDT at testnet.bybit.com", 'info')
                        elif balance_response.get('retCode') == 10003:
                            ws_logger.log("❌ Invalid API key - check if keys match the network (testnet/mainnet)", 'error')
                            return False
                        elif balance_response.get('retCode') == 10004:
                            ws_logger.log("❌ Invalid signature - check API secret", 'error')
                            return False
                        else:
                            error_msg = balance_response.get('retMsg', 'Unknown error')
                            ws_logger.log(f"⚠️ Balance fetch failed: {error_msg}", 'warning')
                        
                    except Exception as balance_error:
                        ws_logger.log(f"⚠️ Balance check failed but connection works: {balance_error}", 'warning')
                
                # Connection successful even if balance fails
                    ws_logger.log("✅ Bybit client initialized successfully", 'success')
                    return True
                else:
                    error_msg = server_time.get('retMsg', 'Unknown error')
                    error_code = server_time.get('retCode', 'Unknown')
                    ws_logger.log(f"❌ Connection failed: [{error_code}] {error_msg}", 'error')
                
                # Provide helpful error messages
                    if error_code == 10003:
                        ws_logger.log("💡 Tip: Check if your API keys match the network:", 'warning')
                        ws_logger.log(f"   - Demo mode is {self.use_demo_account}", 'warning')
                        ws_logger.log("   - Testnet keys only work on testnet", 'warning')
                        ws_logger.log("   - Mainnet keys only work on mainnet", 'warning')
                    elif error_code == 10004:
                        ws_logger.log("💡 Tip: Invalid API secret - check for typos", 'warning')
                
                    self.bybit_client = None
                    return False
                
            except Exception as e:
                ws_logger.log(f"❌ Connection test error: {e}", 'error')
                ws_logger.log(f"DEBUG: Exception details: {str(e)}", 'error')
                self.bybit_client = None
                return False
            
        except Exception as e:
            ws_logger.log(f"❌ Client initialization error: {e}", 'error')
            ws_logger.log(f"DEBUG: Outer exception: {str(e)}", 'error')
            self.bybit_client = None
            return False
    
    def get_subaccounts(self):
        """Get list of subaccounts"""
        try:
            if not self.bybit_client:
                if not self.initialize_bybit_client():
                    return []
            
            response = self.bybit_client.get_sub_account_list()
            
            if response.get('retCode') == 0:
                subaccounts = response.get('result', {}).get('subMembers', [])
                ws_logger.log(f"✅ Fetched {len(subaccounts)} subaccounts", 'success')
                return subaccounts
            else:
                ws_logger.log(f"❌ Error fetching subaccounts: {response.get('retMsg', 'Unknown error')}", 'error')
                return []
                
        except Exception as e:
            ws_logger.log(f"❌ Error get_subaccounts: {e}", 'error')
            return []
    
    def get_wallet_balance(self):
        """Get wallet balance - ENHANCED ERROR HANDLING"""
        try:
            if not self.bybit_client:
                ws_logger.log("❌ No Bybit client", 'error')
                # Try to initialize client
                if not self.initialize_bybit_client():
                    # Return demo balance if in demo mode
                    if self.use_demo_account:
                        ws_logger.log("🎮 Returning simulated demo balance", 'info')
                        return {
                            'success': True,
                            'totalMarginBalance': 10000.0,
                            'totalWalletBalance': 10000.0,
                            'totalAvailableBalance': 10000.0,
                            'accountType': 'DEMO'
                        }
                    return None
            
            ws_logger.log("💰 Fetching balance...")
            
            # Get balance - handle errors gracefully
            try:
                balance_response = None
                
                # Try UNIFIED account first
                try:
                    if self.bybit_subaccount:
                        balance_response = self.bybit_client.get_wallet_balance(
                            accountType="UNIFIED",
                            memberId=self.bybit_subaccount
                        )
                    else:
                        balance_response = self.bybit_client.get_wallet_balance(
                            accountType="UNIFIED"
                        )
                    
                    ws_logger.log(f"DEBUG: UNIFIED balance response code: {balance_response.get('retCode')}")
                    
                except Exception as unified_error:
                    ws_logger.log(f"⚠️ UNIFIED account error: {unified_error}", 'warning')
                    
                    # Try CONTRACT account as fallback
                    try:
                        balance_response = self.bybit_client.get_wallet_balance(
                            accountType="CONTRACT"
                        )
                        ws_logger.log(f"DEBUG: CONTRACT balance response code: {balance_response.get('retCode')}")
                    except Exception as contract_error:
                        ws_logger.log(f"⚠️ CONTRACT account error: {contract_error}", 'warning')
                
                # Process response if we got one
                if balance_response and balance_response.get('retCode') == 0:
                    balance_list = balance_response.get('result', {}).get('list', [])
                    
                    if balance_list:
                        account = balance_list[0]
                        
                        # Handle different account structures
                        total_margin_balance = float(account.get('totalMarginBalance', account.get('totalEquity', '0')))
                        total_wallet_balance = float(account.get('totalWalletBalance', account.get('totalEquity', '0')))
                        total_available_balance = float(account.get('totalAvailableBalance', account.get('availableBalance', '0')))
                        account_type = account.get('accountType', 'UNIFIED')
                        
                        ws_logger.log(f"✅ Balance fetched successfully", 'success')
                        ws_logger.log(f"💵 Available: {total_available_balance:.2f} USDT")
                        ws_logger.log(f"💰 Wallet: {total_wallet_balance:.2f} USDT")
                        ws_logger.log(f"📊 Margin: {total_margin_balance:.2f} USDT")
                        
                        # Emit balance update via Socket.IO
                        socketio.emit('message', {
                            'type': 'balance',
                            'balance': {
                                'totalMarginBalance': total_margin_balance,
                                'totalWalletBalance': total_wallet_balance,
                                'totalAvailableBalance': total_available_balance,
                                'accountType': account_type
                            }
                        })
                        
                        return {
                            'success': True,
                            'totalMarginBalance': total_margin_balance,
                            'totalWalletBalance': total_wallet_balance,
                            'totalAvailableBalance': total_available_balance,
                            'accountType': account_type
                        }
                
                # No valid balance response - return demo balance if in demo mode
                if self.use_demo_account:
                    ws_logger.log("🎮 Using simulated demo balance", 'info')
                    return {
                        'success': True,
                        'totalMarginBalance': 10000.0,
                        'totalWalletBalance': 10000.0,
                        'totalAvailableBalance': 10000.0,
                        'accountType': 'DEMO'
                    }
                else:
                    ws_logger.log("❌ Failed to get balance", 'error')
                    return None
                    
            except Exception as api_error:
                ws_logger.log(f"❌ Balance API error: {api_error}", 'error')
                
                # Return demo balance for demo mode
                if self.use_demo_account:
                    return {
                        'success': True,
                        'totalMarginBalance': 10000.0,
                        'totalWalletBalance': 10000.0,
                        'totalAvailableBalance': 10000.0,
                        'accountType': 'DEMO'
                    }
                return None
                
        except Exception as e:
            ws_logger.log(f"❌ Error get_wallet_balance: {e}", 'error')
            
            # Return default balance for demo mode
            if self.use_demo_account:
                return {
                    'success': True,
                    'totalMarginBalance': 10000.0,
                    'totalWalletBalance': 10000.0,
                    'totalAvailableBalance': 10000.0,
                    'accountType': 'DEMO'
                }
            return None
    
    def get_symbol_info(self, symbol):
        """Get symbol information"""
        try:
            if not self.bybit_client:
                return None
            
            instruments_response = self.bybit_client.get_instruments_info(
                category="linear",
                symbol=symbol
            )
            
            if instruments_response.get('retCode') == 0:
                instruments = instruments_response.get('result', {}).get('list', [])
                if instruments:
                    return instruments[0]
            
            return None
            
        except Exception as e:
            ws_logger.log(f"❌ Error get_symbol_info: {e}", 'error')
            return None
    
    def format_quantity(self, qty, symbol_info):
        """Format position quantity according to symbol requirements"""
        try:
            if not symbol_info:
                return None
            
            qty_filter = symbol_info.get('lotSizeFilter', {})
            qty_step = float(qty_filter.get('qtyStep', '0.001'))
            min_qty = float(qty_filter.get('minOrderQty', '0'))
            max_qty = float(qty_filter.get('maxOrderQty', '0'))
            
            # Round to multiple of qty_step
            if qty_step > 0:
                qty = round(qty / qty_step) * qty_step
            
            # Check limits
            if min_qty > 0 and qty < min_qty:
                qty = min_qty
            if max_qty > 0 and qty > max_qty:
                qty = max_qty
            
            # Determine precision
            if qty_step < 1:
                precision = len(str(qty_step).split('.')[-1])
            else:
                precision = 0
            
            return round(qty, precision)
            
        except Exception as e:
            ws_logger.log(f"❌ Error format_quantity: {e}", 'error')
            return None
    
    def get_position_idx(self, position_type):
        """Get position index based on position mode"""
        if self.position_mode == 'hedge':
            return 1 if position_type.lower() == 'long' else 2
        else:  # one_way
            return 0
    
    def parse_trading_signal(self, text):
        """Recognize and parse trading signal"""
        try:
            ws_logger.log("🔍 Analyzing text for signal...", 'info')
            
            # Remove emojis that might interfere
            text_clean = re.sub(r'[^\w\s\-\.\:,/@#]', ' ', text)
            text_clean = ' '.join(text_clean.split())
            
            # Regex patterns
            symbol_pattern = r'#?([A-Z0-9]+USDT?)\b'
            position_pattern = r'\b(LONG|SHORT|Long|Short|long|short)\b'
            entry_pattern = r'(?:Entry|entry|Wejście|ENTRY|Zone|zone|ZONE)[\s:]*([0-9]+\.?[0-9]*(?:\s*-\s*[0-9]+\.?[0-9]*)?)'
            target_pattern = r'(?:Target|target|TARGET|TP|tp|Cel|cel|CEL)[\s#]*(\d+)[\s:]*([0-9]+\.?[0-9]*)'
            sl_pattern = r'(?:Stop[\s-]?Loss|stop[\s-]?loss|SL|sl|STOP[\s-]?LOSS|Stop|stop|STOP)[\s:]*([0-9]+\.?[0-9]*)'
            
            # Find elements
            symbol_match = re.search(symbol_pattern, text_clean)
            position_match = re.search(position_pattern, text_clean)
            entry_match = re.search(entry_pattern, text_clean)
            target_matches = re.findall(target_pattern, text_clean)
            sl_match = re.search(sl_pattern, text_clean)
            
            # Log found elements
            ws_logger.log(f"📊 Symbol: {symbol_match.group(1) if symbol_match else 'Not found'}")
            ws_logger.log(f"📈 Position: {position_match.group(1) if position_match else 'Not found'}")
            ws_logger.log(f"💰 Entry: {entry_match.group(1) if entry_match else 'Not found'}")
            ws_logger.log(f"🎯 Targets: {len(target_matches)} found")
            ws_logger.log(f"🛑 Stop Loss: {sl_match.group(1) if sl_match else 'Not found'}")
            
            # Check if we have minimum required data
            if not symbol_match or not position_match or not entry_match:
                ws_logger.log("❌ Missing required signal elements", 'error')
                return None
            
            # Prepare signal data
            symbol = symbol_match.group(1).upper()
            if not symbol.endswith('USDT'):
                symbol += 'USDT'
            
            position_type = position_match.group(1).lower()
            
            # Parse entry price
            entry_str = entry_match.group(1)
            if '-' in entry_str:
                # Price range - take average
                prices = [float(p.strip()) for p in entry_str.split('-')]
                entry_price = sum(prices) / len(prices)
                ws_logger.log(f"📊 Entry range {prices[0]} - {prices[1]}, using average: {entry_price}")
            else:
                entry_price = float(entry_str)
            
            # Parse targets
            targets = {}
            for target_num, target_price in target_matches:
                targets[int(target_num)] = float(target_price)
            
            # Parse stop loss
            stop_loss = float(sl_match.group(1)) if sl_match else None
            
            # Basic validation
            if entry_price <= 0:
                ws_logger.log("❌ Invalid entry price", 'error')
                return None
            
            # Create signal object
            signal = {
                'symbol': symbol,
                'position_type': position_type,
                'entry_price': entry_price,
                'targets': targets,
                'stop_loss': stop_loss
            }
            
            ws_logger.log("✅ Signal recognized successfully!", 'success')
            ws_logger.log(f"📋 {json.dumps(signal, indent=2)}")
            
            return signal
            
        except Exception as e:
            ws_logger.log(f"❌ Error parsing signal: {e}", 'error')
            return None
    
    def analyze_trading_signal(self, signal):
        """Analyze trading signal"""
        try:
            analysis = []
            
            # Basic analysis
            analysis.append(f"\n📊 SIGNAL ANALYSIS:")
            analysis.append(f"{'=' * 40}")
            
            # Risk/Reward if SL exists
            if signal['stop_loss']:
                entry = signal['entry_price']
                sl = signal['stop_loss']
                
                if signal['position_type'] == 'long':
                    risk_percent = ((entry - sl) / entry) * 100
                    analysis.append(f"📉 Risk (to SL): {risk_percent:.2f}%")
                    
                    for target_num, target_price in sorted(signal['targets'].items()):
                        reward_percent = ((target_price - entry) / entry) * 100
                        rr_ratio = reward_percent / risk_percent if risk_percent > 0 else 0
                        analysis.append(f"🎯 Target {target_num}: +{reward_percent:.2f}% (R:R = 1:{rr_ratio:.1f})")
                else:  # short
                    risk_percent = ((sl - entry) / entry) * 100
                    analysis.append(f"📉 Risk (to SL): {risk_percent:.2f}%")
                    
                    for target_num, target_price in sorted(signal['targets'].items()):
                        reward_percent = ((entry - target_price) / entry) * 100
                        rr_ratio = reward_percent / risk_percent if risk_percent > 0 else 0
                        analysis.append(f"🎯 Target {target_num}: +{reward_percent:.2f}% (R:R = 1:{rr_ratio:.1f})")
            else:
                # Without SL - just percentages to targets
                entry = signal['entry_price']
                
                for target_num, target_price in sorted(signal['targets'].items()):
                    if signal['position_type'] == 'long':
                        reward_percent = ((target_price - entry) / entry) * 100
                        analysis.append(f"🎯 Target {target_num}: +{reward_percent:.2f}%")
                    else:
                        reward_percent = ((entry - target_price) / entry) * 100
                        analysis.append(f"🎯 Target {target_num}: +{reward_percent:.2f}%")
            
            # Position management info
            analysis.append(f"\n💡 POSITION MANAGEMENT:")
            analysis.append(f"• Position size: According to settings")
            if self.auto_tp_sl:
                analysis.append(f"• TP/SL: Automatic setup ✅")
            if self.auto_breakeven:
                analysis.append(f"• Breakeven: After reaching TP{self.breakeven_after_target} ✅")
            
            return '\n'.join(analysis)
            
        except Exception as e:
            ws_logger.log(f"❌ Error analyzing signal: {e}", 'error')
            return "❌ Signal analysis error"
    
    def execute_trade(self, signal):
        """Execute trade based on signal - WITH ENHANCED RISK MANAGEMENT"""
        try:
            # Get balance for risk checks
            balance_info = self.get_wallet_balance()
            
            # CHECK RISK LIMITS FIRST
            if self.risk_management_enabled:
                can_trade, reason = self.risk_manager.can_trade(
                    self.daily_loss_limit,
                    self.weekly_loss_limit,
                    self.max_consecutive_losses,
                    balance_info,  # Pass balance for margin check
                    self.min_margin_level
                )
                
                if not can_trade:
                    ws_logger.log(f"🛑 TRADE BLOCKED: {reason}", 'error')
                    return f"🛑 TRADE BLOCKED by Risk Management:\n{reason}"
            
            if not self.bybit_client:
                if not self.initialize_bybit_client():
                    return "❌ Error initializing Bybit client"
            
            symbol = signal['symbol']
            side = "Buy" if signal['position_type'] == "long" else "Sell"
            entry_price = signal['entry_price']
            
            ws_logger.log(f"🚀 Executing trade: {symbol} {side}", 'info')
            
            # Get symbol info
            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                return f"❌ Cannot get symbol info for {symbol}"
            
            # Check balance
            if not balance_info or not balance_info.get('success'):
                return "❌ Cannot get balance"
            
            available_balance = balance_info.get('totalAvailableBalance', 0)
            
            if available_balance <= 0:
                return f"❌ No available balance (available: {available_balance} USDT)"
            
            # Calculate position size
            amount_to_use = self.default_amount
            
            if self.use_percentage:
                amount_to_use = available_balance * (self.default_amount / 100.0)
                ws_logger.log(f"📊 Using {self.default_amount}% of {available_balance:.2f} USDT = {amount_to_use:.2f} USDT")
            else:
                amount_to_use = min(self.default_amount, available_balance)
                ws_logger.log(f"💵 Using fixed amount: {amount_to_use:.2f} USDT")
            
            # Control maximum position size
            position_value_usdt = amount_to_use * self.default_leverage
            if position_value_usdt > self.max_position_size:
                position_value_usdt = self.max_position_size
                amount_to_use = position_value_usdt / self.default_leverage
                ws_logger.log(f"⚠️ Limited to max position: {self.max_position_size} USDT")
            
            # Calculate quantity
            qty = position_value_usdt / entry_price
            
            # Format quantity according to requirements
            qty_formatted = self.format_quantity(qty, symbol_info)
            if not qty_formatted or qty_formatted <= 0:
                return f"❌ Invalid position size: {qty}"
            
            ws_logger.log(f"📊 Position calculations:")
            ws_logger.log(f"   💰 Margin: {amount_to_use:.2f} USDT")
            ws_logger.log(f"   ⚔️ Leverage: {self.default_leverage}x")
            ws_logger.log(f"   📈 Position value: {position_value_usdt:.2f} USDT")
            ws_logger.log(f"   📊 Quantity: {qty_formatted} {symbol}")
            
            # Set leverage
            try:
                ws_logger.log(f"⚔️ Setting leverage {self.default_leverage}x...")
                leverage_response = self.bybit_client.set_leverage(
                    category="linear",
                    symbol=symbol,
                    buyLeverage=str(self.default_leverage),
                    sellLeverage=str(self.default_leverage)
                )
                
                if leverage_response.get('retCode') == 0:
                    ws_logger.log(f"✅ Leverage set: {self.default_leverage}x", 'success')
                else:
                    ws_logger.log(f"⚠️ Error setting leverage: {leverage_response.get('retMsg', 'Unknown error')}", 'warning')
                    
            except Exception as e:
                ws_logger.log(f"⚠️ Error setting leverage: {e}", 'warning')
            
            # Create order
            order_params = {
                'category': "linear",
                'symbol': symbol,
                'side': side,
                'orderType': "Market",
                'qty': str(qty_formatted),
                'positionIdx': self.get_position_idx(signal['position_type'])
            }
            
            ws_logger.log(f"📤 Sending order: {order_params}")
            
            if self.use_demo_account:
                ws_logger.log("🎮 DEMO MODE - simulating order", 'info')
                order_response = {
                    'retCode': 0,
                    'retMsg': 'Demo order simulated',
                    'result': {
                        'orderId': f'DEMO_{symbol}_{int(time.time())}',
                        'orderLinkId': f'demo_{int(time.time())}'
                    }
                }
            else:
                ws_logger.log("💰 LIVE MODE - real order!", 'warning')
                order_response = self.bybit_client.place_order(**order_params)
            
            if order_response.get('retCode') == 0:
                order_id = order_response.get('result', {}).get('orderId', 'Unknown')
                ws_logger.log(f"✅ Order executed! Order ID: {order_id}", 'success')
                
                # Add position to monitoring if auto TP/SL enabled
                if self.auto_tp_sl or self.auto_breakeven:
                    ws_logger.log(f"🎯 Adding position to TP/SL monitoring...")
                    self.position_manager.add_position(symbol, signal, order_id)
                    
                    # Start monitoring if not active
                    if not self.position_manager.monitoring_active:
                        self.position_manager.start_monitoring()
                
                result = f"""✅ TRADE EXECUTED!
{'=' * 40}
📊 Symbol: {symbol}
📈 Type: {signal['position_type'].upper()}
💰 Entry price: {entry_price}
📊 Quantity: {qty_formatted}
💵 Position value: {position_value_usdt:.2f} USDT
⚔️ Leverage: {self.default_leverage}x
🎮 Mode: {'DEMO' if self.use_demo_account else 'LIVE'}
🆔 Order ID: {order_id}
{'=' * 40}"""
                
                if self.auto_tp_sl:
                    result += f"\n🎯 Auto TP/SL: Active (setting in 2 seconds...)"
                if self.auto_breakeven:
                    result += f"\n💡 Auto Breakeven: Active (after reaching TP{self.breakeven_after_target})"
                
                return result
                
            else:
                error_msg = order_response.get('retMsg', 'Unknown error')
                
                # Record failed trade for risk management
                if self.risk_management_enabled:
                    self.risk_manager.record_trade(-amount_to_use * 0.01, symbol)  # Record small loss for failed trade
                
                return f"❌ Order execution error: {error_msg}"
                
        except Exception as e:
            ws_logger.log(f"❌ Error execute_trade: {e}", 'error')
            return f"❌ Trade execution error: {str(e)}"


# === CONSOLE MANAGER WITH TELETHON COMMANDS ===
class ConsoleManager:
    """Manager for interactive console and redirections - WITH TELETHON INTEGRATION"""
    
    def __init__(self, bot):
        self.bot = bot
        self.redirect_active = False
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.buffer = io.StringIO()
        
        # Telethon console client for console integration
        self.telethon_client = None
        self.telethon_connected = False
        self.telethon_session_info = {}
    
    def start_redirect(self):
        """Start console output redirection"""
        if not self.redirect_active:
            self.redirect_active = True
            sys.stdout = self.buffer
            sys.stderr = self.buffer
            ws_logger.log("🟢 Console redirection started", 'success')
    
    def stop_redirect(self):
        """Stop console output redirection"""
        if self.redirect_active:
            self.redirect_active = False
            sys.stdout = self.original_stdout
            sys.stderr = self.original_stderr
            ws_logger.log("🔴 Console redirection stopped", 'warning')
    
    def get_output(self):
        """Get and clear buffered output"""
        if self.redirect_active:
            output = self.buffer.getvalue()
            self.buffer.truncate(0)
            self.buffer.seek(0)
            return output
        return ""
    
    async def execute_command(self, command):
        """Execute console command - ENHANCED WITH TELETHON COMMANDS"""
        try:
            cmd_parts = command.strip().split()
            if not cmd_parts:
                return "No command entered"
            
            cmd = cmd_parts[0].lower()
            args = cmd_parts[1:] if len(cmd_parts) > 1 else []
            
            # Forwarder commands
            if cmd == 'forwarder.status':
                return self._forwarder_status()
            elif cmd == 'forwarder.start':
                return self._forwarder_start()
            elif cmd == 'forwarder.stop':
                return self._forwarder_stop()
            elif cmd == 'forwarder.channels':
                return self._forwarder_channels()
            
            # Bot commands
            elif cmd == 'bot.balance':
                return self._bot_balance()
            elif cmd == 'bot.positions':
                return self._bot_positions()
            elif cmd == 'bot.test_api':
                return self._bot_test_api()
            
            # Risk management commands
            elif cmd == 'risk.status':
                return self._risk_status()
            elif cmd == 'risk.reset':
                return self._risk_reset()
            elif cmd == 'risk.margin':
                return self._risk_margin()
            
            # TELETHON COMMANDS - NEW!
            elif cmd == 'telethon.connect':
                return await self._telethon_connect()
            elif cmd == 'telethon.disconnect':
                return await self._telethon_disconnect()
            elif cmd == 'telethon.status':
                return self._telethon_status()
            elif cmd == 'telethon.channels':
                return await self._telethon_channels()
            elif cmd == 'telethon.session':
                return self._telethon_session()
            
            # System commands
            elif cmd == 'clear':
                return "clear_console"  # Special signal for frontend
            elif cmd == 'help':
                return self._show_help()
            else:
                return f"❌ Unknown command: {cmd}"
                
        except Exception as e:
            return f"❌ Command error: {str(e)}"
    
    # === TELETHON COMMAND IMPLEMENTATIONS ===
    
    async def _telethon_connect(self):
        """Connect to Telegram via Telethon in console"""
        try:
            # Check if forwarder has valid config
            if not self.bot.forwarder.api_id or not self.bot.forwarder.api_hash:
                return "❌ Missing Telethon API credentials. Configure in Forwarder tab first."
            
            if not self.bot.forwarder.phone_number:
                return "❌ Missing phone number. Configure in Forwarder tab first."
            
            # Initialize Telethon client
            if not self.bot.forwarder.initialize_telethon_client():
                return "❌ Failed to initialize Telethon client"
            
            # Connect and get session info
            loop = asyncio.get_event_loop()
            success = await self.bot.forwarder.connect_and_get_channels()
            
            if success:
                self.telethon_connected = True
                self.telethon_session_info = self.bot.forwarder.console_session_info
                
                session_info = self.telethon_session_info
                return f"""✅ Connected to Telegram!
User: {session_info.get('first_name', 'Unknown')} (@{session_info.get('username', 'none')})
Phone: {session_info.get('phone', 'Unknown')}
ID: {session_info.get('user_id', 'Unknown')}
Session saved for future use - no 2FA needed next time!"""
            else:
                return "❌ Failed to connect to Telegram"
                
        except Exception as e:
            return f"❌ Telethon connection error: {str(e)}"
    
    async def _telethon_disconnect(self):
        """Disconnect Telethon"""
        try:
            if not self.telethon_connected:
                return "⚠️ Telethon is not connected"
            
            # Disconnect client if exists
            if self.bot.forwarder.telethon_client:
                try:
                    await self.bot.forwarder.telethon_client.disconnect()
                except:
                    pass
            
            self.telethon_connected = False
            self.telethon_session_info = {}
            self.bot.forwarder.console_connection_status = "disconnected"
            
            return "✅ Disconnected from Telegram"
            
        except Exception as e:
            return f"❌ Disconnect error: {str(e)}"
    
    def _telethon_status(self):
        """Get Telethon connection status"""
        try:
            if self.telethon_connected:
                session = self.telethon_session_info
                return f"""📱 Telethon Status: CONNECTED
User: {session.get('first_name', 'Unknown')} (@{session.get('username', 'none')})
Phone: {session.get('phone', 'Unknown')}
Session exists: {self.bot.forwarder._session_authorized}"""
            else:
                return """📴 Telethon Status: DISCONNECTED
Session exists: """ + str(self.bot.forwarder.check_existing_session())
                
        except Exception as e:
            return f"❌ Status error: {str(e)}"
    
    async def _telethon_channels(self):
        """List available channels via Telethon"""
        try:
            if not self.telethon_connected:
                return "❌ Not connected. Use 'telethon.connect' first"
            
            channels = self.bot.forwarder.available_channels
            if not channels:
                return "No channels available"
            
            result = f"📺 Available Channels ({len(channels)}):\n"
            for i, ch in enumerate(channels[:20], 1):  # Limit to 20 for console
                monitored = "✅" if ch['is_monitored'] else "❌"
                result += f"{i}. {ch['name']} ({ch['type']}) {monitored}\n"
                result += f"   ID: {ch['id']}"
                if ch['username']:
                    result += f" | @{ch['username']}"
                result += "\n"
            
            if len(channels) > 20:
                result += f"\n... and {len(channels) - 20} more channels"
            
            return result
            
        except Exception as e:
            return f"❌ Channels error: {str(e)}"
    
    def _telethon_session(self):
        """Show current Telethon session info"""
        try:
            if not self.telethon_connected:
                return "❌ Not connected. Use 'telethon.connect' first"
            
            session = self.telethon_session_info
            session_path = self.bot.forwarder.session_name
            
            return f"""📱 Telethon Session Info:
User: {session.get('first_name', 'Unknown')} 
Username: @{session.get('username', 'none')}
Phone: {session.get('phone', 'Unknown')}
User ID: {session.get('user_id', 'Unknown')}
Session Path: {session_path}
Session Persistent: Yes - no 2FA needed on reconnect!"""
            
        except Exception as e:
            return f"❌ Session info error: {str(e)}"
    
    # === EXISTING COMMAND IMPLEMENTATIONS ===
    
    def _forwarder_status(self):
        """Get forwarder status"""
        status = "🟢 Running" if self.bot.forwarder.forwarder_running else "🔴 Stopped"
        channels = len(self.bot.forwarder.monitored_channels)
        return f"Forwarder Status: {status}\nMonitored channels: {channels}"
    
    def _forwarder_start(self):
        """Start forwarder"""
        if self.bot.forwarder.start_forwarder():
            return "✅ Forwarder started successfully"
        return "❌ Failed to start forwarder"
    
    def _forwarder_stop(self):
        """Stop forwarder"""
        if self.bot.forwarder.stop_forwarder():
            return "✅ Forwarder stopped"
        return "❌ Failed to stop forwarder"
    
    def _forwarder_channels(self):
        """List monitored channels"""
        channels = self.bot.forwarder.monitored_channels
        if not channels:
            return "No channels monitored"
        
        result = "Monitored channels:\n"
        for i, ch in enumerate(channels, 1):
            result += f"{i}. {ch['name']} (ID: {ch['id']})\n"
        return result
    
    def _bot_balance(self):
        """Get bot balance"""
        balance = self.bot.get_wallet_balance()
        if balance and balance.get('success'):
            return f"💰 Balance: {balance['totalAvailableBalance']:.2f} USDT"
        return "❌ Failed to get balance"
    
    def _bot_positions(self):
        """Get active positions"""
        positions = self.bot.position_manager.get_positions_summary()
        if not positions:
            return "No active positions"
        
        result = "Active positions:\n"
        for pos in positions:
            result += f"• {pos['symbol']} {pos['type']} @ {pos['entry']} (Targets: {pos['targets']})\n"
        return result
    
    def _bot_test_api(self):
        """Test API connection"""
        if self.bot.test_api_keys_simple():
            return "✅ API connection successful"
        return "❌ API connection failed"
    
    def _risk_status(self):
        """Get risk management status"""
        stats = self.bot.risk_manager.get_stats()
        margin_info = stats.get('last_margin_check', {})
        
        result = f"""📊 Risk Management Status:
Daily P/L: ${stats['daily_loss']:.2f} / ${self.bot.daily_loss_limit:.2f}
Weekly P/L: ${stats['weekly_loss']:.2f} / ${self.bot.weekly_loss_limit:.2f}
Consecutive Losses: {stats['consecutive_losses']} / {self.bot.max_consecutive_losses}
Trades Today: {stats['total_trades_today']}
Cooling Until: {stats['cooling_until'] or 'None'}"""
        
        if margin_info:
            result += f"\n\n📊 Margin Level: {margin_info.get('margin_level', 'N/A'):.2f}"
            result += f"\nMin Required: {self.bot.min_margin_level}"
        
        return result
    
    def _risk_reset(self):
        """Reset risk limits"""
        self.bot.risk_manager.reset_daily_limits()
        return "✅ Risk limits reset"
    
    def _risk_margin(self):
        """Check current margin level"""
        balance = self.bot.get_wallet_balance()
        if balance:
            is_safe, msg = self.bot.risk_manager.check_margin_level(balance, self.bot.min_margin_level)
            return f"📊 Margin Status: {'✅ SAFE' if is_safe else '⚠️ WARNING'}\n{msg}"
        return "❌ Cannot check margin level"
    
    def _show_help(self):
        """Show help message"""
        return """Available commands:

🔧 FORWARDER:
  • forwarder.status - forwarder status
  • forwarder.start - start forwarder
  • forwarder.stop - stop forwarder  
  • forwarder.channels - list monitored channels

🤖 BOT:
  • bot.balance - check balance
  • bot.positions - active positions
  • bot.test_api - test API connection

📊 RISK MANAGEMENT:
  • risk.status - risk management status
  • risk.reset - reset risk limits
  • risk.margin - check margin level

📱 TELETHON (NEW):
  • telethon.connect - connect to Telegram via Telethon
  • telethon.disconnect - disconnect from Telethon
  • telethon.status - check Telethon connection status
  • telethon.channels - list available channels via Telethon
  • telethon.session - show current session info

📊 SYSTEM:
  • clear - clear console
  • help - show this help"""


# === GLOBAL INSTANCES ===
bot = TelegramTradingBot()
console_manager = ConsoleManager(bot)


# === SOCKET.IO HANDLERS ===
@socketio.on('connect')
def handle_connect():
    """Handle Socket.IO connection"""
    try:
        ws_logger.update_client_count(ws_logger.clients_connected + 1)
        emit('connected', {'message': 'Connected to Socket.IO'})
        ws_logger.log('📌 Socket.IO client connected', 'info')
    except Exception as e:
        logger.error(f"Socket.IO connect error: {e}")


@socketio.on('disconnect')
def handle_disconnect():
    """Handle Socket.IO disconnection"""
    try:
        ws_logger.update_client_count(max(0, ws_logger.clients_connected - 1))
        ws_logger.log('📌 Socket.IO client disconnected', 'info')
    except Exception as e:
        logger.error(f"Socket.IO disconnect error: {e}")


@socketio.on('request_status')
def handle_status_request():
    """Send current status via Socket.IO"""
    try:
        status = {
            'telegram_bot': getattr(bot, 'telegram_running', False),
            'forwarder': getattr(bot.forwarder, 'forwarder_running', False) if hasattr(bot, 'forwarder') else False,
            'monitoring': getattr(bot.position_manager, 'monitoring_active', False) if hasattr(bot, 'position_manager') else False,
            'console_redirect': getattr(console_manager, 'redirect_active', False) if hasattr(console_manager, 'redirect_active') else False
        }
        emit('status_update', status)
    except Exception as e:
        logger.error(f"Socket.IO status error: {e}")
        emit('error', {'message': 'Failed to get status'})


# === FLASK ROUTES ===

@app.route('/')
def index():
    """Render main page"""
    try:
        import os
        
        # Debug info
        current_dir = os.getcwd()
        template_path = os.path.join(current_dir, 'templates', 'index.html')
        file_exists = os.path.exists(template_path)
        
        print("="*60)
        print("🔍 DEBUG: Route '/' called")
        print(f"📁 Current directory: {current_dir}")
        print(f"📄 Template path: {template_path}")
        print(f"✅ File exists: {file_exists}")
        
        if file_exists:
            # Sprawdź rozmiar pliku
            file_size = os.path.getsize(template_path)
            print(f"📊 File size: {file_size} bytes")
            
            if file_size > 0:
                print("🚀 Attempting to render template...")
                result = render_template('index.html')
                print("✅ Template rendered successfully!")
                return result
            else:
                print("❌ File is empty!")
                return """
                <html>
                <head><title>Trading Bot - Error</title></head>
                <body style="font-family: Arial; padding: 50px; text-align: center;">
                    <h1>🚀 Trading Bot</h1>
                    <h2>❌ File Error</h2>
                    <p>templates/index.html exists but is empty (0 bytes)</p>
                    <p><a href="/test">Test Page</a></p>
                </body>
                </html>
                """
        else:
            print("❌ File not found!")
            
        print("="*60)
        
        # If no file, return setup error
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Trading Bot - Setup Required</title>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 50px; background-color: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #2E86AB; }}
                .error {{ background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .info {{ background-color: #d1ecf1; color: #0c5460; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                code {{ background-color: #e9ecef; padding: 2px 5px; border-radius: 3px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🚀 Trading Bot - Setup Required</h1>
                <div class="error">
                    <strong>⚠️ Missing HTML file!</strong><br>
                    File <code>templates/index.html</code> not found
                </div>
                <div class="info">
                    <strong>📋 Debug Info:</strong><br>
                    Current directory: <code>{current_dir}</code><br>
                    Template path: <code>{template_path}</code><br>
                    File exists: <code>{file_exists}</code><br><br>
                    
                    <strong>Instructions:</strong><br><br>
                    1. Create folder <code>templates</code> in the same directory as <code>app.py</code><br>
                    2. Save HTML file with interface as <code>templates/index.html</code><br>
                    3. Refresh the page<br><br>
                    
                    <strong>Directory structure:</strong><br>
                    <pre>
trading-bot/
├── app.py              (this file)
├── templates/
│   └── index.html      (missing file)
├── config.ini
└── bot_trading.log
                    </pre>
                </div>
                <p><a href="/test">Go to Test Page</a> | <a href="/api/health">API Health Check</a></p>
            </div>
        </body>
        </html>
        """
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print("❌ EXCEPTION in index():")
        print(error_details)
        
        return f"""
        <html>
        <head><title>Trading Bot - Error</title></head>
        <body style="font-family: Arial; padding: 50px;">
            <h1>🚀 Trading Bot</h1>
            <div style="background: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; margin: 20px;">
                <strong>❌ Rendering error:</strong><br>
                {str(e)}<br><br>
                <details>
                    <summary>Technical details (click to expand)</summary>
                    <pre style="background: #f8f9fa; padding: 10px; overflow: auto;">{error_details}</pre>
                </details>
                <br>
                Check if file <code>templates/index.html</code> exists and is correct.
            </div>
            <p><a href="/test">Try Test Page</a></p>
        </body>
        </html>
        """
    



# Health check endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        return jsonify({
            'status': 'ok',
            'message': 'Trading Bot API is running',
            'timestamp': datetime.now().isoformat(),
            'bot_initialized': hasattr(bot, 'config') and bot.config is not None,
            'socketio_clients': ws_logger.clients_connected
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


# API Routes
@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """Get or update configuration"""
    try:
        if request.method == 'GET':
            # Safely get config values with defaults
            config_data = {
                'telegram_token': getattr(bot, 'telegram_token', ''),
                'telegram_chat_id': getattr(bot, 'telegram_chat_id', ''),
                'bybit_api_key': getattr(bot, 'bybit_api_key', ''),
                'bybit_api_secret': getattr(bot, 'bybit_api_secret', ''),
                'bybit_subaccount': getattr(bot, 'bybit_subaccount', ''),
                'bybit_platform': getattr(bot, 'bybit_platform', 'bybitglobal'),
                'position_mode': getattr(bot, 'position_mode', 'one_way'),
                'default_leverage': getattr(bot, 'default_leverage', 10),
                'default_amount': getattr(bot, 'default_amount', 100),
                'use_percentage': getattr(bot, 'use_percentage', False),
                'use_demo_account': getattr(bot, 'use_demo_account', True),
                'auto_tp_sl': getattr(bot, 'auto_tp_sl', True),
                'auto_breakeven': getattr(bot, 'auto_breakeven', True),
                'breakeven_after_target': getattr(bot, 'breakeven_after_target', 1),
                'auto_execute_signals': getattr(bot, 'auto_execute_signals', False),
                'max_position_size': getattr(bot, 'max_position_size', 1000),
                'risk_percent': getattr(bot, 'risk_percent', 2),
                'risk_management_enabled': getattr(bot, 'risk_management_enabled', True),
                'daily_loss_limit': getattr(bot, 'daily_loss_limit', 500),
                'weekly_loss_limit': getattr(bot, 'weekly_loss_limit', 2000),
                'max_consecutive_losses': getattr(bot, 'max_consecutive_losses', 3),
                'min_margin_level': getattr(bot, 'min_margin_level', 1.5)
            }
            
            # Safely get forwarder config
            if hasattr(bot, 'forwarder') and bot.forwarder:
                config_data.update({
                    'forwarder_api_id': str(getattr(bot.forwarder, 'api_id', '')) if getattr(bot.forwarder, 'api_id', None) else '',
                    'forwarder_api_hash': getattr(bot.forwarder, 'api_hash', ''),
                    'forwarder_phone_number': getattr(bot.forwarder, 'phone_number', ''),
                    'forwarder_target_chat_id': getattr(bot.forwarder, 'target_chat_id', ''),
                    'forward_all_messages': getattr(bot.forwarder, 'forward_all_messages', False)
                })
            else:
                config_data.update({
                    'forwarder_api_id': '',
                    'forwarder_api_hash': '',
                    'forwarder_phone_number': '',
                    'forwarder_target_chat_id': '',
                    'forward_all_messages': False
                })
            
            return jsonify(config_data)
        
        else:  # POST
            try:
                data = request.json
                if not data:
                    return jsonify({'success': False, 'error': 'No data provided'}), 400
                
                # Update config
                bot.telegram_token = data.get('telegram_token', '')
                bot.telegram_chat_id = data.get('telegram_chat_id', '')
                bot.bybit_api_key = data.get('bybit_api_key', '')
                bot.bybit_api_secret = data.get('bybit_api_secret', '')
                bot.bybit_subaccount = data.get('bybit_subaccount', '')
                bot.bybit_platform = data.get('bybit_platform', 'bybitglobal')
                bot.position_mode = data.get('position_mode', 'one_way')
                
                # Save config
                if bot.save_config():
                    return jsonify({'success': True, 'message': 'Configuration saved'})
                else:
                    return jsonify({'success': False, 'error': 'Failed to save configuration'}), 500
                    
            except Exception as e:
                logger.error(f"Error saving config: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
                
    except Exception as e:
        logger.error(f"Error in handle_config: {e}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500


@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    """Test API connection"""
    try:
        if bot.initialize_bybit_client():
            platform = 'bybitglobal.com' if bot.bybit_platform == 'bybitglobal' else 'bybit.com'
            return jsonify({
                'success': True,
                'platform': platform,
                'demo': bot.use_demo_account
            })
        else:
            return jsonify({'success': False, 'error': 'Connection failed'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/subaccounts', methods=['GET'])
def get_subaccounts():
    """Get list of subaccounts"""
    try:
        subaccounts = bot.get_subaccounts()
        formatted_subs = []
        
        for sub in subaccounts:
            formatted_subs.append({
                'uid': sub.get('uid'),
                'display': f"{sub.get('memberName', 'Unknown')} ({sub.get('uid')})"
            })
        
        return jsonify({'success': True, 'subaccounts': formatted_subs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/profiles', methods=['GET', 'POST'])
def handle_profiles():
    """Get all profiles or save new profile"""
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'profiles': bot.profile_manager.profiles
        })
    
    else:  # POST
        try:
            data = request.json
            name = data.get('name')
            
            if not name:
                return jsonify({'success': False, 'error': 'Profile name required'}), 400
            
            if bot.save_current_as_profile(name):
                return jsonify({'success': True, 'message': f'Profile {name} saved'})
            else:
                return jsonify({'success': False, 'error': 'Failed to save profile'}), 500
                
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/profiles/<name>/load', methods=['POST'])
def load_profile(name):
    """Load a profile"""
    try:
        if bot.load_profile(name):
            return jsonify({'success': True, 'message': f'Profile {name} loaded'})
        else:
            return jsonify({'success': False, 'error': 'Profile not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/profiles/<name>', methods=['DELETE'])
def delete_profile(name):
    """Delete a profile"""
    try:
        if bot.profile_manager.delete_profile(name):
            return jsonify({'success': True, 'message': f'Profile {name} deleted'})
        else:
            return jsonify({'success': False, 'error': 'Profile not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/trading-settings', methods=['POST'])
def update_trading_settings():
    """Update trading settings - ENHANCED"""
    try:
        data = request.json
        
        bot.default_leverage = int(data.get('default_leverage', 10))
        bot.default_amount = float(data.get('default_amount', 100))
        bot.use_percentage = data.get('use_percentage', False)
        bot.use_demo_account = data.get('use_demo_account', True)
        bot.auto_tp_sl = data.get('auto_tp_sl', True)
        bot.auto_breakeven = data.get('auto_breakeven', True)
        bot.breakeven_after_target = int(data.get('breakeven_after_target', 1))
        bot.max_position_size = float(data.get('max_position_size', 1000))
        bot.risk_percent = float(data.get('risk_percent', 2))
        
        # Risk Management Settings
        bot.risk_management_enabled = data.get('risk_management_enabled', True)
        bot.daily_loss_limit = float(data.get('daily_loss_limit', 500))
        bot.weekly_loss_limit = float(data.get('weekly_loss_limit', 2000))
        bot.max_consecutive_losses = int(data.get('max_consecutive_losses', 3))
        bot.min_margin_level = float(data.get('min_margin_level', 1.5))
        
        if bot.save_config():
            return jsonify({'success': True, 'message': 'Trading settings saved'})
        else:
            return jsonify({'success': False, 'error': 'Failed to save settings'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/balance', methods=['GET'])
def get_balance():
    """Get wallet balance"""
    try:
        balance = bot.get_wallet_balance()
        if balance:
            return jsonify(balance)
        else:
            return jsonify({'success': False, 'error': 'Failed to get balance'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/risk-stats', methods=['GET'])
def get_risk_stats():
    """Get risk management statistics - ENHANCED"""
    try:
        stats = bot.risk_manager.get_stats()
        return jsonify({
            'success': True,
            **stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analyze-signal', methods=['POST'])
def analyze_signal():
    """Analyze trading signal"""
    try:
        data = request.json
        signal_text = data.get('signal', '')
        
        signal = bot.parse_trading_signal(signal_text)
        if signal:
            analysis = bot.analyze_trading_signal(signal)
            return jsonify({
                'success': True,
                'signal': signal,
                'analysis': analysis
            })
        else:
            return jsonify({'success': False, 'error': 'Signal not recognized'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/execute-trade', methods=['POST'])
def execute_trade():
    """Execute trade from signal"""
    try:
        data = request.json
        signal = data.get('signal')
        
        if not signal:
            return jsonify({'success': False, 'error': 'No signal provided'}), 400
        
        result = bot.execute_trade(signal)
        success = '✅' in result
        
        return jsonify({
            'success': success,
            'message': result
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/telegram/start', methods=['POST'])
def start_telegram():
    """Start Telegram bot"""
    try:
        # Get checkbox state from frontend
        data = request.json or {}
        
        # Update auto-execute from checkbox if present
        if 'auto_execute' in data:
            bot.auto_execute_signals = bool(data.get('auto_execute', False))
            bot.save_config()  # Save the updated setting
            ws_logger.log(f"🤖 Auto-trade set to: {bot.auto_execute_signals}", 'info')
        
        # Validate configuration
        if not bot.telegram_token:
            return jsonify({
                'success': False,
                'error': 'No Telegram bot token. Enter token in Configuration tab.'
            }), 400
        
        if bot.start_telegram_bot():
            return jsonify({'success': True, 'message': 'Telegram bot started'})
        else:
            return jsonify({'success': False, 'error': 'Failed to start Telegram bot'}), 500
    except Exception as e:
        logger.error(f"Error starting Telegram bot: {e}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500


@app.route('/api/telegram/stop', methods=['POST'])
def stop_telegram():
    """Stop Telegram bot"""
    try:
        if bot.stop_telegram_bot():
            return jsonify({'success': True, 'message': 'Telegram bot stopped'})
        else:
            return jsonify({'success': False, 'error': 'Failed to stop bot'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/telegram/chat-id', methods=['GET'])
def get_chat_id():
    """Get Telegram chat ID"""
    try:
        chat_id = bot.get_telegram_chat_id()
        if chat_id:
            return jsonify({'success': True, 'chat_id': chat_id})
        else:
            return jsonify({'success': False, 'error': 'No chat ID found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/forwarder/config', methods=['POST'])
def update_forwarder_config():
    """Update forwarder configuration"""
    try:
        data = request.json
        
        # Parse API ID safely
        api_id_str = data.get('api_id', '').strip()
        if api_id_str and api_id_str.isdigit():
            bot.forwarder.api_id = int(api_id_str)
        else:
            bot.forwarder.api_id = None
        
        bot.forwarder.api_hash = data.get('api_hash', '').strip()
        bot.forwarder.phone_number = data.get('phone_number', '').strip()
        bot.forwarder.target_chat_id = data.get('target_chat_id', '').strip()
        bot.forwarder.forward_all_messages = data.get('forward_all_messages', False)
        
        # Save configuration
        if bot.forwarder.save_forwarder_config():
            ws_logger.log("✅ Forwarder configuration saved successfully", 'success')
            return jsonify({'success': True, 'message': 'Forwarder config saved'})
        else:
            ws_logger.log("❌ Error saving forwarder configuration", 'error')
            return jsonify({'success': False, 'error': 'Failed to save config'}), 500
            
    except Exception as e:
        logger.error(f"Error updating forwarder config: {e}")
        ws_logger.log(f"❌ Error update_forwarder_config: {e}", 'error')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/forwarder/channels', methods=['GET'])
def get_forwarder_channels():
    """Get available channels"""
    try:
        # Check if channels are already being loaded
        cache = bot.forwarder.get_cached_channels()
        if cache.get('is_loading'):
            return jsonify({
                'success': True,
                'channels': cache.get('channels', []),
                'loading': True,
                'cached': True
            })
        
        # Return cached channels if available and recent
        if cache.get('channels') and cache.get('last_update'):
            try:
                last_update = datetime.fromisoformat(cache.get('last_update'))
                # If channels were updated in the last 5 minutes, return cached
                if (datetime.now() - last_update).seconds < 300:
                    return jsonify({
                        'success': True,
                        'channels': cache.get('channels', []),
                        'cached': True,
                        'last_update': cache.get('last_update')
                    })
            except:
                pass
        
        # Validate configuration first
        if not bot.forwarder.api_id or not bot.forwarder.api_hash:
            return jsonify({
                'success': False,
                'error': 'Missing API configuration. First enter API ID and API Hash.'
            }), 400
        
        if not bot.forwarder.phone_number:
            return jsonify({
                'success': False,
                'error': 'Missing phone number. Enter phone number.'
            }), 400
        
        ws_logger.log("📱 API: Fetching channels list...", 'info')
        
        # Get channels
        channels = bot.forwarder.get_channels_list()
        
        if channels is None:
            return jsonify({
                'success': False,
                'error': 'Failed to fetch channels. Check API configuration.'
            }), 500
        elif isinstance(channels, list):
            ws_logger.log(f"✅ API: Returning {len(channels)} channels", 'success')
            return jsonify({
                'success': True, 
                'channels': channels,
                'cached': False
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Unexpected server response'
            }), 500
            
    except Exception as e:
        logger.error(f"Error getting channels: {e}")
        ws_logger.log(f"❌ API Error: {str(e)}", 'error')
        return jsonify({'success': False, 'error': f'Error fetching channels: {str(e)}'}), 500


@app.route('/api/forwarder/monitor', methods=['POST'])
def add_channel_to_monitoring():
    """Add channel to monitoring"""
    try:
        data = request.json
        channel_id = data.get('channel_id')
        channel_name = data.get('channel_name')
        
        if not channel_id or not channel_name:
            return jsonify({'success': False, 'error': 'Channel ID and name required'}), 400
        
        # Ensure channel_id is string for consistency
        channel_id = str(channel_id)
        
        # Check if channel already exists
        existing = [ch for ch in bot.forwarder.monitored_channels if ch['id'] == channel_id]
        if existing:
            return jsonify({'success': False, 'error': 'Channel already monitored'}), 400
        
        bot.forwarder.monitored_channels.append({
            'id': channel_id,
            'name': channel_name
        })
        
        if bot.forwarder.save_forwarder_config():
            # Emit update via Socket.IO
            socketio.emit('forwarder_channels_update', {
                'channels': bot.forwarder.available_channels,
                'monitored': bot.forwarder.monitored_channels
            })
            return jsonify({'success': True, 'message': 'Channel added'})
        else:
            return jsonify({'success': False, 'error': 'Failed to save'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/forwarder/monitor/<int:index>', methods=['DELETE'])
def remove_channel_from_monitoring(index):
    """Remove channel from monitoring"""
    try:
        if 0 <= index < len(bot.forwarder.monitored_channels):
            bot.forwarder.monitored_channels.pop(index)
            
            if bot.forwarder.save_forwarder_config():
                # Emit update via Socket.IO
                socketio.emit('forwarder_channels_update', {
                    'channels': bot.forwarder.available_channels,
                    'monitored': bot.forwarder.monitored_channels
                })
                return jsonify({'success': True, 'message': 'Channel removed'})
            else:
                return jsonify({'success': False, 'error': 'Failed to save'}), 500
        else:
            return jsonify({'success': False, 'error': 'Invalid index'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/forwarder/monitored', methods=['GET'])
def get_monitored_channels():
    """Get monitored channels"""
    try:
        return jsonify({
            'success': True,
            'channels': bot.forwarder.monitored_channels
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/forwarder/start', methods=['POST'])
def start_forwarder():
    """Start forwarder"""
    try:
        # Validate configuration before starting
        if not bot.forwarder.api_id or not bot.forwarder.api_hash:
            return jsonify({
                'success': False, 
                'error': 'Missing Telethon API configuration. Enter API ID and API Hash in FORWARDER tab.'
            }), 400
        
        if not bot.forwarder.phone_number:
            return jsonify({
                'success': False,
                'error': 'Missing phone number. Enter phone number in FORWARDER tab.'
            }), 400
        
        if not bot.forwarder.monitored_channels:
            return jsonify({
                'success': False,
                'error': 'No channels for monitoring. First fetch channels and select which to monitor.'
            }), 400
        
        if bot.forwarder.start_forwarder():
            return jsonify({'success': True, 'message': 'Forwarder started'})
        else:
            return jsonify({'success': False, 'error': 'Failed to start forwarder. Check logs.'})
    except Exception as e:
        logger.error(f"Error starting forwarder: {e}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500


@app.route('/api/forwarder/stop', methods=['POST'])
def stop_forwarder():
    """Stop forwarder"""
    try:
        if bot.forwarder.stop_forwarder():
            return jsonify({'success': True, 'message': 'Forwarder stopped'})
        else:
            return jsonify({'success': False, 'error': 'Failed to stop forwarder'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/console/command', methods=['POST'])
def execute_console_command():
    """Execute console command"""
    try:
        data = request.json
        command = data.get('command', '')
        
        # Create new event loop for this request
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(console_manager.execute_command(command))
            return jsonify({'success': True, 'message': result})
        finally:
            loop.close()
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/positions', methods=['GET'])
def get_positions():
    """Get active positions"""
    try:
        positions = bot.position_manager.get_positions_summary()
        monitoring_active = bot.position_manager.monitoring_active
        
        return jsonify({
            'success': True,
            'positions': positions,
            'monitoring_active': monitoring_active
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/positions/monitoring/start', methods=['POST'])
def start_position_monitoring():
    """Start position monitoring"""
    try:
        bot.position_manager.start_monitoring()
        return jsonify({'success': True, 'message': 'Monitoring started'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/positions/monitoring/stop', methods=['POST'])
def stop_position_monitoring():
    """Stop position monitoring"""
    try:
        bot.position_manager.stop_monitoring()
        return jsonify({'success': True, 'message': 'Monitoring stopped'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/positions/breakeven', methods=['POST'])
def set_breakeven():
    """Manually set position to breakeven"""
    try:
        data = request.json
        symbol = data.get('symbol', '').upper()
        
        if not symbol:
            return jsonify({'success': False, 'error': 'Symbol required'}), 400
        
        if bot.position_manager.move_sl_to_breakeven(symbol):
            return jsonify({'success': True, 'message': f'Breakeven set for {symbol}'})
        else:
            return jsonify({'success': False, 'error': 'Failed to set breakeven'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/positions/<symbol>', methods=['DELETE'])
def remove_position(symbol):
    """Remove position from monitoring"""
    try:
        bot.position_manager.remove_position(symbol.upper())
        return jsonify({'success': True, 'message': f'Position {symbol} removed'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get application logs"""
    try:
        # Read log file
        logs = []
        if os.path.exists('bot_trading.log'):
            with open('bot_trading.log', 'r', encoding='utf-8') as f:
                logs = f.readlines()[-500:]  # Last 500 lines
        
        return jsonify({'success': True, 'logs': logs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs', methods=['DELETE'])
def clear_logs():
    """Clear application logs"""
    try:
        if os.path.exists('bot_trading.log'):
            open('bot_trading.log', 'w').close()
        return jsonify({'success': True, 'message': 'Logs cleared'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/submit', methods=['POST'])
def submit_auth():
    """Submit authentication data"""
    try:
        data = request.json
        auth_value = data.get('auth_value', '')
        
        # Determine auth type based on content
        auth_type = 'code'
        if len(auth_value) > 10:  # Likely a password
            auth_type = 'password'
        
        # Add to auth queue
        auth_queue.put({
            'type': auth_type,
            'value': auth_value
        })
        
        return jsonify({'success': True, 'message': 'Auth submitted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Error handlers
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'API endpoint not found'}), 404
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head><title>404 - Not Found</title></head>
    <body style="font-family: Arial; padding: 50px; text-align: center;">
        <h1>🚀 Trading Bot</h1>
        <h2>404 - Page not found</h2>
        <p><a href="/">← Back to application</a></p>
    </body>
    </html>
    """), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head><title>500 - Server Error</title></head>
    <body style="font-family: Arial; padding: 50px; text-align: center;">
        <h1>🚀 Trading Bot</h1>
        <h2>500 - Server error</h2>
        <p>Check application logs or restart server.</p>
        <p><a href="/">← Back to application</a></p>
    </body>
    </html>
    """), 500

# Global error handler
@app.errorhandler(Exception)
def handle_exception(e):
    """Handle all uncaught exceptions"""
    logger.error(f"Unhandled exception: {e}", exc_info=True)
    
    # If it's an API request, return JSON
    if request.path.startswith('/api/'):
        return jsonify({
            'error': 'Internal server error',
            'message': str(e) if app.debug else 'An error occurred'
        }), 500
    
    # Otherwise return HTML
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head><title>Error - Trading Bot</title></head>
    <body style="font-family: Arial; padding: 50px; text-align: center;">
        <h1>🚀 Trading Bot</h1>
        <h2>❌ An error occurred</h2>
        <p>{{ error_message }}</p>
        <p><a href="/">← Back to application</a></p>
    </body>
    </html>
    """, error_message=str(e) if app.debug else 'An unexpected error occurred'), 500


# Background thread to process message queue
def process_message_queue():
    """Process messages from queue and send via Socket.IO"""
    while True:
        try:
            if not message_queue.empty() and ws_logger.clients_connected > 0:
                message = message_queue.get()
                socketio.emit('message', message)
        except Exception as e:
            logger.error(f"Error processing message queue: {e}")
        time.sleep(0.1)


# Enhanced initialization with error handling
def initialize_application():
    """Initialize the application with proper error handling"""
    try:
        print("🚀 Initializing Trading Bot Application...")
        
        # Create required directories
        os.makedirs('templates', exist_ok=True)
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        
        # Check critical files
        if not os.path.exists('templates/index.html'):
            print("⚠️  WARNING: templates/index.html not found!")
            print("   Application will run but frontend may not work properly.")
        
        # Initialize global instances
        global bot, console_manager
        
        print("✅ Application initialized successfully")
        return True
        
    except Exception as e:
        print(f"❌ Failed to initialize application: {e}")
        return False


# Start background thread
threading.Thread(target=process_message_queue, daemon=True).start()


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 TRADING BOT WEB APPLICATION - ULTIMATE ENHANCED EDITION")
    print("="*60)
    
    # Initialize application
    if not initialize_application():
        print("❌ Failed to initialize application. Exiting.")
        sys.exit(1)
    
    # Check setup
    if not setup_ok:
        print("⚠️  Setup issues detected but continuing...")
    
    print("\n✨ ENHANCED FEATURES:")
    print("  ✅ Persistent Telegram sessions (no repeated 2FA)")
    print("  ✅ Auto Break Even after target 1-4 (configurable)")
    print("  ✅ Enhanced Risk Management with margin level tracking")
    print("  ✅ Daily/Weekly loss limits & consecutive loss protection")
    print("  ✅ Improved Bybit connection with better error handling")
    print("  ✅ Fixed balance fetching issues for demo accounts")
    print("  ✅ TELETHON CONSOLE COMMANDS INTEGRATED")
    
    print("\n📁 Open in browser: http://localhost:5000")
    print("🌐 API Health Check: http://localhost:5000/api/health")
    print("💡 Debug mode: OFF")
    print("📌 Socket.IO: ENABLED")
    print("="*60 + "\n")
    
    try:
        # Run Flask app with SocketIO
        socketio.run(
            app, 
            debug=False,  # Disable debug to avoid double initialization
            host='0.0.0.0', 
            port=5001,
            allow_unsafe_werkzeug=True  # For development
        )
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)