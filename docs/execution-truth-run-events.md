# Execution truth: `run_events` contract

Postgres table `run_events` is the **durable append-only log** for orchestration alongside `task_runs` and `task_runs.checkpoint_json`.

## What to log

- Run queue/start/recovery/signal application/completion/failure/cancel.
- Task status changes when a `TaskRun` is in context, or else on the **latest** run for the task (manual updates, approvals without an active run pointer).

## What not to duplicate

- High-volume token stream lines may stay in provider logs; keep `run_events` bounded (messages truncated in service where needed).

## Relation to checkpoints

- **Checkpoint** = machine-readable workflow state for resume/signal/query.
- **Run event** = human-readable + structured audit trail for inspectors, SLA, and episodic indexing.

Both are required; neither replaces the other.
