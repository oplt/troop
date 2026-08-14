"""P5.5 multi-tenant ACL regression suite (P0.2 / P0.3 class bugs)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import delete

from backend.db.session import SessionLocal
from backend.modules.github.models import GithubConnection, GithubRepository, GithubSyncEvent
from backend.modules.identity_access.models import User
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.team.models import AgentProfile

pytestmark_integration = pytest.mark.integration


def _compile_sql(stmt: Any) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class CaptureDb:
    """Minimal async session stub that records SQLAlchemy statements."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    async def execute(self, stmt: Any) -> MagicMock:
        self.statements.append(stmt)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        result.all.return_value = []
        return result

    async def flush(self) -> None:
        return None


@pytest.fixture
def capture_repo() -> tuple[OrchestrationRepository, CaptureDb]:
    db = CaptureDb()
    return OrchestrationRepository(db), db


@pytest.mark.parametrize("owner_id", ["owner-a", "owner-b"])
def test_approval_owner_clause_binds_requester_for_null_project(owner_id: str) -> None:
    clause = OrchestrationRepository._approval_owner_clause(owner_id)
    compiled = _compile_sql(clause)
    assert owner_id in compiled
    assert "requested_by_user_id" in compiled
    assert "project_id IS NULL" in compiled


@pytest.mark.asyncio
async def test_list_approvals_query_requires_owner_or_requester(capture_repo) -> None:
    repo, db = capture_repo
    await repo.list_approvals("owner-a", status="pending")
    assert db.statements, "expected list_approvals to execute a query"
    compiled = _compile_sql(db.statements[0])
    assert "owner-a" in compiled
    assert "requested_by_user_id" in compiled
    assert "repository_id IS NULL" not in compiled.upper()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        ("list_sync_events", ("owner-a",)),
        ("list_sync_events", ("owner-a", "project-1")),
    ],
)
async def test_sync_event_queries_require_connection_owner(
    capture_repo, method_name: str, args: tuple[str, ...]
) -> None:
    repo, db = capture_repo
    await getattr(repo, method_name)(*args)
    assert db.statements
    compiled = _compile_sql(db.statements[0]).upper()
    assert "OWNER-A" in compiled
    assert "REPOSITORY_ID IS NULL" not in compiled


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("project_id", "expect_global_only"),
    [
        (None, True),
        ("project-1", False),
    ],
)
async def test_list_agents_scopes_by_owner_and_project_scope(
    capture_repo, project_id: str | None, expect_global_only: bool
) -> None:
    repo, db = capture_repo
    await repo.list_agents("owner-a", project_id=project_id)
    compiled = _compile_sql(db.statements[0])
    assert "owner-a" in compiled
    if expect_global_only:
        assert "project_id IS NULL" in compiled
    else:
        assert "project_id" in compiled
        assert "project-1" in compiled


@pytest.mark.asyncio
async def test_company_semantic_memory_list_requires_owner_and_null_project(
    capture_repo,
) -> None:
    repo, db = capture_repo
    await repo.list_semantic_memory_entries_for_company("owner-a", "company-1")
    compiled = _compile_sql(db.statements[0])
    assert "owner-a" in compiled
    assert "company-1" in compiled
    assert "project_id IS NULL" in compiled


@pytest.mark.asyncio
async def test_get_agent_requires_matching_owner(capture_repo) -> None:
    repo, db = capture_repo
    await repo.get_agent("owner-a", "agent-123")
    compiled = _compile_sql(db.statements[0])
    assert "owner-a" in compiled
    assert "agent-123" in compiled


