"""
Flask API Routes Module

This module contains all Flask @app.route() endpoints for the Trading Bot API.
Includes endpoints for:
  - Health checks and configuration
  - Trading signal analysis and execution
  - Telegram bot management
  - Message forwarder (Telethon) integration
  - Position monitoring and management
  - Trading profiles and settings
  - Console command execution
  - Application logs management
  - WebSocket authentication
"""

import os
import asyncio
from datetime import datetime
from flask import render_template, render_template_string, request, jsonify, send_file


def register_routes(app, bot, console_manager, ws_logger, logger, auth_queue):
    """
    Register all Flask routes with the application.

    Args:
        app: Flask application instance
        bot: TelegramTradingBot instance
        console_manager: ConsoleManager instance
        ws_logger: WebSocketLogger instance
        logger: Logger instance
    """

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
                # Emit update via Socket.IO - will be done in socketio_handlers
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
                    # Emit update via Socket.IO - will be done in socketio_handlers
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
