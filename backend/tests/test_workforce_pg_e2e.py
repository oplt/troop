"""PostgreSQL live HTTP E2E for the workforce runtime path.

Uses existing integration fixtures (auth cookies + CSRF + real Postgres/Redis).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from backend.tests.conftest import csrf_headers

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _ensure_tool_definition(db, slug: str) -> str:
    from backend.modules.workforce.repository import WorkforceRepository
    from backend.modules.workforce.services.tool_registry import ToolRegistryService

    repo = WorkforceRepository(db)
    existing = await repo.get_tool_definition(slug)
    if existing:
        return existing.id
    registry = ToolRegistryService(db)
    await registry.seed_tool_definitions()
    existing = await repo.get_tool_definition(slug)
    assert existing is not None, f"tool definition missing for {slug}"
    return existing.id


async def test_workforce_pg_runtime_e2e_skill_snapshot_immutability(
    auth_client: AsyncClient,
    verified_user: tuple,
) -> None:
    """Full runtime path: analyze → publish skill → agent → run → snapshot immutability."""
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
    analysis_body = analysis.json()
    assert analysis_body.get("required_tools_json") or analysis_body.get("required_capabilities_json")
    raw = analysis_body.get("raw_output_json") or {}
    if isinstance(raw, dict):
        assert raw.get("analysis_mode") == "deterministic"

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
    skill_id = skill["id"]
    version_v1_id = skill.get("current_version_id")
    assert version_v1_id, skill

    agent_slug = f"e2e-agent-{suffix}"
    agent_resp = await auth_client.post(
        "/api/v1/orchestration/agents",
        headers=headers,
        json={
            "name": f"E2E Agent {suffix}",
            "slug": agent_slug,
            "role": "worker",
            "project_id": project_id,
            "capabilities": ["web_research"],
            "allowed_tools": ["web_search", "knowledge_search"],
        },
    )
    assert agent_resp.status_code == 201, agent_resp.text
    agent_id = agent_resp.json()["id"]

    activate = await auth_client.patch(
        f"/api/v1/orchestration/agents/{agent_id}",
        headers=headers,
        json={"is_active": True},
    )
    assert activate.status_code == 200, activate.text

    from backend.db.session import SessionLocal
    from backend.modules.orchestration.repository import OrchestrationRepository
    from backend.modules.workforce.models import ToolGrant
    from backend.modules.workforce.repository import WorkforceRepository

    async with SessionLocal() as db:
        repo = WorkforceRepository(db)
        orch = OrchestrationRepository(db)
        await repo.create_agent_skill_assignment(
            agent_id=agent_id,
            skill_id=skill_id,
            skill_version_id=version_v1_id,
            version_policy="pinned",
            priority=0,
            enabled=True,
        )
        membership = await orch.get_project_membership(project_id, agent_id)
        if membership is None:
            await orch.create_project_membership(project_id=project_id, agent_id=agent_id)
        tool_def_id = await _ensure_tool_definition(db, "web_search")
        db.add(
            ToolGrant(
                tool_definition_id=tool_def_id,
                subject_type="project",
                subject_id=project_id,
                effect="allow",
            )
        )
        await db.commit()

    run = await auth_client.post(
        f"/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/runs",
        headers=headers,
        json={
            "run_mode": "single_agent",
            "worker_agent_id": agent_id,
            "input_payload": {"prompt": "workforce e2e"},
        },
    )
    assert run.status_code == 201, run.text
    run_body = run.json()
    run_id = run_body["id"]
    checkpoint = run_body.get("checkpoint_json") or {}
    snapshot = checkpoint.get("skill_version_snapshot") or {}
    frozen_ids = snapshot.get("skill_version_ids") or []
    assert version_v1_id in frozen_ids, snapshot
    assert checkpoint.get("snapshot_status") == "frozen"

    events = await auth_client.get(f"/api/v1/orchestration/runs/{run_id}/events")
    assert events.status_code == 200
    assert isinstance(events.json(), list)

    draft_v2 = await auth_client.post(
        "/api/v1/workforce/skill-drafts",
        headers=headers,
        json={
            "name": f"E2E Research {suffix}",
            "slug": f"e2e-research-{suffix}-v2",
            "purpose": "Research v2",
            "when_to_use": "research tasks v2",
            "instructions_markdown": "Updated instructions for version two.",
            "capabilities": ["web_research"],
            "required_tools": ["web_search", "web_fetch"],
            "tools": ["web_search", "web_fetch"],
            "scope": "project",
            "source_project_id": project_id,
            "company_id": company_id,
            "skill_id": skill_id,
            "risk_level": "low",
        },
    )
    assert draft_v2.status_code in {200, 201}, draft_v2.text
    draft_v2_id = draft_v2.json()["id"]

    validated_v2 = await auth_client.post(
        f"/api/v1/workforce/skill-drafts/{draft_v2_id}/validate",
        headers=headers,
    )
    assert validated_v2.status_code < 500, validated_v2.text

    published_v2 = await auth_client.post(
        f"/api/v1/workforce/skill-drafts/{draft_v2_id}/publish",
        headers=headers,
    )
    assert published_v2.status_code in {200, 201}, published_v2.text
    version_v2_id = published_v2.json().get("current_version_id")
    assert version_v2_id and version_v2_id != version_v1_id

    fetched = await auth_client.get(f"/api/v1/orchestration/runs/{run_id}")
    assert fetched.status_code == 200
    fetched_snapshot = (fetched.json().get("checkpoint_json") or {}).get(
        "skill_version_snapshot"
    ) or {}
    fetched_ids = fetched_snapshot.get("skill_version_ids") or []
    assert version_v1_id in fetched_ids
    assert version_v2_id not in fetched_ids

    # --- Approval + one-time consume + skill usage recording (best-effort via services) ---
    from datetime import UTC, datetime

    from sqlalchemy import select

    from backend.modules.orchestration.models import ApprovalRequest, TaskRun
    from backend.modules.orchestration.skill_evaluation_hooks import record_skill_usage_for_run
    from backend.modules.orchestration.tool_execution_context import (
        arguments_hash,
        consume_or_check_tool_approval,
    )
    from backend.modules.orchestration.tools import OrchestrationToolbox, ToolExecutionError
    from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask
    from backend.modules.team.models import AgentProfile
    from backend.modules.workforce.models import SkillEvaluation, SkillUsageStat, ToolGrant

    fs_write_args = {"path": f"e2e-{suffix}.txt", "content": "approved write"}
    fs_args_hash = arguments_hash(fs_write_args)
    owner_id = str(verified_user[0].id)

    async with SessionLocal() as db:
        orch_repo = OrchestrationRepository(db)
        tool_def_id = await _ensure_tool_definition(db, "fs_write")
        db.add(
            ToolGrant(
                tool_definition_id=tool_def_id,
                subject_type="project",
                subject_id=project_id,
                effect="allow",
            )
        )
        agent_row = await db.get(AgentProfile, agent_id)
        if agent_row is not None:
            tools = list(agent_row.allowed_tools_json or [])
            if "fs_write" not in tools:
                tools.append("fs_write")
                agent_row.allowed_tools_json = tools

        approval = ApprovalRequest(
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            requested_by_user_id=owner_id,
            approved_by_user_id=owner_id,
            approval_type="tool:fs_write",
            status="approved",
            payload_json={
                "action_key": "tool:fs_write",
                "arguments_hash": fs_args_hash,
                "tool": "fs_write",
            },
            resolved_at=datetime.now(UTC),
        )
        db.add(approval)
        await db.commit()

    async with SessionLocal() as db:
        orch_repo = OrchestrationRepository(db)
        assert await consume_or_check_tool_approval(
            db,
            owner_id=owner_id,
            tool_name="fs_write",
            arguments_hash=fs_args_hash,
            run_id=run_id,
            task_id=task_id,
            project_id=project_id,
            agent_id=agent_id,
            consume=False,
            require_arguments_hash=True,
        )

        project_row = await db.get(OrchestratorProject, project_id)
        task_row = await db.get(OrchestratorTask, task_id)
        run_row = await db.get(TaskRun, run_id)
        assert project_row is not None and task_row is not None and run_row is not None

        toolbox = OrchestrationToolbox(
            db=db,
            repo=orch_repo,
            project=project_row,
            task=task_row,
            run=run_row,
        )
        write_result = await toolbox.execute({"tool": "fs_write", "arguments": fs_write_args})
        assert write_result.get("path") == fs_write_args["path"]

        assert await consume_or_check_tool_approval(
            db,
            owner_id=owner_id,
            tool_name="fs_write",
            arguments_hash=fs_args_hash,
            run_id=run_id,
            task_id=task_id,
            project_id=project_id,
            agent_id=agent_id,
            consume=True,
            require_arguments_hash=True,
        ) is False

        with pytest.raises(ToolExecutionError, match="APPROVAL_REQUIRED"):
            await toolbox.execute({"tool": "fs_write", "arguments": fs_write_args})

        snapshot_ids = (
            (run_row.checkpoint_json or {}).get("skill_version_snapshot") or {}
        ).get("skill_version_ids") or []
        assert version_v1_id in snapshot_ids

        await record_skill_usage_for_run(
            db,
            agent_id=agent_id,
            task_id=task_id,
            run_id=run_id,
            success=True,
            used_skill_version_ids=[str(v) for v in snapshot_ids],
            run=run_row,
        )

        evaluations = (
            await db.execute(
                select(SkillEvaluation).where(
                    SkillEvaluation.skill_id == skill_id,
                    SkillEvaluation.run_id == run_id,
                )
            )
        ).scalars().all()
        assert evaluations, "expected skill evaluation for completed run path"
        eval_version_ids = {row.skill_version_id for row in evaluations}
        assert version_v1_id in eval_version_ids
        assert version_v2_id not in eval_version_ids

        usage_stats = (
            await db.execute(
                select(SkillUsageStat).where(SkillUsageStat.skill_id == skill_id)
            )
        ).scalars().all()
        v1_stat = next((s for s in usage_stats if s.skill_version_id == version_v1_id), None)
        v2_stat = next((s for s in usage_stats if s.skill_version_id == version_v2_id), None)
        assert v1_stat is not None and v1_stat.run_count >= 1
        assert v2_stat is None or v2_stat.run_count == 0
