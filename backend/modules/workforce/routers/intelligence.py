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
    use_llm: bool = False,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> TaskAnalysisResponse:
    """Analyze a task and extract requirements."""
    # Verify task ownership via project
    res = await db.execute(
        select(OrchestratorTask).where(OrchestratorTask.id == task_id)
    )
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    
    project_res = await db.execute(
        select(OrchestratorProject).where(OrchestratorProject.id == task.project_id)
    )
    project = project_res.scalar_one_or_none()
    if not project or project.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="access denied")
    
    service = TaskAnalyzerService(db)
    analysis = await service.analyze_task(
        task_id=task_id,
        owner_id=user.id,
        use_llm=use_llm,
        model_name=None,
        provider=None,
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
    res = await db.execute(
        select(OrchestratorTask).where(OrchestratorTask.id == task_id)
    )
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
    """Find matching skills for a task's requirements."""
    # Verify task ownership via project
    res = await db.execute(
        select(OrchestratorTask).where(OrchestratorTask.id == task_id)
    )
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no analysis found - run analyze first")
    
    matcher_service = SkillMatcherService(db)
    matches = await matcher_service.match_skills(
        owner_id=user.id,
        required_capabilities=analysis.required_capabilities_json,
        required_tools=analysis.required_tools_json,
        task_scope="task",
    )
    
    # Convert to frontend format
    match_results = [
        SkillMatchResult(
            skill_id=m.skill_id,
            skill_slug=m.skill_slug,
            skill_name=m.skill_name,
            score=m.score,
            explanation=m.explanation,
            matched_capabilities=m.matched_capabilities,
            scope="task",
            status="active",
        )
        for m in matches
    ]
    
    # Categorize requirements by coverage
    covered = []
    partial = []
    missing = list(analysis.required_capabilities_json)
    
    for match in matches:
        if match.score >= 0.8:
            for cap in match.matched_capabilities:
                if cap in missing:
                    covered.append({"capability": cap, "skill_id": match.skill_id})
                    missing.remove(cap)
        elif match.score >= 0.4:
            for cap in match.matched_capabilities:
                if cap in missing:
                    partial.append({"capability": cap, "skill_id": match.skill_id})
    
    missing_dicts = [{"capability": c} for c in missing]
    
    return GapDetectionResult(
        covered=covered,
        partial=partial,
        missing=missing_dicts,
        matches=match_results,
    )


@router.post("/tasks/{task_id}/generate-skills", response_model=list[SkillDraftResponse])
async def generate_missing_skills(
    task_id: str,
    use_llm: bool = False,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[SkillDraftResponse]:
    """Generate skill drafts for missing requirements."""
    # Verify task ownership via project
    res = await db.execute(
        select(OrchestratorTask).where(OrchestratorTask.id == task_id)
    )
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no analysis found - run analyze first")
    requirements = await repo.list_task_requirements(analysis.id)
    missing_reqs = [
        {
            "kind": req.kind,
            "key": req.key,
            "label": req.label,
            "description": req.description,
        }
        for req in requirements
        if req.coverage_status == "missing"
    ]
    # Fallback: if requirements rows empty, use analysis capability list
    if not missing_reqs:
        missing_reqs = [
            {"kind": "capability", "key": cap, "label": cap.replace("_", " "), "description": ""}
            for cap in (analysis.required_capabilities_json or [])
        ]
    
    if not missing_reqs:
        return []
    
    generator_service = SkillGeneratorService(db)
    result = await generator_service.generate_skills(
        owner_id=user.id,
        company_id=project.company_id,
        missing_requirements=missing_reqs,
        use_llm=use_llm,
        model_name=None,
        provider=None,
    )
    
    # Fetch the created drafts
    drafts = []
    for draft_info in result.drafts:
        draft = await repo.get_skill_draft(draft_info["id"], user.id)
        if draft:
            drafts.append(SkillDraftResponse.model_validate(draft))
    
    return drafts


@router.get("/tasks/{task_id}/agent-matches", response_model=list[AgentMatchResult])
async def find_agent_matches(
    task_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentMatchResult]:
    """Find agents that match task requirements."""
    # Verify task ownership via project
    res = await db.execute(
        select(OrchestratorTask).where(OrchestratorTask.id == task_id)
    )
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no analysis found - run analyze first")
    
    matcher_service = AgentMatcherService(db)
    matches = await matcher_service.match_agents(
        owner_id=user.id,
        required_capabilities=analysis.required_capabilities_json,
        required_skills=[],
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
    """Propose an agent assembly for a task."""
    # Verify task ownership via project
    res = await db.execute(
        select(OrchestratorTask).where(OrchestratorTask.id == task_id)
    )
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
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no analysis found - run analyze first")
    
    matcher_service = AgentMatcherService(db)
    proposal = await matcher_service.propose_assembly(
        owner_id=user.id,
        required_capabilities=analysis.required_capabilities_json,
        required_skills=[],
    )
    
    if not proposal:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="no suitable agents found for assembly",
        )
    
    return proposal


@router.post("/tasks/{task_id}/recommend-workforce")
async def recommend_workforce(
    task_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get comprehensive workforce recommendations for a task (placeholder)."""
    # Verify task ownership via project
    res = await db.execute(
        select(OrchestratorTask).where(OrchestratorTask.id == task_id)
    )
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    
    project_res = await db.execute(
        select(OrchestratorProject).where(OrchestratorProject.id == task.project_id)
    )
    project = project_res.scalar_one_or_none()
    if not project or project.owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="access denied")
    
    # TODO: Implement comprehensive recommendation logic
    return {"status": "placeholder", "task_id": task_id}


# ─── Project Intelligence ───────────────────────────────────────

@router.post("/projects/{project_id}/analyze", response_model=ProjectAnalysisResponse)
async def analyze_project(
    project_id: str,
    use_llm: bool = False,
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
    analysis = await service.analyze_project(
        project_id=project_id,
        owner_id=user.id,
        use_llm=use_llm,
        model_name=None,
        provider=None,
    )
    return analysis
