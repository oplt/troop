"""Marketplace install/list for skills, workflows, departments, agent templates."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import User
from backend.modules.workforce.catalog import (
    AGENT_TEMPLATE_CATALOG,
    MARKETPLACE_DEPARTMENTS,
    MARKETPLACE_SKILLS,
    MARKETPLACE_WORKFLOWS,
)
from backend.modules.workforce.email_approval_template import EMAIL_APPROVAL_FLAGSHIP_SLUG
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
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="marketplace agent template not found"
        )

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
        if existing and slug != EMAIL_APPROVAL_FLAGSHIP_SLUG:
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
        connector_installation_ids: dict[str, str] | None = None,
        agent_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
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

        nodes = deepcopy(list(item.get("nodes") or []))
        edges = list(item.get("edges") or [])
        entry = item.get("entry_node_id")
        configuration_required: list[str] = []
        if slug == EMAIL_APPROVAL_FLAGSHIP_SLUG:
            bindings = dict(connector_installation_ids or {})
            gmail_id = str(bindings.get("gmail") or "")
            telegram_id = str(bindings.get("telegram") or "")
            approval_channel = str(bindings.get("approval_channel") or "in_app")
            skill_result = await self.install_skill(
                owner_id,
                "email-response-drafter",
                company_id=company_id,
                publish=True,
            )
            skill_id = str(skill_result.get("skill_id") or "")
            if not gmail_id:
                configuration_required.append("connector_installation_ids.gmail")
            if approval_channel == "telegram" and not telegram_id:
                configuration_required.append("connector_installation_ids.telegram")
            if not agent_id:
                configuration_required.append("agent_id")
            else:
                from backend.modules.team.models import AgentProfile

                agent_result = await self.db.execute(
                    select(AgentProfile).where(
                        AgentProfile.id == agent_id,
                        AgentProfile.owner_id == owner_id,
                    )
                )
                if agent_result.scalar_one_or_none() is None:
                    raise HTTPException(
                        status.HTTP_404_NOT_FOUND,
                        detail="agent not found for workflow owner",
                    )
            if not project_id:
                configuration_required.append("project_id")
            if not task_id:
                configuration_required.append("task_id")
            for node in nodes:
                config = dict(node.get("config") or {})
                if node.get("id") == "gmail_trigger":
                    config["connector_installation_id"] = gmail_id
                    config["project_id"] = project_id
                    config["task_id"] = task_id
                elif node.get("id") == "draft_skill":
                    config.pop("skill_slug", None)
                    config["skill_id"] = skill_id
                elif node.get("id") == "draft_agent":
                    config["agent_id"] = agent_id
                elif node.get("id") == "send_draft":
                    if approval_channel == "telegram" and telegram_id:
                        config["approval_delivery_channel"] = "telegram"
                        config["approval_connector_installation_id"] = telegram_id
                    else:
                        config["approval_delivery_channel"] = "in_app"
                        config["approval_connector_installation_id"] = ""
                node["config"] = config
            if configuration_required:
                publish = False
        runtime = WorkflowRuntimeService(self.db)
        errors = runtime.validate_graph(nodes=nodes, edges=edges, entry_node_id=entry)
        if nodes and errors:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"errors": errors})

        from backend.modules.workforce.services.workflow_version_service import (
            WorkflowVersionService,
        )

        version_service = WorkflowVersionService(self.db)
        if existing is None:
            definition = WorkflowDefinition(
                id=str(uuid4()),
                owner_id=owner_id,
                company_id=company_id,
                slug=slug,
                name=item["name"],
                description=item.get("description") or "",
                category=item.get("category") or "general",
                status="draft",
                is_template=False,
            )
            self.db.add(definition)
            await self.db.flush()
            version = await version_service.ensure_draft(
                definition,
                created_by=owner_id,
                nodes=nodes,
                edges=edges,
                entry_node_id=entry,
            )
            version.metadata_json = {"marketplace_slug": slug}
        else:
            definition = existing
            version = await version_service.update_draft(
                definition,
                nodes=nodes,
                edges=edges,
                entry_node_id=entry,
                actor_user_id=owner_id,
            )
            version.metadata_json = {**(version.metadata_json or {}), "marketplace_slug": slug}
            definition.company_id = company_id or definition.company_id
            definition.status = "draft"

        published_version = version
        if publish:
            published_version = await version_service.publish_draft(
                definition,
                actor_user_id=owner_id,
                nodes=nodes,
                edges=edges,
                entry_node_id=entry,
            )
            from backend.modules.workforce.integrations.events import (
                TriggerSubscriptionService,
            )

            await TriggerSubscriptionService(self.db).register_published_gmail_triggers(
                owner_id=owner_id,
                definition=definition,
                version=published_version,
            )
            await TriggerSubscriptionService(self.db).register_published_outlook_triggers(
                owner_id=owner_id,
                definition=definition,
                version=published_version,
            )

        await self.db.commit()
        await self.db.refresh(definition)
        return {
            "status": "configured" if existing else "installed",
            "kind": "workflow",
            "slug": slug,
            "workflow_id": definition.id,
            "published": bool(publish),
            "configuration_required": configuration_required,
        }

    async def bootstrap_email_approval(
        self,
        user: User,
        *,
        company_id: str | None,
        gmail_installation_id: str,
        telegram_installation_id: str | None = None,
        approval_channel: str = "in_app",
        publish: bool = False,
        project_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Guided install: project + task + agent + flagship workflow wiring."""
        from backend.modules.orchestration.repository import OrchestrationRepository
        from backend.modules.team.service import TeamService

        owner_id = user.id
        orch_repo = OrchestrationRepository(self.db)
        team = TeamService(self.db)

        if not gmail_installation_id.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="gmail_installation_id required")

        channel = str(approval_channel or "in_app").strip().lower()
        if channel not in {"in_app", "telegram"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid approval_channel")

        if not agent_id:
            existing_agent = await team.repo.get_agent_by_slug(owner_id, "email-inbox-agent")
            if existing_agent is not None:
                agent_id = existing_agent.id
            else:
                agent = await team.create_agent(
                    user,
                    {
                        "name": "Email Inbox Agent",
                        "slug": "email-inbox-agent",
                        "role": "worker",
                        "description": "Triages inbound email and drafts grounded replies for approval.",
                        "system_prompt": (
                            "You triage inbound email, classify intent, and draft concise grounded replies. "
                            "Never send email without human approval."
                        ),
                        "capabilities": ["email_triage", "email_drafting", "knowledge_retrieval"],
                        "allowed_tools": [
                            "knowledge_search",
                            "gmail.get_thread",
                            "gmail.create_draft",
                        ],
                        "is_active": True,
                        "tags": ["customer_success", "email", "flagship"],
                        "metadata": {"flagship_template": EMAIL_APPROVAL_FLAGSHIP_SLUG},
                    },
                )
                agent_id = agent.id

        if not project_id:
            suffix = uuid4().hex[:8]
            project = await orch_repo.create_project(
                owner_id=owner_id,
                company_id=company_id,
                name="Email automation",
                slug=f"email-automation-{suffix}",
                description="Flagship Gmail triage → draft → approval → send workflow.",
                status="active",
                metadata_json={"flagship_template": EMAIL_APPROVAL_FLAGSHIP_SLUG},
            )
            project_id = project.id
        else:
            project = await orch_repo.get_project(owner_id, project_id)
            if project is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="project not found")

        if not task_id:
            task = await orch_repo.create_task(
                project_id=project_id,
                created_by_user_id=owner_id,
                assigned_agent_id=agent_id,
                title="Inbound email triage",
                description="Workflow task anchor for Gmail trigger events.",
                source="template",
                task_type="automation",
                status="queued",
                metadata_json={"flagship_template": EMAIL_APPROVAL_FLAGSHIP_SLUG},
            )
            task_id = task.id
        else:
            task = await orch_repo.get_task(project_id, task_id)
            if task is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")

        connector_bindings: dict[str, str] = {
            "gmail": gmail_installation_id.strip(),
            "approval_channel": channel,
        }
        if channel == "telegram" and telegram_installation_id:
            connector_bindings["telegram"] = telegram_installation_id.strip()

        install_result = await self.install_workflow(
            owner_id,
            EMAIL_APPROVAL_FLAGSHIP_SLUG,
            company_id=company_id or project.company_id,
            publish=publish,
            connector_installation_ids=connector_bindings,
            agent_id=agent_id,
            project_id=project_id,
            task_id=task_id,
        )

        await self.db.commit()
        return {
            **install_result,
            "project_id": project_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "approval_channel": channel,
            "template_pack": next(
                (
                    item.get("template_pack")
                    for item in MARKETPLACE_WORKFLOWS
                    if item.get("slug") == EMAIL_APPROVAL_FLAGSHIP_SLUG
                ),
                None,
            ),
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
