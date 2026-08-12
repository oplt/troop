"""Legacy `projects` / `project_tasks` tables.

`OrchestratorProject` and `OrchestratorTask` (see `orchestration_models.py`) are the
canonical project/task entities. The legacy tables remain for migration compatibility
until all callers are migrated and CI is green on table drops.

- HTTP router: `backend/modules/projects/router.py` (intentionally unmounted)
- Service warnings: `ProjectsService` logs on each legacy method call
