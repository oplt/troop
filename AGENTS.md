# Project rules

## Commands
- Use pnpm, not npm
- Frontend: `cd frontend && pnpm lint && pnpm test`
- Backend: `cd backend && uv sync` then run targeted tests only for changed areas

## Code standards
- Prefer TypeScript strict types
- Avoid adding new dependencies unless necessary
- Keep functions small and side effects explicit
- Backend logic stays in services, not controllers
- Do not couple UI components to data-fetching details

## Workflow
- For large changes, propose a short plan first
- For bug fixes, reproduce before patching
- Keep diffs focused and avoid unrelated refactors

