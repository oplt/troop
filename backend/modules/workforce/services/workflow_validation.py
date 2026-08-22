"""Extended workflow graph validation for publish and test (WF-001B)."""

from __future__ import annotations

from collections import deque
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.services.tool_governance import is_external_mutating_tool
from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService

_GMAIL_TRIGGER_TYPES = frozenset({"gmail_new_message", "gmail.new_message"})
_OUTLOOK_TRIGGER_TYPES = frozenset({"outlook_new_message", "outlook.new_message"})


def _reachable_node_ids(
    *,
    nodes: list[Any],
    edges: list[Any],
    entry_node_id: str | None,
) -> set[str]:
    node_ids = {str(n.get("id")) for n in nodes if isinstance(n, dict) and n.get("id")}
    if not entry_node_id or entry_node_id not in node_ids:
        return set()

    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("from") or edge.get("source") or "")
        target = str(edge.get("to") or edge.get("target") or "")
        if source in adjacency and target in node_ids:
            adjacency[source].append(target)

    seen: set[str] = set()
    queue: deque[str] = deque([str(entry_node_id)])
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        queue.extend(adjacency.get(current, []))
    return seen


class WorkflowValidationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.runtime = WorkflowRuntimeService(db)

    def validate_for_publish(
        self,
        *,
        nodes: list[Any],
        edges: list[Any],
        entry_node_id: str | None,
    ) -> dict[str, Any]:
        errors: list[str] = list(
            self.runtime.validate_graph(nodes=nodes, edges=edges, entry_node_id=entry_node_id)
        )
        warnings: list[str] = []
        infos: list[str] = []
        external_write_nodes: list[dict[str, Any]] = []

        node_ids = {str(n.get("id")) for n in nodes if isinstance(n, dict) and n.get("id")}
        reachable = _reachable_node_ids(nodes=nodes, edges=edges, entry_node_id=entry_node_id)
        unreachable = sorted(node_ids - reachable)
        if unreachable:
            warnings.append(f"unreachable nodes from entry: {', '.join(unreachable)}")

        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "")
            ntype = str(node.get("type") or "")
            config = dict(node.get("config") or {})

            if ntype == "tool":
                tool_slug = str(config.get("tool") or config.get("tool_slug") or "").strip()
                if not tool_slug:
                    errors.append(f"tool node `{node_id}` missing config.tool or config.tool_slug")
                elif is_external_mutating_tool(tool_slug):
                    external_write_nodes.append(
                        {"node_id": node_id, "tool_slug": tool_slug, "type": ntype}
                    )

            if ntype == "trigger":
                trigger_type = str(config.get("trigger_type") or "").strip()
                if (
                    trigger_type in _GMAIL_TRIGGER_TYPES
                    and not str(config.get("connector_installation_id") or "").strip()
                ):
                    errors.append(
                        f"Gmail trigger node `{node_id}` requires connector_installation_id"
                    )
                if (
                    trigger_type in _OUTLOOK_TRIGGER_TYPES
                    and not str(config.get("connector_installation_id") or "").strip()
                ):
                    errors.append(
                        f"Outlook trigger node `{node_id}` requires connector_installation_id"
                    )

            if ntype == "agent" and not str(config.get("agent_id") or "").strip():
                errors.append(f"agent node `{node_id}` missing config.agent_id")

            if (
                ntype == "subworkflow"
                and not str(config.get("workflow_id") or config.get("subworkflow_id") or "").strip()
            ):
                errors.append(f"subworkflow node `{node_id}` missing config.workflow_id")

        if external_write_nodes:
            infos.append(f"{len(external_write_nodes)} node(s) invoke external-mutating tools")

        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "infos": infos,
            "external_write_nodes": external_write_nodes,
        }
