# Workspace RBAC migration plan (RBAC-001A → RBAC-001C)

This document describes the incremental workspace rollout. **Legacy `owner_id` /
`user_id` columns remain authoritative** until RBAC-001C enforces `workspace_id`.

## Phase A — RBAC-001A (this change)

- Add `workspaces` and `workspace_memberships` tables.
- Backfill one **default workspace per user** with an `owner` membership.
- Publish tenant table inventory (`tenant_inventory.py`) before any `workspace_id` columns.
- Validation: `backend/scripts/rbac/validate_workspace_backfill.sql`.

## Phase B — RBAC-001B (next)

- Introduce `WorkspaceContext` on authenticated requests.
- Route authorization through a canonical service; keep owner checks at commit boundaries.

## Phase C — RBAC-001C (FK rollout)

1. Migration `i5c6d7e8f9a0` adds nullable `workspace_id` to every `top_level` table in `tenant_inventory.py` (except `workspaces`).
2. Backfill via `workspace_fk_migration.direct_backfill_sql()` from each row's `owner_id` / `user_id` default workspace.
3. Zero-null verification runs in-migration before `NOT NULL` is applied.
4. Composite indexes on high-traffic list queries (see `WORKSPACE_COMPOSITE_INDEXES`).
5. Validation: `backend/scripts/rbac/validate_workspace_id_backfill.sql`.
6. **Do not drop** legacy `owner_id` columns in this tranche.

Child-phase tables (`workflow_runs`, `departments`, `project_analyses`, …) inherit workspace scope through parent FKs in a follow-up tranche.

## Roles

| Role | Intended use |
|------|----------------|
| `owner` | Full control, billing, destructive settings |
| `admin` | Membership + policy management |
| `builder` | Agents, workflows, integrations, templates |
| `operator` | Run/monitor automations, tasks |
| `approver` | Approval queue decisions |
| `viewer` | Read-only dashboards and traces |

## Rollback

- Alembic downgrade `h4b5c6d7e8f0` drops `workspace_memberships` then `workspaces`.
- No data loss to legacy ownership columns (unchanged).

## Inventory maintenance

Regenerate a machine-readable snapshot:

```bash
cd backend && python -m backend.scripts.rbac.export_tenant_inventory
```

Source of truth: `backend/modules/identity_access/tenant_inventory.py`.
