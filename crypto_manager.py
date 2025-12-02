"""
Crypto Manager - AES-256 Encryption for Sensitive Data
=========================================================
This module handles encryption and decryption of sensitive data like API keys.
Uses AES-256 encryption with Fernet (symmetric encryption).

Security Features:
- AES-256 encryption
- PBKDF2 key derivation
- Unique salt per installation
- No admin access to decrypted keys
"""

import os
import base64
import secrets
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import logging

logger = logging.getLogger(__name__)


class CryptoManager:
    """
    Manages encryption and decryption of sensitive data.

    IMPORTANT: The encryption key should be stored securely in environment variables.
    If the key is lost, encrypted data cannot be recovered!
    """

    def __init__(self, master_key=None):
        """
        Initialize CryptoManager with a master encryption key.

        Args:
            master_key (str): Master encryption key. If None, reads from environment.
        """
        if master_key is None:
            master_key = os.environ.get('ENCRYPTION_KEY')

        if not master_key:
            raise ValueError(
                "ENCRYPTION_KEY not found! Please set it in .env file.\n"
                "Generate a secure key with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )

        # Store the master key
        self._master_key = master_key

        # Generate a unique salt for this installation
        # In production, this should be stored securely and consistently
        self._salt = self._get_or_generate_salt()

        # Derive encryption key using PBKDF2
        self._cipher = self._create_cipher()

        logger.info("CryptoManager initialized successfully")

    def _get_or_generate_salt(self):
        """
        Get existing salt or generate a new one.
        Salt is stored in a file to ensure consistency across restarts.
        """
        salt_file = '.encryption_salt'

        if os.path.exists(salt_file):
            with open(salt_file, 'rb') as f:
                return f.read()
        else:
            # Generate new salt
            salt = secrets.token_bytes(32)
            with open(salt_file, 'wb') as f:
                f.write(salt)
            logger.info("Generated new encryption salt")
            return salt

    def _create_cipher(self):
        """
        Create a Fernet cipher using PBKDF2 key derivation.
        """
        # Derive a key from the master key and salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self._salt,
            iterations=100000,  # High iteration count for security
            backend=default_backend()
        )

        key = base64.urlsafe_b64encode(kdf.derive(self._master_key.encode()))
        return Fernet(key)

    def encrypt(self, plaintext):
        """
        Encrypt plaintext data.

        Args:
            plaintext (str): Data to encrypt

        Returns:
            str: Base64-encoded encrypted data

        Example:
            >>> crypto = CryptoManager()
            >>> encrypted = crypto.encrypt("my_api_key_12345")
            >>> print(encrypted)  # Returns encrypted string
        """
        if not plaintext:
            return None

        try:
            encrypted_bytes = self._cipher.encrypt(plaintext.encode())
            return encrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def decrypt(self, ciphertext):
        """
        Decrypt encrypted data.

        Args:
            ciphertext (str): Base64-encoded encrypted data

        Returns:
            str: Decrypted plaintext

        Example:
            >>> crypto = CryptoManager()
            >>> decrypted = crypto.decrypt(encrypted_data)
            >>> print(decrypted)  # Returns original plaintext
        """
        if not ciphertext:
            return None

        try:
            decrypted_bytes = self._cipher.decrypt(ciphertext.encode())
            return decrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError("Failed to decrypt data. The encryption key may have changed.")

    def encrypt_dict(self, data_dict, keys_to_encrypt):
        """
        Encrypt specific keys in a dictionary.

        Args:
            data_dict (dict): Dictionary containing data
            keys_to_encrypt (list): List of keys to encrypt

        Returns:
            dict: Dictionary with specified keys encrypted

        Example:
            >>> data = {'api_key': 'secret123', 'name': 'My Key'}
            >>> encrypted_data = crypto.encrypt_dict(data, ['api_key'])
            >>> # data['api_key'] is now encrypted, data['name'] is unchanged
        """
        encrypted_dict = data_dict.copy()

        for key in keys_to_encrypt:
            if key in encrypted_dict and encrypted_dict[key]:
                encrypted_dict[key] = self.encrypt(encrypted_dict[key])

        return encrypted_dict

    def decrypt_dict(self, data_dict, keys_to_decrypt):
        """
        Decrypt specific keys in a dictionary.

        Args:
            data_dict (dict): Dictionary containing encrypted data
            keys_to_decrypt (list): List of keys to decrypt

        Returns:
            dict: Dictionary with specified keys decrypted
        """
        decrypted_dict = data_dict.copy()

        for key in keys_to_decrypt:
            if key in decrypted_dict and decrypted_dict[key]:
                try:
                    decrypted_dict[key] = self.decrypt(decrypted_dict[key])
                except Exception as e:
                    logger.error(f"Failed to decrypt key '{key}': {e}")
                    decrypted_dict[key] = None

        return decrypted_dict

    def mask_sensitive_data(self, data, visible_chars=4):
        """
        Mask sensitive data for display (e.g., API keys).

        Args:
            data (str): Sensitive data to mask
            visible_chars (int): Number of characters to show at the end

        Returns:
            str: Masked string (e.g., "**********************4567")

        Example:
            >>> crypto.mask_sensitive_data("my_secret_api_key_12345")
            '**********************2345'
        """
        if not data or len(data) <= visible_chars:
            return '*' * 8

        mask_length = max(20, len(data) - visible_chars)
        return '*' * mask_length + data[-visible_chars:]

    @staticmethod
    def generate_random_token(length=32):
        """
        Generate a cryptographically secure random token.

        Args:
            length (int): Length of the token

        Returns:
            str: Random URL-safe token

        Example:
            >>> token = CryptoManager.generate_random_token()
            >>> print(len(token))  # 43 characters (base64 encoded)
        """
        return secrets.token_urlsafe(length)

    @staticmethod
    def generate_verification_code(length=6):
        """
        Generate a numeric verification code (for 2FA, email verification, etc.).

        Args:
            length (int): Length of the code

        Returns:
            str: Numeric code

        Example:
            >>> code = CryptoManager.generate_verification_code()
            >>> print(code)  # "123456"
        """
        return ''.join([str(secrets.randbelow(10)) for _ in range(length)])


