"""Manifest-aware gap analysis for NL workflow scaffolds (PROD-002)."""

from __future__ import annotations

from collections import deque
from typing import Any

from backend.modules.workforce.connectors.manifest import ConnectorManifest, OperationKind
from backend.modules.workforce.services.tool_governance import (
    is_external_mutating_tool,
)
from backend.modules.workforce.services.workflow_validation import WorkflowValidationService


def _operation_slug_for_trigger_type(trigger_type: str) -> str:
    normalized = trigger_type.strip()
    if normalized in {"gmail_new_message", "gmail.new_message"}:
        return "gmail.new_message"
    if normalized in {"outlook_new_message", "outlook.new_message"}:
        return "outlook.new_message"
    return normalized


def _trigger_type_for_operation_slug(slug: str) -> str:
    if slug == "gmail.new_message":
        return "gmail_new_message"
    if slug == "outlook.new_message":
        return "outlook_new_message"
    return slug.replace(".", "_")


def _provider_for_operation(
    operation_slug: str,
    manifests_by_provider: dict[str, ConnectorManifest],
) -> str | None:
    for provider_slug, manifest in manifests_by_provider.items():
        if manifest.get_operation(operation_slug) is not None:
            return provider_slug
    return None


def _downstream_node_ids(
    *,
    start_id: str,
    edges: list[Any],
    node_ids: set[str],
) -> set[str]:
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("from") or edge.get("source") or "")
        target = str(edge.get("to") or edge.get("target") or "")
        if source in adjacency and target in node_ids:
            adjacency[source].append(target)

    seen: set[str] = set()
    queue: deque[str] = deque([start_id])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(adjacency.get(current, []))
    return seen


