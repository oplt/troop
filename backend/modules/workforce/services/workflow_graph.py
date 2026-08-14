"""Canonical workflow graph normalization and hashing (WF-001A)."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


def _sorted_node(node: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(node)
    config = normalized.get("config")
    if isinstance(config, dict):
        normalized["config"] = dict(sorted(config.items()))
    return normalized


def _sorted_edge(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "from": str(edge.get("from") or edge.get("source") or ""),
        "to": str(edge.get("to") or edge.get("target") or ""),
        **{
            key: edge[key]
            for key in sorted(edge)
            if key not in {"from", "to", "source", "target"}
        },
    }


def canonicalize_workflow_graph(
    *,
    nodes: list[Any],
    edges: list[Any],
    entry_node_id: str | None,
) -> dict[str, Any]:
    """Return a deterministic graph payload suitable for hashing and storage."""
    normalized_nodes = [
        _sorted_node(node)
        for node in nodes
        if isinstance(node, dict) and node.get("id")
    ]
    normalized_nodes.sort(key=lambda item: str(item.get("id")))

    normalized_edges = [
        _sorted_edge(edge)
        for edge in edges
        if isinstance(edge, dict) and (edge.get("from") or edge.get("source"))
    ]
    normalized_edges.sort(
        key=lambda item: (str(item.get("from")), str(item.get("to")))
    )

    entry = str(entry_node_id or "").strip() or None
    if entry is None and normalized_nodes:
        entry = str(normalized_nodes[0].get("id"))

    return {
        "nodes": normalized_nodes,
        "edges": normalized_edges,
        "entry_node_id": entry,
    }


def workflow_graph_hash(graph: dict[str, Any]) -> str:
    payload = json.dumps(graph, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def apply_canonical_graph_to_version(
    version: Any,
    *,
    nodes: list[Any],
    edges: list[Any],
    entry_node_id: str | None,
) -> dict[str, Any]:
    graph = canonicalize_workflow_graph(
        nodes=nodes,
        edges=edges,
        entry_node_id=entry_node_id,
    )
    version.nodes_json = graph["nodes"]
    version.edges_json = graph["edges"]
    version.entry_node_id = graph["entry_node_id"]
    if hasattr(version, "graph_hash"):
        version.graph_hash = workflow_graph_hash(graph)
    return graph
