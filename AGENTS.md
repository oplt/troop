# Repository Guidelines

## Project Structure & Module Organization
This repo is split by runtime. `backend/` contains the FastAPI app, Celery workers, Alembic migrations, and tests. Key areas are `backend/api/`, `backend/modules/`, `backend/core/`, and `backend/alembic/versions/`. `frontend/` contains the React + Vite client with `src/pages/`, `src/components/`, `src/features/`, `src/api/`, and `src/test/`. Infrastructure lives in `infra/`; architecture notes live in `docs/adr/`.

## Build, Test, and Development Commands
Use the commands from each app directory.

- `cd frontend && npm run dev`: start the Vite dev server.
- `cd frontend && npm run build`: type-check and build the production bundle.
- `cd frontend && npm run lint`: run ESLint on TS/TSX files.
- `cd frontend && npm run test` or `npm run test:coverage`: run Vitest once, with optional coverage output.
- `cd backend && uv sync`: install backend dependencies into `.venv`.
- `cd backend && .venv/bin/uvicorn backend.api.main:app --reload`: run the API locally.
- `cd backend && .venv/bin/alembic upgrade head`: apply database migrations.
- `docker compose -f infra/docker-compose.yml up -d`: start PostgreSQL, Redis, and MinIO.

## Coding Style & Naming Conventions
Frontend code uses TypeScript with ESLint. Use PascalCase for React components (`PageHeader.tsx`), camelCase for hooks and utilities (`useAuth.ts`), and keep API modules grouped by domain. Backend Python follows Ruff with a 100-character line length. Use snake_case for Python modules and keep routers, schemas, services, and repositories aligned inside each module directory.

## Testing Guidelines
Frontend tests use Vitest with a `jsdom` environment and shared setup in `frontend/src/test/setup.ts`. Place new tests beside the feature as `*.test.ts` or `*.test.tsx`. Backend coverage is currently light; add tests under `backend/tests/` for new API, service, or migration behavior. Run affected frontend tests before opening a PR and note any backend checks performed manually if automation is missing.

## Commit & Pull Request Guidelines
Recent commits are short, lowercase summaries like `theme changed` and `calendar periods`. Keep commits focused and imperative, but more specific when possible, for example `add project detail route`. PRs should include a brief summary, linked issue if applicable, testing notes, and screenshots for visible frontend changes.

## Security & Configuration Tips
Auth and local infra are first-class parts of this repo. Keep secrets in `.env` files, never commit credentials, prefer secure `httpOnly` cookies over browser token storage, and review auth, authorization, validation, and CORS impacts for any API or session-related change.

# Repo rules

## Commands
- Backend checks: pnpm test && pnpm lint
- Security checks: pnpm audit --audit-level=high
- API schema validation lives in src/schemas
- Auth middleware lives in src/middleware/auth.ts
- Production env validation is in src/config/env.ts

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **generic_app** (1456 symbols, 5390 relationships, 117 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/generic_app/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/generic_app/context` | Codebase overview, check index freshness |
| `gitnexus://repo/generic_app/clusters` | All functional areas |
| `gitnexus://repo/generic_app/processes` | All execution flows |
| `gitnexus://repo/generic_app/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
