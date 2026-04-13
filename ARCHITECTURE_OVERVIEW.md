# Architecture Overview

## Current Stack

### Backend
- FastAPI application in [backend/api/main.py](/home/polat/Desktop/Projects/troop/backend/api/main.py)
- Async SQLAlchemy session factory in [backend/db/session.py](/home/polat/Desktop/Projects/troop/backend/db/session.py)
- Alembic migrations in `backend/alembic/versions`
- Domain modules under `backend/modules`
- Celery workers in `backend/workers`
- Redis for cache, auth token workflows, and Celery transport
- S3-compatible object storage abstraction for uploaded assets

### Frontend
- React 19 + Vite + TypeScript
- MUI-based shell and page primitives
- TanStack React Query for server state
- Route shell in [frontend/src/app/router.tsx](/home/polat/Desktop/Projects/troop/frontend/src/app/router.tsx)
- Authenticated layout in [frontend/src/components/layout/AppLayout.tsx](/home/polat/Desktop/Projects/troop/frontend/src/components/layout/AppLayout.tsx)

## Existing Product Areas
- Authentication and MFA
- User profile and notifications
- Simple projects and project tasks
- AI studio for prompt templates, retrieval docs, runs, reviews, and evaluations
- Platform metadata, feature flags, settings, and audit foundations

## Target Architecture For The Orchestration Platform

### Core Domains

#### Agent Registry
- Structured agent records with a markdown-backed source format.
- Versioned definitions so imports and manual edits remain auditable.
- Hierarchy metadata for manager, reviewer, and specialist relationships.

#### Project Workspace
- First-class projects own agents, tasks, brainstorms, repos, documents, and activity.
- Existing project pages are extended rather than replaced.

#### Orchestration Tasks
- Durable task lifecycle with dependencies, comments, artifacts, approvals, and GitHub linkage.
- Tasks can be created manually, imported from GitHub, or generated from brainstorm outcomes.

#### Execution Runs
- Every task execution creates a persisted run with status, provider/model usage, costs, latency, retries, and event logs.
- Runs are worker-driven and survive process restarts.

#### Brainstorms
- Multi-agent discussions with participant selection, round limits, stop conditions, and task promotion.

#### Provider Configurations
- Global, project, and agent-specific provider/model policies.
- Secrets never leave the backend and are masked in the UI.

#### GitHub Integration
- Repo connections, issue import, internal mapping, sync logs, and outbound comments with approval gates.

## Data Model Additions

### Agents
- `agent_profiles`
- `agent_profile_versions`
- `project_agent_memberships`

### Projects
- `orchestrator_projects`
- `project_repositories`
- `project_documents`

### Tasks
- `orchestrator_tasks`
- `task_dependencies`
- `task_comments`
- `task_artifacts`

### Runs
- `task_runs`
- `run_events`
- `approval_requests`

### Brainstorms
- `brainstorms`
- `brainstorm_participants`
- `brainstorm_messages`

### Integrations
- `provider_configs`
- `github_connections`
- `github_repositories`
- `github_issue_links`
- `github_sync_events`

## Execution Design

### Request Flow
1. User creates or imports a task.
2. Task is assigned to one or more agents through project hierarchy rules.
3. User starts a run from the UI.
4. API persists the run and queues Celery execution.
5. Worker resolves effective provider/model settings and assembles prompt context from project/task/docs/history.
6. Worker emits `run_events` as the orchestration progresses.
7. Frontend subscribes through SSE and updates run logs/live state.
8. Completion may require human approval before GitHub or external side effects.

### Orchestration Modes
- Single-agent: one agent executes the task directly.
- Manager-worker: manager plans or routes; specialist executes.
- Brainstorm: moderator drives multi-agent rounds to a summary/decision.
- Review: reviewer validates results and can approve or request changes.

### Durability
- Run state is stored in PostgreSQL.
- Worker retries use Celery retry semantics plus task run retry counters.
- SSE reads from persisted event history, not ephemeral memory.

## Security Model
- Existing authenticated cookie session remains unchanged.
- All orchestration routes require `get_current_user`.
- Ownership boundaries:
  - users see their own agents and project-scoped assignments
  - project membership controls task and brainstorm access
  - admin-only controls remain separate
- Approval gates are required before:
  - posting to GitHub
  - externally completing linked work
  - potentially costly reruns over policy thresholds
- Secrets:
  - stored server-side only
  - masked in API responses
  - never returned in plaintext after creation/update

## Real-Time and Observability
- SSE endpoint for run activity stream
- `run_events` timeline for backend truth
- `audit_logs` for user-driven sensitive actions
- provider health summaries and GitHub sync history surfaced in UI

## Frontend Structure

### Navigation Extensions
- Dashboard gains orchestration stats and active runs.
- Project detail becomes tabbed:
  - Overview
  - Tasks
  - Agents
  - Brainstorms
  - GitHub
  - Settings
  - Activity
- New pages:
  - Agent Library
  - Settings for providers and budgets
  - Activity and approvals

### UI Principles
- Preserve current MUI layout primitives and visual language.
- Keep board/list/detail interactions aligned with existing projects UX.
- Use focused forms and drawers/dialogs for editing where possible.

## Provider Abstraction
- Existing `backend/modules/ai/providers.py` remains the transport layer seed.
- New orchestration provider configs add:
  - endpoint aliasing
  - model defaults/fallbacks
  - timeout and token budgets
  - health checks
- OpenAI-compatible and Ollama-compatible endpoints use the same general adapter shape.

## GitHub Sync Design

### Inbound
- User creates a GitHub connection and chooses repositories.
- Sync job fetches issues and stores mirror metadata.
- Import creates or updates internal tasks and keeps a source link.

### Outbound
- Agents complete work in-app.
- Completion summary becomes a draft GitHub update.
- Human approves.
- Backend posts comment or close action and records sync event/audit trail.

## Main Tradeoffs
- The repo already has a simple `projects` domain; compatibility is preserved while richer orchestration entities are introduced beside it.
- SSE is less feature-rich than websockets but operationally simpler for this codebase.
- GitHub App installation flow is deferred in favor of robust token-based repo connectivity for the first version.
