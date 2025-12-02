"""
User Panel API Endpoints for Trading Bot Pro
Direct integration with app.py - guaranteed to work
"""

import sys
from flask import request, jsonify
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

# Initialize backend (singleton pattern)
_db = None
_user_manager = None
_auth = None

def init_backend():
    """Initialize backend modules once"""
    global _db, _user_manager, _auth
    if _db is None:
        _db = Database()
        _user_manager = UserManager(_db)
        _auth = AuthMiddleware()
        print("✅ User API backend initialized")

# Auth decorator
def require_auth(f):
    """Require JWT token authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'Missing or invalid token'}), 401

        token = auth_header.split(' ')[1]
        payload = _auth.validate_token(token)

        if not payload:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401

        # Pass user_id to the endpoint
        return f(user_id=payload['user_id'], *args, **kwargs)

    return decorated_function


def register_user_api(app):
    """Register all user panel API endpoints"""

    # Initialize backend
    init_backend()

    # ============================================
    # AUTHENTICATION ENDPOINTS
    # ============================================

    @app.route('/api/auth/register', methods=['POST'])
    def auth_register():
        """Register new user"""
        try:
            data = request.json

            # Validate
            if not data.get('email') or not data.get('password') or not data.get('full_name'):
                return jsonify({'success': False, 'error': 'Missing required fields'}), 400

            # Register
            result = _user_manager.register_user(
                email=data['email'],
                password=data['password'],
                full_name=data['full_name'],
                phone=data.get('phone'),
                country=data.get('country', 'PL'),
                timezone=data.get('timezone', 'Europe/Warsaw')
            )

            # Create session
            session = _auth.create_session(
                user_id=result['user_id'],
                remember_me=False,
                device_info=request.headers.get('User-Agent', 'Unknown'),
                ip_address=request.remote_addr
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
    def auth_login():
        """Login user"""
        try:
            data = request.json

            if not data.get('email') or not data.get('password'):
                return jsonify({'success': False, 'error': 'Email and password required'}), 400

            # Login (this creates session automatically)
            result = _user_manager.login_user(
                email=data['email'],
                password=data['password'],
                remember_me=data.get('remember_me', False),
                device_info=request.headers.get('User-Agent', 'Unknown'),
                ip_address=request.remote_addr
            )

            # Result already contains success, token, and user
            return jsonify(result)

        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 401
        except Exception as e:
            return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500


    @app.route('/api/auth/logout', methods=['POST'])
    @require_auth
    def auth_logout(user_id):
        """Logout user"""
        try:
            token = request.headers.get('Authorization').split(' ')[1]
            _user_manager.logout(user_id, token)

            return jsonify({
                'success': True,
                'message': 'Logged out successfully'
            })

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/auth/validate', methods=['GET'])
    @require_auth
    def auth_validate(user_id):
        """Validate token and get user info"""
        try:
            profile = _user_manager.get_user_profile(user_id)

            return jsonify({
                'success': True,
                'user': profile
            })

        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    # ============================================
    # PROFILE ENDPOINTS
    # ============================================

    @app.route('/api/user/profile', methods=['GET'])
    @require_auth
    def user_get_profile(user_id):
        """Get user profile"""
        try:
            profile = _user_manager.get_user_profile(user_id)
            return jsonify({'success': True, 'profile': profile})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/profile', methods=['PUT'])
    @require_auth
    def user_update_profile(user_id):
        """Update user profile"""
        try:
            data = request.json
            _user_manager.update_profile(
                user_id=user_id,
                full_name=data.get('full_name'),
                phone=data.get('phone'),
                country=data.get('country'),
                timezone=data.get('timezone')
            )

            return jsonify({'success': True, 'message': 'Profile updated'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    # ============================================
    # SECURITY ENDPOINTS
    # ============================================

    @app.route('/api/user/change-password', methods=['POST'])
    @require_auth
    def user_change_password(user_id):
        """Change password"""
        try:
            data = request.json

            if not data.get('current_password') or not data.get('new_password'):
                return jsonify({'success': False, 'error': 'Both passwords required'}), 400

            _user_manager.change_password(
                user_id,
                data['current_password'],
                data['new_password']
            )

            return jsonify({'success': True, 'message': 'Password changed'})
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/sessions', methods=['GET'])
    @require_auth
    def user_get_sessions(user_id):
        """Get active sessions"""
        try:
            sessions = _user_manager.get_user_sessions(user_id)
            return jsonify({'success': True, 'sessions': sessions})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/sessions/logout-all', methods=['POST'])
    @require_auth
    def user_logout_all(user_id):
        """Logout from all sessions"""
        try:
            count = _user_manager.logout_all_sessions(user_id)
            return jsonify({'success': True, 'message': f'Logged out from {count} sessions'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    # ============================================
    # API KEYS ENDPOINTS
    # ============================================

    @app.route('/api/user/api-keys', methods=['GET'])
    @require_auth
    def user_get_api_keys(user_id):
        """Get all API keys"""
        try:
            keys = _user_manager.get_user_api_keys(user_id)
            return jsonify({'success': True, 'api_keys': keys})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/api-keys', methods=['POST'])
    @require_auth
    def user_add_api_key(user_id):
        """Add new API key"""
        try:
            data = request.json

            required = ['key_name', 'platform', 'api_key', 'api_secret']
            for field in required:
                if not data.get(field):
                    return jsonify({'success': False, 'error': f'Missing: {field}'}), 400

            key_id = _user_manager.add_api_key(
                user_id=user_id,
                key_name=data['key_name'],
                platform=data['platform'],
                api_key=data['api_key'],
                api_secret=data['api_secret']
            )

            return jsonify({'success': True, 'message': 'API key added', 'key_id': key_id})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/api-keys/<int:key_id>', methods=['DELETE'])
    @require_auth
    def user_delete_api_key(user_id, key_id):
        """Delete API key"""
        try:
            _user_manager.delete_api_key(user_id, key_id)
            return jsonify({'success': True, 'message': 'API key deleted'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/api-keys/<int:key_id>/test', methods=['POST'])
    @require_auth
    def user_test_api_key(user_id, key_id):
        """Test API key connection"""
        try:
            result = _user_manager.test_api_key(user_id, key_id)
            return jsonify({'success': True, 'test_result': result})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    # ============================================
    # NOTIFICATION SETTINGS
    # ============================================

    @app.route('/api/user/notifications', methods=['GET'])
    @require_auth
    def user_get_notifications(user_id):
        """Get notification settings"""
        try:
            settings = _user_manager.get_notification_settings(user_id)
            return jsonify({'success': True, 'settings': settings})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/notifications', methods=['PUT'])
    @require_auth
    def user_update_notifications(user_id):
        """Update notification settings"""
        try:
            _user_manager.update_notification_settings(user_id, request.json)
            return jsonify({'success': True, 'message': 'Settings updated'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    # ============================================
    # TRADING SETTINGS (use /api/user/trading-config to avoid conflict)
    # ============================================

    @app.route('/api/user/trading-config', methods=['GET'])
    @require_auth
    def user_get_trading_config(user_id):
        """Get trading settings"""
        try:
            settings = _user_manager.get_trading_settings(user_id)
            return jsonify({'success': True, 'settings': settings})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    @app.route('/api/user/trading-config', methods=['PUT'])
    @require_auth
    def user_update_trading_config(user_id):
        """Update trading settings"""
        try:
            _user_manager.update_trading_settings(user_id, request.json)
            return jsonify({'success': True, 'message': 'Settings updated'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    # ============================================
    # STATISTICS
    # ============================================

    @app.route('/api/user/statistics', methods=['GET'])
    @require_auth
    def user_get_statistics(user_id):
        """Get trading statistics"""
        try:
            stats = _user_manager.get_user_statistics(user_id)
            return jsonify({'success': True, 'statistics': stats})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    # ============================================
    # ALIASES FOR COMPATIBILITY WITH FRONTEND
    # ============================================

    @app.route('/api/auth/profile', methods=['GET'])
    @require_auth
    def auth_get_profile(user_id):
        """Get user profile (alias)"""
        try:
            profile = _user_manager.get_user_profile(user_id)
            return jsonify({'success': True, 'user': profile})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/auth/update-profile', methods=['POST'])
    @require_auth
    def auth_update_profile(user_id):
        """Update profile (alias)"""
        try:
            data = request.json
            _user_manager.update_user_profile(
                user_id=user_id,
                full_name=data.get('full_name'),
                phone=data.get('phone'),
                country=data.get('country'),
                timezone=data.get('timezone')
            )

            return jsonify({'success': True, 'message': 'Profile updated'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/auth/change-password', methods=['POST'])
    @require_auth
    def auth_change_password(user_id):
        """Change password (alias)"""
        try:
            data = request.json

            if not data.get('current_password') or not data.get('new_password'):
                return jsonify({'success': False, 'error': 'Both passwords required'}), 400

            _user_manager.change_password(
                user_id,
                data['current_password'],
                data['new_password']
            )

            return jsonify({'success': True, 'message': 'Password changed'})
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e)}), 400
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/auth/save-api-keys', methods=['POST'])
    @require_auth
    def auth_save_api_keys(user_id):
        """Save API keys (simplified endpoint)"""
        try:
            data = request.json

            # Save as Bybit platform
            key_id = _user_manager.add_api_key(
                user_id=user_id,
                key_name='Bybit Main',
                platform='bybit',
                api_key=data.get('api_key'),
                api_secret=data.get('api_secret')
            )

            return jsonify({'success': True, 'message': 'API keys saved and encrypted', 'key_id': key_id})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/auth/delete-account', methods=['POST'])
    @require_auth
    def auth_delete_account(user_id):
        """Delete user account"""
        try:
            _user_manager.delete_user(user_id)
            return jsonify({'success': True, 'message': 'Account deleted successfully'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500


    print("✅ User panel API endpoints registered (20+ endpoints)")
    return True
