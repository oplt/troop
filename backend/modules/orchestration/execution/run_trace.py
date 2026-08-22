"""Project TaskRun events and checkpoint rows into ordered safe trace spans (OBS-002A)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.pagination import build_cursor_page, fetch_limit, token_from_created_at_id
from backend.modules.orchestration.execution.execution_workflow import summarize_trace
from backend.modules.orchestration.execution.run_trace_redaction import build_safe_payload
from backend.modules.orchestration.models import ApprovalRequest, RunEvent, TaskRun
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.schemas.run_trace import (
    RunTracePageMeta,
    RunTracePageResponse,
    RunTraceSpanKind,
    RunTraceSpanSafe,
)
from backend.modules.workforce.models import ExternalActionExecution

_EVENT_KIND: dict[str, RunTraceSpanKind] = {
    "queued": RunTraceSpanKind.TRIGGER,
    "started": RunTraceSpanKind.TRIGGER,
    "workflow_step": RunTraceSpanKind.NODE,
    "tool_call_started": RunTraceSpanKind.TOOL_AUTH,
    "tool_call_completed": RunTraceSpanKind.TOOL_EFFECT,
    "tool_call_failed": RunTraceSpanKind.TOOL_EFFECT,
    "tool_calls_skipped": RunTraceSpanKind.TOOL_AUTH,
    "tool_parallel_group_started": RunTraceSpanKind.TOOL_AUTH,
    "llm_request": RunTraceSpanKind.MODEL_ATTEMPT,
    "llm_response": RunTraceSpanKind.MODEL_ATTEMPT,
    "model_retry": RunTraceSpanKind.RETRY_CHECKPOINT,
    "model_fallback": RunTraceSpanKind.RETRY_CHECKPOINT,
    "model_fallback_used": RunTraceSpanKind.RETRY_CHECKPOINT,
    "provider_failover": RunTraceSpanKind.RETRY_CHECKPOINT,
    "retry_queued": RunTraceSpanKind.RETRY_CHECKPOINT,
    "workflow_recovery": RunTraceSpanKind.RETRY_CHECKPOINT,
    "workflow_resumed": RunTraceSpanKind.RETRY_CHECKPOINT,
    "replay_queued": RunTraceSpanKind.RETRY_CHECKPOINT,
    "context_compressed": RunTraceSpanKind.RETRY_CHECKPOINT,
    "approval_grant_consumed": RunTraceSpanKind.APPROVAL,
    "approval_rejected": RunTraceSpanKind.APPROVAL,
    "unblocked": RunTraceSpanKind.APPROVAL,
    "blocked": RunTraceSpanKind.APPROVAL,
}

_STATUS_BY_EVENT: dict[str, str] = {
    "tool_call_started": "started",
    "tool_call_completed": "completed",
    "tool_call_failed": "failed",
    "llm_request": "started",
    "llm_response": "completed",
    "approval_grant_consumed": "completed",
    "approval_rejected": "rejected",
    "blocked": "blocked",
    "unblocked": "completed",
    "retry_queued": "queued",
    "workflow_recovery": "recovered",
}


def _span_title(kind: RunTraceSpanKind, event: RunEvent) -> str:
    payload = dict(event.payload_json or {})
    if kind == RunTraceSpanKind.TOOL_AUTH:
        return f"Tool auth: {payload.get('tool') or event.message[:80]}"
    if kind == RunTraceSpanKind.TOOL_EFFECT:
        return f"Tool effect: {payload.get('tool') or event.message[:80]}"
    if kind == RunTraceSpanKind.MODEL_ATTEMPT:
        model = payload.get("model") or payload.get("model_name")
        return f"Model attempt{': ' + str(model) if model else ''}"
    if kind == RunTraceSpanKind.APPROVAL:
        return payload.get("approval_type") or event.message[:80] or "Approval"
    if kind == RunTraceSpanKind.NODE:
        step = payload.get("step_id") or payload.get("title")
        return f"Workflow node{': ' + str(step) if step else ''}"
    if kind == RunTraceSpanKind.RETRY_CHECKPOINT:
        return event.message[:120] or "Retry / checkpoint"
    return event.message[:120] or event.event_type


def _event_to_span(run_id: str, event: RunEvent) -> RunTraceSpanSafe | None:
    kind = _EVENT_KIND.get(str(event.event_type or ""))
    if kind is None:
        return None
    safe_payload, restricted = build_safe_payload(
        dict(event.payload_json or {}),
        event_type=str(event.event_type or ""),
    )
    status = _STATUS_BY_EVENT.get(str(event.event_type or ""), "info")
    if event.level == "error":
        status = "failed"
    return RunTraceSpanSafe(
        id=f"evt:{event.id}",
        run_id=run_id,
        kind=kind,
        title=_span_title(kind, event),
        status=status,
        message=(event.message or "")[:400] or None,
        started_at=event.created_at,
        finished_at=event.created_at if status in {"completed", "failed", "rejected"} else None,
        safe_payload=safe_payload,
        restricted=restricted,
        source_event_id=event.id,
        source_event_type=event.event_type,
        tokens_input=int(event.input_tokens or 0),
        tokens_output=int(event.output_tokens or 0),
        cost_usd_micros=int(event.cost_usd_micros or 0),
    )


def _checkpoint_spans(run: TaskRun) -> list[RunTraceSpanSafe]:
    spans: list[RunTraceSpanSafe] = []
    for step in summarize_trace(run.checkpoint_json):
        step_id = str(step.get("step_id") or "")
        if not step_id:
            continue
        started_raw = step.get("started_at")
        started_at = _parse_iso(started_raw) or run.created_at
        finished_at = _parse_iso(step.get("completed_at"))
        safe_payload, restricted = build_safe_payload(
            {
                "step_id": step_id,
                "actor": step.get("actor"),
                "attempts": step.get("attempts"),
                "is_current": step.get("is_current"),
            }
        )
        spans.append(
            RunTraceSpanSafe(
                id=f"ckpt:{step_id}",
                run_id=run.id,
                kind=RunTraceSpanKind.NODE,
                title=str(step.get("title") or step_id),
                status=str(step.get("status") or "pending"),
                message=(step.get("last_error") or None),
                started_at=started_at,
                finished_at=finished_at,
                safe_payload=safe_payload,
                restricted=restricted,
                parent_span_id=None,
            )
        )
    return spans


def _approval_span(run_id: str, approval: ApprovalRequest) -> RunTraceSpanSafe:
    safe_payload, restricted = build_safe_payload(
        {
            "approval_type": approval.approval_type,
            "status": approval.status,
            "reason": approval.reason,
            "effect_hash": approval.effect_hash,
        }
    )
    finished_at = (
        approval.resolved_at if approval.status in {"approved", "rejected", "expired"} else None
    )
    return RunTraceSpanSafe(
        id=f"approval:{approval.id}",
        run_id=run_id,
        kind=RunTraceSpanKind.APPROVAL,
        title=f"Approval: {approval.approval_type}",
        status=str(approval.status or "pending"),
        message=(approval.reason or "")[:400] or None,
        started_at=approval.created_at,
        finished_at=finished_at,
        safe_payload=safe_payload,
        restricted=restricted,
    )


def _effect_span(run_id: str, effect: ExternalActionExecution) -> RunTraceSpanSafe:
    safe_payload, restricted = build_safe_payload(
        {
            "action_key": effect.action_key,
            "status": effect.status,
            "external_result_id": effect.external_result_id,
            "idempotency_key": effect.idempotency_key[:16] + "…"
            if effect.idempotency_key
            else None,
            "error": effect.error,
        }
    )
    finished_at = effect.updated_at if effect.status in {"completed", "failed"} else None
    return RunTraceSpanSafe(
        id=f"effect:{effect.id}",
        run_id=run_id,
        kind=RunTraceSpanKind.TOOL_EFFECT,
        title=f"External effect: {effect.action_key}",
        status=str(effect.status or "claimed"),
        message=(effect.error or "")[:400] or None,
        started_at=effect.created_at,
        finished_at=finished_at,
        safe_payload=safe_payload,
        restricted=restricted,
        parent_span_id=(
            f"approval:{effect.approval_request_id}" if effect.approval_request_id else None
        ),
    )


def _parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


class RunTraceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = OrchestrationRepository(db)

    async def _static_spans(self, run: TaskRun) -> list[RunTraceSpanSafe]:
        spans = _checkpoint_spans(run)
        approvals = await self.repo.list_approvals_for_run(run.id)
        approval_ids: list[str] = []
        for approval in approvals:
            approval_ids.append(approval.id)
            spans.append(_approval_span(run.id, approval))
        if approval_ids:
            result = await self.db.execute(
                select(ExternalActionExecution).where(
                    ExternalActionExecution.approval_request_id.in_(approval_ids)
                )
            )
            for effect in result.scalars().all():
                spans.append(_effect_span(run.id, effect))
        return spans

    async def list_run_trace_spans(
        self,
        run: TaskRun,
        *,
        limit: int,
        cursor_created_at: datetime | None = None,
        cursor_id: str | None = None,
    ) -> RunTracePageResponse:
        cap = min(max(int(limit), 1), settings.RUN_EVENTS_MAX_LIMIT)
        spans: list[RunTraceSpanSafe] = []
        truncated = False

        if cursor_created_at is None and cursor_id is None:
            spans.extend(await self._static_spans(run))

        event_cursor_created_at = cursor_created_at
        event_cursor_id = cursor_id
        if cursor_id and ":" in cursor_id:
            prefix, _, raw_id = cursor_id.partition(":")
            if prefix == "evt":
                event_cursor_created_at = cursor_created_at
                event_cursor_id = raw_id

        max_event_batches = 20
        batch = 0
        while len(spans) < fetch_limit(cap) and batch < max_event_batches:
            events = await self.repo.list_run_events(
                run.id,
                limit=100,
                cursor_created_at=event_cursor_created_at,
                cursor_id=event_cursor_id,
            )
            if not events:
                break
            for event in events:
                span = _event_to_span(run.id, event)
                if span is not None:
                    spans.append(span)
            event_cursor_created_at = events[-1].created_at
            event_cursor_id = events[-1].id
            batch += 1
            if len(events) < 100:
                break
        else:
            truncated = batch >= max_event_batches

        spans.sort(key=lambda item: (item.started_at, item.id))
        if cursor_created_at is not None and cursor_id is not None:
            spans = [
                span
                for span in spans
                if (span.started_at, span.id) > (cursor_created_at, cursor_id)
            ]

        page, next_cursor = build_cursor_page(
            spans,
            cap,
            token_from_row=lambda row: token_from_created_at_id(
                SimpleNamespace(created_at=row.started_at, id=row.id)
            ),
        )
        kinds = sorted({span.kind.value for span in page})
        return RunTracePageResponse(
            items=page,
            next_cursor=next_cursor,
            meta=RunTracePageMeta(
                run_id=run.id,
                span_kinds_present=kinds,
                truncated=truncated,
            ),
        )
