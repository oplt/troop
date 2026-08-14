"""Tool registry service managing tool definitions and policies."""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.external_effect_inventory import (
    get_external_effect_contract,
)
from backend.modules.workforce.action_metadata import (
    governance_for_action_key,
    native_tool_governance_rows,
)
from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG
from backend.modules.workforce.models import ToolDefinition
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.services.action_policy import (
    DECISION_APPROVAL,
    DECISION_AUTONOMOUS,
    DECISION_PROHIBITED,
    ActionPolicyService,
)


class ToolProvider(Protocol):
    """Protocol for tool providers."""

    async def discover_tools(self) -> list[dict]: ...

    async def get_schema(self, tool_slug: str) -> dict: ...

    async def validate_permissions(self, tool_slug: str, context: dict) -> bool: ...

    async def estimate_risk(self, tool_slug: str) -> str: ...

    async def execute(self, tool_slug: str, params: dict, context: dict) -> dict: ...


class NativeToolProvider:
    """Provider for native/built-in tools with real permission checks."""

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db

    async def discover_tools(self) -> list[dict]:
        return NATIVE_TOOL_CATALOG

    async def get_schema(self, tool_slug: str) -> dict:
        for tool in NATIVE_TOOL_CATALOG:
            if tool["slug"] == tool_slug:
                return tool.get("schema_json", {})
        return {}

    async def validate_permissions(self, tool_slug: str, context: dict) -> bool:
        """Deny by default when owner missing; otherwise resolve ActionPolicy."""
        owner_id = context.get("owner_id")
        if not owner_id:
            return False
        allowed = set(context.get("allowed_tools") or [])
        if allowed and tool_slug not in allowed:
            return False
        if self.db is None:
            # Without DB, only agent allow-list can authorize
            return tool_slug in allowed if allowed else False
        policy = ActionPolicyService(self.db)
        ok, resolution = await policy.may_execute(str(owner_id), tool_slug, context)
        context["_policy_resolution"] = resolution
        if resolution.get("decision") == DECISION_PROHIBITED:
            return False
        return bool(ok)

    async def estimate_risk(self, tool_slug: str) -> str:
        for tool in NATIVE_TOOL_CATALOG:
            if tool["slug"] == tool_slug:
                return tool.get("risk_level", "medium")
        return "medium"

    async def execute(self, tool_slug: str, params: dict, context: dict) -> dict:
        """Permission gate only — execution stays in OrchestrationToolbox."""
        if not await self.validate_permissions(tool_slug, context):
            return {
                "status": "denied",
                "tool_slug": tool_slug,
                "policy": context.get("_policy_resolution"),
            }
        return {
            "status": "delegated",
            "tool_slug": tool_slug,
            "policy": context.get("_policy_resolution"),
        }


class GitHubToolProvider:
    """GitHub tools — same permission model, executes via toolbox."""

    GITHUB_TOOLS = {
        "github_comment",
        "github_label_issue",
        "github_create_pr",
    }

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db
        self._native = NativeToolProvider(db)

    async def discover_tools(self) -> list[dict]:
        return [t for t in NATIVE_TOOL_CATALOG if t["slug"] in self.GITHUB_TOOLS]

    async def get_schema(self, tool_slug: str) -> dict:
        return await self._native.get_schema(tool_slug)

    async def validate_permissions(self, tool_slug: str, context: dict) -> bool:
        if tool_slug not in self.GITHUB_TOOLS:
            return False
        return await self._native.validate_permissions(tool_slug, context)

    async def estimate_risk(self, tool_slug: str) -> str:
        return await self._native.estimate_risk(tool_slug)

    async def execute(self, tool_slug: str, params: dict, context: dict) -> dict:
        return await self._native.execute(tool_slug, params, context)


class MCPToolProvider:
    """Backward-compatible export — live implementation in ecosystem_providers."""

    def __init__(self, db=None) -> None:
        from backend.modules.workforce.services.ecosystem_providers import (
            MCPToolProvider as _Live,
        )

        self._live = _Live(db)

    async def discover_tools(self, context: dict | None = None) -> list[dict]:
        return await self._live.discover_tools(context)

    async def get_schema(self, tool_slug: str) -> dict:
        return await self._live.get_schema(tool_slug)

    async def validate_permissions(self, tool_slug: str, context: dict) -> bool:
        return await self._live.validate_permissions(tool_slug, context)

    async def estimate_risk(self, tool_slug: str) -> str:
        return await self._live.estimate_risk(tool_slug)

    async def execute(self, tool_slug: str, params: dict, context: dict) -> dict:
        return await self._live.execute(tool_slug, params, context)


