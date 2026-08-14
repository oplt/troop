-- RBAC-001A workspace backfill validation (run after h4b5c6d7e8f0 upgrade)
-- Expected: zero rows for every check.

-- 1) Every user has exactly one default workspace they own
SELECT u.id AS user_id, COUNT(w.id) AS default_workspace_count
FROM users u
LEFT JOIN workspaces w
  ON w.owner_user_id = u.id AND w.is_default = true
GROUP BY u.id
HAVING COUNT(w.id) <> 1;

-- 2) Default workspace owner is also an active owner member
SELECT w.id AS workspace_id, w.owner_user_id
FROM workspaces w
WHERE w.is_default = true
  AND NOT EXISTS (
    SELECT 1
    FROM workspace_memberships m
    WHERE m.workspace_id = w.id
      AND m.user_id = w.owner_user_id
      AND m.role = 'owner'
      AND m.status = 'active'
  );

-- 3) No duplicate memberships per workspace/user
SELECT workspace_id, user_id, COUNT(*) AS membership_count
FROM workspace_memberships
GROUP BY workspace_id, user_id
HAVING COUNT(*) > 1;

-- 4) No orphan memberships
SELECT m.id
FROM workspace_memberships m
LEFT JOIN workspaces w ON w.id = m.workspace_id
WHERE w.id IS NULL;

-- 5) Slug uniqueness per owner (including non-default future workspaces)
SELECT owner_user_id, slug, COUNT(*) AS slug_count
FROM workspaces
GROUP BY owner_user_id, slug
HAVING COUNT(*) > 1;
