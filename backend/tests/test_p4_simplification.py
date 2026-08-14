"""P4 code simplification smoke tests."""

from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_projects_router_removed():
    assert not (BACKEND_ROOT / "modules/projects/router.py").exists()
    assert not (BACKEND_ROOT / "modules/projects/repository.py").exists()


def test_projects_service_has_no_legacy_class():
    from backend.modules.projects import service as projects_service

    assert not hasattr(projects_service, "ProjectsService")
    assert hasattr(projects_service, "OrchestrationProjectsServiceMixin")


def test_orchestration_router_uses_presenters():
    text = (BACKEND_ROOT / "modules/orchestration/router.py").read_text()
    assert "to_task_response as _task" in text
    assert "def _task(" not in text
    assert "def _run(" not in text
    assert "def _event(" not in text


def test_shared_validation_token_jaccard():
    from backend.core.validation.text import token_jaccard, token_jaccard_alnum

    assert token_jaccard("hello world", "hello there") > 0
    assert token_jaccard_alnum("hello world", "hello there") > 0


def test_compatibility_module_still_deleted():
    assert not (BACKEND_ROOT / "modules/workforce/services/compatibility.py").exists()


def test_execution_service_collapsed_mro():
    from backend.modules.orchestration.services.base import (
        OrchestrationRunQueryMixin,
        OrchestrationServiceBase,
    )
    from backend.modules.orchestration.services.execution_backend import (
        ExecutionCapabilitiesMixin,
    )
    from backend.modules.orchestration.services.execution_domain import ExecutionService

    assert ExecutionService.__bases__ == (
        OrchestrationRunQueryMixin,
        OrchestrationServiceBase,
        ExecutionCapabilitiesMixin,
    )


def test_github_http_client_module():
    from backend.modules.github import http_client

    assert callable(http_client.github_request)
    assert callable(http_client.connection_mode)


def test_orchestration_schemas_package():
    from backend.modules.orchestration import schemas

    assert hasattr(schemas, "AgentResponse")
    assert hasattr(schemas, "RunEventResponse")
    assert (BACKEND_ROOT / "modules/orchestration/schemas/agents.py").is_file()
    assert not (BACKEND_ROOT / "modules/orchestration/schemas.py").exists()


def test_memory_episodic_jobs_mixin_extracted():
    from backend.modules.memory.episodic_jobs import EpisodicJobsMixin
    from backend.modules.memory.service import OrchestrationMemoryServiceMixin

    assert EpisodicJobsMixin in OrchestrationMemoryServiceMixin.__mro__
    text = (BACKEND_ROOT / "modules/memory/service.py").read_text()
    assert "async def search_episodic_memory(" not in text
    assert (BACKEND_ROOT / "modules/memory/episodic_jobs.py").is_file()


def test_orchestration_repository_agents_mixin():
    from backend.modules.orchestration.repository import OrchestrationRepository
    from backend.modules.orchestration.repository.agents import OrchestrationAgentsRepositoryMixin

    assert OrchestrationAgentsRepositoryMixin in OrchestrationRepository.__mro__
    text = (BACKEND_ROOT / "modules/orchestration/repository/__init__.py").read_text()
    assert "async def list_agents(" not in text
    assert (BACKEND_ROOT / "modules/orchestration/repository/agents.py").is_file()


def test_routing_llm_invoke_module():
    from backend.modules.orchestration.services.routing import llm_invoke

    assert callable(llm_invoke.build_model_candidates)
    assert callable(llm_invoke.build_provider_failover_chain)
    assert (BACKEND_ROOT / "modules/orchestration/services/routing/llm_invoke.py").is_file()
