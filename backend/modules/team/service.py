from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select

from backend.core.logging import get_logger

from backend.modules.identity_access.models import User
from backend.modules.orchestration.markdown import parse_agent_markdown
from backend.modules.projects.orchestration_models import OrchestratorTask
from backend.modules.team.models import (
    AgentProfile,
    AgentTemplateCatalog,
    ProjectAgentMembership,
    TeamProfile,
    TeamTemplateCatalog,
)


logger = get_logger(__name__)

LEGACY_TOOL_ALIASES = {
    "file_read_stub": "fs_read",
    "web_search_stub": "web_search",
    "python_analysis_stub": "code_execute",
    "github_issue_stub": "github_comment",
    "geospatial_analysis_stub": "code_execute",
}


class TeamServiceMixin:
    """Agent CRUD + template + skill + team-template methods.

    Composed into OrchestrationService via multiple inheritance. Relies on the
    host class to supply ``self.db``, ``self.repo``, ``self.audit_repo``,
    ``self._provider_model_exists`` and ``self._model_capability``.
    """

    async def validate_agent_markdown(
        self, user: User, content: str
    ) -> tuple[dict[str, Any] | None, list[str], list[str]]:
        await self._ensure_catalog_seeded()
        normalized, errors = parse_agent_markdown(content)
        if errors or normalized is None:
            return normalized, errors, []
        lint = await self.lint_agent_payload_detailed(user, normalized)
        return normalized, lint["errors"], lint["warnings"]

    async def list_agents(self, user: User, project_id: str | None = None) -> list[AgentProfile]:
        await self._ensure_catalog_seeded()
        await self._purge_placeholder_test_agents(user.id)
        await self._purge_orphan_template_agents(user.id)
        agents = await self.repo.list_agents(user.id, project_id)
        for agent in agents:
            await self._attach_orchestration_skills(agent)
        return agents

    async def _collect_agents_linked_to_template_slug(self, template_slug: str) -> list[AgentProfile]:
        linked_agents = await self.db.execute(
            select(AgentProfile).where(AgentProfile.parent_template_slug == template_slug)
        )
        agent_map = {agent.id: agent for agent in linked_agents.scalars().all()}
        by_metadata = await self.db.execute(
            select(AgentProfile).where(AgentProfile.metadata_json.is_not(None))
        )
        for agent in by_metadata.scalars().all():
            metadata = agent.metadata_json or {}
            if str(metadata.get("from_template") or "").strip() == template_slug:
                agent_map[agent.id] = agent
        return list(agent_map.values())

    async def create_agent(self, user: User, payload: dict[str, Any]) -> AgentProfile:
        await self._ensure_catalog_seeded()
        await self._ensure_unique_agent_slug(user.id, payload["slug"], None)
        requested_skills = self._normalize_skill_refs(payload.get("skills") or [])
        if requested_skills:
            payload = dict(payload)
            payload["skills"] = []
            logger.warning(
                "Ignoring skills_json on agent create; use AgentSkillAssignment instead",
                extra={"owner_id": user.id, "skill_count": len(requested_skills)},
            )
        payload = await self._validate_and_normalize_agent_payload(user, payload, existing_agent_id=None)
        await self._validate_reporting_line(user, payload.get("project_id"), None, payload)
        payload["is_active"] = bool(payload.get("is_active", False))
        agent = await self.repo.create_agent(owner_id=user.id, **self._agent_payload_to_model(payload))
        if requested_skills:
            await self._assign_skills_from_legacy_payload(user.id, agent.id, requested_skills)
        await self._snapshot_agent(agent, user.id)
        await self.audit_repo.log(
            "orchestration.agent.created",
            user_id=user.id,
            resource_type="agent",
            resource_id=agent.id,
            metadata={"slug": agent.slug},
        )
        await self.db.commit()
        await self.db.refresh(agent)
        await self._attach_orchestration_skills(agent)
        return agent

    async def import_agent_markdown(
        self,
        user: User,
        *,
        content: str,
        project_id: str | None = None,
        existing_agent_id: str | None = None,
    ) -> AgentProfile:
        await self._ensure_catalog_seeded()
        normalized, errors = parse_agent_markdown(content)
        if errors or normalized is None:
            raise HTTPException(status_code=422, detail={"errors": errors})
        normalized["project_id"] = project_id
        normalized = await self._validate_and_normalize_agent_payload(
            user,
            normalized,
            existing_agent_id=existing_agent_id,
        )

        manager_slug = normalized["model_policy"].pop("manager_slug", None)
        parent_agent = None
        if manager_slug:
            parent_agent = await self.repo.get_agent_by_slug(user.id, manager_slug)
            if parent_agent:
                normalized["parent_agent_id"] = parent_agent.id

        requested_skills = self._normalize_skill_refs(normalized.get("skills") or [])
        normalized["skills"] = []

        if existing_agent_id:
            agent = await self.get_agent(user, existing_agent_id)
            await self._ensure_unique_agent_slug(user.id, normalized["slug"], agent.id)
            self._apply_agent_updates(agent, normalized)
            agent.version += 1
        else:
            await self._ensure_unique_agent_slug(user.id, normalized["slug"], None)
            normalized["is_active"] = False
            agent = await self.repo.create_agent(
                owner_id=user.id, **self._agent_payload_to_model(normalized)
            )

        if requested_skills:
            await self._assign_skills_from_legacy_payload(user.id, agent.id, requested_skills)
        await self._snapshot_agent(agent, user.id)
        await self.audit_repo.log(
            "orchestration.agent.imported_markdown",
            user_id=user.id,
            resource_type="agent",
            resource_id=agent.id,
            metadata={"project_id": project_id},
        )
        await self.db.commit()
        await self.db.refresh(agent)
        await self._attach_orchestration_skills(agent)
        return agent

    async def get_agent(self, user: User, agent_id: str) -> AgentProfile:
        await self._ensure_catalog_seeded()
        agent = await self.repo.get_agent(user.id, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        await self._attach_orchestration_skills(agent)
        return agent

    async def update_agent(self, user: User, agent_id: str, updates: dict[str, Any]) -> AgentProfile:
        await self._ensure_catalog_seeded()
        agent = await self.get_agent(user, agent_id)
        requested_skills = self._normalize_skill_refs(updates.get("skills") or [])
        if requested_skills or "skills" in updates:
            updates = dict(updates)
            updates.pop("skills", None)
            logger.warning(
                "Ignoring skills_json on agent update; use AgentSkillAssignment instead",
                extra={"agent_id": agent_id, "skill_count": len(requested_skills)},
            )
        if "slug" in updates and updates["slug"] is not None:
            await self._ensure_unique_agent_slug(user.id, updates["slug"], agent.id)
        if "source_markdown" in updates and updates["source_markdown"]:
            normalized, errors = parse_agent_markdown(updates["source_markdown"])
            if errors or normalized is None:
                raise HTTPException(status_code=422, detail={"errors": errors})
            updates = {**normalized, **updates}
            updates.pop("skills", None)
        updates = await self._validate_and_normalize_agent_payload(user, updates, existing_agent_id=agent.id)
        await self._validate_reporting_line(user, updates.get("project_id", agent.project_id), agent, updates)
        self._apply_agent_updates(agent, updates)
        agent.version += 1
        if requested_skills:
            await self._assign_skills_from_legacy_payload(user.id, agent.id, requested_skills)
        await self._snapshot_agent(agent, user.id)
        await self.db.commit()
        await self.db.refresh(agent)
        await self._attach_orchestration_skills(agent)
        return agent

    async def _validate_reporting_line(
        self,
        user: User,
        project_id: str | None,
        agent: AgentProfile | None,
        updates: dict[str, Any],
    ) -> None:
        parent_id = updates.get("parent_agent_id")
        reviewer_id = updates.get("reviewer_agent_id")
        if agent is not None and parent_id == agent.id:
            raise HTTPException(status_code=422, detail="An agent cannot report to itself.")

        async def load_related(related_id: str | None, label: str) -> AgentProfile | None:
            if not related_id:
                return None
            related = await self.repo.get_agent(user.id, str(related_id))
            if related is None:
                raise HTTPException(status_code=422, detail=f"{label} agent was not found.")
            if project_id and related.project_id and related.project_id != project_id:
                raise HTTPException(status_code=422, detail=f"{label} agent must belong to the same project.")
            return related

        parent = await load_related(parent_id, "Parent")
        reviewer = await load_related(reviewer_id, "Reviewer")
        if reviewer is not None and reviewer.role not in {"reviewer", "manager", "team_lead"}:
            raise HTTPException(status_code=422, detail="Reviewer relationship must target a reviewer, manager, or team lead.")

        if parent is None or agent is None:
            return
        seen = {agent.id}
        cursor = parent
        while cursor is not None:
            if cursor.id in seen:
                raise HTTPException(status_code=422, detail="Reporting lines cannot contain cycles.")
            seen.add(cursor.id)
            if not cursor.parent_agent_id:
                break
            cursor = await self.repo.get_agent(user.id, cursor.parent_agent_id)

    async def delete_agent(self, user: User, agent_id: str) -> None:
        await self._ensure_catalog_seeded()
        agent = await self.get_agent(user, agent_id)
        await self.db.delete(agent)
        await self.audit_repo.log(
            "orchestration.agent.deleted",
            user_id=user.id,
            resource_type="agent",
            resource_id=agent.id,
            metadata={"slug": agent.slug},
        )
        await self.db.commit()

    async def duplicate_agent(self, user: User, agent_id: str) -> AgentProfile:
        await self._ensure_catalog_seeded()
        source = await self.get_agent(user, agent_id)
        duplicate_slug = await self._generate_duplicate_slug(user.id, source.slug)
        payload = {
            **self._agent_model_to_payload(source),
            "slug": duplicate_slug,
            "name": f"{source.name} Copy",
            "is_active": False,
            "version": 1,
        }
        copy = await self.repo.create_agent(owner_id=user.id, **payload)
        await self._copy_agent_skill_assignments(source.id, copy.id)
        await self._snapshot_agent(copy, user.id)
        await self.db.commit()
        await self.db.refresh(copy)
        await self._attach_orchestration_skills(copy)
        return copy

    async def set_agent_active_state(self, user: User, agent_id: str, is_active: bool) -> AgentProfile:
        agent = await self.get_agent(user, agent_id)
        if is_active:
            lint = await self.summarize_agent_lint(user, agent)
            if lint["errors"]:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "errors": lint["errors"],
                        "warnings": lint["warnings"],
                        "message": "Agent must pass validation before activation.",
                    },
                )
        agent.is_active = is_active
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def list_agent_versions(self, user: User, agent_id: str):
        await self.get_agent(user, agent_id)
        return await self.repo.list_agent_versions(agent_id)

    async def pin_agent_skills(self, user: User, agent_id: str, payload: dict[str, Any]) -> AgentProfile:
        """Pin skills via AgentSkillAssignment(version_policy=pinned).

        Does not write metadata_json["skill_pins"]. Legacy metadata pins are migrated
        into assignments when the request payload is empty.
        """
        from backend.modules.workforce.repository import WorkforceRepository

        agent = await self.get_agent(user, agent_id)
        pins = list(payload.get("skill_pins") or [])
        meta = dict(agent.metadata_json or {})
        # Brief migration: prefer assignments; migrate old metadata pins when payload empty.
        if not pins and meta.get("skill_pins"):
            pins = list(meta.get("skill_pins") or [])

        repo = WorkforceRepository(self.db)
        for idx, raw in enumerate(pins):
            skill_ref, version_id = self._parse_skill_pin(raw)
            if not skill_ref:
                continue
            skill = await self._resolve_skill_ref(repo, user.id, skill_ref)
            if skill is None:
                raise HTTPException(status_code=404, detail=f"Skill '{skill_ref}' not found")
            pinned_version_id = version_id or skill.current_version_id
            if version_id:
                version = await repo.get_skill_version(version_id)
                if version is None or version.skill_id != skill.id:
                    raise HTTPException(
                        status_code=404, detail=f"Skill version '{version_id}' not found"
                    )
            await repo.upsert_agent_skill_assignment(
                agent_id=agent.id,
                skill_id=skill.id,
                skill_version_id=pinned_version_id,
                version_policy="pinned",
                priority=idx,
                enabled=True,
            )

        if "skill_pins" in meta:
            meta.pop("skill_pins", None)
            agent.metadata_json = meta
        await self.db.commit()
        await self.db.refresh(agent)
        await self._attach_orchestration_skills(agent)
        return agent

    async def list_agent_templates(self) -> list[dict]:
        await self._ensure_catalog_seeded()
        await self._purge_placeholder_test_agent_templates()
        templates = await self.repo.list_agent_templates()
        return [self._template_model_to_payload(item) for item in templates]

    async def _purge_placeholder_test_agents(self, owner_id: str) -> None:
        result = await self.db.execute(
            select(AgentProfile).where(
                AgentProfile.owner_id == owner_id,
                or_(AgentProfile.slug == "test", AgentProfile.name == "test"),
            )
        )
        stale_agents = list(result.scalars().all())
        if not stale_agents:
            return
        for agent in stale_agents:
            await self.db.delete(agent)
        await self.db.commit()

    async def _purge_orphan_template_agents(self, owner_id: str) -> None:
        template_slugs_result = await self.db.execute(select(AgentTemplateCatalog.slug))
        live_slugs = {slug for (slug,) in template_slugs_result.all()}
        result = await self.db.execute(
            select(AgentProfile).where(
                AgentProfile.owner_id == owner_id,
                AgentProfile.parent_template_slug.is_not(None),
            )
        )
        orphans = [agent for agent in result.scalars().all() if agent.parent_template_slug not in live_slugs]
        if not orphans:
            return
        for agent in orphans:
            await self.db.delete(agent)
        await self.db.commit()

    async def _purge_placeholder_test_agent_templates(self) -> None:
        result = await self.db.execute(
            select(AgentTemplateCatalog).where(
                or_(AgentTemplateCatalog.slug == "test", AgentTemplateCatalog.name == "test"),
            )
        )
        stale_templates = list(result.scalars().all())
        if not stale_templates:
            return
        for template in stale_templates:
            await self.db.delete(template)
        await self.db.commit()

    async def create_agent_template(self, payload: dict) -> dict:
        existing = await self.repo.get_agent_template_by_slug(payload["slug"])
        if existing is not None:
            raise HTTPException(status_code=409, detail="Template slug already exists")
        model_policy = dict(payload.get("model_policy") or {})
        if payload.get("permissions") is not None:
            model_policy["permissions"] = payload["permissions"]
        if payload.get("escalation_path") is not None:
            model_policy["escalation_path"] = payload["escalation_path"]
        metadata = dict(payload.get("metadata") or {})
        if payload.get("task_filters") is not None:
            metadata["task_filters"] = list(payload["task_filters"])
        # Legacy mirror only: store Skill id/slug refs (no SkillPack writes).
        skill_refs = self._normalize_skill_refs(payload.get("skills") or [])
        data = {
            "slug": payload["slug"],
            "name": payload["name"],
            "role": payload.get("role", "specialist"),
            "description": payload.get("description"),
            "parent_template_slug": payload.get("parent_template_slug"),
            "system_prompt": payload.get("system_prompt", ""),
            "mission_markdown": payload.get("mission_markdown", ""),
            "rules_markdown": payload.get("rules_markdown", ""),
            "output_contract_markdown": payload.get("output_contract_markdown", ""),
            "capabilities_json": payload.get("capabilities", []),
            "allowed_tools_json": payload.get("allowed_tools", []),
            "skills_json": skill_refs,
            "tags_json": payload.get("tags", []),
            "model_policy_json": model_policy,
            "budget_json": payload.get("budget", {}),
            "memory_policy_json": payload.get("memory_policy", {}),
            "output_schema_json": payload.get("output_schema", {}),
            "metadata_json": metadata,
        }
        template = await self.repo.create_agent_template(**data)
        await self.db.commit()
        await self.db.refresh(template)
        return self._template_model_to_payload(template)

    async def update_agent_template(self, template_id: str, payload: dict) -> dict:
        template = await self.repo.get_agent_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
        if "slug" in payload and payload["slug"] != template.slug:
            existing = await self.repo.get_agent_template_by_slug(payload["slug"])
            if existing is not None and existing.id != template.id:
                raise HTTPException(status_code=409, detail="Template slug already exists")
        payload = dict(payload)
        model_policy = dict(payload.get("model_policy") or template.model_policy_json or {})
        if "permissions" in payload:
            model_policy["permissions"] = payload.pop("permissions")
        if "escalation_path" in payload:
            model_policy["escalation_path"] = payload.pop("escalation_path")
        if "model_policy" in payload:
            payload["model_policy"] = model_policy
        if "task_filters" in payload:
            metadata = dict(payload.get("metadata") or template.metadata_json or {})
            metadata["task_filters"] = list(payload.pop("task_filters") or [])
            payload["metadata"] = metadata
        if "skills" in payload:
            # Legacy mirror of Skill id/slug refs — not SkillPack rows.
            payload["skills"] = self._normalize_skill_refs(payload.get("skills") or [])
        field_map = {
            "slug": "slug",
            "name": "name",
            "role": "role",
            "description": "description",
            "parent_template_slug": "parent_template_slug",
            "system_prompt": "system_prompt",
            "mission_markdown": "mission_markdown",
            "rules_markdown": "rules_markdown",
            "output_contract_markdown": "output_contract_markdown",
            "capabilities": "capabilities_json",
            "allowed_tools": "allowed_tools_json",
            "skills": "skills_json",
            "tags": "tags_json",
            "model_policy": "model_policy_json",
            "budget": "budget_json",
            "memory_policy": "memory_policy_json",
            "output_schema": "output_schema_json",
            "metadata": "metadata_json",
        }
        for key, value in payload.items():
            target = field_map.get(key)
            if target is not None:
                setattr(template, target, value)
        await self.db.commit()
        await self.db.refresh(template)
        return self._template_model_to_payload(template)

    async def delete_agent_template(self, template_id: str) -> None:
        template = await self.repo.get_agent_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
        linked_agents = await self._collect_agents_linked_to_template_slug(template.slug)
        linked_agent_ids = [agent.id for agent in linked_agents]
        if linked_agent_ids:
            memberships = await self.db.execute(
                select(ProjectAgentMembership).where(ProjectAgentMembership.agent_id.in_(linked_agent_ids))
            )
            membership_hits = list(memberships.scalars().all())
            tasks = await self.db.execute(
                select(OrchestratorTask).where(
                    or_(
                        OrchestratorTask.assigned_agent_id.in_(linked_agent_ids),
                        OrchestratorTask.reviewer_agent_id.in_(linked_agent_ids),
                    )
                )
            )
            task_hits = list(tasks.scalars().all())
            if membership_hits or task_hits:
                sample_agents = ", ".join(agent.slug for agent in linked_agents[:3])
                if len(linked_agents) > 3:
                    sample_agents = f"{sample_agents}, +{len(linked_agents) - 3} more"
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Template cannot be deleted because linked agents are still assigned. "
                        f"Agents: {sample_agents or 'unknown'}. "
                        f"Project assignments: {len(membership_hits)}. Task assignments: {len(task_hits)}. "
                        "Remove those project/task assignments first."
                    ),
                )
        for agent in linked_agents:
            await self.db.delete(agent)
        await self.db.delete(template)
        await self.db.commit()

    async def update_agent_template_by_slug(self, slug: str, payload: dict) -> dict:
        template = await self.repo.get_agent_template_by_slug(slug)
        if template is None:
            raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
        return await self.update_agent_template(template.id, payload)

    async def delete_agent_template_by_slug(self, slug: str) -> None:
        template = await self.repo.get_agent_template_by_slug(slug)
        if template is None:
            raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
        await self.delete_agent_template(template.id)

    async def list_skill_catalog(self, user: User) -> list[dict[str, Any]]:
        """List canonical workforce Skills (+ current version), SkillPackResponse-shaped."""
        from backend.modules.workforce.repository import WorkforceRepository

        repo = WorkforceRepository(self.db)
        skills = await repo.list_skills(user.id)
        payloads: list[dict[str, Any]] = []
        for skill in skills:
            version = None
            if skill.current_version_id:
                version = await repo.get_skill_version(skill.current_version_id)
            payloads.append(self._skill_model_to_payload(skill, version))
        return payloads

    async def create_skill_pack(self, payload: dict[str, Any]) -> dict[str, Any]:
        from backend.modules.workforce.services.skillpack_retirement import assert_no_skillpack_writes

        assert_no_skillpack_writes()

    async def update_skill_pack(self, slug: str, payload: dict[str, Any]) -> dict[str, Any]:
        from backend.modules.workforce.services.skillpack_retirement import assert_no_skillpack_writes

        assert_no_skillpack_writes()

    async def delete_skill_pack(self, slug: str) -> None:
        await self._ensure_catalog_seeded()
        skill = await self.repo.get_skill_pack_by_slug(slug)
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
        await self.db.delete(skill)
        await self.db.commit()

    async def list_team_templates(self) -> list[dict[str, Any]]:
        await self._ensure_team_template_catalog_seeded()
        items = await self.repo.list_team_templates()
        return [self._team_template_model_to_payload(item) for item in items]

    async def list_team_profiles(self, user: User) -> list[dict[str, Any]]:
        items = await self.repo.list_team_profiles(user.id)
        return [self._team_profile_model_to_payload(item) for item in items]

    async def create_team_profile_from_template(
        self,
        user: User,
        template_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self._ensure_team_template_catalog_seeded()
        template = await self.repo.get_team_template(template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="Team template not found")
        existing_profiles = await self.repo.list_team_profiles(user.id)
        taken_slugs = {item.slug for item in existing_profiles}

        def _slugify(value: str) -> str:
            return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", value.lower().strip()))

        requested_name = str((payload or {}).get("name") or "").strip()
        requested_slug = str((payload or {}).get("slug") or "").strip()
        base_name = requested_name or template.name or "Team profile"
        base_slug = _slugify(requested_slug or base_name or template.slug or "team-profile") or "team-profile"
        next_slug = base_slug
        index = 2
        while next_slug in taken_slugs:
            next_slug = f"{base_slug}-{index}"
            index += 1

        profile = await self.repo.create_team_profile(
            owner_id=user.id,
            source_team_template_slug=template.slug,
            slug=next_slug,
            name=base_name,
            description=template.description,
            outcome=template.outcome,
            roles_json=list(template.roles_json or []),
            tools_json=list(template.tools_json or []),
            autonomy=template.autonomy,
            visibility=template.visibility,
            agent_template_slugs_json=list(template.agent_template_slugs_json or []),
            canvas_layout_json=dict(template.canvas_layout_json or {}),
        )
        await self.db.commit()
        await self.db.refresh(profile)
        return self._team_profile_model_to_payload(profile)

    async def create_team_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_team_template_catalog_seeded()
        existing = await self.repo.get_team_template_by_slug(payload["slug"])
        if existing is not None:
            raise HTTPException(status_code=409, detail="Team template slug already exists")
        item = await self.repo.create_team_template(
            slug=payload["slug"],
            name=payload["name"],
            description=payload.get("description"),
            outcome=payload.get("outcome", ""),
            roles_json=payload.get("roles", []),
            tools_json=payload.get("tools", []),
            autonomy=payload.get("autonomy", "medium"),
            visibility=payload.get("visibility", "private"),
            agent_template_slugs_json=payload.get("agent_template_slugs", []),
            canvas_layout_json=payload.get("canvas_layout", {}),
        )
        await self.db.commit()
        await self.db.refresh(item)
        return self._team_template_model_to_payload(item)

    async def update_team_template(self, template_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_team_template_catalog_seeded()
        item = await self.repo.get_team_template(template_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Team template not found")
        field_map = {
            "name": "name",
            "description": "description",
            "outcome": "outcome",
            "roles": "roles_json",
            "tools": "tools_json",
            "autonomy": "autonomy",
            "visibility": "visibility",
            "agent_template_slugs": "agent_template_slugs_json",
            "canvas_layout": "canvas_layout_json",
        }
        for key, value in payload.items():
            target = field_map.get(key)
            if target is not None:
                setattr(item, target, value)
        await self.db.commit()
        await self.db.refresh(item)
        return self._team_template_model_to_payload(item)

    async def delete_team_template(self, template_id: str) -> None:
        await self._ensure_team_template_catalog_seeded()
        item = await self.repo.get_team_template(template_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Team template not found")
        await self.db.delete(item)
        await self.db.commit()

    async def create_agent_from_template(
        self, user: User, template_slug: str, overrides: dict[str, Any]
    ) -> AgentProfile:
        await self._ensure_catalog_seeded()
        template = await self.repo.get_agent_template_by_slug(template_slug)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{template_slug}' not found")
        payload = {
            **self._template_model_to_payload(template),
            **{k: v for k, v in overrides.items() if v is not None},
        }
        payload["slug"] = overrides.get("slug") or template.slug
        payload["name"] = overrides.get("name") or template.name
        payload["parent_template_slug"] = overrides.get("parent_template_slug") or template.slug
        payload["metadata"] = {
            **payload.get("metadata", {}),
            "from_template": template_slug,
        }
        requested_skills = self._normalize_skill_refs(payload.get("skills") or [])
        payload["skills"] = []
        payload = await self._validate_and_normalize_agent_payload(user, payload, existing_agent_id=None)
        payload["is_active"] = bool(payload.get("is_active", False))
        await self._ensure_unique_agent_slug(user.id, payload["slug"], None)
        agent = await self.repo.create_agent(owner_id=user.id, **self._agent_payload_to_model(payload))
        if requested_skills:
            await self._assign_skills_from_legacy_payload(user.id, agent.id, requested_skills)
        await self._snapshot_agent(agent, user.id)
        await self.audit_repo.log(
            "orchestration.agent.created_from_template",
            user_id=user.id,
            resource_type="agent",
            resource_id=agent.id,
            metadata={"template_slug": template_slug},
        )
        await self.db.commit()
        await self.db.refresh(agent)
        await self._attach_orchestration_skills(agent)
        return agent

    async def _load_agent_for_run(self, agent_id: str | None) -> AgentProfile | None:
        if not agent_id:
            return None
        return await self.db.get(AgentProfile, agent_id)

    def _is_agent_descendant(self, manager: AgentProfile, worker: AgentProfile) -> bool:
        return manager.id == worker.id or worker.parent_agent_id == manager.id

    async def get_agent_serialization(self, agent: AgentProfile) -> dict[str, Any]:
        payload = self._agent_model_to_payload(agent)
        inheritance = await self.resolve_agent_inheritance(agent)
        payload["inheritance"] = inheritance
        payload["skills"] = await self._skill_slugs_for_agent(agent.id)
        return payload

    async def resolve_agent_inheritance(self, agent: AgentProfile) -> dict[str, Any]:
        await self._ensure_catalog_seeded()
        template = None
        if agent.parent_template_slug:
            template = await self.repo.get_agent_template_by_slug(agent.parent_template_slug)
        inherited_fields: dict[str, Any] = {}
        if template is not None:
            inherited_fields = await self._resolve_template_effective_profile(template)
        agent_skills = await self._skill_slugs_for_agent(agent.id)
        effective = self._merge_agent_with_inheritance(
            agent, inherited_fields, agent_skills=agent_skills
        )
        overridden = self._compute_overridden_fields(
            agent, inherited_fields, agent_skills=agent_skills
        )
        return {
            "parent_template_slug": agent.parent_template_slug,
            "inherited_fields": inherited_fields,
            "overridden_fields": overridden,
            "effective": effective,
        }

    async def _snapshot_agent(self, agent: AgentProfile, user_id: str | None) -> None:
        snapshot = self._agent_model_to_payload(agent)
        snapshot["skills_json"] = await self._skill_slugs_for_agent(agent.id)
        await self.repo.create_agent_version(
            agent_profile_id=agent.id,
            version_number=agent.version,
            source_markdown=agent.source_markdown,
            snapshot_json=snapshot,
            created_by_user_id=user_id,
        )

    def _agent_payload_to_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_policy = dict(payload.get("model_policy") or {})
        if payload.get("permissions") is not None:
            model_policy["permissions"] = payload["permissions"]
        if payload.get("escalation_path") is not None:
            model_policy["escalation_path"] = payload["escalation_path"]
        metadata = dict(payload.get("metadata") or {})
        if payload.get("task_filters") is not None:
            metadata["task_filters"] = list(payload["task_filters"])
        return {
            "project_id": payload.get("project_id"),
            "parent_agent_id": payload.get("parent_agent_id"),
            "reviewer_agent_id": payload.get("reviewer_agent_id"),
            "provider_config_id": payload.get("provider_config_id"),
            "parent_template_slug": payload.get("parent_template_slug"),
            "name": payload["name"],
            "slug": payload["slug"],
            "description": payload.get("description"),
            "role": payload.get("role", "specialist"),
            "system_prompt": payload.get("system_prompt", ""),
            "mission_markdown": payload.get("mission_markdown", ""),
            "rules_markdown": payload.get("rules_markdown", ""),
            "output_contract_markdown": payload.get("output_contract_markdown", ""),
            "source_markdown": payload.get("source_markdown", ""),
            "capabilities_json": payload.get("capabilities", []),
            "allowed_tools_json": payload.get("allowed_tools", []),
            # Assignments are source of truth; leave column empty on write paths.
            "skills_json": [],
            "model_policy_json": model_policy,
            "visibility": payload.get("visibility", "private"),
            "is_active": payload.get("is_active", True),
            "tags_json": payload.get("tags", []),
            "budget_json": payload.get("budget", {}),
            "timeout_seconds": payload.get("timeout_seconds", 900),
            "retry_limit": payload.get("retry_limit", 1),
            "memory_policy_json": payload.get("memory_policy", {}),
            "output_schema_json": payload.get("output_schema", {}),
            "version": payload.get("version", 1),
            "metadata_json": metadata,
        }

    async def _assign_skills_from_legacy_payload(
        self,
        owner_id: str,
        agent_id: str,
        skills: list[str],
    ) -> None:
        """Create AgentSkillAssignment rows from skill slugs/ids."""
        from backend.modules.workforce.repository import WorkforceRepository

        repo = WorkforceRepository(self.db)
        for idx, raw in enumerate(skills):
            token = str(raw or "").strip()
            if not token:
                continue
            skill = await self._resolve_skill_ref(repo, owner_id, token)
            if skill is None or skill.status not in {"active", "testing"}:
                logger.info(
                    "Skipped legacy skill assignment; skill not found or inactive",
                    extra={"agent_id": agent_id, "skill_ref": token},
                )
                continue
            await repo.upsert_agent_skill_assignment(
                agent_id=agent_id,
                skill_id=skill.id,
                skill_version_id=skill.current_version_id,
                version_policy="latest_active",
                priority=idx,
                enabled=True,
            )

    @staticmethod
    def _parse_skill_pin(raw: Any) -> tuple[str, str | None]:
        if isinstance(raw, dict):
            ref = raw.get("skill_id") or raw.get("skill_slug") or raw.get("slug") or raw.get("id")
            version_id = raw.get("skill_version_id")
            return (
                str(ref or "").strip(),
                str(version_id).strip() if version_id else None,
            )
        return str(raw or "").strip(), None

    @classmethod
    def _normalize_skill_refs(cls, skills: list[Any]) -> list[str]:
        refs: list[str] = []
        for raw in skills or []:
            ref, _ = cls._parse_skill_pin(raw)
            if ref and ref not in refs:
                refs.append(ref)
        return refs

    async def _resolve_skill_ref(self, repo: Any, owner_id: str, token: str) -> Any:
        skill = await repo.get_skill(token, owner_id)
        if skill is None:
            skill = await repo.find_skill_by_slug(owner_id, token)
        return skill

    async def _skill_slugs_for_agent(self, agent_id: str) -> list[str]:
        from backend.modules.workforce.models import AgentSkillAssignment, Skill

        result = await self.db.execute(
            select(Skill.slug)
            .join(AgentSkillAssignment, AgentSkillAssignment.skill_id == Skill.id)
            .where(
                AgentSkillAssignment.agent_id == agent_id,
                AgentSkillAssignment.enabled.is_(True),
            )
            .order_by(AgentSkillAssignment.priority.asc())
        )
        return [row[0] for row in result.all()]

    async def _attach_orchestration_skills(self, agent: AgentProfile) -> AgentProfile:
        agent.__orchestration_skills__ = await self._skill_slugs_for_agent(agent.id)
        return agent

    async def _copy_agent_skill_assignments(self, source_agent_id: str, target_agent_id: str) -> None:
        from backend.modules.workforce.repository import WorkforceRepository

        repo = WorkforceRepository(self.db)
        for assignment in await repo.list_agent_skill_assignments(source_agent_id):
            await repo.upsert_agent_skill_assignment(
                agent_id=target_agent_id,
                skill_id=assignment.skill_id,
                skill_version_id=assignment.skill_version_id,
                version_policy=assignment.version_policy,
                priority=assignment.priority,
                enabled=assignment.enabled,
            )

    def _agent_model_to_payload(self, agent: AgentProfile) -> dict[str, Any]:
        model_policy = dict(agent.model_policy_json or {})
        metadata = dict(agent.metadata_json or {})
        return {
            "project_id": agent.project_id,
            "parent_agent_id": agent.parent_agent_id,
            "reviewer_agent_id": agent.reviewer_agent_id,
            "provider_config_id": agent.provider_config_id,
            "parent_template_slug": agent.parent_template_slug,
            "name": agent.name,
            "slug": agent.slug,
            "description": agent.description,
            "role": agent.role,
            "system_prompt": agent.system_prompt,
            "mission_markdown": agent.mission_markdown,
            "rules_markdown": agent.rules_markdown,
            "output_contract_markdown": agent.output_contract_markdown,
            "source_markdown": agent.source_markdown,
            "capabilities_json": agent.capabilities_json,
            "allowed_tools_json": agent.allowed_tools_json,
            # Prefer assignments on hot paths; column retained for legacy/migration only.
            "skills_json": [],
            "model_policy_json": model_policy,
            "permissions": model_policy.get("permissions"),
            "escalation_path": model_policy.get("escalation_path"),
            "visibility": agent.visibility,
            "is_active": agent.is_active,
            "tags_json": agent.tags_json,
            "budget_json": agent.budget_json,
            "timeout_seconds": agent.timeout_seconds,
            "retry_limit": agent.retry_limit,
            "memory_policy_json": agent.memory_policy_json,
            "output_schema_json": agent.output_schema_json,
            "version": agent.version,
            "task_filters": list(metadata.get("task_filters") or []),
            "metadata_json": metadata,
        }

    def _apply_agent_updates(self, agent: AgentProfile, updates: dict[str, Any]) -> None:
        updates = dict(updates)
        model_policy = dict(updates.get("model_policy") or agent.model_policy_json or {})
        if "permissions" in updates:
            model_policy["permissions"] = updates.pop("permissions")
        if "escalation_path" in updates:
            model_policy["escalation_path"] = updates.pop("escalation_path")
        if "model_policy" in updates:
            updates["model_policy"] = model_policy
        if "task_filters" in updates:
            metadata = dict(updates.get("metadata") or agent.metadata_json or {})
            metadata["task_filters"] = list(updates.pop("task_filters") or [])
            updates["metadata"] = metadata
        mapping = {
            "capabilities": "capabilities_json",
            "allowed_tools": "allowed_tools_json",
            "model_policy": "model_policy_json",
            "tags": "tags_json",
            "budget": "budget_json",
            "memory_policy": "memory_policy_json",
            "output_schema": "output_schema_json",
            "metadata": "metadata_json",
        }
        updates.pop("skills", None)
        for field, value in updates.items():
            target = mapping.get(field, field)
            if hasattr(agent, target) and value is not None:
                setattr(agent, target, value)

    async def _ensure_catalog_seeded(self) -> None:
        return

    async def _ensure_team_template_catalog_seeded(self) -> None:
        existing_templates = await self.repo.list_team_templates()
        if existing_templates:
            return

        await self.db.commit()

    async def _validate_and_normalize_agent_payload(
        self,
        user: User,
        payload: dict[str, Any],
        *,
        existing_agent_id: str | None,
    ) -> dict[str, Any]:
        await self._ensure_catalog_seeded()
        normalized = self._normalize_agent_payload_shape(payload)
        lint = await self.lint_agent_payload_detailed(
            user, normalized, existing_agent_id=existing_agent_id
        )
        if lint["errors"]:
            raise HTTPException(
                status_code=422,
                detail={"errors": lint["errors"], "warnings": lint["warnings"]},
            )
        return normalized

    async def lint_agent_payload(
        self,
        user: User,
        payload: dict[str, Any],
        *,
        existing_agent_id: str | None = None,
    ) -> list[str]:
        lint = await self.lint_agent_payload_detailed(
            user, payload, existing_agent_id=existing_agent_id
        )
        return lint["errors"]

    async def lint_agent_payload_detailed(
        self,
        user: User,
        payload: dict[str, Any],
        *,
        existing_agent_id: str | None = None,
    ) -> dict[str, list[str] | bool]:
        errors: list[str] = []
        warnings: list[str] = []
        allowed_tools = {
            "github_comment",
            "github_label_issue",
            "github_create_pr",
            "web_fetch",
            "web_search",
            "code_execute",
            "fs_read",
            "fs_write",
            "db_query",
            "repo_search",
            "knowledge_search",
        }
        for tool in payload.get("allowed_tools", []):
            if tool in allowed_tools:
                continue
            # Ecosystem tools: MCP / A2A live providers
            if isinstance(tool, str) and (tool.startswith("mcp.") or tool.startswith("a2a.")):
                continue
            errors.append(f"Tool '{tool}' is not available in the orchestration runtime.")

        skill_map: dict[str, Any] = {}
        from backend.modules.workforce.repository import WorkforceRepository

        for skill in await WorkforceRepository(self.db).list_skills(user.id):
            skill_map[skill.slug] = skill
            skill_map[skill.id] = skill
        for skill_ref in payload.get("skills", []):
            token = str(skill_ref or "").strip()
            if token and token not in skill_map:
                errors.append(f"Skill '{skill_ref}' is not defined.")

        parent_template_slug = payload.get("parent_template_slug")
        if parent_template_slug and await self.repo.get_agent_template_by_slug(parent_template_slug) is None:
            errors.append(f"Parent template '{parent_template_slug}' does not exist.")

        model_policy = payload.get("model_policy") or {}
        model_name = model_policy.get("model")
        fallback_model = model_policy.get("fallback_model")
        provider = None
        provider_config_id = payload.get("provider_config_id")
        if provider_config_id:
            provider = await self.repo.get_provider(user.id, provider_config_id)
            if provider is None:
                errors.append("Selected provider_config_id does not exist.")
        else:
            providers = await self.repo.list_providers(user.id, payload.get("project_id"))
            provider = next((item for item in providers if item.is_default), None) or (providers[0] if providers else None)
        if model_name and provider and not await self._provider_model_exists(provider, model_name):
            errors.append(
                f"Primary model '{model_name}' is not available on the selected/default provider."
            )
        if fallback_model and provider and not await self._provider_model_exists(provider, fallback_model):
            errors.append(
                f"Fallback model '{fallback_model}' is not available on the selected/default provider."
            )
        if model_name and provider:
            capability = await self._model_capability(model_name, provider.provider_type)
            if capability is None and provider.provider_type != "ollama":
                errors.append(f"Primary model '{model_name}' is missing from the capability matrix.")
        if fallback_model and provider:
            capability = await self._model_capability(fallback_model, provider.provider_type)
            if capability is None and provider.provider_type != "ollama":
                errors.append(f"Fallback model '{fallback_model}' is missing from the capability matrix.")

        linked_to_catalog_template = bool(str(parent_template_slug or "").strip()) or bool(
            str((payload.get("metadata") or {}).get("from_template") or "").strip()
        )
        if linked_to_catalog_template and not payload.get("provider_config_id"):
            if provider is None:
                warnings.append(
                    "This agent profile is linked to a catalog template but has no LLM provider assigned and no workspace default provider exists."
                )
            else:
                warnings.append(
                    "This agent profile is linked to a catalog template without a pinned saved LLM provider; assign one on this profile for predictable execution."
                )

        budget = payload.get("budget") or {}
        token_budget = budget.get("token_budget")
        time_budget = budget.get("time_budget_seconds")
        retry_budget = budget.get("retry_budget")
        if token_budget is not None and (not isinstance(token_budget, (int, float)) or token_budget <= 0 or token_budget > 1_000_000):
            errors.append("budget.token_budget must be between 1 and 1,000,000.")
        if time_budget is not None and (not isinstance(time_budget, (int, float)) or time_budget < 10 or time_budget > 86_400):
            errors.append("budget.time_budget_seconds must be between 10 and 86400.")
        if retry_budget is not None and (not isinstance(retry_budget, (int, float)) or retry_budget < 0 or retry_budget > 20):
            errors.append("budget.retry_budget must be between 0 and 20.")
        cost_cap = budget.get("cost_cap_usd")
        if cost_cap is not None and (
            not isinstance(cost_cap, (int, float)) or float(cost_cap) <= 0 or float(cost_cap) > 50_000
        ):
            errors.append("budget.cost_cap_usd must be between 0 and 50000 (USD, rolling window).")

        task_filters = payload.get("task_filters") or payload.get("metadata", {}).get("task_filters", [])
        for value in task_filters:
            text = str(value).strip()
            if not text:
                continue
            if any(char in text for char in "^$[]().*+?{}\\|"):
                try:
                    re.compile(text)
                except re.error as exc:
                    errors.append(f"task_filter regex '{text}' is invalid: {exc}")

        memory_scope = (payload.get("memory_policy") or {}).get("scope")
        if memory_scope and memory_scope not in {"none", "project-only", "long-term"}:
            errors.append("memory_policy.scope must be one of: none, project-only, long-term.")

        output_format = (payload.get("output_schema") or {}).get("format")
        if output_format and output_format not in {"checklist", "json", "patch_proposal", "issue_reply", "adr"}:
            errors.append("output_schema.format is not supported.")

        permission_level = payload.get("permissions")
        if permission_level is None:
            permission_level = (payload.get("model_policy") or {}).get("permissions")
        if isinstance(permission_level, str) and permission_level not in {"read-only", "comment-only", "code-write", "merge-blocked"}:
            errors.append("permissions must be one of: read-only, comment-only, code-write, merge-blocked.")
        if not str(payload.get("description") or "").strip():
            warnings.append("Description is missing.")
        if not str(payload.get("mission_markdown") or "").strip():
            warnings.append("Mission section is missing.")
        if not str(payload.get("rules_markdown") or "").strip():
            warnings.append("Rules section is missing.")
        if not str(payload.get("output_contract_markdown") or "").strip():
            warnings.append("Output Contract section is missing.")
        if not payload.get("capabilities"):
            warnings.append("Capabilities are empty.")
        if not payload.get("allowed_tools"):
            warnings.append("Allowed tools are empty.")
        if not (payload.get("model_policy") or {}).get("model"):
            warnings.append("Primary model is not configured.")
        if not permission_level:
            warnings.append("Permissions are not configured.")
        if not memory_scope:
            warnings.append("Memory policy scope is not configured.")
        if budget.get("token_budget") is None:
            warnings.append("Token budget is not configured.")
        if budget.get("time_budget_seconds") is None:
            warnings.append("Time budget is not configured.")
        if not task_filters:
            warnings.append("Task filters are empty.")
        if not output_format:
            warnings.append("Output schema format is not configured.")
        if not payload.get("escalation_path") and not (payload.get("model_policy") or {}).get("escalation_path"):
            warnings.append("Escalation path is not configured.")
        return {
            "errors": errors,
            "warnings": warnings,
            "activation_ready": not errors,
        }

    async def summarize_agent_lint(self, user: User, agent: AgentProfile) -> dict[str, Any]:
        payload = self._normalize_agent_payload_shape(self._agent_model_to_payload(agent))
        lint = await self.lint_agent_payload_detailed(user, payload, existing_agent_id=agent.id)
        return {
            "errors": list(lint["errors"]),
            "warnings": list(lint["warnings"]),
            "activation_ready": bool(lint["activation_ready"]),
        }

    def _normalize_agent_payload_shape(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        if "skills_json" in normalized and "skills" not in normalized:
            normalized["skills"] = normalized["skills_json"]
        if "capabilities_json" in normalized and "capabilities" not in normalized:
            normalized["capabilities"] = normalized["capabilities_json"]
        if "allowed_tools_json" in normalized and "allowed_tools" not in normalized:
            normalized["allowed_tools"] = normalized["allowed_tools_json"]
        if "tags_json" in normalized and "tags" not in normalized:
            normalized["tags"] = normalized["tags_json"]
        if "model_policy_json" in normalized and "model_policy" not in normalized:
            normalized["model_policy"] = normalized["model_policy_json"]
        if "budget_json" in normalized and "budget" not in normalized:
            normalized["budget"] = normalized["budget_json"]
        if "memory_policy_json" in normalized and "memory_policy" not in normalized:
            normalized["memory_policy"] = normalized["memory_policy_json"]
        if "output_schema_json" in normalized and "output_schema" not in normalized:
            normalized["output_schema"] = normalized["output_schema_json"]
        if "metadata_json" in normalized and "metadata" not in normalized:
            normalized["metadata"] = normalized["metadata_json"]
        normalized["skills"] = [
            str(item).strip() for item in normalized.get("skills", []) if str(item).strip()
        ]
        normalized["capabilities"] = [
            str(item).strip()
            for item in normalized.get("capabilities", [])
            if str(item).strip()
        ]
        normalized["allowed_tools"] = [
            LEGACY_TOOL_ALIASES.get(str(item).strip(), str(item).strip())
            for item in normalized.get("allowed_tools", [])
            if str(item).strip()
        ]
        normalized["tags"] = [
            str(item).strip() for item in normalized.get("tags", []) if str(item).strip()
        ]
        for key in ("budget", "memory_policy", "model_policy", "output_schema", "metadata"):
            if key in normalized:
                normalized[key] = normalized.get(key) or {}
        model_policy = dict(normalized.get("model_policy") or {})
        has_permissions = "permissions" in normalized or "permissions" in model_policy
        has_escalation = "escalation_path" in normalized or "escalation_path" in model_policy
        if has_permissions:
            if normalized.get("permissions") is None:
                normalized["permissions"] = model_policy.get("permissions")
            else:
                model_policy["permissions"] = normalized["permissions"]
        if has_escalation:
            if normalized.get("escalation_path") is None:
                normalized["escalation_path"] = model_policy.get("escalation_path")
            else:
                model_policy["escalation_path"] = normalized["escalation_path"]
        if "model_policy" in normalized:
            normalized["model_policy"] = model_policy
        if "task_filters" in normalized or "metadata" in normalized:
            metadata = normalized.get("metadata") or {}
            normalized["task_filters"] = list(
                normalized.get("task_filters")
                or metadata.get("task_filters")
                or []
            )
        return normalized

    async def _resolve_template_effective_profile(self, template: AgentTemplateCatalog) -> dict[str, Any]:
        inherited: dict[str, Any] = {}
        if template.parent_template_slug:
            parent = await self.repo.get_agent_template_by_slug(template.parent_template_slug)
            if parent is not None and parent.slug != template.slug:
                inherited = await self._resolve_template_effective_profile(parent)
        current_skills = self._normalize_skill_refs(template.skills_json or [])
        effective = {
            "system_prompt": template.system_prompt or inherited.get("system_prompt", ""),
            "mission_markdown": template.mission_markdown or inherited.get("mission_markdown", ""),
            "rules_markdown": "\n".join(
                chunk for chunk in [inherited.get("rules_markdown", ""), template.rules_markdown or ""] if chunk
            ),
            "output_contract_markdown": template.output_contract_markdown or inherited.get("output_contract_markdown", ""),
            "capabilities": self._merge_unique_lists(
                inherited.get("capabilities", []),
                template.capabilities_json or [],
            ),
            "allowed_tools": self._merge_unique_lists(
                inherited.get("allowed_tools", []),
                template.allowed_tools_json or [],
            ),
            "skills": self._merge_unique_lists(inherited.get("skills", []), current_skills),
            "tags": self._merge_unique_lists(inherited.get("tags", []), template.tags_json or []),
            "budget": {**inherited.get("budget", {}), **(template.budget_json or {})},
            "memory_policy": {**inherited.get("memory_policy", {}), **(template.memory_policy_json or {})},
            "output_schema": {**inherited.get("output_schema", {}), **(template.output_schema_json or {})},
            "model_policy": {**inherited.get("model_policy", {}), **(template.model_policy_json or {})},
            "metadata": {**inherited.get("metadata", {}), **(template.metadata_json or {})},
        }
        effective["permissions"] = effective["model_policy"].get("permissions")
        effective["escalation_path"] = effective["model_policy"].get("escalation_path")
        effective["task_filters"] = list(effective["metadata"].get("task_filters") or [])
        # Skill capability enrichment happens at agent instantiation via SkillVersion,
        # not via legacy SkillPack rows.
        return effective

    def _merge_agent_with_inheritance(
        self,
        agent: AgentProfile,
        inherited: dict[str, Any],
        *,
        agent_skills: list[str] | None = None,
    ) -> dict[str, Any]:
        skills = list(agent_skills) if agent_skills is not None else []
        effective = {
            "system_prompt": agent.system_prompt or inherited.get("system_prompt", ""),
            "mission_markdown": agent.mission_markdown or inherited.get("mission_markdown", ""),
            "rules_markdown": "\n".join(
                chunk for chunk in [inherited.get("rules_markdown", ""), agent.rules_markdown or ""] if chunk
            ),
            "output_contract_markdown": agent.output_contract_markdown or inherited.get("output_contract_markdown", ""),
            "capabilities": self._merge_unique_lists(inherited.get("capabilities", []), agent.capabilities_json or []),
            "allowed_tools": self._merge_unique_lists(inherited.get("allowed_tools", []), agent.allowed_tools_json or []),
            "skills": self._merge_unique_lists(inherited.get("skills", []), skills),
            "tags": self._merge_unique_lists(inherited.get("tags", []), agent.tags_json or []),
            "budget": {**inherited.get("budget", {}), **(agent.budget_json or {})},
            "memory_policy": {**inherited.get("memory_policy", {}), **(agent.memory_policy_json or {})},
            "output_schema": {**inherited.get("output_schema", {}), **(agent.output_schema_json or {})},
            "model_policy": {**inherited.get("model_policy", {}), **(agent.model_policy_json or {})},
        }
        effective["permissions"] = effective["model_policy"].get("permissions")
        effective["escalation_path"] = effective["model_policy"].get("escalation_path")
        effective["task_filters"] = list(
            (agent.metadata_json or {}).get("task_filters")
            or inherited.get("task_filters", [])
        )
        return effective

    def _compute_overridden_fields(
        self,
        agent: AgentProfile,
        inherited: dict[str, Any],
        *,
        agent_skills: list[str] | None = None,
    ) -> dict[str, Any]:
        skills = list(agent_skills) if agent_skills is not None else []
        explicit_fields = {
            "capabilities": list(agent.capabilities_json or []),
            "allowed_tools": list(agent.allowed_tools_json or []),
            "skills": skills,
            "tags": list(agent.tags_json or []),
            "rules_markdown": agent.rules_markdown or "",
            "memory_policy": dict(agent.memory_policy_json or {}),
            "output_schema": dict(agent.output_schema_json or {}),
            "budget": dict(agent.budget_json or {}),
            "model_policy": dict(agent.model_policy_json or {}),
            "permissions": (agent.model_policy_json or {}).get("permissions"),
            "escalation_path": (agent.model_policy_json or {}).get("escalation_path"),
            "task_filters": list((agent.metadata_json or {}).get("task_filters") or []),
        }
        overrides = {}
        for key, value in explicit_fields.items():
            if not value:
                continue
            if value != inherited.get(key):
                overrides[key] = value
        return overrides

    def _merge_unique_lists(self, base: list[str], extra: list[str]) -> list[str]:
        merged: list[str] = []
        for value in [*base, *extra]:
            text = str(value).strip()
            if text and text not in merged:
                merged.append(text)
        return merged

    def _template_model_to_payload(self, template: AgentTemplateCatalog) -> dict[str, Any]:
        model_policy = dict(template.model_policy_json or {})
        metadata = dict(template.metadata_json or {})
        return {
            "id": template.id,
            "slug": template.slug,
            "name": template.name,
            "role": template.role,
            "description": template.description or "",
            "parent_template_slug": template.parent_template_slug,
            "system_prompt": template.system_prompt,
            "mission_markdown": template.mission_markdown,
            "rules_markdown": template.rules_markdown,
            "output_contract_markdown": template.output_contract_markdown,
            "capabilities": list(template.capabilities_json or []),
            "allowed_tools": list(template.allowed_tools_json or []),
            "skills": self._normalize_skill_refs(template.skills_json or []),
            "tags": list(template.tags_json or []),
            "model_policy": model_policy,
            "permissions": model_policy.get("permissions"),
            "escalation_path": model_policy.get("escalation_path"),
            "budget": dict(template.budget_json or {}),
            "memory_policy": dict(template.memory_policy_json or {}),
            "output_schema": dict(template.output_schema_json or {}),
            "task_filters": list(metadata.get("task_filters") or []),
            "metadata": metadata,
        }

    def _skill_model_to_payload(self, skill: Any, version: Any | None = None) -> dict[str, Any]:
        """Map Skill (+ optional SkillVersion) into SkillPackResponse-compatible shape."""
        capabilities = list((version.capabilities_json if version is not None else None) or [])
        allowed_tools = list((version.required_tools_json if version is not None else None) or [])
        rules_markdown = ""
        if version is not None:
            rules_markdown = (
                getattr(version, "constraints_markdown", None)
                or getattr(version, "instructions_markdown", None)
                or ""
            )
        tags: list[str] = []
        if version is not None:
            meta = getattr(version, "generation_metadata_json", None) or {}
            if isinstance(meta, dict):
                tags = [str(t) for t in (meta.get("tags") or []) if str(t).strip()]
        description = skill.description
        if not description and version is not None:
            description = getattr(version, "purpose", None) or None
        return {
            "id": skill.id,
            "slug": skill.slug,
            "name": skill.name,
            "description": description,
            "capabilities": capabilities,
            "allowed_tools": allowed_tools,
            "rules_markdown": rules_markdown,
            "tags": tags,
        }

    def _team_template_model_to_payload(self, template: TeamTemplateCatalog) -> dict[str, Any]:
        return {
            "id": template.id,
            "slug": template.slug,
            "name": template.name,
            "description": template.description or "",
            "outcome": template.outcome,
            "roles": list(template.roles_json or []),
            "tools": list(template.tools_json or []),
            "autonomy": template.autonomy,
            "visibility": template.visibility,
            "agent_template_slugs": list(template.agent_template_slugs_json or []),
            "canvas_layout": dict(template.canvas_layout_json or {}),
        }

    def _team_profile_model_to_payload(self, profile: TeamProfile) -> dict[str, Any]:
        return {
            "id": profile.id,
            "source_team_template_slug": profile.source_team_template_slug,
            "slug": profile.slug,
            "name": profile.name,
            "description": profile.description or "",
            "outcome": profile.outcome,
            "roles": list(profile.roles_json or []),
            "tools": list(profile.tools_json or []),
            "autonomy": profile.autonomy,
            "visibility": profile.visibility,
            "agent_template_slugs": list(profile.agent_template_slugs_json or []),
            "canvas_layout": dict(profile.canvas_layout_json or {}),
        }

    async def _ensure_unique_agent_slug(
        self, owner_id: str, slug: str, existing_id: str | None
    ) -> None:
        existing = await self.repo.get_agent_by_slug(owner_id, slug)
        if existing and existing.id != existing_id:
            raise HTTPException(status_code=409, detail="An agent with this slug already exists")

    async def _generate_duplicate_slug(self, owner_id: str, base_slug: str) -> str:
        for index in range(2, 100):
            candidate = f"{base_slug}-{index}"
            if await self.repo.get_agent_by_slug(owner_id, candidate) is None:
                return candidate
        raise HTTPException(status_code=409, detail="Could not generate duplicate slug")


class TeamService(TeamServiceMixin):
    """Standalone team service for DI in future work.

    Requires caller-supplied ``db``, ``repo``, ``audit_repo`` and provider
    capability helpers. Mirrors the mixin API; kept minimal until lint-time
    provider validation can be decoupled from orchestration.
    """

    def __init__(
        self,
        db,
        repo,
        audit_repo,
        *,
        provider_model_exists,
        model_capability,
    ) -> None:
        self.db = db
        self.repo = repo
        self.audit_repo = audit_repo
        self._provider_model_exists = provider_model_exists
        self._model_capability = model_capability
