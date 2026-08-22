"""Draft vs published workflow version lifecycle (WF-001A)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.repository import AuditRepository
from backend.modules.workforce.models import WorkflowDefinition, WorkflowVersion
from backend.modules.workforce.services.workflow_graph import (
    apply_canonical_graph_to_version,
    workflow_graph_hash,
)
from backend.modules.workforce.services.workflow_graph_diff import diff_workflow_graphs
from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService
from backend.modules.workforce.services.workflow_validation import WorkflowValidationService

DRAFT_VERSION_NUMBER = 0


class WorkflowVersionImmutableError(ValueError):
    """Raised when a caller attempts to mutate a published workflow version."""


class WorkflowVersionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.runtime = WorkflowRuntimeService(db)

    @staticmethod
    def assert_mutable(version: WorkflowVersion) -> None:
        if version.is_published:
            raise WorkflowVersionImmutableError(
                f"Workflow version {version.id!r} is published and immutable"
            )

    async def get_version(self, version_id: str | None) -> WorkflowVersion | None:
        if not version_id:
            return None
        return await self.db.get(WorkflowVersion, version_id)

    async def get_draft(self, definition: WorkflowDefinition) -> WorkflowVersion | None:
        return await self.get_version(definition.draft_version_id)

    async def get_published(self, definition: WorkflowDefinition) -> WorkflowVersion | None:
        return await self.get_version(definition.published_version_id)

    async def _next_published_version_number(self, workflow_id: str) -> int:
        result = await self.db.execute(
            select(func.max(WorkflowVersion.version_number)).where(
                WorkflowVersion.workflow_id == workflow_id,
                WorkflowVersion.is_published.is_(True),
            )
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1

    async def ensure_draft(
        self,
        definition: WorkflowDefinition,
        *,
        created_by: str | None,
        nodes: list[Any] | None = None,
        edges: list[Any] | None = None,
        entry_node_id: str | None = None,
    ) -> WorkflowVersion:
        draft = await self.get_draft(definition)
        if draft is not None:
            if nodes is not None or edges is not None or entry_node_id is not None:
                await self.update_draft(
                    definition,
                    nodes=list(nodes or draft.nodes_json or []),
                    edges=list(edges or draft.edges_json or []),
                    entry_node_id=entry_node_id
                    if entry_node_id is not None
                    else draft.entry_node_id,
                    actor_user_id=created_by,
                )
                draft = await self.get_draft(definition)
            assert draft is not None
            return draft

        draft = WorkflowVersion(
            id=str(uuid4()),
            workflow_id=definition.id,
            version_number=DRAFT_VERSION_NUMBER,
            nodes_json=list(nodes or []),
            edges_json=list(edges or []),
            entry_node_id=entry_node_id,
            metadata_json={"kind": "draft"},
            is_published=False,
            created_by=created_by,
        )
        if draft.nodes_json:
            apply_canonical_graph_to_version(
                draft,
                nodes=draft.nodes_json,
                edges=draft.edges_json,
                entry_node_id=draft.entry_node_id,
            )
        self.db.add(draft)
        await self.db.flush()
        definition.draft_version_id = draft.id
        definition.current_version_id = draft.id
        return draft

    async def update_draft(
        self,
        definition: WorkflowDefinition,
        *,
        nodes: list[Any],
        edges: list[Any],
        entry_node_id: str | None,
        actor_user_id: str | None = None,
    ) -> WorkflowVersion:
        draft = await self.ensure_draft(definition, created_by=actor_user_id)
        self.assert_mutable(draft)
        errors = self.runtime.validate_graph(
            nodes=nodes,
            edges=edges,
            entry_node_id=entry_node_id,
        )
        if errors:
            raise ValueError({"errors": errors})
        apply_canonical_graph_to_version(
            draft,
            nodes=nodes,
            edges=edges,
            entry_node_id=entry_node_id,
        )
        draft.created_by = actor_user_id or draft.created_by
        await self.db.flush()
        definition.draft_version_id = draft.id
        definition.current_version_id = draft.id
        if definition.status != "active":
            definition.status = "draft"
        return draft

    async def validate_draft(self, definition: WorkflowDefinition) -> dict[str, Any]:
        draft = await self.get_draft(definition)
        if draft is None:
            return {
                "valid": False,
                "errors": ["workflow has no draft"],
                "warnings": [],
                "infos": [],
                "external_write_nodes": [],
            }
        return WorkflowValidationService(self.db).validate_for_publish(
            nodes=list(draft.nodes_json or []),
            edges=list(draft.edges_json or []),
            entry_node_id=draft.entry_node_id,
        )

    async def diff_draft_vs_published(self, definition: WorkflowDefinition) -> dict[str, Any]:
        draft = await self.get_draft(definition)
        published = await self.get_published(definition)
        if draft is None:
            raise ValueError("workflow has no draft")
        if published is None:
            return diff_workflow_graphs(
                left_nodes=[],
                left_edges=[],
                left_entry_node_id=None,
                right_nodes=list(draft.nodes_json or []),
                right_edges=list(draft.edges_json or []),
                right_entry_node_id=draft.entry_node_id,
            )
        return diff_workflow_graphs(
            left_nodes=list(published.nodes_json or []),
            left_edges=list(published.edges_json or []),
            left_entry_node_id=published.entry_node_id,
            right_nodes=list(draft.nodes_json or []),
            right_edges=list(draft.edges_json or []),
            right_entry_node_id=draft.entry_node_id,
        )

    async def list_published_versions(self, workflow_id: str) -> list[WorkflowVersion]:
        result = await self.db.execute(
            select(WorkflowVersion)
            .where(
                WorkflowVersion.workflow_id == workflow_id,
                WorkflowVersion.is_published.is_(True),
            )
            .order_by(WorkflowVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def rollback_to_version(
        self,
        definition: WorkflowDefinition,
        *,
        target_version_id: str,
        actor_user_id: str | None,
    ) -> WorkflowVersion:
        target = await self.get_version(target_version_id)
        if target is None or target.workflow_id != definition.id:
            raise ValueError("workflow version not found")
        if not target.is_published:
            raise ValueError("rollback target must be a published version")

        previous_version_id = definition.published_version_id
        definition.published_version_id = target.id
        definition.status = "active"
        await self.db.flush()

        await AuditRepository(self.db).log(
            "workflow.rollback",
            user_id=actor_user_id,
            resource_type="workflow",
            resource_id=definition.id,
            metadata={
                "workflow_id": definition.id,
                "previous_published_version_id": previous_version_id,
                "target_version_id": target.id,
                "target_version_number": target.version_number,
            },
        )
        return target

    async def publish_draft(
        self,
        definition: WorkflowDefinition,
        *,
        actor_user_id: str | None,
        nodes: list[Any] | None = None,
        edges: list[Any] | None = None,
        entry_node_id: str | None = None,
    ) -> WorkflowVersion:
        draft = await self.ensure_draft(definition, created_by=actor_user_id)
        graph_nodes = list(nodes if nodes is not None else (draft.nodes_json or []))
        graph_edges = list(edges if edges is not None else (draft.edges_json or []))
        graph_entry = entry_node_id if entry_node_id is not None else draft.entry_node_id
        validation = WorkflowValidationService(self.db).validate_for_publish(
            nodes=graph_nodes,
            edges=graph_edges,
            entry_node_id=graph_entry,
        )
        if validation["errors"]:
            raise ValueError({"errors": validation["errors"], "validation": validation})

        graph = apply_canonical_graph_to_version(
            draft,
            nodes=graph_nodes,
            edges=graph_edges,
            entry_node_id=graph_entry,
        )
        graph_hash = workflow_graph_hash(graph)
        version_number = await self._next_published_version_number(definition.id)
        published = WorkflowVersion(
            id=str(uuid4()),
            workflow_id=definition.id,
            version_number=version_number,
            nodes_json=graph["nodes"],
            edges_json=graph["edges"],
            entry_node_id=graph["entry_node_id"],
            metadata_json={"kind": "published", "source_draft_id": draft.id},
            graph_hash=graph_hash,
            is_published=True,
            created_by=actor_user_id,
        )
        self.db.add(published)
        await self.db.flush()

        definition.published_version_id = published.id
        definition.status = "active"
        definition.draft_version_id = draft.id
        definition.current_version_id = draft.id
        if actor_user_id:
            from backend.modules.platform.activation_hooks import record_activation_for_owner

            await record_activation_for_owner(
                self.db,
                actor_user_id,
                "first_published_workflow",
                at=datetime.now(UTC),
                resource_type="workflow_definition",
                resource_id=definition.id,
                metadata={"slug": definition.slug, "version_id": published.id},
            )
        return published

    async def resolve_run_version(self, definition: WorkflowDefinition) -> WorkflowVersion:
        version = await self.get_published(definition)
        if version is None:
            raise ValueError("workflow has no published version")
        if not version.is_published:
            raise ValueError("published_version_id must reference a published version")
        return version
