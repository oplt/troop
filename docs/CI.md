# Continuous integration and branch protection

## Quality workflow

The [Quality](../.github/workflows/quality.yml) workflow runs on every pull request and on pushes to `main`.

| Job | Purpose |
| --- | --- |
| `backend` | Ruff lint/format, Alembic migration smoke, backend unit/integration tests |
| `frontend` | Typecheck, ESLint, Vitest, production build; blocks `@ts-nocheck` in project detail/hierarchy pages |
| `security-audit` | `pip-audit` on backend dependencies; `pnpm audit --prod --audit-level critical` on frontend runtime deps |
| `container-smoke` | Validates `infra/docker-compose.yml`, starts Postgres + Redis, waits for health |

### Local parity

```bash
# Backend (from repo root)
cd backend
.venv/bin/ruff check --ignore E501 core api modules workers db app
.venv/bin/ruff format --check core api modules workers db app
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ../backend/.venv/bin/python -m pytest backend/tests -m "not integration" -q

# Frontend
cd frontend
pnpm exec tsc --noEmit -p tsconfig.app.json
pnpm lint
pnpm test
pnpm build

# Security audits
python -m pip install pip-audit
pip-audit  # after: pip install -e "./backend[dev]"
pnpm audit --prod --audit-level critical

# Container smoke
docker compose -f infra/docker-compose.yml --env-file infra/.env.ci config --quiet
docker compose -f infra/docker-compose.yml --env-file infra/.env.ci up -d postgres redis
docker compose -f infra/docker-compose.yml --env-file infra/.env.ci exec -T postgres pg_isready -U ci -d app
docker compose -f infra/docker-compose.yml --env-file infra/.env.ci exec -T redis redis-cli ping
docker compose -f infra/docker-compose.yml --env-file infra/.env.ci down -v
```

## Protect `main`

`main` should require the Quality jobs above before merge. Direct force-push and branch deletion are blocked. **Signed commits are not required** unless the team later adopts a signing workflow.

### One-time setup (repo admin)

1. Merge a change that includes the Quality workflow jobs so GitHub registers the check names.
2. Install [GitHub CLI](https://cli.github.com/) and authenticate: `gh auth login`.
3. Apply protection:

```bash
chmod +x scripts/github/apply-main-branch-protection.sh
./scripts/github/apply-main-branch-protection.sh --dry-run
./scripts/github/apply-main-branch-protection.sh
```

4. Confirm in **Settings → Branches → Branch protection rules** (or rulesets) that `main` requires:
   - `Quality / backend`
   - `Quality / frontend`
   - `Quality / security-audit`
   - `Quality / container-smoke`
   - At least one approving review
   - No force pushes or deletions

If check names differ (older GitHub UI), list recent runs:

```bash
gh api repos/$(gh repo view --json nameWithOwner -q .nameWithOwner)/commits/$(gh api repos/$(gh repo view --json nameWithOwner -q .nameWithOwner)/branches/main --jq .commit.sha)/check-runs --jq '.check_runs[].name'
```

Update `scripts/github/apply-main-branch-protection.sh` with the exact names before applying.

### Validation

- Open a PR with an intentional lint failure; merge should be blocked.
- Confirm force-push to `main` is rejected: `git push --force origin main` (should fail for non-admins / when protection is active).
