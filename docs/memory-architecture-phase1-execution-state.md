# Memory architecture — Phase 1 (execution state)

This document fulfills **Phase 1** from `memory_tasks.txt`: **Layer 1** as an explicit, **non-vector** contract, with **Celery + Postgres** as execution truth until a durable workflow runner (see [ADR 0004](adr/0004-langgraph-and-temporal-execution-plane.md)) replaces or augments it.

Related: [Phase 0 spec](memory-architecture-phase0.md).

---

## 1. What counts as execution truth

**Authoritative sources** (reads by primary key, filters, and joins — never embedding search):

| Source | Role |
|--------|------|
| `orchestrator_tasks` | Task lifecycle (`status`), SLA-related and handoff hints in `metadata_json` |
| `task_runs` | Run lifecycle, agents, costs, `checkpoint_json`, I/O payloads |
| `run_events` | Append-only execution log (tool calls, LLM milestones, failures) |
| `approval_requests` | Human gates (`pending` / resolved) scoped to task, run, or GitHub issue link |
| `github_sync_events` | Outbound / webhook queue rows (`queued`, `pending`, `completed`, `ignored`, …) |

**Queue / worker plane:** `submit_orchestration_run` (Celery) is the **durable “start work” signal**. The worker still **commits outcomes** to `task_runs` and `run_events`. If those rows are missing or inconsistent, **vector search cannot repair execution state**.

**Not execution truth:** `project_document_chunks` and any `search_document_chunks_by_vector` usage. That path is **prompt enrichment only** (documented on `_search_project_knowledge` in `service.py`).

---

## 2. Read API: execution snapshots

Stable read surfaces for workers and UI (no new tables in Phase 1):

| Method | Route |
|--------|--------|
| Task-scoped snapshot | `GET /orchestration/projects/{project_id}/tasks/{task_id}/execution-state` |
| Run-scoped snapshot | `GET /orchestration/runs/{run_id}/execution-state` |

Response bodies are versioned with `meta.schema_version` (currently `1.0`) and include `meta.execution_truth` (human-readable reminder) plus `meta.sources_read` (logical table list).

**Task snapshot** includes: active runs (`queued` / `in_progress` / `blocked`), pending approvals (including approvals tied via `github_issue_links` to the task), pending GitHub sync events for the task, structured views of `metadata_json` (handoff/SLA hints, optional `execution_memory` ref), focal run id (newest active run or else latest run), bounded `checkpoint_excerpt` from that focal run, and a short tail of `run_events` for that focal run.

**Run snapshot** includes: full `TaskRun` payload, pending approvals for that `run_id`, pending GitHub sync for the linked task (if any), `checkpoint_excerpt`, and a longer `run_events` tail.

Implementation modules: `backend/modules/orchestration/execution_state.py` (constants + pure helpers), repository filters, `OrchestrationService.get_task_execution_snapshot` / `get_run_execution_snapshot`, schemas in `schemas.py`, routes in `router.py`.

---

## 3. Temporal / Celery gap note (ADR 0004)

Until Temporal (or equivalent) stores **replay-safe workflow history** as the system of record, **Postgres rows above remain canonical** for “what is running / blocked / approved.” A future migration would move **durable execution history** to workflow events while keeping **project/task semantic data** and **audit** in SQL as needed. Phase 1 does not add Temporal tables; it only documents the split and exposes snapshots over existing data.

---

## 4. Invariants (Phase 1)

1. No orchestration **correctness** path may **require** embedding search (status transitions, approvals, run scheduling).
2. Execution snapshots are **read-only** and composed from the sources in §1.
3. `checkpoint_excerpt` and event tails are **bounded** for API stability; full checkpoints and full event streams remain on existing endpoints.
