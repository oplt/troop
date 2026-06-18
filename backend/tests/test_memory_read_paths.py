from __future__ import annotations

import inspect

from backend.modules.memory.service import OrchestrationMemoryServiceMixin
from backend.workers.orchestration import memory_expiration_sweep


def test_read_paths_do_not_expire_memory_on_access():
    for method_name in ("list_documents", "_search_project_knowledge", "list_project_memory"):
        source = inspect.getsource(getattr(OrchestrationMemoryServiceMixin, method_name))
        assert "_expire_project_memory" not in source


def test_memory_expiration_sweep_task_is_registered():
    assert memory_expiration_sweep.name == "backend.workers.orchestration.memory_expiration_sweep"


def test_global_sweep_remains_available():
    assert hasattr(OrchestrationMemoryServiceMixin, "sweep_expired_memory_globally")
