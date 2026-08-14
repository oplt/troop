"""Portfolio execution analytics and rollups."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from backend.modules.identity_access.models import User
from backend.modules.projects.orchestration_models import OrchestratorTask
from backend.modules.projects.portfolio.insights_helpers import (
    add_run_to_rollup,
    build_execution_insights_payload,
    index_events_by_run,
    new_insights_rollup,
    summarize_discussion_signals,
)
from backend.modules.team.models import AgentProfile


class PortfolioInsightsMixin:
    async def execution_insights(self, user: User, days: int = 7) -> dict[str, Any]:
        safe_days = max(1, min(int(days or 7), 90))
        since = datetime.now(UTC) - timedelta(days=safe_days)
        rows = await self.repo.aggregate_run_events_by_type_for_owner(user.id, since)
        runs = await self.repo.list_runs_for_owner_since(user.id, since, limit=2000)
        event_projection = await self.repo.list_observability_events_for_owner(user.id, since)
        (
            _events_by_run,
            tool_counts,
            tool_failures_by_run,
            validation_failures_by_run,
            hallucination_failures,
        ) = index_events_by_run(event_projection)

        projects = await self.repo.list_projects(user.id)
        project_names = {project.id: project.name for project in projects}
        task_ids = {run.task_id for run in runs if run.task_id}
        task_names: dict[str, str] = {}
        if task_ids:
            task_result = await self.db.execute(
                select(OrchestratorTask.id, OrchestratorTask.title).where(
                    OrchestratorTask.id.in_(task_ids)
                )
            )
            task_names = {str(task_id): str(title) for task_id, title in task_result.all()}
        agent_result = await self.db.execute(
            select(AgentProfile.id, AgentProfile.name).where(AgentProfile.owner_id == user.id)
        )
        agent_names = {str(agent_id): str(name) for agent_id, name in agent_result.all()}
        providers = await self.repo.list_owned_providers(user.id, enabled_only=False)
        provider_names = {provider.id: provider.name for provider in providers}

        by_project: dict[str, dict[str, Any]] = {}
        by_agent: dict[str, dict[str, Any]] = {}
        by_task: dict[str, dict[str, Any]] = {}
        by_provider: dict[str, dict[str, Any]] = {}

        for run in runs:
            project_row = by_project.setdefault(
                run.project_id,
                new_insights_rollup(run.project_id, project_names.get(run.project_id, "Project")),
            )
            add_run_to_rollup(
                project_row,
                run,
                run_id=run.id,
                tool_failures_by_run=tool_failures_by_run,
                validation_failures_by_run=validation_failures_by_run,
            )
            agent_id = run.worker_agent_id or run.orchestrator_agent_id
            if agent_id:
                agent_row = by_agent.setdefault(
                    agent_id, new_insights_rollup(agent_id, agent_names.get(agent_id, agent_id[:8]))
                )
                add_run_to_rollup(
                    agent_row,
                    run,
                    run_id=run.id,
                    tool_failures_by_run=tool_failures_by_run,
                    validation_failures_by_run=validation_failures_by_run,
                )
            if run.task_id:
                task_row = by_task.setdefault(
                    run.task_id, new_insights_rollup(run.task_id, task_names.get(run.task_id, "Task"))
                )
                add_run_to_rollup(
                    task_row,
                    run,
                    run_id=run.id,
                    tool_failures_by_run=tool_failures_by_run,
                    validation_failures_by_run=validation_failures_by_run,
                )
            if run.provider_config_id:
                provider_row = by_provider.setdefault(
                    run.provider_config_id,
                    new_insights_rollup(
                        run.provider_config_id,
                        provider_names.get(run.provider_config_id, "Provider"),
                    ),
                )
                add_run_to_rollup(
                    provider_row,
                    run,
                    run_id=run.id,
                    tool_failures_by_run=tool_failures_by_run,
                    validation_failures_by_run=validation_failures_by_run,
                )

        sync_events = await self.repo.list_sync_events_for_owner_since(user.id, since)
        brainstorms = await self.repo.list_brainstorms(user.id)
        discussion_rounds, discussion_loop_score, discussion_loop_detected = summarize_discussion_signals(
            brainstorms,
            since,
        )
        evaluation_records = await self.repo.count_eval_records_for_owner_since(user.id, since)
        return build_execution_insights_payload(
            since=since,
            safe_days=safe_days,
            event_type_rows=rows,
            runs=runs,
            tool_counts=tool_counts,
            validation_failures_by_run=validation_failures_by_run,
            hallucination_failures=hallucination_failures,
            by_project=by_project,
            by_agent=by_agent,
            by_task=by_task,
            by_provider=by_provider,
            sync_events=sync_events,
            discussion_rounds=discussion_rounds,
            discussion_loop_score=discussion_loop_score,
            discussion_loop_detected=discussion_loop_detected,
            evaluation_records=evaluation_records,
        )
