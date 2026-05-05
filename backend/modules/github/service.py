from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import attributes as orm_attributes

from backend.core.config import settings
from backend.modules.github.models import GithubConnection, GithubIssueLink, GithubRepository
from backend.modules.identity_access.models import User
from backend.modules.orchestration.models import (
    ApprovalRequest,
    TaskRun,
)
from backend.modules.orchestration.security import decrypt_secret, encrypt_secret, mask_secret
from backend.modules.projects.orchestration_models import (
    OrchestratorProject,
    OrchestratorTask,
    TaskArtifact,
)

logger = logging.getLogger(__name__)


TASK_TRANSITIONS: dict[str, set[str]] = {
    "backlog": {"queued", "archived"},
    "queued": {"planned", "blocked", "failed", "archived"},
    "planned": {"in_progress", "blocked", "archived", "failed"},
    "in_progress": {"blocked", "needs_review", "completed", "failed", "planned"},
    "blocked": {"planned", "in_progress", "failed", "archived"},
    "needs_review": {"approved", "planned", "blocked", "failed"},
    "approved": {"completed", "planned", "archived"},
    "completed": {"synced_to_github", "planned", "archived"},
    "failed": {"planned", "queued", "archived"},
    "synced_to_github": {"archived", "planned"},
    "archived": set(),
}

from backend.modules.memory.entry_types import (
    SEMANTIC_ENTRY_TYPES as _CANONICAL_SEMANTIC_ENTRY_TYPES,
)

SEMANTIC_ENTRY_TYPES = frozenset(_CANONICAL_SEMANTIC_ENTRY_TYPES)

GITHUB_WEBHOOK_EVENT_ALLOWLIST = frozenset(
    {
        "installation",
        "installation_repositories",
        "issues",
        "issue_comment",
        "pull_request",
        "pull_request_review",
        "pull_request_review_comment",
        "push",
        "projects_v2_item",
    }
)


