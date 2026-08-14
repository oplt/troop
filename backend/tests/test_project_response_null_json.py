"""Project response coercion for nullable JSON columns."""

from __future__ import annotations

from types import SimpleNamespace

from backend.modules.orchestration.presenters import to_project_response
from backend.modules.orchestration.schemas.projects import ProjectResponse


def test_project_response_coerces_null_json_columns() -> None:
    item = SimpleNamespace(
        id="proj-1",
        name="Demo",
        slug="demo",
        description=None,
        status="active",
        goals_markdown=None,
        settings_json=None,
        memory_scope="project",
        knowledge_summary=None,
        company_id=None,
        department_id=None,
        knowledge_policy_json=None,
        budget_json=None,
        metadata_json=None,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    response = to_project_response(item)
    assert response.budget == {}
    assert response.metadata == {}
    assert response.knowledge_policy == {}
    assert response.settings == {}


def test_project_response_schema_coerces_explicit_nulls() -> None:
    response = ProjectResponse(
        id="proj-2",
        name="Legacy",
        slug="legacy",
        description=None,
        status="active",
        goals_markdown="",
        settings=None,
        memory_scope="project",
        knowledge_summary=None,
        budget=None,
        metadata=None,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    assert response.budget == {}
    assert response.metadata == {}
    assert response.settings == {}
