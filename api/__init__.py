"""
API Package

This package contains Flask routes and Socket.IO handlers for the Trading Bot API.

Modules:
  - routes: Flask HTTP endpoint handlers
  - socketio_handlers: Socket.IO event handlers
"""

from .routes import register_routes
from .socketio_handlers import register_socketio_handlers

__all__ = ['register_routes', 'register_socketio_handlers']
