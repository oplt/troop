# Backend Architecture Refactor Plan

Status: approved implementation plan, based on repository inspection on 2026-08-14.

## 1. Current architecture

Troop is a modular monolith. Its production entry points are:

- HTTP: `backend.api.main:app`
- Celery: `backend.workers.celery_app:celery_app`
- migrations: `backend/alembic/env.py` and `backend.db.base.Base.metadata`

Most business capabilities live under `backend/modules`. `backend/api` composes HTTP routers and middleware, `backend/core` contains process-wide configuration and infrastructure helpers, `backend/db` owns session/bootstrap code, and `backend/workers` owns Celery transport adapters.

`backend/app` is the exception. It contains only a DeerFlow-inspired agent compatibility API and combines HTTP transport, orchestration use cases, SQL access, memory adaptation, filesystem storage, a static tool catalog, and a second logging sink. It has no independent application-bootstrap purpose.

### Responsibility map

| Capability | Current canonical implementation | Current ambiguity |
| --- | --- | --- |
| Agent definitions | `modules/team/models.py`, `modules/team/service.py`, `modules/orchestration/repository/agents.py` | `app/agents` suggests false ownership; agent lifecycle is split between team and orchestration |
| Task/run orchestration | `modules/orchestration`, project task mixins in `modules/projects` | `app/agents/application.py` implements a separate planned-placeholder lifecycle |
| AI/model gateway | `modules/ai/providers` plus a second provider stack in `modules/orchestration/providers.py` | provider invocation, errors, retry, discovery, accounting, and pricing are duplicated |
| Memory | `modules/memory/layer` | `app/agents/memory/base.py` is an N+1 SQL adapter over the canonical service; repository depends on the orchestration god repository |
| Runtime tools | `modules/workforce/services/tool_registry.py`, `tool_execution_service.py`, and `modules/orchestration/tools.py` | `app/agents/tools/registry.py` duplicates five static tool definitions; `backend/tools` is repository tooling, not runtime tools |
| Workspace/artifacts | run artifacts in project/orchestration models and repositories; repo workspaces in orchestration | `app/agents/workspace.py` provides a separate local-only run filesystem and performs blocking I/O in async functions |
| Observability | `modules/observability`, `core/logging.py`, request/job context | `app/agents/logging.py` writes unredacted JSONL through synchronous file I/O |
| Projects | `modules/projects` | project mixins are composed into the orchestration facade, creating reciprocal imports |
| Workforce/team | `modules/workforce` and `modules/team` | AgentProfile is in team while runtime tools are in workforce; both depend heavily on orchestration |
| Approvals/HITL | `modules/orchestration/execution/hitl`, orchestration approval services, workforce action policy | the compatibility plan approval bypasses the canonical approval-request model |
| External integrations | `modules/github`, workforce connector providers, `core/external_http.py` | domain modules enqueue concrete workers directly |
| Workers | `backend/workers` | workers call services, but modules also import workers, creating bidirectional dependencies |

## 2. Problems identified

### `backend/app` has no legitimate architectural role

Its only consumer is `backend/api/router.py`; its public endpoint paths are also consumed by the frontend. It is therefore an HTTP compatibility surface, not an application root or bounded domain. Keeping it as a peer of `api`, `core`, and `modules` creates a second application namespace and hides ownership.

### Duplicate and misplaced responsibilities

1. `app/agents/logging.py` duplicates the canonical logging/observability stack and bypasses its redaction and context handling.
2. `app/agents/tools/registry.py` duplicates runtime tool metadata already owned by the workforce registry and action-policy system.
3. `app/agents/memory/base.py` wraps `MemoryService`, then loads each result again through SQL. That causes N+1 reads and presents ORM rows even though `MemoryRecord` is the canonical interface.
4. `app/agents/workspace.py` combines authorization lookup, path policy, local persistence, and API exceptions.
5. `app/agents/router.py` combines five resource families and directly queries run events/artifacts.
6. `app/agents/application.py` owns transport exceptions, database transactions, run state changes, event creation, filesystem writes, artifact metadata, and logging in one class.
7. `modules/orchestration/providers.py` independently implements provider HTTP calls, discovery, accounting, and errors despite `modules/ai/providers` being the AI gateway.
8. `modules/memory/layer/repository.py` imports the large orchestration repository instead of owning memory persistence.
9. `backend/tools` contains developer/maintenance commands. It must remain separate from AI runtime tools.

