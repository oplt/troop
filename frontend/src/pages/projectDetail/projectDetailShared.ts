import type { OrchestrationTask, TaskRun } from "../../api/orchestration";
import type { ExternalLinkRecord } from "../../features/orchestration/project/components/ExternalLinksEditor";

export type ExecutionMode = "single_agent" | "manager_worker" | "debate";

export const BRAINSTORM_MODE_OPTIONS = [
    { value: "exploration", label: "Exploration" },
    { value: "solution_design", label: "Solution design" },
    { value: "code_review", label: "Code review debate" },
    { value: "incident_triage", label: "Incident triage" },
    { value: "root_cause", label: "Root-cause analysis" },
    { value: "architecture_proposal", label: "Architecture proposal" },
] as const;

export const BRAINSTORM_OUTPUT_OPTIONS = [
    { value: "implementation_plan", label: "Implementation plan" },
    { value: "adr", label: "ADR" },
    { value: "test_plan", label: "Test plan" },
    { value: "risk_register", label: "Risk register" },
] as const;

export const EXCEPTION_TASK_COLUMNS: { status: string; label: string; color: "default" | "warning" | "info" | "success" | "error" }[] = [
    { status: "blocked", label: "Blocked", color: "warning" },
    { status: "failed", label: "Failed", color: "error" },
    { status: "archived", label: "Archived", color: "default" },
];

export const TASK_TRANSITION_MAP: Record<string, string[]> = {
    backlog: ["queued", "archived"],
    queued: ["planned", "blocked", "failed", "archived"],
    planned: ["in_progress", "blocked", "failed", "archived"],
    in_progress: ["blocked", "needs_review", "completed", "failed", "planned"],
    blocked: ["planned", "in_progress", "failed", "archived"],
    needs_review: ["approved", "planned", "blocked", "failed"],
    approved: ["completed", "planned", "archived"],
    completed: ["synced_to_github", "planned", "archived"],
    failed: ["planned", "queued", "archived"],
    synced_to_github: ["archived", "planned"],
    archived: [],
};

export type EvidenceBundleDraft = {
    accepted_artifact_ids: string[];
    accepted_external_link_ids: string[];
    reviewer_decision_status: string;
    reviewer_decision_notes: string;
    sync_summary: string;
};

export type WorkspaceOverviewDraft = {
    executive_summary: string;
    current_focus: string;
    decision_focus: string;
};

export type LocalRepoDraft = {
    enabled: boolean;
    repo_path: string;
    dirty_worktree_policy: string;
    allowed_branches: string;
    file_allowlist: string;
    file_denylist: string;
    command_allowlist: string;
    max_diff_bytes: string;
};

export function csvFromUnknown(value: unknown, fallback = "") {
    return Array.isArray(value) ? value.map((item) => String(item)).join(", ") : fallback;
}

export function splitCsv(value: string) {
    return value
        .split(/[,\n]/)
        .map((item) => item.trim())
        .filter(Boolean);
}

export type TransitionOption = {
    status: string;
    reason?: string;
    blocked?: boolean;
};

