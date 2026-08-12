"""PostgreSQL live HTTP E2E for the workforce core path.

Uses existing integration fixtures (auth cookies + CSRF + real Postgres/Redis).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from backend.tests.conftest import csrf_headers

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_workforce_pg_core_path_analyze_publish_snapshot_hooks(
    auth_client: AsyncClient,
) -> None:
    """company → department → project → task → analyze → draft → publish."""
    headers = csrf_headers(auth_client)
    suffix = uuid.uuid4().hex[:10]

    company = await auth_client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": f"E2E Co {suffix}", "slug": f"e2e-co-{suffix}"},
    )
    assert company.status_code in {200, 201}, company.text
    company_id = company.json()["id"]

    dept = await auth_client.post(
        "/api/v1/workforce/departments",
        headers=headers,
        json={
            "company_id": company_id,
            "name": "Sales",
            "slug": f"sales-{suffix}",
            "description": "e2e department",
        },
    )
    assert dept.status_code in {200, 201}, dept.text
    department_id = dept.json()["id"]

    project = await auth_client.post(
        "/api/v1/orchestration/projects",
        headers=headers,
        json={
            "name": f"E2E Project {suffix}",
            "slug": f"e2e-proj-{suffix}",
            "description": "workforce e2e",
            "company_id": company_id,
            "department_id": department_id,
        },
    )
    assert project.status_code in {200, 201}, project.text
    project_id = project.json()["id"]

    task = await auth_client.post(
        f"/api/v1/orchestration/projects/{project_id}/tasks",
        headers=headers,
        json={
            "title": "Research greenhouses",
            "description": "Find greenhouse operators in Belgium",
            "objective": "Prospect list",
        },
    )
    assert task.status_code in {200, 201}, task.text
    task_id = task.json()["id"]

    analysis = await auth_client.post(
        f"/api/v1/workforce/tasks/{task_id}/analyze?deterministic=true",
        headers=headers,
    )
    assert analysis.status_code in {200, 201}, analysis.text
    body = analysis.json()
    assert body.get("required_tools_json") or body.get("required_capabilities_json")

    draft = await auth_client.post(
        "/api/v1/workforce/skill-drafts",
        headers=headers,
        json={
            "name": f"E2E Research {suffix}",
            "slug": f"e2e-research-{suffix}",
            "purpose": "Research",
            "when_to_use": "research tasks",
            "instructions_markdown": "Search carefully and cite sources with evidence.",
            "capabilities": ["web_research"],
            "required_tools": ["web_search"],
            "tools": ["web_search"],
            "scope": "project",
            "source_project_id": project_id,
            "company_id": company_id,
            "risk_level": "low",
        },
    )
    assert draft.status_code in {200, 201}, draft.text
    draft_id = draft.json()["id"]

    # Validate then publish
    validated = await auth_client.post(
        f"/api/v1/workforce/skill-drafts/{draft_id}/validate",
        headers=headers,
    )
    assert validated.status_code < 500, validated.text

    published = await auth_client.post(
        f"/api/v1/workforce/skill-drafts/{draft_id}/publish",
        headers=headers,
    )
    assert published.status_code in {200, 201}, published.text
    skill = published.json()
    assert skill.get("id")
    assert skill.get("current_version_id") or skill.get("version") or skill.get("status") == "active"

    # Freeze helpers: ensure snapshot module accepts empty agent (contract)
    from backend.modules.orchestration.models import TaskRun
    from backend.modules.orchestration.skill_snapshot import (
        freeze_skill_version_snapshot,
        get_frozen_skill_version_ids,
    )
    from backend.db.session import SessionLocal

    async with SessionLocal() as db:
        run = TaskRun(
            project_id=project_id,
            task_id=task_id,
            status="queued",
            run_mode="single_agent",
            checkpoint_json={},
        )
        db.add(run)
        await db.flush()
        snapshot = await freeze_skill_version_snapshot(db, run, agent_id=None)
        assert "skill_version_ids" in snapshot
        assert get_frozen_skill_version_ids(run) == []
        await db.rollback()
