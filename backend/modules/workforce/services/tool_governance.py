"""Central tool governance queries — single source for approval/risk decisions.

Replaces duplicated hard-coded ``dangerous_tools``, ``_LOW_RISK_TOOLS``, and
skill-validation tool sets. Catalog + ToolDefinition remain canonical for
``requires_approval`` / ``risk_level``; ActionPolicy layers owner overrides.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.action_metadata import (
    SideEffect,
    governance_for_action_key,
)
from backend.modules.workforce.constants import DEFAULT_ACTION_POLICIES, NATIVE_TOOL_CATALOG
from backend.modules.workforce.models import ToolDefinition
from backend.modules.workforce.services.action_policy import (
    DECISION_APPROVAL,
    DECISION_AUTONOMOUS,
    DECISION_PROHIBITED,
    ActionPolicyService,
)

_HIGH_RISK_LEVELS = frozenset({"high", "critical"})


def _catalog_entry(tool_slug: str) -> dict[str, Any] | None:
    slug = str(tool_slug or "").strip()
    for item in NATIVE_TOOL_CATALOG:
        if item["slug"] == slug:
            return item
    return None


def _abstract_policy_row(action_key: str) -> dict[str, Any] | None:
    for row in DEFAULT_ACTION_POLICIES:
        if row["action_key"] == action_key:
            return row
    return None


def catalog_tool_risk_level(tool_slug: str) -> str:
    entry = _catalog_entry(tool_slug)
    if entry is not None:
        return str(entry.get("risk_level") or "medium")
    policy = _abstract_policy_row(tool_slug)
    if policy is not None:
        return str(policy.get("risk_level") or "medium")
    if str(tool_slug or "").startswith(("mcp.", "a2a.")):
        return "high"
    return "medium"


def catalog_tool_requires_approval(tool_slug: str) -> bool:
    """Fail closed for unknown, ecosystem, and catalog tools marked requires_approval."""
    slug = str(tool_slug or "").strip()
    if not slug:
        return True
    entry = _catalog_entry(slug)
    if entry is not None:
        return bool(entry.get("requires_approval"))
    policy = _abstract_policy_row(slug)
    if policy is not None:
        decision = str(policy.get("decision") or DECISION_APPROVAL)
        if decision == DECISION_PROHIBITED:
            return True
        return decision == DECISION_APPROVAL
    if slug.startswith(("mcp.", "a2a.")):
        return True
    return True


def is_external_mutating_tool(tool_slug: str) -> bool:
    """Whether executing the tool performs an external side effect."""
    slug = str(tool_slug or "").strip()
    if not slug:
        return False
    return governance_for_action_key(slug).side_effect == SideEffect.EXTERNAL_MUTATING


def is_low_risk_tool(tool_slug: str) -> bool:
    """Read-only registered tools that do not require approval."""
    slug = str(tool_slug or "").strip()
    if not slug or slug.startswith(("mcp.", "a2a.", "github_")):
        return False
    entry = _catalog_entry(slug)
    if entry is None:
        return False
    if catalog_tool_requires_approval(slug):
        return False
    governance = governance_for_action_key(slug)
    return governance.side_effect == SideEffect.READ


def tool_requires_hitl_execution_grant(tool_slug: str) -> bool:
    """Whether the run_tool HITL gate should require a dangerous_tool_call grant."""
    return catalog_tool_requires_approval(tool_slug)


def is_governed_high_risk_tool(tool_slug: str) -> bool:
    """Skill validation: tools incompatible with low-risk skills without approval policy."""
    slug = str(tool_slug or "").strip()
    if not slug:
        return True
    if catalog_tool_requires_approval(slug):
        return True
    return catalog_tool_risk_level(slug) in _HIGH_RISK_LEVELS


@dataclass(frozen=True, slots=True)
class EffectiveToolDecision:
    tool_slug: str
    decision: str
    requires_approval: bool
    risk_level: str
    is_low_risk: bool
    requires_hitl_grant: bool
    governance: dict[str, Any]
    source: str

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "tool_slug": self.tool_slug,
            "decision": self.decision,
            "requires_approval": self.requires_approval,
            "risk_level": self.risk_level,
            "is_low_risk": self.is_low_risk,
            "requires_hitl_grant": self.requires_hitl_grant,
            "governance": self.governance,
            "source": self.source,
        }


def _decision_from_tool_record(
    tool_slug: str,
    *,
    requires_approval: bool,
    risk_level: str,
    source: str,
) -> EffectiveToolDecision:
    governance = governance_for_action_key(tool_slug).to_dict()
    decision = DECISION_APPROVAL if requires_approval else DECISION_AUTONOMOUS
    policy = _abstract_policy_row(tool_slug)
    if policy and str(policy.get("decision")) == DECISION_PROHIBITED:
        decision = DECISION_PROHIBITED
        requires_approval = True
    return EffectiveToolDecision(
        tool_slug=tool_slug,
        decision=decision,
        requires_approval=requires_approval,
        risk_level=risk_level,
        is_low_risk=is_low_risk_tool(tool_slug),
        requires_hitl_grant=tool_requires_hitl_execution_grant(tool_slug),
        governance={
            **governance,
            "risk_level": risk_level,
            "requires_approval": requires_approval,
        },
        source=source,
    )


def effective_tool_decision_from_catalog(tool_slug: str) -> EffectiveToolDecision:
    slug = str(tool_slug or "").strip()
    entry = _catalog_entry(slug)
    if entry is not None:
        return _decision_from_tool_record(
            slug,
            requires_approval=bool(entry.get("requires_approval")),
            risk_level=str(entry.get("risk_level") or "medium"),
            source="catalog",
        )
    policy = _abstract_policy_row(slug)
    if policy is not None:
        decision = str(policy.get("decision") or DECISION_APPROVAL)
        requires_approval = decision in {DECISION_APPROVAL, DECISION_PROHIBITED}
        return _decision_from_tool_record(
            slug,
            requires_approval=requires_approval,
            risk_level=str(policy.get("risk_level") or "medium"),
            source="abstract_policy",
        )
    if slug.startswith(("mcp.", "a2a.")):
        return _decision_from_tool_record(
            slug,
            requires_approval=True,
            risk_level="high",
            source="ecosystem_fail_closed",
        )
    return _decision_from_tool_record(
        slug,
        requires_approval=True,
        risk_level="medium",
        source="unknown_fail_closed",
    )


def effective_tool_decision_from_definition(tool: ToolDefinition) -> EffectiveToolDecision:
    return _decision_from_tool_record(
        tool.slug,
        requires_approval=bool(tool.requires_approval),
        risk_level=str(tool.risk_level or "medium"),
        source="tool_definition",
    )


async def resolve_effective_tool_decision(
    db: AsyncSession,
    owner_id: str,
    tool_slug: str,
    context: dict[str, Any] | None = None,
) -> EffectiveToolDecision:
    """Resolve catalog defaults merged with ActionPolicy for an owner."""
    from backend.modules.workforce.repository import WorkforceRepository

    slug = str(tool_slug or "").strip()
    repo = WorkforceRepository(db)
    tool = await repo.get_tool_definition(slug)
    if tool is None:
        base = effective_tool_decision_from_catalog(slug)
    else:
        base = effective_tool_decision_from_definition(tool)

    policy = ActionPolicyService(db)
    resolution = await policy.resolve(
        owner_id,
        action_key=slug,
        context=dict(context or {}),
        tool_slug=slug,
    )
    decision = str(resolution.get("decision") or base.decision)
    requires_approval = decision in {DECISION_APPROVAL, DECISION_PROHIBITED}
    governance = dict(resolution.get("governance") or base.governance)
    return EffectiveToolDecision(
        tool_slug=slug,
        decision=decision,
        requires_approval=requires_approval,
        risk_level=str(governance.get("risk_level") or base.risk_level),
        is_low_risk=is_low_risk_tool(slug) and decision == DECISION_AUTONOMOUS,
        requires_hitl_grant=requires_approval,
        governance=governance,
        source="action_policy",
    )


def built_in_tool_decision_snapshots() -> dict[str, dict[str, Any]]:
    """Frozen effective decisions for every native catalog tool + abstract policy key."""
    snapshots: dict[str, dict[str, Any]] = {}
    for item in NATIVE_TOOL_CATALOG:
        slug = str(item["slug"])
        snapshots[slug] = effective_tool_decision_from_catalog(slug).to_snapshot()
    for row in DEFAULT_ACTION_POLICIES:
        key = str(row["action_key"])
        if key not in snapshots:
            snapshots[key] = effective_tool_decision_from_catalog(key).to_snapshot()
    snapshots["__unknown__"] = effective_tool_decision_from_catalog(
        "not.a.registered.tool"
    ).to_snapshot()
    return snapshots
