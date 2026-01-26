"""
TelegramTradingBot Module

ENHANCED Trading Bot with improved Bybit connection and risk management.
This module provides the core TelegramTradingBot class for executing trades
based on signals received via Telegram, with integrated risk management,
position monitoring, and API key validation.

Dependencies:
- pybit.unified_trading.HTTP
- telegram (python-telegram-bot)
- requests
- configparser
- asyncio
- threading
"""

import os
import re
import json
import time
import logging
import configparser
import asyncio
import threading
from datetime import datetime, timedelta
import requests
import hmac
import hashlib

try:
    from telegram import Bot, Update
    from telegram.ext import Application, MessageHandler, filters, CallbackContext
except ImportError:
    raise ImportError("Missing python-telegram-bot library. Install with: pip install python-telegram-bot")

try:
    from pybit.unified_trading import HTTP
except ImportError:
    raise ImportError("Missing pybit library. Install with: pip install pybit==5.7.0")


# ===  CONFIGURATION CONSTANTS ===

CONFIG_FILE = "config.ini"
PROFILES_FILE = "trading_profiles.json"
RISK_TRACKING_FILE = "risk_tracking.json"
SESSIONS_DIR = "telegram_sessions"


# === GLOBAL LOGGER (must be set by main application) ===

ws_logger = None
socketio = None


def set_logger(logger_instance):
    """Set the global WebSocket logger instance"""
    global ws_logger
    ws_logger = logger_instance


def set_socketio(socketio_instance):
    """Set the global Socket.IO instance"""
    global socketio
    socketio = socketio_instance


# === IMPORTS FROM MODULAR STRUCTURE ===

from config.profile_manager import ProfileManager
from risk.risk_manager import EnhancedRiskManager
from core.position_manager import PositionManager
from telegram_integration.forwarder import TelegramForwarder


# === TELEGRAM TRADING BOT CLASS ===

