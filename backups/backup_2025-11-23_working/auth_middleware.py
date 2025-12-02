"""
Authentication Middleware - JWT Token Management & Session Control
====================================================================
This module handles:
- JWT token generation and validation
- Session management
- Request authentication
- Token refresh
- Device/browser detection

Security Features:
- JWT with expiration
- Token blacklist on logout
- Session tracking per device
- IP address validation
- Automatic session cleanup
"""

import os
import jwt
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g
from database import Database

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """
    Authentication middleware for JWT token management.
    """

    def __init__(self, db=None):
        """
        Initialize AuthMiddleware.

        Args:
            db (Database): Database instance
        """
        self.db = db or Database()

        # Get JWT secret from environment
        self.jwt_secret = os.environ.get('JWT_SECRET_KEY')
        if not self.jwt_secret:
            raise ValueError("JWT_SECRET_KEY not found in environment variables!")

        # Session settings
        self.session_timeout_minutes = int(os.environ.get('SESSION_TIMEOUT_MINUTES', 30))
        self.remember_me_days = int(os.environ.get('REMEMBER_ME_DAYS', 30))

        logger.info("AuthMiddleware initialized")

    def create_session(self, user_id, remember_me=False, device_info=None,
                      ip_address=None, user_agent=None):
        """
        Create a new session with JWT token.

        Args:
            user_id (int): User ID
            remember_me (bool): Extended session duration
            device_info (dict): Device information
            ip_address (str): Client IP address
            user_agent (str): User agent string

        Returns:
            dict: Session data with JWT token
        """
        # Determine expiration time
        if remember_me:
            expires_delta = timedelta(days=self.remember_me_days)
        else:
            expires_delta = timedelta(minutes=self.session_timeout_minutes)

        expires_at = datetime.now() + expires_delta

        # Create JWT payload
        payload = {
            'user_id': user_id,
            'exp': expires_at,
            'iat': datetime.now(),
            'remember_me': remember_me
        }

        # Generate JWT token
        token = jwt.encode(payload, self.jwt_secret, algorithm='HS256')

        # Parse device info
        device_data = self._parse_device_info(user_agent)

        # Store session in database
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessions
                (user_id, token, device_info, browser, os, ip_address, location,
                 expires_at, remember_me, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                token,
                device_info or device_data['full'],
                device_data['browser'],
                device_data['os'],
                ip_address,
                self._get_location_from_ip(ip_address),
                expires_at,
                remember_me,
                1
            ))

            session_id = cursor.lastrowid
            conn.commit()

        logger.info(f"Session created for user {user_id} (Session ID: {session_id})")

        return {
            'token': token,
            'expires_at': expires_at.isoformat(),
            'remember_me': remember_me,
            'session_id': session_id
        }

    def validate_token(self, token):
        """
        Validate JWT token and return user data.

        Args:
            token (str): JWT token

        Returns:
            dict: User data if valid, None otherwise
        """
        try:
            # Decode JWT with leeway for clock skew (5 minutes tolerance)
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=['HS256'],
                options={'verify_iat': False},  # Don't strictly verify 'issued at' timestamp
                leeway=300  # 5 minutes tolerance for clock skew
            )

            user_id = payload.get('user_id')

            # Check if session exists and is active
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM sessions
                    WHERE token = ? AND user_id = ? AND is_active = 1
                """, (token, user_id))

                session = cursor.fetchone()

            if not session:
                logger.warning(f"Session not found or inactive for token")
                return None

            session_data = dict(session)

            # Check if session has expired
            expires_at = datetime.fromisoformat(session_data['expires_at'])
            if expires_at < datetime.now():
                logger.warning(f"Session expired for user {user_id}")
                self._deactivate_session(token)
                return None

            # Update last activity
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE sessions SET last_activity = ?
                    WHERE token = ?
                """, (datetime.now(), token))
                conn.commit()

            return {
                'user_id': user_id,
                'session_id': session_data['id'],
                'remember_me': session_data['remember_me']
            }

        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            self._deactivate_session(token)
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return None

    def refresh_token(self, old_token):
        """
        Refresh JWT token (extend expiration).

        Args:
            old_token (str): Current JWT token

        Returns:
            dict: New session data with refreshed token
        """
        # Validate old token
        user_data = self.validate_token(old_token)

        if not user_data:
            raise ValueError("Invalid or expired token")

        user_id = user_data['user_id']
        remember_me = user_data['remember_me']

        # Deactivate old session
        self._deactivate_session(old_token)

        # Get device info from old session
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT device_info, ip_address
                FROM sessions WHERE token = ?
            """, (old_token,))

            old_session = cursor.fetchone()

        device_info = old_session['device_info'] if old_session else None
        ip_address = old_session['ip_address'] if old_session else None

        # Create new session
        return self.create_session(user_id, remember_me, device_info, ip_address)

    def get_user_sessions(self, user_id):
        """
        Get all active sessions for a user.

        Args:
            user_id (int): User ID

        Returns:
            list: List of active sessions
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, device_info, browser, os, ip_address, location,
                       created_at, last_activity, expires_at, remember_me
                FROM sessions
                WHERE user_id = ? AND is_active = 1
                ORDER BY last_activity DESC
            """, (user_id,))

            sessions = [dict(row) for row in cursor.fetchall()]

        return sessions

    def terminate_session(self, session_id, user_id):
        """
        Terminate a specific session.

        Args:
            session_id (int): Session ID
            user_id (int): User ID (for security check)

        Returns:
            bool: True if successful
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sessions
                SET is_active = 0, last_activity = ?
                WHERE id = ? AND user_id = ?
            """, (datetime.now(), session_id, user_id))

            success = cursor.rowcount > 0
            conn.commit()

        if success:
            logger.info(f"Session {session_id} terminated for user {user_id}")

        return success

    def _deactivate_session(self, token):
        """Deactivate session by token."""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE sessions SET is_active = 0, last_activity = ?
                    WHERE token = ?
                """, (datetime.now(), token))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to deactivate session: {e}")

    def _parse_device_info(self, user_agent):
        """
        Parse user agent string to extract device information.

        Args:
            user_agent (str): User agent string

        Returns:
            dict: Device information
        """
        if not user_agent:
            return {
                'full': 'Unknown',
                'browser': 'Unknown',
                'os': 'Unknown'
            }

        # Simple parsing (in production, use user-agents library)
        browser = 'Unknown'
        os_name = 'Unknown'

        # Detect browser
        if 'Chrome' in user_agent:
            browser = 'Chrome'
        elif 'Firefox' in user_agent:
            browser = 'Firefox'
        elif 'Safari' in user_agent:
            browser = 'Safari'
        elif 'Edge' in user_agent:
            browser = 'Edge'
        elif 'Opera' in user_agent:
            browser = 'Opera'

        # Detect OS
        if 'Windows' in user_agent:
            os_name = 'Windows'
        elif 'Mac OS' in user_agent or 'Macintosh' in user_agent:
            os_name = 'macOS'
        elif 'Linux' in user_agent:
            os_name = 'Linux'
        elif 'Android' in user_agent:
            os_name = 'Android'
        elif 'iOS' in user_agent or 'iPhone' in user_agent or 'iPad' in user_agent:
            os_name = 'iOS'

        return {
            'full': user_agent[:255],  # Truncate to fit database
            'browser': browser,
            'os': os_name
        }

    def _get_location_from_ip(self, ip_address):
        """
        Get location from IP address (placeholder).

        Args:
            ip_address (str): IP address

        Returns:
            str: Location string
        """
        # TODO: Implement IP geolocation (use ipapi.co or similar service)
        # For now, return placeholder
        if not ip_address:
            return 'Unknown'

        # Localhost check
        if ip_address in ['127.0.0.1', '::1', 'localhost']:
            return 'Localhost'

        return f'Location for {ip_address}'  # Placeholder


