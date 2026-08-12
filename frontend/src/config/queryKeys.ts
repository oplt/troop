/** Canonical React Query keys — keep invalidation scopes predictable. */

export const queryKeys = {
    auth: {
        me: ["auth", "me"] as const,
    },
    profile: {
        root: ["profile"] as const,
    },
    notifications: {
        root: ["notifications"] as const,
        preferences: ["notification-preferences"] as const,
    },
    companies: {
        root: ["companies"] as const,
    },
    calendar: {
        items: (start: string, end: string) => ["calendar", "items", start, end] as const,
        root: ["calendar", "items"] as const,
    },
    platform: {
        metadata: ["platform", "metadata"] as const,
        plans: ["platform", "plans"] as const,
        subscription: ["platform", "subscription"] as const,
        apiKeys: ["platform", "api-keys"] as const,
        webhooks: ["platform", "webhooks"] as const,
        featureFlags: ["platform", "feature-flags"] as const,
    },
    ai: {
        root: ["ai"] as const,
        overview: ["ai", "overview"] as const,
        reviews: ["ai", "reviews"] as const,
        evaluationRuns: ["ai", "evaluation-runs"] as const,
        promptVersions: (templateId: string | null) => ["ai", "prompt-versions", templateId] as const,
        datasetCases: (datasetId: string | null) => ["ai", "dataset-cases", datasetId] as const,
    },
    settings: {
        database: ["settings", "database"] as const,
        databaseCatalog: ["settings", "database", "catalog"] as const,
    },
    admin: {
        users: (page: number, search: string) => ["admin", "users", page, search] as const,
    },
    agentRuns: {
        detail: (runId: string) => ["agent-run", runId] as const,
        steps: (runId: string) => ["agent-run", runId, "steps"] as const,
        artifacts: (runId: string) => ["agent-run", runId, "artifacts"] as const,
        task: (runId: string, taskId?: string) => ["agent-run", runId, "task", taskId] as const,
    },
    runs: {
        detail: (runId: string) => ["orchestration", "run", runId] as const,
        cost: (runId: string) => ["orchestration", "run", runId, "cost"] as const,
        executionState: (runId: string) => ["orchestration", "run", runId, "execution-state"] as const,
        explanation: (runId: string) => ["orchestration", "run", runId, "explanation"] as const,
        workingMemory: (runId: string) => ["orchestration", "run", runId, "working-memory"] as const,
    },
    orchestration: {
        projects: ["orchestration", "projects"] as const,
        hierarchyRuns: ["orchestration", "hierarchy", "runs"] as const,
        skillCatalog: ["orchestration", "skill-catalog"] as const,
        teamTemplates: ["orchestration", "team-templates"] as const,
        teamProfiles: ["orchestration", "team-profiles"] as const,
        hierarchyAgents: (projectId: string) => ["orchestration", "hierarchy", "agents", projectId] as const,
        overview: ["orchestration", "overview"] as const,
        runsRoot: ["orchestration", "runs"] as const,
        executionInsights: (days: number) => ["orchestration", "execution-insights", days] as const,
        project: (projectId: string) => ["orchestration", "project", projectId] as const,
        projectRoot: ["orchestration", "project"] as const,
        projectTasks: (projectId: string) => ["orchestration", "project", projectId, "tasks"] as const,
        projectTaskTimeline: (projectId: string, taskId: string) =>
            ["orchestration", "project", projectId, "tasks", taskId, "timeline"] as const,
        projectTaskExecution: (projectId: string, taskId?: string) =>
            taskId
                ? (["orchestration", "project", projectId, "task-exec", taskId] as const)
                : (["orchestration", "project", projectId, "task-exec"] as const),
        projectTaskArtifacts: (projectId: string, taskId?: string) =>
            taskId
                ? (["orchestration", "project", projectId, "task-artifacts", taskId] as const)
                : (["orchestration", "project", projectId, "task-artifacts"] as const),
        projectTaskBlockers: (projectId: string, taskId?: string) =>
            taskId
                ? (["orchestration", "project", projectId, "task-blockers", taskId] as const)
                : (["orchestration", "project", projectId, "task-blockers"] as const),
        projectRuns: (projectId: string) => ["orchestration", "project", projectId, "runs"] as const,
        projectAgents: (projectId: string) => ["orchestration", "project", projectId, "agents"] as const,
        projectDocuments: (projectId: string) => ["orchestration", "project", projectId, "documents"] as const,
        projectRepositories: (projectId: string) =>
            ["orchestration", "project", projectId, "repositories"] as const,
        projectRepositoryIndexStatus: (projectId: string) =>
            ["orchestration", "project", projectId, "repository-index-status"] as const,
        projectKnowledge: (projectId: string, q?: string, includeDecisions?: boolean) =>
            q === undefined
                ? (["orchestration", "project", projectId, "knowledge"] as const)
                : (["orchestration", "project", projectId, "knowledge", q, includeDecisions] as const),
        projectSemanticMemory: (projectId: string, q?: string) =>
            q === undefined
                ? (["orchestration", "project", projectId, "semantic-memory"] as const)
                : (["orchestration", "project", projectId, "semantic-memory", q] as const),
        projectMemorySettings: (projectId: string) =>
            ["orchestration", "project", projectId, "memory-settings"] as const,
        projectMemoryIngestJobs: (projectId: string) =>
            ["orchestration", "project", projectId, "memory-ingest-jobs"] as const,
        projectMemory: (projectId: string) => ["orchestration", "project", projectId, "memory"] as const,
        projectIssues: (projectId: string) => ["orchestration", "project", projectId, "issues"] as const,
        projectSyncEvents: (projectId: string) => ["orchestration", "project", projectId, "sync-events"] as const,
        projectMilestones: (projectId: string) => ["orchestration", "project", projectId, "milestones"] as const,
        projectDecisions: (projectId: string) => ["orchestration", "project", projectId, "decisions"] as const,
        projectGateConfig: (projectId: string) => ["orchestration", "project", projectId, "gate-config"] as const,
        workflowTemplates: ["orchestration", "workflow-templates"] as const,
        projectWorkflowTemplates: (projectId: string) => ["orchestration", "project", projectId, "workflow-templates"] as const,
        projectDagReady: (projectId: string) => ["orchestration", "project", projectId, "dag-ready"] as const,
        projectMergePreview: (projectId: string, taskId: string | null) =>
            ["orchestration", "project", projectId, "merge-preview", taskId] as const,
        projectBrainstorms: (projectId: string) => ["orchestration", "project", projectId, "brainstorms"] as const,
        githubIssues: ["orchestration", "github", "issues"] as const,
        githubSyncEvents: ["orchestration", "github-sync-events", "all"] as const,
        hitlAuditLogs: ["orchestration", "hitl", "audit-logs"] as const,
        projectLiveSnapshot: (projectId: string) =>
            ["orchestration", "project", projectId, "live-snapshot"] as const,
        agents: (projectId?: string) =>
            projectId ? (["orchestration", "agents", projectId] as const) : (["orchestration", "agents"] as const),
        agentTemplates: ["orchestration", "agent-templates"] as const,
        providers: ["orchestration", "providers"] as const,
        providerModelCapabilities: ["orchestration", "provider-model-capabilities"] as const,
        acceptance: (taskId: string) => ["orchestration", "acceptance", taskId] as const,
        subtasks: (taskId?: string) =>
            taskId ? (["orchestration", "subtasks", taskId] as const) : (["orchestration", "subtasks"] as const),
        artifacts: (taskId?: string) =>
            taskId ? (["orchestration", "artifacts", taskId] as const) : (["orchestration", "artifacts"] as const),
        taskEpisodic: (projectId: string, taskId?: string) =>
            taskId
                ? (["orchestration", "task-episodic", projectId, taskId] as const)
                : (["orchestration", "task-episodic", projectId] as const),
        taskSemantic: (projectId: string, taskId?: string) =>
            taskId
                ? (["orchestration", "task-semantic", projectId, taskId] as const)
                : (["orchestration", "task-semantic", projectId] as const),
        taskCoord: (projectId: string, taskId?: string) =>
            taskId
                ? (["orchestration", "task-coord", projectId, taskId] as const)
                : (["orchestration", "task-coord", projectId] as const),
        memorySettings: (projectId: string) => ["orchestration", "memory-settings", projectId] as const,
        semantic: (projectId: string, q: string, vecQ: string) =>
            ["orchestration", "semantic", projectId, q, vecQ] as const,
        semanticRoot: (projectId: string) => ["orchestration", "semantic", projectId] as const,
        semanticConflicts: (projectId: string) => ["orchestration", "semantic-conflicts", projectId] as const,
        episodic: (projectId: string, q: string, vecQ: string) =>
            ["orchestration", "episodic", projectId, q, vecQ] as const,
        episodicRoot: (projectId: string) => ["orchestration", "episodic", projectId] as const,
        episodicArchives: (projectId: string) => ["orchestration", "episodic-archives", projectId] as const,
        procedural: (projectId: string) => ["orchestration", "procedural", projectId] as const,
        runsMemoryPage: (projectId: string) =>
            ["orchestration", "project", projectId, "runs-memory-page"] as const,
        runWorkingMemory: (runId: string) => ["orchestration", "run-wm", runId] as const,
        runWorkingMemoryRoot: ["orchestration", "run-wm"] as const,
        approvals: ["orchestration", "approvals"] as const,
        approvalsPendingCount: ["orchestration", "approvals", "pending-count"] as const,
        tools: ["orchestration", "tools"] as const,
        agentVersions: (agentId: string) => ["orchestration", "agent-versions", agentId] as const,
    },
} as const;

export const defaultQueryStaleTimeMs = 5 * 60_000;
