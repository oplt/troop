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
from backend.modules.workforce.models import SkillVersion
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import TaskAnalysisOutput, TaskAnalysisResponse


def _fingerprint_task(
    task: OrchestratorTask,
    *,
    project: Any | None = None,
    catalog_fingerprint: str = "",
    dependency_fingerprint: str = "",
) -> str:
    """Generate content fingerprint for caching — includes project/catalog/dependency context."""
    parts = [
        task.title or "",
        task.description or "",
        task.objective or "",
        task.acceptance_criteria or "",
        getattr(task, "expected_output", None) or "",
        json.dumps(getattr(task, "acceptance_criteria_json", None) or [], sort_keys=True),
        json.dumps(getattr(task, "labels_json", None) or [], sort_keys=True),
        getattr(task, "task_type", None) or "",
        getattr(task, "risk_level", None) or "",
    ]
    if project is not None:
        parts.extend(
            [
                getattr(project, "id", "") or "",
                getattr(project, "company_id", "") or "",
                getattr(project, "department_id", "") or "",
                getattr(project, "goals_markdown", None) or "",
                getattr(project, "description", None) or "",
            ]
        )
    parts.append(catalog_fingerprint or "")
    parts.append(dependency_fingerprint or "")
    content = "|".join(str(p) for p in parts)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _hash_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()[:12]


def _department_policy_hash(department: Any | None) -> str:
    if department is None:
        return ""
    return _hash_json(
        {
            "knowledge": getattr(department, "default_knowledge_policy_json", None) or {},
            "tool": getattr(department, "default_tool_policy_json", None) or {},
            "model": getattr(department, "default_model_policy_json", None) or {},
            "approval": getattr(department, "default_approval_policy_json", None) or {},
            "budget": getattr(department, "budget_policy_json", None) or {},
        }
    )


def _skill_version_fingerprint(skills: list[Any], versions_by_id: dict[str, Any]) -> str:
    parts: list[str] = []
    for skill in sorted(skills, key=lambda s: getattr(s, "slug", "") or ""):
        version = versions_by_id.get(getattr(skill, "current_version_id", "") or "")
        if version is None:
            parts.append(f"{getattr(skill, 'slug', '')}:none")
            continue
        cap_hash = _hash_json(
            {
                "id": version.id,
                "version_number": version.version_number,
                "capabilities": version.capabilities_json or [],
                "tools": version.required_tools_json or [],
                "knowledge": version.knowledge_requirements_json or [],
                "risk_level": version.risk_level,
            }
        )
        parts.append(f"{getattr(skill, 'slug', '')}:{cap_hash}")
    return _hash_json(parts)


