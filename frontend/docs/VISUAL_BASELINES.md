# Frontend visual baselines

Landmark / IA contracts live in `frontend/src/test/visualBaselines.ts` and are asserted by:

- `AppLayout.accessibility.test.tsx`
- `DashboardPage.a11y.test.tsx`
- `OrchestrationProjectDetailPage.a11y.test.tsx`

## Covered surfaces

| Route | Notes |
|-------|--------|
| Shell | Skip link → `#main-content`, drawer 288/96, toolbar 64/72 |
| `/` | Auth brand + sign-in |
| `/dashboard` | Do next + Projects |
| Project detail | Overview tab workspace |
| `/projects`, `/approvals`, `/portfolio`, `/hierarchy`, `/analytics/cost` | Declared in baselines list |

## Refresh

When shell IA changes intentionally:

1. Update `visualBaselines.ts`
2. Run `pnpm test` in `frontend/`
3. Tick the visualBaselines item in the PR Design QA checklist

Full pixel screenshots are optional (Playwright not required in CI). Landmark contracts catch the high-cost IA regressions without adding browser binaries.
