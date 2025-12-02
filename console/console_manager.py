"""
Console Manager Module

Manager for interactive console and redirections with Telethon integration.
Handles console output redirection, command execution, and Telethon connectivity.
"""

import sys
import io
import asyncio


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