def _build_catalog_fingerprint(
    *,
    tools: list[Any],
    skills: list[Any],
    versions_by_id: dict[str, Any],
    department: Any | None,
    connector_ids: list[str],
    action_policy_keys: list[str],
    tool_grant_slugs: list[str],
) -> str:
    tool_part = "|".join(sorted(getattr(t, "slug", str(t)) for t in tools))
    skill_part = _skill_version_fingerprint(skills, versions_by_id)
    dept_part = _department_policy_hash(department)
    connector_part = "|".join(sorted(connector_ids))
    policy_part = "|".join(sorted(action_policy_keys))
    grant_part = "|".join(sorted(tool_grant_slugs))
    blob = "|".join([tool_part, skill_part, dept_part, connector_part, policy_part, grant_part])
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _apply_tool_catalog_filter(
    output: TaskAnalysisOutput, available_tools: list[str] | set[str]
) -> TaskAnalysisOutput:
    """Filter required_tools to the available catalog — shared by JSON and text LLM paths."""
    allowed = {str(t).strip() for t in available_tools if t}
    if not allowed:
        return output
    filtered = [t for t in output.required_tools if t in allowed]
    output.required_tools = filtered or ["knowledge_search"]
    return output


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

    if (
        _has_any(tokens, {"research", "search", "find", "discover", "investigate", "explore"})
        or "web research" in content_lower
    ):
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

    if (
        _has_any(tokens, {"classify", "categorize", "classification", "label", "tag"})
        and "classification" not in capabilities
        and "greenhouse_classification" not in capabilities
    ):
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
        res = await self.db.execute(select(OrchestratorTask).where(OrchestratorTask.id == task_id))
        task = res.scalar_one_or_none()
        if task is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")

        from backend.modules.projects.orchestration_models import OrchestratorProject

        project = await self.db.get(OrchestratorProject, task.project_id)
        tools = await self.repo.list_tool_definitions(is_active=True)
        skills = await self.repo.list_skills(owner_id, status="active")

        department = None
        if project and getattr(project, "department_id", None):
            department = await self.repo.get_department_by_id(project.department_id)

        version_ids = [s.current_version_id for s in skills if s.current_version_id]
        versions_by_id: dict[str, SkillVersion] = {}
        if version_ids:
            ver_res = await self.db.execute(
                select(SkillVersion).where(SkillVersion.id.in_(version_ids))
            )
            versions_by_id = {v.id: v for v in ver_res.scalars().all()}

        connectors = await self.repo.list_connector_installations(owner_id)
        connector_def_ids = list({c.connector_definition_id for c in connectors})
        connector_defs = await self.repo.list_connector_definitions_by_ids(connector_def_ids)
        defs_by_id = {d.id: d for d in connector_defs}

        action_policies = await self.repo.list_action_policies(owner_id)
        action_policy_keys = sorted({p.action_key for p in action_policies if p.action_key})

        grant_sources: list[Any] = []
        if project:
            grant_sources.extend(
                await self.repo.list_tool_grants_for_subject("project", project.id, effect="allow")
            )
        if department:
            grant_sources.extend(
                await self.repo.list_tool_grants_for_subject(
                    "department", department.id, effect="allow"
                )
            )
        grant_tool_ids = list({g.tool_definition_id for g in grant_sources if g.tool_definition_id})
        grant_tools = await self.repo.list_tool_definitions_by_ids(grant_tool_ids)
        tool_grant_slugs = sorted({t.slug for t in grant_tools if t.slug})

        catalog_fp = _build_catalog_fingerprint(
            tools=tools,
            skills=skills,
            versions_by_id=versions_by_id,
            department=department,
            connector_ids=[c.id for c in connectors],
            action_policy_keys=action_policy_keys,
            tool_grant_slugs=tool_grant_slugs,
        )
        dependency_fp = _hash_json(
            {
                "connectors": [
                    {
                        "id": c.id,
                        "slug": defs_by_id.get(c.connector_definition_id).slug
                        if defs_by_id.get(c.connector_definition_id)
                        else None,
                        "status": c.status,
                    }
                    for c in connectors
                ],
                "action_policies": action_policy_keys,
                "tool_grants": tool_grant_slugs,
                "department": _department_policy_hash(department),
                "skill_versions": _skill_version_fingerprint(skills, versions_by_id),
            }
        )
        fingerprint = _fingerprint_task(
            task,
            project=project,
            catalog_fingerprint=catalog_fp,
            dependency_fingerprint=dependency_fp,
        )
        cached = await self.repo.get_task_analysis_by_fingerprint(fingerprint, task_id)
        if cached:
            return TaskAnalysisResponse.model_validate(cached)

        skill_capabilities = []
        for skill in skills[:80]:
            version = versions_by_id.get(skill.current_version_id or "")
            if not version:
                continue
            skill_capabilities.append(
                {
                    "slug": skill.slug,
                    "version_id": version.id,
                    "version_number": version.version_number,
                    "capabilities": version.capabilities_json or [],
                    "tools": version.required_tools_json or [],
                    "risk_level": version.risk_level,
                    "capability_hash": _hash_json(
                        {
                            "id": version.id,
                            "version_number": version.version_number,
                            "capabilities": version.capabilities_json or [],
                        }
                    ),
                }
            )

        context = {
            "project_goals": getattr(project, "goals_markdown", None) if project else None,
            "project_description": getattr(project, "description", None) if project else None,
            "department_id": getattr(project, "department_id", None) if project else None,
            "company_id": getattr(project, "company_id", None) if project else None,
            "department_policies": (
                {
                    "knowledge": department.default_knowledge_policy_json or {},
                    "tool": department.default_tool_policy_json or {},
                    "model": department.default_model_policy_json or {},
                    "approval": department.default_approval_policy_json or {},
                    "budget": department.budget_policy_json or {},
                }
                if department
                else None
            ),
            "connector_installations": [
                {
                    "id": c.id,
                    "name": c.name,
                    "slug": defs_by_id.get(c.connector_definition_id).slug
                    if defs_by_id.get(c.connector_definition_id)
                    else None,
                    "status": c.status,
                }
                for c in connectors[:40]
            ],
            "action_policies": [
                {
                    "action_key": p.action_key,
                    "decision": p.decision,
                    "scope_type": p.scope_type,
                    "risk_level": p.risk_level,
                }
                for p in action_policies[:60]
            ],
            "tool_grant_slugs": tool_grant_slugs,
            "available_tools": [t.slug for t in tools[:80]],
            "available_skills": [s.slug for s in skills[:80]],
            "skill_capabilities": skill_capabilities,
        }

        if use_llm and provider:
            try:
                analysis_output = await self._llm_analyze(
                    task, model_name, provider, context=context
                )
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
        self,
        task: OrchestratorTask,
        model_name: str | None,
        provider: ProviderConfig,
        *,
        context: dict[str, Any] | None = None,
    ) -> TaskAnalysisOutput:
        """Use LLM for structured analysis."""
        system_prompt = """You are a task analysis expert. Analyze the task and return structured JSON.

Only recommend tools from available_tools when provided. Prefer existing skill slugs from available_skills.

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

        ctx = context or {}
        user_prompt = f"""Analyze this task:

