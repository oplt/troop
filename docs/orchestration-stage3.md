# Orchestration Stage 3

Stage 3 closes operator and portfolio-control gaps left after P0-P2.

## Acceptance checker

- Acceptance checks run before `approved` and `completed`.
- Evidence includes acceptance criteria coverage, artifact presence, dependency completion, reviewer verdict, and GitHub side effects.
- Project task detail remains source of truth for pass/fail evidence and blocker messages.

## Explainability payloads

- Routing explainability stores:
  - `agent_selection_reason`
  - `model_selection_reason`
  - `routing_inputs`
  - `routing_policy_snapshot`
- Task detail, run inspector, and hierarchy views consume same payload contract.

## GitHub sync console and replay

- Sync Console is operator entry point for:
  - webhook event drilldown
  - retry/replay actions
  - replay history
  - failure inspection
  - imported issue and PR sync state
- Replay flow keeps prior event metadata and queues safe reprocessing rather than mutating completed records in place.

## Repo indexing lifecycle

- Repo indexing supports:
  - full index
  - incremental reindex
  - auto scheduling metadata
  - file/error reporting
- Portfolio policy now defines default repo indexing cadence:
  - `hourly`
  - `daily`
  - `weekly`
  - `manual`

## Portfolio controls

- Portfolio control plane now includes:
  - operator dashboard
  - queue health
  - webhook lag
  - replay backlog
  - stuck run tracking
  - per-service health cards
  - execution policy defaults
  - project-level override visibility
- Portfolio execution defaults apply to inheriting projects immediately.
- Project overrides remain pinned through `settings.portfolio_policy_overrides`.

## Durable workflow migration

- Durable workflow state remains checkpoint-first inside `task_runs.checkpoint_json`.
- Migration ADR is `docs/adr/0004-durable-workflow-migration.md`.
- Operator dashboard surfaces stuck durable runs so migration can be observed during coexistence with Celery.

## Tests

Targeted backend coverage exists for:

- acceptance checker behavior
- routing explainability extraction
- replay metadata propagation
- portfolio execution policy inheritance and override tracking
- operator dashboard aggregation
