# Backend Architecture Refactor Result

Completed: 2026-08-14

## Outcome

The backend now has one application namespace. `backend/app` is removed. Its legacy public endpoints remain available under an explicitly named HTTP compatibility package, while memory, runtime tools, workspaces, planned-run execution, and observability use canonical domain owners.

No database schema or Alembic revision was added.

## Files moved and deleted

The following are semantic moves; implementation was reshaped instead of blindly relocating folders.

| Removed source | New owner |
| --- | --- |
| `app/agents/router.py` | split into `api/compat/agents.py`, `tasks.py`, `runs.py`, `memory.py`, and `tools.py` |
| `app/agents/application.py` | `modules/orchestration/services/planned_runs.py` |
| `app/agents/workspace.py` | `modules/orchestration/workspace/storage.py` and `service.py` |
| `app/agents/memory/base.py` | removed; compatibility API calls canonical `modules.memory.layer.MemoryService` |
| `app/agents/tools/registry.py` | removed; compatibility aliases derive policy from the workforce native catalog |
| `app/agents/logging.py` | removed; events use canonical observability logging |
| `modules/orchestration/services/application.py` | removed; zero-value facade and repository escape hatch no longer needed |

Deleted:

- all ten tracked files under `backend/app`;
- the unused `OrchestrationApplicationService` file/export/dependency provider;
- generated `backend/app` bytecode and stale build/egg metadata found during validation.

## Modules created

### `backend/api/compat`

Eight small transport modules preserve these public contracts:

- `/api/v1/agents`
- `/api/v1/tools`
- `/api/v1/tasks`
- `/api/v1/tasks/{task_id}/runs`
- `/api/v1/runs/{run_id}` and run subresources
- `/api/v1/memory`

Routers validate transport input, resolve authentication/database dependencies, call services, translate planned-run errors, and present responses. They no longer query SQLAlchemy directly or access files directly.

The former 419-line mixed router is split into resource files; the largest compatibility router is 145 lines.

### `backend/modules/orchestration/services/planned_runs.py`

`PlannedRunService` owns the deterministic compatibility plan lifecycle:

- authorized task/project lookup;
- run and checkpoint creation;
- plan approval under a locked run row;
- run events and state transitions;
- workspace artifact creation;
- database artifact metadata;
- transaction commits;
- structured, context-aware observability events.

New planned-run exceptions are framework-neutral and translated to HTTP responses in `api/compat/runs.py`. Existing project authorization still uses the current orchestration facade and its legacy HTTP error contract; replacing all domain `HTTPException` use remains separate debt.

### `backend/modules/orchestration/workspace`

- `WorkspaceStorage` protocol defines list/write operations.
- `LocalWorkspaceStorage` is the current adapter.
- `RunWorkspaceService` maps an already-authorized `TaskRun` to a storage key.

Preserved security behavior:

- relative paths only;
- resolved-path containment;
- traversal and absolute-path rejection;
- secret filename rejection;
- extension allowlist;
- 2 MiB content limit;
- collision-safe filenames.

Filesystem operations are dispatched through `asyncio.to_thread`, so async request paths no longer perform blocking local I/O. S3/object-storage implementation was intentionally not added.

## Architecture decisions

### Agent definitions

Agent definitions have an independent lifecycle and semantically deserve a future `modules/agents` bounded domain. The current model/service/repository graph is deeply coupled across `team`, projects, workforce, and orchestration. A partial move would create a second false owner.

Current canonical owner is therefore explicit:

- model and lifecycle: `modules/team/AgentProfile` and `TeamServiceMixin`;
- compatibility HTTP delivery: `api/compat/agents.py`;
- run participation/execution: `modules/orchestration`.

An atomic `team -> agents` extraction remains follow-up work. No duplicate Agent model or re-export shell was created.

### Memory

`modules/memory/layer/service.py::MemoryService` is the single agent-facing memory service. It now exposes direct `get_memory` and non-embedding `list_memories` operations in addition to add/search/update/delete.

Improvements:

