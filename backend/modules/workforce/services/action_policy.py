"""Action policy resolution with deny-overrides precedence.

Algorithm (documented for operators and tests):

1. Collect applicable policies for an action_key across scopes present in context:
   task → skill → agent → project → department → organization → global
   (most specific first). Missing scopes are skipped.

2. DENY WINS: if any applicable policy decision is ``prohibited``,
   the resolved decision is ``prohibited``. A narrower scope cannot
   weaken a broader prohibition.

3. Otherwise, the most specific (first found in the order above) non-null
   decision wins among {autonomous, approval_required}.

4. If no policy exists, fall back to the tool definition default:
   - requires_approval True → approval_required
   - else → autonomous
   - unknown tools → approval_required
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.action_metadata import governance_for_action_key
from backend.modules.workforce.models import ActionPolicy
from backend.modules.workforce.repository import WorkforceRepository

# Most specific → least specific
POLICY_SCOPE_ORDER = (
    "task",
    "skill",
    "agent",
    "project",
    "department",
    "organization",
    "global",
)

DECISION_PROHIBITED = "prohibited"
DECISION_APPROVAL = "approval_required"
DECISION_AUTONOMOUS = "autonomous"
VALID_DECISIONS = {DECISION_PROHIBITED, DECISION_APPROVAL, DECISION_AUTONOMOUS}


def resolve_decision_from_policies(
    policies: list[ActionPolicy],
    *,
    default: str = DECISION_APPROVAL,
) -> dict[str, Any]:
    """Pure resolver used by service + unit tests."""
    by_scope: dict[str, ActionPolicy] = {}
    for policy in policies:
        scope = (policy.scope_type or "").strip().lower()
        if scope not in POLICY_SCOPE_ORDER:
            continue
        decision = (policy.decision or "").strip().lower()
        if decision not in VALID_DECISIONS:
            continue
        # Prefer first seen; callers should pass most-specific duplicates carefully
        by_scope.setdefault(scope, policy)

    ordered = [by_scope[s] for s in POLICY_SCOPE_ORDER if s in by_scope]
    if not ordered:
        return {
            "decision": default,
            "reason": "no_policy_matched",
            "matched_scope": None,
            "matched_policy_id": None,
            "deny_override": False,
        }

    prohibited = [p for p in ordered if p.decision == DECISION_PROHIBITED]
    if prohibited:
        # Prefer the broadest prohibition for explanation (last in specificity order)
        chosen = prohibited[-1]
        return {
            "decision": DECISION_PROHIBITED,
            "reason": "deny_override",
            "matched_scope": chosen.scope_type,
            "matched_policy_id": chosen.id,
            "deny_override": True,
        }

    chosen = ordered[0]
    return {
        "decision": chosen.decision,
        "reason": "most_specific",
        "matched_scope": chosen.scope_type,
        "matched_policy_id": chosen.id,
        "deny_override": False,
    }


class ActionPolicyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)

    async def list_applicable_policies(
        self,
        owner_id: str,
        action_key: str,
        context: dict[str, Any],
    ) -> list[ActionPolicy]:
        """Batch-load policies for all scopes present in context (no N+1)."""
        scope_filters: list[tuple[str, str | None]] = []
        for scope in POLICY_SCOPE_ORDER:
            if scope == "global":
                scope_filters.append(("global", None))
                continue
            scope_id = context.get(f"{scope}_id")
            if scope_id:
                scope_filters.append((scope, str(scope_id)))
            # Also allow owner-level organization policy without id
            if scope == "organization" and context.get("company_id"):
                scope_filters.append(("organization", str(context["company_id"])))

        if not scope_filters:
            scope_filters = [("global", None)]

        result = await self.db.execute(
            select(ActionPolicy).where(
                ActionPolicy.owner_id == owner_id,
                ActionPolicy.action_key == action_key,
            )
        )
        all_policies = list(result.scalars().all())
        wanted = {(s, sid) for s, sid in scope_filters}
        matched: list[ActionPolicy] = []
        for policy in all_policies:
            key = (policy.scope_type, policy.scope_id)
            if (
                key in wanted
                or policy.scope_type == "global"
                and ("global", None) in wanted
                or (
                    policy.scope_type == "organization"
                    and policy.scope_id is None
                    and any(s == "organization" for s, _ in scope_filters)
                )
            ):
                matched.append(policy)
        return matched

    async def resolve(
        self,
        owner_id: str,
        action_key: str,
        context: dict[str, Any],
        *,
        tool_slug: str | None = None,
    ) -> dict[str, Any]:
        policies = await self.list_applicable_policies(owner_id, action_key, context)
        default = DECISION_APPROVAL
        slug = tool_slug or action_key
        tool = await self.repo.get_tool_definition(slug)
        if tool is not None:
            default = DECISION_APPROVAL if tool.requires_approval else DECISION_AUTONOMOUS
        resolved = resolve_decision_from_policies(policies, default=default)
        resolved["action_key"] = action_key
        resolved["tool_slug"] = slug
        if tool is not None:
            resolved["tool_risk_level"] = tool.risk_level
            resolved["tool_requires_approval"] = tool.requires_approval
            governance = governance_for_action_key(slug)
            resolved["governance"] = {
                **governance.to_dict(),
                "risk_level": tool.risk_level,
                "requires_approval": tool.requires_approval,
            }
        else:
            governance = governance_for_action_key(action_key)
            resolved["governance"] = governance.to_dict()
        return resolved

    async def may_execute(
        self,
        owner_id: str,
        tool_slug: str,
        context: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        """Return (allowed_without_approval, resolution)."""
        resolution = await self.resolve(
            owner_id,
            action_key=tool_slug,
            context=context,
            tool_slug=tool_slug,
        )
        decision = resolution["decision"]
        if decision == DECISION_PROHIBITED:
            return False, resolution
        if decision == DECISION_APPROVAL:
            if context.get("approval_granted"):
                return True, resolution
            return False, resolution
        return True, resolution
