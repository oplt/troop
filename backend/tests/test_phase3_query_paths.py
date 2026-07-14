from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from backend.modules.orchestration.repository import OrchestrationRepository


@pytest.mark.asyncio
async def test_project_task_page_and_dependencies_are_loaded_in_one_bounded_query():
    first = SimpleNamespace(id="task-1", position=0, created_at=1)
    second = SimpleNamespace(id="task-2", position=1, created_at=2)
    dependency = SimpleNamespace(task_id="task-2", depends_on_task_id="task-1", created_at=3)
    db = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                all=lambda: [(first, None), (second, dependency)],
            )
        )
    )

    tasks, dependencies = await OrchestrationRepository(db).list_tasks_with_dependencies(
        "project-1", limit=25
    )

    assert [item.id for item in tasks] == ["task-1", "task-2"]
    assert dependencies == {"task-2": ["task-1"]}
    db.execute.assert_awaited_once()
    statement = str(db.execute.await_args.args[0]).lower()
    assert "left outer join task_dependencies" in statement
    assert "limit" in statement
    assert "orchestrator_tasks.id in (select orchestrator_tasks.id" in statement
