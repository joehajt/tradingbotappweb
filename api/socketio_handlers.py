"""
Socket.IO Handlers Module

This module contains all Socket.IO event handlers for real-time communication
between the Flask server and connected WebSocket clients.

Event handlers:
  - connect: Handle new client connections
  - disconnect: Handle client disconnections
  - request_status: Request current system status
"""

from flask_socketio import emit


def register_socketio_handlers(socketio, bot, ws_logger, logger):
    """
    Register all Socket.IO event handlers with the SocketIO instance.

    Args:
        socketio: SocketIO instance
        bot: TelegramTradingBot instance
        ws_logger: WebSocketLogger instance
        logger: Logger instance
    """

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
