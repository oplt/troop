"""Tests for SkillValidationService."""

import asyncio
from types import SimpleNamespace

from backend.modules.workforce.services.skill_validation import SkillValidationService


class _FakeRepo:
    def __init__(self) -> None:
        self.tools = [
            SimpleNamespace(slug="web_search"),
            SimpleNamespace(slug="web_fetch"),
            SimpleNamespace(slug="code_execute"),
        ]
        self.skills_by_slug: dict[str, SimpleNamespace] = {}

    async def list_tool_definitions(self, is_active: bool = True):
        return self.tools

    async def find_skill_by_slug(self, owner_id: str, slug: str):
        return self.skills_by_slug.get(slug)


class _FakeDuplicates:
    async def detect_duplicates(self, **kwargs):
        return []


def _make_service() -> SkillValidationService:
    service = SkillValidationService.__new__(SkillValidationService)
    service.repo = _FakeRepo()
    service.duplicates = _FakeDuplicates()

    async def _commit():
        return None

    async def _refresh(_draft):
        return None

    service.db = SimpleNamespace(commit=_commit, refresh=_refresh)
    return service


def test_validation_requires_core_fields():
    service = _make_service()
    draft = SimpleNamespace(
        name="",
        slug="BAD SLUG",
        purpose="",
        when_to_use="",
        instructions_markdown="short",
        scope="company",
        risk_level="nope",
        capabilities_json=[],
        required_tools_json=["web_search"],
        input_schema_json={},
        output_schema_json={},
        approval_policy_json={},
        skill_id=None,
        validation_errors_json=[],
        warnings_json=[],
        duplicate_matches_json=[],
    )
    result = asyncio.get_event_loop().run_until_complete(
        SkillValidationService.validate_draft(service, "owner", draft)
    )
    assert result["is_valid"] is False
    assert any("name" in e for e in result["validation_errors"])
    assert any("slug" in e for e in result["validation_errors"])
    assert any("purpose" in e for e in result["validation_errors"])
    assert any("scope" in e for e in result["validation_errors"])


def test_validation_blocks_dangerous_tool_with_low_risk():
    service = _make_service()
    draft = SimpleNamespace(
        name="Code Patcher",
        slug="code-patcher",
        purpose="Apply code patches",
        when_to_use="When a repository change is needed",
        instructions_markdown=(
            "Read the repository, apply a minimal patch, run tests, and return a structured diff."
        ),
        scope="project",
        risk_level="low",
        capabilities_json=["code_modification"],
        required_tools_json=["code_execute"],
        input_schema_json={"type": "object"},
        output_schema_json={"type": "object"},
        approval_policy_json={},
        skill_id=None,
        validation_errors_json=[],
        warnings_json=[],
        duplicate_matches_json=[],
    )
    result = asyncio.get_event_loop().run_until_complete(
        SkillValidationService.validate_draft(service, "owner", draft)
    )
    assert result["is_valid"] is False
    assert any("dangerous" in e for e in result["validation_errors"])
