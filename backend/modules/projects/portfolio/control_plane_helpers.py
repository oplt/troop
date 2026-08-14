"""Pure helpers for portfolio control-plane read models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

ESCALATION_APPROVAL_TYPES = frozenset({"rule_escalation", "task_escalation", "sla_escalation"})
STUCK_RUN_THRESHOLD_MINUTES = 45


def build_escalation_inbox(project_approvals: list[Any], *, limit: int = 8) -> list[dict[str, Any]]:
    return [
        {
            "approval_id": item.id,
            "approval_type": item.approval_type,
            "task_id": item.task_id,
            "run_id": item.run_id,
            "reason": item.reason,
            "created_at": item.created_at,
        }
        for item in project_approvals
        if item.approval_type in ESCALATION_APPROVAL_TYPES
    ][:limit]


def compute_project_health(
    *,
    blocked_count: int,
    repo_failures: int,
    ingest_failures: int,
    escalation_count: int,
) -> dict[str, Any]:
    health_score = 100
    health_score -= min(blocked_count * 10, 40)
    health_score -= min(repo_failures * 8, 24)
    health_score -= min(ingest_failures * 8, 16)
    health_score -= min(escalation_count * 6, 18)
    health_status = (
        "healthy" if health_score >= 80 else "watch" if health_score >= 55 else "critical"
    )
    return {
        "status": health_status,
        "score": health_score,
        "repository_failures": repo_failures,
        "index_failures": ingest_failures,
        "open_blockers": blocked_count,
    }


def build_queue_depth(task_counts: dict[str, int], run_counts: dict[str, int]) -> dict[str, int]:
    return {
        "queued_runs": int(run_counts.get("queued", 0)),
        "active_runs": int(run_counts.get("in_progress", 0)) + int(run_counts.get("blocked", 0)),
        "queued_tasks": int(task_counts.get("queued", 0)) + int(task_counts.get("planned", 0)),
    }


def build_project_control_plane_row(
    *,
    project: Any,
    manager_agent: Any | None,
    task_counts: dict[str, int],
    run_counts: dict[str, int],
    blocked_tasks: list[Any],
    project_approvals: list[Any],
    latest_run: Any | None,
    repo_failures: int,
    ingest_failures: int,
    cost_usd_30d: float,
    token_total_30d: int,
    repository_links: int,
    execution_policy: dict[str, Any],
) -> dict[str, Any]:
    blocked_count = int(task_counts.get("blocked", 0))
    escalation_inbox = build_escalation_inbox(project_approvals)
    queue_depth = build_queue_depth(task_counts, run_counts)
    return {
        "project_id": project.id,
        "name": project.name,
        "slug": project.slug,
        "manager": {
            "agent_id": getattr(manager_agent, "id", None),
            "name": getattr(manager_agent, "name", None),
            "slug": getattr(manager_agent, "slug", None),
        },
        "health": compute_project_health(
            blocked_count=blocked_count,
            repo_failures=repo_failures,
            ingest_failures=ingest_failures,
            escalation_count=len(escalation_inbox),
        ),
        "queue_depth": queue_depth,
        "cost_rollup": {
            "cost_usd_30d": round(cost_usd_30d, 4),
            "token_total_30d": token_total_30d,
            "repository_links": repository_links,
        },
        "blocked_work": [
            {
                "task_id": task.id,
                "title": task.title,
                "priority": task.priority,
                "updated_at": task.updated_at,
            }
            for task in blocked_tasks[:6]
        ],
        "escalation_inbox": escalation_inbox,
        "latest_run": {
            "run_id": latest_run.id,
            "status": latest_run.status,
            "task_id": latest_run.task_id,
            "created_at": latest_run.created_at,
        }
        if latest_run
        else None,
        "execution_policy": execution_policy,
    }


def _status_from_thresholds(value: float, *, watch: float, critical: float) -> str:
    if value >= critical:
        return "critical"
    if value >= watch:
        return "watch"
    return "healthy"


def build_operator_dashboard(
    *,
    totals: dict[str, Any],
    queued_runs_count: int,
    active_runs_count: int,
    stuck_runs: list[Any],
    pending_webhooks: list[Any],
    replay_backlog: list[Any],
    providers: list[Any],
    index_running_count: int,
    index_failed_count: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    oldest_pending_webhook = min((event.created_at for event in pending_webhooks), default=None)
    webhook_lag_minutes = (
        round((generated_at - oldest_pending_webhook).total_seconds() / 60, 1)
        if oldest_pending_webhook
        else 0.0
    )
    provider_unhealthy = [provider for provider in providers if not provider.is_healthy]
    queue_status = _status_from_thresholds(float(queued_runs_count), watch=8, critical=20)
    webhook_status = _status_from_thresholds(webhook_lag_minutes, watch=15, critical=60)
    replay_status = _status_from_thresholds(float(len(replay_backlog)), watch=3, critical=8)
    stuck_status = "critical" if stuck_runs else "healthy"
    index_status = (
        "critical" if index_failed_count else "watch" if index_running_count else "healthy"
    )
    provider_status = (
        "critical" if len(provider_unhealthy) >= 2 else "watch" if provider_unhealthy else "healthy"
    )

    return {
        "generated_at": generated_at,
        "queue_health": {
            "queued_runs": queued_runs_count,
            "active_runs": active_runs_count,
            "blocked_tasks": totals["blocked_tasks"],
            "status": queue_status,
        },
        "webhook_lag": {
            "pending_events": len(pending_webhooks),
            "max_lag_minutes": webhook_lag_minutes,
            "status": webhook_status,
        },
        "replay_backlog": {
            "events": len(replay_backlog),
            "failed_events": sum(
                1 for event in replay_backlog if event.status in {"failed", "error"}
            ),
            "status": replay_status,
        },
        "stuck_runs": {
            "count": len(stuck_runs),
            "threshold_minutes": STUCK_RUN_THRESHOLD_MINUTES,
            "oldest_started_at": min(
                ((run.started_at or run.created_at) for run in stuck_runs),
                default=None,
            ),
            "status": stuck_status,
        },
        "services": [
            {
                "key": "runtime_queue",
                "label": "Runtime queue",
                "status": queue_status,
                "summary": (
                    f"{queued_runs_count} queued run(s), "
                    f"{active_runs_count} active/blocking run(s)."
                ),
                "metrics": {
                    "queued_runs": queued_runs_count,
                    "active_runs": active_runs_count,
                },
            },
            {
                "key": "github_sync",
                "label": "GitHub sync",
                "status": webhook_status if pending_webhooks else "healthy",
                "summary": (
                    f"{len(pending_webhooks)} pending webhook event(s), "
                    f"max lag {webhook_lag_minutes} min."
                ),
                "metrics": {
                    "pending_events": len(pending_webhooks),
                    "max_lag_minutes": webhook_lag_minutes,
                },
            },
            {
                "key": "repo_indexing",
                "label": "Repo indexing",
                "status": index_status,
                "summary": (
                    f"{index_running_count} indexing job(s) running, {index_failed_count} failed."
                ),
                "metrics": {
                    "running_jobs": index_running_count,
                    "failed_jobs": index_failed_count,
                },
            },
            {
                "key": "durable_workflow",
                "label": "Durable workflow",
                "status": stuck_status,
                "summary": f"{len(stuck_runs)} stuck run(s) over {STUCK_RUN_THRESHOLD_MINUTES} min threshold.",
                "metrics": {
                    "stuck_runs": len(stuck_runs),
                    "threshold_minutes": STUCK_RUN_THRESHOLD_MINUTES,
                },
            },
            {
                "key": "model_routing",
                "label": "Model routing",
                "status": provider_status,
                "summary": (
                    f"{len(provider_unhealthy)} unhealthy provider(s) "
                    f"out of {len(providers)} configured."
                ),
                "metrics": {
                    "unhealthy_providers": len(provider_unhealthy),
                    "providers": len(providers),
                },
            },
        ],
    }
