"""Canonical effective tool permission resolution across grant + policy hierarchy."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.services.action_policy import (
    DECISION_APPROVAL,
    DECISION_AUTONOMOUS,
    DECISION_PROHIBITED,
    ActionPolicyService,
)

# Most specific → least specific (for allow precedence)
_GRANT_SCOPE_ORDER = ("skill", "agent", "project", "department", "organization")
_GRANT_SUBJECT_ALIASES = {"dept": "department", "company": "organization"}


def _normalize_scope(subject_type: str) -> str:
    key = (subject_type or "").strip().lower()
    return _GRANT_SUBJECT_ALIASES.get(key, key)


def _grant_scope_rank(subject_type: str) -> int:
    normalized = _normalize_scope(subject_type)
    try:
        return _GRANT_SCOPE_ORDER.index(normalized)
    except ValueError:
        return len(_GRANT_SCOPE_ORDER)


async def resolve_effective_tool_permissions(
    db: AsyncSession,
    *,
    owner_id: str,
    agent_id: str | None = None,
    project_id: str | None = None,
    company_id: str | None = None,
    department_id: str | None = None,
    skill_ids: list[str] | None = None,
    tool_slugs: list[str] | None = None,
    declared_tools: list[str] | None = None,
) -> dict[str, Any]:
    """Resolve inherited ToolGrants + ActionPolicy for an execution context.

    Hierarchy (grants): organization → department → project → agent → skill.
    Deny grants win globally; allow uses the most specific matching scope.
    Final executable set intersects declared agent tools when provided.
    """
    repo = WorkforceRepository(db)
    policy_svc = ActionPolicyService(db)

    subjects: list[tuple[str, str]] = []
    if company_id:
        subjects.append(("organization", str(company_id)))
    if department_id:
        subjects.append(("department", str(department_id)))
    if project_id:
        subjects.append(("project", str(project_id)))
    if agent_id:
        subjects.append(("agent", str(agent_id)))
    for skill_id in skill_ids or []:
        if skill_id:
            subjects.append(("skill", str(skill_id)))

    grants_by_scope: dict[str, list[Any]] = {}
    for subject_type, subject_id in subjects:
        grants = await repo.list_tool_grants_for_subject(subject_type, subject_id, effect=None)
        if not grants:
            # tolerate legacy alias subject types
            alias = "dept" if subject_type == "department" else subject_type
            grants = await repo.list_tool_grants_for_subject(alias, subject_id, effect=None)
        if grants:
            grants_by_scope.setdefault(subject_type, []).extend(grants)

    all_grants = [g for batch in grants_by_scope.values() for g in batch]
    tool_ids = list({g.tool_definition_id for g in all_grants if g.tool_definition_id})
    tool_defs = await repo.list_tool_definitions_by_ids(tool_ids)
    slug_by_id = {t.id: t.slug for t in tool_defs if t.slug}
    id_by_slug: dict[str, str] = {t.slug: t.id for t in tool_defs if t.slug}

    requested = [str(t).strip() for t in (tool_slugs or []) if str(t).strip()]
    if requested:
        for slug in requested:
            if slug not in id_by_slug:
                tool_def = await repo.get_tool_definition(slug)
                if tool_def:
                    id_by_slug[tool_def.id] = tool_def.slug
                    slug_by_id[tool_def.id] = tool_def.slug
        candidate_slugs = list(dict.fromkeys(requested))
    else:
        candidate_slugs = sorted(
            {
                slug_by_id[g.tool_definition_id]
                for g in all_grants
                if g.tool_definition_id in slug_by_id
            }
        )

    declared = {str(t).strip() for t in (declared_tools or []) if str(t).strip()}

    context_base: dict[str, Any] = {
        "owner_id": owner_id,
        "project_id": project_id,
        "company_id": company_id,
        "department_id": department_id,
        "agent_id": agent_id,
    }
    if skill_ids:
        context_base["skill_id"] = skill_ids[0]

    by_tool: dict[str, dict[str, Any]] = {}
    effective_allow: list[str] = []
    effective_deny: list[str] = []

    for slug in candidate_slugs:
        slug_grants = [g for g in all_grants if slug_by_id.get(g.tool_definition_id) == slug]
        sources: list[dict[str, Any]] = []
        denied = False
        allowed = False

        for grant in sorted(
            slug_grants,
            key=lambda g: _grant_scope_rank(_normalize_scope(g.subject_type)),
        ):
            scope = _normalize_scope(grant.subject_type)
            sources.append(
                {
                    "type": "grant",
                    "scope_type": scope,
                    "scope_id": grant.subject_id,
                    "effect": grant.effect,
                    "grant_id": grant.id,
                }
            )
            if (grant.effect or "").lower() == "deny":
                denied = True
                break
            if (grant.effect or "").lower() == "allow":
                allowed = True

        policy_context = {**context_base, "allowed_tools": list(declared) if declared else [slug]}
        resolution = await policy_svc.resolve(owner_id, slug, policy_context, tool_slug=slug)
        decision = str(resolution.get("decision") or DECISION_APPROVAL)
        sources.append(
            {
                "type": "policy",
                "action_key": resolution.get("action_key") or slug,
                "decision": decision,
                "matched_scope": resolution.get("matched_scope"),
                "matched_policy_id": resolution.get("matched_policy_id"),
                "risk_level": resolution.get("tool_risk_level"),
            }
        )

        if denied:
            effect = "deny"
        elif decision == DECISION_PROHIBITED:
            effect = "prohibited"
        elif not allowed:
            effect = "deny"
        elif decision == DECISION_APPROVAL:
            effect = "approval_required"
        elif decision == DECISION_AUTONOMOUS:
            effect = "allow"
        else:
            effect = "approval_required"

        if declared and slug not in declared:
            effect = "deny"
            sources.append({"type": "declared_tools", "effect": "not_declared"})

        by_tool[slug] = {"effect": effect, "sources": sources}

        if effect in {"allow", "approval_required"}:
            effective_allow.append(slug)
        else:
            effective_deny.append(slug)

    requested_unavailable = [slug for slug in requested if slug not in effective_allow]

    return {
        "effective_allow": sorted(set(effective_allow)),
        "effective_deny": sorted(set(effective_deny)),
        "requested_unavailable": sorted(set(requested_unavailable)),
        "by_tool": by_tool,
    }
