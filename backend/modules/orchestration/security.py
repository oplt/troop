import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from backend.core.config import settings


def _legacy_jwt_fernet_key() -> bytes:
    """Historical key material (JWT_SECRET truncated/padded). Decrypt-only during migration."""
    secret_bytes = settings.JWT_SECRET.encode("utf-8")
    return base64.urlsafe_b64encode(secret_bytes[:32].ljust(32, b"0"))


def _normalize_key(value: str | None) -> str:
    return (value or "").strip()


def _fernet_from_setting(value: str) -> Fernet:
    return Fernet(_normalize_key(value).encode("utf-8"))


def uses_dedicated_encryption_key() -> bool:
    return bool(_normalize_key(settings.SECRETS_ENCRYPTION_KEY))


def encryption_key_status() -> dict[str, bool | str]:
    current = _normalize_key(settings.SECRETS_ENCRYPTION_KEY)
    previous = _normalize_key(settings.SECRETS_ENCRYPTION_PREVIOUS_KEY)
    return {
        "dedicated_key_configured": bool(current),
        "previous_key_configured": bool(previous),
        "legacy_jwt_fallback_active": not bool(current),
        "mode": "dedicated" if current else "legacy_jwt",
    }


@lru_cache(maxsize=1)
def _fernet() -> Fernet | MultiFernet:
    current = _normalize_key(settings.SECRETS_ENCRYPTION_KEY)
    previous = _normalize_key(settings.SECRETS_ENCRYPTION_PREVIOUS_KEY)
    legacy = Fernet(_legacy_jwt_fernet_key())

    if not current:
        return legacy

    keys: list[Fernet] = [_fernet_from_setting(current)]
    if previous and previous != current:
        keys.append(_fernet_from_setting(previous))

    current_bytes = current.encode("utf-8")
    if current_bytes != _legacy_jwt_fernet_key():
        keys.append(legacy)

    if len(keys) == 1:
        return keys[0]
    return MultiFernet(keys)


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


def reencrypt_secret(value: str | None) -> str | None:
    """Decrypt with any configured key ring entry and re-encrypt with the current primary key."""
    if not value:
        return None
    plaintext = decrypt_secret(value)
    if plaintext is None:
        return None
    refreshed = encrypt_secret(plaintext)
    return refreshed if refreshed != value else value


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = value.strip()
    if len(trimmed) <= 8:
        return "*" * len(trimmed)
    return f"{trimmed[:4]}...{trimmed[-4:]}"
