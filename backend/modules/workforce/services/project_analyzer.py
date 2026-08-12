"""Project analysis service for workforce recommendations."""

from __future__ import annotations

import json

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.providers import execute_prompt
from backend.modules.projects.orchestration_models import OrchestratorProject
from backend.modules.workforce.constants import ANALYZER_VERSION
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import ProjectAnalysisOutput, ProjectAnalysisResponse


def _heuristic_project_analyze(project: OrchestratorProject) -> ProjectAnalysisOutput:
    """Heuristic project analyzer for offline testing."""
    goals_lower = (project.goals_markdown or "").lower()

    recommended_tasks: list[dict] = []
    if "research" in goals_lower:
        recommended_tasks.append(
            {
                "title": "Research Phase",
                "description": "Conduct research based on project goals",
                "priority": "high",
            }
        )
    if "implement" in goals_lower or "develop" in goals_lower:
        recommended_tasks.append(
            {
                "title": "Implementation Phase",
                "description": "Implement features based on requirements",
                "priority": "normal",
            }
        )
    if "test" in goals_lower:
        recommended_tasks.append(
            {
                "title": "Testing Phase",
                "description": "Test implemented features",
                "priority": "normal",
            }
        )

    recommended_skills = ["web_research", "general_task_execution"]
    if "code" in goals_lower or "develop" in goals_lower:
        recommended_skills.append("code_modification")

    recommended_agents = []
    recommended_workflow = {
        "type": "sequential",
        "stages": [s["title"] for s in recommended_tasks],
    }

    return ProjectAnalysisOutput(
        recommended_tasks=recommended_tasks,
        recommended_skills=recommended_skills,
        recommended_agents=recommended_agents,
        recommended_workflow=recommended_workflow,
    )


class ProjectAnalyzerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)

    async def analyze_project(
        self,
        project_id: str,
        owner_id: str,
        use_llm: bool = True,
        model_name: str | None = None,
        provider: ProviderConfig | None = None,
    ) -> ProjectAnalysisResponse:
        """
        Analyze project goals and recommend workforce structure.

        Falls back to heuristic if LLM unavailable.
        """
        res = await self.db.execute(
            select(OrchestratorProject).where(OrchestratorProject.id == project_id)
        )
        project = res.scalar_one_or_none()
        if project is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="project not found")

        if use_llm and provider:
            try:
                analysis_output = await self._llm_analyze(project, model_name, provider)
                model_used = model_name or provider.default_model
            except Exception:
                analysis_output = _heuristic_project_analyze(project)
                model_used = None
        else:
            analysis_output = _heuristic_project_analyze(project)
            model_used = None

        analysis = await self.repo.create_project_analysis(
            project_id=project_id,
            analyzer_version=ANALYZER_VERSION,
            model_name=model_used,
            recommended_tasks_json=analysis_output.recommended_tasks,
            recommended_skills_json=analysis_output.recommended_skills,
            recommended_agents_json=analysis_output.recommended_agents,
            recommended_workflow_json=analysis_output.recommended_workflow,
            raw_output_json=analysis_output.model_dump(),
            created_by=owner_id,
        )

        await self.db.commit()
        await self.db.refresh(analysis)
        return ProjectAnalysisResponse.model_validate(analysis)

    async def _llm_analyze(
        self, project: OrchestratorProject, model_name: str | None, provider: ProviderConfig
    ) -> ProjectAnalysisOutput:
        """Use LLM for structured project analysis."""
        system_prompt = """You are a project planning expert. Analyze the project and return structured JSON.

Output JSON schema:
{
  "recommended_tasks": [
    {
      "title": "string",
      "description": "string",
      "priority": "string (low|normal|high)"
    }
  ],
  "recommended_skills": ["array of skill slugs"],
  "recommended_agents": ["array of agent types"],
  "recommended_workflow": {
    "type": "string (sequential|parallel|hybrid)",
    "stages": ["array of strings"]
  }
}"""

        user_prompt = f"""Analyze this project:

Name: {project.name}
Goals: {project.goals_markdown or "N/A"}
Description: {project.description or "N/A"}

Return only valid JSON matching the schema."""

        result = await execute_prompt(
            provider,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format="json",
            request_options={"structured_output": True},
        )

        if result.output_json:
            return ProjectAnalysisOutput(**result.output_json)
        else:
            data = json.loads(result.output_text)
            return ProjectAnalysisOutput(**data)
