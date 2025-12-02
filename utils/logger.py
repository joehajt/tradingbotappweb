"""
WebSocket Logger Module
Handles real-time logging to Socket.IO clients
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


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
