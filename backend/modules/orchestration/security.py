import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from backend.core.config import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    secret_bytes = settings.JWT_SECRET.encode("utf-8")
    key = base64.urlsafe_b64encode(secret_bytes[:32].ljust(32, b"0"))
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = value.strip()
    if len(trimmed) <= 8:
        return "*" * len(trimmed)
    return f"{trimmed[:4]}...{trimmed[-4:]}"
