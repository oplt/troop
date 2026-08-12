"""Task analysis service with heuristic and LLM support."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.providers import execute_prompt
from backend.modules.projects.orchestration_models import OrchestratorTask
from backend.modules.workforce.constants import ANALYZER_VERSION
from backend.modules.workforce.models import TaskAnalysis, TaskRequirement
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import TaskAnalysisOutput, TaskAnalysisResponse


def _fingerprint_task(task: OrchestratorTask) -> str:
    """Generate content fingerprint for caching."""
    content = f"{task.title}|{task.description or ''}|{task.objective or ''}|{task.acceptance_criteria or ''}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _tokens(text: str) -> set[str]:
    import re

    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t}


def _has_any(tokens: set[str], words: set[str]) -> bool:
    return bool(tokens & words)


def _heuristic_analyze(task: OrchestratorTask) -> TaskAnalysisOutput:
    """Deterministic heuristic analyzer for offline testing."""
    content = f"{task.title} {task.description or ''} {task.objective or ''}"
    content_lower = content.lower()
    tokens = _tokens(content)

    capabilities: list[str] = []
    tools: list[str] = []
    knowledge: list[str] = []

    if _has_any(
        tokens, {"research", "search", "find", "discover", "investigate", "explore"}
    ) or "web research" in content_lower:
        capabilities.append("web_research")
        tools.append("web_search")
        tools.append("web_fetch")

    if _has_any(
        tokens,
        {
            "company",
            "companies",
            "business",
            "organization",
            "startup",
            "operator",
            "operators",
            "prospect",
            "prospects",
            "firm",
            "firms",
        },
    ):
        capabilities.append("company_discovery")
        knowledge.append("business_context")

    if _has_any(tokens, {"greenhouse", "agriculture", "agricultural", "crop", "farm"}):
        capabilities.append("greenhouse_classification")

    if _has_any(tokens, {"classify", "categorize", "classification", "label", "tag"}):
        if "classification" not in capabilities and "greenhouse_classification" not in capabilities:
            capabilities.append("classification")

    if _has_any(tokens, {"enrich", "enrichment", "augment", "firmographic", "firmographics"}):
        capabilities.append("company_enrichment")

    if _has_any(tokens, {"qualify", "qualification", "lead", "leads", "icp"}):
        capabilities.append("lead_qualification")

    if _has_any(tokens, {"verify", "verification", "validate", "citation", "source", "sources"}):
        capabilities.append("source_verification")

    if _has_any(tokens, {"extract", "structured", "dataset", "csv"}):
        capabilities.append("structured_extraction")

    if _has_any(tokens, {"repository", "repo", "codebase"}) or "github" in tokens:
        capabilities.append("repository_investigation")
        tools.append("repo_search")

    if _has_any(tokens, {"implement", "refactor", "patch", "bugfix"}) or (
        "code" in tokens and _has_any(tokens, {"modify", "edit", "change", "fix"})
    ):
        capabilities.append("code_modification")
        tools.append("fs_write")
        tools.append("fs_read")

    if _has_any(tokens, {"pytest", "unittest"}) or (
        "test" in tokens and _has_any(tokens, {"run", "execute", "ci", "lint"})
    ):
        capabilities.append("test_execution")
        tools.append("code_execute")

    # Avoid false positives: substring "pr" matches inside "product".
    if (
        "github" in tokens
        or ("pull" in tokens and "request" in tokens)
        or ("issue" in tokens and ("github" in tokens or "#" in (task.title or "")))
        or "pr" in tokens
    ):
        capabilities.append("github_interaction")
        if "github_comment" not in tools:
            tools.append("github_comment")

    # Deduplicate tools preserving order
    tools = list(dict.fromkeys(tools))

    is_coding = any(
        c in capabilities
        for c in (
            "repository_investigation",
            "code_modification",
            "test_execution",
            "github_interaction",
        )
    )
    is_research = any(
        c in capabilities
        for c in (
            "web_research",
            "company_discovery",
            "lead_qualification",
            "greenhouse_classification",
        )
    )

    risk_level = "medium"
    if "fs_write" in tools or "code_execute" in tools:
        risk_level = "high"
    elif is_research and not is_coding:
        risk_level = "medium"

    autonomy_recommendation = "semi-autonomous"
    if risk_level == "low":
        autonomy_recommendation = "autonomous"
    elif risk_level == "high":
        autonomy_recommendation = "assisted"

    if is_coding and not is_research:
        task_category = "software_engineering"
        expected_artifacts = ["changed_files", "test_results", "pull_request"]
        approvals = ["mark_complete"]
        if "github_interaction" in capabilities:
            approvals.append("open_pr")
    elif is_research:
        task_category = "research"
        expected_artifacts = [
            "structured_prospect_dataset",
            "research_sources",
            "execution_evidence",
        ]
        approvals = ["mark_complete"]
    else:
        task_category = "general"
        expected_artifacts = ["summary", "results"]
        approvals = ["mark_complete"]

    criteria: list[str] = []
    if task.acceptance_criteria:
        criteria = [
            line.strip("-• \t")
            for line in str(task.acceptance_criteria).splitlines()
            if line.strip()
        ]
    if not criteria and task.acceptance_criteria:
        criteria = [str(task.acceptance_criteria)]

    return TaskAnalysisOutput(
        objective=task.objective or task.title,
        task_category=task_category,
        risk_level=risk_level,  # type: ignore[arg-type]
        autonomy_recommendation=autonomy_recommendation,
        required_capabilities=capabilities if capabilities else ["general_task_execution"],
        required_tools=tools if tools else ["knowledge_search"],
        knowledge_requirements=knowledge,
        expected_artifacts=expected_artifacts,
        acceptance_criteria=criteria,
        review_requirements=["human_review"] if risk_level == "high" else [],
        approval_requirements=approvals,
    )


class TaskAnalyzerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)

    async def analyze_task(
        self,
        task_id: str,
        owner_id: str,
        use_llm: bool = True,
        model_name: str | None = None,
        provider: ProviderConfig | None = None,
    ) -> TaskAnalysisResponse:
        """
        Analyze task requirements with caching.

        Returns cached analysis if fingerprint matches, otherwise generates new.
        Falls back to heuristic if LLM unavailable.
        """
        res = await self.db.execute(
            select(OrchestratorTask).where(OrchestratorTask.id == task_id)
        )
        task = res.scalar_one_or_none()
        if task is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")

        fingerprint = _fingerprint_task(task)
        cached = await self.repo.get_task_analysis_by_fingerprint(fingerprint, task_id)
        if cached:
            return TaskAnalysisResponse.model_validate(cached)

        if use_llm and provider:
            try:
                analysis_output = await self._llm_analyze(task, model_name, provider)
                model_used = model_name or provider.default_model
            except Exception:
                analysis_output = _heuristic_analyze(task)
                model_used = None
        else:
            analysis_output = _heuristic_analyze(task)
            model_used = None

        analysis = await self.repo.create_task_analysis(
            task_id=task_id,
            project_id=task.project_id,
            analyzer_version=ANALYZER_VERSION,
            model_name=model_used,
            content_fingerprint=fingerprint,
            objective=analysis_output.objective,
            task_category=analysis_output.task_category,
            risk_level=analysis_output.risk_level,
            autonomy_recommendation=analysis_output.autonomy_recommendation,
            required_capabilities_json=analysis_output.required_capabilities,
            required_tools_json=analysis_output.required_tools,
            knowledge_requirements_json=analysis_output.knowledge_requirements,
            expected_artifacts_json=analysis_output.expected_artifacts,
            acceptance_criteria_json=analysis_output.acceptance_criteria,
            review_requirements_json=analysis_output.review_requirements,
            approval_requirements_json=analysis_output.approval_requirements,
            raw_output_json=analysis_output.model_dump(),
            created_by=owner_id,
        )

        for cap in analysis_output.required_capabilities:
            await self.repo.create_task_requirement(
                analysis_id=analysis.id,
                task_id=task_id,
                kind="capability",
                key=cap,
                label=cap.replace("_", " ").title(),
                description="",
                priority="required",
                coverage_status="missing",
                metadata_json={},
            )

        for tool in analysis_output.required_tools:
            await self.repo.create_task_requirement(
                analysis_id=analysis.id,
                task_id=task_id,
                kind="tool",
                key=tool,
                label=tool.replace("_", " ").title(),
                description="",
                priority="required",
                coverage_status="missing",
                metadata_json={},
            )

        await self.db.commit()
        await self.db.refresh(analysis)
        return TaskAnalysisResponse.model_validate(analysis)

    async def _llm_analyze(
        self, task: OrchestratorTask, model_name: str | None, provider: ProviderConfig
    ) -> TaskAnalysisOutput:
        """Use LLM for structured analysis."""
        system_prompt = """You are a task analysis expert. Analyze the task and return structured JSON.

Output JSON schema:
{
  "objective": "string",
  "task_category": "string (research|development|data_processing|general)",
  "risk_level": "string (low|medium|high|critical)",
  "autonomy_recommendation": "string (autonomous|semi-autonomous|assisted|supervised)",
  "required_capabilities": ["array of strings"],
  "required_tools": ["array of strings"],
  "knowledge_requirements": ["array of strings"],
  "expected_artifacts": ["array of strings"],
  "acceptance_criteria": ["array of strings"],
  "review_requirements": ["array of strings"],
  "approval_requirements": ["array of strings"]
}"""

        user_prompt = f"""Analyze this task:

Title: {task.title}
Description: {task.description or 'N/A'}
Objective: {task.objective or 'N/A'}
Acceptance Criteria: {task.acceptance_criteria or 'N/A'}

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
            return TaskAnalysisOutput(**result.output_json)
        else:
            data = json.loads(result.output_text)
            return TaskAnalysisOutput(**data)
