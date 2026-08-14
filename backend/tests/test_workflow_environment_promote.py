"""Async tests for workflow environment promotion rules."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.modules.workforce.models import WorkflowDefinition
from backend.modules.workforce.services.workflow_environment_service import WorkflowEnvironmentService


@pytest.mark.asyncio
async def test_promote_to_prod_rejects_dev_installation() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    definition = WorkflowDefinition(
        id="wf-1",
        owner_id="owner-1",
        slug="demo",
        name="Demo",
    )
    version = SimpleNamespace(
        id="ver-1",
        workflow_id="wf-1",
        is_published=True,
        version_number=1,
        nodes_json=[
            {
                "id": "send",
                "type": "tool",
                "config": {"tool_slug": "gmail.send_draft"},
            }
        ],
        edges_json=[],
        entry_node_id="send",
    )
    installation = SimpleNamespace(id="inst-dev", owner_id="owner-1", environment="dev")

    service = WorkflowEnvironmentService(db)
    service.version_service.get_version = AsyncMock(return_value=version)
    service.get_deployment = AsyncMock(return_value=None)

    async def _execute(stmt):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [installation]))

    db.execute = AsyncMock(side_effect=_execute)

    with pytest.raises(ValueError) as exc:
        await service.promote(
            definition,
            environment="prod",
            version_id="ver-1",
            connection_bindings={"send": {"connector_installation_id": "inst-dev"}},
            actor_user_id="owner-1",
        )

    detail = exc.value.args[0]
    assert isinstance(detail, dict)
    assert any("cannot be used in `prod`" in err for err in detail["errors"])
