"""
API Routes for Trading Bot Pro User Panel
=========================================
All endpoints for user authentication, profile, settings, etc.
"""

import os
import sys
from datetime import datetime
from flask import jsonify, request
from functools import wraps

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'ignore')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'ignore')
    except Exception:
        pass

# Import backend modules
from database import Database
from user_manager import UserManager
from auth_middleware import AuthMiddleware

# Initialize
db = Database()
user_manager = UserManager(db)
auth = AuthMiddleware()


# ============================================
# AUTHENTICATION DECORATOR
# ============================================

def require_auth(f):
    """Decorator to require authentication for endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')

        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'Missing or invalid token'}), 401

        token = auth_header.split(' ')[1]

        # Validate token
        payload = auth.validate_token(token)
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401

        # Add user_id to kwargs
        kwargs['user_id'] = payload['user_id']
        return f(*args, **kwargs)

    return decorated_function


# ============================================
# AUTHENTICATION ENDPOINTS
# ============================================

def register_auth_routes(app):
    """Register authentication routes"""

    @app.route('/api/auth/register', methods=['POST'])
    def register():
        """Register new user"""
        try:
            data = request.json

            # Validate required fields
            required = ['email', 'password', 'full_name']
            for field in required:
                if not data.get(field):
                    return jsonify({
                        'success': False,
                        'error': f'Missing required field: {field}'
                    }), 400

            # Register user
            result = user_manager.register_user(
                email=data['email'],
                password=data['password'],
                full_name=data['full_name'],
                phone=data.get('phone'),
                country=data.get('country', 'PL'),
                timezone=data.get('timezone', 'Europe/Warsaw')
            )

            # Create session token
            device_info = request.headers.get('User-Agent', 'Unknown')
            ip_address = request.remote_addr

            session = auth.create_session(
                user_id=result['user_id'],
                remember_me=False,
                device_info=device_info,
                ip_address=ip_address
            )

            return jsonify({
                'success': True,
                'message': 'Registration successful',
                'user': {
                    'user_id': result['user_id'],
                    'email': data['email'],
                    'full_name': data['full_name']
                },
                'token': session['token']
            })

        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500


    @app.route('/api/auth/login', methods=['POST'])
    def login():
        """Login user"""
        try:
            data = request.json

            email = data.get('email')
            password = data.get('password')
            remember_me = data.get('remember_me', False)

            if not email or not password:
                return jsonify({
                    'success': False,
                    'error': 'Email and password required'
                }), 400

            # Login
            result = user_manager.login(email, password)

            # Create session
            device_info = request.headers.get('User-Agent', 'Unknown')
            ip_address = request.remote_addr

            session = auth.create_session(
                user_id=result['user_id'],
                remember_me=remember_me,
                device_info=device_info,
                ip_address=ip_address
            )

            return jsonify({
                'success': True,
                'message': 'Login successful',
                'user': result,
                'token': session['token']
            })

        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 401
        except Exception as e:
            return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500


    @app.route('/api/auth/logout', methods=['POST'])
    @require_auth
    def logout(user_id):
        """Logout user (invalidate current session)"""
        try:
            auth_header = request.headers.get('Authorization')
            token = auth_header.split(' ')[1]

            user_manager.logout(user_id, token)

            return jsonify({
                'success': True,
                'message': 'Logged out successfully'
            })

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/auth/validate', methods=['GET'])
    @require_auth
    def validate_token(user_id):
        """Validate token and return user info"""
        try:
            # Get user info
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id, email, full_name, phone, country,
                           avatar_initials, created_at, last_login,
                           two_factor_enabled
                    FROM users
                    WHERE user_id = ?
                """, (user_id,))

                row = cursor.fetchone()
                if not row:
                    return jsonify({'success': False, 'error': 'User not found'}), 404

                user = {
                    'user_id': row[0],
                    'email': row[1],
                    'full_name': row[2],
                    'phone': row[3],
                    'country': row[4],
                    'avatar_initials': row[5],
                    'created_at': row[6],
                    'last_login': row[7],
                    'two_factor_enabled': bool(row[8])
                }

                return jsonify({
                    'success': True,
                    'user': user
                })

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# PROFILE ENDPOINTS
# ============================================

