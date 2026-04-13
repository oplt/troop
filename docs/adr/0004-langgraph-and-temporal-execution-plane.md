# ADR 0004: LangGraph (optional) + Celery today; Temporal later

## Status

Accepted

## Context

`product_idea.txt` §8 recommends **LangGraph / LangChain** for agent graphs and **Temporal** for durable long-running workflows. ADR 0003 deferred a hard LangGraph dependency until checkpointing needs exceeded `TaskRun` + `RunEvent`.

Troop still runs a **modular monolith**: FastAPI, async SQLAlchemy, **Celery** for worker dispatch, Redis for broker/cache.

## Decision

1. **Celery remains the primary durable execution plane** for process boundaries, retries, and queueing (unchanged from ADR 0002).
2. **LangGraph is an optional in-process router** behind `ORCHESTRATION_USE_LANGGRAPH=true`. When enabled, `OrchestrationService.execute_run` dispatches run modes through a compiled `StateGraph`; each node calls the existing `_execute_*` methods so behaviour stays aligned with the legacy branch.
3. **Temporal is not introduced** in this iteration. When workflow requirements need first-class signals, child workflows, or cross-day replay independent of Celery task semantics, add a `submit_orchestration_run` implementation backed by Temporal and route via settings (see `backend/modules/orchestration/durable_execution.py`).
4. **LangChain** enters the dependency tree transitively via `langgraph` → `langchain-core`; we do not require application code to use LCEL for non-graph paths.

## Consequences

- Operators can turn on LangGraph routing without new infrastructure.
- Graph checkpoints use LangGraph defaults in-process; **durable** history remains `run_events` + Postgres, not Temporal workflow history.
- One more dependency surface (`langgraph`, `langchain-core`); keep versions pinned in `uv.lock`.
- Revisit when/if Temporal is adopted: extract `submit_orchestration_run` to a Temporal client and keep LangGraph nodes thin (I/O still asyncio inside workers).

## References

- [LangGraph overview](https://langchain-ai.github.io/langgraph/)
- [Temporal workflows](https://docs.temporal.io/workflows)
- ADR 0002 (Celery), ADR 0003 (vision alignment)
