"""SEC-001: GitHub tool resources must resolve within tenant/project scope."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from backend.db.session import SessionLocal
from backend.modules.github.models import GithubConnection, GithubIssueLink, GithubRepository
from backend.modules.identity_access.models import User
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.tools import OrchestrationToolbox, ToolExecutionError
from backend.modules.projects.orchestration_models import OrchestratorProject
from sqlalchemy import delete

pytestmark_integration = pytest.mark.integration


async def _create_project(owner_id: str, *, suffix: str) -> OrchestratorProject:
    async with SessionLocal() as db:
        repo = OrchestrationRepository(db)
        project = await repo.create_project(
            owner_id=owner_id,
            name=f"GitHub tenant test {suffix}",
            slug=f"github-tenant-{suffix}",
        )
        await db.commit()
        await db.refresh(project)
        return project


async def _create_github_fixture(
    owner_id: str,
    *,
    suffix: str,
    full_name: str,
    project_id: str | None = None,
) -> tuple[GithubConnection, GithubRepository, GithubIssueLink]:
    async with SessionLocal() as db:
        repo = OrchestrationRepository(db)
        connection = await repo.create_github_connection(
            owner_id=owner_id,
            name=f"conn-{suffix}",
            encrypted_token="enc:test-token",
        )
        repository = await repo.create_github_repository(
            connection_id=connection.id,
            project_id=project_id,
            owner_name="acme",
            repo_name=f"repo-{suffix}",
            full_name=full_name,
        )
        issue_link = await repo.create_issue_link(
            repository_id=repository.id,
            issue_number=42,
            title=f"Issue {suffix}",
        )
        await db.commit()
        await db.refresh(connection)
        await db.refresh(repository)
        await db.refresh(issue_link)
        return connection, repository, issue_link


async def _cleanup_github_fixture(
    *,
    connection_id: str,
    repository_id: str,
    issue_link_id: str,
) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(GithubIssueLink).where(GithubIssueLink.id == issue_link_id))
        await db.execute(delete(GithubRepository).where(GithubRepository.id == repository_id))
        await db.execute(delete(GithubConnection).where(GithubConnection.id == connection_id))
        await db.commit()


async def _cleanup_project(project_id: str) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(OrchestratorProject).where(OrchestratorProject.id == project_id))
        await db.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_resolve_authorized_repository_rejects_cross_tenant_id(
    tenant_pair: tuple[User, User],
) -> None:
    user_a, user_b = tenant_pair
    suffix = uuid.uuid4().hex[:8]
    shared_full_name = f"acme/shared-{suffix}"
    project_a = await _create_project(user_a.id, suffix=suffix)
    _, repo_b, issue_b = await _create_github_fixture(
        user_b.id, suffix=f"b-{suffix}", full_name=shared_full_name
    )

    try:
        async with SessionLocal() as db:
            repo = OrchestrationRepository(db)
            assert (
                await repo.resolve_authorized_repository(
                    user_a.id,
                    project_id=project_a.id,
                    repository_id=repo_b.id,
                )
                is None
            )
            assert (
                await repo.resolve_authorized_repository(
                    user_a.id,
                    project_id=project_a.id,
                    full_name=shared_full_name,
                )
                is None
            )
            assert (
                await repo.resolve_authorized_issue_link(
                    user_a.id,
                    issue_b.id,
                    project_id=project_a.id,
                )
                is None
            )
    finally:
        await _cleanup_github_fixture(
            connection_id=repo_b.connection_id,
            repository_id=repo_b.id,
            issue_link_id=issue_b.id,
        )
        await _cleanup_project(project_a.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_resolve_authorized_repository_rejects_other_project_scope(
    tenant_pair: tuple[User, User],
) -> None:
    user_a, _user_b = tenant_pair
    suffix = uuid.uuid4().hex[:8]
    project_a = await _create_project(user_a.id, suffix=f"a-{suffix}")
    project_b = await _create_project(user_a.id, suffix=f"b-{suffix}")
    _, repo_scoped, issue_link = await _create_github_fixture(
        user_a.id,
        suffix=suffix,
        full_name=f"acme/scoped-{suffix}",
        project_id=project_b.id,
    )

    try:
        async with SessionLocal() as db:
            repo = OrchestrationRepository(db)
            assert (
                await repo.resolve_authorized_repository(
                    user_a.id,
                    project_id=project_a.id,
                    repository_id=repo_scoped.id,
                )
                is None
            )
            assert (
                await repo.resolve_authorized_issue_link(
                    user_a.id,
                    issue_link.id,
                    project_id=project_a.id,
                )
                is None
            )
            assert (
                await repo.resolve_authorized_repository(
                    user_a.id,
                    project_id=project_b.id,
                    repository_id=repo_scoped.id,
                )
                is not None
            )
    finally:
        await _cleanup_github_fixture(
            connection_id=repo_scoped.connection_id,
            repository_id=repo_scoped.id,
            issue_link_id=issue_link.id,
        )
        await _cleanup_project(project_a.id)
        await _cleanup_project(project_b.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_github_comment_allows_owner_scoped_repository(
    tenant_pair: tuple[User, User],
) -> None:
    user_a, user_b = tenant_pair
    suffix = uuid.uuid4().hex[:8]
    shared_full_name = f"acme/tool-{suffix}"
    project_a = await _create_project(user_a.id, suffix=suffix)
    conn_a, repo_a, issue_a = await _create_github_fixture(
        user_a.id,
        suffix=f"a-{suffix}",
        full_name=shared_full_name,
        project_id=project_a.id,
    )
    _, repo_b, issue_b = await _create_github_fixture(
        user_b.id,
        suffix=f"b-{suffix}",
        full_name=f"acme/other-{suffix}",
    )

    try:
        async with SessionLocal() as db:
            repo = OrchestrationRepository(db)
            project = await db.get(OrchestratorProject, project_a.id)
            assert project is not None
            toolbox = OrchestrationToolbox(
                db=db,
                repo=repo,
                project=project,
                task=None,
                run=None,
            )

            with patch.object(
                toolbox,
                "_github_auth_headers",
                new=AsyncMock(return_value={"Authorization": "Bearer test"}),
            ), patch(
                "backend.modules.orchestration.tools.managed_http_client"
            ) as mock_client_ctx:
                mock_client = AsyncMock()
                mock_response = AsyncMock()
                mock_response.status_code = 201
                mock_response.text = ""
                mock_client.post.return_value = mock_response
                mock_client_ctx.return_value.__aenter__.return_value = mock_client

                result = await toolbox._github_comment(
                    {
                        "repository_id": repo_a.id,
                        "issue_number": 42,
                        "body": "tenant-safe comment",
                    }
                )

            assert result["repository"] == repo_a.full_name
            assert result["comment_posted"] is True

            with pytest.raises(ToolExecutionError, match="not authorized"):
                await toolbox._github_comment(
                    {
                        "repository_id": repo_b.id,
                        "issue_number": 42,
                        "body": "cross-tenant attempt",
                    }
                )

            with pytest.raises(ToolExecutionError, match="not authorized"):
                await toolbox._github_comment(
                    {
                        "repository_full_name": repo_b.full_name,
                        "issue_number": 42,
                        "body": "other tenant full name",
                    }
                )

            with pytest.raises(ToolExecutionError, match="not authorized"):
                await toolbox._github_comment(
                    {
                        "issue_link_id": issue_b.id,
                        "body": "cross-tenant issue link",
                    }
                )
    finally:
        await _cleanup_github_fixture(
            connection_id=conn_a.id,
            repository_id=repo_a.id,
            issue_link_id=issue_a.id,
        )
        await _cleanup_github_fixture(
            connection_id=repo_b.connection_id,
            repository_id=repo_b.id,
            issue_link_id=issue_b.id,
        )
        await _cleanup_project(project_a.id)
