"""Memory namespace taxonomy.

Enforced shape: `<scope>/<id>/<sub>...`
where scope ∈ {company, project, task, agent, global}.

Examples:
    company/<company_id>/policy/security
    project/<project_id>/decision/auth
    task/<task_id>/working/findings
    agent/<agent_id>/preferences/tone
    agent/<agent_id>/procedural/code-review
    global/glossary/payments
"""

from __future__ import annotations

import re
from typing import Final

from fastapi import HTTPException, status

NAMESPACE_SCOPES: Final[tuple[str, ...]] = (
    "company",
    "project",
    "task",
    "agent",
    "user",
    "global",
)

AGENT_SUB_PREFIXES: Final[tuple[str, ...]] = ("preferences", "procedural", "memory")

_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")
_NAMESPACE_RE = re.compile(r"^[a-z0-9][a-z0-9_\-/]*$")


def parse_namespace(namespace: str) -> tuple[str, str | None, list[str]]:
    """Return (scope, scoped_id, remainder_segments). Raises if invalid."""
    if not namespace or len(namespace) > 512:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="namespace empty or too long"
        )
    if not _NAMESPACE_RE.match(namespace):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="namespace must match [a-z0-9][a-z0-9_-/]*",
        )
    parts = [p for p in namespace.split("/") if p != ""]
    if not parts:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="namespace has no segments"
        )
    scope = parts[0]
    if scope not in NAMESPACE_SCOPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"namespace scope must be one of {NAMESPACE_SCOPES}",
        )
    for seg in parts[1:]:
        if not _SEGMENT_RE.match(seg):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"namespace segment invalid: {seg!r}",
            )
    if scope == "global":
        return scope, None, parts[1:]
    if len(parts) < 2:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"namespace scope {scope!r} requires an id segment",
        )
    return scope, parts[1], parts[2:]


def validate_namespace(namespace: str) -> str:
    parse_namespace(namespace)
    return namespace


def build_namespace(scope: str, scoped_id: str | None, *segments: str) -> str:
    parts: list[str] = [scope]
    if scope != "global":
        if not scoped_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"build_namespace: scope {scope!r} requires id",
            )
        parts.append(scoped_id)
    parts.extend(segments)
    ns = "/".join(parts).lower()
    return validate_namespace(ns)


def coerce_legacy_namespace(
    namespace: str,
    *,
    project_id: str | None,
    company_id: str | None,
    agent_id: str | None,
) -> str:
    """Best-effort upgrade of free-string legacy namespaces to taxonomy form."""
    if not namespace:
        if project_id:
            return build_namespace("project", project_id, "general")
        if company_id:
            return build_namespace("company", company_id, "general")
        return build_namespace("global", None, "general")
    head = namespace.split("/", 1)[0].lower()
    if head in NAMESPACE_SCOPES:
        try:
            return validate_namespace(namespace)
        except HTTPException:
            pass
    safe = re.sub(r"[^a-z0-9_\-]+", "-", namespace.strip().lower()).strip("-/") or "general"
    if agent_id:
        return build_namespace("agent", agent_id, "memory", safe[:64])
    if project_id:
        return build_namespace("project", project_id, safe[:64])
    if company_id:
        return build_namespace("company", company_id, safe[:64])
    return build_namespace("global", None, safe[:64])


__all__ = [
    "AGENT_SUB_PREFIXES",
    "NAMESPACE_SCOPES",
    "build_namespace",
    "coerce_legacy_namespace",
    "parse_namespace",
    "validate_namespace",
]
