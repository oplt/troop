from sqlalchemy.pool import NullPool

from backend.core.config import settings
from backend.db.session import engine


def test_engine_uses_connection_pool_not_null_pool():
    assert not isinstance(engine.pool, NullPool)


def test_database_pool_settings_have_sensible_defaults():
    assert settings.DATABASE_POOL_SIZE >= 1
    assert settings.DATABASE_MAX_OVERFLOW >= 0
    assert settings.DATABASE_POOL_SIZE_WORKER >= 1
    assert settings.DATABASE_MAX_OVERFLOW_WORKER >= 0
    assert settings.DATABASE_POOL_RECYCLE_SECONDS >= 0
    assert settings.DATABASE_POOL_TIMEOUT_SECONDS >= 1
    assert settings.effective_database_pool_size >= 1
    assert settings.effective_database_max_overflow >= 0
    assert settings.database_process_role in {"api", "worker"}


def test_vector_write_and_fallback_flags_default_off():
    assert settings.VECTOR_WRITE_EMBEDDING_JSON is False
    assert settings.vector_python_fallback_enabled is False
    assert settings.PROJECT_DECISIONS_MERGE_LIMIT >= 1