def register_profile_routes(app):
    """Register profile management routes"""

    @app.route('/api/user/profile', methods=['GET'])
    @require_auth
    def get_profile(user_id):
        """Get user profile"""
        try:
            profile = user_manager.get_user_profile(user_id)
            return jsonify({
                'success': True,
                'profile': profile
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/profile', methods=['PUT'])
    @require_auth
    def update_profile(user_id):
        """Update user profile"""
        try:
            data = request.json

            user_manager.update_profile(
                user_id=user_id,
                full_name=data.get('full_name'),
                phone=data.get('phone'),
                country=data.get('country'),
                timezone=data.get('timezone')
            )

            return jsonify({
                'success': True,
                'message': 'Profile updated successfully'
            })

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# SECURITY ENDPOINTS
# ============================================

def register_security_routes(app):
    """Register security management routes"""

    @app.route('/api/user/change-password', methods=['POST'])
    @require_auth
    def change_password(user_id):
        """Change user password"""
        try:
            data = request.json

            current_password = data.get('current_password')
            new_password = data.get('new_password')

            if not current_password or not new_password:
                return jsonify({
                    'success': False,
                    'error': 'Current and new password required'
                }), 400

            user_manager.change_password(user_id, current_password, new_password)

            return jsonify({
                'success': True,
                'message': 'Password changed successfully'
            })

        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/sessions', methods=['GET'])
    @require_auth
    def get_sessions(user_id):
        """Get active sessions"""
        try:
            sessions = user_manager.get_user_sessions(user_id)
            return jsonify({
                'success': True,
                'sessions': sessions
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/sessions/logout-all', methods=['POST'])
    @require_auth
    def logout_all_sessions(user_id):
        """Logout from all sessions"""
        try:
            count = user_manager.logout_all_sessions(user_id)
            return jsonify({
                'success': True,
                'message': f'Logged out from {count} sessions'
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# API KEYS ENDPOINTS
# ============================================

def register_api_keys_routes(app):
    """Register API keys management routes"""

    @app.route('/api/user/api-keys', methods=['GET'])
    @require_auth
    def get_api_keys(user_id):
        """Get all API keys for user"""
        try:
            keys = user_manager.get_user_api_keys(user_id)
            return jsonify({
                'success': True,
                'api_keys': keys
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/api-keys', methods=['POST'])
    @require_auth
    def add_api_key(user_id):
        """Add new API key"""
        try:
            data = request.json

            required = ['key_name', 'platform', 'api_key', 'api_secret']
            for field in required:
                if not data.get(field):
                    return jsonify({
                        'success': False,
                        'error': f'Missing required field: {field}'
                    }), 400

            key_id = user_manager.add_api_key(
                user_id=user_id,
                key_name=data['key_name'],
                platform=data['platform'],
                api_key=data['api_key'],
                api_secret=data['api_secret']
            )

            return jsonify({
                'success': True,
                'message': 'API key added successfully',
                'key_id': key_id
            })

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/api-keys/<int:key_id>', methods=['DELETE'])
    @require_auth
    def delete_api_key(user_id, key_id):
        """Delete API key"""
        try:
            user_manager.delete_api_key(user_id, key_id)
            return jsonify({
                'success': True,
                'message': 'API key deleted successfully'
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/api-keys/<int:key_id>/test', methods=['POST'])
    @require_auth
    def test_api_key(user_id, key_id):
        """Test API key connection"""
        try:
            result = user_manager.test_api_key(user_id, key_id)
            return jsonify({
                'success': True,
                'test_result': result
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# NOTIFICATION SETTINGS ENDPOINTS
# ============================================

def register_notification_routes(app):
    """Register notification settings routes"""

    @app.route('/api/user/notifications', methods=['GET'])
    @require_auth
    def get_notification_settings(user_id):
        """Get notification settings"""
        try:
            settings = user_manager.get_notification_settings(user_id)
            return jsonify({
                'success': True,
                'settings': settings
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/notifications', methods=['PUT'])
    @require_auth
    def update_notification_settings(user_id):
        """Update notification settings"""
        try:
            data = request.json
            user_manager.update_notification_settings(user_id, data)

            return jsonify({
                'success': True,
                'message': 'Notification settings updated'
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# TRADING SETTINGS ENDPOINTS
# ============================================

def register_trading_routes(app):
    """Register trading settings routes"""

    @app.route('/api/user/trading-settings', methods=['GET'])
    @require_auth
    def get_user_trading_settings(user_id):
        """Get trading settings"""
        try:
            settings = user_manager.get_trading_settings(user_id)
            return jsonify({
                'success': True,
                'settings': settings
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/trading-settings', methods=['PUT'])
    @require_auth
    def update_user_trading_settings(user_id):
        """Update trading settings"""
        try:
            data = request.json
            user_manager.update_trading_settings(user_id, data)

            return jsonify({
                'success': True,
                'message': 'Trading settings updated'
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# STATISTICS ENDPOINTS
# ============================================

def register_statistics_routes(app):
    """Register statistics routes"""

    @app.route('/api/user/statistics', methods=['GET'])
    @require_auth
    def get_statistics(user_id):
        """Get user trading statistics"""
        try:
            stats = user_manager.get_user_statistics(user_id)
            return jsonify({
                'success': True,
                'statistics': stats
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# REGISTER ALL ROUTES
# ============================================

def register_all_routes(app):
    """Register all API routes"""
    register_auth_routes(app)
    register_profile_routes(app)
    register_security_routes(app)
    register_api_keys_routes(app)
    register_notification_routes(app)
    register_trading_routes(app)
    register_statistics_routes(app)

    print("✅ All user panel API routes registered")
