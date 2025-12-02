# 🎯 Trading Bot Pro - Complete API Documentation

## ✅ Status: Backend DZIAŁA na http://localhost:5001

---

## 📋 Lista Wszystkich API Endpointów

### 🔐 Authentication (Autentykacja)

#### `POST /api/auth/register`
Rejestracja nowego użytkownika

**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass123",
  "full_name": "Jan Kowalski",
  "phone": "+48123456789",
  "country": "PL"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Registration successful",
  "user": {
    "user_id": 1,
    "email": "user@example.com",
    "full_name": "Jan Kowalski"
  },
  "token": "eyJ0eXAi..."
}
```

---

#### `POST /api/auth/login`
Logowanie użytkownika

**Request:**
```json
{
  "email": "admin@demo.com",
  "password": "Admin123!",
  "remember_me": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Login successful",
  "user": {
    "user_id": 1,
    "email": "admin@demo.com",
    "full_name": "Admin User"
  },
  "token": "eyJ0eXAi..."
}
```

---

#### `POST /api/auth/logout`
Wylogowanie (wymaga tokenu)

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "message": "Logged out successfully"
}
```

---

#### `GET /api/auth/validate`
Walidacja tokenu i pobranie danych użytkownika

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "user": {
    "user_id": 1,
    "email": "admin@demo.com",
    "full_name": "Admin User",
    "phone": null,
    "country": "PL",
    "avatar_initials": "AU",
    "created_at": "2025-01-20 10:30:00",
    "last_login": "2025-01-20 15:45:00",
    "two_factor_enabled": false
  }
}
```

---

### 👤 Profile (Profil Użytkownika)

#### `GET /api/user/profile`
Pobierz profil użytkownika

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "profile": {
    "user_id": 1,
    "email": "admin@demo.com",
    "full_name": "Admin User",
    "phone": "+48797605141",
    "country": "PL",
    "timezone": "Europe/Warsaw",
    "avatar_initials": "AU",
    "created_at": "2025-01-20 10:30:00"
  }
}
```

---

#### `PUT /api/user/profile`
Aktualizuj profil użytkownika

**Headers:**
```
Authorization: Bearer {token}
```

**Request:**
```json
{
  "full_name": "Jan Kowalski",
  "phone": "+48123456789",
  "country": "PL",
  "timezone": "Europe/Warsaw"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Profile updated successfully"
}
```

---

### 🔒 Security (Bezpieczeństwo)

#### `POST /api/user/change-password`
Zmiana hasła

**Headers:**
```
Authorization: Bearer {token}
```

**Request:**
```json
{
  "current_password": "OldPass123",
  "new_password": "NewPass123"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Password changed successfully"
}
```

---

#### `GET /api/user/sessions`
Pobierz aktywne sesje

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "sessions": [
    {
      "session_id": 1,
      "device_info": "Mozilla/5.0...",
      "browser": "Chrome",
      "os": "Windows",
      "ip_address": "192.168.0.100",
      "location": "Warsaw, Poland",
      "created_at": "2025-01-20 10:00:00",
      "last_activity": "2025-01-20 15:00:00",
      "is_active": true
    }
  ]
}
```

---

#### `POST /api/user/sessions/logout-all`
Wyloguj ze wszystkich sesji

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "message": "Logged out from 3 sessions"
}
```

---

### 🔑 API Keys (Klucze API)

#### `GET /api/user/api-keys`
Pobierz listę kluczy API (zaszyfrowanych)

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "api_keys": [
    {
      "key_id": 1,
      "key_name": "Bybit Main Account",
      "platform": "Bybit Live",
      "is_active": true,
      "created_at": "2025-01-20 10:00:00",
      "last_used": "2025-01-20 14:30:00",
      "last_test_status": "success",
      "last_test_time": "2025-01-20 14:30:00"
    }
  ]
}
```

---

#### `POST /api/user/api-keys`
Dodaj nowy klucz API

**Headers:**
```
Authorization: Bearer {token}
```

**Request:**
```json
{
  "key_name": "Bybit Main Account",
  "platform": "Bybit Live",
  "api_key": "your-api-key-here",
  "api_secret": "your-api-secret-here"
}
```

**Response:**
```json
{
  "success": true,
  "message": "API key added successfully",
  "key_id": 1
}
```

**UWAGA:** Klucze są szyfrowane AES-256 i **admin NIE MA dostępu** do odszyfrowanych kluczy!

---

#### `DELETE /api/user/api-keys/{key_id}`
Usuń klucz API

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "message": "API key deleted successfully"
}
```

---

