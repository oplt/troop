"""Agent matching and optional composed-agent creation."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.team.models import AgentProfile, ProjectAgentMembership
from backend.modules.workforce.models import (
    AgentSkillAssignment,
    Skill,
    SkillVersion,
    ToolDefinition,
)
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import AgentAssemblyProposal, AgentMatchResult
from backend.modules.workforce.services.action_policy import (
    DECISION_PROHIBITED,
    ActionPolicyService,
)

_SLUG_RE = re.compile(r"[^a-z0-9-]+")
_HIGH_RISK = {"high", "critical"}


def _slugify(value: str) -> str:
    cleaned = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return (cleaned or "composed-agent")[:255]


class AgentMatcherService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)

    async def _load_agent_coverage(
        self, owner_id: str, agents: list[AgentProfile]
    ) -> dict[str, dict[str, Any]]:
        """Batch-load assignments + skill versions for all agents (no N+1)."""
        if not agents:
            return {}
        agent_ids = [a.id for a in agents]
        assign_res = await self.db.execute(
            select(AgentSkillAssignment).where(
                AgentSkillAssignment.agent_id.in_(agent_ids),
                AgentSkillAssignment.enabled.is_(True),
            )
        )
        assignments = list(assign_res.scalars().all())
        skill_ids = list({a.skill_id for a in assignments})
        skills_by_id: dict[str, Skill] = {}
        if skill_ids:
            skill_res = await self.db.execute(
                select(Skill).where(Skill.id.in_(skill_ids), Skill.owner_id == owner_id)
            )
            skills_by_id = {s.id: s for s in skill_res.scalars().all()}

        version_ids = list(
            {
                *(a.skill_version_id for a in assignments if a.skill_version_id),
                *(s.current_version_id for s in skills_by_id.values() if s.current_version_id),
            }
        )
        versions_by_id: dict[str, SkillVersion] = {}
        if version_ids:
            ver_res = await self.db.execute(
                select(SkillVersion).where(SkillVersion.id.in_(version_ids))
            )
            versions_by_id = {v.id: v for v in ver_res.scalars().all()}

        coverage: dict[str, dict[str, Any]] = {
            a.id: {
                "matched_skills": [],
                "skill_ids": [],
                "caps": set(),
                "tools": set(),
            }
            for a in agents
        }
        for assignment in assignments:
            skill = skills_by_id.get(assignment.skill_id)
            if not skill or skill.status != "active":
                continue
            version = None
            if assignment.version_policy == "pinned" and assignment.skill_version_id:
                version = versions_by_id.get(assignment.skill_version_id)
            elif skill.current_version_id:
                version = versions_by_id.get(skill.current_version_id)
            bucket = coverage[assignment.agent_id]
            bucket["matched_skills"].append(skill.slug)
            bucket["skill_ids"].append(skill.id)
            if version:
                bucket["caps"].update(
                    c.lower().strip() for c in (version.capabilities_json or []) if c
                )
                bucket["tools"].update(t for t in (version.required_tools_json or []) if t)
        return coverage

    async def _project_member_ids(self, project_id: str | None) -> set[str]:
        if not project_id:
            return set()
        result = await self.db.execute(
            select(ProjectAgentMembership.agent_id).where(
                ProjectAgentMembership.project_id == project_id
            )
        )
        return {row[0] for row in result.all() if row[0]}

    async def _resolve_unresolved_tool_permissions(
        self,
        owner_id: str,
        agent_id: str,
        *,
        project_id: str,
        company_id: str | None,
        department_id: str | None,
        requested_tools: list[str],
    ) -> list[dict[str, Any]]:
        grants = await self.repo.list_tool_grants_for_subject("agent", agent_id, effect="allow")
        grant_tool_ids = [g.tool_definition_id for g in grants if g.tool_definition_id]
        grant_tools = await self.repo.list_tool_definitions_by_ids(grant_tool_ids)
        granted_slugs = {t.slug for t in grant_tools if t.slug}

        tool_defs: dict[str, ToolDefinition] = {}
        for tool_slug in requested_tools:
            tool_def = await self.repo.get_tool_definition(tool_slug)
            if tool_def:
                tool_defs[tool_slug] = tool_def

        policy = ActionPolicyService(self.db)
        context = {
            "owner_id": owner_id,
            "project_id": project_id,
            "agent_id": agent_id,
            "company_id": company_id,
            "department_id": department_id,
            "allowed_tools": requested_tools,
        }

        unresolved: list[dict[str, Any]] = []
        for tool_slug in requested_tools:
            tool_def = tool_defs.get(tool_slug)
            risk_level = (tool_def.risk_level if tool_def else "medium") or "medium"
            resolution = await policy.resolve(owner_id, tool_slug, context, tool_slug=tool_slug)
            if resolution.get("decision") == DECISION_PROHIBITED:
                unresolved.append(
                    {
                        "tool": tool_slug,
                        "reason": "prohibited_by_action_policy",
                        "risk_level": risk_level,
                    }
                )
                continue
            if tool_slug not in granted_slugs:
                unresolved.append(
                    {
                        "tool": tool_slug,
                        "reason": "missing_tool_grant",
                        "risk_level": risk_level,
                    }
                )
        return unresolved

    async def match_agents(
        self,
        owner_id: str,
        required_capabilities: list[str],
        required_skills: list[str],
        *,
        required_tools: list[str] | None = None,
        project_id: str | None = None,
    ) -> list[AgentMatchResult]:
        res = await self.db.execute(select(AgentProfile).where(AgentProfile.owner_id == owner_id))
        agents = [a for a in res.scalars().all() if a.is_active]
        coverage_map = await self._load_agent_coverage(owner_id, agents)
        project_members = await self._project_member_ids(project_id)

        matches: list[AgentMatchResult] = []
        req_cap_set = {c.lower().strip() for c in required_capabilities if c}
        req_skill_set = {s.lower().strip() for s in required_skills if s}
        req_tool_set = {t.lower().strip() for t in (required_tools or []) if t}

        for agent in agents:
            cov = coverage_map.get(agent.id) or {
                "matched_skills": [],
                "skill_ids": [],
                "caps": set(),
                "tools": set(),
            }
            agent_cap_set: set[str] = set(cov["caps"])
            if not agent_cap_set:
                agent_cap_set = {c.lower().strip() for c in (agent.capabilities_json or []) if c}
            matched_skills = list(cov["matched_skills"])
            agent_tools = set(cov["tools"]) | {
                t.lower().strip() for t in (agent.allowed_tools_json or []) if t
            }

            if not agent_cap_set and not matched_skills:
                continue

            cap_coverage = (
                len(req_cap_set & agent_cap_set) / len(req_cap_set) if req_cap_set else 0.0
            )
            skill_coverage = (
                len(req_skill_set & set(matched_skills)) / len(req_skill_set)
                if req_skill_set
                else 0.0
            )
            tool_coverage = (
                len(req_tool_set & agent_tools) / len(req_tool_set) if req_tool_set else 0.0
            )
            coverage_score = cap_coverage * 0.5 + skill_coverage * 0.22 + tool_coverage * 0.18
            if not req_skill_set and not req_tool_set:
                coverage_score = cap_coverage

            project_bonus = 0.1 if project_id and agent.id in project_members else 0.0
            coverage_score = min(1.0, coverage_score + project_bonus)

            missing_capabilities = sorted(req_cap_set - agent_cap_set)
            if coverage_score < 0.1:
                continue

            parts: list[str] = []
            if req_cap_set:
                parts.append(f"capability coverage {cap_coverage:.0%}")
            if req_skill_set:
                parts.append(f"skill coverage {skill_coverage:.0%}")
            if req_tool_set:
                parts.append(f"tool coverage {tool_coverage:.0%}")
            if project_id and agent.id in project_members:
                parts.append("project member")
            if matched_skills:
                parts.append(f"{len(matched_skills)} assigned skills")
            parts.append("historical success: not enough historical data")

            matches.append(
                AgentMatchResult(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    coverage_score=coverage_score,
                    score=coverage_score,
                    matched_skills=matched_skills,
                    covered_capabilities=sorted(req_cap_set & agent_cap_set),
                    missing_capabilities=missing_capabilities,
                    explanation="; ".join(parts),
                )
            )

        matches.sort(key=lambda m: m.coverage_score, reverse=True)
        return matches[:10]

    async def propose_assembly(
        self,
        owner_id: str,
        required_capabilities: list[str],
        required_skills: list[str],
        *,
        required_tools: list[str] | None = None,
        skill_ids: list[str] | None = None,
        task_title: str | None = None,
        project_id: str | None = None,
    ) -> AgentAssemblyProposal | None:
        matches = await self.match_agents(
            owner_id,
            required_capabilities,
            required_skills,
            required_tools=required_tools,
            project_id=project_id,
        )
        req_cap_set = {c.lower().strip() for c in required_capabilities if c}
        tools = list(required_tools or [])

        if matches and matches[0].coverage_score >= 0.7:
            best = matches[0]
            return AgentAssemblyProposal(
                recommended_agents=[best.agent_id],
                assembly_type="single_agent",
                rationale=(
                    f"Existing agent `{best.agent_name}` covers requirements "
                    f"({best.coverage_score:.0%} coverage). Prefer reuse over creation."
                ),
                proposed_name=best.agent_name,
                proposed_slug=_slugify(best.agent_name),
                skill_ids=skill_ids or [],
                skill_slugs=best.matched_skills,
                capabilities=list(required_capabilities),
                tools=tools,
            )

        recommended_agents = [m.agent_id for m in matches[:3]]
        covered: set[str] = set()
        for m in matches[:3]:
            covered.update(c.lower() for c in m.covered_capabilities)
        team_coverage = len(covered & req_cap_set) / len(req_cap_set) if req_cap_set else 0.0

        base_name = (task_title or "Composed workforce agent").strip()[:80]
        proposed_name = f"{base_name} Agent" if base_name else "Composed Agent"
        assembly_type = "manager_worker" if len(recommended_agents) > 1 else "create_agent"
        if team_coverage < 0.5 or not recommended_agents:
            assembly_type = "create_agent"

        rationale = (
            "No single agent has ≥70% coverage. "
            f"Proposed composition covers {team_coverage:.0%} of required capabilities. "
            "Create a composed agent with matched SkillVersions when reuse is insufficient."
        )
        return AgentAssemblyProposal(
            recommended_agents=recommended_agents,
            assembly_type=assembly_type,
            rationale=rationale,
            proposed_name=proposed_name,
            proposed_slug=_slugify(proposed_name),
            skill_ids=skill_ids or [],
            skill_slugs=[],
            capabilities=list(required_capabilities),
            tools=tools,
        )

    async def create_composed_agent(
        self,
        user: Any,
        *,
        project_id: str,
        proposal: AgentAssemblyProposal,
        name: str | None = None,
        slug: str | None = None,
        activate: bool = False,
        skill_ids: list[str] | None = None,
        company_id: str | None = None,
        department_id: str | None = None,
    ) -> AgentProfile:
        """Create AgentProfile + AgentSkillAssignment rows from a proposal."""
        from backend.modules.team.service import TeamService

        team = TeamService(self.db)
        agent_name = (name or proposal.proposed_name or "Composed Agent").strip()
        agent_slug = _slugify(slug or proposal.proposed_slug or agent_name)
        tools = list(proposal.tools or [])
        caps = list(proposal.capabilities or [])

        agent = await team.create_agent(
            user,
            {
                "name": agent_name,
                "slug": agent_slug,
                "role": "worker",
                "description": proposal.rationale[:500],
                "mission_markdown": proposal.rationale,
                "system_prompt": (
                    f"You are {agent_name}. Complete assigned tasks using your skills and tools."
                ),
                "rules_markdown": "",
                "capabilities": caps,
                "allowed_tools": tools,
                "skills": [],
                "project_id": project_id,
                "is_active": False,
                "model_policy": {},
                "memory_policy": {"scope": "project"},
                "metadata": {
                    "assembled_by": "workforce.agent_matcher",
                    "assembly_type": proposal.assembly_type,
                },
            },
        )

        ids = skill_ids if skill_ids is not None else list(proposal.skill_ids or [])
        uncovered: list[str] = []
        assigned = 0
        for idx, skill_id in enumerate(ids):
            skill = await self.repo.get_skill(skill_id, user.id)
            if not skill or skill.status not in {"active", "testing"}:
                uncovered.append(str(skill_id))
                continue
            await self.repo.create_agent_skill_assignment(
                agent_id=agent.id,
                skill_id=skill.id,
                skill_version_id=skill.current_version_id,
                version_policy="latest_active",
                priority=idx,
                enabled=True,
            )
            assigned += 1

        # Ensure project membership
        existing = await team.repo.get_project_membership(project_id, agent.id)
        if existing is None:
            await team.repo.create_project_membership(
                project_id=project_id,
                agent_id=agent.id,
            )

        # Resolve provider / model policy when empty
        if not agent.model_policy_json:
            from backend.modules.workforce.services.provider_resolution import (
                resolve_owner_provider,
            )

            provider = await resolve_owner_provider(
                self.db, user.id, project_id=project_id, purpose="default"
            )
            if provider:
                agent.model_policy_json = {
                    "provider_config_id": provider.id,
                    "model": provider.default_model,
                }
                agent.provider_config_id = getattr(agent, "provider_config_id", None) or provider.id

        unresolved = await self._resolve_unresolved_tool_permissions(
            user.id,
            agent.id,
            project_id=project_id,
            company_id=company_id,
            department_id=department_id,
            requested_tools=tools,
        )
        high_risk_unresolved = [
            item for item in unresolved if (item.get("risk_level") or "").lower() in _HIGH_RISK
        ]

        should_activate = False
        activation_reason = "inactive_by_default"
        if activate:
            if not unresolved:
                should_activate = True
                activation_reason = "all_tools_resolved"
            elif not high_risk_unresolved:
                should_activate = True
                activation_reason = "activated_with_low_risk_unresolved_tools"
            else:
                should_activate = False
                activation_reason = "blocked_unresolved_high_risk_tools"

        agent.is_active = should_activate

        meta = dict(agent.metadata_json or {})
        meta["uncovered_skill_ids"] = uncovered
        meta["assigned_skill_count"] = assigned
        meta["unresolved_tool_permissions"] = unresolved
        meta["activation_requested"] = bool(activate)
        meta["activation_reason"] = activation_reason
        agent.metadata_json = meta

        await self.db.commit()
        await self.db.refresh(agent)
        return agent
