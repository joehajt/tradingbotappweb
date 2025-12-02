"""
Database Manager - SQLite Database with Complete Schema
=========================================================
This module handles database initialization, schema creation, and basic operations.

Tables:
- users: User accounts with authentication
- api_keys: Encrypted API keys for trading platforms
- sessions: Active user sessions with JWT tokens
- notification_settings: User notification preferences
- trading_settings: User trading configuration
- password_reset_tokens: Tokens for password reset
- user_statistics: Trading statistics per user
- audit_log: Security and activity audit trail
"""

import sqlite3
import os
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Database:
    """
    Database manager for Trading Bot Pro.

    Handles all database operations including initialization, migrations, and queries.
    """

    def __init__(self, db_path=None):
        """
        Initialize database connection.

        Args:
            db_path (str): Path to SQLite database file
        """
        if db_path is None:
            db_path = os.environ.get('DATABASE_URL', 'sqlite:///trading_bot.db')
            # Remove 'sqlite:///' prefix if present
            db_path = db_path.replace('sqlite:///', '')

        self.db_path = db_path
        logger.info(f"Database initialized: {self.db_path}")

    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.

        Usage:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users")
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def initialize(self):
        """
        Initialize database with all required tables.
        Safe to call multiple times (checks if tables exist).
        """
        logger.info("Initializing database schema...")

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # ============================================
            # USERS TABLE
            # ============================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    full_name VARCHAR(255),
                    phone VARCHAR(50),
                    country VARCHAR(2) DEFAULT 'PL',
                    timezone VARCHAR(100) DEFAULT 'Europe/Warsaw',
                    avatar_initials VARCHAR(5),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    is_email_verified BOOLEAN DEFAULT 0,
                    email_verification_token VARCHAR(255),
                    two_factor_enabled BOOLEAN DEFAULT 0,
                    two_factor_secret VARCHAR(255),
                    failed_login_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP,
                    UNIQUE(email)
                )
            """)

            # ============================================
            # API KEYS TABLE (Encrypted)
            # ============================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    key_name VARCHAR(255) NOT NULL,
                    platform VARCHAR(50) NOT NULL,
                    api_key_encrypted TEXT NOT NULL,
                    api_secret_encrypted TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP,
                    last_test_status VARCHAR(50),
                    last_test_time TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            # ============================================
            # SESSIONS TABLE
            # ============================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token VARCHAR(500) NOT NULL UNIQUE,
                    device_info VARCHAR(255),
                    browser VARCHAR(100),
                    os VARCHAR(100),
                    ip_address VARCHAR(50),
                    location VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    remember_me BOOLEAN DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            # ============================================
            # NOTIFICATION SETTINGS TABLE
            # ============================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notification_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    notification_email VARCHAR(255),
                    email_enabled BOOLEAN DEFAULT 1,
                    email_trade_confirmations BOOLEAN DEFAULT 1,
                    email_price_alerts BOOLEAN DEFAULT 1,
                    email_daily_reports BOOLEAN DEFAULT 1,
                    email_security_alerts BOOLEAN DEFAULT 1,
                    email_newsletter BOOLEAN DEFAULT 0,
                    telegram_enabled BOOLEAN DEFAULT 0,
                    telegram_username VARCHAR(255),
                    telegram_chat_id VARCHAR(255),
                    telegram_trade_signals BOOLEAN DEFAULT 1,
                    telegram_stop_loss_tp BOOLEAN DEFAULT 1,
                    telegram_errors BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            # ============================================
            # TRADING SETTINGS TABLE
            # ============================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    max_risk_per_trade DECIMAL(5,2) DEFAULT 2.0,
                    max_daily_loss DECIMAL(5,2) DEFAULT 5.0,
                    leverage INTEGER DEFAULT 5,
                    default_stop_loss DECIMAL(5,2) DEFAULT 3.0,
                    default_take_profit DECIMAL(5,2) DEFAULT 6.0,
                    max_open_positions INTEGER DEFAULT 10,
                    auto_trading_enabled BOOLEAN DEFAULT 0,
                    strategy VARCHAR(50) DEFAULT 'daytrading',
                    assets_btc BOOLEAN DEFAULT 1,
                    assets_eth BOOLEAN DEFAULT 1,
                    assets_sol BOOLEAN DEFAULT 0,
                    assets_bnb BOOLEAN DEFAULT 0,
                    assets_xrp BOOLEAN DEFAULT 0,
                    assets_ada BOOLEAN DEFAULT 0,
                    trading_24_7 BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            # ============================================
            # PASSWORD RESET TOKENS TABLE
            # ============================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token VARCHAR(255) NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT 0,
                    used_at TIMESTAMP,
                    ip_address VARCHAR(50),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            # ============================================
            # USER STATISTICS TABLE
            # ============================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_statistics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    total_profit DECIMAL(20,8) DEFAULT 0.0,
                    total_loss DECIMAL(20,8) DEFAULT 0.0,
                    best_trade DECIMAL(20,8) DEFAULT 0.0,
                    worst_trade DECIMAL(20,8) DEFAULT 0.0,
                    current_balance DECIMAL(20,8) DEFAULT 0.0,
                    initial_balance DECIMAL(20,8) DEFAULT 0.0,
                    active_days INTEGER DEFAULT 0,
                    last_trade_date TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            # ============================================
            # AUDIT LOG TABLE (Security & Activity Tracking)
            # ============================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action VARCHAR(100) NOT NULL,
                    resource VARCHAR(100),
                    resource_id INTEGER,
                    details TEXT,
                    ip_address VARCHAR(50),
                    user_agent TEXT,
                    status VARCHAR(20),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            """)

            # ============================================
            # TRADING PROFILES TABLE (User-specific)
            # ============================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    profile_name VARCHAR(255) NOT NULL,
                    config_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, profile_name)
                )
            """)

            # ============================================
            # INDEXES for Performance
            # ============================================
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trading_profiles_user_id ON trading_profiles(user_id)
            """)

            conn.commit()
            logger.info("Database schema initialized successfully")

    def create_default_settings(self, user_id):
        """
        Create default notification and trading settings for a new user.

        Args:
            user_id (int): User ID
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create default notification settings
            cursor.execute("""
                INSERT OR IGNORE INTO notification_settings (user_id)
                VALUES (?)
            """, (user_id,))

            # Create default trading settings
            cursor.execute("""
                INSERT OR IGNORE INTO trading_settings (user_id)
                VALUES (?)
            """, (user_id,))

            # Create user statistics record
            cursor.execute("""
                INSERT OR IGNORE INTO user_statistics (user_id)
                VALUES (?)
            """, (user_id,))

            conn.commit()
            logger.info(f"Created default settings for user {user_id}")

    def log_action(self, user_id, action, resource=None, resource_id=None,
                   details=None, ip_address=None, user_agent=None, status='success'):
        """
        Log user action to audit log.

        Args:
            user_id (int): User ID (can be None for anonymous actions)
            action (str): Action name (e.g., 'login', 'api_key_added')
            resource (str): Resource type (e.g., 'user', 'api_key')
            resource_id (int): Resource ID
            details (str): Additional details
            ip_address (str): IP address
            user_agent (str): User agent string
            status (str): 'success' or 'failure'
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO audit_log
                    (user_id, action, resource, resource_id, details, ip_address, user_agent, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_id, action, resource, resource_id, details, ip_address, user_agent, status))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log action: {e}")

    def cleanup_expired_sessions(self):
        """
        Remove expired sessions from database.
        Should be called periodically (e.g., daily cron job).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM sessions
                WHERE expires_at < ? OR (is_active = 0 AND last_activity < ?)
            """, (datetime.now(), datetime.now() - timedelta(days=7)))

            deleted_count = cursor.rowcount
            conn.commit()
            logger.info(f"Cleaned up {deleted_count} expired sessions")
            return deleted_count

    def cleanup_expired_reset_tokens(self):
        """
        Remove expired password reset tokens.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM password_reset_tokens
                WHERE expires_at < ? OR used = 1
            """, (datetime.now(),))

            deleted_count = cursor.rowcount
            conn.commit()
            logger.info(f"Cleaned up {deleted_count} expired reset tokens")
            return deleted_count

    def get_database_stats(self):
        """
        Get database statistics.

        Returns:
            dict: Database statistics
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            # Count users
            cursor.execute("SELECT COUNT(*) as count FROM users")
            stats['total_users'] = cursor.fetchone()['count']

            # Count active sessions
            cursor.execute("SELECT COUNT(*) as count FROM sessions WHERE is_active = 1")
            stats['active_sessions'] = cursor.fetchone()['count']

            # Count API keys
            cursor.execute("SELECT COUNT(*) as count FROM api_keys WHERE is_active = 1")
            stats['active_api_keys'] = cursor.fetchone()['count']

            # Get database file size
            if os.path.exists(self.db_path):
                stats['database_size_mb'] = round(os.path.getsize(self.db_path) / (1024 * 1024), 2)

            return stats

    def backup_database(self, backup_path=None):
        """
        Create a backup of the database.

        Args:
            backup_path (str): Path for backup file

        Returns:
            str: Path to backup file
        """
        if backup_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = f"{self.db_path}.backup_{timestamp}"

        import shutil
        shutil.copy2(self.db_path, backup_path)
        logger.info(f"Database backed up to: {backup_path}")
        return backup_path

    def execute_query(self, query, params=None, fetch_one=False):
        """
        Execute a custom SQL query.

        Args:
            query (str): SQL query
            params (tuple): Query parameters
            fetch_one (bool): If True, return only first result

        Returns:
            list or dict: Query results
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params or ())

            if fetch_one:
                result = cursor.fetchone()
                return dict(result) if result else None
            else:
                return [dict(row) for row in cursor.fetchall()]


# ============================================
# DATABASE MIGRATION SYSTEM
# ============================================

class DatabaseMigration:
    """
    Simple database migration system.
    """

    def __init__(self, db):
        self.db = db

    def create_migrations_table(self):
        """Create table to track migrations."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version VARCHAR(50) UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def has_migration(self, version):
        """Check if migration has been applied."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM schema_migrations WHERE version = ?",
                (version,)
            )
            result = cursor.fetchone()
            return result['count'] > 0

    def add_migration(self, version):
        """Mark migration as applied."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)",
                (version,)
            )
            conn.commit()


# ============================================
# USAGE EXAMPLE
# ============================================

if __name__ == "__main__":
    print("=== Database Manager Test ===\n")

    # Initialize database
    db = Database('test_trading_bot.db')
    db.initialize()

    print("✅ Database initialized")

    # Get stats
    stats = db.get_database_stats()
    print(f"\n📊 Database Statistics:")
    for key, value in stats.items():
        print(f"   {key}: {value}")

    # Create backup
    backup_path = db.backup_database()
    print(f"\n💾 Backup created: {backup_path}")

    print("\n=== Test Completed ===")
