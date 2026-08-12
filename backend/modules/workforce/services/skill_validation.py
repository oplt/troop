"""Skill draft validation — blocking errors prevent publish."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.constants import SKILL_SCOPES
from backend.modules.workforce.models import SkillDraft
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.services.duplicate_detector import DuplicateDetectorService

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
_RISK = {"low", "medium", "high", "critical"}
_DANGEROUS_TOOLS = {
    "code_execute",
    "fs_write",
    "db_query",
    "github_create_pr",
    "shell_destructive_action",
}


def _is_json_schema(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    if not value:
        return True
    # Minimal JSON Schema check
    if "type" in value or "properties" in value or "$schema" in value or "items" in value:
        return True
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError):
        return False


class SkillValidationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)
        self.duplicates = DuplicateDetectorService(db)

    async def validate_draft(self, owner_id: str, draft: SkillDraft) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []

        name = (draft.name or "").strip()
        slug = (draft.slug or "").strip()
        purpose = (draft.purpose or "").strip()
        when_to_use = (draft.when_to_use or "").strip()
        instructions = (draft.instructions_markdown or "").strip()
        scope = (draft.scope or "").strip()
        risk = (draft.risk_level or "").strip().lower()
        capabilities = [str(c).strip() for c in (draft.capabilities_json or []) if str(c).strip()]
        tools = [str(t).strip() for t in (draft.required_tools_json or []) if str(t).strip()]

        if len(name) < 2:
            errors.append("name is required (min 2 characters)")
        if not slug or not _SLUG_RE.match(slug):
            errors.append("slug must match ^[a-z0-9][a-z0-9-]*$")
        if scope not in SKILL_SCOPES:
            errors.append(f"scope must be one of: {', '.join(sorted(SKILL_SCOPES))}")
        if not purpose:
            errors.append("purpose is required")
        if not when_to_use:
            errors.append("when_to_use is required")
        if len(instructions) < 40:
            errors.append("instructions_markdown must be meaningful (min ~40 characters)")
        if not capabilities:
            errors.append("at least one capability is required")
        if risk and risk not in _RISK:
            errors.append(f"risk_level must be one of: {', '.join(sorted(_RISK))}")
        if not risk:
            errors.append("risk_level is required")

        if not _is_json_schema(draft.input_schema_json):
            errors.append("input_schema_json must be a valid JSON Schema object")
        if not _is_json_schema(draft.output_schema_json):
            errors.append("output_schema_json must be a valid JSON Schema object")

        # Tool existence
        known_tools = {t.slug for t in await self.repo.list_tool_definitions(is_active=True)}
        unknown = [t for t in tools if t not in known_tools]
        if unknown:
            # Unknown tools block publish unless catalog empty (pre-seed)
            if known_tools:
                errors.append(f"unknown tools: {', '.join(unknown)}")
            else:
                warnings.append(f"tool catalog empty; cannot verify tools: {', '.join(unknown)}")

        dangerous = [t for t in tools if t in _DANGEROUS_TOOLS]
        if dangerous and risk in {"low"}:
            errors.append(
                f"dangerous tools ({', '.join(dangerous)}) incompatible with risk_level=low"
            )
        elif dangerous and risk == "medium":
            warnings.append(
                f"dangerous tools ({', '.join(dangerous)}) usually require high/critical risk + approval"
            )
            if not (draft.approval_policy_json or {}):
                warnings.append("high-risk tools should declare approval_policy_json")

        # Quality heuristics
        lowered = instructions.lower()
        if "general task" in lowered or instructions.strip() in {"TODO", "TBD", "..."}:
            errors.append("instructions are too generic / placeholder")
        if len(capabilities) == 1 and capabilities[0] in {"general", "general_task_execution"}:
            warnings.append("capability set is overly generic")

        # Duplicates
        duplicate_matches = await self.duplicates.detect_duplicates(
            owner_id=owner_id,
            name=name,
            slug=slug,
            capabilities=capabilities,
            threshold=0.75,
        )
        # Exact slug collision against existing skill (exclude draft.skill_id if improving)
        existing = await self.repo.find_skill_by_slug(owner_id, slug)
        if existing and existing.id != draft.skill_id:
            errors.append(f"slug '{slug}' already exists for skill {existing.id}")
            duplicate_matches = [
                {
                    "skill_id": existing.id,
                    "skill_slug": existing.slug,
                    "skill_name": existing.name,
                    "similarity": 1.0,
                    "reasons": ["exact slug collision"],
                },
                *duplicate_matches,
            ]
        elif duplicate_matches:
            warnings.append(
                f"near-duplicate skills found: "
                f"{', '.join(d.skill_name if hasattr(d, 'skill_name') else d.get('skill_name', '?') for d in duplicate_matches[:3])}"
            )

        # Normalize duplicate dumps
        dup_payload = []
        for d in duplicate_matches[:10]:
            if hasattr(d, "model_dump"):
                dup_payload.append(d.model_dump())
            elif isinstance(d, dict):
                dup_payload.append(d)
            else:
                dup_payload.append({"value": str(d)})

        is_valid = len(errors) == 0
        draft.validation_errors_json = errors
        draft.warnings_json = warnings
        draft.duplicate_matches_json = dup_payload
        await self.db.commit()
        await self.db.refresh(draft)

        return {
            "validation_errors": errors,
            "validation_warnings": warnings,
            "duplicate_matches": dup_payload,
            "is_valid": is_valid,
            "draft": draft,
        }
