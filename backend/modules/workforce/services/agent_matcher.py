"""Agent matching and optional composed-agent creation."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import TaskRun
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.team.models import AgentProfile, ProjectAgentMembership
from backend.modules.workforce.models import (
    AgentSkillAssignment,
    Skill,
    SkillEvaluation,
    SkillUsageStat,
    SkillVersion,
)
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import AgentAssemblyProposal, AgentMatchResult
from backend.modules.workforce.services.effective_permissions import (
    resolve_effective_tool_permissions,
)

_SLUG_RE = re.compile(r"[^a-z0-9-]+")
_HIGH_RISK = {"high", "critical"}
_ACTIVE_RUN_STATUSES = ("queued", "in_progress", "blocked")
_RISK_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _slugify(value: str) -> str:
    cleaned = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return (cleaned or "composed-agent")[:255]


def _risk_compat_score(
    task_risk: str | None, agent_tools: set[str], by_tool: dict[str, Any]
) -> float:
    if not task_risk:
        return 0.7
    task_rank = _RISK_RANK.get(task_risk.lower(), 1)
    if not agent_tools:
        return 0.6
    worst = 0.0
    for slug in agent_tools:
        sources = (by_tool.get(slug) or {}).get("sources") or []
        tool_rank = 1
        for src in sources:
            if src.get("type") == "policy" and src.get("risk_level"):
                tool_rank = max(tool_rank, _RISK_RANK.get(str(src["risk_level"]).lower(), 1))
        if tool_rank <= task_rank:
            worst = max(worst, 1.0)
        else:
            worst = max(worst, max(0.0, 1.0 - (tool_rank - task_rank) * 0.25))
    return worst or 0.6


def _resolve_model_slug(agent: AgentProfile) -> str:
    policy = dict(agent.model_policy_json or {})
    return str(policy.get("model") or "").strip().lower()


def _model_capability_score(
    agent: AgentProfile,
    capabilities_by_slug: dict[str, Any],
    *,
    needs_tools: bool,
) -> tuple[float, str]:
    """Soft score from ModelCapability: tools support, cost, context, latency."""
    model_slug = _resolve_model_slug(agent)
    if not model_slug:
        return 0.5, "no model policy"
    cap = capabilities_by_slug.get(model_slug)
    if cap is None:
        for slug, item in capabilities_by_slug.items():
            if model_slug in slug or slug in model_slug:
                cap = item
                break
    if cap is None:
        return 0.45, "model capability unknown"

    meta = dict(getattr(cap, "metadata_json", None) or {})
    cost = float(getattr(cap, "cost_per_1k_input", 0.0) or 0.0) + float(
        getattr(cap, "cost_per_1k_output", 0.0) or 0.0
    )
    ctx = int(getattr(cap, "max_context_tokens", 0) or 0)
    latency_ms = int(meta.get("latency_ms") or meta.get("p50_latency_ms") or 0)
    supports_tools = bool(getattr(cap, "supports_tools", False))

    cost_score = max(0.0, 1.0 - min(cost * 2.0, 1.0))
    ctx_score = min(1.0, ctx / 128_000) if ctx else 0.4
    latency_score = max(0.0, 1.0 - min(latency_ms / 5000.0, 1.0)) if latency_ms else 0.6
    tools_score = 1.0 if supports_tools else (0.35 if needs_tools else 0.75)

    score = cost_score * 0.25 + ctx_score * 0.25 + latency_score * 0.20 + tools_score * 0.30
    detail = (
        f"model={model_slug}; cost~{cost:.4f}/1k; ctx={ctx}; "
        f"latency~{latency_ms or 'n/a'}ms; tools={supports_tools}"
    )
    return score, detail


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
                "requested_tools": set(),
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
                bucket["requested_tools"].update(
                    t.lower().strip() for t in (version.required_tools_json or []) if t
                )
        return coverage

    async def _active_run_counts(self, agent_ids: list[str]) -> dict[str, int]:
        if not agent_ids:
            return {}
        result = await self.db.execute(
            select(TaskRun.worker_agent_id, func.count(TaskRun.id))
            .where(
                TaskRun.worker_agent_id.in_(agent_ids),
                TaskRun.status.in_(_ACTIVE_RUN_STATUSES),
            )
            .group_by(TaskRun.worker_agent_id)
        )
        return {str(agent_id): int(count) for agent_id, count in result.all() if agent_id}

    async def _skill_success_scores(
        self, skill_ids: list[str], versions_by_skill: dict[str, str | None]
    ) -> dict[str, float]:
        if not skill_ids:
            return {}
        stats = await self.repo.list_skill_usage_stats(skill_ids)
        by_skill: dict[str, SkillUsageStat] = {}
        for stat in stats:
            expected_version = versions_by_skill.get(stat.skill_id)
            if expected_version and stat.skill_version_id != expected_version:
                continue
            existing = by_skill.get(stat.skill_id)
            if existing is None or stat.run_count > existing.run_count:
                by_skill[stat.skill_id] = stat

        eval_res = await self.db.execute(
            select(SkillEvaluation)
            .where(SkillEvaluation.skill_id.in_(skill_ids))
            .order_by(SkillEvaluation.created_at.desc())
            .limit(200)
        )
        eval_success: dict[str, list[bool]] = {}
        for ev in eval_res.scalars().all():
            if ev.skill_id not in eval_success:
                eval_success[ev.skill_id] = []
            if len(eval_success[ev.skill_id]) < 5:
                eval_success[ev.skill_id].append(bool(ev.success))

        scores: dict[str, float] = {}
        for skill_id in skill_ids:
            stat = by_skill.get(skill_id)
            if stat and stat.run_count > 0:
                scores[skill_id] = stat.success_count / stat.run_count
            elif eval_success.get(skill_id):
                scores[skill_id] = sum(eval_success[skill_id]) / len(eval_success[skill_id])
            else:
                scores[skill_id] = 0.5
        return scores

    async def _project_member_ids(self, project_id: str | None) -> set[str]:
        if not project_id:
            return set()
        result = await self.db.execute(
            select(ProjectAgentMembership.agent_id).where(
                ProjectAgentMembership.project_id == project_id
            )
        )
        return {row[0] for row in result.all() if row[0]}

    async def match_agents(
        self,
        owner_id: str,
        required_capabilities: list[str],
        required_skills: list[str],
        *,
        required_tools: list[str] | None = None,
        project_id: str | None = None,
        company_id: str | None = None,
        department_id: str | None = None,
        task_risk_level: str | None = None,
    ) -> list[AgentMatchResult]:
        res = await self.db.execute(select(AgentProfile).where(AgentProfile.owner_id == owner_id))
        agents = [a for a in res.scalars().all() if a.is_active]
        coverage_map = await self._load_agent_coverage(owner_id, agents)
        project_members = await self._project_member_ids(project_id)
        workload = await self._active_run_counts([a.id for a in agents])

        all_skill_ids = list(
            {sid for cov in coverage_map.values() for sid in cov.get("skill_ids", [])}
        )
        skills_by_id: dict[str, Skill] = {}
        if all_skill_ids:
            skill_res = await self.db.execute(
                select(Skill).where(Skill.id.in_(all_skill_ids), Skill.owner_id == owner_id)
            )
            skills_by_id = {s.id: s for s in skill_res.scalars().all()}
        versions_by_skill_global = {
            sid: skills_by_id[sid].current_version_id
            for sid in all_skill_ids
            if sid in skills_by_id
        }
        success_by_skill = await self._skill_success_scores(all_skill_ids, versions_by_skill_global)

        req_cap_set = {c.lower().strip() for c in required_capabilities if c}
        req_skill_set = {s.lower().strip() for s in required_skills if s}
        req_tool_set = {t.lower().strip() for t in (required_tools or []) if t}

        orch_repo = OrchestrationRepository(self.db)
        try:
            model_caps = await orch_repo.list_model_capabilities_for_owner(owner_id)
        except Exception:
            model_caps = []
        capabilities_by_slug = {str(c.model_slug).lower(): c for c in model_caps if c.model_slug}
        needs_tools = bool(req_tool_set)

        matches: list[AgentMatchResult] = []

        for agent in agents:
            cov = coverage_map.get(agent.id) or {
                "matched_skills": [],
                "skill_ids": [],
                "caps": set(),
                "requested_tools": set(),
            }
            agent_cap_set: set[str] = set(cov["caps"])
            if not agent_cap_set:
                agent_cap_set = {c.lower().strip() for c in (agent.capabilities_json or []) if c}
            matched_skills = list(cov["matched_skills"])
            skill_ids = list(dict.fromkeys(cov["skill_ids"]))
            declared_tools = {t.lower().strip() for t in (agent.allowed_tools_json or []) if t}

            permissions = await resolve_effective_tool_permissions(
                self.db,
                owner_id=owner_id,
                agent_id=agent.id,
                project_id=project_id,
                company_id=company_id,
                department_id=department_id,
                skill_ids=skill_ids,
                tool_slugs=list(req_tool_set) if req_tool_set else None,
                declared_tools=sorted(declared_tools),
            )
            effective_tools = {t.lower() for t in permissions["effective_allow"]}
            unavailable = list(permissions["requested_unavailable"])

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
                len(req_tool_set & effective_tools) / len(req_tool_set) if req_tool_set else 0.0
            )
            coverage_score = cap_coverage * 0.35 + skill_coverage * 0.22 + tool_coverage * 0.15
            if not req_skill_set and not req_tool_set:
                coverage_score = cap_coverage * 0.65

            project_bonus = 0.05 if project_id and agent.id in project_members else 0.0
            active_count = workload.get(agent.id, 0)
            load_score = max(0.0, 1.0 - min(active_count, 5) * 0.12)
            load_bonus = load_score * 0.07

            success_scores = {
                sid: success_by_skill[sid] for sid in skill_ids if sid in success_by_skill
            }
            history_score = (
                sum(success_scores.values()) / len(success_scores) if success_scores else 0.5
            )
            history_bonus = history_score * 0.12

            risk_bonus = (
                _risk_compat_score(task_risk_level, effective_tools, permissions["by_tool"]) * 0.04
            )
            model_score, model_detail = _model_capability_score(
                agent,
                capabilities_by_slug,
                needs_tools=needs_tools,
            )
            model_bonus = model_score * 0.08

            coverage_score = min(
                1.0,
                coverage_score
                + project_bonus
                + load_bonus
                + history_bonus
                + risk_bonus
                + model_bonus,
            )

            missing_capabilities = sorted(req_cap_set - agent_cap_set)
            if coverage_score < 0.1:
                continue

            parts: list[str] = []
            if req_cap_set:
                parts.append(f"capability coverage {cap_coverage:.0%}")
            if req_skill_set:
                parts.append(f"skill coverage {skill_coverage:.0%}")
            if req_tool_set:
                parts.append(f"effective tool coverage {tool_coverage:.0%}")
            if unavailable:
                parts.append(f"unavailable tools: {', '.join(unavailable[:5])}")
            if project_id and agent.id in project_members:
                parts.append("project member")
            if matched_skills:
                parts.append(f"{len(matched_skills)} assigned skills")
            if active_count:
                parts.append(f"active runs {active_count}")
            if success_scores:
                parts.append(f"skill success {int(history_score * 100)}%")
            else:
                parts.append("historical success: not enough historical data")
            parts.append(f"model fit {int(model_score * 100)}% ({model_detail})")

            matches.append(
                AgentMatchResult(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    coverage_score=coverage_score,
                    score=coverage_score,
                    matched_skills=matched_skills,
                    covered_capabilities=sorted(req_cap_set & agent_cap_set),
                    missing_capabilities=missing_capabilities,
                    effective_tools=sorted(effective_tools),
                    requested_but_unavailable_tools=unavailable,
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
        company_id: str | None = None,
        department_id: str | None = None,
    ) -> AgentAssemblyProposal | None:
        matches = await self.match_agents(
            owner_id,
            required_capabilities,
            required_skills,
            required_tools=required_tools,
            project_id=project_id,
            company_id=company_id,
            department_id=department_id,
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
        assigned_skill_ids: list[str] = []
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
            assigned_skill_ids.append(skill.id)
            assigned += 1

        existing = await team.repo.get_project_membership(project_id, agent.id)
        if existing is None:
            await team.repo.create_project_membership(
                project_id=project_id,
                agent_id=agent.id,
            )

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

        permissions = await resolve_effective_tool_permissions(
            self.db,
            owner_id=user.id,
            agent_id=agent.id,
            project_id=project_id,
            company_id=company_id,
            department_id=department_id,
            skill_ids=assigned_skill_ids,
            tool_slugs=tools,
            declared_tools=tools,
        )
        unresolved = [
            {
                "tool": slug,
                "reason": (permissions["by_tool"].get(slug) or {}).get("effect", "deny"),
                "sources": (permissions["by_tool"].get(slug) or {}).get("sources", []),
            }
            for slug in permissions["requested_unavailable"]
        ]
        high_risk_unresolved = [
            item
            for item in unresolved
            if item["tool"] in tools
            and any(
                src.get("risk_level", "").lower() in _HIGH_RISK
                for src in item.get("sources") or []
                if src.get("type") == "policy"
            )
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
        meta["effective_tool_permissions"] = permissions
        meta["activation_requested"] = bool(activate)
        meta["activation_reason"] = activation_reason
        agent.metadata_json = meta

        await self.db.commit()
        await self.db.refresh(agent)
        return agent