### Dependency and circularity risks

A static import scan found one strongly connected component spanning nearly every backend layer. Important contributors are:

- `core -> modules.observability` while observability also imports `core` and `db`;
- orchestration, projects, team, workforce, memory, AI, GitHub, and RAG importing each other;
- domain modules importing concrete Celery modules while Celery imports those domains;
- domain service code importing FastAPI `HTTPException`;
- domain routers importing `backend.api.deps`.

The existing module routers are transport modules even though they reside under their domains. Non-router module code does not currently import `backend.api`, which is a useful enforceable boundary.

### Oversized compatibility facades

Several existing files are already far beyond a maintainable module size, including orchestration routing/repository code, memory service code, GitHub service code, workflow runtime code, and the team service mixin. This refactor must not grow those files. Splitting all of them at once would be a separate high-risk program.

### Performance findings

- Workspace `mkdir`, recursive listing, `stat`, and file writes block the event loop.
- Agent-facing memory list/search performs one extra SQL lookup per result.
- The memory repository routes through the complete orchestration repository.
- Company memory filtering uses the authenticated user ID where the company ID should be used.
- Orchestration and AI maintain separate provider paths, increasing duplicate retries, serialization, and accounting risk.
- Several service paths perform repeated fetch/commit sequences. These need focused profiling before modification.

Only the clear workspace, memory N+1, and company-scope defects are in the safe implementation scope. Other performance findings remain documented debt.

## 3. Dependency graph

### Current critical paths

```text
FastAPI
  -> backend.api.router
     -> backend.app.agents.router
        -> backend.api.deps                 (transport loop)
        -> app AgentRunApplicationService
           -> orchestration facade/repository
           -> local filesystem
           -> TaskArtifact ORM
           -> private JSONL logger
        -> memory SqlMemoryStore
           -> canonical MemoryService
           -> orchestration repository

Celery
  -> backend.workers.orchestration
     -> orchestration / AI / workforce services
        -> backend.workers.*                (reverse edge)

Orchestration model invocation
  -> modules.orchestration.providers        (provider SDK/HTTP/accounting)

AI Studio and memory model invocation
  -> modules.ai.providers                   (second provider stack)
```

### Intended dependency direction

```text
HTTP transport (backend.api, domain router modules)
  -> application/domain services
     -> repository and runtime interfaces
        -> SQLAlchemy / Celery dispatch port / AI gateway / tool providers / storage adapter

Celery task transport
  -> the same application/execution services used by HTTP

Compatibility HTTP representation
  -> canonical Troop schemas/services
```

No business module should depend on `backend.api`. No core domain behavior should live in compatibility code.

## 4. Proposed architecture

### Compatibility HTTP ownership

The existing `/api/v1/agents`, `/tools`, `/tasks`, `/runs`, and `/memory` paths remain stable, but their transport adapters move to `backend/api/compat`. The compatibility package translates legacy request/response shapes to canonical Troop services. It does not own models, repositories, logging, storage, memory, tool execution, or orchestration state machines.

### Agent domain decision

Agent definitions have an independent lifecycle: profile configuration, prompts, model policy, allowed tools, skills, versions, templates, activation, inheritance, and linting. Semantically, they warrant bounded-domain ownership under a future `backend/modules/agents` package, separate from run orchestration.

The current implementation, however, entangles `AgentProfile` with `TeamServiceMixin`, project membership, workforce skills, and orchestration repositories. Moving only the model would make ownership worse; moving the entire graph in this refactor would be a dangerous big bang. Therefore:

- this change removes the false `backend/app/agents` owner;
- existing agent behavior remains canonically implemented by the current team service and orchestration facade;
- compatibility HTTP code calls that canonical behavior;
- extraction into `modules/agents` is an explicit follow-up migration, performed atomically with its model, repository, service, router, and imports.

No second Agent model or partial re-export package will be introduced.

### Orchestration application boundary

The planned-placeholder run contract remains for API compatibility, but moves to `modules/orchestration/services/planned_runs.py`. The service owns its transaction and lifecycle. It uses repository methods, the workspace boundary, canonical artifact metadata, and canonical observability. Framework-neutral exceptions replace new FastAPI exceptions at this boundary.

Run event and artifact reads move out of routers and behind orchestration service methods. The existing `OrchestrationApplicationService` compatibility wrapper is removed if it has no remaining callers; routers use the specific existing services/facade until narrower service extraction is justified.

