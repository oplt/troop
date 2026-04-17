from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncGenerator

import strawberry
from fastapi import Depends
from strawberry.fastapi import GraphQLRouter
from strawberry.schema.config import StrawberryConfig
from strawberry.scalars import JSON
from strawberry.types import Info

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules.orchestration.control_plane import (
    ControlPlaneEvent,
    HierarchyControlPlaneService,
    control_plane_pubsub,
)


@strawberry.type
class ModelProfileType:
    id: str
    provider_config_id: str | None
    provider_name: str | None
    provider_type: str | None
    model_slug: str
    display_name: str
    temperature: float | None
    max_tokens: int | None
    supports_tools: bool
    supports_structured_output: bool
    max_context_tokens: int | None
    is_fallback: bool


@strawberry.type
class TaskType:
    id: str
    title: str
    description: str | None
    status: str
    priority: str
    task_type: str
    acceptance_criteria: str | None
    result_summary: str | None
    labels: list[str]
    updated_at: datetime
    pending_approval_count: int


@strawberry.type
class RunType:
    id: str
    status: str
    run_mode: str
    model_name: str | None
    token_total: int
    estimated_cost_micros: int
    latency_ms: int | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@strawberry.type
class ApprovalType:
    id: str
    task_id: str | None
    run_id: str | None
    approval_type: str
    status: str
    reason: str | None
    created_at: datetime


@strawberry.type
class BrainstormType:
    id: str
    topic: str
    status: str
    participant_count: int
    current_round: int
    consensus_status: str
    updated_at: datetime


@strawberry.type
class ArtifactType:
    id: str
    task_id: str
    run_id: str | None
    kind: str
    title: str
    content: str | None
    metadata: JSON
    created_at: datetime


@strawberry.type
class MemberType:
    id: str
    parent_id: str | None
    membership_id: str | None
    name: str
    role: str
    objective: str | None
    skills: list[str]
    instructions: str
    tool_access: list[str]
    memory_scope: str
    memory_policy: JSON
    autonomy_level: str
    approval_policy: str
    current_status: str
    workload_count: int
    active_task_count: int
    is_active: bool
    model_profile: ModelProfileType | None
    fallback_model_profile: ModelProfileType | None
    routing_policy: JSON
    tasks: list[TaskType]
    runs: list[RunType]
    runtime_profile: JSON


@strawberry.type
class ProjectSummaryType:
    id: str
    name: str
    status: str
    goals_markdown: str
    memory_scope: str
    updated_at: datetime


@strawberry.type
class HierarchySnapshotType:
    project: ProjectSummaryType
    manager_id: str | None
    members: list[MemberType]
    pending_approvals: list[ApprovalType]
    brainstorms: list[BrainstormType]


@strawberry.type
class ControlPlaneEventType:
    event_type: str
    project_id: str | None
    member_id: str | None
    task_id: str | None
    run_id: str | None
    status: str | None
    payload: JSON
    emitted_at: datetime


@strawberry.input
class TeamMemberInput:
    project_id: str
    name: str | None = None
    slug: str | None = None
    role: str | None = None
    objective: str | None = None
    instructions: str | None = None
    skills: list[str] | None = None
    tool_access: list[str] | None = None
    memory_scope: str | None = None
    memory_policy: JSON | None = None
    autonomy_level: str | None = None
    approval_policy: str | None = None
    parent_member_id: str | None = None
    model_profile: JSON | None = None
    fallback_model_profile: JSON | None = None
    routing_policy: JSON | None = None
    is_active: bool | None = None
    is_manager: bool = False


@strawberry.input
class TaskInput:
    project_id: str
    title: str
    description: str | None = None
    assigned_member_id: str | None = None
    reviewer_member_id: str | None = None
    acceptance_criteria: str | None = None
    priority: str | None = None
    task_type: str | None = None
    labels: list[str] | None = None
    metadata: JSON | None = None


def _model_profile(value: dict[str, Any] | None) -> ModelProfileType | None:
    if not value:
        return None
    return ModelProfileType(**value)


def _task(value: dict[str, Any]) -> TaskType:
    return TaskType(**value)


def _run(value: dict[str, Any]) -> RunType:
    return RunType(**value)


def _approval(value: dict[str, Any]) -> ApprovalType:
    return ApprovalType(**value)


def _brainstorm(value: dict[str, Any]) -> BrainstormType:
    return BrainstormType(**value)


def _member(value: dict[str, Any]) -> MemberType:
    return MemberType(
        **{
            **value,
            "model_profile": _model_profile(value.get("model_profile")),
            "fallback_model_profile": _model_profile(value.get("fallback_model_profile")),
            "tasks": [_task(item) for item in value.get("tasks", [])],
            "runs": [_run(item) for item in value.get("runs", [])],
        }
    )


def _snapshot(value: dict[str, Any]) -> HierarchySnapshotType:
    return HierarchySnapshotType(
        project=ProjectSummaryType(**value["project"]),
        manager_id=value.get("manager_id"),
        members=[_member(item) for item in value.get("members", [])],
        pending_approvals=[_approval(item) for item in value.get("pending_approvals", [])],
        brainstorms=[_brainstorm(item) for item in value.get("brainstorms", [])],
    )


def _artifact(item) -> ArtifactType:
    return ArtifactType(
        id=item.id,
        task_id=item.task_id,
        run_id=item.run_id,
        kind=item.kind,
        title=item.title,
        content=item.content,
        metadata=item.metadata_json,
        created_at=item.created_at,
    )


