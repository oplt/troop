"""Tool registry service managing tool definitions and policies."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG
from backend.modules.workforce.models import ToolDefinition
from backend.modules.workforce.repository import WorkforceRepository


class ToolProvider(Protocol):
    """Protocol for tool providers."""

    async def discover_tools(self) -> list[dict]:
        """Discover available tools."""
        ...

    async def get_schema(self, tool_slug: str) -> dict:
        """Get tool schema."""
        ...

    async def validate_permissions(self, tool_slug: str, context: dict) -> bool:
        """Validate tool permissions."""
        ...

    async def estimate_risk(self, tool_slug: str) -> str:
        """Estimate risk level (low|medium|high|critical)."""
        ...

    async def execute(self, tool_slug: str, params: dict, context: dict) -> dict:
        """Execute tool action (can delegate to execution layer)."""
        ...


class NativeToolProvider:
    """Provider for native/built-in tools."""

    async def discover_tools(self) -> list[dict]:
        """Return native tool catalog."""
        return NATIVE_TOOL_CATALOG

    async def get_schema(self, tool_slug: str) -> dict:
        """Get native tool schema."""
        for tool in NATIVE_TOOL_CATALOG:
            if tool["slug"] == tool_slug:
                return tool.get("schema_json", {})
        return {}

    async def validate_permissions(self, tool_slug: str, context: dict) -> bool:
        """Native tools use default permission model."""
        return True

    async def estimate_risk(self, tool_slug: str) -> str:
        """Return risk level from catalog."""
        for tool in NATIVE_TOOL_CATALOG:
            if tool["slug"] == tool_slug:
                return tool.get("risk_level", "medium")
        return "medium"

    async def execute(self, tool_slug: str, params: dict, context: dict) -> dict:
        """Delegate to execution layer (not implemented here)."""
        return {"status": "delegated", "tool_slug": tool_slug}


class ToolRegistryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)
        self.providers: dict[str, ToolProvider] = {
            "native": NativeToolProvider(),
        }

    async def seed_tool_definitions(self) -> int:
        """
        Seed native tools into ToolDefinition table.

        Returns count of seeded tools.
        """
        count = 0
        for tool_data in NATIVE_TOOL_CATALOG:
            existing = await self.repo.get_tool_definition(tool_data["slug"])
            if existing:
                continue

            await self.repo.create_tool_definition(
                slug=tool_data["slug"],
                name=tool_data["name"],
                description=tool_data["description"],
                provider_type=tool_data.get("provider_type", "native"),
                schema_json=tool_data.get("schema_json", {}),
                risk_level=tool_data["risk_level"],
                requires_approval=tool_data["requires_approval"],
                is_active=True,
                metadata_json={},
            )
            count += 1

        await self.db.commit()
        return count

    async def list_tools(self, is_active: bool | None = True) -> list[ToolDefinition]:
        """List tool definitions."""
        return await self.repo.list_tool_definitions(is_active=is_active)

    async def resolve_action_policy(
        self,
        owner_id: str,
        action_key: str,
        context: dict,
    ) -> str:
        """
        Resolve action policy with precedence: org → dept → project → agent → skill → task.

        Returns decision (autonomous|approval_required|prohibited).
        """
        for scope_type in ["organization", "department", "project", "agent", "skill", "task"]:
            scope_id = context.get(f"{scope_type}_id")
            policy = await self.repo.get_action_policy(owner_id, scope_type, scope_id, action_key)
            if policy:
                return policy.decision

        return "approval_required"
