# Backend Architecture Rules

These rules govern the Troop backend modular monolith. They are dependency and ownership rules, not a requirement to create a folder for every concept.

## 1. Module ownership

Every behavior has one canonical owner.

| Responsibility | Canonical owner |
| --- | --- |
| HTTP composition, auth dependency resolution, request/response mapping, compatibility representations | `backend/api` and router modules |
| Process configuration, security primitives, cache/HTTP/storage clients, request context | `backend/core` |
| SQLAlchemy base, session lifecycle, database bootstrap | `backend/db` |
| Agent profiles, versions, prompts/model policy, tool/skill assignment lifecycle | currently `backend/modules/team`; target atomic extraction to `backend/modules/agents` |
| Tasks, runs, plans, steps, execution, checkpoints, retries, run events, scheduling intent | `backend/modules/orchestration` with project task ownership where already established |
| Project aggregate and task/artifact metadata | `backend/modules/projects` |
| Semantic and scoped memory | `backend/modules/memory` |
| LLM/provider invocation and accounting | `backend/modules/ai` |
| Runtime tool definitions, registration, grants, permissions, risk, approval policy | `backend/modules/workforce` |
| Runtime tool dispatch in an orchestration execution context | workforce `ToolExecutionService` and orchestration `OrchestrationToolbox` |
| Structured logs, metrics, traces, safe context | `backend/modules/observability` plus core bootstrap |
| Celery registration, queue mapping, task deserialization and service invocation | `backend/workers` |
| Repository/developer/maintenance commands | `backend/tools` and `backend/scripts` |

Compatibility code translates an external representation into a canonical Troop representation. It never becomes the canonical owner.

## 2. Dependency direction

Preferred direction:

```text
api/routers -> application/domain services -> ports/repositories -> infrastructure adapters
workers     -> application/domain services -> ports/repositories -> infrastructure adapters
```

Rules:

1. `backend/core` must not depend on business domain modules. Existing observability bootstrap coupling is migration debt and must not spread.
2. `backend/db` must not import API code or domain services.
3. Business/domain code must not import `backend/api`.
4. Only router/transport modules may import FastAPI request/dependency types.
5. Domain and application services should raise domain/application exceptions. Routers map them to HTTP responses.
6. Workers call the same application/execution services as HTTP callers. Workers do not reimplement business state machines.
7. Domain code should enqueue work through a dispatch port, not import concrete worker tasks. Existing direct imports are migration debt.
8. Cross-domain imports must target a public service, schema/value object, protocol, or repository contract with explicit ownership.
9. Avoid wildcard or broad `__init__.py` re-exports. Import the defining module when cycle risk exists.
10. No production module imports tests. No domain module imports a router.

## 3. Router responsibilities

Routers may:

- declare paths, methods, tags, status codes, and response schemas;
- validate transport input;
- resolve authentication, tenant context, and dependencies;
- call an application/domain service;
- translate known domain exceptions to HTTP errors;
- call pure presenters to construct responses.

Routers must not:

- implement plans, retries, execution loops, or state machines;
- query SQLAlchemy directly for business resources;
- commit or roll back business transactions;
- access workspace files directly;
- call provider SDKs or external services directly;
- implement memory retrieval or tool policy;
- encode approval decisions beyond transport mapping.

Prefer resource-focused routers. Split a router before unrelated resource families or business algorithms accumulate.

## 4. Service responsibilities

Application/domain services own use-case composition, authorization invariants, state transitions, transaction boundaries, and calls to ports.

- A service method should represent a meaningful use case.
- Do not introduce wrappers that only forward arguments and return values.
- Inject repositories, gateways, storage, clocks, or dispatchers where substitution improves tests or ownership.
- Session-scoped construction is acceptable while the monolith uses SQLAlchemy `AsyncSession` dependencies.
- Keep provider/framework types at adapters where practical.
- New service files should stay focused; split by cohesive capability before they become god objects.

## 5. Persistence boundaries

- SQLAlchemy ORM models belong to their owning domain.
- Repositories own query construction and persistence mechanics.
- Routers do not issue SQL statements.
- Services decide transaction boundaries; repositories normally flush rather than commit unless explicitly documented.
- Cross-domain persistence access must be through an owned repository/service contract, not a giant repository escape hatch.
- Database artifact rows store metadata, evidence, lineage, and optionally bounded content. Workspace/object storage stores file payloads.
- Database schema changes require an Alembic migration. Pure code movement must not create a migration.

## 6. Worker boundaries

- Celery files are transport adapters: task name, queue, retry/time-limit settings, context restoration, session lifecycle, and service invocation.
- Keep task names stable unless an explicit migration exists.
- Business status transitions happen in shared services, not only in worker bodies.
- Workers must propagate safe request/job context and idempotency information.
- Do not pass ORM objects through Celery; pass stable identifiers and reload under server-owned authorization/context.
- Domain code should depend on a job-dispatch protocol; concrete Celery imports are temporary debt.

