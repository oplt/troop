"""Workflow environment deployments: promote, bindings, rollback (ENV-001)."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.audit.repository import AuditRepository
from backend.modules.workforce.models import (
    ConnectorInstallation,
    WorkflowDefinition,
    WorkflowEnvironmentDeployment,
    WorkflowEnvironmentDeploymentEvent,
    WorkflowVersion,
)
from backend.modules.workforce.services.workflow_graph_diff import diff_workflow_graphs
from backend.modules.workforce.services.workflow_version_service import WorkflowVersionService

WORKFLOW_ENVIRONMENTS: tuple[str, ...] = ("dev", "staging", "prod")

_BINDING_KEYS = (
    "connector_installation_id",
    "approval_connector_installation_id",
)


def normalize_environment(value: str | None) -> str:
    env = str(value or "dev").strip().lower()
    if env not in WORKFLOW_ENVIRONMENTS:
        raise ValueError(f"invalid environment `{env}`")
    return env


def installation_allowed_for_environment(
    installation_environment: str | None,
    target_environment: str,
) -> bool:
    inst = str(installation_environment or "dev").strip().lower()
    target = normalize_environment(target_environment)
    if target == "prod":
        return inst == "prod"
    if target == "staging":
        return inst in {"staging", "prod"}
    return True


def extract_bindings_from_graph(nodes: list[Any]) -> dict[str, dict[str, str]]:
    bindings: dict[str, dict[str, str]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        config = dict(node.get("config") or {})
        node_bindings: dict[str, str] = {}
        for key in _BINDING_KEYS:
            value = str(config.get(key) or "").strip()
            if value:
                node_bindings[key] = value
        if node_bindings:
            bindings[node_id] = node_bindings
    return bindings


def apply_bindings_to_graph(
    nodes: list[Any],
    bindings: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    overlay = dict(bindings or {})
    resolved: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        copy = deepcopy(node)
        node_id = str(copy.get("id") or "")
        config = dict(copy.get("config") or {})
        node_overlay = overlay.get(node_id)
        if isinstance(node_overlay, dict):
            for key in _BINDING_KEYS:
                value = str(node_overlay.get(key) or "").strip()
                if value:
                    config[key] = value
        elif isinstance(node_overlay, str) and node_overlay.strip():
            config["connector_installation_id"] = node_overlay.strip()
        copy["config"] = config
        resolved.append(copy)
    return resolved


def diff_bindings(
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    left_map = dict(left or {})
    right_map = dict(right or {})
    node_ids = sorted(set(left_map) | set(right_map))
    changed: list[dict[str, Any]] = []
    added: list[str] = []
    removed: list[str] = []
    for node_id in node_ids:
        if node_id not in left_map:
            added.append(node_id)
            continue
        if node_id not in right_map:
            removed.append(node_id)
            continue
        if left_map[node_id] != right_map[node_id]:
            changed.append(
                {"node_id": node_id, "before": left_map[node_id], "after": right_map[node_id]}
            )
    return {
        "bindings_added": added,
        "bindings_removed": removed,
        "bindings_changed": changed,
        "bindings_changed_count": len(changed) + len(added) + len(removed),
    }


class WorkflowEnvironmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.version_service = WorkflowVersionService(db)

    async def list_environment_summaries(
        self,
        definition: WorkflowDefinition,
    ) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(WorkflowEnvironmentDeployment).where(
                WorkflowEnvironmentDeployment.workflow_id == definition.id
            )
        )
        by_env = {row.environment: row for row in result.scalars().all()}
        summaries: list[dict[str, Any]] = []
        for environment in WORKFLOW_ENVIRONMENTS:
            deployment = by_env.get(environment)
            version = (
                await self.version_service.get_version(deployment.workflow_version_id)
                if deployment
                else None
            )
            summaries.append(
                {
                    "environment": environment,
                    "deployed": deployment is not None,
                    "deployment_id": deployment.id if deployment else None,
                    "workflow_version_id": deployment.workflow_version_id if deployment else None,
                    "version_number": version.version_number if version else None,
                    "graph_hash": version.graph_hash if version else None,
                    "deployed_at": deployment.deployed_at if deployment else None,
                    "connection_bindings": dict(deployment.connection_bindings_json or {})
                    if deployment
                    else {},
                }
            )
        return summaries

    async def get_deployment(
        self,
        definition: WorkflowDefinition,
        environment: str,
    ) -> WorkflowEnvironmentDeployment | None:
        env = normalize_environment(environment)
        result = await self.db.execute(
            select(WorkflowEnvironmentDeployment).where(
                WorkflowEnvironmentDeployment.workflow_id == definition.id,
                WorkflowEnvironmentDeployment.environment == env,
            )
        )
        return result.scalar_one_or_none()

    async def resolve_version_for_environment(
        self,
        definition: WorkflowDefinition,
        environment: str,
    ) -> tuple[WorkflowVersion, WorkflowEnvironmentDeployment | None]:
        env = normalize_environment(environment)
        deployment = await self.get_deployment(definition, env)
        if deployment is not None:
            version = await self.version_service.get_version(deployment.workflow_version_id)
            if version is None:
                raise ValueError(f"{env} deployment references missing workflow version")
            if not version.is_published:
                raise ValueError(f"{env} deployment must reference a published version")
            return version, deployment

        if env == "dev" and definition.published_version_id:
            version = await self.version_service.get_published(definition)
            if version is not None:
                return version, None

        raise ValueError(f"workflow has no deployment for `{env}`")

    async def resolved_graph_for_environment(
        self,
        definition: WorkflowDefinition,
        environment: str,
    ) -> tuple[WorkflowVersion, list[dict[str, Any]], list[Any], str | None]:
        version, deployment = await self.resolve_version_for_environment(definition, environment)
        nodes = list(version.nodes_json or [])
        if deployment is not None:
            nodes = apply_bindings_to_graph(nodes, deployment.connection_bindings_json)
        elif normalize_environment(environment) == "dev":
            nodes = apply_bindings_to_graph(nodes, extract_bindings_from_graph(nodes))
        return version, nodes, list(version.edges_json or []), version.entry_node_id

    async def validate_bindings(
        self,
        *,
        owner_id: str,
        environment: str,
        bindings: dict[str, Any],
        nodes: list[Any],
    ) -> dict[str, Any]:
        env = normalize_environment(environment)
        errors: list[str] = []
        warnings: list[str] = []

        installation_ids: set[str] = set()
        for node_bindings in bindings.values():
            if isinstance(node_bindings, dict):
                for key in _BINDING_KEYS:
                    value = str(node_bindings.get(key) or "").strip()
                    if value:
                        installation_ids.add(value)
            elif isinstance(node_bindings, str) and node_bindings.strip():
                installation_ids.add(node_bindings.strip())

        installations: dict[str, ConnectorInstallation] = {}
        if installation_ids:
            result = await self.db.execute(
                select(ConnectorInstallation).where(
                    ConnectorInstallation.id.in_(installation_ids),
                    ConnectorInstallation.owner_id == owner_id,
                )
            )
            installations = {row.id: row for row in result.scalars().all()}

        for installation_id in installation_ids:
            installation = installations.get(installation_id)
            if installation is None:
                errors.append(f"connector installation `{installation_id}` not found")
                continue
            if not installation_allowed_for_environment(installation.environment, env):
                errors.append(
                    f"installation `{installation_id}` ({installation.environment or 'dev'}) "
                    f"cannot be used in `{env}`"
                )

        required_nodes = [
            str(node.get("id"))
            for node in nodes
            if isinstance(node, dict)
            and str(node.get("type") or "") in {"trigger", "tool"}
            and str(node.get("id") or "")
        ]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            ntype = str(node.get("type") or "")
            if ntype not in {"trigger", "tool"}:
                continue
            node_id = str(node.get("id") or "")
            node_bindings = bindings.get(node_id)
            has_binding = False
            if isinstance(node_bindings, dict):
                has_binding = any(
                    str(node_bindings.get(key) or "").strip() for key in _BINDING_KEYS
                )
            elif isinstance(node_bindings, str):
                has_binding = bool(node_bindings.strip())
            inline = dict(node.get("config") or {})
            if not has_binding and not any(
                str(inline.get(key) or "").strip() for key in _BINDING_KEYS
            ):
                if ntype == "trigger":
                    trigger_type = str(inline.get("trigger_type") or inline.get("event_type") or "")
                    if trigger_type not in {"manual", "schedule", ""}:
                        warnings.append(f"trigger node `{node_id}` has no environment binding")
                elif ntype == "tool":
                    warnings.append(f"tool node `{node_id}` has no environment binding")

        if required_nodes and not bindings and errors:
            pass

        return {"valid": not errors, "errors": errors, "warnings": warnings}

    async def promote(
        self,
        definition: WorkflowDefinition,
        *,
        environment: str,
        version_id: str,
        connection_bindings: dict[str, Any] | None,
        actor_user_id: str | None,
    ) -> WorkflowEnvironmentDeployment:
        env = normalize_environment(environment)
        version = await self.version_service.get_version(version_id)
        if version is None or version.workflow_id != definition.id:
            raise ValueError("workflow version not found")
        if not version.is_published:
            raise ValueError("only published versions can be promoted to an environment")

        bindings = dict(
            connection_bindings or extract_bindings_from_graph(list(version.nodes_json or []))
        )
        validation = await self.validate_bindings(
            owner_id=definition.owner_id,
            environment=env,
            bindings=bindings,
            nodes=list(version.nodes_json or []),
        )
        if validation["errors"]:
            raise ValueError({"errors": validation["errors"], "validation": validation})

        existing = await self.get_deployment(definition, env)
        previous_version_id = existing.workflow_version_id if existing else None
        previous_bindings = dict(existing.connection_bindings_json or {}) if existing else None

        if existing is None:
            deployment = WorkflowEnvironmentDeployment(
                id=str(uuid4()),
                workflow_id=definition.id,
                environment=env,
                workflow_version_id=version.id,
                connection_bindings_json=bindings,
                deployed_by=actor_user_id,
                deployed_at=datetime.now(UTC),
                metadata_json={"action": "promote"},
            )
            self.db.add(deployment)
        else:
            deployment = existing
            deployment.workflow_version_id = version.id
            deployment.connection_bindings_json = bindings
            deployment.deployed_by = actor_user_id
            deployment.deployed_at = datetime.now(UTC)
            deployment.metadata_json = {
                **(deployment.metadata_json or {}),
                "action": "promote",
            }

        event = WorkflowEnvironmentDeploymentEvent(
            id=str(uuid4()),
            workflow_id=definition.id,
            environment=env,
            action="promote",
            workflow_version_id=version.id,
            connection_bindings_json=bindings,
            previous_version_id=previous_version_id,
            previous_bindings_json=previous_bindings,
            actor_user_id=actor_user_id,
            metadata_json={},
        )
        self.db.add(event)

        if env == "dev":
            definition.published_version_id = version.id
            definition.status = "active"

        await self.db.flush()

        await AuditRepository(self.db).log(
            "workflow.promote",
            user_id=actor_user_id,
            resource_type="workflow",
            resource_id=definition.id,
            metadata={
                "workflow_id": definition.id,
                "environment": env,
                "version_id": version.id,
                "version_number": version.version_number,
                "bindings_count": len(bindings),
            },
        )
        return deployment

    async def rollback(
        self,
        definition: WorkflowDefinition,
        *,
        environment: str,
        actor_user_id: str | None,
    ) -> WorkflowEnvironmentDeployment:
        env = normalize_environment(environment)
        result = await self.db.execute(
            select(WorkflowEnvironmentDeploymentEvent)
            .where(
                WorkflowEnvironmentDeploymentEvent.workflow_id == definition.id,
                WorkflowEnvironmentDeploymentEvent.environment == env,
                WorkflowEnvironmentDeploymentEvent.action == "promote",
            )
            .order_by(WorkflowEnvironmentDeploymentEvent.created_at.desc())
            .limit(2)
        )
        events = list(result.scalars().all())
        if len(events) < 2:
            raise ValueError("no previous deployment to roll back to")

        previous_event = events[1]
        deployment = await self.get_deployment(definition, env)
        if deployment is None:
            raise ValueError("no active deployment")

        previous_version_id = deployment.workflow_version_id
        previous_bindings = dict(deployment.connection_bindings_json or {})

        deployment.workflow_version_id = previous_event.workflow_version_id
        deployment.connection_bindings_json = dict(previous_event.connection_bindings_json or {})
        deployment.deployed_by = actor_user_id
        deployment.deployed_at = datetime.now(UTC)

        rollback_event = WorkflowEnvironmentDeploymentEvent(
            id=str(uuid4()),
            workflow_id=definition.id,
            environment=env,
            action="rollback",
            workflow_version_id=previous_event.workflow_version_id,
            connection_bindings_json=dict(previous_event.connection_bindings_json or {}),
            previous_version_id=previous_version_id,
            previous_bindings_json=previous_bindings,
            actor_user_id=actor_user_id,
            metadata_json={"restored_from_event_id": previous_event.id},
        )
        self.db.add(rollback_event)
        await self.db.flush()

        await AuditRepository(self.db).log(
            "workflow.rollback_environment",
            user_id=actor_user_id,
            resource_type="workflow",
            resource_id=definition.id,
            metadata={
                "workflow_id": definition.id,
                "environment": env,
                "from_version_id": previous_version_id,
                "to_version_id": previous_event.workflow_version_id,
            },
        )
        return deployment

    async def diff_promotion(
        self,
        definition: WorkflowDefinition,
        *,
        environment: str,
        candidate_version_id: str,
        candidate_bindings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        env = normalize_environment(environment)
        candidate = await self.version_service.get_version(candidate_version_id)
        if candidate is None or candidate.workflow_id != definition.id:
            raise ValueError("workflow version not found")

        current_deployment = await self.get_deployment(definition, env)
        current_version = (
            await self.version_service.get_version(current_deployment.workflow_version_id)
            if current_deployment
            else await self.version_service.get_published(definition)
        )

        left_nodes = list(current_version.nodes_json or []) if current_version else []
        left_edges = list(current_version.edges_json or []) if current_version else []
        left_entry = current_version.entry_node_id if current_version else None
        left_bindings = (
            dict(current_deployment.connection_bindings_json or {})
            if current_deployment
            else extract_bindings_from_graph(left_nodes)
        )

        candidate_binding_map = dict(
            candidate_bindings or extract_bindings_from_graph(list(candidate.nodes_json or []))
        )
        graph_diff = diff_workflow_graphs(
            left_nodes=left_nodes,
            left_edges=left_edges,
            left_entry_node_id=left_entry,
            right_nodes=list(candidate.nodes_json or []),
            right_edges=list(candidate.edges_json or []),
            right_entry_node_id=candidate.entry_node_id,
        )
        binding_diff = diff_bindings(left_bindings, candidate_binding_map)
        return {
            **graph_diff,
            **binding_diff,
            "environment": env,
            "current_version_id": current_version.id if current_version else None,
            "candidate_version_id": candidate.id,
        }

    async def list_history(
        self,
        definition: WorkflowDefinition,
        environment: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        env = normalize_environment(environment)
        result = await self.db.execute(
            select(WorkflowEnvironmentDeploymentEvent)
            .where(
                WorkflowEnvironmentDeploymentEvent.workflow_id == definition.id,
                WorkflowEnvironmentDeploymentEvent.environment == env,
            )
            .order_by(WorkflowEnvironmentDeploymentEvent.created_at.desc())
            .limit(limit)
        )
        events = list(result.scalars().all())
        return [
            {
                "id": event.id,
                "action": event.action,
                "workflow_version_id": event.workflow_version_id,
                "connection_bindings": dict(event.connection_bindings_json or {}),
                "previous_version_id": event.previous_version_id,
                "actor_user_id": event.actor_user_id,
                "created_at": event.created_at,
            }
            for event in events
        ]
