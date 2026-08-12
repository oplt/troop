# Troop frontend

React 19 + TypeScript + Vite application for AI-assisted orchestration, projects, agents, memory, runs, and operational workspace workflows.

## Development

From the repository root:

```bash
pnpm install
cd frontend
pnpm dev
```

The frontend expects the backend API at `http://localhost:8000/api/v1` by default. Set `VITE_API_BASE` in `frontend/.env` when the API is hosted elsewhere.

## Verification

```bash
cd frontend
pnpm lint
pnpm exec tsc --noEmit
pnpm test
pnpm build
pnpm run baseline:build -- --output /tmp/frontend-baseline.json
```

The application uses Material UI as its design system, TanStack Query for server state, React Hook Form/Zod for validated forms, and React Flow for hierarchy editing. Route-level page imports are lazy-loaded in `src/app/router.tsx`.

## Structure

- `src/app/` — providers, routing, theme, and application shell concerns.
- `src/components/` — shared layout, UI primitives, and focused feature components.
- `src/features/` — feature-owned queries, state, parsers, and API façades.
- `src/pages/` — route composition and legacy feature views being migrated incrementally.
- `src/api/` — compatibility API clients and shared authentication/error handling.
