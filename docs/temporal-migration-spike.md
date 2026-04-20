# Temporal migration spike (deferred)

ADR `0004-durable-workflow-migration.md` keeps Celery+Postgres until Phase 2. If/when Temporal is introduced:

## Mapping sketch

| Troop today | Temporal target |
|-------------|-----------------|
| `TaskRun.id` | Workflow id or deterministic idempotency key |
| `TaskRun.checkpoint_json["durable_workflow_v1"]` | Workflow history + search attributes mirror |
| `signal_queue` / `signal_history` | Signals + workflow updates |
| `run_events` | Continue as audit mirror (export workflow history snippets or dual-write) |
| Celery `execute_run` task | Worker poller or Temporal activity host |

## Spike order

1. One read-only workflow replaying Troop checkpoint JSON.
2. Dual-write `run_events` from Temporal history deltas for one run mode.
3. Cut over enqueue for that mode only.

No implementation in this repo until Phase 2 is scheduled.
