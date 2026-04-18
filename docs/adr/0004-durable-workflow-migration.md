# ADR 0004: Durable Workflow Runtime And Migration Plan

## Status

Accepted

## Context

Troop already persists orchestration execution truth in Postgres through `task_runs.checkpoint_json`, `run_events`, task state, approvals, and GitHub sync records. Celery + Redis provide the durable queue for execution starts, retries, and replay requests.

What was missing before this ADR:

- no explicit workflow id / execution handle surfaced to operators
- no first-class signal/query model for long-running executions
- no formal migration story from checkpoint-first Celery runtime to an external durable workflow backend
- no product-facing explanation of which workflows move first and how coexistence works

## Decision

Troop will use a **checkpoint-first durable workflow contract** now, with a clean migration seam for a future external workflow backend such as Temporal.

Current implementation:

- durable workflow state lives in `TaskRun.checkpoint_json["durable_workflow_v1"]`
- every run gets a `workflow_id` and `execution_handle`
- signals are queued in `signal_queue` and moved to `signal_history` when workers consume them
- queries read `query_snapshot` from checkpoint state
- Celery remains the process-level durable queue backend
- APIs stay stable while runtime internals evolve

## Why This Approach

This gives immediate operator value without a large infrastructure migration:

- survives retries, worker crashes, and resumes with current stack
- exposes workflow controls in the product now
- keeps migration incremental instead of blocking roadmap work on Temporal adoption
- avoids a big-bang rewrite of GitHub sync, brainstorms, and manager-worker runs

## Alternatives Considered

### Keep plain Celery with no workflow contract

Rejected.

- replay/resume semantics stay implicit
- operators cannot signal/query executions cleanly
- future migration stays expensive because API and checkpoint shapes are not stabilized

### Immediate Temporal migration

Rejected for now.

- operationally heavier
- forces infrastructure and workflow rewrite before product value lands
- increases delivery risk across GitHub sync, approvals, and long-running orchestration

## Workflow Contract

Each run exposes:

- `workflow_id`
- `execution_handle`
- `current_step_id`
- `last_completed_step_id`
- `resume_count`
- `recovery_count`
- `signal_queue`
- `signal_history`
- `query_snapshot`
- migration metadata

Supported signals now:

- `pause`
- `resume`
- `retry_step`
- `update_objective`
- `add_note`

Query surface now:

- current workflow status
- current/last-completed step
- resume + recovery counters
- pending/applied signals
- handle metadata
- migration posture

## Migration Plan

### Phase 1: checkpoint-first coexistence

Already implemented.

- Celery owns start/resume/replay dispatch
- Postgres checkpoint owns workflow truth
- signals and queries are persisted in checkpoint state

### Phase 2: external backend shadow mode

Next durable backend can subscribe to the same contract:

- map `workflow_id` to external workflow id
- mirror `execution_handle.thread_id` into backend execution id
- publish query results back into `query_snapshot`
- mirror incoming signals into backend signal APIs
- continue writing final execution truth to Postgres

### Phase 3: selective workflow migration

Move highest-value long-running workflows first:

1. GitHub sync and webhook replay pipelines
2. manager-worker multi-branch runs
3. brainstorm sessions with multiple rounds
4. approval-gated review workflows

### Phase 4: default external durable backend

When external backend is proven:

- keep API responses unchanged
- set backend marker from `celery_checkpointed` to backend-specific value
- retain checkpoint JSON as audit mirror and fallback restore source

## Checkpoint Migration Strategy

Checkpoint schema is versioned.

- old runs remain readable
- `ensure_workflow_state` upgrades missing fields in place
- migration metadata records source/current versions
- future backend migration must preserve `workflow_id`, `execution_handle`, and trace step ids

This means replay, resume, and inspector pages can continue to work across runtime transitions.

## Consequences

Positive:

- product gets durable workflow controls now
- migration risk reduced
- run inspector and control plane can reason about workflows consistently

Tradeoffs:

- still not equivalent to full Temporal history replay
- signal application is worker-consumed, not instant remote execution
- query model is checkpoint-based, not live engine-native

## Follow-up

- add external backend adapter implementing same contract
- shadow-write query snapshots from backend-native state
- add operator dashboards for lag, stuck workflows, replay backlog, and queue health
