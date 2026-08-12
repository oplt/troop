"""Event-driven hooks to resume paused workflow runs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.modules.workforce.models import WorkflowRun

logger = get_logger(__name__)

_RESUMABLE = frozenset({"paused", "waiting_approval", "waiting_input"})


async def on_task_run_completed(db: AsyncSession, task_run_id: str) -> None:
    """Resume parent workflows waiting on a child TaskRun."""
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.status.in_(_RESUMABLE)))
    runs = list(result.scalars().all())
    for run in runs:
        vars_ = dict((run.context_json or {}).get("vars") or {})
        agent_runs = dict(vars_.get("_agent_runs") or {})
        if task_run_id not in {str(v) for v in agent_runs.values()}:
            continue
        await _resume_workflow(db, run)


async def on_workflow_run_completed(db: AsyncSession, workflow_run_id: str) -> None:
    """Resume parent workflows waiting on a child WorkflowRun."""
    result = await db.execute(select(WorkflowRun).where(WorkflowRun.status.in_(_RESUMABLE)))
    runs = list(result.scalars().all())
    for run in runs:
        vars_ = dict((run.context_json or {}).get("vars") or {})
        sub_runs = dict(vars_.get("_subworkflow_runs") or {})
        if workflow_run_id not in {str(v) for v in sub_runs.values()}:
            continue
        await _resume_workflow(db, run)


async def on_approval_decided(db: AsyncSession, approval_request_id: str) -> None:
    """Resume workflows waiting on a decided ApprovalRequest."""
    from backend.modules.orchestration.models import ApprovalRequest

    approval = await db.get(ApprovalRequest, approval_request_id)
    if approval is None or approval.status != "approved":
        return

    payload = dict(approval.payload_json or {})
    workflow_run_id = payload.get("workflow_run_id")
    if workflow_run_id:
        run = await db.get(WorkflowRun, str(workflow_run_id))
        if run is not None and run.status in _RESUMABLE:
            await _resume_workflow(
                db,
                run,
                approval_request_id=approval_request_id,
            )
        return

    result = await db.execute(select(WorkflowRun).where(WorkflowRun.status == "waiting_approval"))
    for run in result.scalars().all():
        vars_ = dict((run.context_json or {}).get("vars") or {})
        pending_id = str(vars_.get("pending_approval_request_id") or "")
        pending_tool = dict(vars_.get("pending_tool") or {})
        if (
            pending_id == approval_request_id
            or pending_tool.get("approval_request_id") == approval_request_id
        ):
            await _resume_workflow(
                db,
                run,
                approval_request_id=approval_request_id,
            )


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
