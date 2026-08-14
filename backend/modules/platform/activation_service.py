"""Persist and backfill workspace activation milestones."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import Workspace
from backend.modules.identity_access.workspace_repository import WorkspaceRepository
from backend.modules.observability.metrics import record_activation_milestone
from backend.modules.platform.activation_milestones import (
    MILESTONE_ORDER,
    ActivationMilestoneKey,
    build_activation_response,
    merge_milestone,
    read_activation_state,
    write_activation_state,
)
from backend.modules.workforce.models import (
    ConnectorInstallation,
    ExternalActionExecution,
    WorkflowDefinition,
    WorkflowRun,
)


class ActivationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.workspaces = WorkspaceRepository(db)

    async def get_status(self, workspace: Workspace) -> dict[str, Any]:
        await self._backfill_missing_milestones(workspace)
        state = read_activation_state(workspace.settings_json)
        baseline = workspace.created_at
        if baseline.tzinfo is None:
            baseline = baseline.replace(tzinfo=UTC)
        if not state.get("baseline_at"):
            state["baseline_at"] = baseline.isoformat()
        return build_activation_response(
            workspace_id=workspace.id,
            baseline_at=baseline,
            milestones=dict(state.get("milestones") or {}),
        )

    async def record_milestone(
        self,
        workspace: Workspace,
        key: ActivationMilestoneKey,
        *,
        at: datetime | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        state = read_activation_state(workspace.settings_json)
        milestones = dict(state.get("milestones") or {})
        recorded = merge_milestone(
            milestones,
            key,
            at=at or datetime.now(UTC),
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
        )
        if not recorded:
            return False
        if not state.get("baseline_at"):
            baseline = workspace.created_at
            if baseline.tzinfo is None:
                baseline = baseline.replace(tzinfo=UTC)
            state["baseline_at"] = baseline.isoformat()
        state["milestones"] = milestones
        workspace.settings_json = write_activation_state(workspace.settings_json, state)
        await self.db.flush()
        record_activation_milestone(key)
        return True

    async def record_for_owner(
        self,
        owner_id: str,
        key: ActivationMilestoneKey,
        **kwargs: Any,
    ) -> bool:
        workspace = await self.workspaces.get_default_workspace_for_user(owner_id)
        if workspace is None:
            return False
        return await self.record_milestone(workspace, key, **kwargs)

    async def _backfill_missing_milestones(self, workspace: Workspace) -> None:
        state = read_activation_state(workspace.settings_json)
        milestones = dict(state.get("milestones") or {})
        missing = [key for key in MILESTONE_ORDER if key not in milestones]
        if not missing:
            return

        owner_id = workspace.owner_user_id
        changed = False

        if "first_connected_integration" in missing:
            row = await self._first_connector(owner_id)
            if row is not None:
                changed |= merge_milestone(
                    milestones,
                    "first_connected_integration",
                    at=row.created_at,
                    resource_type="connector_installation",
                    resource_id=row.id,
                    metadata={
                        "provider": (row.metadata_json or {}).get("provider"),
                        "name": row.name,
                    },
                )

        if "first_test_run" in missing:
            run = await self._first_test_run(owner_id)
            if run is not None:
                changed |= merge_milestone(
                    milestones,
                    "first_test_run",
                    at=run.created_at,
                    resource_type="workflow_run",
                    resource_id=run.id,
                    metadata={"workflow_id": run.workflow_id},
                )

        if "first_published_workflow" in missing:
            definition = await self._first_published_workflow(owner_id)
            if definition is not None:
                changed |= merge_milestone(
                    milestones,
                    "first_published_workflow",
                    at=definition.updated_at,
                    resource_type="workflow_definition",
                    resource_id=definition.id,
                    metadata={"slug": definition.slug},
                )

        if "first_external_effect" in missing:
            execution = await self._first_external_effect(owner_id)
            if execution is not None:
                changed |= merge_milestone(
                    milestones,
                    "first_external_effect",
                    at=execution.created_at,
                    resource_type="external_action_execution",
                    resource_id=execution.id,
                    metadata={
                        "action_key": execution.action_key,
                        "external_result_id": execution.external_result_id,
                    },
                )

        if not changed:
            return

        if not state.get("baseline_at"):
            baseline = workspace.created_at
            if baseline.tzinfo is None:
                baseline = baseline.replace(tzinfo=UTC)
            state["baseline_at"] = baseline.isoformat()
        state["milestones"] = milestones
        workspace.settings_json = write_activation_state(workspace.settings_json, state)
        await self.db.flush()

    async def _first_connector(self, owner_id: str) -> ConnectorInstallation | None:
        result = await self.db.execute(
            select(ConnectorInstallation)
            .where(
                ConnectorInstallation.owner_id == owner_id,
                ConnectorInstallation.status == "active",
            )
            .order_by(ConnectorInstallation.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _first_test_run(self, owner_id: str) -> WorkflowRun | None:
        result = await self.db.execute(
            select(WorkflowRun)
            .join(WorkflowDefinition, WorkflowDefinition.id == WorkflowRun.workflow_id)
            .where(WorkflowDefinition.owner_id == owner_id)
            .order_by(WorkflowRun.created_at.asc())
        )
        for run in result.scalars():
            context = run.context_json or {}
            if context.get("test_mode") is True:
                return run
        return None

    async def _first_published_workflow(self, owner_id: str) -> WorkflowDefinition | None:
        result = await self.db.execute(
            select(WorkflowDefinition)
            .where(
                WorkflowDefinition.owner_id == owner_id,
                WorkflowDefinition.published_version_id.is_not(None),
            )
            .order_by(WorkflowDefinition.updated_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _first_external_effect(self, owner_id: str) -> ExternalActionExecution | None:
        result = await self.db.execute(
            select(ExternalActionExecution)
            .where(
                ExternalActionExecution.owner_id == owner_id,
                ExternalActionExecution.status == "succeeded",
                ExternalActionExecution.external_result_id.is_not(None),
            )
            .order_by(ExternalActionExecution.created_at.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()
