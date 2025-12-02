"""
Quick automated backend setup - creates database and demo admin user
"""

import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'ignore')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'ignore')
    except Exception:
        pass

import os
from dotenv import load_dotenv

print("\n" + "=" * 60)
print("  QUICK BACKEND SETUP")
print("=" * 60 + "\n")

# Step 1: Load or create .env
if os.path.exists('.env'):
    print("✅ .env file exists, loading...")
    load_dotenv()
else:
    print("📝 Creating .env file with secure keys...")

    import secrets

    secret_key = secrets.token_urlsafe(32)
    encryption_key = secrets.token_urlsafe(32)
    jwt_secret = secrets.token_urlsafe(32)

    env_content = f"""# Auto-generated configuration
SECRET_KEY={secret_key}
ENCRYPTION_KEY={encryption_key}
JWT_SECRET_KEY={jwt_secret}

DATABASE_URL=sqlite:///trading_bot.db

# Email (optional - skip for now)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
EMAIL_FROM=Trading Bot <noreply@tradingbot.com>

FRONTEND_URL=http://localhost:5000
BACKEND_URL=http://localhost:5000

SESSION_TIMEOUT_MINUTES=30
REMEMBER_ME_DAYS=30
PASSWORD_RESET_TOKEN_EXPIRY_HOURS=1

BCRYPT_ROUNDS=12
RATE_LIMIT_ENABLED=true

CORS_ORIGINS=http://localhost:5000,http://127.0.0.1:5000

LOG_LEVEL=INFO
LOG_FILE=trading_bot.log

DEBUG_MODE=false
TESTING_MODE=false
"""

    with open('.env', 'w', encoding='utf-8') as f:
        f.write(env_content)

    print("✅ .env file created!\n")
    load_dotenv()

# Step 2: Initialize database
print("🗄️  Initializing database...")

try:
    from database import Database

    db = Database()
    db.initialize()

    print("✅ Database initialized!\n")

except Exception as e:
    print(f"❌ Database error: {e}")
    sys.exit(1)

# Step 3: Create demo admin user
print("👤 Creating demo admin user...\n")

try:
    from user_manager import UserManager

    um = UserManager(db)

    # Check if user already exists
    existing_user = um.get_user_by_email("admin@demo.com")

    if existing_user:
        print("ℹ️  Demo admin user already exists!")
        print(f"   Email: admin@demo.com")
        print(f"   Password: (use your existing password)\n")
    else:
        # Create new demo user
        result = um.register_user(
            email="admin@demo.com",
            password="Admin123!",
            full_name="Admin User",
            phone=None,
            country='PL',
            timezone='Europe/Warsaw'
        )

        print("✅ Demo admin user created!")
        print(f"   Email: admin@demo.com")
        print(f"   Password: Admin123!")
        print(f"   User ID: {result['user_id']}\n")

except Exception as e:
    print(f"❌ Error creating user: {e}\n")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 4: Show database stats
print("📊 Database Statistics:")
try:
    stats = db.get_database_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
except Exception as e:
    print(f"   Error: {e}")

print("\n" + "=" * 60)
print("  ✅ SETUP COMPLETE!")
print("=" * 60)
print("\n📋 Next Steps:")
print("   1. Run: python app.py")
print("   2. Open: http://localhost:5000")
print("   3. Login with:")
print("      Email: admin@demo.com")
print("      Password: Admin123!")
print("\n💡 You can change the password after logging in!")
print("=" * 60 + "\n")
