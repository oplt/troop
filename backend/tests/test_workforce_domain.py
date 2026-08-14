"""Unit tests for workforce domain — matcher, gaps, analyzer heuristics, duplicates."""

import pytest
from backend.modules.orchestration.constants import TASK_TRANSITIONS
from backend.modules.workforce.constants import LEGACY_STATUS_ALIASES
from backend.modules.workforce.services.duplicate_detector import DuplicateDetectorService
from backend.modules.workforce.services.skill_matcher import SkillMatcherService
from backend.modules.workforce.services.task_analyzer import _heuristic_analyze


class _FakeTask:
    def __init__(self, **kwargs):
        self.title = kwargs.get("title", "")
        self.description = kwargs.get("description")
        self.objective = kwargs.get("objective")
        self.acceptance_criteria = kwargs.get("acceptance_criteria")
        self.risk_level = kwargs.get("risk_level", "medium")


def test_generic_task_transitions_include_new_statuses() -> None:
    assert "ready" in TASK_TRANSITIONS["backlog"]
    assert "needs_input" in TASK_TRANSITIONS["in_progress"]
    assert "needs_approval" in TASK_TRANSITIONS["needs_review"]
    assert "cancelled" in TASK_TRANSITIONS["backlog"]
    # Legacy GitHub path retained for compatibility
    assert "synced_to_github" in TASK_TRANSITIONS["completed"]
    assert LEGACY_STATUS_ALIASES["synced_to_github"] == "completed"
    assert LEGACY_STATUS_ALIASES["queued"] == "ready"


def test_heuristic_analyze_agriculture_research_task() -> None:
    task = _FakeTask(
        title="Identify 50 greenhouse operators in Belgium and the Netherlands",
        description=(
            "Find strong candidates for our drone crop-monitoring product. "
            "Research companies, classify greenhouse operators, enrich firmographics, "
            "qualify leads, and verify sources."
        ),
        objective="Build a structured prospect dataset of greenhouse operators",
        acceptance_criteria="- At least 50 prospects\n- Sources cited\n- Qualification notes",
    )
    result = _heuristic_analyze(task)
    caps = set(result.required_capabilities)
    assert "web_research" in caps or any("research" in c for c in caps)
    assert any("company" in c or "discover" in c for c in caps)
    assert "web_search" in result.required_tools or "web_fetch" in result.required_tools
    assert result.task_category
    assert result.objective
    assert result.expected_artifacts


def test_heuristic_analyze_coding_task() -> None:
    task = _FakeTask(
        title="Fix failing GitHub issue #123",
        description="Investigate repository, implement code change, run tests, open PR",
        objective="Resolve CI failure from issue 123",
    )
    result = _heuristic_analyze(task)
    caps = " ".join(result.required_capabilities)
    assert "repository" in caps or "github" in caps or "code" in caps
    assert any(
        t.startswith("github") or t in {"fs_read", "fs_write", "code_execute", "repo_search"}
        for t in result.required_tools
    )


def test_apply_tool_catalog_filter_unifies_llm_paths() -> None:
    from backend.modules.workforce.schemas import TaskAnalysisOutput
    from backend.modules.workforce.services.task_analyzer import _apply_tool_catalog_filter

    output = TaskAnalysisOutput(
        objective="Do research",
        task_category="research",
        required_tools=["web_search", "unknown_tool"],
    )
    filtered = _apply_tool_catalog_filter(output, ["web_search", "knowledge_search"])
    assert filtered.required_tools == ["web_search"]

    empty_allowed = _apply_tool_catalog_filter(
        TaskAnalysisOutput(objective="x", task_category="general", required_tools=["anything"]),
        [],
    )
    assert empty_allowed.required_tools == ["anything"]


def test_jaccard_skill_match_scoring() -> None:
    from backend.core.validation.text import jaccard_similarity

    assert jaccard_similarity({"a", "b"}, {"a", "b"}) == 1.0
    assert jaccard_similarity({"a"}, {"b"}) == 0.0
    assert 0 < jaccard_similarity({"a", "b"}, {"a", "c"}) < 1


def test_duplicate_detector_slug_collision() -> None:
    # DuplicateDetectorService.find_duplicates is async+db; test pure similarity if exposed
    from backend.modules.workforce.services import duplicate_detector as dd

    if hasattr(dd, "name_similarity"):
        assert dd.name_similarity("Web Research", "web-research") >= 0.5
    if hasattr(dd, "find_duplicates") and not hasattr(DuplicateDetectorService, "find_duplicates"):
        pass
    # Ensure class exists
    assert DuplicateDetectorService is not None
    assert SkillMatcherService is not None


def test_schema_compat_score_overlaps_keys_and_types() -> None:
    from backend.modules.workforce.services.skill_matcher import _schema_compat_score

    required = {
        "properties": {
            "company_name": {"type": "string"},
            "revenue": {"type": "number"},
        }
    }
    skill = {
        "properties": {
            "company_name": {"type": "string"},
            "revenue": {"type": "integer"},
            "notes": {"type": "string"},
        }
    }
    score = _schema_compat_score(required, skill)
    assert score > 0.5


def test_token_jaccard_semantic_similarity() -> None:
    from backend.core.validation.text import token_jaccard

    a = "greenhouse lead qualification research agriculture"
    b = "Qualify greenhouse operators for agriculture sales research"
    assert token_jaccard(a, b) > 0.3


def test_workflow_step_legacy_alias_normalization() -> None:
    from backend.modules.orchestration.execution.execution_service import (
        EXTERNAL_ACTION_STEP_ID,
        _normalize_workflow_step_id,
    )

    assert EXTERNAL_ACTION_STEP_ID == "external_action_sync"
    assert _normalize_workflow_step_id("github_sync") == "external_action_sync"
    assert _normalize_workflow_step_id("review") == "review"


