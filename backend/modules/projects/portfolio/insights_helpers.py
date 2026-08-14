"""Pure helpers for portfolio execution insights aggregation."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

VALIDATION_EVENT_TYPES = frozenset(
    {
        "output_validation_failed",
        "validation_failed",
        "schema_validation_failed",
        "hallucination_detected",
        "hallucination_failure",
    }
)


def new_insights_rollup(identifier: str | None, name: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": name,
        "runs": 0,
        "tokens": 0,
        "cost_usd": 0.0,
        "latency_sum": 0,
        "latency_count": 0,
        "retries": 0,
        "tool_failures": 0,
        "validation_failures": 0,
        "accepted": 0,
        "acceptance_total": 0,
    }


def index_events_by_run(
    event_projection: list[tuple[str, str | None, str, dict[str, Any]]],
) -> tuple[
    dict[str, list[tuple[str, dict[str, Any]]]], Counter[str], Counter[str], Counter[str], int
]:
    tool_counts: Counter[str] = Counter()
    events_by_run: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    validation_failures_by_run: Counter[str] = Counter()
    tool_failures_by_run: Counter[str] = Counter()
    hallucination_failures = 0

    for run_id, _task_id, event_type, payload in event_projection:
        events_by_run.setdefault(run_id, []).append((event_type, payload))
        if event_type == "tool_call_failed":
            tool_counts[str(payload.get("tool") or "unknown")] += 1
            tool_failures_by_run[run_id] += 1
        normalized = event_type.lower()
        if event_type in VALIDATION_EVENT_TYPES or (
            "validation" in normalized and "pass" not in normalized
        ):
            validation_failures_by_run[run_id] += 1
        if "halluc" in normalized:
            hallucination_failures += 1

    return (
        events_by_run,
        tool_counts,
        tool_failures_by_run,
        validation_failures_by_run,
        hallucination_failures,
    )


def add_run_to_rollup(
    row: dict[str, Any],
    run: Any,
    *,
    run_id: str,
    tool_failures_by_run: Counter[str],
    validation_failures_by_run: Counter[str],
) -> None:
    row["runs"] += 1
    row["tokens"] += int(run.token_total or 0)
    row["cost_usd"] += int(run.estimated_cost_micros or 0) / 1_000_000
    row["retries"] += int(run.retry_count or 0)
    if run.latency_ms is not None:
        row["latency_sum"] += int(run.latency_ms)
        row["latency_count"] += 1
    row["tool_failures"] += tool_failures_by_run.get(run_id, 0)
    row["validation_failures"] += validation_failures_by_run.get(run_id, 0)
    if run.run_mode == "review":
        row["acceptance_total"] += 1
        row["accepted"] += int(run.status == "completed")


def finalize_insights_rollups(items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in items.values():
        total = max(int(row["acceptance_total"]), 1)
        result.append(
            {
                "id": row["id"],
                "name": row["name"],
                "runs": row["runs"],
                "tokens": row["tokens"],
                "cost_usd": round(row["cost_usd"], 6),
                "avg_latency_ms": round(row["latency_sum"] / max(row["latency_count"], 1), 2),
                "retries": row["retries"],
                "tool_failures": row["tool_failures"],
                "validation_failures": row["validation_failures"],
                "acceptance_rate": round(row["accepted"] / total, 3)
                if row["acceptance_total"]
                else None,
            }
        )
    return sorted(result, key=lambda item: item["cost_usd"], reverse=True)


def summarize_discussion_signals(
    brainstorms: list[Any],
    since: datetime,
) -> tuple[int, float | None, int]:
    repetitions: list[float] = []
    discussion_rounds = 0
    discussion_loop_detected = 0
    for brainstorm in brainstorms:
        if brainstorm.updated_at < since and brainstorm.created_at < since:
            continue
        for entry in brainstorm.decision_log_json or []:
            if entry.get("type") != "round_summary":
                continue
            discussion_rounds += 1
            if entry.get("repetition_score") is not None:
                repetitions.append(float(entry["repetition_score"]))
            if (
                entry.get("consensus_kind") == "loop_detected"
                or entry.get("consensus_status") == "loop_detected"
            ):
                discussion_loop_detected += 1
    loop_score = round(sum(repetitions) / len(repetitions), 3) if repetitions else None
    return discussion_rounds, loop_score, discussion_loop_detected


def build_execution_insights_payload(
    *,
    since: datetime,
    safe_days: int,
    event_type_rows: list[tuple[str, int]],
    runs: list[Any],
    tool_counts: Counter[str],
    validation_failures_by_run: Counter[str],
    hallucination_failures: int,
    by_project: dict[str, dict[str, Any]],
    by_agent: dict[str, dict[str, Any]],
    by_task: dict[str, dict[str, Any]],
    by_provider: dict[str, dict[str, Any]],
    sync_events: list[Any],
    discussion_rounds: int,
    discussion_loop_score: float | None,
    discussion_loop_detected: int,
    evaluation_records: int,
) -> dict[str, Any]:
    by_type = {event_type: count for event_type, count in event_type_rows}
    tool_failures_by_tool = [
        {"tool": tool, "count": count} for tool, count in tool_counts.most_common(25)
    ]
    latencies = sorted(int(run.latency_ms) for run in runs if run.latency_ms is not None)
    p95_index = max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1)) if latencies else 0
    review_runs = [run for run in runs if run.run_mode == "review"]
    accepted_after_review = sum(1 for run in review_runs if run.status == "completed")

    return {
        "since": since,
        "days": safe_days,
        "by_event_type": [
            {"event_type": event_type, "count": count} for event_type, count in event_type_rows
        ],
        "tool_failures_by_tool": tool_failures_by_tool,
        "reopen_events": int(by_type.get("reopened", 0)),
        "brainstorm_round_summary_events": int(by_type.get("brainstorm_round_summary", 0)),
        "blocked_events": int(by_type.get("blocked", 0)),
        "tool_call_failed_events": int(by_type.get("tool_call_failed", 0)),
        "total_runs": len(runs),
        "completed_runs": sum(1 for run in runs if run.status == "completed"),
        "failed_runs": sum(1 for run in runs if run.status == "failed"),
        "total_tokens": sum(int(run.token_total or 0) for run in runs),
        "total_cost_usd": round(
            sum(int(run.estimated_cost_micros or 0) for run in runs) / 1_000_000, 6
        ),
        "avg_latency_ms": round(sum(latencies) / max(len(latencies), 1), 2),
        "p95_latency_ms": float(latencies[p95_index]) if latencies else 0.0,
        "retry_count": sum(int(run.retry_count or 0) for run in runs),
        "retry_rate": round(
            sum(1 for run in runs if int(run.retry_count or 0) > 0) / max(len(runs), 1), 3
        ),
        "validation_failures": sum(validation_failures_by_run.values()),
        "hallucination_failures": hallucination_failures,
        "github_sync_events": len(sync_events),
        "github_sync_failures": sum(
            1 for item in sync_events if item.status in {"failed", "error"}
        ),
        "discussion_rounds": discussion_rounds,
        "discussion_loop_score": discussion_loop_score,
        "discussion_loop_detected": discussion_loop_detected,
        "acceptance_checks": len(review_runs),
        "accepted_after_review": accepted_after_review,
        "acceptance_rate_after_review": round(accepted_after_review / len(review_runs), 3)
        if review_runs
        else None,
        "evaluation_records": evaluation_records,
        "by_project": finalize_insights_rollups(by_project),
        "by_agent": finalize_insights_rollups(by_agent),
        "by_task": finalize_insights_rollups(by_task),
        "by_provider": finalize_insights_rollups(by_provider),
    }
