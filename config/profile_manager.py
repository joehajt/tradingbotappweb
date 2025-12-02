"""
Profile Manager Module
Handles saving and loading of trading bot configuration profiles
"""

import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Profile file path
PROFILES_FILE = "trading_profiles.json"


class ProfileManager:
    """Zarządzanie profilami handlowymi"""

    def __init__(self):
        self.profiles = self.load_profiles()

    def load_profiles(self):
        """Wczytaj profile z pliku"""
        try:
            if os.path.exists(PROFILES_FILE):
                with open(PROFILES_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"❌ Błąd wczytywania profili: {e}")
            return {}

    def save_profiles(self):
        """Zapisz profile do pliku"""
        try:
            with open(PROFILES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.profiles, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"❌ Błąd zapisu profili: {e}")
            return False

    def save_profile(self, name, config_data):
        """Zapisz profil"""
        self.profiles[name] = {
            'timestamp': datetime.now().isoformat(),
            'config': config_data
        }
        return self.save_profiles()

    def load_profile(self, name):
        """Wczytaj profil"""
        return self.profiles.get(name, {}).get('config', {})

    def delete_profile(self, name):
        """Usuń profil"""
        if name in self.profiles:
            del self.profiles[name]
            return self.save_profiles()
        return False
