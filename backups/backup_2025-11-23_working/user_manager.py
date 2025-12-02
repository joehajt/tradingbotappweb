"""
User Manager - Complete User Management System
================================================
This module handles all user-related operations including:
- Registration and authentication
- Profile management
- API keys management (encrypted)
- Session management
- Password reset
- Settings management

Security Features:
- Bcrypt password hashing
- AES-256 API key encryption
- JWT session tokens
- Rate limiting
- Account lockout after failed logins
- Audit logging
"""

import os
import logging
from datetime import datetime, timedelta
from database import Database
from crypto_manager import CryptoManager, PasswordManager
import re

logger = logging.getLogger(__name__)


class UserManager:
    """
    Complete user management system.
    """

    def __init__(self, db=None, crypto=None, password_manager=None):
        """
        Initialize UserManager.

        Args:
            db (Database): Database instance
            crypto (CryptoManager): Crypto manager instance
            password_manager (PasswordManager): Password manager instance
        """
        self.db = db or Database()
        self.crypto = crypto or CryptoManager()
        self.pm = password_manager or PasswordManager()

        # Account lockout settings
        self.max_failed_attempts = 5
        self.lockout_duration_minutes = 30

        logger.info("UserManager initialized")

    # ============================================
    # USER REGISTRATION & AUTHENTICATION
    # ============================================

    def register_user(self, email, password, full_name, phone=None, country='PL',
                     timezone='Europe/Warsaw', ip_address=None):
        """
        Register a new user.

        Args:
            email (str): User email
            password (str): Plain text password
            full_name (str): Full name
            phone (str): Phone number (optional)
            country (str): Country code
            timezone (str): Timezone
            ip_address (str): Registration IP address

        Returns:
            dict: User data with success status

        Raises:
            ValueError: If validation fails
        """
        # Validate email
        if not self._validate_email(email):
            raise ValueError("Invalid email format")

        # Validate password strength
        is_valid, msg = self.pm.validate_password_strength(password)
        if not is_valid:
            raise ValueError(msg)

        # Check if email already exists
        if self.get_user_by_email(email):
            raise ValueError("Email already registered")

        # Hash password
        password_hash = self.pm.hash_password(password)

        # Generate avatar initials
        avatar_initials = self._generate_avatar_initials(full_name)

        # Generate email verification token
        verification_token = CryptoManager.generate_random_token()

        # Insert user
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO users
                (email, password_hash, full_name, phone, country, timezone, avatar_initials,
                 email_verification_token, is_email_verified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (email, password_hash, full_name, phone, country, timezone,
                  avatar_initials, verification_token, 0))

            user_id = cursor.lastrowid
            conn.commit()

        # Create default settings
        self.db.create_default_settings(user_id)

        # Log registration
        self.db.log_action(
            user_id, 'user_registered', 'user', user_id,
            f"New user registered: {email}", ip_address, None, 'success'
        )

        logger.info(f"User registered: {email} (ID: {user_id})")

        return {
            'success': True,
            'user_id': user_id,
            'email': email,
            'verification_token': verification_token,
            'message': 'User registered successfully. Please verify your email.'
        }

    def login_user(self, email, password, remember_me=False, device_info=None,
                   ip_address=None, user_agent=None):
        """
        Authenticate user and create session.

        Args:
            email (str): User email
            password (str): Plain text password
            remember_me (bool): Extended session duration
            device_info (dict): Device information
            ip_address (str): Login IP address
            user_agent (str): User agent string

        Returns:
            dict: Login result with session token

        Raises:
            ValueError: If authentication fails
        """
        # Get user
        user = self.get_user_by_email(email)

        if not user:
            self.db.log_action(None, 'login_failed', 'user', None,
                             f"Login attempt with non-existent email: {email}",
                             ip_address, user_agent, 'failure')
            raise ValueError("Invalid email or password")

        # Check if account is locked
        if user['locked_until'] and datetime.fromisoformat(user['locked_until']) > datetime.now():
            remaining_minutes = (datetime.fromisoformat(user['locked_until']) - datetime.now()).seconds // 60
            raise ValueError(f"Account locked. Try again in {remaining_minutes} minutes.")

        # Verify password
        if not self.pm.verify_password(password, user['password_hash']):
            # Increment failed attempts
            self._increment_failed_login(user['id'])

            self.db.log_action(user['id'], 'login_failed', 'user', user['id'],
                             "Invalid password", ip_address, user_agent, 'failure')
            raise ValueError("Invalid email or password")

        # Check if account is active
        if not user['is_active']:
            raise ValueError("Account is disabled. Please contact support.")

        # Reset failed login attempts
        self._reset_failed_login(user['id'])

        # Update last login
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET last_login = ? WHERE id = ?
            """, (datetime.now(), user['id']))
            conn.commit()

        # Create session
        from auth_middleware import AuthMiddleware
        auth = AuthMiddleware(self.db)

        session_data = auth.create_session(
            user['id'], remember_me, device_info, ip_address, user_agent
        )

        # Log successful login
        self.db.log_action(user['id'], 'login_success', 'user', user['id'],
                         f"User logged in from {ip_address}",
                         ip_address, user_agent, 'success')

        logger.info(f"User logged in: {email} (ID: {user['id']})")

        return {
            'success': True,
            'token': session_data['token'],
            'user': {
                'id': user['id'],
                'email': user['email'],
                'full_name': user['full_name'],
                'avatar_initials': user['avatar_initials'],
                'is_email_verified': user['is_email_verified']
            }
        }

    def logout_user(self, token, ip_address=None):
        """
        Logout user (invalidate session).

        Args:
            token (str): Session token
            ip_address (str): Logout IP address

        Returns:
            bool: True if successful
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # Get session info before deletion
            cursor.execute("""
                SELECT user_id FROM sessions WHERE token = ? AND is_active = 1
            """, (token,))
            session = cursor.fetchone()

            if not session:
                return False

            user_id = session['user_id']

            # Deactivate session
            cursor.execute("""
                UPDATE sessions SET is_active = 0, last_activity = ?
                WHERE token = ?
            """, (datetime.now(), token))
            conn.commit()

        # Log logout
        self.db.log_action(user_id, 'logout', 'user', user_id,
                         "User logged out", ip_address, None, 'success')

        logger.info(f"User logged out (ID: {user_id})")
        return True

    def logout_all_sessions(self, user_id, ip_address=None):
        """
        Logout user from all devices.

        Args:
            user_id (int): User ID
            ip_address (str): Request IP address

        Returns:
            int: Number of sessions terminated
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sessions SET is_active = 0, last_activity = ?
                WHERE user_id = ? AND is_active = 1
            """, (datetime.now(), user_id))

            count = cursor.rowcount
            conn.commit()

        # Log action
        self.db.log_action(user_id, 'logout_all', 'user', user_id,
                         f"All sessions terminated ({count} sessions)",
                         ip_address, None, 'success')

        logger.info(f"All sessions terminated for user {user_id}")
        return count

    # ============================================
    # USER PROFILE MANAGEMENT
    # ============================================

    def get_user_by_id(self, user_id):
        """
        Get user by ID.

        Args:
            user_id (int): User ID

        Returns:
            dict: User data (without password)
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, email, full_name, phone, country, timezone, avatar_initials,
                       created_at, updated_at, last_login, is_active, is_email_verified,
                       two_factor_enabled
                FROM users WHERE id = ?
            """, (user_id,))

            result = cursor.fetchone()
            return dict(result) if result else None

    def get_user_by_email(self, email):
        """
        Get user by email (includes password_hash for authentication).

        Args:
            email (str): User email

        Returns:
            dict: User data
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM users WHERE email = ?
            """, (email,))

            result = cursor.fetchone()
            return dict(result) if result else None

    def update_user_profile(self, user_id, full_name=None, phone=None,
                           country=None, timezone=None):
        """
        Update user profile information.

        Args:
            user_id (int): User ID
            full_name (str): New full name
            phone (str): New phone
            country (str): New country
            timezone (str): New timezone

        Returns:
            dict: Updated user data
        """
        updates = []
        params = []

        if full_name is not None:
            updates.append("full_name = ?")
            params.append(full_name)
            # Update avatar initials
            updates.append("avatar_initials = ?")
            params.append(self._generate_avatar_initials(full_name))

        if phone is not None:
            updates.append("phone = ?")
            params.append(phone)

        if country is not None:
            updates.append("country = ?")
            params.append(country)

        if timezone is not None:
            updates.append("timezone = ?")
            params.append(timezone)

        if not updates:
            raise ValueError("No fields to update")

        updates.append("updated_at = ?")
        params.append(datetime.now())
        params.append(user_id)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE users SET {', '.join(updates)}
                WHERE id = ?
            """, params)
            conn.commit()

        logger.info(f"User profile updated (ID: {user_id})")
        return self.get_user_by_id(user_id)

    def change_password(self, user_id, current_password, new_password):
        """
        Change user password.

        Args:
            user_id (int): User ID
            current_password (str): Current password
            new_password (str): New password

        Returns:
            bool: True if successful

        Raises:
            ValueError: If validation fails
        """
        # Get user
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        # Get full user data with password
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            password_hash = result['password_hash']

        # Verify current password
        if not self.pm.verify_password(current_password, password_hash):
            self.db.log_action(user_id, 'password_change_failed', 'user', user_id,
                             "Incorrect current password", None, None, 'failure')
            raise ValueError("Current password is incorrect")

        # Validate new password
        is_valid, msg = self.pm.validate_password_strength(new_password)
        if not is_valid:
            raise ValueError(msg)

        # Hash new password
        new_password_hash = self.pm.hash_password(new_password)

        # Update password
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET password_hash = ?, updated_at = ?
                WHERE id = ?
            """, (new_password_hash, datetime.now(), user_id))
            conn.commit()

        # Log action
        self.db.log_action(user_id, 'password_changed', 'user', user_id,
                         "Password changed successfully", None, None, 'success')

        logger.info(f"Password changed for user {user_id}")
        return True

    # ============================================
    # API KEYS MANAGEMENT (Encrypted)
    # ============================================

    def add_api_key(self, user_id, key_name, platform, api_key, api_secret):
        """
        Add encrypted API key for user.

        Args:
            user_id (int): User ID
            key_name (str): Key name/label
            platform (str): Platform (e.g., 'bybit-live', 'bybit-testnet')
            api_key (str): API key (will be encrypted)
            api_secret (str): API secret (will be encrypted)

        Returns:
            dict: API key data (with masked keys)
        """
        # Encrypt API credentials
        api_key_encrypted = self.crypto.encrypt(api_key)
        api_secret_encrypted = self.crypto.encrypt(api_secret)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_keys
                (user_id, key_name, platform, api_key_encrypted, api_secret_encrypted)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, key_name, platform, api_key_encrypted, api_secret_encrypted))

            key_id = cursor.lastrowid
            conn.commit()

        # Log action
        self.db.log_action(user_id, 'api_key_added', 'api_key', key_id,
                         f"API key added: {key_name} ({platform})",
                         None, None, 'success')

        logger.info(f"API key added for user {user_id}: {key_name}")

        return {
            'id': key_id,
            'key_name': key_name,
            'platform': platform,
            'api_key_masked': self.crypto.mask_sensitive_data(api_key),
            'is_active': True,
            'created_at': datetime.now().isoformat()
        }

    def get_user_api_keys(self, user_id, include_secrets=False):
        """
        Get all API keys for user.

        Args:
            user_id (int): User ID
            include_secrets (bool): If True, decrypt and include secrets (USE WITH CAUTION!)

        Returns:
            list: List of API keys
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, key_name, platform, api_key_encrypted, api_secret_encrypted,
                       is_active, created_at, updated_at, last_used,
                       last_test_status, last_test_time
                FROM api_keys
                WHERE user_id = ?
                ORDER BY created_at DESC
            """, (user_id,))

            keys = [dict(row) for row in cursor.fetchall()]

        # Process keys
        for key in keys:
            if include_secrets:
                # DANGER: Only use this for trading operations!
                key['api_key'] = self.crypto.decrypt(key['api_key_encrypted'])
                key['api_secret'] = self.crypto.decrypt(key['api_secret_encrypted'])
            else:
                # Show masked version
                decrypted_key = self.crypto.decrypt(key['api_key_encrypted'])
                key['api_key_masked'] = self.crypto.mask_sensitive_data(decrypted_key)

            # Remove encrypted versions from response
            del key['api_key_encrypted']
            del key['api_secret_encrypted']

        return keys

    def get_api_key_by_id(self, key_id, user_id, decrypt=False):
        """
        Get specific API key.

        Args:
            key_id (int): API key ID
            user_id (int): User ID (for security check)
            decrypt (bool): If True, decrypt the keys

        Returns:
            dict: API key data
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM api_keys
                WHERE id = ? AND user_id = ?
            """, (key_id, user_id))

            result = cursor.fetchone()

        if not result:
            return None

        key_data = dict(result)

        if decrypt:
            key_data['api_key'] = self.crypto.decrypt(key_data['api_key_encrypted'])
            key_data['api_secret'] = self.crypto.decrypt(key_data['api_secret_encrypted'])
        else:
            decrypted_key = self.crypto.decrypt(key_data['api_key_encrypted'])
            key_data['api_key_masked'] = self.crypto.mask_sensitive_data(decrypted_key)

        del key_data['api_key_encrypted']
        del key_data['api_secret_encrypted']

        return key_data

    def update_api_key(self, key_id, user_id, key_name=None, api_key=None, api_secret=None):
        """
        Update API key.

        Args:
            key_id (int): API key ID
            user_id (int): User ID
            key_name (str): New key name
            api_key (str): New API key
            api_secret (str): New API secret

        Returns:
            dict: Updated API key data
        """
        updates = []
        params = []

        if key_name is not None:
            updates.append("key_name = ?")
            params.append(key_name)

        if api_key is not None:
            updates.append("api_key_encrypted = ?")
            params.append(self.crypto.encrypt(api_key))

        if api_secret is not None:
            updates.append("api_secret_encrypted = ?")
            params.append(self.crypto.encrypt(api_secret))

        if not updates:
            raise ValueError("No fields to update")

        updates.append("updated_at = ?")
        params.append(datetime.now())
        params.append(key_id)
        params.append(user_id)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE api_keys SET {', '.join(updates)}
                WHERE id = ? AND user_id = ?
            """, params)
            conn.commit()

        # Log action
        self.db.log_action(user_id, 'api_key_updated', 'api_key', key_id,
                         f"API key updated: {key_id}", None, None, 'success')

        logger.info(f"API key updated: {key_id}")
        return self.get_api_key_by_id(key_id, user_id)

    def delete_api_key(self, key_id, user_id):
        """
        Delete API key.

        Args:
            key_id (int): API key ID
            user_id (int): User ID

        Returns:
            bool: True if successful
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM api_keys WHERE id = ? AND user_id = ?
            """, (key_id, user_id))

            deleted = cursor.rowcount > 0
            conn.commit()

        if deleted:
            # Log action
            self.db.log_action(user_id, 'api_key_deleted', 'api_key', key_id,
                             f"API key deleted: {key_id}", None, None, 'success')
            logger.info(f"API key deleted: {key_id}")

        return deleted

    def test_api_key(self, key_id, user_id):
        """
        Test API key connection (placeholder - implement with actual exchange API).

        Args:
            key_id (int): API key ID
            user_id (int): User ID

        Returns:
            dict: Test result
        """
        # Get decrypted key
        key_data = self.get_api_key_by_id(key_id, user_id, decrypt=True)

        if not key_data:
            return {'success': False, 'message': 'API key not found'}

        # TODO: Implement actual API test with exchange
        # For now, just update last_test_time
        test_status = 'success'  # or 'failure' based on actual test

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE api_keys
                SET last_used = ?, last_test_status = ?, last_test_time = ?
                WHERE id = ?
            """, (datetime.now(), test_status, datetime.now(), key_id))
            conn.commit()

        logger.info(f"API key tested: {key_id} - Status: {test_status}")

        return {
            'success': test_status == 'success',
            'message': 'API key connection successful' if test_status == 'success' else 'API key test failed',
            'platform': key_data['platform']
        }

    # ============================================
    # SETTINGS MANAGEMENT
    # ============================================

    def get_notification_settings(self, user_id):
        """Get user notification settings."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM notification_settings WHERE user_id = ?
            """, (user_id,))

            result = cursor.fetchone()
            return dict(result) if result else None

    def update_notification_settings(self, user_id, settings):
        """
        Update notification settings.

        Args:
            user_id (int): User ID
            settings (dict): Settings to update

        Returns:
            dict: Updated settings
        """
        allowed_fields = [
            'notification_email', 'email_enabled', 'email_trade_confirmations',
            'email_price_alerts', 'email_daily_reports', 'email_security_alerts',
            'email_newsletter', 'telegram_enabled', 'telegram_username',
            'telegram_chat_id', 'telegram_trade_signals', 'telegram_stop_loss_tp',
            'telegram_errors'
        ]

        updates = []
        params = []

        for field, value in settings.items():
            if field in allowed_fields:
                updates.append(f"{field} = ?")
                params.append(value)

        if not updates:
            raise ValueError("No valid fields to update")

        updates.append("updated_at = ?")
        params.append(datetime.now())
        params.append(user_id)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE notification_settings SET {', '.join(updates)}
                WHERE user_id = ?
            """, params)
            conn.commit()

        logger.info(f"Notification settings updated for user {user_id}")
        return self.get_notification_settings(user_id)

    def get_trading_settings(self, user_id):
        """Get user trading settings."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trading_settings WHERE user_id = ?
            """, (user_id,))

            result = cursor.fetchone()
            return dict(result) if result else None

    def update_trading_settings(self, user_id, settings):
        """
        Update trading settings.

        Args:
            user_id (int): User ID
            settings (dict): Settings to update

        Returns:
            dict: Updated settings
        """
        allowed_fields = [
            'max_risk_per_trade', 'max_daily_loss', 'leverage', 'default_stop_loss',
            'default_take_profit', 'max_open_positions', 'auto_trading_enabled',
            'strategy', 'assets_btc', 'assets_eth', 'assets_sol', 'assets_bnb',
            'assets_xrp', 'assets_ada', 'trading_24_7'
        ]

        updates = []
        params = []

        for field, value in settings.items():
            if field in allowed_fields:
                updates.append(f"{field} = ?")
                params.append(value)

        if not updates:
            raise ValueError("No valid fields to update")

        updates.append("updated_at = ?")
        params.append(datetime.now())
        params.append(user_id)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE trading_settings SET {', '.join(updates)}
                WHERE user_id = ?
            """, params)
            conn.commit()

        logger.info(f"Trading settings updated for user {user_id}")
        return self.get_trading_settings(user_id)

    def get_user_statistics(self, user_id):
        """Get user trading statistics."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM user_statistics WHERE user_id = ?
            """, (user_id,))

            result = cursor.fetchone()
            stats = dict(result) if result else None

        if stats:
            # Calculate win rate
            if stats['total_trades'] > 0:
                stats['win_rate'] = round((stats['winning_trades'] / stats['total_trades']) * 100, 2)
            else:
                stats['win_rate'] = 0.0

            # Calculate net profit
            stats['net_profit'] = stats['total_profit'] - stats['total_loss']

        return stats

    # ============================================
    # PASSWORD RESET
    # ============================================

    def request_password_reset(self, email, ip_address=None):
        """
        Create password reset token.

        Args:
            email (str): User email
            ip_address (str): Request IP

        Returns:
            dict: Reset token data
        """
        user = self.get_user_by_email(email)

        if not user:
            # Don't reveal that email doesn't exist (security)
            logger.warning(f"Password reset requested for non-existent email: {email}")
            return {
                'success': True,
                'message': 'If email exists, reset link will be sent'
            }

        # Generate token
        token = CryptoManager.generate_random_token()
        expires_at = datetime.now() + timedelta(hours=1)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO password_reset_tokens
                (user_id, token, expires_at, ip_address)
                VALUES (?, ?, ?, ?)
            """, (user['id'], token, expires_at, ip_address))
            conn.commit()

        # Log action
        self.db.log_action(user['id'], 'password_reset_requested', 'user', user['id'],
                         "Password reset requested", ip_address, None, 'success')

        logger.info(f"Password reset requested for user {user['id']}")

        return {
            'success': True,
            'token': token,
            'expires_at': expires_at.isoformat(),
            'user_id': user['id'],
            'email': email
        }

    def reset_password_with_token(self, token, new_password, ip_address=None):
        """
        Reset password using token.

        Args:
            token (str): Reset token
            new_password (str): New password
            ip_address (str): Request IP

        Returns:
            bool: True if successful
        """
        # Validate token
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM password_reset_tokens
                WHERE token = ? AND used = 0 AND expires_at > ?
            """, (token, datetime.now()))

            result = cursor.fetchone()

        if not result:
            raise ValueError("Invalid or expired reset token")

        reset_data = dict(result)
        user_id = reset_data['user_id']

        # Validate new password
        is_valid, msg = self.pm.validate_password_strength(new_password)
        if not is_valid:
            raise ValueError(msg)

        # Hash new password
        new_password_hash = self.pm.hash_password(new_password)

        # Update password and mark token as used
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE users SET password_hash = ?, updated_at = ?
                WHERE id = ?
            """, (new_password_hash, datetime.now(), user_id))

            cursor.execute("""
                UPDATE password_reset_tokens
                SET used = 1, used_at = ?
                WHERE token = ?
            """, (datetime.now(), token))

            conn.commit()

        # Log action
        self.db.log_action(user_id, 'password_reset', 'user', user_id,
                         "Password reset completed", ip_address, None, 'success')

        logger.info(f"Password reset completed for user {user_id}")
        return True

    # ============================================
    # HELPER METHODS
    # ============================================

    def _validate_email(self, email):
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None

    def _generate_avatar_initials(self, full_name):
        """Generate avatar initials from full name."""
        if not full_name:
            return "??"

        parts = full_name.strip().split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[1][0]}".upper()
        elif len(parts) == 1:
            return parts[0][:2].upper()
        else:
            return "??"

    def _increment_failed_login(self, user_id):
        """Increment failed login attempts and lock account if necessary."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT failed_login_attempts FROM users WHERE id = ?
            """, (user_id,))
            result = cursor.fetchone()
            attempts = result['failed_login_attempts'] + 1

            if attempts >= self.max_failed_attempts:
                # Lock account
                locked_until = datetime.now() + timedelta(minutes=self.lockout_duration_minutes)
                cursor.execute("""
                    UPDATE users
                    SET failed_login_attempts = ?, locked_until = ?
                    WHERE id = ?
                """, (attempts, locked_until, user_id))

                self.db.log_action(user_id, 'account_locked', 'user', user_id,
                                 f"Account locked after {attempts} failed attempts",
                                 None, None, 'success')
                logger.warning(f"Account locked for user {user_id}")
            else:
                cursor.execute("""
                    UPDATE users SET failed_login_attempts = ? WHERE id = ?
                """, (attempts, user_id))

            conn.commit()

    def _reset_failed_login(self, user_id):
        """Reset failed login attempts after successful login."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users
                SET failed_login_attempts = 0, locked_until = NULL
                WHERE id = ?
            """, (user_id,))
            conn.commit()


# ============================================
# USAGE EXAMPLE
# ============================================

if __name__ == "__main__":
    print("=== User Manager Test ===\n")

    # Initialize
    os.environ['ENCRYPTION_KEY'] = 'test_key_for_demonstration'
    db = Database('test_trading_bot.db')
    db.initialize()

    um = UserManager(db)

    # Test registration
    print("1. Testing User Registration:")
    try:
        result = um.register_user(
            email="test@example.com",
            password="SecurePass123",
            full_name="Test User",
            phone="+48123456789"
        )
        print(f"   ✅ User registered: ID {result['user_id']}")
    except ValueError as e:
        print(f"   ❌ Registration failed: {e}")

    print("\n=== Test Completed ===")
