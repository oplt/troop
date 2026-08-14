-- RBAC-001C workspace_id backfill validation (run after i5c6d7e8f9a0 upgrade)
-- Expected: zero rows for every check.

-- 1) No NULL workspace_id on top-level tenant tables (expect zero rows)
SELECT table_name, null_workspace_rows
FROM (
    SELECT 'companies' AS table_name, COUNT(*) AS null_workspace_rows FROM companies WHERE workspace_id IS NULL
    UNION ALL SELECT 'orchestrator_projects', COUNT(*) FROM orchestrator_projects WHERE workspace_id IS NULL
    UNION ALL SELECT 'projects', COUNT(*) FROM projects WHERE workspace_id IS NULL
    UNION ALL SELECT 'agent_profiles', COUNT(*) FROM agent_profiles WHERE workspace_id IS NULL
    UNION ALL SELECT 'team_profiles', COUNT(*) FROM team_profiles WHERE workspace_id IS NULL
    UNION ALL SELECT 'skill_packs', COUNT(*) FROM skill_packs WHERE workspace_id IS NULL
    UNION ALL SELECT 'team_templates', COUNT(*) FROM team_templates WHERE workspace_id IS NULL
    UNION ALL SELECT 'agent_templates', COUNT(*) FROM agent_templates WHERE workspace_id IS NULL
    UNION ALL SELECT 'provider_configs', COUNT(*) FROM provider_configs WHERE workspace_id IS NULL
    UNION ALL SELECT 'github_connections', COUNT(*) FROM github_connections WHERE workspace_id IS NULL
    UNION ALL SELECT 'connector_installations', COUNT(*) FROM connector_installations WHERE workspace_id IS NULL
    UNION ALL SELECT 'connector_oauth_states', COUNT(*) FROM connector_oauth_states WHERE workspace_id IS NULL
    UNION ALL SELECT 'trigger_subscriptions', COUNT(*) FROM trigger_subscriptions WHERE workspace_id IS NULL
    UNION ALL SELECT 'external_events', COUNT(*) FROM external_events WHERE workspace_id IS NULL
    UNION ALL SELECT 'workflow_definitions', COUNT(*) FROM workflow_definitions WHERE workspace_id IS NULL
    UNION ALL SELECT 'action_policies', COUNT(*) FROM action_policies WHERE workspace_id IS NULL
    UNION ALL SELECT 'skills', COUNT(*) FROM skills WHERE workspace_id IS NULL
    UNION ALL SELECT 'procedural_playbooks', COUNT(*) FROM procedural_playbooks WHERE workspace_id IS NULL
    UNION ALL SELECT 'memory_ingest_jobs', COUNT(*) FROM memory_ingest_jobs WHERE workspace_id IS NULL
    UNION ALL SELECT 'episodic_archive_manifests', COUNT(*) FROM episodic_archive_manifests WHERE workspace_id IS NULL
    UNION ALL SELECT 'episodic_search_index', COUNT(*) FROM episodic_search_index WHERE workspace_id IS NULL
    UNION ALL SELECT 'knowledge_graph_edges', COUNT(*) FROM knowledge_graph_edges WHERE workspace_id IS NULL
    UNION ALL SELECT 'semantic_memory_links', COUNT(*) FROM semantic_memory_links WHERE workspace_id IS NULL
    UNION ALL SELECT 'ai_prompt_templates', COUNT(*) FROM ai_prompt_templates WHERE workspace_id IS NULL
    UNION ALL SELECT 'ai_documents', COUNT(*) FROM ai_documents WHERE workspace_id IS NULL
    UNION ALL SELECT 'ai_runs', COUNT(*) FROM ai_runs WHERE workspace_id IS NULL
    UNION ALL SELECT 'ai_evaluation_datasets', COUNT(*) FROM ai_evaluation_datasets WHERE workspace_id IS NULL
    UNION ALL SELECT 'calendar_entries', COUNT(*) FROM calendar_entries WHERE workspace_id IS NULL
    UNION ALL SELECT 'api_keys', COUNT(*) FROM api_keys WHERE workspace_id IS NULL
    UNION ALL SELECT 'webhook_endpoints', COUNT(*) FROM webhook_endpoints WHERE workspace_id IS NULL
) checks
WHERE null_workspace_rows > 0;

-- 2) workspace_id must reference an existing workspace
SELECT 'companies' AS table_name, t.id AS row_id
FROM companies t
LEFT JOIN workspaces w ON w.id = t.workspace_id
WHERE w.id IS NULL
UNION ALL
SELECT 'orchestrator_projects', t.id
FROM orchestrator_projects t
LEFT JOIN workspaces w ON w.id = t.workspace_id
WHERE w.id IS NULL;

-- 3) Default-workspace owner alignment for owner_id tables (sample high-traffic tables)
SELECT p.id AS project_id, p.owner_id, p.workspace_id, w.owner_user_id
FROM orchestrator_projects p
JOIN workspaces w ON w.id = p.workspace_id
WHERE w.owner_user_id <> p.owner_id;

SELECT c.id AS company_id, c.owner_id, c.workspace_id, w.owner_user_id
FROM companies c
JOIN workspaces w ON w.id = c.workspace_id
WHERE w.owner_user_id <> c.owner_id;

-- 4) user_id tables align to workspace owner
SELECT d.id AS document_id, d.user_id, d.workspace_id, w.owner_user_id
FROM ai_documents d
JOIN workspaces w ON w.id = d.workspace_id
WHERE w.owner_user_id <> d.user_id;