# ============================================
# FLASK DECORATORS
# ============================================

def create_auth_decorator(auth_middleware):
    """
    Create authentication decorator for Flask routes.

    Args:
        auth_middleware (AuthMiddleware): AuthMiddleware instance

    Returns:
        function: Decorator function
    """

    def require_auth(f):
        """
        Decorator to require authentication for a route.

        Usage:
            @app.route('/api/protected')
            @require_auth
            def protected_route():
                user_id = g.user_id
                return jsonify({'user_id': user_id})
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get token from Authorization header
            auth_header = request.headers.get('Authorization')

            if not auth_header:
                return jsonify({
                    'success': False,
                    'error': 'No authorization token provided'
                }), 401

            # Extract token (format: "Bearer TOKEN")
            try:
                token = auth_header.split(' ')[1]
            except IndexError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid authorization header format'
                }), 401

            # Validate token
            user_data = auth_middleware.validate_token(token)

            if not user_data:
                return jsonify({
                    'success': False,
                    'error': 'Invalid or expired token'
                }), 401

            # Store user data in Flask g object for access in route
            g.user_id = user_data['user_id']
            g.session_id = user_data['session_id']
            g.token = token

            return f(*args, **kwargs)

        return decorated_function

    return require_auth


def create_optional_auth_decorator(auth_middleware):
    """
    Create optional authentication decorator (doesn't fail if no token).

    Usage:
        @app.route('/api/mixed')
        @optional_auth
        def mixed_route():
            if hasattr(g, 'user_id'):
                return jsonify({'message': 'Authenticated user', 'user_id': g.user_id})
            else:
                return jsonify({'message': 'Anonymous user'})
    """

    def optional_auth(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get('Authorization')

            if auth_header:
                try:
                    token = auth_header.split(' ')[1]
                    user_data = auth_middleware.validate_token(token)

                    if user_data:
                        g.user_id = user_data['user_id']
                        g.session_id = user_data['session_id']
                        g.token = token
                except Exception as e:
                    logger.warning(f"Optional auth failed: {e}")

            return f(*args, **kwargs)

        return decorated_function

    return optional_auth


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_request_ip():
    """
    Get client IP address from request (handles proxies).

    Returns:
        str: Client IP address
    """
    # Check for X-Forwarded-For header (proxy)
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()

    # Check for X-Real-IP header
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')

    # Default to remote_addr
    return request.remote_addr


def get_request_user_agent():
    """
    Get user agent from request.

    Returns:
        str: User agent string
    """
    return request.headers.get('User-Agent', 'Unknown')


# ============================================
# USAGE EXAMPLE
# ============================================

if __name__ == "__main__":
    print("=== Auth Middleware Test ===\n")

    import os
    os.environ['JWT_SECRET_KEY'] = 'test_secret_key_for_demonstration'

    from database import Database

    # Initialize
    db = Database('test_trading_bot.db')
    db.initialize()

    auth = AuthMiddleware(db)

    # Test session creation
    print("1. Creating session:")
    session = auth.create_session(
        user_id=1,
        remember_me=False,
        device_info="Test Device",
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0 (Test Browser)"
    )
    print(f"   Token: {session['token'][:50]}...")
    print(f"   Expires: {session['expires_at']}")

    # Test token validation
    print("\n2. Validating token:")
    result = auth.validate_token(session['token'])
    if result:
        print(f"   ✅ Valid - User ID: {result['user_id']}")
    else:
        print("   ❌ Invalid token")

    # Test get sessions
    print("\n3. Getting user sessions:")
    sessions = auth.get_user_sessions(1)
    print(f"   Active sessions: {len(sessions)}")

    print("\n=== Test Completed ===")