### Memory

`modules/memory/layer/service.py::MemoryService` remains the one canonical memory interface for add, search/list, update, delete, scoping, and semantic retrieval. Compatibility transport maps scope input into `MemoryFilters` and presents `MemoryRecord` directly. `SqlMemoryStore` is removed because it adds no useful runtime abstraction and causes N+1 queries.

### Runtime tools

`modules/workforce/services/tool_registry.py` remains the canonical registry/policy boundary. `ToolExecutionService` plus `OrchestrationToolbox` remain the execution path. Compatibility tool names are translated in `api/compat/tools.py` to canonical catalog entries. These aliases are presentation adapters only and cannot execute tools or define policy.

`backend/tools` remains repository/operations tooling.

### Workspace and artifacts

Create a small justified orchestration workspace package:

- `WorkspaceStorage`: storage protocol for write/list operations;
- `LocalWorkspaceStorage`: local filesystem implementation with existing path, extension, secret-name, and size checks; blocking calls use `asyncio.to_thread`;
- `RunWorkspaceService`: derives the run-scoped storage key from an already-authorized run and returns storage-neutral file metadata.

Database `TaskArtifact` rows remain metadata/evidence records. Local workspace files remain payload storage. S3 is not implemented.

### Observability

Remove the agent JSONL logger. Planned-run and compatibility events use `modules.observability.logging.log_event`, which includes safe request/job context. Explicit fields include user, company/tenant, project, task, run, agent, tool, step, latency, tokens, cost, status, and error where available. Prompts, credentials, tokens, secrets, and private payloads are not logged by default.

### AI provider boundary

`modules/ai` is the intended canonical LLM gateway owner: invocation, provider selection, retry/fallback policy, timeout, token/cost accounting, and provider SDK/HTTP integration. `modules/orchestration` should express routing intent and call that gateway.

The existing orchestration provider stack is heavily coupled to persisted `ProviderConfig` and routing behavior. It will be documented, tested, and migrated in a separate focused phase rather than rewritten alongside the compatibility API. No third provider abstraction will be introduced here.

### HITL and workers

Canonical external-effect approval remains in orchestration HITL and workforce action policy. The legacy `/approve-plan` endpoint retains its deterministic-placeholder contract but is explicitly named and isolated; it must not be reused as generic tool approval.

Celery task names and registration remain stable. The target is worker adapters calling shared execution services through a dispatch port; direct module-to-worker imports are follow-up debt because changing queue dispatch across all domains is broader than this safe slice.

## 5. File-by-file migration table

| Current file | Destination/action | Reason |
| --- | --- | --- |
| `app/agents/application.py` | `modules/orchestration/services/planned_runs.py` | planned-run lifecycle belongs to orchestration; remove FastAPI and private logging |
| `app/agents/logging.py` | delete; use `modules/observability/logging.py` | one logging/trace stack |
| `app/agents/router.py` | split into `api/compat/{agents,tasks,runs,memory,tools}.py` | explicit compatibility transport; small routers |
| `app/agents/workspace.py` | `modules/orchestration/workspace/{storage,service}.py` | storage boundary and non-blocking local adapter |
| `app/agents/memory/base.py` | delete; call canonical `MemoryService` | remove adapter and N+1 SQL reads |
| `app/agents/tools/registry.py` | delete; compatibility translation in `api/compat/tools.py` backed by workforce catalog | remove duplicate registry/policy |
| `app/**/__init__.py` | delete | remove second application namespace |
| `modules/orchestration/services/application.py` | delete if unused after migration | zero-value compatibility wrapper with repository escape hatch |
| `api/router.py` | include one `api.compat.router` | central API composition remains stable |
| `pyproject.toml` | remove `app*` package discovery and validate editable install | no stale package |
| `.github/workflows/quality.yml` | remove `app` Ruff targets | CI follows new production tree |
| `tests/test_deerflow_adapters.py` | point to compatibility translator and workspace storage policy | preserve tool approval and path security coverage |
| `tests/test_phase6_modularization.py` | point to split compatibility transport | preserve public presenter boundary check |
| new architecture test | enforce no `backend.app`; prohibit non-router modules importing `backend.api` | prevent regression |

## 6. Import changes

Planned production changes:

