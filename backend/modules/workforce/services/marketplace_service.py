"""Marketplace install/list for skills, workflows, departments, agent templates."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.catalog import (
    AGENT_TEMPLATE_CATALOG,
    MARKETPLACE_DEPARTMENTS,
    MARKETPLACE_SKILLS,
    MARKETPLACE_WORKFLOWS,
)
from backend.modules.workforce.models import WorkflowDefinition, WorkflowVersion
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.services.department_service import DepartmentService
from backend.modules.workforce.services.skill_service import SkillService
from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService


class MarketplaceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)
        self.skills = SkillService(db)
        self.departments = DepartmentService(db)

    def catalog_summary(self) -> dict[str, Any]:
        return {
            "skills": len(MARKETPLACE_SKILLS),
            "workflows": len(MARKETPLACE_WORKFLOWS),
            "departments": len(MARKETPLACE_DEPARTMENTS),
            "agent_templates": len(AGENT_TEMPLATE_CATALOG),
        }

    def list_skills(self, category: str | None = None) -> list[dict[str, Any]]:
        items = MARKETPLACE_SKILLS
        if category:
            items = [s for s in items if s.get("category") == category]
        return [{**s, "kind": "skill"} for s in items]

    def list_workflows(self, category: str | None = None) -> list[dict[str, Any]]:
        items = MARKETPLACE_WORKFLOWS
        if category:
            items = [w for w in items if w.get("category") == category]
        return [{**w, "kind": "workflow"} for w in items]

    def list_departments(self) -> list[dict[str, Any]]:
        return [{**d, "kind": "department"} for d in MARKETPLACE_DEPARTMENTS]

    def list_agent_templates(self) -> list[dict[str, Any]]:
        return [{**a, "kind": "agent_template"} for a in AGENT_TEMPLATE_CATALOG]

    def list_all(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "skills": self.list_skills(),
            "workflows": self.list_workflows(),
            "departments": self.list_departments(),
            "agent_templates": self.list_agent_templates(),
            "summary": self.catalog_summary(),
        }

    def _find_skill(self, slug: str) -> dict[str, Any]:
        for item in MARKETPLACE_SKILLS:
            if item["slug"] == slug:
                return item
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="marketplace skill not found")

    def _find_workflow(self, slug: str) -> dict[str, Any]:
        for item in MARKETPLACE_WORKFLOWS:
            if item["slug"] == slug:
                return item
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="marketplace workflow not found")

    def _find_department(self, slug: str) -> dict[str, Any]:
        for item in MARKETPLACE_DEPARTMENTS:
            if item["slug"] == slug:
                return item
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="marketplace department not found")

    def _find_agent_template(self, slug: str) -> dict[str, Any]:
        for item in AGENT_TEMPLATE_CATALOG:
            if item["slug"] == slug:
                return item
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="marketplace agent template not found")

    async def install_skill(
        self,
        owner_id: str,
        slug: str,
        *,
        company_id: str | None = None,
        publish: bool = True,
    ) -> dict[str, Any]:
        item = self._find_skill(slug)
        existing = await self.repo.find_skill_by_slug(owner_id, slug)
        if existing:
            return {
                "status": "already_installed",
                "kind": "skill",
                "slug": slug,
                "skill_id": existing.id,
            }

        draft = await self.skills.create_draft(
            owner_id,
            company_id=company_id,
            source_type="marketplace",
            status="draft",
            name=item["name"],
            slug=item["slug"],
            description=item.get("description") or "",
            purpose=item.get("purpose") or item.get("description") or "",
            when_to_use=item.get("when_to_use") or "",
            instructions_markdown=item.get("instructions_markdown") or "",
            scope="organization",
            risk_level=item.get("risk_level") or "low",
            capabilities_json=list(item.get("capabilities") or []),
            required_tools_json=list(item.get("required_tools") or []),
            generation_metadata_json={
                "marketplace_slug": slug,
                "category": item.get("category"),
                "department": item.get("department"),
            },
        )
        if not publish:
            return {
                "status": "draft_created",
                "kind": "skill",
                "slug": slug,
                "draft_id": draft.id,
            }

        skill = await self.skills.publish_draft(owner_id, draft.id, created_by=owner_id)
        return {
            "status": "installed",
            "kind": "skill",
            "slug": slug,
            "skill_id": skill.id,
            "draft_id": draft.id,
        }

    async def install_workflow(
        self,
        owner_id: str,
        slug: str,
        *,
        company_id: str | None = None,
        publish: bool = True,
    ) -> dict[str, Any]:
        item = self._find_workflow(slug)
        result = await self.db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.owner_id == owner_id,
                WorkflowDefinition.slug == slug,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return {
                "status": "already_installed",
                "kind": "workflow",
                "slug": slug,
                "workflow_id": existing.id,
            }

        nodes = list(item.get("nodes") or [])
        edges = list(item.get("edges") or [])
        entry = item.get("entry_node_id")
        runtime = WorkflowRuntimeService(self.db)
        errors = runtime.validate_graph(nodes=nodes, edges=edges, entry_node_id=entry)
        if nodes and errors:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"errors": errors})

        definition = WorkflowDefinition(
            id=str(uuid4()),
            owner_id=owner_id,
            company_id=company_id,
            slug=slug,
            name=item["name"],
            description=item.get("description") or "",
            category=item.get("category") or "general",
            status="draft",
            is_template=True,
        )
        self.db.add(definition)
        await self.db.flush()

        version = WorkflowVersion(
            id=str(uuid4()),
            workflow_id=definition.id,
            version_number=1,
            nodes_json=nodes,
            edges_json=edges,
            entry_node_id=entry,
            metadata_json={"marketplace_slug": slug},
            is_published=False,
            created_by=owner_id,
        )
        self.db.add(version)
        await self.db.flush()
        definition.current_version_id = version.id

        if publish:
            version.is_published = True
            definition.status = "published"

        await self.db.commit()
        await self.db.refresh(definition)
        return {
            "status": "installed",
            "kind": "workflow",
            "slug": slug,
            "workflow_id": definition.id,
            "published": bool(publish),
        }

    async def install_department(
        self,
        owner_id: str,
        company_id: str,
        slug: str,
    ) -> dict[str, Any]:
        item = self._find_department(slug)
        existing = await self.repo.find_department_by_slug(company_id, slug)
        if existing:
            return {
                "status": "already_installed",
                "kind": "department",
                "slug": slug,
                "department_id": existing.id,
            }
        dept = await self.departments.create(
            owner_id,
            company_id,
            name=item["name"],
            slug=item["slug"],
            description=item.get("description") or "",
            default_tool_policy_json=item.get("default_tool_policy") or {},
            default_model_policy_json=item.get("default_model_policy") or {},
            default_approval_policy_json=item.get("default_approval_policy") or {},
            metadata_json={"marketplace_slug": slug},
        )
        return {
            "status": "installed",
            "kind": "department",
            "slug": slug,
            "department_id": dept.id,
        }

    async def install_agent_template(self, slug: str) -> dict[str, Any]:
        item = self._find_agent_template(slug)
        from backend.modules.team.service import TeamService

        team = TeamService(self.db)
        existing = await team.repo.get_agent_template_by_slug(slug)
        if existing:
            return {
                "status": "already_installed",
                "kind": "agent_template",
                "slug": slug,
                "template_id": existing.id,
            }
        template = await team.create_agent_template(
            {
                "slug": item["slug"],
                "name": item["name"],
                "role": item.get("role") or "worker",
                "description": item.get("description") or "",
                "system_prompt": f"You are {item['name']}. {item.get('description') or ''}",
                "mission_markdown": item.get("description") or "",
                "capabilities": list(item.get("capabilities") or []),
                "allowed_tools": list(item.get("allowed_tools") or []),
                "skills": list(item.get("skills") or []),
                "tags": list(item.get("tags") or [item.get("department") or "general"]),
                "metadata": {
                    "marketplace_slug": slug,
                    "department": item.get("department"),
                },
            }
        )
        return {
            "status": "installed",
            "kind": "agent_template",
            "slug": slug,
            "template_id": template.get("id"),
        }

    async def seed_agent_templates(self) -> dict[str, Any]:
        results = []
        for item in AGENT_TEMPLATE_CATALOG:
            results.append(await self.install_agent_template(item["slug"]))
        return {
            "installed": sum(1 for r in results if r["status"] == "installed"),
            "skipped": sum(1 for r in results if r["status"] == "already_installed"),
            "results": results,
        }
