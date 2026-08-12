"""Unit tests for WorkflowRuntimeService node execution and pause/resume gates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.modules.orchestration.tool_execution_context import arguments_hash
from backend.modules.workforce.services.workflow_conditions import evaluate_condition
from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService


def _make_run(
    *, current_node_id: str, status: str = "running", vars_: dict | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        id="run-1",
        workflow_id="wf-1",
        workflow_version_id="wv-1",
        project_id="proj-1",
        task_id="task-1",
        status=status,
        current_node_id=current_node_id,
        context_json={"completed": [], "vars": dict(vars_ or {})},
        result_json={},
        created_by="user-1",
    )


def _make_version(nodes: list[dict], edges: list[dict] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id="wv-1",
        nodes_json=nodes,
        edges_json=edges or [],
        entry_node_id=nodes[0]["id"] if nodes else None,
    )


@pytest.mark.asyncio
async def test_human_input_pauses_until_payload_then_completes() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    runtime = WorkflowRuntimeService(db)

    run = _make_run(current_node_id="input-1")
    version = _make_version(
        [
            {"id": "input-1", "type": "human_input"},
            {
                "id": "done-1",
                "type": "condition",
                "config": {"operator": "truthy", "left": {"var": "answer"}, "right": True},
            },
        ],
        [{"from": "input-1", "to": "done-1"}],
    )

    await runtime._advance(run, version)
    assert run.status == "waiting_input"
    assert run.current_node_id == "input-1"

    run.context_json["vars"]["human_input"] = {"answer": "yes"}
    run.context_json["vars"]["human_input_by"] = "user-1"
    run.status = "running"
    await runtime._advance(run, version)

    assert run.status == "completed"
    assert "input-1" in run.context_json["completed"]
    assert "done-1" in run.context_json["completed"]
    assert "human_input" not in run.context_json["vars"]


@pytest.mark.asyncio
async def test_tool_node_executes_via_tool_execution_service() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    runtime = WorkflowRuntimeService(db)

    run = _make_run(current_node_id="tool-1")
    version = _make_version(
        [{"id": "tool-1", "type": "tool", "config": {"tool": "web_search", "params": {"q": "x"}}}]
    )

    with patch(
        "backend.modules.workforce.services.tool_execution_service.ToolExecutionService.execute",
        new_callable=AsyncMock,
        return_value={
            "status": "succeeded",
            "tool_slug": "web_search",
            "output": {"query": "x", "results": []},
            "evidence": None,
        },
    ) as execute_tool:
        await runtime._advance(run, version)

    execute_tool.assert_awaited_once()
    assert run.status == "completed"
    assert run.context_json["vars"]["tool_result_tool-1"]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_tool_node_pauses_on_approval_required() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    runtime = WorkflowRuntimeService(db)

    run = _make_run(current_node_id="tool-1")
    version = _make_version([{"id": "tool-1", "type": "tool", "config": {"tool_slug": "fs_write"}}])

    with (
        patch.object(
            runtime,
            "_create_workflow_approval_request",
            new_callable=AsyncMock,
            return_value="appr-new",
        ),
        patch(
            "backend.modules.workforce.services.tool_execution_service.ToolExecutionService.execute",
            new_callable=AsyncMock,
            return_value={"status": "approval_required", "decision": "approval_required"},
        ),
    ):
        await runtime._advance(run, version)

    assert run.status == "waiting_approval"
    pending = run.context_json["vars"]["pending_tool"]
    assert pending["tool_slug"] == "fs_write"
    assert pending["node_id"] == "tool-1"
    assert pending["approval_request_id"] == "appr-new"
    assert run.context_json["vars"]["pending_approval_request_id"] == "appr-new"


@pytest.mark.asyncio
async def test_tool_node_resumes_after_consumed_approval() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    runtime = WorkflowRuntimeService(db)

    run = _make_run(
        current_node_id="tool-1",
        status="waiting_approval",
        vars_={
            "pending_tool": {
                "node_id": "tool-1",
                "tool_slug": "fs_write",
                "params": {"path": "/tmp/x"},
                "context": {"owner_id": "user-1"},
                "approval_consumed": True,
                "approval_request_id": "appr-1",
            }
        },
    )
    version = _make_version([{"id": "tool-1", "type": "tool", "config": {"tool_slug": "fs_write"}}])

    with patch(
        "backend.modules.workforce.services.tool_execution_service.ToolExecutionService.execute",
        new_callable=AsyncMock,
        return_value={
            "status": "succeeded",
            "tool_slug": "fs_write",
            "output": {"path": "/tmp/x"},
            "evidence": None,
        },
    ) as execute_tool:
        await runtime._advance(run, version)

    execute_tool.assert_awaited_once()
    call_context = execute_tool.await_args.args[3]
    assert call_context["approval_granted"] is True
    assert call_context["approval_request_id"] == "appr-1"
    assert run.status == "completed"
    assert "pending_tool" not in run.context_json["vars"]


@pytest.mark.asyncio
async def test_strict_tool_approval_rejects_missing_arguments_hash() -> None:
    db = AsyncMock()
    runtime = WorkflowRuntimeService(db)

    run = _make_run(current_node_id="tool-1")
    vars_ = {
        "pending_tool": {
            "node_id": "tool-1",
            "tool_slug": "fs_write",
            "params": {"path": "/tmp/x"},
        }
    }
    approval = SimpleNamespace(
        id="appr-1",
        status="approved",
        project_id="proj-1",
        approved_by_user_id="user-2",
        approval_type="tool:fs_write",
        payload_json={
            "workflow_run_id": "run-1",
            "workflow_node_id": "tool-1",
            "action_key": "tool:fs_write",
        },
    )
    db.get = AsyncMock(return_value=approval)

    with pytest.raises(ValueError, match="arguments_hash"):
        await runtime._consume_approval_for_node(
            "appr-1",
            run=run,
            node_id="tool-1",
            vars_=vars_,
            actor_user_id="user-2",
            pending_tool=True,
        )


@pytest.mark.asyncio
async def test_condition_evaluator_gte() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    runtime = WorkflowRuntimeService(db)

    run = _make_run(current_node_id="cond-1", vars_={"score": 90})
    version = _make_version(
        [
            {
                "id": "cond-1",
                "type": "condition",
                "config": {
                    "operator": "gte",
                    "left": {"var": "score"},
                    "right": 80,
                },
            }
        ]
    )

    await runtime._advance(run, version)

    assert run.status == "completed"
    assert run.context_json["vars"]["_last_condition"] is True
    assert evaluate_condition(
        {"operator": "gte", "left": {"var": "score"}, "right": 80},
        {"score": 90},
    )


@pytest.mark.asyncio
async def test_approval_node_creates_approval_request() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    runtime = WorkflowRuntimeService(db)

    run = _make_run(current_node_id="appr-node")
    version = _make_version([{"id": "appr-node", "type": "approval", "config": {}}])

    with patch.object(
        runtime,
        "_create_workflow_approval_request",
        new_callable=AsyncMock,
        return_value="appr-workflow-1",
    ) as create_approval:
        await runtime._advance(run, version)

    create_approval.assert_awaited_once()
    assert run.status == "waiting_approval"
    assert run.context_json["vars"]["pending_approval_request_id"] == "appr-workflow-1"


@pytest.mark.asyncio
async def test_delay_node_pauses_with_resume_at() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    runtime = WorkflowRuntimeService(db)

    run = _make_run(current_node_id="delay-1")
    version = _make_version([{"id": "delay-1", "type": "delay", "config": {"seconds": 60}}])

    with patch(
        "backend.modules.workforce.services.workflow_runtime.WorkflowRuntimeService._schedule_delay_resume"
    ):
        await runtime._advance(run, version)

    assert run.status == "paused"
    delay_state = run.context_json["vars"]["_delay_resume"]
    assert delay_state["node_id"] == "delay-1"
    resume_at = datetime.fromisoformat(delay_state["resume_at"])
    assert resume_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_delay_node_completes_when_resume_at_passed() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    runtime = WorkflowRuntimeService(db)

    past = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    run = _make_run(
        current_node_id="delay-1",
        vars_={"_delay_resume": {"node_id": "delay-1", "resume_at": past}},
    )
    version = _make_version([{"id": "delay-1", "type": "delay", "config": {"seconds": 60}}])

    await runtime._advance(run, version)

    assert run.status == "completed"
    assert "_delay_resume" not in run.context_json["vars"]


@pytest.mark.asyncio
async def test_skill_node_resolves_version_into_vars() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.get = AsyncMock(
        return_value=SimpleNamespace(
            id="sv-1",
            skill_id="skill-1",
            version_number=2,
            instructions_markdown="Do the thing",
            required_tools_json=["web_search"],
            capabilities_json=["research"],
        )
    )
    runtime = WorkflowRuntimeService(db)

    run = _make_run(current_node_id="skill-1")
    version = _make_version(
        [{"id": "skill-1", "type": "skill", "config": {"skill_version_id": "sv-1"}}]
    )

    await runtime._advance(run, version)

    payload = run.context_json["vars"]["skill_payload"]
    assert payload["skill_version_id"] == "sv-1"
    assert payload["instructions_markdown"] == "Do the thing"
    assert run.status == "completed"


def test_arguments_hash_stable_for_tool_params() -> None:
    assert arguments_hash({"path": "/tmp/x"}) == arguments_hash({"path": "/tmp/x"})


def test_evaluate_parallel_join_fail_fast() -> None:
    runtime = WorkflowRuntimeService(AsyncMock())

    assert runtime._evaluate_parallel_join("fail_fast", ["succeeded", "succeeded"]) == "succeeded"
    assert runtime._evaluate_parallel_join("fail_fast", ["succeeded", "failed"]) == "failed"
    assert runtime._evaluate_parallel_join("fail_fast", ["succeeded", "pending"]) == "paused"
    assert runtime._evaluate_parallel_join("fail_fast", ["paused", "pending"]) == "paused"
    assert runtime._evaluate_parallel_join("fail_fast", ["failed", "pending"]) == "failed"


def test_evaluate_parallel_join_n_of_m() -> None:
    runtime = WorkflowRuntimeService(AsyncMock())

    assert (
        runtime._evaluate_parallel_join("n_of_m", ["succeeded", "pending", "pending"], n=2)
        == "paused"
    )
    assert (
        runtime._evaluate_parallel_join("n_of_m", ["succeeded", "succeeded", "pending"], n=2)
        == "succeeded"
    )
    assert (
        runtime._evaluate_parallel_join("n_of_m", ["succeeded", "failed", "failed"], n=2)
        == "failed"
    )
    assert runtime._evaluate_parallel_join("2_of_3", ["succeeded", "failed", "pending"]) == "paused"
    assert (
        runtime._evaluate_parallel_join("2_of_3", ["succeeded", "succeeded", "failed"])
        == "succeeded"
    )


def test_parse_parallel_join_config_from_policy_string() -> None:
    from backend.modules.workforce.services.workflow_runtime import _parse_parallel_join_config

    policy, n = _parse_parallel_join_config({"join_policy": "2_of_3"})
    assert policy == "n_of_m"
    assert n == 2

    policy, n = _parse_parallel_join_config({"join_policy": "n_of_m", "min_success": 2})
    assert policy == "n_of_m"
    assert n == 2