class TelegramTradingBot:
    """ENHANCED Trading Bot with improved Bybit connection and risk management"""

    def __init__(self, ws_logger_instance=None, socketio_instance=None):
        print("🚀 Initializing bot...")

        # Set global instances if provided
        if ws_logger_instance:
            set_logger(ws_logger_instance)
        if socketio_instance:
            set_socketio(socketio_instance)

        self.config = self.load_config()
        self.profile_manager = ProfileManager()
        self.risk_manager = EnhancedRiskManager(ws_logger=ws_logger_instance)
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
        self.min_margin_level = float(self.config.get('RiskManagement', 'min_margin_level', fallback='1.5'))

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

            if self.telegram_chat_id and chat_id != self.telegram_chat_id:
                if ws_logger:
                    ws_logger.log(f"Message from unauthorized chat_id: {chat_id}", 'warning')
                return

            if ws_logger:
                ws_logger.log(f"Received message from Telegram (Chat ID: {chat_id})")
                ws_logger.log(f"Content: {message_text[:100]}...")

            signal = self.parse_trading_signal(message_text)

            if signal:
                if ws_logger:
                    ws_logger.log(f"Signal recognized: {signal['symbol']} {signal['position_type']}", 'success')

                if self.auto_execute_signals:
                    try:
                        if not self.bybit_client:
                            await self.send_telegram_message(f"No Bybit API connection")
                            return

                        result = self.execute_trade(signal)
                        await self.send_telegram_message(f"Auto-trade:\n{result}")

                    except Exception as e:
                        error_msg = f"Auto-trade error: {str(e)}"
                        if ws_logger:
                            ws_logger.log(error_msg, 'error')
                        await self.send_telegram_message(error_msg)
                else:
                    await self.send_telegram_message(
                        f"Signal recognized:\n"
                        f"{signal['symbol']} {signal['position_type'].upper()}\n"
                        f"Entry: {signal['entry_price']}\n"
                        f"Targets: {len(signal['targets'])}\n"
                        f"SL: {signal['stop_loss'] or 'None'}\n\n"
                        f"Auto-trade disabled - execute manually"
                    )
            else:
                if ws_logger:
                    ws_logger.log(f"Message is not a trading signal")

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error handling Telegram message: {e}", 'error')

    async def send_telegram_message(self, text):
        """Send message via Telegram"""
        try:
            if not self.telegram_bot or not self.telegram_chat_id:
                if ws_logger:
                    ws_logger.log("No Telegram configuration", 'warning')
                return False

            await self.telegram_bot.send_message(
                chat_id=self.telegram_chat_id,
                text=text,
                parse_mode='Markdown'
            )
            return True

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error sending message: {e}", 'error')
            return False

    def start_telegram_bot(self):
        """Start Telegram bot"""
        try:
            if not self.telegram_token:
                if ws_logger:
                    ws_logger.log("No Telegram token - bot won't start", 'warning')
                return False

            if self.telegram_running:
                if ws_logger:
                    ws_logger.log("Telegram bot already running", 'warning')
                return True

            if ws_logger:
                ws_logger.log("Starting Telegram bot...")

            self.telegram_app = Application.builder().token(self.telegram_token).build()

            message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, self.telegram_message_handler)
            self.telegram_app.add_handler(message_handler)

            self.telegram_bot = Bot(self.telegram_token)

            self.telegram_thread = threading.Thread(
                target=self._run_telegram_bot,
                daemon=True
            )
            self.telegram_thread.start()

            self.telegram_running = True

            if socketio:
                socketio.emit('status_update', {'telegram_bot': True})

            if ws_logger:
                ws_logger.log("Telegram bot started", 'success')
            return True

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error starting Telegram bot: {e}", 'error')
            return False

    def _run_telegram_bot(self):
        """Run bot in event loop"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            self.telegram_app.run_polling(
                poll_interval=1.0,
                timeout=10,
                drop_pending_updates=True
            )

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error in Telegram thread: {e}", 'error')
            self.telegram_running = False
            if socketio:
                socketio.emit('status_update', {'telegram_bot': False})

    def stop_telegram_bot(self):
        """Stop Telegram bot"""
        try:
            if not self.telegram_running:
                return True

            if ws_logger:
                ws_logger.log("Stopping Telegram bot...")

            self.telegram_running = False

            if self.telegram_app:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    loop.run_until_complete(self.telegram_app.stop())
                    loop.run_until_complete(self.telegram_app.shutdown())
                except Exception as e:
                    if ws_logger:
                        ws_logger.log(f"Error during stop: {e}", 'warning')
                finally:
                    loop.close()

            if self.telegram_thread and self.telegram_thread.is_alive():
                self.telegram_thread.join(timeout=5)

            self.telegram_bot = None
            self.telegram_app = None

            if socketio:
                socketio.emit('status_update', {'telegram_bot': False})

            if ws_logger:
                ws_logger.log("Telegram bot stopped", 'success')
            return True

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error stopping bot: {e}", 'error')
            return False

    def get_telegram_chat_id(self):
        """Automatically get Chat ID"""
        try:
            if not self.telegram_token:
                return None

            url = f"https://api.telegram.org/bot{self.telegram_token}/getUpdates"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('result'):
                    last_update = data['result'][-1]
                    chat_id = last_update.get('message', {}).get('chat', {}).get('id')

                    if chat_id:
                        if ws_logger:
                            ws_logger.log(f"Found Chat ID: {chat_id}", 'success')
                        return str(chat_id)

            return None

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error getting Chat ID: {e}", 'error')
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
                print(f"Error loading configuration: {e}")
        else:
            print("Creating new configuration...")
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
                print(f"Error creating configuration: {e}")

        return config

    def save_config(self):
        """Save configuration to file"""
        try:
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

            if not self.config.has_section('RiskManagement'):
                self.config.add_section('RiskManagement')
            self.config['RiskManagement']['enabled'] = str(self.risk_management_enabled)
            self.config['RiskManagement']['daily_loss_limit'] = str(self.daily_loss_limit)
            self.config['RiskManagement']['weekly_loss_limit'] = str(self.weekly_loss_limit)
            self.config['RiskManagement']['max_consecutive_losses'] = str(self.max_consecutive_losses)
            self.config['RiskManagement']['min_margin_level'] = str(self.min_margin_level)

            with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
                self.config.write(configfile)

            if ws_logger:
                ws_logger.log("Configuration saved", 'success')
            return True
        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error saving configuration: {e}", 'error')
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
            if ws_logger:
                ws_logger.log(f"Error saving profile: {e}", 'error')
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

            self.bybit_client = None

            return True
        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error loading profile: {e}", 'error')
            return False

    def test_api_keys_simple(self):
        """Simple API keys test"""
        try:
            api_key = self.bybit_api_key.strip()
            api_secret = self.bybit_api_secret.strip()

            if not api_key or not api_secret:
                if ws_logger:
                    ws_logger.log("No API keys", 'error')
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

            if ws_logger:
                ws_logger.log("Running simple HTTP test...")
            response = requests.get('https://api.bybit.com/v5/market/time', headers=headers, timeout=10)
            result = response.json()

            if result.get('retCode') == 0:
                if ws_logger:
                    ws_logger.log("Simple HTTP test successful", 'success')
                return True
            else:
                if ws_logger:
                    ws_logger.log(f"Simple HTTP test failed: {result.get('retMsg', 'Unknown error')}", 'error')
                return False

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"HTTP test failed: {e}", 'error')
            return False

    def initialize_bybit_client(self):
        try:
            if ws_logger:
                ws_logger.log("Starting Bybit client initialization...")

            if ws_logger:
                ws_logger.log(f"DEBUG: API key exists: {bool(self.bybit_api_key)}")
                ws_logger.log(f"DEBUG: API secret exists: {bool(self.bybit_api_secret)}")
                ws_logger.log(f"DEBUG: Demo mode: {self.use_demo_account}")

            if not self.bybit_api_key or not self.bybit_api_secret:
                if ws_logger:
                    ws_logger.log("Missing Bybit API keys", 'error')
                self.bybit_client = None
                return False

            clean_api_key = self.bybit_api_key.strip()
            clean_api_secret = self.bybit_api_secret.strip()

            use_testnet = self.use_demo_account

            if ws_logger:
                ws_logger.log(f"Bybit Configuration:")
                ws_logger.log(f"   Demo Mode: {self.use_demo_account}")
                ws_logger.log(f"   Use Testnet: {use_testnet}")
                ws_logger.log(f"   Position Mode: {self.position_mode}")
                ws_logger.log("Creating HTTP client...")

            try:
                if use_testnet:
                    if ws_logger:
                        ws_logger.log("Connecting to Bybit TESTNET (api-testnet.bybit.com)")
                    self.bybit_client = HTTP(
                        api_key=clean_api_key,
                        api_secret=clean_api_secret,
                        testnet=True
                    )
                else:
                    if ws_logger:
                        ws_logger.log("Connecting to Bybit MAINNET (api.bybit.com)")
                    self.bybit_client = HTTP(
                        api_key=clean_api_key,
                        api_secret=clean_api_secret,
                        testnet=False
                    )

                if ws_logger:
                    ws_logger.log("Testing Bybit connection...")
                server_time = self.bybit_client.get_server_time()

                if ws_logger:
                    ws_logger.log(f"DEBUG: Server time response: {server_time}")

                if server_time.get('retCode') == 0:
                    endpoint = "api-testnet.bybit.com" if use_testnet else "api.bybit.com"
                    mode = "DEMO (Testnet)" if use_testnet else "LIVE (Mainnet)"

                    if ws_logger:
                        ws_logger.log(f"Connected to Bybit API", 'success')
                        ws_logger.log(f"   Endpoint: {endpoint}")
                        ws_logger.log(f"   Mode: {mode}")

                    try:
                        if ws_logger:
                            ws_logger.log("Attempting to fetch balance...")
                        balance_response = self.bybit_client.get_wallet_balance(
                            accountType="UNIFIED"
                        )

                        if ws_logger:
                            ws_logger.log(f"DEBUG: Balance response code: {balance_response.get('retCode')}")

                        if balance_response.get('retCode') == 0:
                            balance_list = balance_response.get('result', {}).get('list', [])
                            if balance_list:
                                account = balance_list[0]
                                available = float(account.get('totalAvailableBalance', '0'))
                                wallet = float(account.get('totalWalletBalance', '0'))
                                if ws_logger:
                                    ws_logger.log(f"Wallet Balance: {wallet:.2f} USDT", 'success')
                                    ws_logger.log(f"Available Balance: {available:.2f} USDT", 'success')
                            else:
                                if ws_logger:
                                    ws_logger.log("Balance data empty but connection OK", 'warning')
                        elif balance_response.get('retCode') == 10001:
                            if ws_logger:
                                ws_logger.log("Account not activated or no balance (normal for new testnet)", 'warning')
                                ws_logger.log("For testnet: Get free USDT at testnet.bybit.com", 'info')
                        elif balance_response.get('retCode') == 10003:
                            if ws_logger:
                                ws_logger.log("Invalid API key - check if keys match the network (testnet/mainnet)", 'error')
                            return False
                        elif balance_response.get('retCode') == 10004:
                            if ws_logger:
                                ws_logger.log("Invalid signature - check API secret", 'error')
                            return False
                        else:
                            error_msg = balance_response.get('retMsg', 'Unknown error')
                            if ws_logger:
                                ws_logger.log(f"Balance fetch failed: {error_msg}", 'warning')

                    except Exception as balance_error:
                        if ws_logger:
                            ws_logger.log(f"Balance check failed but connection works: {balance_error}", 'warning')

                    if ws_logger:
                        ws_logger.log("Bybit client initialized successfully", 'success')
                    return True
                else:
                    error_msg = server_time.get('retMsg', 'Unknown error')
                    error_code = server_time.get('retCode', 'Unknown')
                    if ws_logger:
                        ws_logger.log(f"Connection failed: [{error_code}] {error_msg}", 'error')

                    if error_code == 10003:
                        if ws_logger:
                            ws_logger.log("Tip: Check if your API keys match the network:", 'warning')
                            ws_logger.log(f"   - Demo mode is {self.use_demo_account}", 'warning')
                            ws_logger.log("   - Testnet keys only work on testnet", 'warning')
                            ws_logger.log("   - Mainnet keys only work on mainnet", 'warning')
                    elif error_code == 10004:
                        if ws_logger:
                            ws_logger.log("Tip: Invalid API secret - check for typos", 'warning')

                    self.bybit_client = None
                    return False

            except Exception as e:
                if ws_logger:
                    ws_logger.log(f"Connection test error: {e}", 'error')
                    ws_logger.log(f"DEBUG: Exception details: {str(e)}", 'error')
                self.bybit_client = None
                return False

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Client initialization error: {e}", 'error')
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
                if ws_logger:
                    ws_logger.log(f"Fetched {len(subaccounts)} subaccounts", 'success')
                return subaccounts
            else:
                if ws_logger:
                    ws_logger.log(f"Error fetching subaccounts: {response.get('retMsg', 'Unknown error')}", 'error')
                return []

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error get_subaccounts: {e}", 'error')
            return []

    def get_wallet_balance(self):
        """Get wallet balance - ENHANCED ERROR HANDLING"""
        try:
            if not self.bybit_client:
                if ws_logger:
                    ws_logger.log("No Bybit client", 'error')
                if not self.initialize_bybit_client():
                    if self.use_demo_account:
                        if ws_logger:
                            ws_logger.log("Returning simulated demo balance", 'info')
                        return {
                            'success': True,
                            'totalMarginBalance': 10000.0,
                            'totalWalletBalance': 10000.0,
                            'totalAvailableBalance': 10000.0,
                            'accountType': 'DEMO'
                        }
                    return None

            if ws_logger:
                ws_logger.log("Fetching balance...")

            try:
                balance_response = None

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

                    if ws_logger:
                        ws_logger.log(f"DEBUG: UNIFIED balance response code: {balance_response.get('retCode')}")

                except Exception as unified_error:
                    if ws_logger:
                        ws_logger.log(f"UNIFIED account error: {unified_error}", 'warning')

                    try:
                        balance_response = self.bybit_client.get_wallet_balance(
                            accountType="CONTRACT"
                        )
                        if ws_logger:
                            ws_logger.log(f"DEBUG: CONTRACT balance response code: {balance_response.get('retCode')}")
                    except Exception as contract_error:
                        if ws_logger:
                            ws_logger.log(f"CONTRACT account error: {contract_error}", 'warning')

                if balance_response and balance_response.get('retCode') == 0:
                    balance_list = balance_response.get('result', {}).get('list', [])

                    if balance_list:
                        account = balance_list[0]

                        total_margin_balance = float(account.get('totalMarginBalance', account.get('totalEquity', '0')))
                        total_wallet_balance = float(account.get('totalWalletBalance', account.get('totalEquity', '0')))
                        total_available_balance = float(account.get('totalAvailableBalance', account.get('availableBalance', '0')))
                        account_type = account.get('accountType', 'UNIFIED')

                        if ws_logger:
                            ws_logger.log(f"Balance fetched successfully", 'success')
                            ws_logger.log(f"Available: {total_available_balance:.2f} USDT")
                            ws_logger.log(f"Wallet: {total_wallet_balance:.2f} USDT")
                            ws_logger.log(f"Margin: {total_margin_balance:.2f} USDT")

                        if socketio:
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

                if self.use_demo_account:
                    if ws_logger:
                        ws_logger.log("Using simulated demo balance", 'info')
                    return {
                        'success': True,
                        'totalMarginBalance': 10000.0,
                        'totalWalletBalance': 10000.0,
                        'totalAvailableBalance': 10000.0,
                        'accountType': 'DEMO'
                    }
                else:
                    if ws_logger:
                        ws_logger.log("Failed to get balance", 'error')
                    return None

            except Exception as api_error:
                if ws_logger:
                    ws_logger.log(f"Balance API error: {api_error}", 'error')

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
            if ws_logger:
                ws_logger.log(f"Error get_wallet_balance: {e}", 'error')

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
            if ws_logger:
                ws_logger.log(f"Error get_symbol_info: {e}", 'error')
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

            if qty_step > 0:
                qty = round(qty / qty_step) * qty_step

            if min_qty > 0 and qty < min_qty:
                qty = min_qty
            if max_qty > 0 and qty > max_qty:
                qty = max_qty

            if qty_step < 1:
                precision = len(str(qty_step).split('.')[-1])
            else:
                precision = 0

            return round(qty, precision)

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error format_quantity: {e}", 'error')
            return None

    def get_position_idx(self, position_type):
        """Get position index based on position mode"""
        if self.position_mode == 'hedge':
            return 1 if position_type.lower() == 'long' else 2
        else:
            return 0

    def parse_trading_signal(self, text):
        """Recognize and parse trading signal"""
        try:
            if ws_logger:
                ws_logger.log("Analyzing text for signal...", 'info')

            text_clean = re.sub(r'[^\w\s\-\.\:,/@#]', ' ', text)
            text_clean = ' '.join(text_clean.split())

            symbol_pattern = r'#?([A-Z0-9]+USDT?)\b'
            # Priority 1: Look for position type directly with Entry Zone (e.g., "Short Entry Zone")
            entry_with_position_pattern = r'\b(LONG|SHORT|Long|Short|long|short)\s+(?:Entry|entry|ENTRY)\s+(?:Zone|zone|ZONE)'
            # Priority 2: Look for position type, but exclude "-Term" context (avoid "Long-Term", "Short-Term")
            position_pattern = r'\b(LONG|SHORT|Long|Short|long|short)(?!\s*-\s*[Tt]erm)\b'
            entry_pattern = r'(?:Entry|entry|Wejście|ENTRY|Zone|zone|ZONE)[\s:]*([0-9]+\.?[0-9]*(?:\s*-\s*[0-9]+\.?[0-9]*)?)'
            target_pattern = r'(?:Target|target|TARGET|TP|tp|Cel|cel|CEL)[\s#]*(\d+)[\s:]*([0-9]+\.?[0-9]*)'
            sl_pattern = r'(?:Stop[\s-]?Loss|stop[\s-]?loss|SL|sl|STOP[\s-]?LOSS|Stop|stop|STOP)[\s:]*([0-9]+\.?[0-9]*)'

            symbol_match = re.search(symbol_pattern, text_clean)
            # First try to find position type with Entry Zone
            entry_with_position_match = re.search(entry_with_position_pattern, text_clean)
            if entry_with_position_match:
                position_match = entry_with_position_match  # Use position from "Short/Long Entry Zone"
            else:
                position_match = re.search(position_pattern, text_clean)  # Fallback to general pattern
            entry_match = re.search(entry_pattern, text_clean)
            target_matches = re.findall(target_pattern, text_clean)
            sl_match = re.search(sl_pattern, text_clean)

            if ws_logger:
                ws_logger.log(f"Symbol: {symbol_match.group(1) if symbol_match else 'Not found'}")
                ws_logger.log(f"Position: {position_match.group(1) if position_match else 'Not found'}")
                ws_logger.log(f"Entry: {entry_match.group(1) if entry_match else 'Not found'}")
                ws_logger.log(f"Targets: {len(target_matches)} found")
                ws_logger.log(f"Stop Loss: {sl_match.group(1) if sl_match else 'Not found'}")

            if not symbol_match or not position_match or not entry_match:
                if ws_logger:
                    ws_logger.log("Missing required signal elements", 'error')
                return None

            symbol = symbol_match.group(1).upper()
            if not symbol.endswith('USDT'):
                symbol += 'USDT'

            position_type = position_match.group(1).lower()

            entry_str = entry_match.group(1)
            if '-' in entry_str:
                prices = [float(p.strip()) for p in entry_str.split('-')]
                entry_price = sum(prices) / len(prices)
                if ws_logger:
                    ws_logger.log(f"Entry range {prices[0]} - {prices[1]}, using average: {entry_price}")
            else:
                entry_price = float(entry_str)

            targets = {}
            for target_num, target_price in target_matches:
                targets[int(target_num)] = float(target_price)

            stop_loss = float(sl_match.group(1)) if sl_match else None

            if entry_price <= 0:
                if ws_logger:
                    ws_logger.log("Invalid entry price", 'error')
                return None

            signal = {
                'symbol': symbol,
                'position_type': position_type,
                'entry_price': entry_price,
                'targets': targets,
                'stop_loss': stop_loss
            }

            if ws_logger:
                ws_logger.log("Signal recognized successfully!", 'success')
                ws_logger.log(f"{json.dumps(signal, indent=2)}")

            return signal

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error parsing signal: {e}", 'error')
            return None

    def analyze_trading_signal(self, signal):
        """Analyze trading signal"""
        try:
            analysis = []

            analysis.append(f"\nSIGNAL ANALYSIS:")
            analysis.append(f"{'=' * 40}")

            if signal['stop_loss']:
                entry = signal['entry_price']
                sl = signal['stop_loss']

                if signal['position_type'] == 'long':
                    risk_percent = ((entry - sl) / entry) * 100
                    analysis.append(f"Risk (to SL): {risk_percent:.2f}%")

                    for target_num, target_price in sorted(signal['targets'].items()):
                        reward_percent = ((target_price - entry) / entry) * 100
                        rr_ratio = reward_percent / risk_percent if risk_percent > 0 else 0
                        analysis.append(f"Target {target_num}: +{reward_percent:.2f}% (R:R = 1:{rr_ratio:.1f})")
                else:
                    risk_percent = ((sl - entry) / entry) * 100
                    analysis.append(f"Risk (to SL): {risk_percent:.2f}%")

                    for target_num, target_price in sorted(signal['targets'].items()):
                        reward_percent = ((entry - target_price) / entry) * 100
                        rr_ratio = reward_percent / risk_percent if risk_percent > 0 else 0
                        analysis.append(f"Target {target_num}: +{reward_percent:.2f}% (R:R = 1:{rr_ratio:.1f})")
            else:
                entry = signal['entry_price']

                for target_num, target_price in sorted(signal['targets'].items()):
                    if signal['position_type'] == 'long':
                        reward_percent = ((target_price - entry) / entry) * 100
                        analysis.append(f"Target {target_num}: +{reward_percent:.2f}%")
                    else:
                        reward_percent = ((entry - target_price) / entry) * 100
                        analysis.append(f"Target {target_num}: +{reward_percent:.2f}%")

            analysis.append(f"\nPOSITION MANAGEMENT:")
            analysis.append(f"* Position size: According to settings")
            if self.auto_tp_sl:
                analysis.append(f"* TP/SL: Automatic setup")
            if self.auto_breakeven:
                analysis.append(f"* Breakeven: After reaching TP{self.breakeven_after_target}")

            return '\n'.join(analysis)

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error analyzing signal: {e}", 'error')
            return "Signal analysis error"

    def execute_trade(self, signal):
        """Execute trade based on signal - WITH ENHANCED RISK MANAGEMENT"""
        try:
            balance_info = self.get_wallet_balance()

            if self.risk_management_enabled:
                can_trade, reason = self.risk_manager.can_trade(
                    self.daily_loss_limit,
                    self.weekly_loss_limit,
                    self.max_consecutive_losses,
                    balance_info,
                    self.min_margin_level
                )

                if not can_trade:
                    if ws_logger:
                        ws_logger.log(f"TRADE BLOCKED: {reason}", 'error')
                    return f"TRADE BLOCKED by Risk Management:\n{reason}"

            if not self.bybit_client:
                if not self.initialize_bybit_client():
                    return "Error initializing Bybit client"

            symbol = signal['symbol']
            side = "Buy" if signal['position_type'] == "long" else "Sell"
            entry_price = signal['entry_price']

            if ws_logger:
                ws_logger.log(f"Executing trade: {symbol} {side}", 'info')

            symbol_info = self.get_symbol_info(symbol)
            if not symbol_info:
                return f"Cannot get symbol info for {symbol}"

            if not balance_info or not balance_info.get('success'):
                return "Cannot get balance"

            available_balance = balance_info.get('totalAvailableBalance', 0)

            if available_balance <= 0:
                return f"No available balance (available: {available_balance} USDT)"

            amount_to_use = self.default_amount

            if self.use_percentage:
                amount_to_use = available_balance * (self.default_amount / 100.0)
                if ws_logger:
                    ws_logger.log(f"Using {self.default_amount}% of {available_balance:.2f} USDT = {amount_to_use:.2f} USDT")
            else:
                amount_to_use = min(self.default_amount, available_balance)
                if ws_logger:
                    ws_logger.log(f"Using fixed amount: {amount_to_use:.2f} USDT")

            position_value_usdt = amount_to_use * self.default_leverage
            if position_value_usdt > self.max_position_size:
                position_value_usdt = self.max_position_size
                amount_to_use = position_value_usdt / self.default_leverage
                if ws_logger:
                    ws_logger.log(f"Limited to max position: {self.max_position_size} USDT")

            qty = position_value_usdt / entry_price

            qty_formatted = self.format_quantity(qty, symbol_info)
            if not qty_formatted or qty_formatted <= 0:
                return f"Invalid position size: {qty}"

            if ws_logger:
                ws_logger.log(f"Position calculations:")
                ws_logger.log(f"   Margin: {amount_to_use:.2f} USDT")
                ws_logger.log(f"   Leverage: {self.default_leverage}x")
                ws_logger.log(f"   Position value: {position_value_usdt:.2f} USDT")
                ws_logger.log(f"   Quantity: {qty_formatted} {symbol}")

            try:
                if ws_logger:
                    ws_logger.log(f"Setting leverage {self.default_leverage}x...")
                leverage_response = self.bybit_client.set_leverage(
                    category="linear",
                    symbol=symbol,
                    buyLeverage=str(self.default_leverage),
                    sellLeverage=str(self.default_leverage)
                )

                if leverage_response.get('retCode') == 0:
                    if ws_logger:
                        ws_logger.log(f"Leverage set: {self.default_leverage}x", 'success')
                else:
                    if ws_logger:
                        ws_logger.log(f"Error setting leverage: {leverage_response.get('retMsg', 'Unknown error')}", 'warning')

            except Exception as e:
                if ws_logger:
                    ws_logger.log(f"Error setting leverage: {e}", 'warning')

            order_params = {
                'category': "linear",
                'symbol': symbol,
                'side': side,
                'orderType': "Market",
                'qty': str(qty_formatted),
                'positionIdx': self.get_position_idx(signal['position_type'])
            }

            if ws_logger:
                ws_logger.log(f"Sending order: {order_params}")

            if self.use_demo_account:
                if ws_logger:
                    ws_logger.log("DEMO MODE - simulating order", 'info')
                order_response = {
                    'retCode': 0,
                    'retMsg': 'Demo order simulated',
                    'result': {
                        'orderId': f'DEMO_{symbol}_{int(time.time())}',
                        'orderLinkId': f'demo_{int(time.time())}'
                    }
                }
            else:
                if ws_logger:
                    ws_logger.log("LIVE MODE - real order!", 'warning')
                order_response = self.bybit_client.place_order(**order_params)

            if order_response.get('retCode') == 0:
                order_id = order_response.get('result', {}).get('orderId', 'Unknown')
                if ws_logger:
                    ws_logger.log(f"Order executed! Order ID: {order_id}", 'success')

                if self.auto_tp_sl or self.auto_breakeven:
                    if ws_logger:
                        ws_logger.log(f"Adding position to TP/SL monitoring...")
                    self.position_manager.add_position(symbol, signal, order_id)

                    if not self.position_manager.monitoring_active:
                        self.position_manager.start_monitoring()

                result = f"""TRADE EXECUTED!
{'=' * 40}
Symbol: {symbol}
Type: {signal['position_type'].upper()}
Entry price: {entry_price}
Quantity: {qty_formatted}
Position value: {position_value_usdt:.2f} USDT
Leverage: {self.default_leverage}x
Mode: {'DEMO' if self.use_demo_account else 'LIVE'}
Order ID: {order_id}
{'=' * 40}"""

                if self.auto_tp_sl:
                    result += f"\nAuto TP/SL: Active (setting in 2 seconds...)"
                if self.auto_breakeven:
                    result += f"\nAuto Breakeven: Active (after reaching TP{self.breakeven_after_target})"

                return result

            else:
                error_msg = order_response.get('retMsg', 'Unknown error')

                if self.risk_management_enabled:
                    self.risk_manager.record_trade(-amount_to_use * 0.01, symbol)

                return f"Order execution error: {error_msg}"

        except Exception as e:
            if ws_logger:
                ws_logger.log(f"Error execute_trade: {e}", 'error')
            return f"Trade execution error: {str(e)}"
