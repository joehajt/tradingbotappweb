"""
Telegram Message Forwarder Module

This module provides the TelegramForwarder class for monitoring Telegram channels
and groups, detecting trading signals, and forwarding messages. It uses Telethon
for persistent session management and async/await for efficient message handling.

Features:
- Persistent Telegram session management
- Multi-channel monitoring with polling
- Trading signal detection and parsing
- Message forwarding to target chat
- Auto-trading signal execution (optional)
- Session reuse across restarts
"""

import os
import re
import json
import time
import logging
import asyncio
import threading
from datetime import datetime
from flask_socketio import SocketIO

# Telethon imports for Telegram client
try:
    from telethon.sync import TelegramClient
    from telethon import TelegramClient as AsyncTelegramClient, events
    from telethon.tl.types import Channel, Chat, User
    from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError, FloodWaitError
    TELETHON_AVAILABLE = True
except ImportError:
    TELETHON_AVAILABLE = False

# Directory for persistent Telegram sessions
SESSIONS_DIR = "telegram_sessions"

# Global logger instance (to be set by main app)
ws_logger = None
socketio = None


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

            with open('config.ini', 'w', encoding='utf-8') as configfile:
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
                # Import global auth_queue at function level
                from __main__ import auth_queue

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
                # Import global auth_queue at function level
                from __main__ import auth_queue

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
