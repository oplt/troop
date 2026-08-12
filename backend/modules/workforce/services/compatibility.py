"""Compatibility helpers for SkillPack → Skill migration."""

from __future__ import annotations

from typing import Any

from backend.modules.workforce.constants import LEGACY_STATUS_ALIASES


def skill_to_skill_pack_payload(skill: Any, version: Any | None = None) -> dict:
    """
    Convert Skill + SkillVersion → SkillPack API payload for backward compatibility.

    Args:
        skill: Skill model instance
        version: Optional SkillVersion instance (latest if not provided)

    Returns:
        Dict matching SkillPack API response format
    """
    payload = {
        "id": skill.id,
        "slug": skill.slug,
        "name": skill.name,
        "description": skill.description or "",
        "capabilities": [],
        "allowed_tools": [],
        "rules_markdown": "",
        "tags": [],
    }

    if version:
        payload["capabilities"] = version.capabilities_json or []
        payload["allowed_tools"] = version.required_tools_json or []
        payload["rules_markdown"] = version.instructions_markdown or ""

    return payload


def skill_pack_to_skill_data(skill_pack: Any) -> dict:
    """
    Convert SkillPack → Skill/SkillVersion creation data.

    Used when creating Skill from existing SkillPack via old API.
    """
    return {
        "skill": {
            "name": skill_pack.name,
            "slug": skill_pack.slug,
            "description": skill_pack.description or "",
            "scope": "organization",
            "status": "active",
            "legacy_skill_pack_id": skill_pack.id,
        },
        "version": {
            "version_number": 1,
            "purpose": skill_pack.description or "",
            "when_to_use": "",
            "instructions_markdown": skill_pack.rules_markdown or "",
            "capabilities_json": skill_pack.capabilities_json or [],
            "required_tools_json": skill_pack.allowed_tools_json or [],
            "knowledge_requirements_json": [],
            "input_schema_json": {},
            "output_schema_json": {},
            "constraints_markdown": "",
            "risk_level": "low",
            "approval_policy_json": {},
            "examples_json": [],
            "evaluation_criteria_json": [],
            "source_type": "skill_pack_migration",
            "is_published": True,
        },
    }


def normalize_task_status(status: str) -> str:
    """
    Normalize legacy task status to generic equivalent.

    Args:
        status: Raw status from database

    Returns:
        Generic status (or original if not aliased)
    """
    return LEGACY_STATUS_ALIASES.get(status, status)
