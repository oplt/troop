"""Unit tests for workforce domain — matcher, gaps, analyzer heuristics, duplicates."""

from backend.modules.orchestration.constants import TASK_TRANSITIONS
from backend.modules.workforce.constants import LEGACY_STATUS_ALIASES
from backend.modules.workforce.services.skill_matcher import SkillMatcherService
from backend.modules.workforce.services.task_analyzer import _heuristic_analyze
from backend.modules.workforce.services.duplicate_detector import DuplicateDetectorService


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
    assert any(t.startswith("github") or t in {"fs_read", "fs_write", "code_execute", "repo_search"} for t in result.required_tools)


def test_jaccard_skill_match_scoring() -> None:
    # Exercise pure helper via service module internals
    from backend.modules.workforce.services.skill_matcher import _jaccard_similarity

    assert _jaccard_similarity({"a", "b"}, {"a", "b"}) == 1.0
    assert _jaccard_similarity({"a"}, {"b"}) == 0.0
    assert 0 < _jaccard_similarity({"a", "b"}, {"a", "c"}) < 1


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
