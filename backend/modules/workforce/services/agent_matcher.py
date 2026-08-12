"""Agent matching service for task assignment."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.team.models import AgentProfile
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import AgentAssemblyProposal, AgentMatchResult


class AgentMatcherService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)

    async def match_agents(
        self,
        owner_id: str,
        required_capabilities: list[str],
        required_skills: list[str],
    ) -> list[AgentMatchResult]:
        """
        Match agents to requirements by skill coverage.

        Scoring:
        - AgentSkillAssignment coverage (preferred)
        - Fallback to skills_json slugs
        """
        res = await self.db.execute(select(AgentProfile).where(AgentProfile.owner_id == owner_id))
        agents = list(res.scalars().all())

        matches: list[AgentMatchResult] = []
        req_cap_set = set(c.lower().strip() for c in required_capabilities if c)
        req_skill_set = set(s.lower().strip() for s in required_skills if s)

        for agent in agents:
            if not agent.is_active:
                continue

            assignments = await self.repo.list_agent_skill_assignments(agent.id)
            matched_skills: list[str] = []
            agent_cap_set: set[str] = set()

            for assignment in assignments:
                if not assignment.enabled:
                    continue
                skill = await self.repo.get_skill(assignment.skill_id, owner_id)
                if not skill or skill.status != "active":
                    continue
                matched_skills.append(skill.slug)

                if skill.current_version_id:
                    version = await self.repo.get_skill_version(skill.current_version_id)
                    if version:
                        agent_cap_set.update(
                            c.lower().strip() for c in version.capabilities_json if c
                        )

            if not agent_cap_set:
                agent_cap_set = set(c.lower().strip() for c in agent.capabilities_json if c)

            if not agent_cap_set and not matched_skills:
                continue

            cap_intersection = len(req_cap_set & agent_cap_set) if req_cap_set else 0
            cap_coverage = (
                cap_intersection / len(req_cap_set) if req_cap_set else 0.0
            )

            skill_intersection = len(req_skill_set & set(matched_skills)) if req_skill_set else 0
            skill_coverage = (
                skill_intersection / len(req_skill_set) if req_skill_set else 0.0
            )

            coverage_score = cap_coverage * 0.6 + skill_coverage * 0.4

            missing_capabilities = list(req_cap_set - agent_cap_set)

            if coverage_score < 0.1:
                continue

            explanation_parts = []
            if cap_coverage > 0:
                explanation_parts.append(f"{int(cap_coverage * 100)}% capability coverage")
            if skill_coverage > 0:
                explanation_parts.append(f"{int(skill_coverage * 100)}% skill coverage")
            if matched_skills:
                explanation_parts.append(f"{len(matched_skills)} skills assigned")

            matches.append(
                AgentMatchResult(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    coverage_score=coverage_score,
                    matched_skills=matched_skills,
                    missing_capabilities=missing_capabilities,
                    explanation=", ".join(explanation_parts) if explanation_parts else "low coverage",
                )
            )

        matches.sort(key=lambda m: m.coverage_score, reverse=True)
        return matches[:10]

    async def propose_assembly(
        self,
        owner_id: str,
        required_capabilities: list[str],
        required_skills: list[str],
    ) -> AgentAssemblyProposal | None:
        """
        Propose agent assembly if no single agent has ≥70% coverage.

        Returns assembly proposal with recommended agents and strategy.
        """
        matches = await self.match_agents(owner_id, required_capabilities, required_skills)
        if not matches:
            return None

        best_match = matches[0]
        if best_match.coverage_score >= 0.7:
            return None

        recommended_agents = []
        covered_caps: set[str] = set()
        req_cap_set = set(c.lower().strip() for c in required_capabilities if c)

        for match in matches[:3]:
            if len(recommended_agents) >= 3:
                break

            agent_assignments = await self.repo.list_agent_skill_assignments(match.agent_id)
            agent_caps: set[str] = set()
            for assignment in agent_assignments:
                if not assignment.enabled:
                    continue
                skill = await self.repo.get_skill(assignment.skill_id, owner_id)
                if skill and skill.current_version_id:
                    version = await self.repo.get_skill_version(skill.current_version_id)
                    if version:
                        agent_caps.update(c.lower().strip() for c in version.capabilities_json if c)

            new_coverage = agent_caps - covered_caps
            if new_coverage or not recommended_agents:
                recommended_agents.append(match.agent_id)
                covered_caps.update(agent_caps)

            total_coverage = len(covered_caps & req_cap_set) / len(req_cap_set) if req_cap_set else 0
            if total_coverage >= 0.9:
                break

        assembly_type = "manager_worker" if len(recommended_agents) > 1 else "single_agent"
        rationale = f"No single agent has ≥70% coverage. Proposed {len(recommended_agents)} agents cover {int(len(covered_caps & req_cap_set) / len(req_cap_set) * 100 if req_cap_set else 0)}% of requirements."

        return AgentAssemblyProposal(
            recommended_agents=recommended_agents,
            assembly_type=assembly_type,
            rationale=rationale,
        )
