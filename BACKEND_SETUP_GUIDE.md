# 🚀 Trading Bot Pro - Backend Setup Guide

## 📋 Spis Treści
1. [Wymagania](#wymagania)
2. [Szybka Instalacja](#szybka-instalacja)
3. [Konfiguracja](#konfiguracja)
4. [Uruchomienie](#uruchomienie)
5. [Testowanie](#testowanie)
6. [Bezpieczeństwo](#bezpieczeństwo)
7. [Troubleshooting](#troubleshooting)

---

## ✅ Wymagania

### System:
- Python 3.9+ (zalecane 3.10 lub 3.11)
- Windows, Linux, lub macOS
- 500 MB wolnego miejsca na dysku
- 1 GB RAM (minimum)

### Zainstaluj Python:
- Windows: https://www.python.org/downloads/
- Linux: `sudo apt install python3 python3-pip`
- macOS: `brew install python3`

---

## 🚀 Szybka Instalacja

### Krok 1: Zainstaluj Zależności

Otwórz terminal/cmd w folderze projektu i wykonaj:

```bash
cd C:\Users\rxosk\Desktop\tradingbotfinalversion22

# Zainstaluj wymagane biblioteki
pip install -r requirements_backend.txt
```

**WAŻNE**: Jeśli pojawią się błędy, spróbuj:
```bash
pip install --upgrade pip
pip install -r requirements_backend.txt --no-cache-dir
```

### Krok 2: Uruchom Setup

```bash
python setup_backend.py
```

Ten skrypt:
- ✅ Sprawdzi zainstalowane pakiety
- ✅ Wygeneruje bezpieczne klucze szyfrowania
- ✅ Utworzy plik `.env` z konfiguracją
- ✅ Zainicjuje bazę danych SQLite
- ✅ Pomoże utworzyć pierwszego użytkownika (admina)

### Krok 3: Uruchom Aplikację

```bash
python app.py
```

Aplikacja uruchomi się na: **http://localhost:5000**

---

## ⚙️ Konfiguracja

### Plik .env

Po uruchomieniu `setup_backend.py` zostanie utworzony plik `.env` z konf igurację.

**WAŻNE:**
- ❌ **NIE commituj pliku .env do git!**
- ✅ **Trzymaj klucze w bezpiecznym miejscu**
- ✅ **Backup pliku .env przed zmianami**

### Konfiguracja Email (SMTP)

Aby wysyłać emaile (powiadomienia, reset hasła), skonfiguruj SMTP:

#### Gmail (Zalecane dla testów):

1. Włącz 2FA w swoim koncie Google
2. Wygeneruj "App Password":
   - Przejdź do: https://myaccount.google.com/security
   - "2-Step Verification" → "App passwords"
   - Wybierz "Mail" i "Other"
   - Skopiuj wygenerowane hasło (16 znaków)

3. W pliku `.env` ustaw:
```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=twoj-email@gmail.com
SMTP_PASSWORD=wygenerowane-app-password
```

#### Inne Dostawcy SMTP:

**SendGrid:**
```env
SMTP_SERVER=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=twoj-sendgrid-api-key
```

**Mailgun:**
```env
SMTP_SERVER=smtp.mailgun.org
SMTP_PORT=587
SMTP_USERNAME=twoj-mailgun-username
SMTP_PASSWORD=twoj-mailgun-password
```

---

## 🎮 Uruchomienie

### Tryb Deweloperski (Development)

```bash
# W pliku .env ustaw:
DEBUG_MODE=true

# Uruchom:
python app.py
```

Aplikacja będzie automatycznie restartować się przy zmianach w kodzie.

### Tryb Produkcyjny (Production)

```bash
# W pliku .env ustaw:
DEBUG_MODE=false

# Zainstaluj Gunicorn (Linux/macOS):
pip install gunicorn

# Uruchom:
gunicorn -w 4 -b 0.0.0.0:5000 --worker-class eventlet app:app
```

**Windows (Production):**
```bash
# Użyj waitress:
pip install waitress

# Uruchom:
waitress-serve --host=0.0.0.0 --port=5000 app:app
```

---

## 🧪 Testowanie

### Test 1: Sprawdź Backend API

Otwórz przeglądarkę i przejdź do:
```
http://localhost:5000/api/health
```

Powinieneś zobaczyć:
```json
{
  "status": "ok",
  "message": "Trading Bot Pro API is running"
}
```

### Test 2: Test Szyfrowania

```bash
python crypto_manager.py
```

Powinno wyświetlić testy szyfrowania i hashowania haseł.

### Test 3: Test Bazy Danych

```bash
python database.py
```

Powinno wyświetlić statystyki bazy danych.

### Test 4: Test User Manager

```bash
python user_manager.py
```

Utworzy testowego użytkownika i wyświetli potwierdzenie.

---

## 🔐 Bezpieczeństwo

### ✅ Zaimplementowane Zabezpieczenia:

1. **Szyfrowanie AES-256** dla kluczy API
   - Żaden admin nie ma dostępu do odszyfrowanych kluczy
   - Klucze deszyfrowane tylko podczas transakcji

2. **Bcrypt Password Hashing**
   - 12 rund (domyślnie)
   - Automatyczna generacja salt

3. **JWT Session Tokens**
   - Wygasają po 30 minutach (domyślnie)
   - "Remember me" - 30 dni
   - Przechowywane w bazie danych

4. **Account Lockout**
   - 5 nieudanych prób logowania
   - Blokada na 30 minut

5. **Audit Logging**
   - Wszystkie ważne akcje logowane
   - IP address tracking
   - User agent logging

6. **SQL Injection Prevention**
   - Parametryzowane zapytania
   - Prepared statements

7. **CORS Protection**
   - Whitelist dozwolonych origin

8. **Rate Limiting** (opcjonalne)
   - Limit żądań na minutę/godzinę
   - Ochrona przed brute force

### 🔒 Checklist Bezpieczeństwa dla Produkcji:

- [ ] Zmień wszystkie domyślne klucze w `.env`
- [ ] Użyj silnych haseł dla SMTP
- [ ] Włącz HTTPS (SSL/TLS) - użyj Let's Encrypt
- [ ] Skonfiguruj firewall
- [ ] Regularny backup bazy danych
- [ ] Monitoring logów
- [ ] Aktualizuj dependencies (pip)
- [ ] Włącz 2FA dla wszystkich użytkowników
- [ ] Ustaw `DEBUG_MODE=false`
- [ ] Ogranicz dostęp do pliku `.env`
- [ ] Używaj oddzielnych baz dla dev/prod

---

## 🗄️ Struktura Bazy Danych

Backend automatycznie tworzy następujące tabele:

### 1. `users`
- Dane użytkowników (email, hasło, profil)
- Status konta, weryfikacja email
- 2FA settings
- Account lockout

### 2. `api_keys`
- Zaszyfrowane klucze API (AES-256)
- Platforma (Bybit Live/Testnet)
- Status, ostatnie użycie

### 3. `sessions`
- JWT tokens
- Informacje o urządzeniu
- IP address, lokalizacja
- Expiration time

### 4. `notification_settings`
- Preferencje email
- Preferencje Telegram
- Toggle dla każdego typu powiadomienia

### 5. `trading_settings`
- Risk management
- Leverage, Stop Loss, Take Profit
- Auto-trading toggle
- Wybrane aktywa

### 6. `user_statistics`
- Liczba transakcji
- Win rate
- Profit/Loss
- Best/Worst trade

### 7. `password_reset_tokens`
- Tokeny resetowania hasła
- Expiration (1 godzina)
- Used status

### 8. `audit_log`
- Historia akcji użytkownika
- Security events
- IP tracking

---

## 📁 Struktura Plików Backend

```
tradingbotfinalversion22/
├── .env                        # Konfiguracja (NIE commituj!)
├── .env.example                # Przykładowa konfiguracja
├── .gitignore                  # Git ignore rules
│
├── setup_backend.py            # 🚀 Skrypt instalacji
├── requirements_backend.txt    # Zależności Python
│
├── database.py                 # 🗄️ Database Manager
├── crypto_manager.py           # 🔐 Szyfrowanie AES-256 & Bcrypt
├── user_manager.py             # 👤 User Management (CRUD)
├── auth_middleware.py          # 🔑 JWT & Sessions
├── email_service.py            # 📧 Email SMTP Service
│
├── app.py                      # 🎯 Flask App (główny)
├── trading_bot.db              # 📊 SQLite Database
├── trading_bot.log             # 📝 Application Logs
│
├── templates/
│   ├── index.html              # Stary frontend (backup)
│   └── index_new.html          # ✨ Nowy frontend z panelem użytkownika
│
└── docs/
    ├── FRONTEND_DOCUMENTATION.md
    └── BACKEND_SETUP_GUIDE.md
```

---

## 🔧 Troubleshooting

### Problem: ModuleNotFoundError

```
ModuleNotFoundError: No module named 'bcrypt'
```

**Rozwiązanie:**
```bash
pip install bcrypt
# lub
pip install -r requirements_backend.txt
```

---

### Problem: ENCRYPTION_KEY not found

```
ValueError: ENCRYPTION_KEY not found!
```

**Rozwiązanie:**
1. Uruchom `python setup_backend.py`
2. Lub ręcznie utwórz plik `.env` z kluczami

---

### Problem: Database is locked

```
sqlite3.OperationalError: database is locked
```

**Rozwiązanie:**
1. Zamknij wszystkie inne instancje aplikacji
2. Usuń plik `trading_bot.db-journal`
3. Uruchom ponownie

---

### Problem: Email nie wysyła się

```
SMTPAuthenticationError: Username and Password not accepted
```

**Rozwiązanie (Gmail):**
1. Włącz 2FA w Google Account
2. Wygeneruj App Password
3. Użyj App Password zamiast normalnego hasła

---

### Problem: Port 5000 zajęty

```
OSError: [Errno 48] Address already in use
```

**Rozwiązanie:**

**Windows:**
```cmd
netstat -ano | findstr :5000
taskkill /PID <PID> /F
```

**Linux/macOS:**
```bash
lsof -ti:5000 | xargs kill -9
```

Lub zmień port w `app.py`:
```python
socketio.run(app, host='0.0.0.0', port=8080)
```

---

## 📊 Monitoring & Maintenance

### Backup Bazy Danych

```python
from database import Database

db = Database()
backup_path = db.backup_database()
print(f"Backup created: {backup_path}")
```

### Czyszczenie Wygasłych Sesji

```python
from database import Database

db = Database()
deleted = db.cleanup_expired_sessions()
print(f"Cleaned up {deleted} sessions")
```

### Sprawdzanie Statystyk

```bash
python -c "from database import Database; db = Database(); print(db.get_database_stats())"
```

---

## 🚀 Deployment (Produkcja)

### Option 1: VPS (Recommended)

1. **Wynajmij VPS** (np. DigitalOcean, AWS, Heroku, Linode)
2. **Zainstaluj Python 3.10+**
3. **Sklonuj repozytorium**
4. **Uruchom setup:**
   ```bash
   python setup_backend.py
   ```
5. **Zainstaluj Nginx jako reverse proxy**
6. **Skonfiguruj SSL (Let's Encrypt)**
7. **Uruchom z Gunicorn/Waitress**
8. **Skonfiguruj systemd service (Linux)**

### Option 2: Docker

Utwórz `Dockerfile`:
```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements_backend.txt .
RUN pip install --no-cache-dir -r requirements_backend.txt

COPY . .

CMD ["python", "app.py"]
```

Buduj i uruchom:
```bash
docker build -t trading-bot-pro .
docker run -p 5000:5000 trading-bot-pro
```

---

## 📚 Przydatne Komendy

### Generowanie Nowego Klucza

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Reset Hasła Użytkownika (przez Python)

```python
from user_manager import UserManager
from database import Database

db = Database()
um = UserManager(db)

# Zmień hasło
um.change_password(
    user_id=1,
    current_password="OldPassword123",
    new_password="NewPassword123"
)
```

### Wylogowanie Wszystkich Sesji

```python
from user_manager import UserManager
from database import Database

db = Database()
um = UserManager(db)

# Wyloguj wszystkie sesje użytkownika
um.logout_all_sessions(user_id=1)
```

---

## 🆘 Wsparcie

### Logi

Sprawdź plik `trading_bot.log` dla szczegółów błędów:
```bash
tail -f trading_bot.log
```

### Debug Mode

W `.env` ustaw:
```env
DEBUG_MODE=true
LOG_LEVEL=DEBUG
```

---

## ✅ Gotowe!

Twój backend Trading Bot Pro jest teraz skonfigurowany i gotowy do użycia!

**Następne kroki:**
1. Otwórz http://localhost:5000
2. Zaloguj się swoim kontem
3. Skonfiguruj klucze API w panelu użytkownika
4. Rozpocznij trading!

---

**Wersja:** 1.0
**Data:** 2025-01-20
**Autor:** Trading Bot Pro Team

🎉 **Powodzenia w tradingu!**
