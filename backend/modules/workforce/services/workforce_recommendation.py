"""Workforce recommendation orchestration — compose analysis, skills, agents."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.services.agent_matcher import AgentMatcherService
from backend.modules.workforce.services.skill_matcher import SkillMatcherService


class WorkforceRecommendationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)
        self.skill_matcher = SkillMatcherService(db)
        self.agent_matcher = AgentMatcherService(db)

    async def recommend(
        self,
        *,
        owner_id: str,
        task_id: str,
        project: Any,
        task: Any,
    ) -> dict[str, Any]:
        analysis = await self.repo.get_latest_task_analysis(task_id)
        if analysis is None:
            return {
                "status": "needs_analysis",
                "task_id": task_id,
                "warnings": ["Run POST /tasks/{id}/analyze before recommend-workforce"],
            }

        requirements = await self.repo.list_task_requirements(analysis.id)
        caps = list(analysis.required_capabilities_json or [])
        tools = list(analysis.required_tools_json or [])

        matches = await self.skill_matcher.match_skills(
            owner_id=owner_id,
            required_capabilities=caps,
            required_tools=tools,
            task_scope="task",
            project_id=getattr(task, "project_id", None),
            task_id=task_id,
            company_id=getattr(project, "company_id", None),
            required_knowledge=list(analysis.knowledge_requirements_json or []),
            task_risk_level=analysis.risk_level,
        )

        # Persist gap coverage if requirements exist
        existing_skills: list[dict[str, Any]] = []
        missing_skills: list[dict[str, Any]] = []
        partial_skills: list[dict[str, Any]] = []
        covered_skill_ids: list[str] = []

        if requirements:
            for req in requirements:
                if req.kind != "capability":
                    continue
                key = (req.key or "").lower().strip()
                best = None
                best_score = 0.0
                for match in matches:
                    matched_caps = {c.lower().strip() for c in (match.matched_capabilities or [])}
                    score = float(match.score or 0)
                    if key in matched_caps and score >= best_score:
                        best = match
                        best_score = score
                if best and best_score >= 0.55:
                    req.coverage_status = "covered"
                    req.matched_skill_id = best.skill_id
                    req.match_score = best_score
                    req.match_explanation = best.explanation
                    existing_skills.append(
                        {
                            "capability": req.key,
                            "skill_id": best.skill_id,
                            "skill_slug": best.skill_slug,
                            "score": best_score,
                        }
                    )
                    covered_skill_ids.append(best.skill_id)
                elif best and best_score >= 0.3:
                    req.coverage_status = "partial"
                    req.matched_skill_id = best.skill_id
                    req.match_score = best_score
                    req.match_explanation = best.explanation
                    partial_skills.append(
                        {
                            "capability": req.key,
                            "skill_id": best.skill_id,
                            "score": best_score,
                        }
                    )
                else:
                    req.coverage_status = "missing"
                    req.matched_skill_id = None
                    req.match_score = None
                    req.match_explanation = None
                    missing_skills.append({"capability": req.key, "kind": req.kind})
            await self.db.commit()
        else:
            # No requirement rows — derive from matches vs analysis caps
            covered_caps: set[str] = set()
            for match in matches:
                if match.score >= 0.55:
                    existing_skills.append(
                        {
                            "skill_id": match.skill_id,
                            "skill_slug": match.skill_slug,
                            "score": match.score,
                            "capabilities": match.matched_capabilities,
                        }
                    )
                    covered_skill_ids.append(match.skill_id)
                    covered_caps.update(c.lower() for c in (match.matched_capabilities or []))
            for cap in caps:
                if cap.lower().strip() not in covered_caps:
                    missing_skills.append({"capability": cap, "kind": "capability"})

        agent_matches = await self.agent_matcher.match_agents(
            owner_id,
            required_capabilities=caps,
            required_skills=[m.skill_slug for m in matches[:5]],
            required_tools=tools,
            project_id=getattr(task, "project_id", None),
        )
        proposal = await self.agent_matcher.propose_assembly(
            owner_id,
            required_capabilities=caps,
            required_skills=[m.skill_slug for m in matches[:5]],
            required_tools=tools,
            skill_ids=list(dict.fromkeys(covered_skill_ids)),
            task_title=getattr(task, "title", None),
            project_id=getattr(task, "project_id", None),
        )

        warnings: list[str] = []
        if missing_skills:
            warnings.append(
                f"{len(missing_skills)} capability gap(s) — generate skill drafts before execution"
            )
        if not agent_matches:
            warnings.append("No active agents matched — create or activate agents")
        if (analysis.risk_level or "").lower() in {"high", "critical"}:
            warnings.append("High/critical risk — human review recommended before autonomy")

        recommended_agent = agent_matches[0] if agent_matches else None
        alternate = agent_matches[1:4] if len(agent_matches) > 1 else []

        review_reqs = list(analysis.review_requirements_json or [])
        approval_reqs = list(analysis.approval_requirements_json or [])
        if not review_reqs and (analysis.risk_level or "").lower() in {
            "medium",
            "high",
            "critical",
        }:
            review_reqs = ["human_review"]
        if not approval_reqs and (analysis.risk_level or "").lower() in {"high", "critical"}:
            approval_reqs = ["human_approval"]

        workflow = {
            "suggested": True,
            "entry": "analyze_complete",
            "nodes": [
                {"id": "skills", "type": "skill", "label": "Ensure skill coverage"},
                {"id": "assign", "type": "agent", "label": "Assign or create agent"},
                {"id": "execute", "type": "agent", "label": "Execute task"},
                {"id": "review", "type": "approval", "label": "Review / approve"},
            ],
            "edges": [
                {"from": "skills", "to": "assign"},
                {"from": "assign", "to": "execute"},
                {"from": "execute", "to": "review"},
            ],
        }

        return {
            "status": "ok",
            "task_id": task_id,
            "analysis": {
                "id": analysis.id,
                "objective": analysis.objective,
                "task_category": analysis.task_category,
                "risk_level": analysis.risk_level,
                "autonomy_recommendation": analysis.autonomy_recommendation,
                "required_capabilities": caps,
                "required_tools": tools,
                "analyzer_version": analysis.analyzer_version,
                "model_name": analysis.model_name,
            },
            "skill_plan": {
                "existing_skills": existing_skills,
                "partial_skills": partial_skills,
                "missing_skills": missing_skills,
                "drafts_to_generate": [
                    {"capability": m.get("capability"), "action": "generate_skill_draft"}
                    for m in missing_skills
                ],
            },
            "execution_plan": {
                "recommended_agent": (
                    {
                        "agent_id": recommended_agent.agent_id,
                        "agent_name": recommended_agent.agent_name,
                        "coverage_score": recommended_agent.coverage_score,
                        "explanation": recommended_agent.explanation,
                        "missing_capabilities": recommended_agent.missing_capabilities,
                    }
                    if recommended_agent
                    else None
                ),
                "alternate_agents": [
                    {
                        "agent_id": a.agent_id,
                        "agent_name": a.agent_name,
                        "coverage_score": a.coverage_score,
                        "explanation": a.explanation,
                    }
                    for a in alternate
                ],
                "recommended_team": proposal.recommended_agents if proposal else [],
                "new_agent_proposal": (
                    {
                        "assembly_type": proposal.assembly_type,
                        "proposed_name": proposal.proposed_name,
                        "proposed_slug": proposal.proposed_slug,
                        "rationale": proposal.rationale,
                        "skill_ids": proposal.skill_ids,
                        "capabilities": proposal.capabilities,
                        "tools": proposal.tools,
                        "historical_success": "Not enough historical data",
                    }
                    if proposal
                    else None
                ),
            },
            "workflow": workflow,
            "reviewer": {
                "requirements": review_reqs,
                "recommendation": "human_reviewer" if review_reqs else "optional",
            },
            "approvals": {
                "requirements": approval_reqs,
                "required": bool(approval_reqs),
            },
            "warnings": warnings,
        }