export function createClientId(prefix: string) {
    return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export function toastQueuedRunWithOptionalWarnings(
    showToast: (opts: { message: string; severity: "success" | "error" | "warning" | "info" }) => void,
    run: TaskRun,
    successLine: string,
) {
    const w = run.startup_warnings ?? [];
    if (w.length) {
        showToast({ message: `${successLine} ${w.join(" ")}`, severity: "warning" });
    } else {
        showToast({ message: successLine, severity: "success" });
    }
}

export function readExternalLinks(raw: unknown): ExternalLinkRecord[] {
    if (!Array.isArray(raw)) return [];
    return raw.flatMap((item) => {
        if (typeof item !== "object" || item === null) return [];
        const row = item as Record<string, unknown>;
        const url = String(row.url ?? "").trim();
        const label = String(row.label ?? "").trim();
        if (!url || !label) return [];
        return [{
            id: String(row.id ?? createClientId("link")),
            kind: String(row.kind ?? "other"),
            label,
            url,
            notes: String(row.notes ?? ""),
        }];
    });
}

export function serializeExternalLinks(links: ExternalLinkRecord[]) {
    return links
        .map((link) => ({
            id: link.id,
            kind: link.kind || "other",
            label: link.label.trim(),
            url: link.url.trim(),
            notes: link.notes.trim(),
        }))
        .filter((link) => link.label && link.url);
}

export function readEvidenceBundle(task: OrchestrationTask): EvidenceBundleDraft {
    const raw = typeof task.metadata?.evidence_bundle === "object" && task.metadata.evidence_bundle !== null
        ? task.metadata.evidence_bundle as Record<string, unknown>
        : {};
    const reviewerDecision = typeof raw.reviewer_decision === "object" && raw.reviewer_decision !== null
        ? raw.reviewer_decision as Record<string, unknown>
        : {};
    return {
        accepted_artifact_ids: Array.isArray(raw.accepted_artifact_ids)
            ? raw.accepted_artifact_ids.map((item) => String(item)).filter(Boolean)
            : [],
        accepted_external_link_ids: Array.isArray(raw.accepted_external_link_ids)
            ? raw.accepted_external_link_ids.map((item) => String(item)).filter(Boolean)
            : [],
        reviewer_decision_status: String(reviewerDecision.status ?? ""),
        reviewer_decision_notes: String(reviewerDecision.notes ?? ""),
        sync_summary: String(raw.sync_summary ?? ""),
    };
}

export function buildEvidenceBundlePayload(bundle: EvidenceBundleDraft) {
    return {
        accepted_artifact_ids: bundle.accepted_artifact_ids,
        accepted_external_link_ids: bundle.accepted_external_link_ids,
        reviewer_decision: {
            status: bundle.reviewer_decision_status.trim(),
            notes: bundle.reviewer_decision_notes.trim(),
        },
        sync_summary: bundle.sync_summary.trim(),
    };
}

export function readWorkspaceOverview(settings: Record<string, unknown> | undefined): WorkspaceOverviewDraft {
    const raw = typeof settings?.workspace_overview === "object" && settings.workspace_overview !== null
        ? settings.workspace_overview as Record<string, unknown>
        : {};
    return {
        executive_summary: String(raw.executive_summary ?? ""),
        current_focus: String(raw.current_focus ?? ""),
        decision_focus: String(raw.decision_focus ?? ""),
    };
}

export function buildTransitionOptions(args: {
    task: OrchestrationTask;
    acceptancePassed: boolean;
    evidenceReadyForSync: boolean;
    evidenceReadyForArchive: boolean;
    hasIncompleteDependencies: boolean;
}): TransitionOption[] {
    const allowed = TASK_TRANSITION_MAP[args.task.status] ?? [];
    return allowed.map((status) => {
        if (status === "approved" || status === "completed") {
            return {
                status,
                blocked: !args.acceptancePassed,
                reason: args.acceptancePassed ? undefined : "Acceptance gate must pass first.",
            };
        }
        if (status === "synced_to_github") {
            return {
                status,
                blocked: !args.evidenceReadyForSync,
                reason: args.evidenceReadyForSync ? undefined : "Evidence bundle needs accepted artifacts, links, reviewer decision, sync summary.",
            };
        }
        if (status === "archived") {
            return {
                status,
                blocked: !args.evidenceReadyForArchive,
                reason: args.evidenceReadyForArchive ? undefined : "Archive needs final evidence bundle or prior GitHub sync.",
            };
        }
        if (status === "in_progress") {
            return {
                status,
                blocked: args.hasIncompleteDependencies,
                reason: args.hasIncompleteDependencies ? "Task still blocked by incomplete dependencies." : undefined,
            };
        }
        return { status };
    });
}

export type PolicyRoutingRule = {
    field?: string;
    operator?: string;
    value?: unknown;
    route_to?: "cheap_model_slug" | "strong_model_slug" | "local_model_slug" | string;
};

export function policyFieldValue(
    field: string,
    sample: { priority: string; taskType: string; labels: string[]; projectSensitive: boolean }
): unknown {
    if (field === "task.priority") return sample.priority;
    if (field === "task.task_type") return sample.taskType;
    if (field === "task.labels") return sample.labels;
    if (field === "project.is_sensitive") return sample.projectSensitive;
    return null;
}

export function policyRuleMatches(actual: unknown, operator: string, expected: unknown): boolean {
    if (operator === "equals") return actual === expected;
    if (operator === "contains") {
        if (Array.isArray(actual)) return actual.includes(expected);
        if (typeof actual === "string") return String(actual).includes(String(expected ?? ""));
    }
    return false;
}

export type AcceptanceCheckerConfig = {
    required_artifact_kinds: string[];
    require_github_comment: boolean;
    require_github_pr: boolean;
    require_reviewer_approval: boolean;
};

export function readAcceptanceCheckerConfig(task: OrchestrationTask): AcceptanceCheckerConfig {
    const raw = task.metadata?.acceptance_checker;
    const config = typeof raw === "object" && raw !== null ? raw as Record<string, unknown> : {};
    return {
        required_artifact_kinds: Array.isArray(config.required_artifact_kinds)
            ? config.required_artifact_kinds.map((item) => String(item).trim()).filter(Boolean)
            : [],
        require_github_comment: Boolean(config.require_github_comment),
        require_github_pr: Boolean(config.require_github_pr),
        require_reviewer_approval: Boolean(config.require_reviewer_approval),
    };
}
