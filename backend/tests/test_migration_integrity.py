"""Prevent schema drift: single head, models importable after upgrade path."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _script() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def test_alembic_has_exactly_one_head() -> None:
    heads = list(_script().get_heads())
    assert len(heads) == 1, f"Expected one Alembic head, found {heads}"


def test_expected_workforce_schema_objects_are_in_migration_chain() -> None:
    """Guard against models landing without migrations that create them."""
    versions = BACKEND_DIR / "alembic" / "versions"
    contents = "\n".join(path.read_text() for path in versions.glob("*.py"))
    for needle in (
        "department_id",
        "human_assignee_id",
        '"skills"',
        "connector_installations",
        "connector_definitions",
        "trigger_subscriptions",
    ):
        assert needle in contents, f"Migration chain is missing {needle!r}"


def test_sqlalchemy_models_import_after_package_load() -> None:
    from backend.db.base import Base
    from backend.modules.orchestration import models as orchestration_models
    from backend.modules.workforce import models as workforce_models

    _ = workforce_models, orchestration_models
    table_names = set(Base.metadata.tables)
    for required in {
        "skills",
        "connector_definitions",
        "connector_installations",
        "trigger_subscriptions",
        "orchestrator_projects",
        "orchestrator_tasks",
        "task_runs",
    }:
        assert required in table_names