Title: {task.title}
Description: {task.description or "N/A"}
Objective: {task.objective or "N/A"}
Expected output: {getattr(task, "expected_output", None) or "N/A"}
Acceptance Criteria: {task.acceptance_criteria or "N/A"}
Labels: {json.dumps(getattr(task, "labels_json", None) or [])}
Task type: {getattr(task, "task_type", None) or "N/A"}
Risk level hint: {getattr(task, "risk_level", None) or "N/A"}

Project context:
- goals: {ctx.get("project_goals") or "N/A"}
- description: {ctx.get("project_description") or "N/A"}
- department_id: {ctx.get("department_id") or "N/A"}
- company_id: {ctx.get("company_id") or "N/A"}

Available tools: {json.dumps(ctx.get("available_tools") or [])}
Available skills: {json.dumps(ctx.get("available_skills") or [])}
Skill version capabilities: {json.dumps(ctx.get("skill_capabilities") or [])}
Department policies: {json.dumps(ctx.get("department_policies") or {})}
Connector installations: {json.dumps(ctx.get("connector_installations") or [])}
Action policies: {json.dumps(ctx.get("action_policies") or [])}
Effective tool grants: {json.dumps(ctx.get("tool_grant_slugs") or [])}

Return only valid JSON matching the schema."""

        result = await execute_prompt(
            provider,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format="json",
            request_options={"structured_output": True},
        )

        available_tools = ctx.get("available_tools") or []

        if result.output_json:
            output = TaskAnalysisOutput(**result.output_json)
            return _apply_tool_catalog_filter(output, available_tools)
        if result.output_text:
            data = json.loads(result.output_text)
            output = TaskAnalysisOutput(**data)
            return _apply_tool_catalog_filter(output, available_tools)
        return _heuristic_analyze(task)
