from sqlalchemy.pool import NullPool

from backend.core.config import settings
from backend.db.session import engine


def test_engine_uses_connection_pool_not_null_pool():
    assert not isinstance(engine.pool, NullPool)


def test_database_pool_settings_have_sensible_defaults():
    assert settings.DATABASE_POOL_SIZE >= 1
    assert settings.DATABASE_MAX_OVERFLOW >= 0
    assert settings.DATABASE_POOL_RECYCLE_SECONDS >= 0
    assert settings.DATABASE_POOL_TIMEOUT_SECONDS >= 1
