"""Thin orchestration execution service facade."""

from __future__ import annotations

from typing import Any

from backend.modules.orchestration.execution.artifacts import ExecutionArtifactsMixin
from backend.modules.orchestration.execution.external_actions import (
    ExecutionExternalActionsMixin,
    normalize_workflow_step_id,
)
from backend.modules.orchestration.execution.hitl import ExecutionHitlMixin
from backend.modules.orchestration.execution.manager_worker import ExecutionManagerWorkerMixin
from backend.modules.orchestration.execution.result_contracts import (
    EXTERNAL_ACTION_STEP_ID,
    normalize_subtask_graph,
    review_state_from_payload,
    run_event_tail_payloads,
    run_is_resumable,
    stage_state_payload,
    worker_result_contract,
)
from backend.modules.orchestration.execution.run_analytics import ExecutionRunAnalyticsMixin
from backend.modules.orchestration.execution.run_lifecycle import ExecutionRunLifecycleMixin
from backend.modules.orchestration.execution.run_queries import ExecutionRunQueriesMixin
from backend.modules.orchestration.execution.snapshots import ExecutionSnapshotsMixin
from backend.modules.orchestration.execution.tool_execution import ExecutionToolCallsMixin
from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import OrchestratorTask

LEGACY_STEP_ALIASES = {"github_sync": EXTERNAL_ACTION_STEP_ID}
_normalize_workflow_step_id = normalize_workflow_step_id


class OrchestrationExecutionServiceMixin(
    ExecutionSnapshotsMixin,
    ExecutionRunQueriesMixin,
    ExecutionRunAnalyticsMixin,
    ExecutionArtifactsMixin,
    ExecutionHitlMixin,
    ExecutionExternalActionsMixin,
    ExecutionToolCallsMixin,
    ExecutionManagerWorkerMixin,
    ExecutionRunLifecycleMixin,
):
    """Compatibility execution façade.

    Requires ``self.db``, ``self.repo``, ``self.audit_repo``, and
    ``self.ai_providers`` from the host service. Cross-domain calls to project,
    task, approval, and memory behavior are temporary and tracked in the shim
    retirement plan.
    """

    def _run_event_tail_payloads(
        self, events: list[Any], *, limit: int = 12
    ) -> list[dict[str, Any]]:
        return run_event_tail_payloads(events, limit=limit)

    def _stage_state_payload(self, run: TaskRun) -> dict[str, Any]:
        return stage_state_payload(run.checkpoint_json)

    def _normalize_subtask_graph(
        self,
        sub_tasks: list[dict[str, Any]],
        *,
        parent_task: OrchestratorTask | None,
    ) -> list[dict[str, Any]]:
        return normalize_subtask_graph(sub_tasks, parent_task=parent_task)

    def _worker_result_contract(
        self,
        sub_task: dict[str, Any],
        output_text: str,
        output_json: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return worker_result_contract(sub_task, output_text, output_json)

    def _review_state_from_payload(
        self, review_payload: dict[str, Any], *, round_number: int
    ) -> dict[str, Any]:
        return review_state_from_payload(review_payload, round_number=round_number)

    def _run_is_resumable(self, run: TaskRun) -> bool:
        return run_is_resumable(status=run.status, checkpoint_json=run.checkpoint_json)