class WorkflowScaffoldValidator:
    def __init__(
        self,
        *,
        allowed_operation_slugs: set[str],
        manifests_by_provider: dict[str, ConnectorManifest],
        installations_by_provider: dict[str, dict[str, Any]],
    ) -> None:
        self.allowed_operation_slugs = allowed_operation_slugs
        self.manifests_by_provider = manifests_by_provider
        self.installations_by_provider = installations_by_provider

    def analyze_gaps(
        self,
        *,
        nodes: list[Any],
        edges: list[Any],
        entry_node_id: str | None,
    ) -> list[dict[str, Any]]:
        gaps: list[dict[str, Any]] = []
        node_ids = {str(n.get("id")) for n in nodes if isinstance(n, dict) and n.get("id")}
        approval_node_ids = {
            str(n.get("id"))
            for n in nodes
            if isinstance(n, dict) and str(n.get("type") or "") == "approval" and n.get("id")
        }

        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "")
            ntype = str(node.get("type") or "")
            config = dict(node.get("config") or {})

            if ntype == "agent" and not str(config.get("agent_id") or "").strip():
                gaps.append(
                    {
                        "kind": "missing_agent",
                        "node_id": node_id,
                        "provider_slug": None,
                        "operation_slug": None,
                        "message": f"Agent node `{node_id}` needs an assigned agent before publish.",
                        "remediation": "Select an agent in the node inspector or create one under Team.",
                    }
                )

            operation_slug = ""
            provider_slug: str | None = None
            manifest_op = None

            if ntype == "trigger":
                trigger_type = str(
                    config.get("trigger_type") or config.get("event_type") or ""
                ).strip()
                if trigger_type in {"manual", "schedule", ""}:
                    continue
                operation_slug = _operation_slug_for_trigger_type(trigger_type)
                provider_slug = _provider_for_operation(operation_slug, self.manifests_by_provider)
                if provider_slug:
                    manifest_op = self.manifests_by_provider[provider_slug].get_operation(
                        operation_slug
                    )
            elif ntype == "tool":
                operation_slug = str(
                    config.get("tool") or config.get("tool_slug") or config.get("operation") or ""
                ).strip()
                provider_slug = _provider_for_operation(operation_slug, self.manifests_by_provider)
                if provider_slug:
                    manifest_op = self.manifests_by_provider[provider_slug].get_operation(
                        operation_slug
                    )

            if not operation_slug or ntype not in {"trigger", "tool"}:
                continue

            if operation_slug not in self.allowed_operation_slugs:
                gaps.append(
                    {
                        "kind": "unavailable_operation",
                        "node_id": node_id,
                        "provider_slug": provider_slug,
                        "operation_slug": operation_slug,
                        "message": (
                            f"Operation `{operation_slug}` is not available from installed connectors."
                        ),
                        "remediation": "Connect the required integration or replace this step.",
                    }
                )
                continue

            installation_id = str(config.get("connector_installation_id") or "").strip()
            installation = (
                self.installations_by_provider.get(provider_slug or "") if provider_slug else None
            )
            if not installation_id:
                gaps.append(
                    {
                        "kind": "missing_connection",
                        "node_id": node_id,
                        "provider_slug": provider_slug,
                        "operation_slug": operation_slug,
                        "message": (
                            f"Node `{node_id}` requires a {provider_slug or 'connector'} connection."
                        ),
                        "remediation": (
                            f"Connect {provider_slug} under Integrations and select the installation."
                            if provider_slug
                            else "Select a connector installation for this node."
                        ),
                    }
                )
            elif installation and installation.get("id") != installation_id:
                gaps.append(
                    {
                        "kind": "missing_connection",
                        "node_id": node_id,
                        "provider_slug": provider_slug,
                        "operation_slug": operation_slug,
                        "message": f"Node `{node_id}` references an unknown connector installation.",
                        "remediation": "Pick one of your active connector installations.",
                    }
                )

            required_scopes = list(manifest_op.required_scopes if manifest_op else [])
            granted = set((installation or {}).get("granted_scopes") or [])
            if required_scopes and installation and granted:
                missing = [scope for scope in required_scopes if scope not in granted]
                if missing:
                    gaps.append(
                        {
                            "kind": "missing_scope",
                            "node_id": node_id,
                            "provider_slug": provider_slug,
                            "operation_slug": operation_slug,
                            "message": (
                                f"Node `{node_id}` needs additional OAuth scopes: {', '.join(missing)}"
                            ),
                            "remediation": (
                                f"Reconnect {provider_slug} and grant the missing scopes."
                                if provider_slug
                                else "Reconnect the integration with required scopes."
                            ),
                        }
                    )

            requires_approval = bool(manifest_op and manifest_op.requires_approval)
            if ntype == "tool" and (requires_approval or is_external_mutating_tool(operation_slug)):
                downstream = _downstream_node_ids(
                    start_id=node_id,
                    edges=edges,
                    node_ids=node_ids,
                )
                if not downstream.intersection(approval_node_ids):
                    gaps.append(
                        {
                            "kind": "missing_approval_step",
                            "node_id": node_id,
                            "provider_slug": provider_slug,
                            "operation_slug": operation_slug,
                            "message": (
                                f"Mutating tool `{operation_slug}` should be followed by a human approval step."
                            ),
                            "remediation": "Add an approval node after this action before publish.",
                        }
                    )

        return gaps

    def validate_graph(
        self,
        *,
        nodes: list[Any],
        edges: list[Any],
        entry_node_id: str | None,
        db: Any,
    ) -> dict[str, Any]:
        report = WorkflowValidationService(db).validate_for_publish(
            nodes=nodes,
            edges=edges,
            entry_node_id=entry_node_id,
        )
        gaps = self.analyze_gaps(nodes=nodes, edges=edges, entry_node_id=entry_node_id)
        return {**report, "gaps": gaps}


def trigger_type_for_operation_slug(slug: str) -> str:
    return _trigger_type_for_operation_slug(slug)


def operation_requires_connector(operation_kind: OperationKind) -> bool:
    return operation_kind in {OperationKind.TRIGGER, OperationKind.ACTION}
