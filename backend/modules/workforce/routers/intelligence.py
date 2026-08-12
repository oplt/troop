"""Task and project intelligence endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask
from backend.modules.workforce.schemas import (
    AgentAssemblyProposal,
    AgentMatchResult,
    AssembleAgentRequest,
    GapDetectionResult,
    ProjectAnalysisResponse,
    SkillDraftResponse,
    SkillMatchResult,
    TaskAnalysisResponse,
)
from backend.modules.workforce.services.agent_matcher import AgentMatcherService
from backend.modules.workforce.services.project_analyzer import ProjectAnalyzerService
from backend.modules.workforce.services.skill_generator import SkillGeneratorService
from backend.modules.workforce.services.skill_matcher import SkillMatcherService
from backend.modules.workforce.services.task_analyzer import TaskAnalyzerService

router = APIRouter()


# ─── Task Intelligence ──────────────────────────────────────────


@router.post("/tasks/{task_id}/analyze", response_model=TaskAnalysisResponse)
async def analyze_task(
    task_id: str,
    use_llm: bool | None = None,
    deterministic: bool = False,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> TaskAnalysisResponse:
    """Analyze a task and extract requirements using configured providers when available."""
    from backend.modules.workforce.services.provider_resolution import resolve_owner_provider

    res = await db.execute(select(OrchestratorTask).where(OrchestratorTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")

    project_res = await db.execute(
        select(OrchestratorProject).where(OrchestratorProject.id == task.project_id)
    )
    project = project_res.scalar_one_or_none()
    if not project or project.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="access denied")

    provider = None
    if not deterministic:
        provider = await resolve_owner_provider(
            db, user.id, project_id=project.id, purpose="task_analysis"
        )
    # Default: use LLM when a provider is configured unless caller forces heuristics.
    effective_use_llm = (
        use_llm if use_llm is not None else provider is not None
    ) and not deterministic

    service = TaskAnalyzerService(db)
    analysis = await service.analyze_task(
        task_id=task_id,
        owner_id=user.id,
        use_llm=effective_use_llm,
        model_name=(provider.default_model if provider else None),
        provider=provider,
    )
    return analysis


@router.get("/tasks/{task_id}/analysis", response_model=TaskAnalysisResponse)
async def get_task_analysis(
    task_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> TaskAnalysisResponse:
    """Get the latest analysis for a task."""
    # Verify task ownership via project
    res = await db.execute(select(OrchestratorTask).where(OrchestratorTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")

    project_res = await db.execute(
        select(OrchestratorProject).where(OrchestratorProject.id == task.project_id)
    )
    project = project_res.scalar_one_or_none()
    if not project or project.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="access denied")

    from backend.modules.workforce.repository import WorkforceRepository

    repo = WorkforceRepository(db)
    analysis = await repo.get_latest_task_analysis(task_id)
    if not analysis:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no analysis found")

    return TaskAnalysisResponse.model_validate(analysis)


@router.get("/tasks/{task_id}/skill-matches", response_model=GapDetectionResult)
async def find_skill_matches(
    task_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> GapDetectionResult:
    """Find matching skills and persist coverage on TaskRequirement rows."""
    res = await db.execute(select(OrchestratorTask).where(OrchestratorTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")

    project_res = await db.execute(
        select(OrchestratorProject).where(OrchestratorProject.id == task.project_id)
    )
    project = project_res.scalar_one_or_none()
    if not project or project.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="access denied")

    from backend.modules.workforce.repository import WorkforceRepository

    repo = WorkforceRepository(db)
    analysis = await repo.get_latest_task_analysis(task_id)
    if not analysis:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="no analysis found - run analyze first"
        )

    matcher_service = SkillMatcherService(db)
    matches = await matcher_service.match_skills(
        owner_id=user.id,
        required_capabilities=analysis.required_capabilities_json or [],
        required_tools=analysis.required_tools_json or [],
        task_scope="task",
        task_id=task.id,
        project_id=task.project_id,
        company_id=project.company_id,
        required_knowledge=analysis.knowledge_requirements_json or [],
        task_risk_level=analysis.risk_level,
    )

    requirements = await repo.list_task_requirements(analysis.id)
    covered: list[dict] = []
    partial: list[dict] = []
    missing: list[dict] = []

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
            covered.append(
                {
                    "capability": req.key,
                    "skill_id": best.skill_id,
                    "score": best_score,
                }
            )
        elif best and best_score >= 0.3:
            req.coverage_status = "partial"
            req.matched_skill_id = best.skill_id
            req.match_score = best_score
            req.match_explanation = best.explanation
            partial.append(
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
            missing.append({"capability": req.key})

    await db.commit()

    match_results = [
        SkillMatchResult(
            skill_id=m.skill_id,
            skill_slug=m.skill_slug,
            skill_name=m.skill_name,
            score=m.score,
            explanation=m.explanation,
            matched_capabilities=m.matched_capabilities,
            matched_tools=getattr(m, "matched_tools", []) or [],
            capability_overlap=getattr(m, "capability_overlap", 0.0) or 0.0,
            tool_overlap=getattr(m, "tool_overlap", 0.0) or 0.0,
            scope_relevance=getattr(m, "scope_relevance", 0.0) or 0.0,
            status_bonus=getattr(m, "status_bonus", 0.0) or 0.0,
            scope=getattr(m, "scope", "organization") or "organization",
            status=getattr(m, "status", "active") or "active",
        )
        for m in matches
    ]

    return GapDetectionResult(
        covered=covered,
        partial=partial,
        missing=missing,
        matches=match_results,
    )


@router.post("/tasks/{task_id}/generate-skills", response_model=list[SkillDraftResponse])
async def generate_missing_skills(
    task_id: str,
    use_llm: bool | None = None,
    deterministic: bool = False,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[SkillDraftResponse]:
    """Generate skill drafts for missing requirements."""
    # Verify task ownership via project
    res = await db.execute(select(OrchestratorTask).where(OrchestratorTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")

    project_res = await db.execute(
        select(OrchestratorProject).where(OrchestratorProject.id == task.project_id)
    )
    project = project_res.scalar_one_or_none()
    if not project or project.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="access denied")

    from backend.modules.workforce.dto import skill_draft_response
    from backend.modules.workforce.repository import WorkforceRepository

    repo = WorkforceRepository(db)
    analysis = await repo.get_latest_task_analysis(task_id)
    if not analysis:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="no analysis found - run analyze first"
        )
    requirements = await repo.list_task_requirements(analysis.id)
    missing_reqs = [
        {
            "kind": req.kind,
            "key": req.key,
            "label": req.label,
            "description": req.description,
        }
        for req in requirements
        if req.kind == "capability" and req.coverage_status == "missing"
    ]
    # Only fall back to raw analysis caps when no requirement rows exist yet.
    if not requirements:
        missing_reqs = [
            {
                "kind": "capability",
                "key": cap,
                "label": cap.replace("_", " "),
                "description": "",
            }
            for cap in (analysis.required_capabilities_json or [])
        ]

    if not missing_reqs:
        return []

    from backend.modules.workforce.services.provider_resolution import resolve_owner_provider

    provider = None
    if not deterministic:
        provider = await resolve_owner_provider(
            db, user.id, project_id=project.id, purpose="skill_generation"
        )
    effective_use_llm = (
        use_llm if use_llm is not None else provider is not None
    ) and not deterministic
    generator_service = SkillGeneratorService(db)
    result = await generator_service.generate_skills(
        owner_id=user.id,
        company_id=project.company_id,
        missing_requirements=missing_reqs,
        use_llm=bool(effective_use_llm and provider),
        model_name=(provider.default_model if provider else None),
        provider=provider,
    )

    # Fetch the created drafts
    drafts = []
    for draft_info in result.drafts:
        draft = await repo.get_skill_draft(draft_info["id"], user.id)
        if draft:
            drafts.append(skill_draft_response(draft))

    return drafts


@router.get("/tasks/{task_id}/agent-matches", response_model=list[AgentMatchResult])
async def find_agent_matches(
    task_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentMatchResult]:
    """Find agents that match task requirements."""
    # Verify task ownership via project
    res = await db.execute(select(OrchestratorTask).where(OrchestratorTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")

    project_res = await db.execute(
        select(OrchestratorProject).where(OrchestratorProject.id == task.project_id)
    )
    project = project_res.scalar_one_or_none()
    if not project or project.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="access denied")

    from backend.modules.workforce.repository import WorkforceRepository

    repo = WorkforceRepository(db)
    analysis = await repo.get_latest_task_analysis(task_id)
    if not analysis:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="no analysis found - run analyze first"
        )

    requirements = await repo.list_task_requirements(analysis.id)
    matched_skill_slugs: list[str] = []
    for req in requirements:
        if req.matched_skill_id and req.coverage_status in {"covered", "partial"}:
            skill = await repo.get_skill(req.matched_skill_id, user.id)
            if skill:
                matched_skill_slugs.append(skill.slug)

    matcher_service = AgentMatcherService(db)
    matches = await matcher_service.match_agents(
        owner_id=user.id,
        required_capabilities=analysis.required_capabilities_json or [],
        required_skills=matched_skill_slugs,
        required_tools=analysis.required_tools_json or [],
        project_id=task.project_id,
    )

    return [
        AgentMatchResult(
            agent_id=m.agent_id,
            agent_name=m.agent_name,
            score=m.coverage_score,
            explanation=m.explanation,
            covered_capabilities=m.matched_skills,
            missing_capabilities=m.missing_capabilities,
        )
        for m in matches
    ]


@router.post("/tasks/{task_id}/assemble-agent", response_model=AgentAssemblyProposal)
async def assemble_agent(
    task_id: str,
    payload: AssembleAgentRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> AgentAssemblyProposal:
    """Propose or create a composed agent for a task."""
    res = await db.execute(select(OrchestratorTask).where(OrchestratorTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")

    project_res = await db.execute(
        select(OrchestratorProject).where(OrchestratorProject.id == task.project_id)
    )
    project = project_res.scalar_one_or_none()
    if not project or project.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="access denied")

    from backend.modules.workforce.repository import WorkforceRepository

    repo = WorkforceRepository(db)
    analysis = await repo.get_latest_task_analysis(task_id)
    if not analysis:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="no analysis found - run analyze first"
        )

    requirements = await repo.list_task_requirements(analysis.id)
    skill_ids = [
        req.matched_skill_id
        for req in requirements
        if req.matched_skill_id and req.coverage_status in {"covered", "partial"}
    ]

    matcher_service = AgentMatcherService(db)
    proposal = await matcher_service.propose_assembly(
        owner_id=user.id,
        required_capabilities=analysis.required_capabilities_json or [],
        required_skills=[],
        required_tools=analysis.required_tools_json or [],
        skill_ids=list(dict.fromkeys(skill_ids)),
        task_title=task.title,
        project_id=project.id,
    )

    if not proposal:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="no suitable agents found for assembly",
        )

    # Create composed agent when reuse is insufficient or caller supplies a name.
    should_create = proposal.assembly_type == "create_agent" or bool(payload.name)
    if should_create and proposal.assembly_type != "single_agent":
        agent = await matcher_service.create_composed_agent(
            user,
            project_id=project.id,
            proposal=proposal,
            name=payload.name,
            slug=payload.slug,
            activate=payload.activate,
            skill_ids=proposal.skill_ids,
            company_id=project.company_id,
            department_id=project.department_id,
        )
        if payload.assign_to_task:
            task.assigned_agent_id = agent.id
            await db.commit()
        proposal.recommended_agents = [agent.id, *proposal.recommended_agents]
        proposal.proposed_name = agent.name
        proposal.proposed_slug = agent.slug
        proposal.rationale = f"Created agent `{agent.name}` ({agent.id}). " + proposal.rationale

    return proposal


@router.post("/tasks/{task_id}/recommend-workforce")
async def recommend_workforce(
    task_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Compose analysis, skill gaps, agent matches, and workflow recommendations."""
    res = await db.execute(select(OrchestratorTask).where(OrchestratorTask.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")

    project_res = await db.execute(
        select(OrchestratorProject).where(OrchestratorProject.id == task.project_id)
    )
    project = project_res.scalar_one_or_none()
    if not project or project.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="access denied")

    from backend.modules.workforce.services.workforce_recommendation import (
        WorkforceRecommendationService,
    )

    service = WorkforceRecommendationService(db)
    return await service.recommend(
        owner_id=user.id,
        task_id=task_id,
        project=project,
        task=task,
    )


# ─── Project Intelligence ───────────────────────────────────────


@router.post("/projects/{project_id}/analyze", response_model=ProjectAnalysisResponse)
async def analyze_project(
    project_id: str,
    use_llm: bool | None = None,
    deterministic: bool = False,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectAnalysisResponse:
    """Analyze a project and recommend workforce structure."""
    # Verify project ownership
    project_res = await db.execute(
        select(OrchestratorProject).where(OrchestratorProject.id == project_id)
    )
    project = project_res.scalar_one_or_none()
    if not project or project.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="access denied")

    service = ProjectAnalyzerService(db)
    from backend.modules.workforce.services.provider_resolution import resolve_owner_provider

    provider = None
    if not deterministic:
        provider = await resolve_owner_provider(
            db, user.id, project_id=project.id, purpose="project_analysis"
        )
    effective_use_llm = (
        use_llm if use_llm is not None else provider is not None
    ) and not deterministic
    analysis = await service.analyze_project(
        project_id=project_id,
        owner_id=user.id,
        use_llm=bool(effective_use_llm and provider),
        model_name=(provider.default_model if provider else None),
        provider=provider,
    )
    return analysis
