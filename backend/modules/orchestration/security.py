import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from backend.core.config import settings


def _legacy_jwt_fernet_key() -> bytes:
    """Historical key material (JWT_SECRET truncated/padded). Kept for decrypt migration only."""
    secret_bytes = settings.JWT_SECRET.encode("utf-8")
    return base64.urlsafe_b64encode(secret_bytes[:32].ljust(32, b"0"))


def _primary_fernet_key() -> bytes:
    configured = (settings.SECRETS_ENCRYPTION_KEY or "").strip()
    if configured:
        return configured.encode("utf-8")
    return _legacy_jwt_fernet_key()


@lru_cache(maxsize=1)
def _fernet() -> Fernet | MultiFernet:
    primary = Fernet(_primary_fernet_key())
    legacy_key = _legacy_jwt_fernet_key()
    if (settings.SECRETS_ENCRYPTION_KEY or "").strip() and _primary_fernet_key() != legacy_key:
        # Encrypt with dedicated key; decrypt accepts dedicated then legacy.
        return MultiFernet([primary, Fernet(legacy_key)])
    return primary


def clear_secrets_fernet_cache() -> None:
    """Test/helper hook after mutating SECRETS_ENCRYPTION_KEY or JWT_SECRET."""
    _fernet.cache_clear()


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