```text
backend.api.router
  backend.app.agents.router
  -> backend.api.compat.router

backend.api.compat.agents/tasks/runs
  -> existing orchestration/project schemas, presenters, and services

backend.api.compat.memory
  -> backend.modules.memory.layer.service.MemoryService
  -> backend.modules.memory.layer.schemas.MemoryFilters/MemoryRecord

backend.api.compat.tools
  -> backend.modules.workforce.constants.NATIVE_TOOL_CATALOG

backend.modules.orchestration.services.planned_runs
  -> orchestration repository/workflow helpers
  -> orchestration.workspace.RunWorkspaceService
  -> modules.observability.log_event
```

There will be no production import of `backend.app`. Compatibility modules will not be re-exported through `modules` or `core`.

## 7. Compatibility risks

| Risk | Mitigation |
| --- | --- |
| Frontend depends on `/tools`, `/tasks/{id}/runs`, `/runs/*` | preserve exact paths, verbs, response models, and placeholder semantics |
| Tool aliases are legacy names | explicit legacy-to-canonical mapping; test risk/approval flags |
| Workspace path behavior changes | preserve allowed extensions, 2 MiB limit, denied names, collision suffix, and traversal checks |
| Memory responses switch from ORM to `MemoryRecord` | compatibility presenter preserves fields and derives task scope from metadata |
| Company/task memory filtering was defective | add focused tests; fix only canonical filter mapping |
| Planned run service changes exception type | compatibility router translates domain exceptions to current HTTP statuses |
| Package discovery currently relies on unusual `package-dir` mapping and `PYTHONPATH=.` | validate editable install and imports; avoid unrelated package-layout rewrite |
| Dirty worktree contains unrelated backend changes | patch only scoped files and preserve existing modifications |

## 8. Migration phases

1. Record current architecture, rules, migration table, risks, and test plan.
2. Add workspace storage boundary and compatibility tool translation; replace duplicate logging and memory adapters.
3. Move planned-run lifecycle into orchestration service and add repository/service query methods needed by transport.
4. Split compatibility routers and preserve public paths.
5. remove all `backend/app` files and stale imports.
6. Clean package/CI configuration and update tests.
7. Run Ruff, formatting checks, unit tests, architecture/security scripts, FastAPI import/router smoke, Celery import/registration smoke, Alembic model/metadata smoke, and stale-import searches.
8. Write `ARCHITECTURE_REFACTOR_RESULT.md` with exact results and deferred debt.

Each phase is independently import/testable. No old and new core implementation will remain active together.

## 9. Testing strategy

### Focused unit tests

- legacy tool aliases derive risk and approval from canonical catalog;
- workspace traversal, absolute paths, secret filenames, extensions, size limit, collision handling, and listing;
- memory company/project/agent/task filter mapping and direct `MemoryRecord` presentation;
- planned run creation, plan approval, event order, artifact metadata, and transaction behavior;
- compatibility router registration and public presenters.

### Architecture checks

- `backend/app` does not exist;
- repository contains no `backend.app` imports;
- production non-router files under `backend/modules` do not import `backend.api`;
- compatibility API code does not define SQLAlchemy models or provider/tool execution logic.

### Existing regression suites

- unit and architecture tests;
- router/auth tests;
- memory and orchestration tests;
- workforce/tool/action-policy tests;
- workspace authorization/security tests;
- Celery registration/concurrency tests;
- migration integrity/model import tests.

### Smoke validation

```text
ruff check
ruff format --check
pytest
python -c "from backend.api.main import app; ..."
python -c "from backend.workers.celery_app import celery_app; ..."
Alembic config/env metadata import
repository searches for backend.app and moved imports
```

Integration tests requiring PostgreSQL/Redis are reported separately if those services are unavailable.

## 10. Final intended directory tree

Only relevant additions/changed areas are shown.

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
├── modules/
│   ├── ai/                         # canonical AI gateway target
│   ├── memory/                     # canonical memory subsystem
│   ├── observability/              # canonical logging/tracing/metrics
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
│   ├── team/                       # current AgentProfile owner; extraction debt
│   └── workforce/                  # canonical runtime tool registry/policy
├── workers/
├── scripts/                        # repository/runtime administration scripts
├── tools/                          # developer/maintenance validation tools
├── tests/
└── alembic/
```

`backend/app` is absent. A future atomic migration may add `modules/agents`; this refactor will not create an empty or misleading shell.
