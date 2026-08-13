"""Fail closed when the application database is behind Alembic head."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.core.logging import get_logger

logger = get_logger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


class SchemaCompatibilityError(RuntimeError):
    """Raised when the live database revision does not match repository head."""


def _alembic_config() -> Config:
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return config


def expected_heads() -> list[str]:
    script = ScriptDirectory.from_config(_alembic_config())
    return list(script.get_heads())


async def assert_database_matches_alembic_head(engine: AsyncEngine) -> str:
    """Ensure the connected database is exactly at the single repository head."""
    heads = expected_heads()
    if len(heads) != 1:
        raise SchemaCompatibilityError(
            f"Repository has {len(heads)} Alembic heads ({', '.join(heads)}); merge before startup"
        )
    expected = heads[0]
    async with engine.connect() as connection:
        def _current(sync_conn) -> str | None:
            context = MigrationContext.configure(sync_conn)
            return context.get_current_revision()

        current = await connection.run_sync(_current)
        if current is None:
            # Distinguish empty/unmigrated DBs from drifted ones.
            tables = (
                await connection.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
            ).scalar_one()
            raise SchemaCompatibilityError(
                "Database has no Alembic revision "
                f"(public tables={tables}). Run `alembic upgrade head` before starting the API."
            )
        if current != expected:
            raise SchemaCompatibilityError(
                f"Database Alembic revision {current!r} does not match repository head "
                f"{expected!r}. Run `alembic upgrade head` before starting the API."
            )
    logger.info("schema_compat ok revision=%s", expected)
    return expected
