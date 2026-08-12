"""Skill generation service from missing requirements."""

from __future__ import annotations

import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.providers import execute_prompt
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import (
    DuplicateMatch,
    SkillGenerationBatchResult,
)
from backend.modules.workforce.services.duplicate_detector import DuplicateDetectorService


def _normalize_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower()).strip("-")
    return cleaned[:255]


def _heuristic_generate(
    missing_requirements: list[dict], owner_id: str, company_id: str | None
) -> list[dict]:
    """Generate skill drafts from gaps using heuristic approach."""
    drafts: list[dict] = []
    for req in missing_requirements[:5]:
        label = str(req.get("label") or req.get("key") or "Unknown Capability")
        name = label.replace("_", " ").strip().title()
        if name.lower().endswith(" skill"):
            name = name[: -len(" skill")].strip()
        key = str(req.get("key") or label.lower().replace(" ", "_"))
        slug = _normalize_slug(name)
        purpose = f"Reusable capability for {name.lower()}"
        when_to_use = f"Use when a task requires {name.lower()}"
        tools: list[str] = []
        lowered = name.lower()
        if any(w in lowered for w in ("research", "discover", "enrich", "verify", "web", "lead")):
            tools = ["web_search", "web_fetch"]
        if "github" in lowered or "code" in lowered:
            tools = list(dict.fromkeys([*tools, "repo_search", "fs_read"]))

        drafts.append(
            {
                "name": name,
                "slug": slug,
                "description": f"Composable skill covering {name.lower()}",
                "purpose": purpose,
                "when_to_use": when_to_use,
                "instructions_markdown": (
                    f"# {name}\n\n"
                    f"Provide {name.lower()} as a small, testable capability.\n\n"
                    "Steps:\n"
                    "1. Gather only required inputs\n"
                    "2. Use allowed tools\n"
                    "3. Return structured output with evidence\n"
                ),
                "scope": "project",
                "risk_level": "medium",
                "capabilities_json": [key],
                "required_tools_json": tools,
                "knowledge_requirements_json": [],
                "input_schema_json": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
                "output_schema_json": {
                    "type": "object",
                    "properties": {
                        "result": {"type": "object"},
                        "confidence": {"type": "number"},
                    },
                },
                "source_type": "task_generation",
            }
        )
    return drafts


class SkillGeneratorService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)
        self.duplicate_detector = DuplicateDetectorService(db)

    async def generate_skills(
        self,
        owner_id: str,
        company_id: str | None,
        missing_requirements: list[dict],
        use_llm: bool = True,
        model_name: str | None = None,
        provider: ProviderConfig | None = None,
    ) -> SkillGenerationBatchResult:
        """
        Generate skill drafts from missing requirements.

        Returns structured output with drafts and duplicate warnings.
        """
        if use_llm and provider:
            try:
                drafts_data = await self._llm_generate(missing_requirements, model_name, provider)
            except Exception:
                drafts_data = _heuristic_generate(missing_requirements, owner_id, company_id)
        else:
            drafts_data = _heuristic_generate(missing_requirements, owner_id, company_id)

        duplicate_warnings: list[DuplicateMatch] = []
        created_drafts: list[dict] = []

        for draft_data in drafts_data[:10]:
            duplicates = await self.duplicate_detector.detect_duplicates(
                owner_id=owner_id,
                name=draft_data.get("name", ""),
                slug=draft_data.get("slug", ""),
                capabilities=draft_data.get("capabilities_json", []),
                threshold=0.75,
            )

            if duplicates:
                duplicate_warnings.extend(duplicates[:2])

            draft = await self.repo.create_skill_draft(
                owner_id=owner_id,
                company_id=company_id,
                name=draft_data.get("name", "Generated Skill"),
                slug=draft_data.get("slug", "generated-skill"),
                description=draft_data.get("description", ""),
                purpose=draft_data.get("purpose", ""),
                when_to_use=draft_data.get("when_to_use", ""),
                instructions_markdown=draft_data.get("instructions_markdown", ""),
                scope=draft_data.get("scope", "project"),
                risk_level=draft_data.get("risk_level", "medium"),
                capabilities_json=draft_data.get("capabilities_json", []),
                required_tools_json=draft_data.get("required_tools_json", []),
                knowledge_requirements_json=draft_data.get("knowledge_requirements_json", []),
                input_schema_json=draft_data.get("input_schema_json", {}),
                output_schema_json=draft_data.get("output_schema_json", {}),
                source_type="task_generation",
                status="draft",
                duplicate_matches_json=[d.model_dump() for d in duplicates[:2]],
            )
            created_drafts.append(
                {
                    "id": draft.id,
                    "name": draft.name,
                    "slug": draft.slug,
                    "description": draft.description,
                }
            )

        await self.db.commit()
        return SkillGenerationBatchResult(
            drafts=created_drafts,
            duplicate_warnings=duplicate_warnings[:5],
        )

    async def _llm_generate(
        self, missing_requirements: list[dict], model_name: str | None, provider: ProviderConfig
    ) -> list[dict]:
        """Use LLM for structured skill generation."""
        system_prompt = """You are a skill design expert. Generate skill definitions from requirements.

Output JSON schema:
{
  "drafts": [
    {
      "name": "string",
      "slug": "string (lowercase-dash-separated)",
      "description": "string",
      "purpose": "string",
      "when_to_use": "string",
      "instructions_markdown": "string",
      "scope": "string (project|organization)",
      "risk_level": "string (low|medium|high)",
      "capabilities_json": ["array"],
      "required_tools_json": ["array"],
      "knowledge_requirements_json": ["array"]
    }
  ]
}"""

        reqs_str = "\n".join(
            f"- {req.get('label', req.get('key', 'unknown'))} ({req.get('kind', 'capability')})"
            for req in missing_requirements[:5]
        )

        user_prompt = f"""Generate skill definitions for these missing requirements:

{reqs_str}

Return only valid JSON matching the schema. Limit to 5 skills."""

        result = await execute_prompt(
            provider,
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format="json",
            request_options={"structured_output": True},
        )

        data = result.output_json or json.loads(result.output_text)

        return data.get("drafts", [])
