"""Structural diff between two workflow graph snapshots (WF-001B)."""

from __future__ import annotations

import json
from typing import Any

from backend.modules.workforce.services.workflow_graph import (
    canonicalize_workflow_graph,
    workflow_graph_hash,
)


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    extra = {
        key: edge[key] for key in sorted(edge) if key not in {"from", "to", "source", "target"}
    }
    return (
        str(edge.get("from") or edge.get("source") or ""),
        str(edge.get("to") or edge.get("target") or ""),
        json.dumps(extra, sort_keys=True, default=str),
    )


def _node_changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            fields.append(key)
    return fields


def diff_workflow_graphs(
    *,
    left_nodes: list[Any],
    left_edges: list[Any],
    left_entry_node_id: str | None,
    right_nodes: list[Any],
    right_edges: list[Any],
    right_entry_node_id: str | None,
) -> dict[str, Any]:
    """Return a structural diff from ``left`` (baseline) to ``right`` (candidate)."""
    left = canonicalize_workflow_graph(
        nodes=left_nodes,
        edges=left_edges,
        entry_node_id=left_entry_node_id,
    )
    right = canonicalize_workflow_graph(
        nodes=right_nodes,
        edges=right_edges,
        entry_node_id=right_entry_node_id,
    )

    left_nodes_by_id = {str(node["id"]): node for node in left["nodes"]}
    right_nodes_by_id = {str(node["id"]): node for node in right["nodes"]}

    nodes_added = sorted(set(right_nodes_by_id) - set(left_nodes_by_id))
    nodes_removed = sorted(set(left_nodes_by_id) - set(right_nodes_by_id))
    nodes_changed: list[dict[str, Any]] = []
    for node_id in sorted(set(left_nodes_by_id) & set(right_nodes_by_id)):
        before = left_nodes_by_id[node_id]
        after = right_nodes_by_id[node_id]
        if before != after:
            nodes_changed.append(
                {
                    "id": node_id,
                    "changed_fields": _node_changed_fields(before, after),
                }
            )

    left_edge_keys = {_edge_key(edge): edge for edge in left["edges"]}
    right_edge_keys = {_edge_key(edge): edge for edge in right["edges"]}

    edges_added = [
        right_edge_keys[key]
        for key in sorted(set(right_edge_keys) - set(left_edge_keys), key=lambda item: item[:2])
    ]
    edges_removed = [
        left_edge_keys[key]
        for key in sorted(set(left_edge_keys) - set(right_edge_keys), key=lambda item: item[:2])
    ]

    left_hash = workflow_graph_hash(left)
    right_hash = workflow_graph_hash(right)

    return {
        "nodes_added": nodes_added,
        "nodes_removed": nodes_removed,
        "nodes_changed": nodes_changed,
        "edges_added": edges_added,
        "edges_removed": edges_removed,
        "entry_node_changed": left.get("entry_node_id") != right.get("entry_node_id"),
        "entry_node_before": left.get("entry_node_id"),
        "entry_node_after": right.get("entry_node_id"),
        "graph_hash_before": left_hash,
        "graph_hash_after": right_hash,
        "graph_changed": left_hash != right_hash,
        "summary": {
            "nodes_added": len(nodes_added),
            "nodes_removed": len(nodes_removed),
            "nodes_changed": len(nodes_changed),
            "edges_added": len(edges_added),
            "edges_removed": len(edges_removed),
        },
    }
