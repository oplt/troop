"""Event-driven hooks to resume paused workflow runs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.modules.workforce.models import WorkflowChildExecution, WorkflowRun

logger = get_logger(__name__)

_RESUMABLE = frozenset({"paused", "waiting_approval", "waiting_input"})
_TASK_TERMINAL = frozenset({"completed", "failed", "cancelled"})
_WORKFLOW_TERMINAL = frozenset({"completed", "failed", "cancelled"})


async def on_task_run_terminal(
    db: AsyncSession,
    task_run_id: str,
    status: str | None = None,
) -> None:
    """Resume parent workflows waiting on a terminal child TaskRun.

    Blocked is intentionally not terminal — parents are not resumed.
    """
    resolved = status
    if resolved is None:
        from backend.modules.orchestration.models import TaskRun

        task_run = await db.get(TaskRun, task_run_id)
        if task_run is None:
            return
        resolved = str(task_run.status or "")

    resolved = str(resolved or "").strip().lower()
    if resolved == "blocked" or resolved not in _TASK_TERMINAL:
        return

    result = await db.execute(
        select(WorkflowChildExecution).where(
            WorkflowChildExecution.child_type == "task_run",
            WorkflowChildExecution.child_run_id == task_run_id,
        )
    )
    children = list(result.scalars().all())
    if children:
        parent_ids: set[str] = set()
        for child in children:
            child.status = resolved
            output = dict(child.output_json or {})
            output["task_run_status"] = resolved
            child.output_json = output
            parent_ids.add(str(child.workflow_run_id))
        await db.flush()
        for parent_id in parent_ids:
            parent = await db.get(WorkflowRun, parent_id)
            if parent is not None and parent.status in _RESUMABLE:
                await _resume_workflow(db, parent)
        return

    # Legacy fallback: scan paused run JSON for _agent_runs.
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.status.in_(_RESUMABLE)))
    runs = list(result.scalars().all())
    for run in runs:
        vars_ = dict((run.context_json or {}).get("vars") or {})
        agent_runs = dict(vars_.get("_agent_runs") or {})
        if task_run_id not in {str(v) for v in agent_runs.values()}:
            continue
        await _resume_workflow(db, run)


async def on_task_run_completed(
    db: AsyncSession,
    task_run_id: str,
    status: str | None = None,
) -> None:
    """Thin alias for on_task_run_terminal (defaults to completed)."""
    await on_task_run_terminal(db, task_run_id, status=status or "completed")


async def on_workflow_run_completed(
    db: AsyncSession,
    workflow_run_id: str,
    status: str | None = None,
) -> None:
    """Resume parent workflows waiting on a terminal child WorkflowRun."""
    resolved = status
    if resolved is None:
        child_run = await db.get(WorkflowRun, workflow_run_id)
        if child_run is None:
            return
        resolved = str(child_run.status or "")

    resolved = str(resolved or "").strip().lower()
    if resolved not in _WORKFLOW_TERMINAL:
        return

    result = await db.execute(
        select(WorkflowChildExecution).where(
            WorkflowChildExecution.child_type == "workflow_run",
            WorkflowChildExecution.child_run_id == workflow_run_id,
        )
    )
    children = list(result.scalars().all())
    if children:
        parent_ids: set[str] = set()
        for child in children:
            child.status = resolved
            output = dict(child.output_json or {})
            output["child_status"] = resolved
            child.output_json = output
            parent_ids.add(str(child.workflow_run_id))
        await db.flush()
        for parent_id in parent_ids:
            parent = await db.get(WorkflowRun, parent_id)
            if parent is not None and parent.status in _RESUMABLE:
                await _resume_workflow(db, parent)
        return

    # Legacy fallback: scan paused run JSON for _subworkflow_runs.
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.status.in_(_RESUMABLE)))
    runs = list(result.scalars().all())
    for run in runs:
        vars_ = dict((run.context_json or {}).get("vars") or {})
        sub_runs = dict(vars_.get("_subworkflow_runs") or {})
        if workflow_run_id not in {str(v) for v in sub_runs.values()}:
            continue
        await _resume_workflow(db, run)


async def on_approval_decided(db: AsyncSession, approval_request_id: str) -> None:
    """Resume or fail workflows when an ApprovalRequest is decided."""
    from backend.modules.orchestration.models import ApprovalRequest

    approval = await db.get(ApprovalRequest, approval_request_id)
    if approval is None:
        return
    status = str(approval.status or "").lower()
    if status not in {"approved", "rejected"}:
        return

    payload = dict(approval.payload_json or {})
    workflow_run_id = payload.get("workflow_run_id")
    targets: list[WorkflowRun] = []
    if workflow_run_id:
        run = await db.get(WorkflowRun, str(workflow_run_id))
        if run is not None and run.status in _RESUMABLE:
            targets = [run]
    else:
        result = await db.execute(
            select(WorkflowRun).where(WorkflowRun.status == "waiting_approval")
        )
        for run in result.scalars().all():
            vars_ = dict((run.context_json or {}).get("vars") or {})
            pending_id = str(vars_.get("pending_approval_request_id") or "")
            pending_tool = dict(vars_.get("pending_tool") or {})
            if (
                pending_id == approval_request_id
                or pending_tool.get("approval_request_id") == approval_request_id
            ):
                targets.append(run)

    for run in targets:
        if status == "approved":
            await _resume_workflow(
                db,
                run,
                approval_request_id=approval_request_id,
            )
        else:
            await _reject_workflow(
                db,
                run,
                approval_request_id=approval_request_id,
            )


async def _reject_workflow(
    db: AsyncSession,
    run: WorkflowRun,
    *,
    approval_request_id: str,
) -> None:
    owner_id = str(run.created_by or "")
    if not owner_id:
        logger.warning("workflow_reject_skipped missing_owner run_id=%s", run.id)
        return
    from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService

    service = WorkflowRuntimeService(db)
    try:
        await service.apply_approval_rejection(
            owner_id,
            run.id,
            approval_request_id=approval_request_id,
        )
    except ValueError as exc:
        logger.info(
            "workflow_reject_skipped run_id=%s reason=%s",
            run.id,
            exc,
        )
    except Exception:
        logger.exception("workflow_reject_failed run_id=%s", run.id)


async def _resume_workflow(
    db: AsyncSession,
    run: WorkflowRun,
    *,
    approval_request_id: str | None = None,
) -> None:
    owner_id = str(run.created_by or "")
    if not owner_id:
        logger.warning("workflow_resume_skipped missing_owner run_id=%s", run.id)
        return
    from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService

    service = WorkflowRuntimeService(db)
    try:
        await service.resume_run(
            owner_id,
            run.id,
            approval_request_id=approval_request_id,
        )
    except ValueError as exc:
        logger.info(
            "workflow_resume_skipped run_id=%s reason=%s",
            run.id,
            exc,
        )
    except Exception:
        logger.exception("workflow_resume_failed run_id=%s", run.id)
