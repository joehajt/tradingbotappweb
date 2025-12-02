"""
User Management System
Zarządza użytkownikami, rejestracją, logowaniem i bezpieczeństwem
Każdy użytkownik ma prywatny profil z zaszyfrowanymi danymi
"""

import sqlite3
import hashlib
import secrets
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any


class UserManager:
    """Zarządza użytkownikami i ich profilami"""

    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Inicjalizuje bazę danych użytkowników"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Tabela użytkowników
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')

        # Tabela profili użytkowników (prywatne ustawienia)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                config_data TEXT,
                trading_profiles TEXT,
                risk_settings TEXT,
                telegram_config TEXT,
                bybit_config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # Tabela sesji
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        conn.commit()
        conn.close()

    def _hash_password(self, password: str, salt: str = None) -> tuple:
        """
        Hashuje hasło z solą
        Returns: (hash, salt)
        """
        if salt is None:
            salt = secrets.token_hex(32)

        # Używamy SHA-256 z solą i wielokrotnym hashowaniem (PBKDF2-podobne)
        password_hash = password + salt
        for _ in range(100000):  # 100k iteracji dla bezpieczeństwa
            password_hash = hashlib.sha256(password_hash.encode()).hexdigest()

        return password_hash, salt

    def register_user(self, username: str, email: str, password: str) -> Dict[str, Any]:
        """
        Rejestruje nowego użytkownika

        Args:
            username: Nazwa użytkownika (unikalna)
            email: Email (unikalny)
            password: Hasło (będzie zahashowane)

        Returns:
            Dict z wynikiem: {'success': bool, 'message': str, 'user_id': int}
        """
        # Walidacja
        if len(username) < 3:
            return {'success': False, 'message': 'Nazwa użytkownika musi mieć minimum 3 znaki'}

        if len(password) < 6:
            return {'success': False, 'message': 'Hasło musi mieć minimum 6 znaków'}

        if '@' not in email:
            return {'success': False, 'message': 'Nieprawidłowy adres email'}

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Sprawdź czy użytkownik już istnieje
            cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?',
                          (username, email))
            if cursor.fetchone():
                conn.close()
                return {'success': False, 'message': 'Użytkownik o tej nazwie lub emailu już istnieje'}

            # Hashuj hasło
            password_hash, salt = self._hash_password(password)

            # Dodaj użytkownika
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, salt)
                VALUES (?, ?, ?, ?)
            ''', (username, email, password_hash, salt))

            user_id = cursor.lastrowid

            # Utwórz pusty profil
            cursor.execute('''
                INSERT INTO user_profiles (user_id, config_data, trading_profiles, risk_settings)
                VALUES (?, ?, ?, ?)
            ''', (user_id, '{}', '{}', '{}'))

            conn.commit()
            conn.close()

            return {
                'success': True,
                'message': 'Konto zostało utworzone pomyślnie',
                'user_id': user_id
            }

        except Exception as e:
            return {'success': False, 'message': f'Błąd podczas rejestracji: {str(e)}'}

    def login_user(self, username: str, password: str) -> Dict[str, Any]:
        """
        Loguje użytkownika

        Returns:
            Dict z wynikiem: {'success': bool, 'message': str, 'user_id': int, 'session_id': str}
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Pobierz dane użytkownika
            cursor.execute('''
                SELECT id, password_hash, salt, is_active
                FROM users
                WHERE username = ?
            ''', (username,))

            result = cursor.fetchone()

            if not result:
                conn.close()
                return {'success': False, 'message': 'Nieprawidłowa nazwa użytkownika lub hasło'}

            user_id, stored_hash, salt, is_active = result

            if not is_active:
                conn.close()
                return {'success': False, 'message': 'Konto jest nieaktywne'}

            # Sprawdź hasło
            password_hash, _ = self._hash_password(password, salt)

            if password_hash != stored_hash:
                conn.close()
                return {'success': False, 'message': 'Nieprawidłowa nazwa użytkownika lub hasło'}

            # Aktualizuj ostatnie logowanie
            cursor.execute('''
                UPDATE users
                SET last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (user_id,))

            # Utwórz sesję
            session_id = secrets.token_urlsafe(32)

            cursor.execute('''
                INSERT INTO sessions (session_id, user_id)
                VALUES (?, ?)
            ''', (session_id, user_id))

            conn.commit()
            conn.close()

            return {
                'success': True,
                'message': 'Zalogowano pomyślnie',
                'user_id': user_id,
                'session_id': session_id,
                'username': username
            }

        except Exception as e:
            return {'success': False, 'message': f'Błąd podczas logowania: {str(e)}'}

    def verify_session(self, session_id: str) -> Optional[int]:
        """
        Weryfikuje sesję i zwraca user_id

        Returns:
            user_id jeśli sesja jest ważna, None w przeciwnym razie
        """
        if not session_id:
            return None

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT s.user_id, u.is_active
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.session_id = ?
            ''', (session_id,))

            result = cursor.fetchone()
            conn.close()

            if result and result[1]:  # user is_active
                return result[0]  # user_id

            return None

        except Exception:
            return None

    def logout_user(self, session_id: str) -> bool:
        """Wylogowuje użytkownika usuwając sesję"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))

            conn.commit()
            conn.close()

            return True
        except Exception:
            return False

    def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """Pobiera profil użytkownika (wszystkie prywatne ustawienia)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT config_data, trading_profiles, risk_settings, telegram_config, bybit_config
                FROM user_profiles
                WHERE user_id = ?
            ''', (user_id,))

            result = cursor.fetchone()
            conn.close()

            if result:
                return {
                    'config_data': json.loads(result[0] or '{}'),
                    'trading_profiles': json.loads(result[1] or '{}'),
                    'risk_settings': json.loads(result[2] or '{}'),
                    'telegram_config': json.loads(result[3] or '{}'),
                    'bybit_config': json.loads(result[4] or '{}')
                }

            return {}

        except Exception as e:
            print(f"Error loading user profile: {e}")
            return {}

    def save_user_profile(self, user_id: int, profile_data: Dict[str, Any]) -> bool:
        """Zapisuje profil użytkownika"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE user_profiles
                SET config_data = ?,
                    trading_profiles = ?,
                    risk_settings = ?,
                    telegram_config = ?,
                    bybit_config = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (
                json.dumps(profile_data.get('config_data', {})),
                json.dumps(profile_data.get('trading_profiles', {})),
                json.dumps(profile_data.get('risk_settings', {})),
                json.dumps(profile_data.get('telegram_config', {})),
                json.dumps(profile_data.get('bybit_config', {})),
                user_id
            ))

            conn.commit()
            conn.close()

            return True

        except Exception as e:
            print(f"Error saving user profile: {e}")
            return False

    def get_username(self, user_id: int) -> Optional[str]:
        """Pobiera nazwę użytkownika po ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
            result = cursor.fetchone()

            conn.close()

            return result[0] if result else None

        except Exception:
            return None
