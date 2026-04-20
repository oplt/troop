"""Optional LangGraph router over existing orchestration executors.

When ``ORCHESTRATION_USE_LANGGRAPH`` is enabled, ``OrchestrationService.execute_run`` dispatches
through a compiled ``StateGraph`` so run modes are explicit graph edges (supervisor / multi-agent
shapes from product_idea §8) while Celery remains the process-level durable queue (ADR 0004).

**Checkpoint thread id:** ``TaskRun.checkpoint_json["execution_thread_id"]`` is set to ``run.id``
when execution starts; use the same value if wiring an external LangGraph checkpoint store.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.modules.orchestration.models import TaskRun


class OrchestrationGraphState(TypedDict, total=False):
    """Minimal state — routing is by ``run_mode`` on the bound ``TaskRun``."""

    run_mode: str


def _normalize_run_mode(mode: str | None) -> str:
    allowed = frozenset({"brainstorm", "review", "debate", "manager_worker", "single_agent"})
    if mode in allowed:
        return mode
    return "single_agent"


def _route_run_mode(state: OrchestrationGraphState) -> str:
    return _normalize_run_mode(state.get("run_mode"))


async def run_via_langgraph(service, run: TaskRun) -> None:
    """Execute the run by routing ``run_mode`` through a LangGraph ``StateGraph``.

    Each terminal node delegates to the existing private executors on ``OrchestrationService`` so
    behaviour matches the legacy ``if/elif`` chain.
    """
    async def n_brainstorm(_: OrchestrationGraphState) -> OrchestrationGraphState:
        await service._execute_brainstorm_run(run)
        return {}

    async def n_review(_: OrchestrationGraphState) -> OrchestrationGraphState:
        await service._execute_review_run(run)
        return {}

    async def n_debate(_: OrchestrationGraphState) -> OrchestrationGraphState:
        await service._execute_debate_run(run)
        return {}

    async def n_manager_worker(_: OrchestrationGraphState) -> OrchestrationGraphState:
        await service._execute_manager_worker_run(run)
        return {}

    async def n_single_agent(_: OrchestrationGraphState) -> OrchestrationGraphState:
        await service._execute_single_agent_run(run)
        return {}

    graph = StateGraph(OrchestrationGraphState)
    graph.add_node("brainstorm", n_brainstorm)
    graph.add_node("review", n_review)
    graph.add_node("debate", n_debate)
    graph.add_node("manager_worker", n_manager_worker)
    graph.add_node("single_agent", n_single_agent)

    graph.add_conditional_edges(
        START,
        _route_run_mode,
        {
            "brainstorm": "brainstorm",
            "review": "review",
            "debate": "debate",
            "manager_worker": "manager_worker",
            "single_agent": "single_agent",
        },
    )
    for name in ("brainstorm", "review", "debate", "manager_worker", "single_agent"):
        graph.add_edge(name, END)

    compiled = graph.compile()
    await service._emit_run_event(
        run,
        event_type="langgraph_router",
        message="Run mode dispatched via LangGraph (ORCHESTRATION_USE_LANGGRAPH).",
        payload={"run_mode": _normalize_run_mode(run.run_mode)},
    )
    await compiled.ainvoke({"run_mode": run.run_mode})
