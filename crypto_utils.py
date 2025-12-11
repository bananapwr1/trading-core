# trading-core/crypto_utils.py
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)


def get_fernet_key(key_str: str):
    """Получает объект Fernet из ключа."""
    # Ключ должен быть закодирован в base64
    return Fernet(key_str.encode())


def decrypt_data(encrypted_data: str, key_str: str) -> str:
    """Дешифрует строку, используя ключ из .env."""
    try:
        f = get_fernet_key(key_str)
        return f.decrypt(encrypted_data.encode()).decode()
    except Exception as e:
        logger.error(f"❌ Ошибка дешифрования: {e}")
        raise