## 7. Runtime tool rules

- `backend/tools` is never imported as an AI agent runtime tool registry.
- Runtime `ToolSpec`/definitions come from the workforce catalog/registry.
- Registration is extensible by provider type without a single execution dictionary becoming the policy engine.
- Every executable tool has input schema, risk level, permission decision, approval requirement, timeout, audit/trace context, and normalized output/error behavior.
- Tool authorization is server-owned. Client-supplied owner, project, agent, grant, or approval fields are not trusted.
- External effects use exact-effect approval where required.
- Tool execution must preserve workspace, tenant, network, and secret boundaries.
- Compatibility aliases may translate names and shapes but may not override canonical risk or approval policy.

## 8. Memory ownership

- `backend/modules/memory/layer/service.py::MemoryService` is the canonical high-level memory API.
- Runtime callers depend on `MemoryService` or the `MemoryProvider` interface, not SQL tables.
- Supported operations are add, get through the provider, search/list, update, delete, scoped filtering, and semantic retrieval/context construction.
- Scope and tenant filters are explicit. User, company, project, agent, task, and session identifiers must not be inferred from untrusted payloads when server context exists.
- Memory content passes privacy/redaction policy before persistence and is not logged by default.
- A second memory store abstraction may exist only for a distinct storage concern with active callers; unused or overlapping protocols are removed rather than multiplied.
- Memory persistence should ultimately be owned by a memory repository, not delegated through the orchestration god repository.

## 9. Workspace and artifact rules

- Orchestration depends on `WorkspaceStorage`, not a permanent local path implementation.
- `LocalWorkspaceStorage` is the current adapter; future object storage adapters must preserve the same policy contract.
- All paths are relative, normalized, and resolved beneath a server-owned run root.
- Path traversal, absolute paths, secret-like names, disallowed extensions, and oversized content are rejected.
- Blocking filesystem operations run outside the async event loop.
- A caller authorizes the run before constructing `RunWorkspaceService` operations.
- Stored file metadata is storage-neutral. Do not expose an internal absolute path as the only durable artifact identity.

## 10. Observability ownership

- `backend/modules/observability` is the canonical log/metric/trace API; `backend/core/logging.py` owns process bootstrap/redaction.
- Do not create subsystem-specific log files by writing directly from request/service code.
- Attach safe identifiers where available: request, correlation, trace/span, user, tenant/company, project, task, run, agent, tool, step, job, status, latency, tokens, and estimated cost.
- Never log credentials, access/refresh tokens, encryption keys, raw secrets, full private payloads, or sensitive prompts by default.
- Worker context must continue the originating request/trace when headers are available.

## 11. AI gateway rules

- `backend/modules/ai` is the target canonical owner of provider invocation, provider selection, model policy execution, retries/fallback, timeouts, token accounting, and cost accounting.
- Orchestration supplies intent, context, policy constraints, and desired response shape.
- Orchestration does not add new provider-specific HTTP/SDK integrations.
- Persisted orchestration provider configuration is passed to an AI gateway adapter; it does not justify a duplicate invocation stack.
- Errors crossing into HTTP are translated at transport; provider code should not expose FastAPI exceptions as its long-term domain contract.

## 12. Approvals and HITL

- Approval policy belongs to orchestration HITL and workforce action policy.
- Approval records capture actor, exact requested effect, scope, expiry, decision, and audit context.
- Routers submit/decide approvals through services; they do not execute the approved effect themselves.
- Plan approval is distinct from external tool-effect approval.
- Rechecks occur at decision and execution time where authorization can change.

## 13. Compatibility policy

- Compatibility transport lives under `backend/api/compat` unless it is a non-HTTP domain adapter with a clearly documented owner.
- Preserve public paths and shapes when practical.
- Translation direction is external/legacy representation to canonical Troop representation.
- Compatibility packages contain no SQLAlchemy models, provider SDK clients, storage implementations, execution state machines, or canonical policy tables.
- Compatibility aliases are tested and may be removed only through a documented API deprecation/migration.

## 14. Enforced checks

The test suite should enforce at least:

- no `backend/app` directory or `backend.app` imports;
- no `backend.modules.*` non-router module importing `backend.api.*`;
- FastAPI app and router registration import successfully;
- Celery application and registered task modules import successfully;
- Alembic metadata imports all model packages;
- workspace security policy remains covered;
- runtime tool approval flags come from the canonical catalog;
- memory scope filtering remains covered.

Architecture exceptions must be explicit in this document, narrow, and accompanied by a removal plan. Hidden cycles through re-exports are not exceptions.
