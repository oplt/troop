"""Portfolio control-plane aggregation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.modules.identity_access.models import User
from backend.modules.projects.portfolio.control_plane_helpers import (
    STUCK_RUN_THRESHOLD_MINUTES,
    build_operator_dashboard,
    build_project_control_plane_row,
)


class PortfolioControlPlaneMixin:
    async def portfolio_control_plane(self, user: User) -> dict[str, Any]:
        projects = await self.repo.list_projects(user.id)
        approvals = await self.repo.list_approvals(user.id)
        providers = await self.repo.list_providers(user.id)
        policy_defaults = await self.get_portfolio_execution_policy(user)
        cost_since = datetime.now(UTC) - timedelta(days=30)
        stuck_threshold = datetime.now(UTC) - timedelta(minutes=STUCK_RUN_THRESHOLD_MINUTES)
        project_ids = [project.id for project in projects]
        bundle = await self.repo.load_portfolio_control_plane_bundle(
            user.id,
            project_ids,
            cost_since=cost_since,
            stuck_before=stuck_threshold,
        )

        rows: list[dict[str, Any]] = []
        totals = {
            "projects": len(projects),
            "active_runs": 0,
            "blocked_tasks": 0,
            "pending_escalations": 0,
            "queue_depth": 0,
            "cost_usd_30d": 0.0,
        }
        approvals_by_project: dict[str, list[Any]] = {}
        for item in approvals:
            if item.status == "pending" and item.project_id:
                approvals_by_project.setdefault(item.project_id, []).append(item)

        for project in projects:
            task_counts = bundle["task_status_counts"].get(project.id, {})
            run_counts = bundle["run_status_counts"].get(project.id, {})
            blocked_tasks = bundle["blocked_tasks"].get(project.id, [])
            blocked_count = int(task_counts.get("blocked", 0))
            project_approvals = approvals_by_project.get(project.id, [])
            row = build_project_control_plane_row(
                project=project,
                manager_agent=bundle["managers"].get(project.id),
                task_counts=task_counts,
                run_counts=run_counts,
                blocked_tasks=blocked_tasks,
                project_approvals=project_approvals,
                latest_run=bundle["latest_runs"].get(project.id),
                repo_failures=int(bundle["sync_failure_counts"].get(project.id, 0)),
                ingest_failures=int(bundle["ingest_failure_counts"].get(project.id, 0)),
                cost_usd_30d=float(bundle["run_cost_30d"].get(project.id, 0.0)),
                token_total_30d=int(bundle["run_tokens_30d"].get(project.id, 0)),
                repository_links=int(bundle["repo_link_counts"].get(project.id, 0)),
                execution_policy=self._project_execution_policy_summary(project, policy_defaults),
            )
            queue_depth = row["queue_depth"]
            escalation_inbox = row["escalation_inbox"]
            totals["active_runs"] += queue_depth["active_runs"] + queue_depth["queued_runs"]
            totals["blocked_tasks"] += blocked_count
            totals["pending_escalations"] += len(escalation_inbox)
            totals["queue_depth"] += sum(queue_depth.values())
            totals["cost_usd_30d"] += float(row["cost_rollup"]["cost_usd_30d"])
            rows.append(row)

        operator_dashboard = build_operator_dashboard(
            totals=totals,
            queued_runs_count=int(bundle["queued_run_count"]),
            active_runs_count=int(bundle["active_run_count"]),
            stuck_runs=list(bundle["stuck_runs"]),
            pending_webhooks=list(bundle["pending_webhooks"]),
            replay_backlog=list(bundle["replay_backlog"]),
            providers=providers,
            index_running_count=int(bundle["ingest_running_count"]),
            index_failed_count=int(bundle["ingest_failed_count"]),
        )

        totals["cost_usd_30d"] = round(float(totals["cost_usd_30d"]), 4)
        return {
            "generated_at": datetime.now(UTC),
            "totals": totals,
            "execution_policy": policy_defaults,
            "operator_dashboard": operator_dashboard,
            "projects": rows,
        }