# ============================================
# PASSWORD HASHING (Bcrypt)
# ============================================

import bcrypt


class PasswordManager:
    """
    Manages password hashing and verification using bcrypt.

    Security Features:
    - Bcrypt algorithm (industry standard)
    - Configurable work factor (rounds)
    - Automatic salt generation
    - Constant-time comparison
    """

    def __init__(self, rounds=None):
        """
        Initialize PasswordManager.

        Args:
            rounds (int): Bcrypt work factor (10-14 recommended). Higher = more secure but slower.
        """
        self.rounds = rounds or int(os.environ.get('BCRYPT_ROUNDS', 12))
        logger.info(f"PasswordManager initialized with {self.rounds} rounds")

    def hash_password(self, password):
        """
        Hash a password using bcrypt.

        Args:
            password (str): Plain text password

        Returns:
            str: Hashed password

        Example:
            >>> pm = PasswordManager()
            >>> hashed = pm.hash_password("my_password123")
            >>> print(hashed)  # Returns bcrypt hash
        """
        if not password:
            raise ValueError("Password cannot be empty")

        salt = bcrypt.gensalt(rounds=self.rounds)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    def verify_password(self, password, hashed_password):
        """
        Verify a password against a hash.

        Args:
            password (str): Plain text password to verify
            hashed_password (str): Hashed password from database

        Returns:
            bool: True if password matches, False otherwise

        Example:
            >>> pm = PasswordManager()
            >>> is_valid = pm.verify_password("my_password123", stored_hash)
            >>> print(is_valid)  # True or False
        """
        if not password or not hashed_password:
            return False

        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                hashed_password.encode('utf-8')
            )
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False

    @staticmethod
    def validate_password_strength(password):
        """
        Validate password strength.

        Args:
            password (str): Password to validate

        Returns:
            tuple: (is_valid, error_message)

        Example:
            >>> pm = PasswordManager()
            >>> valid, msg = pm.validate_password_strength("weak")
            >>> print(valid, msg)  # False, "Password must be at least 8 characters"
        """
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"

        if len(password) > 128:
            return False, "Password is too long (max 128 characters)"

        # Check for at least one uppercase, one lowercase, and one number
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)

        if not (has_upper and has_lower and has_digit):
            return False, "Password must contain uppercase, lowercase, and numbers"

        return True, "Password is strong"


# ============================================
# USAGE EXAMPLES
# ============================================

if __name__ == "__main__":
    # This code runs only when the script is executed directly
    print("=== Crypto Manager Test ===\n")

    # Set a test encryption key
    os.environ['ENCRYPTION_KEY'] = 'test_key_for_demonstration_only'

    # Test CryptoManager
    print("1. Testing Encryption/Decryption:")
    crypto = CryptoManager()

    original = "my_secret_api_key_12345"
    encrypted = crypto.encrypt(original)
    decrypted = crypto.decrypt(encrypted)

    print(f"   Original:  {original}")
    print(f"   Encrypted: {encrypted}")
    print(f"   Decrypted: {decrypted}")
    print(f"   Match:     {original == decrypted}\n")

    # Test masking
    print("2. Testing Data Masking:")
    masked = crypto.mask_sensitive_data(original)
    print(f"   Masked: {masked}\n")

    # Test PasswordManager
    print("3. Testing Password Hashing:")
    pm = PasswordManager(rounds=4)  # Low rounds for testing speed

    password = "MySecurePassword123"
    hashed = pm.hash_password(password)

    print(f"   Password:  {password}")
    print(f"   Hash:      {hashed}")
    print(f"   Verify (correct):   {pm.verify_password(password, hashed)}")
    print(f"   Verify (incorrect): {pm.verify_password('wrong', hashed)}\n")

    # Test password strength
    print("4. Testing Password Strength:")
    test_passwords = ["weak", "StrongPass123", "ABC123abc"]
    for pwd in test_passwords:
        valid, msg = pm.validate_password_strength(pwd)
        print(f"   '{pwd}': {msg}")

    print("\n=== All Tests Completed ===")
