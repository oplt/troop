from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.modules.orchestration.services.approvals_domain import ApprovalsService
from backend.modules.orchestration.services.execution_domain import ExecutionService
from backend.modules.orchestration.services.evals_domain import EvalsService
from backend.modules.orchestration.services.brainstorm_domain import BrainstormService
from backend.modules.orchestration.services.github_sync_domain import GithubSyncService
from backend.modules.orchestration.services.knowledge_domain import KnowledgeService
from backend.modules.orchestration.services.memory_domain import MemoryService
from backend.modules.orchestration.services.service import OrchestrationService


@pytest.fixture
def db_session() -> MagicMock:
    return MagicMock()


def test_orchestration_service_composes_domain_services(db_session: MagicMock) -> None:
    service = OrchestrationService(db_session)

    assert isinstance(service.approvals, ApprovalsService)
    assert isinstance(service.execution, ExecutionService)
    assert isinstance(service.memory, MemoryService)
    assert isinstance(service.github_sync, GithubSyncService)
    assert isinstance(service.evals, EvalsService)
    assert isinstance(service.brainstorm, BrainstormService)
    assert isinstance(service.knowledge, KnowledgeService)
    assert service.execution is not service.memory
    assert service.memory is not service.github_sync


def test_orchestration_service_delegates_execution_methods(db_session: MagicMock) -> None:
    service = OrchestrationService(db_session)

    assert service.execute_run.__func__ is service.execution.execute_run.__func__
    assert service.cancel_run.__func__ is service.execution.cancel_run.__func__


def test_orchestration_service_delegates_approval_methods(db_session: MagicMock) -> None:
    service = OrchestrationService(db_session)

    assert service.list_approvals.__func__ is service.approvals.list_approvals.__func__
    assert service.decide_approval.__func__ is service.approvals.decide_approval.__func__


def test_orchestration_service_delegates_memory_methods(db_session: MagicMock) -> None:
    service = OrchestrationService(db_session)

    assert service.upload_document.__func__ is service.memory.upload_document.__func__
    assert service.get_working_memory.__func__ is service.memory.get_working_memory.__func__


def test_orchestration_service_delegates_github_methods(db_session: MagicMock) -> None:
    service = OrchestrationService(db_session)

    assert service.replay_github_sync_event.__func__ is service.github_sync.replay_github_sync_event.__func__


def test_orchestration_service_delegates_evals_and_brainstorm_methods(db_session: MagicMock) -> None:
    service = OrchestrationService(db_session)

    assert service.list_eval_records.__func__ is service.evals.list_eval_records.__func__
    assert service.create_brainstorm.__func__ is service.brainstorm.create_brainstorm.__func__


def test_knowledge_service_delegates_to_memory_host(db_session: MagicMock) -> None:
    memory = MemoryService(db_session)
    knowledge = KnowledgeService(memory)

    assert (
        knowledge.create_knowledge_graph_edge_for_project.__func__
        is memory.create_knowledge_graph_edge_for_project.__func__
    )
    assert (
        knowledge.list_knowledge_graph_edges_for_project.__func__
        is memory.list_knowledge_graph_edges_for_project.__func__
    )


def test_domain_services_share_session(db_session: MagicMock) -> None:
    service = OrchestrationService(db_session)

    assert service.approvals.db is db_session
    assert service.execution.db is db_session
    assert service.memory.db is db_session
    assert service.github_sync.db is db_session
    assert service.evals.db is db_session
    assert service.brainstorm.db is db_session


def test_orchestration_service_exposes_shell_methods(db_session: MagicMock) -> None:
    service = OrchestrationService(db_session)

    assert hasattr(service, "get_project")
    assert hasattr(service, "list_eval_records")