class OrchestrationGithubServiceMixin:
    async def github_issue_summaries_for_link_ids(self, link_ids: list[str]) -> dict[str, dict[str, Any]]:
        return await self.repo.map_github_issue_summaries_by_link_id(link_ids)

    async def github_live_snapshot(self, user: User, project_id: str | None = None) -> dict[str, Any]:
        repositories = await self.repo.list_github_repositories(user.id)
        issue_links = await self.repo.list_issue_links(user.id, project_id)
        sync_events = await self.repo.list_sync_events(user.id, project_id)
        return {
            "project_id": project_id,
            "repositories": len(repositories),
            "linked_issues": len(issue_links),
            "sync_events": {
                "queued": sum(1 for item in sync_events if item.status in {"queued", "pending"}),
                "failed": sum(1 for item in sync_events if item.status in {"failed", "error"}),
                "completed": sum(1 for item in sync_events if item.status == "completed"),
            },
            "latest_event_id": sync_events[0].id if sync_events else None,
        }

    async def build_github_app_install_url(self, user: User) -> str:
        if not settings.GITHUB_APP_SLUG:
            raise HTTPException(status_code=503, detail="GitHub App is not configured")
        state_payload = f"{user.id}:{int(time.time())}"
        encoded_state = base64.urlsafe_b64encode(state_payload.encode("utf-8")).decode("utf-8").rstrip("=")
        return f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new?state={encoded_state}"

    async def finalize_github_app_installation(
        self,
        user: User,
        *,
        installation_id: int,
        setup_action: str | None = None,
        api_url: str = "https://api.github.com",
    ) -> GithubConnection:
        installation = await self._github_app_get_installation(installation_id, api_url=api_url)
        account = installation.get("account") or {}
        account_login = account.get("login") or f"installation-{installation_id}"
        installation_metadata = {
            "connection_mode": "github_app",
            "installation_id": installation_id,
            "account_login": account_login,
            "account_type": account.get("type"),
            "html_url": account.get("html_url"),
            "repositories_url": installation.get("repositories_url"),
            "target_type": installation.get("target_type"),
            "repository_selection": installation.get("repository_selection"),
            "single_file_name": installation.get("single_file_name"),
            "permissions": dict(installation.get("permissions") or {}),
            "events": list(installation.get("events") or []),
            "suspended_at": installation.get("suspended_at"),
            "setup_action": setup_action,
            "last_verified_at": datetime.now(UTC).isoformat(),
        }
        installation_metadata["health"] = self._github_connection_health(installation_metadata)
        verified_at = datetime.now(UTC)
        webhook_fp = None
        if settings.GITHUB_APP_WEBHOOK_SECRET:
            webhook_fp = hashlib.sha256(settings.GITHUB_APP_WEBHOOK_SECRET.encode("utf-8")).hexdigest()[:16]
        existing = await self.repo.get_github_connection_by_installation(user.id, installation_id)
        if existing:
            existing.name = f"{settings.GITHUB_APP_NAME} · {account_login}"
            existing.api_url = api_url
            existing.account_login = account_login
            existing.is_active = True
            existing.github_installation_id = installation_id
            existing.install_account_type = str(account.get("type") or "") or None
            existing.repository_selection = str(installation.get("repository_selection") or "") or None
            existing.install_permissions_json = dict(installation.get("permissions") or {})
            existing.install_events_json = list(installation.get("events") or [])
            existing.install_last_verified_at = verified_at
            existing.webhook_secret_fingerprint = webhook_fp
            existing.metadata_json = {**(existing.metadata_json or {}), **installation_metadata}
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        item = await self.repo.create_github_connection(
            owner_id=user.id,
            name=f"{settings.GITHUB_APP_NAME} · {account_login}",
            api_url=api_url,
            encrypted_token=encrypt_secret("github-app-installation"),
            token_hint="app",
            account_login=account_login,
            metadata_json=installation_metadata,
            github_installation_id=installation_id,
            install_account_type=str(account.get("type") or "") or None,
            repository_selection=str(installation.get("repository_selection") or "") or None,
            install_permissions_json=dict(installation.get("permissions") or {}),
            install_events_json=list(installation.get("events") or []),
            install_last_verified_at=verified_at,
            webhook_secret_fingerprint=webhook_fp,
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def create_github_connection(self, user: User, payload: dict[str, Any]):
        if payload.get("connection_mode") == "github_app":
            installation_id = payload.get("installation_id")
            if not installation_id:
                raise HTTPException(status_code=422, detail="installation_id is required for GitHub App connections")
            return await self.finalize_github_app_installation(
                user,
                installation_id=int(installation_id),
                setup_action=payload.get("setup_action"),
                api_url=payload.get("api_url", "https://api.github.com"),
            )
        token = payload.get("token")
        if not token:
            raise HTTPException(status_code=422, detail="token is required for legacy token connections")
        account_login = await self._fetch_github_login(payload["api_url"], payload["token"])
        item = await self.repo.create_github_connection(
            owner_id=user.id,
            name=payload["name"],
            api_url=payload.get("api_url", "https://api.github.com"),
            encrypted_token=encrypt_secret(payload["token"]),
            token_hint=mask_secret(payload["token"]),
            account_login=account_login,
            metadata_json={"connection_mode": "token"},
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_github_connections(self, user: User):
        return await self.repo.list_github_connections(user.id)

    async def delete_github_connection(self, user: User, connection_id: str) -> None:
        connection = await self.repo.get_github_connection(user.id, connection_id)
        if not connection:
            raise HTTPException(status_code=404, detail="GitHub connection not found")
        await self.repo.delete_github_connection(connection)
        await self.db.commit()

    async def sync_github_repositories(self, user: User, connection_id: str):
        connection = await self.repo.get_github_connection(user.id, connection_id)
        if not connection:
            raise HTTPException(status_code=404, detail="GitHub connection not found")
        repos = await self._list_github_repositories(connection)
        created = []
        existing = {item.full_name: item for item in await self.repo.list_github_repositories(user.id)}
        seen_full_names: set[str] = set()
        for repo in repos:
            seen_full_names.add(str(repo["full_name"]))
            row = existing.get(repo["full_name"])
            repository_metadata = {
                **repo,
                "last_verified_at": datetime.now(UTC).isoformat(),
            }
            repository_metadata["health"] = self._github_repository_health(
                connection,
                repository_metadata,
                is_active=True,
            )
            if row is not None:
                row.owner_name = repo["owner"]["login"]
                row.repo_name = repo["name"]
                row.default_branch = repo.get("default_branch")
                row.repo_url = repo.get("html_url")
                row.is_active = True
                row.last_synced_at = datetime.now(UTC)
                row.metadata_json = repository_metadata
                continue
            created.append(
                await self.repo.create_github_repository(
                    connection_id=connection.id,
                    owner_name=repo["owner"]["login"],
                    repo_name=repo["name"],
                    full_name=repo["full_name"],
                    default_branch=repo.get("default_branch"),
                    repo_url=repo.get("html_url"),
                    metadata_json=repository_metadata,
                    last_synced_at=datetime.now(UTC),
                )
            )
        for full_name, row in existing.items():
            if row.connection_id != connection.id or full_name in seen_full_names:
                continue
            row.is_active = False
            metadata = dict(row.metadata_json or {})
            metadata["last_verified_at"] = datetime.now(UTC).isoformat()
            metadata["health"] = self._github_repository_health(connection, metadata, is_active=False)
            row.metadata_json = metadata
        await self.db.commit()
        return created

    async def resync_github_connection_installation(self, connection_id: str) -> dict[str, Any]:
        """Recovery: refresh repository rows for a connection (post-install / operator tool)."""
        connection = await self.db.get(GithubConnection, connection_id)
        if connection is None:
            return {"ok": False, "detail": "connection_not_found"}
        user = await self.db.get(User, connection.owner_id)
        if user is None:
            return {"ok": False, "detail": "owner_not_found"}
        created = await self.sync_github_repositories(user, connection_id)
        return {"ok": True, "created_repo_rows": len(created or [])}

    async def list_github_repositories(self, user: User):
        return await self.repo.list_github_repositories(user.id)

    async def import_github_issues(self, user: User, payload: dict[str, Any]):
        project = await self.get_project(user, payload["project_id"])
        repository = await self.repo.get_github_repository(user.id, payload["repository_id"])
        if not repository:
            raise HTTPException(status_code=404, detail="GitHub repository not found")
        repository.project_id = project.id
        connection = await self.repo.get_github_connection(user.id, repository.connection_id)
        if not connection:
            raise HTTPException(status_code=404, detail="GitHub connection not found")
        project_manager = await self._project_default_manager(project.id, project=project)
        repo_pool = self._repo_pool_config(project, repository=repository)
        default_worker = str(
            payload.get("auto_assign_agent_id")
            or repo_pool.get("default_assignee_agent_id")
            or (project_manager.id if project_manager else "")
            or ""
        ).strip() or None
        default_reviewer = str(repo_pool.get("default_reviewer_agent_id") or "").strip() or None
        issues = await self._fetch_github_issues(connection, repository, payload.get("issue_numbers", []))
        results = []
        for issue in issues:
            issue_labels = [item["name"] for item in issue.get("labels", [])]
            link = await self.repo.get_issue_link_by_repo_and_number(repository.id, issue["number"])
            if link is None:
                link = await self.repo.create_issue_link(
                    repository_id=repository.id,
                    issue_number=issue["number"],
                    title=issue["title"],
                    body=issue.get("body"),
                    state=issue["state"],
                    labels_json=issue_labels,
                    assignee_login=(issue.get("assignee") or {}).get("login"),
                    issue_url=issue.get("html_url"),
                    last_synced_at=datetime.now(UTC),
                    metadata_json={
                        **issue,
                        "project_id": project.id,
                        "imported_at": datetime.now(UTC).isoformat(),
                    },
                )
            else:
                link.title = issue["title"]
                link.body = issue.get("body")
                link.state = issue["state"]
                link.labels_json = issue_labels
                link.assignee_login = (issue.get("assignee") or {}).get("login")
                link.issue_url = issue.get("html_url")
                link.last_synced_at = datetime.now(UTC)
                link.metadata_json = {
                    **(link.metadata_json or {}),
                    **issue,
                    "project_id": project.id,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "imported_at": (link.metadata_json or {}).get("imported_at") or datetime.now(UTC).isoformat(),
                }

            task = await self.db.get(OrchestratorTask, link.task_id) if link.task_id else None
            if task is None:
                task = await self.repo.create_task(
                    project_id=project.id,
                    created_by_user_id=user.id,
                    assigned_agent_id=default_worker,
                    reviewer_agent_id=default_reviewer,
                    title=issue["title"][:255],
                    description=issue.get("body"),
                    source="github",
                    task_type="github_issue",
                    priority="normal",
                    status="backlog",
                    acceptance_criteria=None,
                    due_date=None,
                    labels_json=issue_labels,
                    result_payload_json={},
                    metadata_json={
                        "github_issue_number": issue["number"],
                        "github_milestone_number": ((issue.get("milestone") or {}).get("number")),
                        "imported_from": "github",
                        "github_sync_provenance": {
                            "source": "github_issue_import",
                            "last_synced_at": datetime.now(UTC).isoformat(),
                            "field_sources": {
                                "title": "github",
                                "description": "github",
                                "labels": "github",
                            },
                        },
                    },
                    position=await self.repo.get_next_task_position(project.id),
                )
                link.task_id = task.id
                task.github_issue_link_id = link.id
            else:
                if task.project_id != project.id:
                    task.project_id = project.id
                    task.position = await self.repo.get_next_task_position(project.id)
                task.title = issue["title"][:255]
                task.description = issue.get("body")
                task.source = "github"
                task.task_type = "github_issue"
                task.labels_json = issue_labels
                task.github_issue_link_id = link.id
                task.metadata_json = {
                    **(task.metadata_json or {}),
                    "github_issue_number": issue["number"],
                    "github_milestone_number": ((issue.get("milestone") or {}).get("number")),
                    "imported_from": "github",
                    "github_sync_provenance": {
                        "source": "github_issue_import",
                        "last_synced_at": datetime.now(UTC).isoformat(),
                        "field_sources": {
                            "title": "github",
                            "description": "github",
                            "labels": "github",
                        },
                    },
                }
                if default_worker and not task.assigned_agent_id:
                    task.assigned_agent_id = default_worker
                if default_reviewer and not task.reviewer_agent_id:
                    task.reviewer_agent_id = default_reviewer
            link.metadata_json = {
                **(link.metadata_json or {}),
                "task_id": task.id,
                "assigned_agent_id": task.assigned_agent_id,
            }
            results.append(task)
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=link.id,
                action="import_issue",
                status="completed",
                detail=f"Issue #{issue['number']} imported.",
                payload_json={"issue_number": issue["number"]},
            )
        await self.db.commit()
        return results

    async def list_github_issue_links(self, user: User, project_id: str | None = None):
        return await self.repo.list_issue_links(user.id, project_id)

    async def list_github_sync_events(self, user: User, project_id: str | None = None):
        return await self.repo.list_sync_events(user.id, project_id)

    async def refresh_github_issue_link_from_api(self, link: GithubIssueLink) -> None:
        repository = await self.db.get(GithubRepository, link.repository_id)
        if repository is None:
            return
        connection = await self.db.get(GithubConnection, repository.connection_id)
        if connection is None or not connection.is_active:
            return
        response = await self._github_request(
            connection,
            "GET",
            f"/repos/{repository.full_name}/issues/{link.issue_number}",
        )
        if response.status_code >= 400:
            link.last_error = response.text[:500]
            link.last_synced_at = datetime.now(UTC)
            return
        issue = response.json()
        link.title = (issue.get("title") or link.title)[:255]
        link.state = str(issue.get("state") or link.state)
        link.body = issue.get("body") or link.body
        link.labels_json = [item["name"] for item in issue.get("labels", []) if isinstance(item, dict)]
        assignee = issue.get("assignee") or {}
        link.assignee_login = assignee.get("login") if isinstance(assignee, dict) else None
        link.issue_url = issue.get("html_url") or link.issue_url
        link.metadata_json = {**(link.metadata_json or {}), "last_poll": issue}
        link.last_synced_at = datetime.now(UTC)
        link.last_error = None

    async def refresh_github_issue_link(self, user: User, issue_link_id: str) -> GithubIssueLink:
        link = await self.repo.get_issue_link(user.id, issue_link_id)
        if link is None:
            raise HTTPException(status_code=404, detail="GitHub issue link not found")
        await self.refresh_github_issue_link_from_api(link)
        task = await self.db.get(OrchestratorTask, link.task_id) if link.task_id else None
        if task is not None:
            task.title = link.title
            task.description = link.body
            task.labels_json = list(link.labels_json or [])
            task.metadata_json = {
                **(task.metadata_json or {}),
                "github_issue_state": link.state,
                "github_issue_url": link.issue_url,
                "github_issue_updated_at": datetime.now(UTC).isoformat(),
            }
        await self.repo.create_sync_event(
            repository_id=link.repository_id,
            issue_link_id=link.id,
            action="issues.manual_refresh",
            status="completed" if not link.last_error else "failed",
            detail=f"Issue #{link.issue_number} refreshed from GitHub.",
            payload_json={"issue_number": link.issue_number, "task_id": link.task_id},
        )
        await self.db.commit()
        await self.db.refresh(link)
        return link

    async def poll_stale_github_issue_links(self) -> int:
        """Background poll for issue state when webhooks are unavailable."""
        before = datetime.now(UTC) - timedelta(minutes=max(1, settings.GITHUB_ISSUE_POLL_INTERVAL_MINUTES))
        links = await self.repo.list_issue_links_stale(older_than=before, limit=50)
        updated = 0
        for link in links:
            try:
                await self.refresh_github_issue_link_from_api(link)
                updated += 1
            except Exception:
                link.last_error = "poll_failed"
                link.last_synced_at = datetime.now(UTC)
        if links:
            await self.db.commit()
        return updated

    async def create_github_comment_approval(
        self,
        user: User,
        issue_link_id: str,
        body: str,
        close_issue: bool,
        *,
        idempotency_key: str | None = None,
        artifact_ids: list[str] | None = None,
    ):
        issue_link = await self.repo.get_issue_link(user.id, issue_link_id)
        if not issue_link:
            raise HTTPException(status_code=404, detail="Issue link not found")
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        task = await self.db.get(OrchestratorTask, issue_link.task_id) if issue_link.task_id else None
        project = await self.db.get(OrchestratorProject, task.project_id) if task else None
        policy, trusted_ids = self._effective_github_outbound_comment_policy(project, repository)
        if policy == "disabled":
            raise HTTPException(status_code=403, detail="Outbound GitHub comments are disabled for this project.")
        if policy == "approved_artifacts_only" and not (artifact_ids or []):
            raise HTTPException(
                status_code=422,
                detail="Outbound policy requires artifact_ids for GitHub comments on this project.",
            )
        artifact_ids = [str(x).strip() for x in (artifact_ids or []) if str(x).strip()]
        if artifact_ids:
            if not issue_link.task_id:
                raise HTTPException(status_code=422, detail="Artifacts require a linked task.")
            for aid in artifact_ids:
                art = await self.db.get(TaskArtifact, aid)
                if art is None or art.task_id != issue_link.task_id:
                    raise HTTPException(status_code=404, detail=f"Artifact {aid} not found for this task.")
                body = (body + f"\n\n### {art.title}\n{art.content or ''}").strip()
        dedup_key = (idempotency_key or "").strip() or (
            f"github-comment:{issue_link.id}:{hashlib.sha256(f'{body}|{close_issue}'.encode()).hexdigest()[:48]}"
        )
        existing_row = await self.repo.get_github_outbound_dedup_row(user.id, dedup_key)
        if existing_row is not None:
            prev = await self.db.get(ApprovalRequest, existing_row.approval_id)
            if prev is not None:
                return prev
        payload_json: dict[str, Any] = {
            "body": body,
            "close_issue": close_issue,
            "draft_created_at": datetime.now(UTC).isoformat(),
            "draft_status": "pending_approval",
            "idempotency_key": dedup_key,
            "artifact_ids": artifact_ids,
        }
        approval: ApprovalRequest | None = None
        try:
            async with self.db.begin_nested():
                approval = await self.repo.create_approval(
                    project_id=task.project_id if task else None,
                    task_id=task.id if task else None,
                    issue_link_id=issue_link.id,
                    requested_by_user_id=user.id,
                    approval_type="github_comment",
                    status="pending",
                    payload_json=payload_json,
                )
                await self.db.flush()
                await self.repo.create_github_outbound_dedup_row(
                    owner_id=user.id,
                    dedup_key=dedup_key,
                    approval_id=approval.id,
                    issue_link_id=issue_link.id,
                )
        except IntegrityError:
            row = await self.repo.get_github_outbound_dedup_row(user.id, dedup_key)
            if row is None:
                raise
            approval = await self.db.get(ApprovalRequest, row.approval_id)
            if approval is None:
                raise
            await self.db.commit()
            await self.db.refresh(approval)
            return approval
        if approval is None:
            raise RuntimeError("GitHub comment approval was not created")
        if policy == "auto_trusted_agent" and user.id in trusted_ids:
            approval.status = "approved"
            approval.approved_by_user_id = user.id
            approval.resolved_at = datetime.now(UTC)
            await self._post_approved_github_comment(approval)
        await self.db.commit()
        await self.db.refresh(approval)
        return approval

    def _project_github_settings(self, project: OrchestratorProject | None) -> dict[str, Any]:
        if project is None:
            return self._normalize_project_settings({}).get("github", {})
        return self._normalize_project_settings(project.settings_json).get("github", {})

    def _effective_github_outbound_comment_policy(
        self, project: OrchestratorProject | None, repository: GithubRepository | None
    ) -> tuple[str, list[str]]:
        gh = self._project_github_settings(project)
        policy = str(gh.get("outbound_comment_policy") or "manual_approval")
        trusted = [str(x).strip() for x in (gh.get("outbound_comment_trusted_user_ids") or []) if str(x).strip()]
        if repository is not None and repository.full_name:
            pool = (gh.get("repo_agent_pools") or {}).get(repository.full_name)
            if isinstance(pool, dict):
                if pool.get("outbound_comment_policy"):
                    policy = str(pool["outbound_comment_policy"])
                if pool.get("outbound_comment_trusted_user_ids"):
                    trusted = [str(x).strip() for x in pool["outbound_comment_trusted_user_ids"] if str(x).strip()]
        return policy, trusted

    def _github_field_write_source(
        self, project: OrchestratorProject | None, task_meta: dict[str, Any], field: str
    ) -> str:
        locked = dict(self._project_github_settings(project).get("github_field_locks") or {})
        if field in locked and str(locked[field]).lower() in {"app", "internal"}:
            return "app"
        prov = (task_meta or {}).get("github_sync_provenance") or {}
        sources = dict(prov.get("field_sources") or {})
        return str(sources.get(field, "github")).lower()

    async def _validate_github_secondary_repository_ids(
        self, user: User, project_id: str, repo_ids: list[str]
    ) -> None:
        for rid in repo_ids:
            row = await self.repo.get_github_repository(user.id, rid)
            if row is None:
                raise HTTPException(status_code=404, detail=f"GitHub repository {rid} not found")
            if row.project_id != project_id:
                raise HTTPException(
                    status_code=422,
                    detail=f"Repository {rid} must be linked to this project before use as secondary.",
                )

    def _github_connection_health(self, metadata: dict[str, Any]) -> dict[str, Any]:
        permissions = dict(metadata.get("permissions") or {})
        missing_permissions = [
            permission
            for permission in ("issues", "pull_requests", "contents", "metadata")
            if permissions.get(permission) not in {"read", "write"}
        ]
        repositories_selected = str(metadata.get("repository_selection") or "unknown")
        installation_id = int(metadata.get("installation_id") or 0)
        status = "healthy"
        if installation_id <= 0 or missing_permissions:
            status = "degraded"
        return {
            "status": status,
            "missing_permissions": missing_permissions,
            "repositories_selected": repositories_selected,
            "last_verified_at": metadata.get("last_verified_at"),
            "suspended_at": metadata.get("suspended_at"),
        }

    def _github_repository_health(
        self,
        connection: GithubConnection | None,
        repository_payload: dict[str, Any],
        *,
        is_active: bool,
    ) -> dict[str, Any]:
        default_branch = str(repository_payload.get("default_branch") or "").strip()
        archived = bool(repository_payload.get("archived"))
        disabled = bool(repository_payload.get("disabled"))
        deleted = bool(repository_payload.get("deleted"))
        installation_health = self._github_connection_health(dict((connection.metadata_json or {}) if connection else {}))
        status = "healthy"
        if not is_active or archived or disabled or deleted or installation_health["status"] != "healthy":
            status = "degraded"
        return {
            "status": status,
            "default_branch_present": bool(default_branch),
            "archived": archived,
            "disabled": disabled,
            "deleted": deleted,
            "installation_status": installation_health["status"],
        }

    def _repo_pool_config(
        self,
        project: OrchestratorProject | None,
        *,
        repository: GithubRepository | None = None,
        repository_id: str | None = None,
        repository_full_name: str | None = None,
    ) -> dict[str, Any]:
        github = self._project_github_settings(project)
        pools = dict(github.get("repo_agent_pools") or {})
        keys = [repository_id, repository_full_name]
        if repository is not None:
            keys = [repository.id, repository.full_name, *keys]
        for key in keys:
            text = str(key or "").strip()
            if text and isinstance(pools.get(text), dict):
                return dict(pools[text])
        return {}

    async def _task_github_repository(self, task: OrchestratorTask | None) -> GithubRepository | None:
        if task is None or not task.github_issue_link_id:
            return None
        issue_link = await self.db.get(GithubIssueLink, task.github_issue_link_id)
        if issue_link is None:
            return None
        return await self.db.get(GithubRepository, issue_link.repository_id)

    async def _task_repo_pool_config(self, task: OrchestratorTask | None) -> dict[str, Any]:
        if task is None:
            return {}
        project = await self.db.get(OrchestratorProject, task.project_id)
        repository = await self._task_github_repository(task)
        return self._repo_pool_config(project, repository=repository)

    async def _fetch_github_login(self, api_url: str, token: str) -> str:
        async with httpx.AsyncClient(timeout=30.0, base_url=api_url) as client:
            response = await client.get("/user", headers={"Authorization": f"Bearer {token}"})
        if response.status_code >= 400:
            raise HTTPException(status_code=422, detail="Failed to validate GitHub token")
        return response.json()["login"]

    def _github_connection_mode(self, connection: GithubConnection) -> str:
        return str((connection.metadata_json or {}).get("connection_mode") or "token")

    def _github_app_jwt(self) -> str:
        if not settings.GITHUB_APP_ID or not settings.GITHUB_APP_PRIVATE_KEY:
            raise HTTPException(status_code=503, detail="GitHub App credentials are not configured")
        now = int(time.time())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": settings.GITHUB_APP_ID},
            settings.GITHUB_APP_PRIVATE_KEY,
            algorithm="RS256",
        )

    async def _github_app_get_installation(
        self, installation_id: int, *, api_url: str = "https://api.github.com"
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0, base_url=api_url) as client:
            response = await client.get(
                f"/app/installations/{installation_id}",
                headers={
                    "Authorization": f"Bearer {self._github_app_jwt()}",
                    "Accept": "application/vnd.github+json",
                },
            )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to read GitHub App installation")
        return response.json()

    async def _github_installation_token(self, connection: GithubConnection) -> str:
        installation_id = int((connection.metadata_json or {}).get("installation_id") or 0)
        if installation_id <= 0:
            raise HTTPException(status_code=422, detail="GitHub App connection is missing installation_id")
        async with httpx.AsyncClient(timeout=30.0, base_url=connection.api_url) as client:
            response = await client.post(
                f"/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {self._github_app_jwt()}",
                    "Accept": "application/vnd.github+json",
                },
            )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to mint GitHub installation token")
        return str(response.json()["token"])

    async def _github_auth_headers(self, connection: GithubConnection) -> dict[str, str]:
        token = (
            await self._github_installation_token(connection)
            if self._github_connection_mode(connection) == "github_app"
            else decrypt_secret(connection.encrypted_token)
        )
        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _github_request(
        self,
        connection: GithubConnection,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers = await self._github_auth_headers(connection)
        async with httpx.AsyncClient(timeout=30.0, base_url=connection.api_url) as client:
            return await client.request(method, path, headers=headers, params=params, json=json_body)

    async def _list_github_repositories(self, connection: GithubConnection) -> list[dict[str, Any]]:
        if self._github_connection_mode(connection) == "github_app":
            response = await self._github_request(
                connection,
                "GET",
                "/installation/repositories",
                params={"per_page": 100},
            )
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail="Failed to fetch GitHub repositories")
            return list((response.json() or {}).get("repositories", []))
        response = await self._github_request(
            connection,
            "GET",
            "/user/repos",
            params={"per_page": 100, "sort": "updated"},
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to fetch GitHub repositories")
        return response.json()

    async def _fetch_github_issues(
        self,
        connection: GithubConnection,
        repository,
        issue_numbers: list[int],
    ) -> list[dict[str, Any]]:
        if issue_numbers:
            issues = []
            for issue_number in issue_numbers:
                response = await self._github_request(
                    connection,
                    "GET",
                    f"/repos/{repository.full_name}/issues/{issue_number}",
                )
                if response.status_code >= 400:
                    if response.status_code in {401, 403}:
                        detail = response.text[:300] or "GitHub denied access to this issue."
                        raise HTTPException(
                            status_code=422,
                            detail=(
                                f"GitHub access failed for issue #{issue_number}. "
                                f"Reconnect GitHub or verify the app/token can read {repository.full_name}. "
                                f"GitHub said: {detail}"
                            ),
                        )
                    raise HTTPException(status_code=502, detail=f"Failed to fetch issue #{issue_number}")
                issues.append(response.json())
            return issues
        response = await self._github_request(
            connection,
            "GET",
            f"/repos/{repository.full_name}/issues",
            params={"state": "open", "per_page": 100},
        )
        if response.status_code >= 400:
            if response.status_code in {401, 403}:
                detail = response.text[:300] or "GitHub denied access to this repository."
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"GitHub access failed for {repository.full_name}. "
                        f"Reconnect GitHub or verify the app/token can read this repository. "
                        f"GitHub said: {detail}"
                    ),
                )
            raise HTTPException(status_code=502, detail="Failed to fetch GitHub issues")
        return [item for item in response.json() if "pull_request" not in item]

    async def _post_approved_github_comment(self, approval: ApprovalRequest) -> None:
        issue_link = await self.db.get(GithubIssueLink, approval.issue_link_id)
        if issue_link is None:
            raise HTTPException(status_code=404, detail="Issue link not found")
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        if repository is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        connection = await self.db.get(GithubConnection, repository.connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        payload = approval.payload_json
        comment_body = payload.get("body") or payload.get("draft_comment")
        if not comment_body:
            raise HTTPException(status_code=422, detail="Approval payload does not include a comment body")
        if payload.get("posted_comment_id"):
            return
        response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/issues/{issue_link.issue_number}/comments",
            json_body={"body": comment_body},
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to post GitHub comment")
        comment_payload = response.json() if callable(getattr(response, "json", None)) else {}
        approval.payload_json = {
            **payload,
            "draft_status": "posted",
            "posted_comment_id": comment_payload.get("id"),
            "posted_comment_url": comment_payload.get("html_url"),
            "posted_at": datetime.now(UTC).isoformat(),
        }
        orm_attributes.flag_modified(approval, "payload_json")
        if payload.get("close_issue"):
            close_response = await self._github_request(
                connection,
                "PATCH",
                f"/repos/{repository.full_name}/issues/{issue_link.issue_number}",
                json_body={"state": "closed"},
            )
            if close_response.status_code >= 400:
                raise HTTPException(status_code=502, detail="Failed to close GitHub issue")
        issue_link.last_comment_posted_at = datetime.now(UTC)
        issue_link.last_synced_at = datetime.now(UTC)
        if payload.get("close_issue"):
            issue_link.state = "closed"
        if approval.task_id:
            task = await self.db.get(OrchestratorTask, approval.task_id)
            if task and task.status == "approved":
                await self._transition_task_status(task, "completed", reason="approved for external sync")
            if task and task.status == "completed":
                await self._transition_task_status(task, "synced_to_github", reason="github comment posted")
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="post_comment",
            status="completed",
            detail="Approved comment posted to GitHub.",
            payload_json={
                **payload,
                "body": comment_body,
                "posted_comment_id": comment_payload.get("id"),
                "posted_comment_url": comment_payload.get("html_url"),
            },
        )

    async def _approve_github_create_pr(self, approval: ApprovalRequest) -> None:
        payload = approval.payload_json or {}
        run_id = payload.get("run_id")
        task_id = approval.task_id or payload.get("task_id")
        issue_link = await self.db.get(GithubIssueLink, approval.issue_link_id) if approval.issue_link_id else None
        if not run_id or not task_id or issue_link is None:
            raise HTTPException(status_code=422, detail="PR approval payload is incomplete")
        run = await self.db.get(TaskRun, str(run_id))
        task = await self.db.get(OrchestratorTask, str(task_id))
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        if run is None or task is None or repository is None:
            raise HTTPException(status_code=404, detail="PR approval target could not be resolved")
        await self._create_github_pr_for_run(run, task, repository, issue_link, approval=approval)

    async def _approve_github_pr_review_comment(self, approval: ApprovalRequest) -> None:
        payload = approval.payload_json or {}
        issue_link = await self.db.get(GithubIssueLink, approval.issue_link_id) if approval.issue_link_id else None
        if issue_link is None:
            raise HTTPException(status_code=404, detail="Issue link not found")
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        connection = await self.db.get(GithubConnection, repository.connection_id) if repository else None
        pr_number = payload.get("pr_number")
        body = str(payload.get("body") or "").strip()
        if connection is None or repository is None or not pr_number or not body:
            raise HTTPException(status_code=422, detail="PR review approval payload is incomplete")
        response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/pulls/{pr_number}/reviews",
            json_body={"body": body[:5000], "event": "COMMENT"},
        )
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="post_pr_review",
            status="completed" if response.status_code < 400 else "failed",
            detail=f"Approved reviewer PR comment posted on #{pr_number}."
            if response.status_code < 400
            else "Failed to post approved reviewer PR comment.",
            payload_json=payload,
        )

    async def _approve_github_issue_sync(self, approval: ApprovalRequest) -> None:
        issue_link = await self.db.get(GithubIssueLink, approval.issue_link_id) if approval.issue_link_id else None
        if issue_link is None:
            raise HTTPException(status_code=404, detail="Issue link not found")
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        connection = await self.db.get(GithubConnection, repository.connection_id) if repository else None
        payload = dict(approval.payload_json or {})
        body = dict(payload.get("issue_update") or {})
        if repository is None or connection is None or not body:
            raise HTTPException(status_code=422, detail="GitHub issue sync approval payload is incomplete")
        response = await self._github_request(
            connection,
            "PATCH",
            f"/repos/{repository.full_name}/issues/{issue_link.issue_number}",
            json_body=body,
        )
        if response.status_code < 400:
            issue_link.last_synced_at = datetime.now(UTC)
            if "state" in body:
                issue_link.state = str(body["state"])
            if "labels" in body and isinstance(body["labels"], list):
                issue_link.labels_json = [str(item) for item in body["labels"]]
            if "assignees" in body:
                assignees = body.get("assignees") or []
                issue_link.assignee_login = str(assignees[0]) if assignees else None
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="sync_issue_fields",
            status="completed" if response.status_code < 400 else "failed",
            detail="Approved internal task changes synced back to GitHub."
            if response.status_code < 400
            else "Failed to sync internal task changes back to GitHub.",
            payload_json=payload,
        )

    def validate_github_webhook_signature(self, body: bytes, signature: str | None) -> bool:
        if not settings.GITHUB_APP_WEBHOOK_SECRET:
            return False
        if not signature or not signature.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(
            settings.GITHUB_APP_WEBHOOK_SECRET.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def record_github_webhook_event(
        self,
        event_name: str,
        payload: dict[str, Any],
        *,
        delivery_id: str | None = None,
        signature_validated: bool = True,
    ) -> str:
        if event_name not in GITHUB_WEBHOOK_EVENT_ALLOWLIST:
            sync_event = await self.repo.create_sync_event(
                repository_id=None,
                issue_link_id=None,
                action=f"webhook.{event_name}.ignored",
                status="ignored",
                detail=f"Webhook event {event_name} is not enabled.",
                payload_json={
                    "_webhook_meta": {
                        "delivery_id": delivery_id,
                        "signature_validated": signature_validated,
                        "received_at": datetime.now(UTC).isoformat(),
                        "ignored_reason": "event_not_allowlisted",
                    }
                },
            )
            await self.db.commit()
            return sync_event.id
        if delivery_id:
            existing = await self.repo.get_sync_event_by_delivery_id(delivery_id)
            if existing is not None:
                meta = dict((existing.payload_json or {}).get("_webhook_meta") or {})
                meta["duplicate_delivery_detected_at"] = datetime.now(UTC).isoformat()
                existing.payload_json = {**(existing.payload_json or {}), "_webhook_meta": meta}
                existing.detail = f"Duplicate delivery ignored for {existing.action}."
                if existing.status == "queued":
                    existing.status = "pending"
                await self.db.commit()
                return existing.id
        repository = payload.get("repository") or {}
        repo_model = None
        if repository.get("full_name"):
            repo_model = await self.repo.get_github_repository_by_full_name(repository["full_name"])
        issue_link = None
        issue_number = int(((payload.get("issue") or {}).get("number")) or ((payload.get("pull_request") or {}).get("number")) or 0)
        if repo_model and issue_number:
            issue_link = await self.repo.get_issue_link_by_repo_and_number(repo_model.id, issue_number)
        payload_excerpt = {
            "issue_number": issue_number or None,
            "installation_id": int(((payload.get("installation") or {}).get("id")) or 0) or None,
            "repository_full_name": repository.get("full_name"),
            "sender_login": ((payload.get("sender") or {}).get("login")),
        }
        payload = dict(payload)
        payload["_webhook_meta"] = {
            **dict(payload.get("_webhook_meta") or {}),
            "delivery_id": delivery_id,
            "signature_validated": signature_validated,
            "received_at": datetime.now(UTC).isoformat(),
            "replay_history": list((payload.get("_webhook_meta") or {}).get("replay_history") or []),
            "event_name": event_name,
            "action": payload.get("action"),
            "payload_excerpt": payload_excerpt,
        }
        sync_event = await self.repo.create_sync_event(
            repository_id=repo_model.id if repo_model else None,
            issue_link_id=issue_link.id if issue_link else None,
            action=f"webhook.{event_name}.{payload.get('action')}",
            status="queued",
            detail=f"Queued GitHub webhook {event_name}.{payload.get('action')}",
            payload_json=payload,
        )
        await self.db.commit()
        return sync_event.id

    async def replay_github_sync_event(
        self, user: User, sync_event_id: str, *, force: bool = False
    ):
        sync_event = await self.repo.get_sync_event(sync_event_id)
        if sync_event is None:
            raise HTTPException(status_code=404, detail="GitHub sync event not found")
        if sync_event.repository_id:
            repository = await self.repo.get_github_repository(user.id, sync_event.repository_id)
            if repository is None:
                raise HTTPException(status_code=404, detail="GitHub sync event not found")
        if sync_event.status == "running":
            raise HTTPException(status_code=409, detail="Sync event is already running")
        if sync_event.status == "completed" and not force:
            raise HTTPException(
                status_code=409,
                detail="Completed sync events require force replay",
            )
        payload = dict(sync_event.payload_json or {})
        meta = dict(payload.get("_webhook_meta") or {})
        history = list(meta.get("replay_history") or [])
        history.append(
            {
                "queued_at": datetime.now(UTC).isoformat(),
                "queued_by_user_id": user.id,
                "previous_status": sync_event.status,
                "forced": force,
            }
        )
        meta["replay_history"] = history
        meta["replay_count"] = len(history)
        payload["_webhook_meta"] = meta
        sync_event.payload_json = payload
        sync_event.status = "queued"
        sync_event.detail = (
            f"Replay queued from {history[-1]['previous_status']}."
            + (" Forced replay enabled." if force else "")
        )
        await self.db.commit()
        try:
            from backend.workers.orchestration import queue_github_webhook_event

            queue_github_webhook_event(sync_event.id)
        except Exception as exc:
            logger.warning("queue github webhook replay failed: %s", exc)
        return sync_event

    async def process_github_webhook_sync_event(self, sync_event_id: str) -> None:
        sync_event = await self.repo.get_sync_event(sync_event_id)
        if sync_event is None:
            raise RuntimeError("GitHub sync event not found")
        payload = sync_event.payload_json or {}
        sync_event.status = "running"
        try:
            if sync_event.action.startswith("webhook.installation."):
                await self._process_webhook_installation(sync_event, payload)
            elif sync_event.action.startswith("webhook.installation_repositories."):
                await self._process_webhook_installation_repositories(sync_event, payload)
            elif sync_event.action == "webhook.issues.opened":
                await self._process_webhook_issue_opened(sync_event, payload)
            elif sync_event.action == "webhook.issues.assigned":
                await self._process_webhook_issue_assigned(sync_event, payload)
            elif sync_event.action.startswith("webhook.issues."):
                await self._process_webhook_issue_changed(sync_event, payload)
            elif sync_event.action == "webhook.issue_comment.created":
                await self._process_webhook_issue_comment(sync_event, payload)
            elif sync_event.action.startswith("webhook.pull_request."):
                suffix = sync_event.action.removeprefix("webhook.pull_request.")
                pr = payload.get("pull_request") or {}
                if suffix == "opened":
                    await self._process_webhook_pull_request_opened(sync_event, payload)
                elif suffix == "closed":
                    if pr.get("merged"):
                        await self._process_webhook_pull_request_merged(sync_event, payload)
                    else:
                        await self._process_webhook_pull_request_lifecycle(
                            sync_event, payload, forced_state="closed"
                        )
                else:
                    await self._process_webhook_pull_request_lifecycle(sync_event, payload)
            elif sync_event.action == "webhook.pull_request_review_comment.created":
                await self._process_webhook_pull_request_review_comment(sync_event, payload)
            elif sync_event.action == "webhook.pull_request_review.submitted":
                await self._process_webhook_pull_request_review(sync_event, payload)
            elif sync_event.action.startswith("webhook.push."):
                await self._process_webhook_push(sync_event, payload)
            elif sync_event.action.startswith("webhook.projects_v2_item."):
                await self._process_webhook_projects_v2_item(sync_event, payload)
            else:
                sync_event.status = "ignored"
                sync_event.detail = f"No handler for {sync_event.action}"
        except Exception as exc:
            sync_event.status = "failed"
            sync_event.detail = f"{type(exc).__name__}: {exc}"[:8000]
            logger.exception("github webhook sync_event=%s failed", sync_event_id)
        await self.db.commit()

    async def _process_webhook_projects_v2_item(self, sync_event, payload: dict[str, Any]) -> None:
        sync_event.status = "ignored"
        sync_event.detail = (
            "GitHub Projects (classic/v2) board sync is not implemented yet; event was recorded for auditing."
        )
        sync_event.payload_json = {
            "projects_v2_stub": True,
            "action": payload.get("action"),
            "projects_v2_node_id": (payload.get("projects_v2_item") or {}).get("node_id"),
        }

    async def _owner_id_for_repository(self, repository: GithubRepository) -> str:
        connection = await self.db.get(GithubConnection, repository.connection_id)
        if connection is None:
            raise RuntimeError("GitHub repository connection is missing")
        return connection.owner_id

    async def _ensure_repository_from_webhook_payload(self, payload: dict[str, Any]) -> GithubRepository | None:
        repository = payload.get("repository") or {}
        full_name = repository.get("full_name")
        if not full_name:
            return None
        repo_model = await self.repo.get_github_repository_by_full_name(full_name)
        if repo_model:
            connection = await self.db.get(GithubConnection, repo_model.connection_id)
            repo_model.metadata_json = {
                **repository,
                "last_verified_at": datetime.now(UTC).isoformat(),
                "health": self._github_repository_health(connection, repository, is_active=bool(repo_model.is_active)),
            }
            return repo_model
        installation_id = int(((payload.get("installation") or {}).get("id")) or 0)
        if installation_id <= 0:
            return None
        result = await self.db.execute(
            select(GithubConnection).where(
                GithubConnection.metadata_json["installation_id"].as_integer() == installation_id
            )
        )
        connection = result.scalar_one_or_none()
        if connection is None:
            return None
        return await self.repo.create_github_repository(
            connection_id=connection.id,
            project_id=None,
            owner_name=(repository.get("owner") or {}).get("login") or "",
            repo_name=repository.get("name") or "",
            full_name=full_name,
            default_branch=repository.get("default_branch"),
            repo_url=repository.get("html_url"),
            metadata_json={
                **repository,
                "last_verified_at": datetime.now(UTC).isoformat(),
                "health": self._github_repository_health(connection, repository, is_active=True),
            },
        )

    async def _process_webhook_installation(self, sync_event, payload: dict[str, Any]) -> None:
        installation = payload.get("installation") or {}
        installation_id = int(installation.get("id") or 0)
        if installation_id <= 0:
            sync_event.status = "ignored"
            sync_event.detail = "Installation webhook missing installation id."
            return
        result = await self.db.execute(
            select(GithubConnection).where(
                or_(
                    GithubConnection.github_installation_id == installation_id,
                    GithubConnection.metadata_json["installation_id"].as_integer() == installation_id,
                )
            )
        )
        connection = result.scalar_one_or_none()
        if connection is None:
            sync_event.status = "ignored"
            sync_event.detail = f"No Troop connection for installation {installation_id}."
            return
        metadata = dict(connection.metadata_json or {})
        metadata.update(
            {
                "installation_id": installation_id,
                "repository_selection": installation.get("repository_selection"),
                "permissions": dict(installation.get("permissions") or metadata.get("permissions") or {}),
                "events": list(installation.get("events") or metadata.get("events") or []),
                "suspended_at": installation.get("suspended_at"),
                "last_verified_at": datetime.now(UTC).isoformat(),
                "last_webhook_action": payload.get("action"),
            }
        )
        metadata["health"] = self._github_connection_health(metadata)
        if payload.get("action") == "deleted":
            connection.is_active = False
        elif payload.get("action") in {"created", "new_permissions_accepted", "unsuspend"}:
            connection.is_active = True
        connection.github_installation_id = installation_id
        connection.install_permissions_json = dict(installation.get("permissions") or {})
        connection.install_events_json = list(installation.get("events") or [])
        connection.install_last_verified_at = datetime.now(UTC)
        connection.repository_selection = str(installation.get("repository_selection") or "") or None
        acct = installation.get("account") if isinstance(installation.get("account"), dict) else {}
        connection.install_account_type = str(acct.get("type") or "") or None
        connection.metadata_json = metadata
        sync_event.status = "completed"
        sync_event.detail = f"Installation {installation_id} state updated from webhook."

    async def _process_webhook_installation_repositories(self, sync_event, payload: dict[str, Any]) -> None:
        installation_id = int(((payload.get("installation") or {}).get("id")) or 0)
        if installation_id <= 0:
            sync_event.status = "ignored"
            sync_event.detail = "Installation repositories webhook missing installation id."
            return
        result = await self.db.execute(
            select(GithubConnection).where(
                or_(
                    GithubConnection.github_installation_id == installation_id,
                    GithubConnection.metadata_json["installation_id"].as_integer() == installation_id,
                )
            )
        )
        connection = result.scalar_one_or_none()
        if connection is None:
            sync_event.status = "ignored"
            sync_event.detail = f"No Troop connection for installation {installation_id}."
            return
        added = list(payload.get("repositories_added") or [])
        removed = list(payload.get("repositories_removed") or [])
        for repo in added:
            repository = await self.repo.get_github_repository_by_full_name(str(repo.get("full_name") or ""))
            if repository is None:
                await self.repo.create_github_repository(
                    connection_id=connection.id,
                    project_id=None,
                    owner_name=((repo.get("owner") or {}).get("login") or ""),
                    repo_name=str(repo.get("name") or ""),
                    full_name=str(repo.get("full_name") or ""),
                    default_branch=repo.get("default_branch"),
                    repo_url=repo.get("html_url"),
                    is_active=True,
                    metadata_json={
                        **repo,
                        "last_verified_at": datetime.now(UTC).isoformat(),
                        "health": self._github_repository_health(connection, repo, is_active=True),
                    },
                    last_synced_at=datetime.now(UTC),
                )
            else:
                repository.is_active = True
                repository.metadata_json = {
                    **(repository.metadata_json or {}),
                    **repo,
                    "last_verified_at": datetime.now(UTC).isoformat(),
                    "health": self._github_repository_health(connection, repo, is_active=True),
                }
        for repo in removed:
            repository = await self.repo.get_github_repository_by_full_name(str(repo.get("full_name") or ""))
            if repository is None:
                continue
            repository.is_active = False
            repository.metadata_json = {
                **(repository.metadata_json or {}),
                **repo,
                "removed_from_installation_at": datetime.now(UTC).isoformat(),
                "health": self._github_repository_health(connection, repo, is_active=False),
            }
        sync_event.status = "completed"
        sync_event.detail = (
            f"Installation repository membership updated: +{len(added)} / -{len(removed)}."
        )

    async def _process_webhook_issue_opened(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        issue = payload.get("issue") or {}
        if repository is None or repository.project_id is None:
            sync_event.status = "ignored"
            sync_event.detail = "Repository is not linked to an orchestration project."
            return
        owner_id = await self._owner_id_for_repository(repository)
        project = await self.db.get(OrchestratorProject, repository.project_id)
        repo_pool = self._repo_pool_config(project, repository=repository)
        link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(issue["number"]))
        if link is None:
            link = await self.repo.create_issue_link(
                repository_id=repository.id,
                issue_number=int(issue["number"]),
                title=issue.get("title") or "",
                body=issue.get("body"),
                state=issue.get("state") or "open",
                labels_json=[item["name"] for item in issue.get("labels", [])],
                assignee_login=((issue.get("assignee") or {}).get("login")),
                issue_url=issue.get("html_url"),
                sync_status="synced",
                last_synced_at=datetime.now(UTC),
                metadata_json=issue,
            )
        task: OrchestratorTask | None = None
        if link.task_id is None:
            task = await self.repo.create_task(
                project_id=repository.project_id,
                created_by_user_id=owner_id,
                assigned_agent_id=str(repo_pool.get("default_assignee_agent_id") or "").strip() or None,
                reviewer_agent_id=str(repo_pool.get("default_reviewer_agent_id") or "").strip() or None,
                title=(issue.get("title") or "GitHub issue")[:255],
                description=issue.get("body"),
                source="github",
                task_type="github_issue",
                priority="normal",
                status="backlog",
                acceptance_criteria=None,
                due_date=None,
                labels_json=[item["name"] for item in issue.get("labels", [])],
                result_payload_json={},
                metadata_json={
                    "github_issue_number": issue.get("number"),
                    "github_milestone_number": ((issue.get("milestone") or {}).get("number")),
                    "github_sync_provenance": {
                        "source": "github_webhook_issue_opened",
                        "last_synced_at": datetime.now(UTC).isoformat(),
                        "field_sources": {
                            "title": "github",
                            "description": "github",
                            "labels": "github",
                            "status": "github",
                        },
                    },
                },
                position=await self.repo.get_next_task_position(repository.project_id),
            )
            task.github_issue_link_id = link.id
            link.task_id = task.id
        else:
            task = await self.db.get(OrchestratorTask, link.task_id)
        if task is not None:
            try:
                async with self.db.begin_nested():
                    await self.repo.create_github_entity_mapping(
                        owner_id=owner_id,
                        external_kind="github_issue",
                        external_ref=f"{repository.full_name}#{int(issue['number'])}",
                        entity_kind="task",
                        entity_id=task.id,
                        connection_id=repository.connection_id,
                        repository_id=repository.id,
                        metadata_json={"issue_number": int(issue["number"])},
                    )
            except IntegrityError:
                pass
        sync_event.issue_link_id = link.id
        sync_event.status = "completed"
        sync_event.detail = f"Issue #{issue['number']} mirrored into an orchestration task."

    async def _process_webhook_issue_assigned(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        issue = payload.get("issue") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(issue["number"]))
        assignee_login = ((payload.get("assignee") or {}).get("login")) or ((issue.get("assignee") or {}).get("login"))
        if link is None or link.task_id is None or not assignee_login:
            sync_event.status = "ignored"
            sync_event.detail = "No linked task or assignee mapping available."
            return
        owner_id = await self._owner_id_for_repository(repository)
        project = await self.db.get(OrchestratorProject, repository.project_id) if repository.project_id else None
        repo_pool = self._repo_pool_config(project, repository=repository)
        assignee_map = dict(repo_pool.get("github_assignee_map") or {})
        mapped = assignee_map.get(assignee_login)
        agent = None
        if mapped:
            mapped_text = str(mapped).strip()
            agent = await self._load_agent_for_run(mapped_text)
            if agent is None:
                agent = await self.repo.get_agent_by_slug(owner_id, mapped_text)
        if agent is None:
            agent = await self.repo.get_agent_by_slug(owner_id, assignee_login)
        if agent is None:
            sync_event.status = "ignored"
            sync_event.detail = f"No agent slug matches GitHub assignee '{assignee_login}'."
            return
        task = await self.db.get(OrchestratorTask, link.task_id)
        if task is None:
            sync_event.status = "ignored"
            return
        task.assigned_agent_id = agent.id
        link.assignee_login = assignee_login
        sync_event.status = "completed"
        sync_event.detail = f"Issue #{issue['number']} assigned to agent {agent.slug}."
        sync_event.payload_json = {**payload, "agent_id": agent.id}

    async def _process_webhook_issue_changed(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        issue = payload.get("issue") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(issue["number"]))
        if link is None:
            sync_event.status = "ignored"
            sync_event.detail = "Issue link does not exist yet."
            return
        link.title = str(issue.get("title") or link.title)[:255]
        link.body = issue.get("body") or link.body
        link.state = str(issue.get("state") or link.state)
        link.labels_json = [item["name"] for item in issue.get("labels", []) if isinstance(item, dict)]
        link.assignee_login = ((issue.get("assignee") or {}).get("login"))
        link.issue_url = issue.get("html_url") or link.issue_url
        link.last_synced_at = datetime.now(UTC)
        link.metadata_json = {**(link.metadata_json or {}), "last_webhook_issue": issue}
        task = await self.db.get(OrchestratorTask, link.task_id) if link.task_id else None
        if task is not None:
            project = await self.db.get(OrchestratorProject, task.project_id) if task.project_id else None
            meta = dict(task.metadata_json or {})
            old_fs = dict((meta.get("github_sync_provenance") or {}).get("field_sources") or {})
            new_fs = dict(old_fs)
            src_title = self._github_field_write_source(project, meta, "title")
            src_desc = self._github_field_write_source(project, meta, "description")
            src_labels = self._github_field_write_source(project, meta, "labels")
            src_status = self._github_field_write_source(project, meta, "status")
            if src_title != "app":
                task.title = str(issue.get("title") or task.title)[:255]
                new_fs["title"] = "github"
            if src_desc != "app":
                task.description = issue.get("body") or task.description
                new_fs["description"] = "github"
            if src_labels != "app":
                task.labels_json = list(link.labels_json or [])
                new_fs["labels"] = "github"
            if src_status != "app":
                new_fs["status"] = "github"
                if link.state == "closed" and task.status not in {"completed", "synced_to_github", "archived"}:
                    await self._transition_task_status(task, "synced_to_github", reason="github issue closed")
                elif link.state == "open" and task.status == "synced_to_github":
                    await self._transition_task_status(task, "planned", reason="github issue reopened")
            meta["github_milestone_number"] = ((issue.get("milestone") or {}).get("number"))
            meta["github_sync_provenance"] = {
                "source": "github_webhook_issue_changed",
                "last_synced_at": datetime.now(UTC).isoformat(),
                "field_sources": new_fs,
            }
            task.metadata_json = meta
            orm_attributes.flag_modified(task, "metadata_json")
        sync_event.status = "completed"
        sync_event.detail = f"Issue #{issue['number']} metadata synced from GitHub."

    async def _enqueue_github_pr_review_run(
        self,
        task: OrchestratorTask,
        project: OrchestratorProject,
        *,
        review: dict[str, Any],
        pr: dict[str, Any],
    ) -> None:
        gh = (project.settings_json or {}).get("github") or {}
        if not bool(gh.get("auto_review_on_pr_review")):
            return
        if await self.repo.task_has_active_run(task.project_id, task.id):
            return
        reviewer_id = task.reviewer_agent_id
        if not reviewer_id:
            execution = (project.settings_json or {}).get("execution") or {}
            rids = execution.get("reviewer_agent_ids") or []
            reviewer_id = rids[0] if isinstance(rids, list) and rids else None
        if not reviewer_id:
            return
        author_login = ((review.get("user") or {}).get("login") if isinstance(review.get("user"), dict) else None)
        run = await self.repo.create_run(
            project_id=task.project_id,
            task_id=task.id,
            triggered_by_user_id=project.owner_id,
            orchestrator_agent_id=None,
            worker_agent_id=task.assigned_agent_id,
            reviewer_agent_id=reviewer_id,
            provider_config_id=(project.settings_json or {}).get("execution", {}).get("provider_config_id"),
            run_mode="review",
            status="queued",
            model_name=(project.settings_json or {}).get("execution", {}).get("model_name"),
            input_payload_json={
                "github_pr_review": {
                    "state": str(review.get("state") or "commented").lower(),
                    "author_login": author_login,
                    "body": review.get("body"),
                    "pr_number": pr.get("number"),
                },
            },
        )
        await self._emit_run_event(
            run,
            event_type="queued",
            message="Review run queued from GitHub PR review webhook.",
            payload={"trigger": "github_pr_review"},
        )
        await self.db.commit()
        from backend.modules.orchestration.execution.durable_execution import (
            submit_orchestration_run,
        )

        submit_orchestration_run(run.id)

    async def _process_webhook_issue_comment(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        issue = payload.get("issue") or {}
        comment = payload.get("comment") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(issue["number"]))
        if link is None or link.task_id is None:
            sync_event.status = "ignored"
            return
        cid = comment.get("id")
        thread_marker = f"<!--gh:comment_id={cid}-->" if cid else ""
        in_reply = comment.get("in_reply_to_id")
        reply_line = f"\n[in_reply_to={in_reply}]" if in_reply else ""
        await self.repo.create_task_comment(
            task_id=link.task_id,
            author_user_id=None,
            author_agent_id=None,
            body=(
                f"{thread_marker}\n[GitHub @{(comment.get('user') or {}).get('login') or 'unknown'}] "
                f"{comment.get('body') or ''}{reply_line}"
            ).strip(),
        )
        sync_event.status = "completed"
        sync_event.detail = f"GitHub comment appended to task thread for issue #{issue['number']}."

    async def _process_webhook_pull_request_opened(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        pr = payload.get("pull_request") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        issue_link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(pr["number"]))
        if issue_link and issue_link.task_id:
            task = await self.db.get(OrchestratorTask, issue_link.task_id)
            project = await self.db.get(OrchestratorProject, task.project_id) if task else None
            if task:
                task.result_payload_json = {
                    **(task.result_payload_json or {}),
                    "github_pr": {
                        "number": pr.get("number"),
                        "url": pr.get("html_url"),
                        "state": pr.get("state"),
                        "draft": pr.get("draft"),
                        "head": ((pr.get("head") or {}).get("ref")),
                        "base": ((pr.get("base") or {}).get("ref")),
                        "commits": pr.get("commits"),
                        "head_sha": ((pr.get("head") or {}).get("sha")),
                        "base_sha": ((pr.get("base") or {}).get("sha")),
                    },
                }
                orm_attributes.flag_modified(task, "result_payload_json")
                try:
                    async with self.db.begin_nested():
                        oid = await self._owner_id_for_repository(repository)
                        await self.repo.create_github_entity_mapping(
                            owner_id=oid,
                            external_kind="github_pull_request",
                            external_ref=f"{repository.full_name}#{int(pr.get('number') or 0)}",
                            entity_kind="task",
                            entity_id=task.id,
                            connection_id=repository.connection_id,
                            repository_id=repository.id,
                            metadata_json={"pr_number": int(pr.get("number") or 0)},
                        )
                except IntegrityError:
                    pass
                if project and self._project_github_settings(project).get("enforce_branch_naming", True):
                    branch_name = (pr.get("head") or {}).get("ref")
                    if not self._github_branch_name_valid_for_task(project, task, branch_name):
                        await self.repo.create_task_comment(
                            task_id=task.id,
                            author_user_id=None,
                            author_agent_id=None,
                            body=(
                                f"[GitHub branch policy] Expected `{self._github_branch_name_for_task(project, task)}` "
                                f"but received `{branch_name}`."
                            ),
                        )
                        await self.repo.create_sync_event(
                            repository_id=repository.id,
                            issue_link_id=issue_link.id,
                            action="branch_policy_violation",
                            status="failed",
                            detail="Opened PR branch does not match the project's naming convention.",
                            payload_json={"branch": branch_name, "expected": self._github_branch_name_for_task(project, task)},
                        )
                if project and self._project_github_settings(project).get("auto_activate_review_on_pr_open", True):
                    await self._enqueue_github_pr_review_run(
                        task,
                        project,
                        review={"state": "commented", "body": "PR opened"},
                        pr=pr,
                    )
        sync_event.status = "completed"
        sync_event.detail = f"Pull request #{pr['number']} opened."

    async def _process_webhook_pull_request_review(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        review = payload.get("review") or {}
        pr = payload.get("pull_request") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        issue_link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(pr["number"]))
        if issue_link and issue_link.task_id:
            rid = review.get("id")
            thread_marker = f"<!--gh:review_id={rid}-->" if rid else ""
            await self.repo.create_task_comment(
                task_id=issue_link.task_id,
                author_user_id=None,
                author_agent_id=None,
                body=(
                    f"{thread_marker}\n[GitHub PR review] {(review.get('state') or 'commented').upper()}: "
                    f"{review.get('body') or ''}"
                ).strip(),
            )
            task = await self.db.get(OrchestratorTask, issue_link.task_id)
            project = await self.db.get(OrchestratorProject, task.project_id) if task else None
            if task and project:
                await self._enqueue_github_pr_review_run(task, project, review=review, pr=pr)
        sync_event.status = "completed"
        sync_event.detail = f"Pull request review received for PR #{pr['number']}."

    async def _process_webhook_pull_request_review_comment(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        pr = payload.get("pull_request") or {}
        comment = payload.get("comment") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        issue_link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(pr["number"]))
        if issue_link and issue_link.task_id:
            marker = f"<!--gh:review_comment_id={comment.get('id')}-->" if comment.get("id") else ""
            path = str(comment.get("path") or "").strip()
            line = comment.get("line") or comment.get("original_line")
            location = f"{path}:{line}" if path and line else path
            await self.repo.create_task_comment(
                task_id=issue_link.task_id,
                author_user_id=None,
                author_agent_id=None,
                body=(
                    f"{marker}\n[GitHub PR review comment] {location}\n"
                    f"{comment.get('body') or ''}"
                ).strip(),
            )
            sync_event.issue_link_id = issue_link.id
        sync_event.status = "completed"
        sync_event.detail = f"Pull request review comment mirrored for PR #{pr['number']}."

    async def _process_webhook_pull_request_merged(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        pr = payload.get("pull_request") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        issue_link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(pr["number"]))
        if issue_link and issue_link.task_id:
            task = await self.db.get(OrchestratorTask, issue_link.task_id)
            if task:
                task.result_payload_json = {
                    **(task.result_payload_json or {}),
                    "github_pr": {
                        **((task.result_payload_json or {}).get("github_pr") or {}),
                        "number": pr.get("number"),
                        "url": pr.get("html_url"),
                        "state": "merged",
                        "merge_commit_sha": pr.get("merge_commit_sha"),
                    },
                }
                orm_attributes.flag_modified(task, "result_payload_json")
                if task.status in {"approved", "completed", "synced_to_github"}:
                    await self._transition_task_status(task, "synced_to_github", reason="pull request merged")
        sync_event.status = "completed"
        sync_event.detail = f"Pull request #{pr['number']} merged."

    async def _process_webhook_pull_request_lifecycle(
        self,
        sync_event,
        payload: dict[str, Any],
        *,
        forced_state: str | None = None,
    ) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        pr = payload.get("pull_request") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        issue_link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(pr["number"]))
        if issue_link is None or issue_link.task_id is None:
            sync_event.status = "ignored"
            return
        task = await self.db.get(OrchestratorTask, issue_link.task_id)
        if task is None:
            sync_event.status = "ignored"
            return
        prev = (task.result_payload_json or {}).get("github_pr") or {}
        head = pr.get("head") or {}
        base = pr.get("base") or {}
        state = forced_state or ("merged" if pr.get("merged") else pr.get("state")) or prev.get("state")
        reviewers = pr.get("requested_reviewers") or []
        reviewer_logins = [u.get("login") for u in reviewers if isinstance(u, dict) and u.get("login")]
        gh_pr = {
            **prev,
            "number": pr.get("number", prev.get("number")),
            "url": pr.get("html_url", prev.get("url")),
            "state": state,
            "title": pr.get("title", prev.get("title")),
            "draft": pr.get("draft", prev.get("draft")),
            "mergeable": pr.get("mergeable", prev.get("mergeable")),
            "head": head.get("ref", prev.get("head")),
            "base": base.get("ref", prev.get("base")),
            "head_sha": head.get("sha", prev.get("head_sha")),
            "base_sha": base.get("sha", prev.get("base_sha")),
            "commits": pr.get("commits", prev.get("commits")),
            "merge_commit_sha": pr.get("merge_commit_sha", prev.get("merge_commit_sha")),
            "changed_files": pr.get("changed_files", prev.get("changed_files")),
        }
        if reviewer_logins:
            gh_pr["requested_reviewers"] = reviewer_logins
        task.result_payload_json = {**(task.result_payload_json or {}), "github_pr": gh_pr}
        orm_attributes.flag_modified(task, "result_payload_json")
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action=f"github_pr_lifecycle.{(payload.get('action') or sync_event.action)}",
            status="completed",
            detail="PR fields synced from GitHub webhook.",
            payload_json={
                "task_id": task.id,
                "pr_number": pr.get("number"),
                "head_sha": gh_pr.get("head_sha"),
                "delivery_id": (payload.get("_webhook_meta") or {}).get("delivery_id"),
            },
        )
        sync_event.issue_link_id = issue_link.id
        sync_event.status = "completed"
        sync_event.detail = f"Pull request #{pr.get('number')} lifecycle synced ({payload.get('action')})."

    async def _process_webhook_push(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        ref = str(payload.get("ref") or "")
        branch = ref.split("/")[-1] if ref else ""
        commits = list(payload.get("commits") or [])
        head_sha = str(payload.get("after") or "")
        if repository is None:
            sync_event.status = "ignored"
            return
        task: OrchestratorTask | None = None
        issue_link: GithubIssueLink | None = None
        for candidate in await self.repo.list_issue_links_stale(older_than=datetime.now(UTC) + timedelta(days=3650), limit=200):
            if candidate.repository_id != repository.id or not candidate.task_id:
                continue
            candidate_task = await self.db.get(OrchestratorTask, candidate.task_id)
            if candidate_task is None:
                continue
            if branch and self._github_branch_name_valid_for_task(await self.db.get(OrchestratorProject, candidate_task.project_id), candidate_task, branch):
                task = candidate_task
                issue_link = candidate
                break
        if task is not None:
            task.result_payload_json = {
                **(task.result_payload_json or {}),
                "github_branch": {
                    "name": branch,
                    "head_sha": head_sha or None,
                    "commit_count": len(commits),
                    "commits": [
                        {
                            "sha": item.get("id"),
                            "message": item.get("message"),
                            "url": item.get("url"),
                        }
                        for item in commits[:20]
                        if isinstance(item, dict)
                    ],
                },
            }
            sync_event.issue_link_id = issue_link.id if issue_link else None
        sync_event.status = "completed"
        sync_event.detail = f"Push mirrored for branch {branch or ref}."
        sync_event.payload_json = {
            **(sync_event.payload_json or {}),
            "branch": branch,
            "head_sha": head_sha or None,
            "commit_count": len(commits),
            "commits": [
                {
                    "sha": item.get("id"),
                    "message": item.get("message"),
                    "url": item.get("url"),
                }
                for item in commits[:20]
                if isinstance(item, dict)
            ],
        }

    async def _sync_run_completion_to_github(self, run: TaskRun, task: OrchestratorTask) -> None:
        if not task.github_issue_link_id:
            return
        issue_link = await self.db.get(GithubIssueLink, task.github_issue_link_id)
        if issue_link is None:
            return
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        if repository is None:
            return
        project = await self.db.get(OrchestratorProject, task.project_id)
        github_settings = self._project_github_settings(project)
        progress_note = (
            str(run.output_payload_json.get("summary") or run.output_payload_json.get("final_output") or task.result_summary or "")
        )[:2000]
        auto_post_progress = bool(github_settings.get("auto_post_progress", False))
        if auto_post_progress:
            await self._create_github_write_approval(
                user_id=run.triggered_by_user_id,
                project_id=task.project_id,
                task_id=task.id,
                run_id=run.id,
                issue_link_id=issue_link.id,
                approval_type="github_progress_comment",
                payload_json={
                    "body": progress_note,
                    "close_issue": False,
                    "repository_id": repository.id,
                    "issue_number": issue_link.issue_number,
                    "run_id": run.id,
                    "agent_id": run.worker_agent_id or run.orchestrator_agent_id,
                },
            )
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="agent_progress_comment_pending",
                status="pending",
                detail="Agent produced a GitHub progress note draft pending approval.",
                payload_json={"run_id": run.id, "body": progress_note, "agent_id": run.worker_agent_id or run.orchestrator_agent_id},
            )
        if (
            github_settings.get("close_issue_with_manager_summary", True)
            and run.run_mode == "manager_worker"
            and task.status in {"completed", "approved", "synced_to_github"}
        ):
            final_summary = str(run.output_payload_json.get("final_output") or progress_note)[:5000]
            await self._create_github_write_approval(
                user_id=run.triggered_by_user_id,
                project_id=task.project_id,
                task_id=task.id,
                run_id=run.id,
                issue_link_id=issue_link.id,
                approval_type="github_manager_closure",
                payload_json={
                    "body": final_summary,
                    "close_issue": True,
                    "repository_id": repository.id,
                    "issue_number": issue_link.issue_number,
                    "run_id": run.id,
                },
            )
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="manager_closure_summary_pending",
                status="pending",
                detail="Manager generated a final issue closure summary pending approval.",
                payload_json={"run_id": run.id},
            )
        if bool(run.input_payload_json.get("create_pr")):
            await self._create_github_write_approval(
                user_id=run.triggered_by_user_id,
                project_id=task.project_id,
                task_id=task.id,
                run_id=run.id,
                issue_link_id=issue_link.id,
                approval_type="github_create_pr",
                payload_json={
                    "run_id": run.id,
                    "task_id": task.id,
                    "draft_pr": bool(run.input_payload_json.get("draft_pr", github_settings.get("draft_prs_by_default", True))),
                },
            )
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="create_pr_pending",
                status="pending",
                detail="Agent drafted a PR proposal pending approval.",
                payload_json={"run_id": run.id, "task_id": task.id},
            )

    def _github_branch_name_for_task(self, project: OrchestratorProject | None, task: OrchestratorTask) -> str:
        template = ((project.settings_json or {}).get("github", {}) if project else {}).get(
            "branch_prefix", "troop/{task_id}-{slug}"
        )
        branch = str(template).format(task_id=task.id, slug=self._slugify(task.title))
        branch = branch.replace("//", "/").strip("/")
        return branch[:120]

    def _github_branch_name_valid_for_task(
        self, project: OrchestratorProject | None, task: OrchestratorTask, branch_name: str | None
    ) -> bool:
        expected = self._github_branch_name_for_task(project, task)
        actual = str(branch_name or "").strip().strip("/")
        if not actual:
            return False
        return actual == expected

    def _task_state_to_github_issue_state(self, task: OrchestratorTask) -> str:
        return "closed" if task.status in {"approved", "completed", "synced_to_github", "archived"} else "open"

    async def _task_assignee_login_for_github(
        self, task: OrchestratorTask, project: OrchestratorProject | None
    ) -> str | None:
        if not task.assigned_agent_id:
            return None
        repo_pool = await self._task_repo_pool_config(task)
        assignee_map = dict(repo_pool.get("github_assignee_map") or {})
        if task.assigned_agent_id in assignee_map:
            return str(assignee_map[task.assigned_agent_id]).strip() or None
        agent = await self._load_agent_for_run(task.assigned_agent_id)
        if agent and agent.slug:
            return agent.slug
        return None

    async def _create_github_write_approval(
        self,
        *,
        user_id: str | None,
        project_id: str | None,
        task_id: str | None,
        run_id: str | None,
        issue_link_id: str | None,
        approval_type: str,
        payload_json: dict[str, Any],
    ) -> ApprovalRequest:
        approval = await self.repo.create_approval(
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            issue_link_id=issue_link_id,
            requested_by_user_id=user_id,
            approval_type=approval_type,
            status="pending",
            payload_json=payload_json,
        )
        await self.db.flush()
        return approval

    async def _create_github_pr_for_run(
        self,
        run: TaskRun,
        task: OrchestratorTask,
        repository: GithubRepository,
        issue_link: GithubIssueLink,
        *,
        approval: ApprovalRequest | None = None,
    ) -> None:
        connection = await self.db.get(GithubConnection, repository.connection_id)
        project = await self.db.get(OrchestratorProject, task.project_id)
        if connection is None:
            return
        branch_name = self._github_branch_name_for_task(project, task)
        github_settings = self._project_github_settings(project)
        if github_settings.get("respect_branch_protections", True):
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="github_branch_protection_guard",
                status="completed",
                detail="Stub: GitHub branch protection API not queried; proceeding with automation.",
                payload_json={"branch": branch_name, "run_id": run.id, "stub": True},
            )
        patch_body = str(
            run.output_payload_json.get("final_output")
            or run.output_payload_json.get("summary")
            or task.result_summary
            or ""
        )
        ap_payload = (approval.payload_json or {}) if approval is not None else {}
        for aid in list(ap_payload.get("artifact_ids") or []):
            art = await self.db.get(TaskArtifact, str(aid))
            if art is None or art.task_id != task.id:
                continue
            patch_body = (patch_body + f"\n\n### {art.title}\n{art.content or ''}").strip()
        msg_tpl = str(github_settings.get("commit_message_template") or "troop: task {task_id} {slug}")
        commit_message = msg_tpl.format(
            task_id=task.id,
            title=(task.title or "")[:120],
            slug=self._slugify(task.title),
        )[:500]
        default_branch = repository.default_branch or "main"
        ref_response = await self._github_request(
            connection,
            "GET",
            f"/repos/{repository.full_name}/git/ref/heads/{default_branch}",
        )
        if ref_response.status_code >= 400:
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="create_pr",
                status="failed",
                detail="Failed to load default branch reference before PR creation.",
                payload_json={"run_id": run.id},
            )
            return
        base_commit_sha = ((ref_response.json() or {}).get("object") or {}).get("sha")
        commit_response = await self._github_request(
            connection,
            "GET",
            f"/repos/{repository.full_name}/git/commits/{base_commit_sha}",
        )
        base_tree_sha = (commit_response.json() or {}).get("tree", {}).get("sha")
        blob_response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/git/blobs",
            json_body={"content": patch_body, "encoding": "utf-8"},
        )
        blob_sha = (blob_response.json() or {}).get("sha")
        tree_response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/git/trees",
            json_body={
                "base_tree": base_tree_sha,
                "tree": [
                    {
                        "path": f".troop/patches/{task.id}-{self._slugify(task.title)}.md",
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_sha,
                    }
                ],
            },
        )
        new_tree_sha = (tree_response.json() or {}).get("sha")
        new_commit_response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/git/commits",
            json_body={
                "message": commit_message,
                "tree": new_tree_sha,
                "parents": [base_commit_sha],
            },
        )
        new_commit_sha = (new_commit_response.json() or {}).get("sha")
        branch_response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/git/refs",
            json_body={"ref": f"refs/heads/{branch_name}", "sha": new_commit_sha},
        )
        if branch_response.status_code >= 400 and branch_response.status_code != 422:
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="create_branch",
                status="failed",
                detail="Failed to create GitHub branch for PR generation.",
                payload_json={"branch": branch_name, "run_id": run.id},
            )
            return
        pr_body = (
            f"Closes #{issue_link.issue_number}\n\n"
            f"Generated from task `{task.id}`.\n\n"
            f"{patch_body[:6000]}"
        )
        pr_response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/pulls",
            json_body={
                "title": f"[Troop] {task.title}",
                "head": branch_name,
                "base": default_branch,
                "body": pr_body,
                "draft": bool(run.input_payload_json.get("draft_pr", github_settings.get("draft_prs_by_default", True))),
            },
        )
        if pr_response.status_code >= 400:
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="create_pr",
                status="failed",
                detail="Failed to open pull request from agent output.",
                payload_json={"branch": branch_name, "run_id": run.id},
            )
            return
        pr_payload = pr_response.json()
        task.result_payload_json = {
            **(task.result_payload_json or {}),
            "github_pr": {
                "number": pr_payload.get("number"),
                "url": pr_payload.get("html_url"),
                "state": pr_payload.get("state"),
                "branch": branch_name,
                "head_sha": new_commit_sha,
                "base_sha": base_commit_sha,
            },
        }
        orm_attributes.flag_modified(task, "result_payload_json")
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="create_pr",
            status="completed",
            detail=f"Opened PR #{pr_payload.get('number')} from agent output.",
            payload_json={
                "run_id": run.id,
                "task_id": task.id,
                "branch": branch_name,
                "head_sha": new_commit_sha,
                "pr_number": pr_payload.get("number"),
                "agent_id": run.worker_agent_id or run.orchestrator_agent_id,
            },
        )

    async def _post_reviewer_pr_comment(self, run: TaskRun, task: OrchestratorTask, review_text: str) -> None:
        if not task.github_issue_link_id:
            return
        issue_link = await self.db.get(GithubIssueLink, task.github_issue_link_id)
        if issue_link is None:
            return
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        pr_payload = (task.result_payload_json or {}).get("github_pr") or {}
        pr_number = pr_payload.get("number")
        if repository is None or not pr_number:
            return
        await self._create_github_write_approval(
            user_id=run.triggered_by_user_id,
            project_id=task.project_id,
            task_id=task.id,
            run_id=run.id,
            issue_link_id=issue_link.id,
            approval_type="github_pr_review_comment",
            payload_json={
                "run_id": run.id,
                "task_id": task.id,
                "pr_number": pr_number,
                "body": review_text[:5000],
                "agent_id": run.reviewer_agent_id or run.worker_agent_id,
            },
        )
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="post_pr_review",
            status="pending",
            detail=f"Reviewer agent drafted a PR comment for #{pr_number} pending approval.",
            payload_json={"run_id": run.id, "pr_number": pr_number, "agent_id": run.reviewer_agent_id or run.worker_agent_id},
        )

    async def _sync_manager_run_to_github(self, run: TaskRun, task: OrchestratorTask) -> dict[str, Any]:
        state = self._workflow_checkpoint_artifact(run, "manager_worker.github_action_state", {})
        if state.get("completed"):
            return state
        await self._sync_run_completion_to_github(run, task)
        state = {
            "completed": True,
            "policy": str((run.input_payload_json or {}).get("github_action_policy") or "auto-on-approval"),
            "last_synced_at": datetime.now(UTC).isoformat(),
            "run_id": run.id,
        }
        self._set_workflow_checkpoint_artifact(run, key="manager_worker.github_action_state", value=state)
        return state