- removed `SqlMemoryStore`;
- removed list/search N+1 ORM reloads;
- compatibility responses use `MemoryRecord`;
- added explicit `task_id` to `MemoryRecord`;
- fixed company filtering to use `company_id`, not `user_id`;
- fixed company/task scope mapping at compatibility transport.

The memory SQL repository still delegates substantial operations to the orchestration repository. Extracting module-owned SQL is documented debt.

### Runtime tools

Runtime tool policy remains canonical in:

- `modules/workforce/constants.py::NATIVE_TOOL_CATALOG`;
- `modules/workforce/services/tool_registry.py`;
- `modules/workforce/services/tool_execution_service.py`;
- `modules/orchestration/tools.py` for execution-context dispatch.

Legacy tool names are explicit compatibility aliases. Risk and approval flags come from the canonical catalog, so the compatibility API cannot weaken policy. `backend/tools` remains developer/maintenance tooling.

### Observability

The private agent JSONL sink is gone. Agent/task/run compatibility events use `modules.observability.logging.log_event` and safe request/job context. No prompts, credentials, tokens, or complete private payloads are added to logs.

### Approvals/HITL

Canonical tool/external-effect approval remains in orchestration HITL and workforce action policy. `/approve-plan` remains a distinct deterministic-placeholder compatibility contract and is not reused as generic tool approval.

### AI gateway

`modules/ai` is documented as the target canonical owner of provider invocation, retry/fallback, token/cost accounting, and provider integration. The existing persisted-provider execution implementation in `modules/orchestration/providers.py` remains active because its routing, persistence, and provider-discovery coupling is too broad for a safe move in this change. No third abstraction was added.

## Dependency improvements

- `backend.api.router -> backend.api.compat.router`; no production `backend.app` edge remains.
- Compatibility transport depends on canonical services, schemas, presenters, and catalog data.
- Memory API no longer depends on an agent-specific SQL adapter.
- Planned-run service no longer depends on FastAPI or the private logging subsystem.
- Workspace persistence sits behind a protocol and no longer performs database authorization itself.
- Run event/artifact reads are behind orchestration service/repository methods; routers issue no SQL.
- A targeted architecture test prohibits non-router `backend.modules` files from importing `backend.api`.

The repository-wide domain dependency graph still contains large cycles. These are listed under remaining debt.

## Packaging and startup

`pyproject.toml` package discovery was corrected, not merely stripped of `app*`:

```text
package-dir "" = ".."
find where = [".."]
include = ["backend*"]
namespaces = false
```

Before the fix, a wheel shipped `api`, `core`, `db`, `modules`, and `workers` as top-level packages even though production imports use `backend.*`. A clean wheel now contains only the real `backend` package tree, includes compatibility/workspace modules, and contains no `app` package.

CI Ruff targets were updated to remove `app`, and the obsolete exclusion for `test_deerflow_adapters.py` was removed. The logging-policy tool no longer scans a nonexistent `app` package.

## Tests added and updated

Added:

- `tests/test_architecture_boundaries.py`
  - no `backend/app` directory;
  - no production `backend.app` imports;
  - non-router modules cannot import `backend.api`;
  - compatibility public paths remain registered;
  - company/task memory scope mapping is explicit.
- `tests/test_planned_run_service.py`
  - planned run and plan event creation;
  - plan approval, step events, workspace output, artifact metadata, and commit.

Updated:

- DeerFlow compatibility tests now target the compatibility translator and workspace policy.
- Workspace tests cover traversal, absolute paths, secret names, extension policy, collision handling, listing, and size limits.
- Memory tests cover canonical get/list without an ORM reload adapter.
- Phase 6 presenter test targets the split agent compatibility router.

## Validation results

### Passing