class ToolRegistryService:
    def __init__(self, db: AsyncSession) -> None:
        from backend.modules.workforce.integrations.tool_provider import (
            NativeConnectorToolProvider,
        )
        from backend.modules.workforce.services.ecosystem_providers import (
            A2AToolProvider,
        )
        from backend.modules.workforce.services.ecosystem_providers import (
            MCPToolProvider as LiveMCP,
        )

        self.db = db
        self.repo = WorkforceRepository(db)
        self.policy = ActionPolicyService(db)
        self.providers: dict[str, ToolProvider] = {
            "native": NativeToolProvider(db),
            "github": GitHubToolProvider(db),
            "mcp": LiveMCP(db),
            "a2a": A2AToolProvider(db),
            "connector": NativeConnectorToolProvider(db),
        }

    def provider_for(self, tool_slug: str) -> ToolProvider:
        if tool_slug.startswith(
            ("gmail.", "outlook.", "google_calendar.", "microsoft_calendar.", "telegram.", "slack.", "teams.")
        ):
            return self.providers["connector"]
        if tool_slug.startswith("github_"):
            return self.providers["github"]
        if tool_slug.startswith("mcp."):
            return self.providers["mcp"]
        if tool_slug.startswith("a2a."):
            return self.providers["a2a"]
        return self.providers["native"]

    async def seed_tool_definitions(self) -> int:
        count = 0
        for tool_data in NATIVE_TOOL_CATALOG:
            governance = governance_for_action_key(tool_data["slug"])
            existing = await self.repo.get_tool_definition(tool_data["slug"])
            if existing:
                await self._apply_governance_to_tool(existing, governance)
                continue
            await self.repo.create_tool_definition(
                slug=tool_data["slug"],
                name=tool_data["name"],
                description=tool_data["description"],
                provider_type=tool_data.get("provider_type", "native"),
                schema_json=tool_data.get("schema_json", {}),
                risk_level=tool_data["risk_level"],
                requires_approval=tool_data["requires_approval"],
                side_effect=governance.side_effect.value,
                reversibility=governance.reversibility.value,
                data_sensitivity=governance.data_sensitivity.value,
                parallel_safe=governance.parallel_safe,
                idempotency_strategy=governance.idempotency_strategy.value,
                commit_check_strategy=governance.commit_check_strategy.value,
                is_active=True,
                metadata_json={"governance": governance.to_dict()},
            )
            count += 1
        await self.db.commit()
        return count

    async def sync_native_tool_governance(self) -> int:
        """Backfill governance columns for all native catalog tools."""
        updated = 0
        for slug, governance in native_tool_governance_rows():
            tool = await self.repo.get_tool_definition(slug)
            if tool is None:
                continue
            if await self._apply_governance_to_tool(tool, governance):
                updated += 1
        await self.db.commit()
        return updated

    @staticmethod
    async def _apply_governance_to_tool(tool, governance) -> bool:
        changed = False
        fields = {
            "side_effect": governance.side_effect.value,
            "reversibility": governance.reversibility.value,
            "data_sensitivity": governance.data_sensitivity.value,
            "parallel_safe": governance.parallel_safe,
            "idempotency_strategy": governance.idempotency_strategy.value,
            "commit_check_strategy": governance.commit_check_strategy.value,
        }
        for key, value in fields.items():
            if getattr(tool, key) != value:
                setattr(tool, key, value)
                changed = True
        meta = dict(tool.metadata_json or {})
        gov = governance.to_dict()
        if meta.get("governance") != gov:
            meta["governance"] = gov
            tool.metadata_json = meta
            changed = True
        return changed

    async def list_tools(self, is_active: bool | None = True) -> list[ToolDefinition]:
        return await self.repo.list_tool_definitions(is_active=is_active)

    async def resolve_action_policy(
        self,
        owner_id: str,
        action_key: str,
        context: dict,
    ) -> str:
        resolved = await self.policy.resolve(owner_id, action_key, context)
        return str(resolved["decision"])

    async def authorize_tool(
        self,
        owner_id: str,
        tool_slug: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        provider = self.provider_for(tool_slug)
        resolution = context.get("_policy_resolution") or await self.policy.resolve(
            owner_id, tool_slug, context, tool_slug=tool_slug
        )
        permitted = await provider.validate_permissions(
            tool_slug, {**context, "owner_id": owner_id}
        )

        # Hierarchical grants (org→dept→project→agent→skill) refine permission.
        # Fail closed for governed/high-risk tools when resolution errors.
        effective = None
        if self.db is not None and (
            context.get("agent_id") or context.get("project_id") or context.get("company_id")
        ):
            from backend.modules.workforce.services.tool_governance import is_low_risk_tool

            try:
                from backend.modules.workforce.services.effective_permissions import (
                    resolve_effective_tool_permissions,
                )

                effective = await resolve_effective_tool_permissions(
                    self.db,
                    owner_id=owner_id,
                    agent_id=context.get("agent_id"),
                    project_id=context.get("project_id"),
                    company_id=context.get("company_id"),
                    department_id=context.get("department_id"),
                    skill_ids=context.get("skill_ids"),
                    tool_slugs=[tool_slug],
                )
                by_tool = (effective.get("by_tool") or {}).get(tool_slug) or {}
                effect = str(by_tool.get("effect") or "")
                if (
                    tool_slug in set(effective.get("effective_deny") or [])
                    or effect
                    in {
                        "deny",
                        "prohibited",
                    }
                    or tool_slug in set(effective.get("requested_unavailable") or [])
                ):
                    permitted = False
                elif (
                    tool_slug in set(effective.get("effective_allow") or [])
                    and resolution.get("decision") != DECISION_PROHIBITED
                ):
                    permitted = True
            except Exception as exc:
                from backend.core.logging import get_logger

                get_logger(__name__).exception(
                    "effective_tool_permissions_failed tool=%s owner=%s",
                    tool_slug,
                    owner_id,
                )
                if not is_low_risk_tool(tool_slug):
                    permitted = False
                    resolution = {
                        **dict(resolution or {}),
                        "decision": DECISION_PROHIBITED,
                        "matched_scope": "effective_permissions_error",
                        "error": str(exc),
                    }
                    context["_policy_resolution"] = resolution
                else:
                    effective = None

        if resolution.get("decision") == DECISION_PROHIBITED:
            permitted = False

        contract = get_external_effect_contract(tool_slug)
        if (
            contract
            and contract.blocks_autonomous_use
            and resolution.get("decision") == DECISION_AUTONOMOUS
            and not context.get("approval_granted")
        ):
            resolution = {
                **dict(resolution or {}),
                "decision": DECISION_APPROVAL,
                "matched_scope": "idempotency_contract",
                "reason": "missing_durable_idempotency",
                "idempotency_blocked_autonomous": True,
                "action_key": contract.action_key,
            }
            context["_policy_resolution"] = resolution

        if tool_slug.startswith("mcp."):
            provider_name = "mcp"
        elif tool_slug.startswith("a2a."):
            provider_name = "a2a"
        elif tool_slug.startswith("github_"):
            provider_name = "github"
        elif tool_slug.startswith(
            ("gmail.", "outlook.", "google_calendar.", "microsoft_calendar.", "telegram.", "slack.", "teams.")
        ):
            provider_name = "connector"
        else:
            provider_name = "native"
        return {
            "permitted": bool(permitted),
            "decision": resolution.get("decision"),
            "resolution": resolution,
            "provider": provider_name,
            "effective": effective,
        }

    async def execute_tool(
        self,
        owner_id: str,
        tool_slug: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        auth = await self.authorize_tool(owner_id, tool_slug, context)
        if not auth.get("permitted"):
            return {"status": "denied", "reason": "not_permitted", **auth}
        if auth.get("decision") == DECISION_PROHIBITED:
            return {"status": "denied", "reason": "prohibited", **auth}
        if auth.get("decision") == "approval_required" and not context.get("approval_granted"):
            return {"status": "approval_required", **auth}
        provider = self.provider_for(tool_slug)
        return await provider.execute(tool_slug, params, {**context, "owner_id": owner_id})
