# Troop

Troop is now extended into a production-minded AI agent orchestration platform on top of the existing FastAPI + React application.

## Current Architecture

- Backend: FastAPI, async SQLAlchemy, Alembic, Redis, Celery
- Frontend: React 19, Vite, TypeScript, React Query, MUI
- Auth: existing cookie-based JWT access/refresh flow is preserved
- Existing modules remain intact; orchestration is added as a native extension module

## New Platform Capabilities

- Agent registry with manual creation and markdown import
- Versioned agent specs with hierarchy, roles, tools, budgets, and memory policy
- Orchestration projects with assigned agents, durable tasks, runs, brainstorms, docs, and activity
- Task execution modes: single-agent, manager + worker, brainstorm, review
- Provider settings for OpenAI-compatible and Ollama-compatible endpoints
- GitHub connection, repo sync, issue import, task linking, approval-gated outbound comments
- Run logs, approvals, auditability, and SSE event streaming

## Key Docs

- [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)
- [ARCHITECTURE_OVERVIEW.md](./ARCHITECTURE_OVERVIEW.md)

## Backend Setup

1. Copy `backend/.env.example` to `backend/.env` and replace the placeholder secrets.
2. Install dependencies:

```bash
cd backend
uv sync
```

3. Start infrastructure:

```bash
docker compose -f infra/docker-compose.yml up -d
```

4. Run migrations:

```bash
cd backend
.venv/bin/alembic upgrade head
```

5. Start the API:

```bash
cd backend
.venv/bin/uvicorn backend.api.main:app --reload
```

6. Start the worker:

```bash
cd backend
.venv/bin/celery -A backend.workers.celery_app.celery_app worker -l info
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

## Orchestration Routes

- `/agents`
- `/agent-projects`
- `/agent-projects/:projectId`
- `/brainstorms`
- `/github-sync`
- `/orchestration-settings`
- `/activity`

## Agent Markdown Format

```md
---
name: Backend Engineer
role: specialist
version: 1
capabilities:
  - coding
tools:
  - github
tags:
  - api
budget:
  max_tokens_per_run: 50000
memory:
  scope: project
---

# Mission
Implement backend features safely.

# Rules
Be precise. Keep changes scoped. Explain tradeoffs briefly.

# Output Contract
Return a concise implementation summary.
```

Required sections:
- `# Mission`
- `# Rules`
- `# Output Contract`

## Provider Setup

- Provider records are stored in the app through `/orchestration/providers`
- Secrets are encrypted server-side and only masked hints are returned
- Supported provider types:
  - `openai`
  - `openai_compatible`
  - `ollama`
  - `local`

## GitHub Setup

1. Open `/github-sync`
2. Add a GitHub token-backed connection
3. Sync repositories
4. Import issues into an orchestration project
5. Run work internally
6. Approve outbound comment actions from `/activity`

## Task Execution Lifecycle

1. Create or import a task
2. Assign an agent or manager/worker chain
3. Start a run
4. Worker persists `run_events` and updates task state
5. Review or brainstorm flows can generate follow-up runs
6. Linked GitHub actions pause behind approval requests

## Verification

Frontend:

```bash
cd frontend
npm run lint
npm run test
npm run build
```

Backend smoke/unit:

```bash
PYTHONPATH=/path/to/troop .venv/bin/python -m unittest backend.tests.test_orchestration_unit
```

## Known Limitations

- GitHub integration currently uses token-based sync rather than GitHub App installation flow
- SSE run streaming is polling-backed, not websocket-backed
- The original `projects` module remains in place for compatibility; the new orchestration workspaces live beside it
- Provider and GitHub secrets are encrypted in-app, but external secret managers are not integrated yet