- Scoped Ruff check for changed production/test files: passed.
- Scoped Ruff format check: 19 files already formatted.
- Focused architecture/memory/orchestration/worker/storage/migration suite: **66 passed, 12 deselected**.
- Broad non-integration suite excluding known baseline-failure/sandbox-stall files: **733 passed, 2 skipped, 27 deselected**.
- Compatibility/planned-run tests: passed.
- External HTTP-client policy: passed.
- Runtime logging policy: passed.
- Security posture audit, config-only: 0 findings.
- Clean wheel build and package-content assertions: passed.
- FastAPI import/router registration: passed; compatibility paths present.
- Celery app plus orchestration task-module import: passed; expected task names registered.
- SQLAlchemy model metadata import: passed; full app/worker smoke registered 109 tables.
- Alembic heads: one head, `t5u6v7w8x9y0`.
- Scoped `git diff --check`: passed.
- Production search: no `backend.app` or `OrchestrationApplicationService` imports.

### Repository baseline failures not changed

An unfiltered run selected 927 non-integration tests but could not complete cleanly in this sandbox. File-isolated runs identified 13 existing failures outside this refactor:

- workforce action metadata/external-effect inventory lacks `invoke_specialist` and has catalog expectation drift;
- a knowledge-search test uses a non-awaitable mock;
- connector-manifest expected providers are stale;
- a tool-authorization expected decision differs from current policy;
- one public webhook test requires unavailable Redis;
- a platform webhook-secret test targets a removed private method;
- a project query-path expectation differs from current projection behavior;
- rate-limit tests patch a removed `execution_service.settings` attribute.

Three files also stall or time out under this managed sandbox's threaded/external execution behavior: concurrency opportunities, filesystem tools, and phase-7 queue metrics. These were not caused by this refactor. PostgreSQL/Redis integration tests and `alembic upgrade head` were not run because those services are unavailable here.

Repository-wide Ruff remains baseline-red:

- `ruff check`: 59 errors (26 import-order, 17 unused-import, and 16 other existing findings);
- `ruff format --check`: 70 existing unformatted files.

No unrelated mass formatting or baseline lint cleanup was performed.

## Final relevant backend tree

```text
backend/
├── api/
│   ├── compat/
│   │   ├── __init__.py
│   │   ├── agents.py
│   │   ├── memory.py
│   │   ├── router.py
│   │   ├── runs.py
│   │   ├── schemas.py
│   │   ├── tasks.py
│   │   └── tools.py
│   ├── deps/
│   ├── middleware/
│   ├── main.py
│   └── router.py
├── core/
├── db/
├── docs/
│   ├── ARCHITECTURE_REFACTOR_PLAN.md
│   ├── ARCHITECTURE_REFACTOR_RESULT.md
│   └── ARCHITECTURE_RULES.md
├── modules/
│   ├── ai/
│   ├── memory/
│   │   └── layer/
│   ├── observability/
│   ├── orchestration/
│   │   ├── execution/
│   │   ├── repository/
│   │   ├── services/
│   │   │   └── planned_runs.py
│   │   └── workspace/
│   │       ├── __init__.py
│   │       ├── service.py
│   │       └── storage.py
│   ├── projects/
│   ├── team/
│   └── workforce/
├── workers/
├── scripts/
├── tools/
├── tests/
└── alembic/
```

`backend/app` is absent.

## Remaining technical debt and intentionally unchanged issues

These issues were discovered but left unchanged to keep the migration safe and reviewable:

1. Atomically extract AgentProfile model/repository/service/router from `team` and orchestration into `modules/agents`.
2. Fold `modules/orchestration/providers.py` into an AI-owned gateway contract without losing persisted provider configuration, routing, fallback, accounting, or discovery behavior.
3. Replace domain/service `HTTPException` usage with domain exceptions, beginning with orchestration execution and approvals.
4. Move memory SQL queries out of the orchestration god repository.
5. Introduce a worker-dispatch port and remove domain-to-Celery reverse imports.
6. Break cycles among orchestration, projects, team, workforce, memory, AI, RAG, GitHub, core, DB, and observability.
7. Split oversized orchestration router/repository, memory service, GitHub service, workflow runtime, and team service mixin.
8. Remove or reconcile the overlapping unused memory-store protocol after caller verification.
9. Complete canonical AI error types so provider code no longer raises FastAPI exceptions.
10. Resolve the documented baseline tests and Ruff debt separately; these predate and are unrelated to `backend/app` removal.
