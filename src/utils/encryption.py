# encryption.py
import os
from cryptography.fernet import Fernet
from src.config import settings

class EncryptionManager:
    def __init__(self):
        key = os.getenv("ENCRYPTION_KEY")
        if not key:
            key = Fernet.generate_key().decode()
        self.cipher = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt_token(self, token: str) -> str:
        return self.cipher.encrypt(token.encode()).decode()

    def decrypt_token(self, encrypted_token: str) -> str:
        return self.cipher.decrypt(encrypted_token.encode()).decode()