async def graphql_context(
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "db": db,
        "current_user": current_user,
    }


@strawberry.type
class Query:
    @strawberry.field
    async def hierarchy(self, info: Info, project_id: str) -> HierarchySnapshotType:
        service = HierarchyControlPlaneService(info.context["db"])
        snapshot = await service.get_hierarchy_snapshot(info.context["current_user"], project_id)
        return _snapshot(snapshot)

    @strawberry.field
    async def model_profiles(self, info: Info, project_id: str | None = None) -> list[ModelProfileType]:
        service = HierarchyControlPlaneService(info.context["db"])
        rows = await service.list_model_profiles(info.context["current_user"], project_id)
        return [_model_profile(item) for item in rows if item]

    @strawberry.field
    async def runtime_profile(self, info: Info, agent_id: str) -> JSON:
        service = HierarchyControlPlaneService(info.context["db"])
        profile = await service.get_runtime_profile(info.context["current_user"], agent_id)
        return profile.model_dump()

    @strawberry.field
    async def task_artifacts(self, info: Info, project_id: str, task_id: str) -> list[ArtifactType]:
        service = HierarchyControlPlaneService(info.context["db"])
        rows = await service.list_task_artifacts(info.context["current_user"], project_id, task_id)
        return [_artifact(item) for item in rows]


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_team_member(self, info: Info, input: TeamMemberInput) -> MemberType:
        service = HierarchyControlPlaneService(info.context["db"])
        agent = await service.create_team_member(info.context["current_user"], input.__dict__)
        snapshot = await service.get_hierarchy_snapshot(info.context["current_user"], input.project_id)
        member = next(item for item in snapshot["members"] if item["id"] == agent.id)
        return _member(member)

    @strawberry.mutation
    async def update_team_member(self, info: Info, member_id: str, input: TeamMemberInput) -> MemberType:
        service = HierarchyControlPlaneService(info.context["db"])
        agent = await service.update_team_member(info.context["current_user"], member_id, input.__dict__)
        snapshot = await service.get_hierarchy_snapshot(info.context["current_user"], input.project_id)
        member = next(item for item in snapshot["members"] if item["id"] == agent.id)
        return _member(member)

    @strawberry.mutation
    async def remove_team_member(self, info: Info, project_id: str, member_id: str) -> bool:
        service = HierarchyControlPlaneService(info.context["db"])
        return await service.remove_team_member(info.context["current_user"], project_id, member_id)

    @strawberry.mutation
    async def create_hierarchy_task(self, info: Info, input: TaskInput) -> TaskType:
        service = HierarchyControlPlaneService(info.context["db"])
        task = await service.create_task(info.context["current_user"], input.__dict__)
        return _task(service._serialize_task(task, []))

    @strawberry.mutation
    async def assign_task(self, info: Info, project_id: str, task_id: str, member_id: str) -> TaskType:
        service = HierarchyControlPlaneService(info.context["db"])
        task = await service.assign_task(info.context["current_user"], project_id, task_id, member_id)
        return _task(service._serialize_task(task, []))

    @strawberry.mutation
    async def update_task_status(self, info: Info, project_id: str, task_id: str, status: str) -> TaskType:
        service = HierarchyControlPlaneService(info.context["db"])
        task = await service.update_task_status(info.context["current_user"], project_id, task_id, status)
        return _task(service._serialize_task(task, []))

    @strawberry.mutation
    async def request_task_revision(self, info: Info, project_id: str, task_id: str, notes: str) -> TaskType:
        service = HierarchyControlPlaneService(info.context["db"])
        task = await service.request_task_revision(info.context["current_user"], project_id, task_id, notes)
        return _task(service._serialize_task(task, []))

    @strawberry.mutation
    async def approve_task_output(
        self,
        info: Info,
        project_id: str,
        task_id: str,
        summary: str | None = None,
    ) -> TaskType:
        service = HierarchyControlPlaneService(info.context["db"])
        task = await service.approve_task_output(info.context["current_user"], project_id, task_id, summary)
        return _task(service._serialize_task(task, []))

    @strawberry.mutation
    async def launch_task_run(self, info: Info, project_id: str, task_id: str, member_id: str | None = None) -> RunType:
        service = HierarchyControlPlaneService(info.context["db"])
        run = await service.launch_task_run(info.context["current_user"], project_id, task_id, member_id)
        return _run(service._serialize_run(run))

    @strawberry.mutation
    async def start_brainstorm(
        self,
        info: Info,
        project_id: str,
        topic: str,
        participant_ids: list[str],
        task_id: str | None = None,
    ) -> BrainstormType:
        service = HierarchyControlPlaneService(info.context["db"])
        result = await service.start_brainstorm(
            info.context["current_user"],
            project_id,
            topic,
            participant_ids,
            task_id=task_id,
        )
        return _brainstorm(service._serialize_brainstorm(result["brainstorm"]))


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def control_plane_updates(self, project_id: str | None = None) -> AsyncGenerator[ControlPlaneEventType, None]:
        async for event in control_plane_pubsub.subscribe():
            if project_id and event.project_id != project_id:
                continue
            yield ControlPlaneEventType(
                event_type=event.event_type,
                project_id=event.project_id,
                member_id=event.member_id,
                task_id=event.task_id,
                run_id=event.run_id,
                status=event.status,
                payload=event.payload,
                emitted_at=event.emitted_at,
            )


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
    config=StrawberryConfig(auto_camel_case=False),
)
graphql_router = GraphQLRouter(schema, context_getter=graphql_context)