@pytest.mark.asyncio
@pytest.mark.integration
async def test_null_project_approval_not_visible_to_other_tenant(tenant_pair: tuple[User, User]) -> None:
    user_a, user_b = tenant_pair
    approval_id: str | None = None
    async with SessionLocal() as db:
        repo = OrchestrationRepository(db)
        approval = await repo.create_approval(
            project_id=None,
            requested_by_user_id=user_a.id,
            approval_type="tenant_isolation_test",
            status="pending",
            payload_json={"probe": True},
        )
        await db.commit()
        approval_id = approval.id

        a_visible = await repo.list_approvals(user_a.id, status="pending")
        b_visible = await repo.list_approvals(user_b.id, status="pending")
        assert any(row.id == approval_id for row in a_visible)
        assert not any(row.id == approval_id for row in b_visible)
        assert await repo.get_approval(user_a.id, approval_id) is not None
        assert await repo.get_approval(user_b.id, approval_id) is None

    async with SessionLocal() as db:
        await db.execute(delete(ApprovalRequest).where(ApprovalRequest.id == approval_id))
        await db.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_orphan_sync_events_not_listed_cross_tenant(tenant_pair: tuple[User, User]) -> None:
    user_a, user_b = tenant_pair
    suffix = uuid.uuid4().hex[:8]
    connection_id: str | None = None
    repository_id: str | None = None
    linked_event_id: str | None = None
    orphan_event_id: str | None = None

    async with SessionLocal() as db:
        repo = OrchestrationRepository(db)
        connection = GithubConnection(
            owner_id=user_a.id,
            name=f"tenant-test-{suffix}",
            encrypted_token="enc:test",
        )
        db.add(connection)
        await db.flush()
        connection_id = connection.id

        repository = GithubRepository(
            connection_id=connection.id,
            owner_name="acme",
            repo_name=f"repo-{suffix}",
            full_name=f"acme/repo-{suffix}",
        )
        db.add(repository)
        await db.flush()
        repository_id = repository.id

        linked = await repo.create_sync_event(
            repository_id=repository.id,
            action="webhook.issues.opened",
            status="queued",
            payload_json={"tenant_probe": "linked"},
        )
        orphan = await repo.create_sync_event(
            repository_id=None,
            action="webhook.push.ignored",
            status="ignored",
            payload_json={"tenant_probe": "orphan"},
        )
        await db.commit()
        linked_event_id = linked.id
        orphan_event_id = orphan.id

        a_events = await repo.list_sync_events(user_a.id)
        b_events = await repo.list_sync_events(user_b.id)
        a_ids = {event.id for event in a_events}
        b_ids = {event.id for event in b_events}

        assert linked_event_id in a_ids
        assert orphan_event_id not in a_ids
        assert linked_event_id not in b_ids
        assert orphan_event_id not in b_ids

    async with SessionLocal() as db:
        await db.execute(delete(GithubSyncEvent).where(GithubSyncEvent.id.in_([linked_event_id, orphan_event_id])))
        await db.execute(delete(GithubRepository).where(GithubRepository.id == repository_id))
        await db.execute(delete(GithubConnection).where(GithubConnection.id == connection_id))
        await db.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_global_agent_not_readable_by_other_tenant(tenant_pair: tuple[User, User]) -> None:
    user_a, user_b = tenant_pair
    agent_id: str | None = None
    slug = f"global-agent-{uuid.uuid4().hex[:10]}"

    async with SessionLocal() as db:
        repo = OrchestrationRepository(db)
        agent = await repo.create_agent(
            owner_id=user_a.id,
            project_id=None,
            name="Global Probe Agent",
            slug=slug,
        )
        await db.commit()
        agent_id = agent.id

        a_agents = await repo.list_agents(user_a.id, project_id=None)
        b_agents = await repo.list_agents(user_b.id, project_id=None)
        assert any(row.id == agent_id for row in a_agents)
        assert not any(row.id == agent_id for row in b_agents)
        assert await repo.get_agent(user_a.id, agent_id) is not None
        assert await repo.get_agent(user_b.id, agent_id) is None

    async with SessionLocal() as db:
        await db.execute(delete(AgentProfile).where(AgentProfile.id == agent_id))
        await db.commit()
