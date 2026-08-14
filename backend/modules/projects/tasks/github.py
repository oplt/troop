"""GitHub sync side effects for internal task changes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from backend.modules.github.models import GithubIssueLink, GithubRepository
from backend.modules.identity_access.models import User
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask


class TaskGithubMixin:
    async def _queue_task_github_sync_from_internal_changes(
        self,
        user: User,
        task: OrchestratorTask,
        prev_snapshot: dict[str, Any],
    ) -> None:
        if not task.github_issue_link_id:
            return
        issue_link = await self.db.get(GithubIssueLink, task.github_issue_link_id)
        if issue_link is None:
            return
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        project = await self.db.get(OrchestratorProject, task.project_id)
        if repository is None or project is None:
            return
        github = self._project_github_settings(project)
        issue_update: dict[str, Any] = {}
        if github.get("sync_state_to_github", True):
            next_state = self._task_state_to_github_issue_state(task)
            prev_state = (
                "closed"
                if prev_snapshot.get("status")
                in {"approved", "completed", "synced_to_github", "archived"}
                else "open"
            )
            if next_state != prev_state:
                issue_update["state"] = next_state
        if github.get("sync_labels_to_github", True):
            next_labels = [str(item) for item in (task.labels_json or [])]
            prev_labels = [str(item) for item in (prev_snapshot.get("labels") or [])]
            if next_labels != prev_labels:
                issue_update["labels"] = next_labels
        if github.get("sync_assignees_to_github", True):
            next_assignee = await self._task_assignee_login_for_github(task, project)
            prev_assignee = None
            prev_assignee_id = prev_snapshot.get("assigned_agent_id")
            if prev_assignee_id:
                shadow = SimpleNamespace(
                    assigned_agent_id=prev_assignee_id,
                    github_issue_link_id=task.github_issue_link_id,
                    project_id=task.project_id,
                )
                prev_assignee = await self._task_assignee_login_for_github(shadow, project)
            if next_assignee != prev_assignee:
                issue_update["assignees"] = [next_assignee] if next_assignee else []
        if github.get("sync_milestone_to_github", True):
            next_milestone = (task.metadata_json or {}).get("github_milestone_number")
            prev_milestone = (prev_snapshot.get("metadata") or {}).get("github_milestone_number")
            if next_milestone != prev_milestone:
                issue_update["milestone"] = next_milestone
        if not issue_update:
            return
        await self._create_github_write_approval(
            user_id=user.id,
            project_id=task.project_id,
            task_id=task.id,
            run_id=None,
            issue_link_id=issue_link.id,
            approval_type="github_issue_sync",
            payload_json={
                "repository_id": repository.id,
                "issue_number": issue_link.issue_number,
                "issue_update": issue_update,
            },
        )
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="sync_issue_fields_pending",
            status="pending",
            detail="Internal task changes queued for GitHub sync approval.",
            payload_json={"issue_update": issue_update, "task_id": task.id},
        )
        await self.db.commit()