#### `POST /api/user/api-keys/{key_id}/test`
Testuj połączenie z kluczem API

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "test_result": {
    "status": "success",
    "message": "Connection successful",
    "balance": 1250.50,
    "timestamp": "2025-01-20 15:00:00"
  }
}
```

---

### 🔔 Notifications (Powiadomienia)

#### `GET /api/user/notifications`
Pobierz ustawienia powiadomień

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "settings": {
    "notification_email": "user@example.com",
    "email_enabled": true,
    "email_trade_confirmations": true,
    "email_price_alerts": true,
    "email_daily_reports": false,
    "email_security_alerts": true,
    "email_newsletter": false,
    "telegram_enabled": false,
    "telegram_username": null,
    "telegram_chat_id": null,
    "telegram_trade_signals": false,
    "telegram_stop_loss_tp": false,
    "telegram_errors": false
  }
}
```

---

#### `PUT /api/user/notifications`
Aktualizuj ustawienia powiadomień

**Headers:**
```
Authorization: Bearer {token}
```

**Request:**
```json
{
  "email_enabled": true,
  "email_trade_confirmations": true,
  "telegram_enabled": true,
  "telegram_username": "@myusername"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Notification settings updated"
}
```

---

### ⚙️ Trading Settings (Ustawienia Tradingowe)

#### `GET /api/user/trading-settings`
Pobierz ustawienia tradingowe

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "settings": {
    "max_risk_per_trade": 2.0,
    "max_daily_loss": 5.0,
    "leverage": 10,
    "default_stop_loss": 1.5,
    "default_take_profit": 3.0,
    "max_open_positions": 5,
    "auto_trading_enabled": false,
    "strategy": "Scalping",
    "assets_btc": true,
    "assets_eth": true,
    "assets_sol": false,
    "assets_bnb": false,
    "assets_xrp": false,
    "assets_ada": false,
    "trading_24_7": false
  }
}
```

---

#### `PUT /api/user/trading-settings`
Aktualizuj ustawienia tradingowe

**Headers:**
```
Authorization: Bearer {token}
```

**Request:**
```json
{
  "max_risk_per_trade": 2.5,
  "leverage": 15,
  "auto_trading_enabled": true,
  "strategy": "Day Trading",
  "assets_btc": true,
  "assets_eth": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Trading settings updated"
}
```

---

### 📊 Statistics (Statystyki)

#### `GET /api/user/statistics`
Pobierz statystyki tradingowe

**Headers:**
```
Authorization: Bearer {token}
```

**Response:**
```json
{
  "success": true,
  "statistics": {
    "total_trades": 150,
    "winning_trades": 95,
    "losing_trades": 55,
    "win_rate": 63.33,
    "total_profit": 5420.50,
    "total_loss": -2100.30,
    "net_profit": 3320.20,
    "best_trade": 850.00,
    "worst_trade": -320.50,
    "current_balance": 10500.75,
    "initial_balance": 5000.00,
    "active_days": 45,
    "last_trade_date": "2025-01-20 14:30:00"
  }
}
```

---

## 🧪 Testowanie API

### Demo użytkownik:
```
Email: admin@demo.com
Hasło: Admin123!
```

### Test logowania (curl):
```bash
curl -X POST http://localhost:5001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@demo.com","password":"Admin123!"}'
```

### Test z tokenem:
```bash
# 1. Zaloguj się i zapisz token
TOKEN=$(curl -s -X POST http://localhost:5001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@demo.com","password":"Admin123!"}' \
  | jq -r '.token')

# 2. Użyj tokenu do pobrania profilu
curl -X GET http://localhost:5001/api/user/profile \
  -H "Authorization: Bearer $TOKEN"
```

---

## ⚠️ Ważne Informacje

### Bezpieczeństwo:
1. **Klucze API są zaszyfrowane AES-256** - admin NIE MA dostępu
2. **JWT tokeny wygasają** po 30 minutach (lub 30 dni z "remember me")
3. **Account lockout** po 5 nieudanych próbach logowania
4. **Audit logging** - wszystkie akcje są logowane
5. **CORS** jest włączony dla localhost

### Limity:
- Maksymalne 100 sesji per użytkownik
- Maksymalne 20 kluczy API per użytkownik
- Token refresh co 15 minut

### Pliki:
- **api_routes.py** - Wszystkie endpointy
- **user_manager.py** - Backend logika
- **auth_middleware.py** - JWT & auth
- **database.py** - SQLite operations

---

**Aplikacja działa na:** http://localhost:5001

**Panel użytkownika:** http://localhost:5001 (z logowaniem)

**API Health Check:** http://localhost:5001/api/health