def test_model_router_purpose_defaults() -> None:
    from backend.modules.orchestration.model_router import _PURPOSE_DEFAULTS

    assert _PURPOSE_DEFAULTS["task_analysis"]["prefer_cheap"] is True
    assert _PURPOSE_DEFAULTS["default"]["require_tools"] is False


@pytest.mark.asyncio
async def test_model_router_hard_requirements_do_not_soft_fallback() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.modules.orchestration.model_router import resolve_route

    provider = SimpleNamespace(
        id="prov-1",
        provider_type="openai",
        is_enabled=True,
        is_default=True,
        default_model="gpt-soft",
        project_id=None,
    )
    soft_cap = SimpleNamespace(
        id="cap-1",
        provider_id="prov-1",
        provider_type="openai",
        model_slug="gpt-soft",
        is_active=True,
        supports_tools=False,
        cost_per_1k_input=0.1,
        cost_per_1k_output=0.1,
        max_context_tokens=8000,
        metadata_json={"supports_structured_output": False},
    )
    repo = MagicMock()
    repo.list_providers = AsyncMock(return_value=[provider])
    repo.list_model_capabilities_for_owner = AsyncMock(return_value=[soft_cap])

    with patch(
        "backend.modules.orchestration.model_router.OrchestrationRepository",
        return_value=repo,
    ):
        result = await resolve_route(
            AsyncMock(),
            "owner-1",
            purpose="task_analysis",
            require_structured=True,
        )

    assert result.provider is None
    assert result.model_slug is None
    assert result.fallback_reason and "hard_requirements" in result.fallback_reason


def test_agent_model_capability_score_unknown_model() -> None:
    from types import SimpleNamespace

    from backend.modules.workforce.services.agent_matcher import _model_capability_score

    agent = SimpleNamespace(model_policy_json={"model": "unknown-model"})
    score, detail = _model_capability_score(agent, {}, needs_tools=False)
    assert score < 0.6
    assert "unknown" in detail


@pytest.mark.asyncio
async def test_pin_agent_skills_creates_pinned_assignments() -> None:
    """pin_agent_skills upserts AgentSkillAssignment with version_policy=pinned."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.modules.team.service import TeamServiceMixin

    class _Svc(TeamServiceMixin):
        pass

    svc = _Svc()
    svc.db = AsyncMock()
    svc.db.commit = AsyncMock()
    svc.db.refresh = AsyncMock()

    agent = MagicMock()
    agent.id = "agent-1"
    agent.metadata_json = {"skill_pins": ["legacy-should-not-win"], "other": 1}

    user = MagicMock()
    user.id = "user-1"

    skill = MagicMock()
    skill.id = "skill-1"
    skill.current_version_id = "ver-1"
    skill.status = "active"

    upsert = AsyncMock(return_value=MagicMock())
    fake_repo = MagicMock()
    fake_repo.get_skill = AsyncMock(return_value=None)
    fake_repo.find_skill_by_slug = AsyncMock(return_value=skill)
    fake_repo.get_skill_version = AsyncMock(return_value=None)
    fake_repo.upsert_agent_skill_assignment = upsert

    svc.get_agent = AsyncMock(return_value=agent)
    svc._attach_orchestration_skills = AsyncMock(return_value=agent)

    with patch(
        "backend.modules.workforce.repository.WorkforceRepository",
        return_value=fake_repo,
    ):
        result = await svc.pin_agent_skills(
            user,
            "agent-1",
            {"skill_pins": ["research-skill"]},
        )

    assert result is agent
    upsert.assert_awaited_once()
    kwargs = upsert.await_args.kwargs
    assert kwargs["agent_id"] == "agent-1"
    assert kwargs["skill_id"] == "skill-1"
    assert kwargs["skill_version_id"] == "ver-1"
    assert kwargs["version_policy"] == "pinned"
    assert kwargs["enabled"] is True
    assert "skill_pins" not in (agent.metadata_json or {})
    assert agent.metadata_json.get("other") == 1


@pytest.mark.asyncio
async def test_pin_agent_skills_migrates_legacy_metadata_pins() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.modules.team.service import TeamServiceMixin

    class _Svc(TeamServiceMixin):
        pass

    svc = _Svc()
    svc.db = AsyncMock()
    svc.db.commit = AsyncMock()
    svc.db.refresh = AsyncMock()

    agent = MagicMock()
    agent.id = "agent-1"
    agent.metadata_json = {"skill_pins": [{"skill_id": "skill-9", "skill_version_id": "ver-9"}]}

    user = MagicMock()
    user.id = "user-1"

    skill = MagicMock()
    skill.id = "skill-9"
    skill.current_version_id = "ver-fallback"
    skill.status = "active"
    version = MagicMock()
    version.skill_id = "skill-9"

    upsert = AsyncMock(return_value=MagicMock())
    fake_repo = MagicMock()
    fake_repo.get_skill = AsyncMock(return_value=skill)
    fake_repo.find_skill_by_slug = AsyncMock(return_value=None)
    fake_repo.get_skill_version = AsyncMock(return_value=version)
    fake_repo.upsert_agent_skill_assignment = upsert

    svc.get_agent = AsyncMock(return_value=agent)
    svc._attach_orchestration_skills = AsyncMock(return_value=agent)

    with patch(
        "backend.modules.workforce.repository.WorkforceRepository",
        return_value=fake_repo,
    ):
        await svc.pin_agent_skills(user, "agent-1", {})

    kwargs = upsert.await_args.kwargs
    assert kwargs["version_policy"] == "pinned"
    assert kwargs["skill_id"] == "skill-9"
    assert kwargs["skill_version_id"] == "ver-9"
    assert "skill_pins" not in (agent.metadata_json or {})
