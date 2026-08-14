"""Build redacted evaluation cases from orchestration production traces (EVAL-001A)."""

from __future__ import annotations

import re
from typing import Any

from backend.modules.ai.evaluations.assertions import (
    derive_assertions_from_expected,
    normalize_assertions,
)
from backend.modules.orchestration.execution.run_trace_redaction import redact_trace_payload
from backend.modules.orchestration.models import RunEvent, TaskRun
from backend.modules.orchestration.schemas.run_trace import RunTraceSpanSafe
from backend.modules.orchestration.tool_execution_context import skill_version_ids_from_run

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.IGNORECASE)
_PHONE_RE = re.compile(r"\b\+?\d[\d\s().-]{7,}\d\b")


def redact_pii(value: Any, *, depth: int = 0) -> Any:
    """Layer PII redaction on top of trace secret redaction."""
    redacted = redact_trace_payload(value, depth=depth)
    if isinstance(redacted, str):
        text = _EMAIL_RE.sub("[email redacted]", redacted)
        return _PHONE_RE.sub("[phone redacted]", text)
    if isinstance(redacted, dict):
        return {key: redact_pii(item, depth=depth + 1) for key, item in redacted.items()}
    if isinstance(redacted, list):
        return [redact_pii(item, depth=depth + 1) for item in redacted]
    return redacted


def _prompt_version_from_events(events: list[RunEvent]) -> str | None:
    for event in reversed(events):
        if str(event.event_type or "") != "llm_response":
            continue
        payload = dict(event.payload_json or {})
        version_id = payload.get("prompt_version_id") or payload.get("ai_prompt_version_id")
        if version_id:
            return str(version_id)
    return None


def _workflow_version_from_run(run: TaskRun) -> str | None:
    checkpoint = dict(run.checkpoint_json or {})
    for key in ("workflow_version_id", "published_workflow_version_id"):
        value = checkpoint.get(key)
        if value:
            return str(value)
    workflow = checkpoint.get("workflow") or {}
    if isinstance(workflow, dict):
        for key in ("version_id", "workflow_version_id"):
            value = workflow.get(key)
            if value:
                return str(value)
    execution = checkpoint.get("execution") or {}
    if isinstance(execution, dict):
        value = execution.get("workflow_version_id")
        if value:
            return str(value)
    return None


def build_provenance(
    run: TaskRun,
    *,
    events: list[RunEvent] | None = None,
    source_trace_span_id: str | None = None,
) -> dict[str, Any]:
    checkpoint = dict(run.checkpoint_json or {})
    skill_snapshot = dict(checkpoint.get("skill_version_snapshot") or {})
    provenance: dict[str, Any] = {
        "run_id": run.id,
        "project_id": run.project_id,
        "task_id": run.task_id,
        "run_mode": run.run_mode,
        "run_status": run.status,
        "model_name": run.model_name,
        "provider_config_id": run.provider_config_id,
        "skill_version_ids": skill_version_ids_from_run(run),
        "skill_snapshot": redact_pii(
            {
                "captured_at": skill_snapshot.get("captured_at"),
                "agent_id": skill_snapshot.get("agent_id"),
                "skill_count": len(skill_snapshot.get("skills") or []),
            }
        ),
        "workflow_version_id": _workflow_version_from_run(run),
        "prompt_version_id": _prompt_version_from_events(events or []),
        "source_trace_span_id": source_trace_span_id,
    }
    query_snapshot = checkpoint.get("query_snapshot")
    if isinstance(query_snapshot, dict) and query_snapshot:
        provenance["query_snapshot_keys"] = sorted(str(key) for key in query_snapshot)
    return provenance


def _span_brief(span: RunTraceSpanSafe) -> dict[str, Any]:
    return {
        "id": span.id,
        "kind": span.kind.value if hasattr(span.kind, "value") else str(span.kind),
        "title": span.title,
        "status": span.status,
        "message": span.message,
        "safe_payload": span.safe_payload,
    }


def build_input_snapshot(
    run: TaskRun,
    *,
    spans: list[RunTraceSpanSafe],
    source_trace_span_id: str | None = None,
) -> dict[str, Any]:
    selected = None
    if source_trace_span_id:
        selected = next((span for span in spans if span.id == source_trace_span_id), None)
    snapshot: dict[str, Any] = {
        "run_status": run.status,
        "input_payload": redact_pii(dict(run.input_payload_json or {})),
        "output_payload": redact_pii(dict(run.output_payload_json or {})),
        "trace_excerpt": [_span_brief(span) for span in spans[:25]],
    }
    if selected is not None:
        snapshot["selected_span"] = _span_brief(selected)
    return snapshot


def build_input_variables(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_input": dict(snapshot.get("input_payload") or {}),
        "run_output": dict(snapshot.get("output_payload") or {}),
        "selected_span": snapshot.get("selected_span"),
    }


def apply_correction(correction: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(correction or {})
    expected_output_text = payload.get("expected_output_text")
    if expected_output_text is not None:
        expected_output_text = str(expected_output_text)
    expected_output_json = payload.get("expected_output_json")
    if expected_output_json is not None and not isinstance(expected_output_json, dict):
        expected_output_json = None
    notes = payload.get("notes")
    assertions = normalize_assertions(payload.get("expected_assertions"))
    if assertions is None and expected_output_json is not None:
        assertions = derive_assertions_from_expected(expected_output_json)
    if assertions is None and expected_output_text:
        assertions = normalize_assertions(
            {
                "mode": "deterministic",
                "rules": [{"type": "text_equals", "value": expected_output_text.strip()}],
            }
        )
    return {
        "expected_output_text": expected_output_text,
        "expected_output_json": expected_output_json,
        "expected_assertions_json": assertions,
        "notes": str(notes) if notes is not None else None,
        "correction_json": redact_pii(payload) if payload else None,
    }
