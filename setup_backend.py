"""
Backend Setup Script
====================
This script helps you set up the Trading Bot Pro backend:
1. Generates secure keys
2. Creates .env file
3. Initializes database
4. Creates first admin user
"""

import os
import secrets
import sys

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'ignore')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'ignore')
    except Exception:
        pass


def print_header():
    print("\n" + "=" * 60)
    print("  TRADING BOT PRO - BACKEND SETUP")
    print("=" * 60 + "\n")


def generate_secure_key():
    """Generate a secure random key."""
    return secrets.token_urlsafe(32)


def create_env_file():
    """Create .env file with secure keys."""
    print("📝 Creating .env file...\n")

    # Generate secure keys
    secret_key = generate_secure_key()
    encryption_key = generate_secure_key()
    jwt_secret = generate_secure_key()

    print("✅ Generated secure keys:")
    print(f"   SECRET_KEY: {secret_key[:20]}...")
    print(f"   ENCRYPTION_KEY: {encryption_key[:20]}...")
    print(f"   JWT_SECRET_KEY: {jwt_secret[:20]}...")

    # Get SMTP configuration from user
    print("\n📧 Email Configuration (Optional - press Enter to skip):")
    smtp_server = input("   SMTP Server (default: smtp.gmail.com): ").strip() or "smtp.gmail.com"
    smtp_port = input("   SMTP Port (default: 587): ").strip() or "587"
    smtp_username = input("   SMTP Username (your email): ").strip()
    smtp_password = input("   SMTP Password (app password): ").strip()

    # Create .env content
    env_content = f"""# ============================================
# TRADING BOT PRO - ENVIRONMENT VARIABLES
# ============================================
# Generated on: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

# ============================================
# SECURITY KEYS (DO NOT SHARE!)
# ============================================
SECRET_KEY={secret_key}
ENCRYPTION_KEY={encryption_key}
JWT_SECRET_KEY={jwt_secret}

# ============================================
# DATABASE
# ============================================
DATABASE_URL=sqlite:///trading_bot.db

# ============================================
# EMAIL CONFIGURATION (SMTP)
# ============================================
SMTP_SERVER={smtp_server}
SMTP_PORT={smtp_port}
SMTP_USERNAME={smtp_username}
SMTP_PASSWORD={smtp_password}
EMAIL_FROM=Trading Bot Pro <noreply@tradingbot.com>

# ============================================
# APPLICATION SETTINGS
# ============================================
FRONTEND_URL=http://localhost:5000
BACKEND_URL=http://localhost:5000

# Session Settings
SESSION_TIMEOUT_MINUTES=30
REMEMBER_ME_DAYS=30
PASSWORD_RESET_TOKEN_EXPIRY_HOURS=1

# ============================================
# SECURITY SETTINGS
# ============================================
BCRYPT_ROUNDS=12
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000

# ============================================
# CORS SETTINGS
# ============================================
CORS_ORIGINS=http://localhost:5000,http://127.0.0.1:5000

# ============================================
# LOGGING
# ============================================
LOG_LEVEL=INFO
LOG_FILE=trading_bot.log

# ============================================
# PRODUCTION FLAGS
# ============================================
DEBUG_MODE=false
TESTING_MODE=false
"""

    # Write .env file
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(env_content)

    print("\n✅ .env file created successfully!")
    print("   ⚠️  IMPORTANT: Keep this file secure and never commit it to git!\n")


def initialize_database():
    """Initialize database with schema."""
    print("🗄️  Initializing database...\n")

    try:
        from database import Database

        db = Database()
        db.initialize()

        print("✅ Database initialized successfully!")
        print(f"   Database file: {db.db_path}\n")

        return db

    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return None


def create_admin_user(db):
    """Create first admin user."""
    print("👤 Create Admin User\n")

    try:
        from user_manager import UserManager

        um = UserManager(db)

        # Get admin details
        print("Enter admin user details:")
        email = input("   Email: ").strip()
        full_name = input("   Full Name: ").strip()
        password = input("   Password (min 8 chars, uppercase, lowercase, numbers): ").strip()
        password_confirm = input("   Confirm Password: ").strip()

        if password != password_confirm:
            print("\n❌ Passwords don't match!")
            return False

        # Register user
        result = um.register_user(
            email=email,
            password=password,
            full_name=full_name,
            phone=None,
            country='PL',
            timezone='Europe/Warsaw'
        )

        print(f"\n✅ Admin user created successfully!")
        print(f"   User ID: {result['user_id']}")
        print(f"   Email: {email}\n")

        return True

    except ValueError as e:
        print(f"\n❌ Failed to create user: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def check_dependencies():
    """Check if required packages are installed."""
    print("🔍 Checking dependencies...\n")

    required_packages = [
        'flask',
        'bcrypt',
        'jwt',
        'cryptography',
        'flask_cors',
        'flask_socketio'
    ]

    missing = []

    for package in required_packages:
        try:
            __import__(package)
            print(f"   ✅ {package}")
        except ImportError:
            print(f"   ❌ {package} (MISSING)")
            missing.append(package)

    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print(f"   Install with: pip install -r requirements_backend.txt\n")
        return False

    print("\n✅ All dependencies installed!\n")
    return True


def main():
    """Main setup function."""
    print_header()

    # Step 1: Check dependencies
    if not check_dependencies():
        print("❌ Please install missing dependencies first.")
        print("   Run: pip install -r requirements_backend.txt\n")
        sys.exit(1)

    # Step 2: Create .env file
    if os.path.exists('.env'):
        overwrite = input("⚠️  .env file already exists. Overwrite? (y/N): ").lower()
        if overwrite != 'y':
            print("   Skipping .env creation.\n")
        else:
            create_env_file()
    else:
        create_env_file()

    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()

    # Step 3: Initialize database
    db = initialize_database()

    if not db:
        print("❌ Setup failed at database initialization.")
        sys.exit(1)

    # Step 4: Create admin user
    create_user = input("Create admin user now? (Y/n): ").lower()
    if create_user != 'n':
        create_admin_user(db)

    # Final instructions
    print("\n" + "=" * 60)
    print("  🎉 SETUP COMPLETE!")
    print("=" * 60)
    print("\n📋 Next Steps:")
    print("   1. Review your .env file and update settings if needed")
    print("   2. Run the application: python app.py")
    print("   3. Open browser: http://localhost:5000")
    print("   4. Login with your admin credentials")
    print("\n📖 For more information, see BACKEND_DOCUMENTATION.md")
    print("\n🔒 Security Reminders:")
    print("   • Keep .env file secure and never commit to git")
    print("   • Use strong passwords for all accounts")
    print("   • Enable 2FA for production environments")
    print("   • Regularly backup your database\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user.\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Setup failed with error: {e}\n")
        sys.exit(1)
