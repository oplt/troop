#!/usr/bin/env bash
# Apply main-branch protection requiring Quality workflow checks.
#
# Prerequisites:
#   - GitHub CLI: https://cli.github.com/
#   - Repo admin permissions
#   - At least one successful Quality workflow run on main (so check names exist)
#
# Usage:
#   ./scripts/github/apply-main-branch-protection.sh
#   ./scripts/github/apply-main-branch-protection.sh --dry-run
#
# Signed commits are intentionally NOT required (opt-in when the team adopts GPG/SSH signing).

set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required. Install from https://cli.github.com/" >&2
  exit 1
fi

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
DEFAULT_BRANCH="$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)"

if [[ "$DEFAULT_BRANCH" != "main" ]]; then
  echo "Default branch is '$DEFAULT_BRANCH', not 'main'. Update this script or pass a fork-specific ruleset." >&2
  exit 1
fi

# After the first Quality run, confirm names with:
#   gh api repos/$REPO/commits/$(gh api repos/$REPO/branches/main --jq .commit.sha)/check-runs --jq '.check_runs[].name'
REQUIRED_CHECKS=(
  "Quality / backend"
  "Quality / frontend"
  "Quality / security-audit"
  "Quality / container-smoke"
)

export REQUIRED_CHECKS="$(printf '%s\n' "${REQUIRED_CHECKS[@]}")"
payload="$(REQUIRED_CHECKS="$REQUIRED_CHECKS" python3 - <<'PY'
import json
import os

checks = [line.strip() for line in os.environ["REQUIRED_CHECKS"].splitlines() if line.strip()]
print(json.dumps({
    "required_status_checks": {
        "strict": True,
        "checks": [{"context": c} for c in checks],
    },
    "enforce_admins": True,
    "required_pull_request_reviews": {
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": False,
        "required_approving_review_count": 1,
    },
    "restrictions": None,
    "required_linear_history": False,
    "allow_force_pushes": False,
    "allow_deletions": False,
    "block_creations": False,
    "required_conversation_resolution": True,
}))
PY
)"

echo "Repository: $REPO"
echo "Branch: main"
echo "Required checks:"
printf '  - %s\n' "${REQUIRED_CHECKS[@]}"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo
  echo "Dry run payload:"
  echo "$payload" | python3 -m json.tool
  exit 0
fi

gh api \
  -X PUT \
  "repos/${REPO}/branches/main/protection" \
  --input - <<<"$payload"

echo
echo "Branch protection applied. Verify in GitHub: Settings → Branches → main."
