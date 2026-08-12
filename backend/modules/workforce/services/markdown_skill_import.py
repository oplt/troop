"""Import markdown skill templates into SkillDraft (canonical path)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.models import SkillDraft
from backend.modules.workforce.repository import WorkforceRepository

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(value: str) -> str:
    cleaned = _SLUG_RE.sub("-", (value or "").strip().lower()).strip("-")
    return (cleaned or "imported-skill")[:255]


def parse_skill_markdown(content: str, *, file_name: str | None = None) -> dict[str, Any]:
    """Lightweight markdown → draft fields parser (keeps useful headings)."""
    text = content or ""
    lines = text.splitlines()
    name = ""
    if file_name:
        name = re.sub(r"\.[^.]+$", "", file_name).replace("_", " ").replace("-", " ").strip()
    for line in lines[:20]:
        if line.startswith("# "):
            name = line[2:].strip() or name
            break

    sections: dict[str, list[str]] = {}
    current = "body"
    sections[current] = []
    for line in lines:
        if line.startswith("## "):
            current = line[3:].strip().lower()
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)

    def section(*keys: str) -> str:
        for key in keys:
            for heading, body in sections.items():
                if key in heading:
                    return "\n".join(body).strip()
        return ""

    caps_raw = section("capabilities", "capability")
    tools_raw = section("tools", "allowed tools", "required tools")
    purpose = section("purpose", "overview", "summary") or name
    when_to_use = section("when to use", "when", "use when")
    instructions = section("instructions", "rules", "body") or text.strip()
    constraints = section("constraints", "guardrails")

    capabilities = [
        part.strip(" -*\t") for part in re.split(r"[\n,]", caps_raw) if part.strip(" -*\t")
    ]
    tools = [part.strip(" -*\t`") for part in re.split(r"[\n,]", tools_raw) if part.strip(" -*\t`")]

    slug = _slugify(name or "imported-skill")
    return {
        "name": name or "Imported skill",
        "slug": slug,
        "description": purpose[:500],
        "purpose": purpose,
        "when_to_use": when_to_use or "Use when the task matches this skill's purpose.",
        "instructions_markdown": instructions,
        "capabilities": capabilities or ["general_task_execution"],
        "required_tools": tools,
        "constraints_markdown": constraints,
        "source_type": "markdown_import",
        "scope": "organization",
        "risk_level": "medium",
        "generation_metadata": {
            "source_filename": file_name,
            "parser": "markdown_skill_import_v1",
        },
    }


class MarkdownSkillImportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkforceRepository(db)

    async def import_markdown(
        self,
        owner_id: str,
        content: str,
        *,
        file_name: str | None = None,
        company_id: str | None = None,
        scope: str = "organization",
    ) -> SkillDraft:
        parsed = parse_skill_markdown(content, file_name=file_name)
        parsed["scope"] = scope or parsed["scope"]
        draft = await self.repo.create_skill_draft(
            owner_id=owner_id,
            company_id=company_id,
            name=parsed["name"],
            slug=parsed["slug"],
            description=parsed["description"],
            purpose=parsed["purpose"],
            when_to_use=parsed["when_to_use"],
            instructions_markdown=parsed["instructions_markdown"],
            scope=parsed["scope"],
            risk_level=parsed["risk_level"],
            source_type="markdown_import",
            capabilities_json=parsed["capabilities"],
            required_tools_json=parsed["required_tools"],
            constraints_markdown=parsed["constraints_markdown"],
            generation_metadata_json=parsed["generation_metadata"],
            status="draft",
        )
        await self.db.commit()
        await self.db.refresh(draft)
        return draft
