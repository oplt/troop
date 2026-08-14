/** Shared hierarchy / team-graph types and option catalogs. */

import type { Edge, Node } from "@xyflow/react";
export {
    MEMORY_SCOPE_OPTIONS,
    OUTPUT_FORMAT_OPTIONS,
    PERMISSION_OPTIONS,
} from "../../features/agents/contractOptions";

export const ROLE_OPTIONS = ["manager", "team_lead", "specialist", "reviewer"] as const;

export const AGENT_ROLE_GUIDANCE: Record<(typeof ROLE_OPTIONS)[number], { summary: string; promptHint: string; filtersHint: string }> = {
    manager: {
        summary: "Owns planning, delegation, escalation, and final delivery quality.",
        promptHint: "Define how this manager decomposes work, routes tasks, asks for review, and decides when to escalate.",
        filtersHint: "Use routing rules for work this manager should own first: architecture, triage, roadmap, escalation.",
    },
    team_lead: {
        summary: "Coordinates a delegated branch and can route work to its direct specialists.",
        promptHint: "Define the branch this lead owns, how it delegates, and when it escalates to the manager.",
        filtersHint: "Use routing rules for a focused workstream such as API, UI, security, or release operations.",
    },
    specialist: {
        summary: "Executes a scoped domain of work with clear tools, boundaries, and outputs.",
        promptHint: "Describe how this specialist approaches tasks, what depth it should go to, and when it must hand off.",
        filtersHint: "Use routing rules for domain ownership: frontend, backend, incidents, docs, tests, security.",
    },
    reviewer: {
        summary: "Audits work before handoff, catches regressions, and enforces approval standards.",
        promptHint: "Define review criteria, evidence required, failure conditions, and what counts as approval.",
        filtersHint: "Use routing rules for review-style work: QA, compliance, acceptance checks, release review.",
    },
};

export type BuilderTab = "library" | "hierarchy";
export type TeamGraphRole = "manager" | "team_lead" | "specialist" | "reviewer";
export type TeamGraphEdgeSemantic = "delegates_to" | "reviews" | "escalates_to" | "collaborates_with";
export type TeamGraphNodeStatus = "active" | "inactive" | "running" | "blocked" | "queued" | "draft";
export type TeamGraphNodeData = {
    name: string;
    slug: string;
    role: TeamGraphRole;
    description: string;
    linkedTemplateSlug: string;
    linkedAgentId: string;
    capabilities: string[];
    allowedTools: string[];
    tags: string[];
    projectAssignments: string[];
    taskFilters: string[];
    model: string;
    fallbackModel: string;
    escalationPath: string;
    permission: string;
    memoryScope: string;
    outputFormat: string;
    tokenBudget: string;
    timeBudgetSeconds: string;
    retryBudget: string;
    status: TeamGraphNodeStatus;
    subtitle: string;
};

export type TeamGraphNode = Node<TeamGraphNodeData, TeamGraphRole>;
export type TeamGraphEdge = Edge<{ semantic: TeamGraphEdgeSemantic }>;


export type TeamLayoutSnapshot = {
    savedAt: string;
    nodes: TeamGraphNode[];
    edges: TeamGraphEdge[];
    persistence: "local-only" | "project";
};
export const TEAM_GRAPH_STORAGE_KEY = "troop:hierarchy-builder:team-graph-layout:v1";
export const TEAM_GRAPH_PROJECT_STORAGE_KEY = "troop:hierarchy-builder:selected-project:v1";
export const TEAM_GRAPH_AUTOSAVE_DELAY_MS = 700;
export const RUNTIME_ALLOWED_TOOLS = new Set([
    "github_comment",
    "github_label_issue",
    "github_create_pr",
    "web_fetch",
    "web_search",
    "code_execute",
    "fs_read",
    "fs_write",
    "db_query",
    "repo_search",
]);
