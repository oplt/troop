## Summary
<!-- What changed and why (1–3 bullets). -->

-

## Test plan
- [ ] Manual smoke of touched flows
- [ ] `pnpm test` / CI green

## Design QA
- [ ] Uses `PageShell` / `PageHeader` (or documented exception)
- [ ] Nav entry (if any) has a unique icon + clear label
- [ ] Empty, loading, and error states handled (EmptyState / SectionError / skeleton)
- [ ] Dark mode smoke: no missing borders, unreadable secondary buttons, or clipped text
- [ ] Destructive actions use `ConfirmDestructiveDialog` (not bare `window.confirm`) when touching delete/disconnect
- [ ] Analytics windows use `DateRangeControl` when date-scoped
- [ ] No new jargon without first-use helper (DAG / semantic memory / module pack)
- [ ] Keyboard: primary actions reachable; skip link still lands on `#main-content`
- [ ] If shell IA / nav labels / routes changed: update `frontend/src/test/visualBaselines.ts`
