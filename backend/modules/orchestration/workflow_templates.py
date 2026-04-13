"""Curated workflow templates (V2 roadmap helpers) — static catalog until graph authoring ships."""

from __future__ import annotations

from typing import Any

BUILTIN_WORKFLOW_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "feature_delivery",
        "name": "Feature delivery lane",
        "description": "Backlog → implementation → review → merge, with optional brainstorm gate before coding.",
        "suggested_execution": {"autonomy_level": "semi-autonomous", "routing_mode": "balanced"},
    },
    {
        "id": "incident_response",
        "name": "Incident response",
        "description": "Triage → mitigation → root-cause brainstorm → follow-up tasks and ADR capture.",
        "suggested_execution": {"autonomy_level": "assisted", "routing_mode": "sla_priority"},
    },
    {
        "id": "security_review",
        "name": "Security-sensitive change",
        "description": "Assisted mode, reviewer on every run, merge-blocked agents for PR tooling.",
        "suggested_execution": {"autonomy_level": "assisted", "routing_mode": "balanced"},
    },
    {
        "id": "docs_only",
        "name": "Documentation refresh",
        "description": "Low-risk autonomous drafting with human publish gate on external posts.",
        "suggested_execution": {"autonomy_level": "autonomous", "routing_mode": "throughput"},
    },
]
