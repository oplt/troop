import { useCallback, useMemo, useState, lazy, Suspense } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Checkbox,
    Chip,
    Collapse,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    Drawer,
    IconButton,
    LinearProgress,
    ListSubheader,
    MenuItem,
    Paper,
    Stack,
    Switch,
    FormControlLabel,
    Tab,
    Tabs,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import {
    Add as AddIcon,
    Close as CloseIcon,
    ExpandMore as ExpandMoreIcon,
    ExpandLess as ExpandLessIcon,
    FactCheck as ApproveIcon,
    MoreVert as MoreIcon,
    PlayArrow as RunIcon,
    Upload as UploadIcon,
} from "@mui/icons-material";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { ProviderConfig, TaskRun } from "../../api/orchestration";
import { useSnackbar } from "../../app/snackbarContext";
import { PageShell } from "../../components/ui/PageShell";
import { DensePageMobileNotice } from "../../components/ui/DensePageMobileNotice";
import { StatusChip } from "../../components/ui/StatusChip";
import { SectionCard } from "../../components/ui/SectionCard";
import { useDebounce } from "../../hooks/useDebounce";
import { useProjectLiveSnapshotSync } from "../../hooks/projectLiveSnapshotSync";
import { formatDateTime, humanizeKey } from "../../utils/formatters";
import { MilestoneTimeline } from "../../features/orchestration/project/components/MilestoneTimeline";
import { ExternalLinksEditor, type ExternalLinkRecord } from "../../features/orchestration/project/components/ExternalLinksEditor";
import { createProjectTaskDraft, normalizeProjectTaskDraft, type ProjectTaskDraft } from "../../features/orchestration/project/taskForm";
import { AcceptanceDialog } from "../../features/orchestration/project/components/AcceptanceDialog";
import { extractApiErrorMessage } from "../../utils/apiErrors";
import { MAIN_KANBAN_COLUMNS } from "./kanbanConstants";
import {
    useProjectDetailQueries,
    type DetailTab,
    type KnowledgeView,
    type TeamView,
    type WorkView,
} from "../../features/orchestration/project/queries";
import {
    EMPTY_BRAINSTORM_FORM,
    useProjectDetailMutations,
} from "../../features/orchestration/project/useProjectDetailMutations";
import {
    parseProjectDetailTab,
    projectDetailTabSideEffects,
    syncProjectDetailTabFromSearchParam,
    withProjectDetailTab,
} from "../../features/orchestration/project/routing";
import { PageSkeleton } from "../../components/ui/PageSkeleton";
import {
    ProjectDetailErrorState,
    ProjectDetailLoadingState,
    ProjectDetailMissingState,
} from "../../features/orchestration/project/ProjectDetailState";
import {
    BRAINSTORM_MODE_OPTIONS,
    BRAINSTORM_OUTPUT_OPTIONS,
    type ExecutionMode,
    type LocalRepoDraft,
    type WorkspaceOverviewDraft,
    csvFromUnknown,
    readExternalLinks,
    serializeExternalLinks,
    readWorkspaceOverview,
    policyFieldValue,
    policyRuleMatches,
    type PolicyRoutingRule,
} from "./projectDetailShared";

const KanbanBoard = lazy(() =>
    import("./KanbanBoard").then((m) => ({ default: m.KanbanBoard })),
);
const DagView = lazy(() =>
    import("./DagView").then((m) => ({ default: m.DagView })),
);

export function ProjectDetailWorkspace() {
    const { projectId = "" } = useParams();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const tabParam = searchParams.get("tab");
    const initialTab: DetailTab = parseProjectDetailTab(tabParam);
    const [tab, setTabState] = useState<DetailTab>(initialTab);
    const setTab = useCallback(
        (value: DetailTab) => {
            setTabState(value);
            setSearchParams(withProjectDetailTab(searchParams, value), { replace: true });
        },
        [searchParams, setSearchParams],
    );
    const [trackedTabParam, setTrackedTabParam] = useState(tabParam);
    if (tabParam !== trackedTabParam) {
        setTrackedTabParam(tabParam);
        const syncedTab = syncProjectDetailTabFromSearchParam(tabParam);
        if (syncedTab) {
            setTabState(syncedTab);
        }
    }
    const [workView, setWorkView] = useState<WorkView>("board");
    const [knowledgeView, setKnowledgeView] = useState<KnowledgeView>("memory");
    const [teamView, setTeamView] = useState<TeamView>("agents");
    const [overviewEditOpen, setOverviewEditOpen] = useState(false);
    const [taskForm, setTaskForm] = useState<ProjectTaskDraft>(createProjectTaskDraft);
    const [projectOverviewForm, setProjectOverviewForm] = useState<WorkspaceOverviewDraft>({
        executive_summary: "",
        current_focus: "",
        decision_focus: "",
    });
    const [projectOverviewTouched, setProjectOverviewTouched] = useState(false);
    const [projectGoalsDraft, setProjectGoalsDraft] = useState("");
    const [projectGoalsTouched, setProjectGoalsTouched] = useState(false);
    const [projectExternalLinks, setProjectExternalLinks] = useState<ExternalLinkRecord[]>([]);
    const [projectExternalLinksTouched, setProjectExternalLinksTouched] = useState(false);
    const [taskOwnerTouched, setTaskOwnerTouched] = useState(false);
    const [taskReviewerTouched, setTaskReviewerTouched] = useState(false);
    const [selectedTaskId, setSelectedTaskId] = useState<string>("");
    const [selectedAgentId, setSelectedAgentId] = useState("");
    const [brainstormForm, setBrainstormForm] = useState(EMPTY_BRAINSTORM_FORM);
    const [brainstormAdvancedOpen, setBrainstormAdvancedOpen] = useState(false);
    const [milestoneForm, setMilestoneForm] = useState({ title: "", description: "", due_date: "" });
    const [decisionForm, setDecisionForm] = useState({ title: "", decision: "", rationale: "", author_label: "" });
    const [knowledgeQuery, setKnowledgeQuery] = useState("");
    const [includeDecisionRecall, setIncludeDecisionRecall] = useState(true);
    const [documentTtlDays, setDocumentTtlDays] = useState("30");
    const [agentMemoryForm, setAgentMemoryForm] = useState({
        agent_id: "",
        key: "",
        value_text: "",
        scope: "project-only" as "project-only" | "long-term",
        ttl_days: "30",
    });
    const [expandedDocumentId, setExpandedDocumentId] = useState<string | null>(null);
    const [githubForm, setGithubForm] = useState<Partial<{
        branch_prefix: string;
        enforce_branch_naming: boolean;
        auto_post_progress: boolean;
        auto_activate_review_on_pr_open: boolean;
        auto_review_on_pr_review: boolean;
        close_issue_with_manager_summary: boolean;
        sync_labels_to_github: boolean;
        sync_assignees_to_github: boolean;
        sync_state_to_github: boolean;
        sync_milestone_to_github: boolean;
        repo_agent_pools_json: string;
    }>>({});
    const [localRepoForm, setLocalRepoForm] = useState<Partial<LocalRepoDraft>>({});
    const [hitlForm, setHitlForm] = useState<Partial<{
        sandbox_note: string;
        secret_scope: string;
        sandbox_mode: string;
    }>>({});
    const [approvalReasonById, setApprovalReasonById] = useState<Record<string, string>>({});
    const [acceptanceTaskId, setAcceptanceTaskId] = useState<string | null>(null);
    const [taskRunModes, setTaskRunModes] = useState<Record<string, ExecutionMode>>({});
    const [taskPrModes, setTaskPrModes] = useState<Record<string, boolean>>({});
    const [dagDrawerTaskId, setDagDrawerTaskId] = useState<string | null>(null);
    const [taskDrawerOpen, setTaskDrawerOpen] = useState(false);
    const [taskAdditionalOpen, setTaskAdditionalOpen] = useState(false);
    const [taskCriteriaList, setTaskCriteriaList] = useState<string[]>([]);
    const [dagDependencyDrafts, setDagDependencyDrafts] = useState<Record<string, string[]>>({});
    const [projectTeamSettings, setProjectTeamSettings] = useState<null | {
        manager_agent_id: string;
        reviewer_agent_ids: string[];
        reviewer_chain_mode: string;
        autonomy_level: string;
        provider_config_id: string;
        model_name: string;
        fallback_model: string;
        escalation_target_agent_id: string;
        stuck_for_minutes: string;
        cost_exceeds_usd: string;
        no_consensus_after_rounds: string;
        routing_mode: string;
        sibling_load_balance: string;
        skip_unhealthy_worker_providers: boolean;
        offline_local_only_mode: boolean;
        enforce_project_model_policy: boolean;
        allowed_provider_types_csv: string;
        allowed_model_slugs_csv: string;
        blocked_handoff_mode: string;
        blocked_handoff_target_agent_id: string;
        blocked_handoff_fallback_to_manager: boolean;
        sla_enabled: boolean;
        sla_warn_hours: string;
        sla_escalate_after_due_hours: string;
    }>(null);
    const [policyPreviewForm, setPolicyPreviewForm] = useState({
        priority: "normal",
        taskType: "general",
        labelsCsv: "",
        projectSensitive: false,
    });
    const [memorySettingsDraft, setMemorySettingsDraft] = useState<null | {
        semantic_write_requires_approval: boolean;
        episodic_retention_days: string;
        deep_recall_mode: boolean;
    }>(null);
    const [mergeTaskId, setMergeTaskId] = useState<string | null>(null);
    const [mergeNotes, setMergeNotes] = useState("");
    const [repoIndexDrafts, setRepoIndexDrafts] = useState<Record<string, { scheduleLabel: string; pathPrefixes: string; autoEnabled: boolean }>>({});
    const debouncedKnowledgeQuery = useDebounce(knowledgeQuery.trim(), 250);
    const projectQueryEnabled = Boolean(projectId);
    const projectDetailQueries = useProjectDetailQueries(projectId, {
        tab,
        workView,
        knowledgeView,
        knowledgeQuery: debouncedKnowledgeQuery,
        includeDecisionRecall,
        mergeTaskId,
    });
    const { data: project, isLoading: projectLoading, isError: projectLoadFailed, error: projectLoadError, refetch: refetchProject, isFetching: projectFetching } = projectDetailQueries.project;
    const { data: tasks = [] } = projectDetailQueries.tasks;
    const { data: allAgents = [] } = projectDetailQueries.allAgents;
    const { data: agentTemplates = [] } = projectDetailQueries.agentTemplates;
    const { data: providers = [] } = projectDetailQueries.providers;
    const { data: projectAgents = [] } = projectDetailQueries.projectAgents;
    const { data: brainstorms = [] } = projectDetailQueries.brainstorms;
    const { data: runs = [] } = projectDetailQueries.runs;
    const lastRunByTaskId = useMemo(() => {
        const m: Record<string, TaskRun> = {};
        for (const r of runs) {
            if (r.task_id && m[r.task_id] === undefined) {
                m[r.task_id] = r;
            }
        }
        return m;
    }, [runs]);
    const { data: docs = [] } = projectDetailQueries.docs;
    const { data: projectRepositories = [] } = projectDetailQueries.projectRepositories;
    const { data: repositoryIndexStatus = [] } = projectDetailQueries.repositoryIndexStatus;
    const { data: knowledgeResults = [] } = projectDetailQueries.knowledgeResults;
    const { data: semanticEntries = [] } = projectDetailQueries.semanticEntries;
    const { data: projectMemorySettings } = projectDetailQueries.projectMemorySettings;
    const { data: memoryIngestJobs = [] } = projectDetailQueries.memoryIngestJobs;
    const { data: memoryEntries = [] } = projectDetailQueries.memoryEntries;
    const { data: approvals = [] } = projectDetailQueries.approvals;
    const { data: issueLinks = [] } = projectDetailQueries.issueLinks;
    const { data: syncEvents = [] } = projectDetailQueries.syncEvents;
    const { data: milestones = [] } = projectDetailQueries.milestones;
    const { data: decisions = [] } = projectDetailQueries.decisions;
    const { data: gateConfig } = projectDetailQueries.gateConfig;
    const { data: dagReadyList = [] } = projectDetailQueries.dagReadyList;
    const { data: mergePreview } = projectDetailQueries.mergePreview;

    useProjectLiveSnapshotSync(projectId, { enabled: projectQueryEnabled });

    const projectAgentMap = useMemo(() => new Set(projectAgents.map((item) => item.agent_id)), [projectAgents]);
    const projectAgentProfiles = useMemo(
        () => allAgents.filter((agent) => projectAgentMap.has(agent.id)),
        [allAgents, projectAgentMap],
    );
    const availableAgents = allAgents.filter((agent) => !projectAgentMap.has(agent.id));
    const assignableTemplates = agentTemplates.filter((template) => {
        const templateSlug = String(template.slug || "").trim();
        if (!templateSlug) return false;
        return !projectAgentProfiles.some((agent) => agent.parent_template_slug === templateSlug);
    });
    const brainstormParticipantProfiles = useMemo(
        () => allAgents.filter((agent) => brainstormForm.participant_agent_ids.includes(agent.id)),
        [allAgents, brainstormForm.participant_agent_ids],
    );
    const brainstormSuggestedOutput = useMemo(() => {
        const byMode: Record<string, string> = {
            exploration: "implementation_plan",
            solution_design: "implementation_plan",
            code_review: "test_plan",
            incident_triage: "risk_register",
            root_cause: "risk_register",
            architecture_proposal: "adr",
        };
        return byMode[brainstormForm.mode] ?? "implementation_plan";
    }, [brainstormForm.mode]);
    const dagTask = useMemo(
        () => (dagDrawerTaskId ? tasks.find((t) => t.id === dagDrawerTaskId) ?? null : null),
        [tasks, dagDrawerTaskId],
    );
    const dagTaskLatestRun = useMemo(() => {
        if (!dagTask) return null;
        const forTask = [...runs].filter((r) => r.task_id === dagTask.id);
        forTask.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        return forTask[0] ?? null;
    }, [runs, dagTask]);
    const dagTaskSubtasks = useMemo(() => {
        if (!dagTask) return [];
        return tasks.filter((t) => t.parent_task_id === dagTask.id);
    }, [tasks, dagTask]);
    const dagTaskDependents = useMemo(() => {
        if (!dagTask) return [];
        return tasks.filter((task) => (task.dependency_ids ?? []).includes(dagTask.id));
    }, [tasks, dagTask]);
    const dagBlockedSuggestion = useMemo(() => {
        if (!dagTask) return null;
        const targetId = typeof dagTask.metadata?.suggested_handoff_agent_id === "string" ? dagTask.metadata.suggested_handoff_agent_id : "";
        if (!targetId) return null;
        const targetAgent = allAgents.find((agent) => agent.id === targetId);
        return {
            agentName: targetAgent?.name || targetId,
            via: String(dagTask.metadata?.handoff_suggested_via || "handoff rule"),
            reason: String(dagTask.metadata?.handoff_blocked_reason || ""),
        };
    }, [allAgents, dagTask]);
    const dagDescendantIds = useMemo(() => {
        if (!dagTask) return new Set<string>();
        const dependentsById = new Map<string, string[]>();
        for (const task of tasks) {
            for (const depId of task.dependency_ids ?? []) {
                const current = dependentsById.get(depId) ?? [];
                current.push(task.id);
                dependentsById.set(depId, current);
            }
        }
        const descendants = new Set<string>();
        const stack = [...(dependentsById.get(dagTask.id) ?? [])];
        while (stack.length > 0) {
            const current = stack.pop();
            if (!current || descendants.has(current)) continue;
            descendants.add(current);
            stack.push(...(dependentsById.get(current) ?? []));
        }
        return descendants;
    }, [dagTask, tasks]);
    const currentDagDependencySelection = dagTask ? (dagDependencyDrafts[dagTask.id] ?? dagTask.dependency_ids ?? []) : [];
    const githubDefaults = useMemo(() => {
        const gh = (project?.settings?.github as Record<string, unknown> | undefined) ?? {};
        return {
            branch_prefix: String(gh.branch_prefix ?? "troop/{task_id}-{slug}"),
            enforce_branch_naming: Boolean(gh.enforce_branch_naming ?? true),
            auto_post_progress: Boolean(gh.auto_post_progress),
            auto_activate_review_on_pr_open: Boolean(gh.auto_activate_review_on_pr_open ?? true),
            auto_review_on_pr_review: Boolean(gh.auto_review_on_pr_review),
            close_issue_with_manager_summary: Boolean(gh.close_issue_with_manager_summary ?? true),
            sync_labels_to_github: Boolean(gh.sync_labels_to_github ?? true),
            sync_assignees_to_github: Boolean(gh.sync_assignees_to_github ?? true),
            sync_state_to_github: Boolean(gh.sync_state_to_github ?? true),
            sync_milestone_to_github: Boolean(gh.sync_milestone_to_github ?? true),
            repo_agent_pools_json: JSON.stringify(gh.repo_agent_pools ?? {}, null, 2),
        };
    }, [project?.settings]);
    const resolvedGithubForm = { ...githubDefaults, ...githubForm };
    const localRepoDefaults = useMemo<LocalRepoDraft>(() => {
        const repo = (project?.settings?.local_repo as Record<string, unknown> | undefined) ?? {};
        return {
            enabled: Boolean(repo.enabled),
            repo_path: String(repo.repo_path ?? ""),
            dirty_worktree_policy: String(repo.dirty_worktree_policy ?? "block"),
            allowed_branches: csvFromUnknown(repo.allowed_branches, "main, master, develop"),
            file_allowlist: csvFromUnknown(repo.file_allowlist, "**/*"),
            file_denylist: csvFromUnknown(repo.file_denylist, ".git/**, .env, .env.*, **/.env, **/.env.*, node_modules/**, **/node_modules/**"),
            command_allowlist: csvFromUnknown(repo.command_allowlist, "git status, git diff, rg, pnpm, uv, pytest"),
            max_diff_bytes: String(repo.max_diff_bytes ?? 200000),
        };
    }, [project?.settings]);
    const resolvedLocalRepoForm = { ...localRepoDefaults, ...localRepoForm };
    const hitlDefaults = useMemo(() => {
        const hitl = (project?.settings?.hitl as Record<string, unknown> | undefined) ?? {};
        return {
            sandbox_note: String(hitl.sandbox_note ?? ""),
            secret_scope: String(hitl.secret_scope ?? "project_default"),
            sandbox_mode: String(hitl.sandbox_mode ?? "allow_host_fallback"),
        };
    }, [project?.settings]);
    const resolvedHitlForm = { ...hitlDefaults, ...hitlForm };
    const executionSettings = ((project?.settings?.execution as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    const defaultReviewerAgentIds = projectAgents
        .filter((membership) => membership.role === "reviewer")
        .map((membership) => membership.agent_id);
    const resolvedProjectTeamSettings = projectTeamSettings ?? {
        manager_agent_id: String((executionSettings.manager_agent_id as string | undefined) ?? ""),
        reviewer_agent_ids: Array.isArray(executionSettings.reviewer_agent_ids) && executionSettings.reviewer_agent_ids.length > 0
            ? executionSettings.reviewer_agent_ids as string[]
            : defaultReviewerAgentIds,
        reviewer_chain_mode: String((executionSettings.reviewer_chain_mode as string | undefined) ?? "sequential"),
        autonomy_level: String((executionSettings.autonomy_level as string | undefined) ?? "semi-autonomous"),
        provider_config_id: String((executionSettings.provider_config_id as string | undefined) ?? ""),
        model_name: String((executionSettings.model_name as string | undefined) ?? ""),
        fallback_model: String((executionSettings.fallback_model as string | undefined) ?? ""),
        escalation_target_agent_id: String((((executionSettings.escalation_rules as Array<Record<string, unknown>> | undefined) ?? [])[0]?.escalate_to as string | undefined) ?? ""),
        stuck_for_minutes: String((((executionSettings.escalation_rules as Array<Record<string, unknown>> | undefined) ?? []).find((item) => item.condition === "stuck_for_minutes")?.value as number | undefined) ?? 30),
        cost_exceeds_usd: String((((executionSettings.escalation_rules as Array<Record<string, unknown>> | undefined) ?? []).find((item) => item.condition === "cost_exceeds_usd")?.value as number | undefined) ?? 10),
        no_consensus_after_rounds: String((((executionSettings.escalation_rules as Array<Record<string, unknown>> | undefined) ?? []).find((item) => item.condition === "no_consensus_after_rounds")?.value as number | undefined) ?? 3),
        routing_mode: String((executionSettings.routing_mode as string | undefined) ?? "capability_based"),
        sibling_load_balance: String((executionSettings.sibling_load_balance as string | undefined) ?? "queue_depth"),
        skip_unhealthy_worker_providers: executionSettings.skip_unhealthy_worker_providers !== false,
        offline_local_only_mode: Boolean(executionSettings.offline_local_only_mode),
        enforce_project_model_policy: Boolean(executionSettings.enforce_project_model_policy),
        allowed_provider_types_csv: Array.isArray(executionSettings.allowed_provider_types)
            ? (executionSettings.allowed_provider_types as string[]).join(", ")
            : "",
        allowed_model_slugs_csv: Array.isArray(executionSettings.allowed_model_slugs)
            ? (executionSettings.allowed_model_slugs as string[]).join(", ")
            : "",
        blocked_handoff_mode: String(((executionSettings.blocked_handoff as Record<string, unknown> | undefined)?.mode as string | undefined) ?? "escalation_path"),
        blocked_handoff_target_agent_id: String(((executionSettings.blocked_handoff as Record<string, unknown> | undefined)?.target_agent_id as string | undefined) ?? ""),
        blocked_handoff_fallback_to_manager: ((executionSettings.blocked_handoff as Record<string, unknown> | undefined)?.fallback_to_manager as boolean | undefined) !== false,
        sla_enabled: ((executionSettings.sla as Record<string, unknown> | undefined)?.enabled as boolean | undefined) !== false,
        sla_warn_hours: String(((executionSettings.sla as Record<string, unknown> | undefined)?.warn_hours_before_due as number | undefined) ?? 24),
        sla_escalate_after_due_hours: String(((executionSettings.sla as Record<string, unknown> | undefined)?.escalate_hours_after_due as number | undefined) ?? 0),
    };
    const policyRoutingPreview = useMemo(() => {
        const policy = ((executionSettings.policy_routing as Record<string, unknown> | undefined) ?? {}) as {
            cheap_model_slug?: string;
            strong_model_slug?: string;
            local_model_slug?: string;
            rules?: PolicyRoutingRule[];
        };
        const labels = policyPreviewForm.labelsCsv
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean);
        const sample = {
            priority: policyPreviewForm.priority,
            taskType: policyPreviewForm.taskType,
            labels,
            projectSensitive: policyPreviewForm.projectSensitive,
        };
        const rules = Array.isArray(policy.rules) ? policy.rules : [];
        let matchedRule: PolicyRoutingRule | null = null;
        let routeKey = "";
        for (const rule of rules) {
            const field = String(rule.field ?? "");
            const operator = String(rule.operator ?? "equals");
            const actual = policyFieldValue(field, sample);
            if (!policyRuleMatches(actual, operator, rule.value)) continue;
            matchedRule = rule;
            routeKey = String(rule.route_to ?? "");
            break;
        }
        const fallbackModel =
            resolvedProjectTeamSettings.model_name ||
            providers.find((provider) => provider.id === resolvedProjectTeamSettings.provider_config_id)?.default_model ||
            "provider/default";
        const modelFromRoute = routeKey
            ? String((policy as Record<string, unknown>)[routeKey] ?? "")
            : "";
        const selectedModel = modelFromRoute || fallbackModel;
        const selectedProvider =
            routeKey === "local_model_slug"
                ? providers.find((provider) => provider.provider_type === "ollama" && provider.is_enabled) ?? null
                : providers.find((provider) => provider.id === resolvedProjectTeamSettings.provider_config_id) ?? null;
        return {
            matchedRule,
            routeKey,
            selectedModel,
            selectedProviderName: selectedProvider?.name ?? (routeKey === "local_model_slug" ? "local runtime fallback" : "project/default provider"),
        };
    }, [
        executionSettings.policy_routing,
        policyPreviewForm.labelsCsv,
        policyPreviewForm.priority,
        policyPreviewForm.projectSensitive,
        policyPreviewForm.taskType,
        providers,
        resolvedProjectTeamSettings.model_name,
        resolvedProjectTeamSettings.provider_config_id,
    ]);
    const resolvedMemorySettings = memorySettingsDraft ?? {
        semantic_write_requires_approval: Boolean(projectMemorySettings?.semantic_write_requires_approval),
        episodic_retention_days: String(projectMemorySettings?.episodic_retention_days ?? 90),
        deep_recall_mode: Boolean(projectMemorySettings?.deep_recall_mode),
    };
    const workspaceOverviewBase = readWorkspaceOverview(project?.settings);
    const effectiveWorkspaceOverview = projectOverviewTouched ? projectOverviewForm : workspaceOverviewBase;
    const effectiveProjectGoals = projectGoalsTouched ? projectGoalsDraft : (project?.goals_markdown ?? "");
    const effectiveProjectExternalLinks = projectExternalLinksTouched
        ? projectExternalLinks
        : readExternalLinks(project?.settings?.external_links);
    const suggestedTaskOwnerId = useMemo(() => {
        const reviewerIds = new Set(resolvedProjectTeamSettings.reviewer_agent_ids);
        const candidateMembers = projectAgentProfiles.filter((agent) => !reviewerIds.has(agent.id));
        const workerOnly = candidateMembers.filter((agent) => agent.id !== resolvedProjectTeamSettings.manager_agent_id);
        if (workerOnly.length === 1) return workerOnly[0].id;
        if (resolvedProjectTeamSettings.manager_agent_id) return resolvedProjectTeamSettings.manager_agent_id;
        return workerOnly[0]?.id ?? candidateMembers[0]?.id ?? "";
    }, [projectAgentProfiles, resolvedProjectTeamSettings.manager_agent_id, resolvedProjectTeamSettings.reviewer_agent_ids]);
    const suggestedTaskReviewerId = useMemo(() => {
        const owner = projectAgentProfiles.find((agent) => agent.id === (taskForm.assigned_agent_id || suggestedTaskOwnerId));
        if (owner?.reviewer_agent_id) return owner.reviewer_agent_id;
        return resolvedProjectTeamSettings.reviewer_agent_ids[0] ?? "";
    }, [projectAgentProfiles, resolvedProjectTeamSettings.reviewer_agent_ids, suggestedTaskOwnerId, taskForm.assigned_agent_id]);
    const effectiveTaskOwnerId = taskOwnerTouched ? taskForm.assigned_agent_id : (taskForm.assigned_agent_id || suggestedTaskOwnerId);
    const effectiveTaskReviewerId = taskReviewerTouched ? taskForm.reviewer_agent_id : (taskForm.reviewer_agent_id || suggestedTaskReviewerId);
    const memoryIngestCounts = useMemo(() => {
        const counts = { pending: 0, running: 0, completed: 0, failed: 0 };
        for (const job of memoryIngestJobs) {
            const status = String(job.status);
            if (status === "pending") counts.pending += 1;
            else if (status === "running") counts.running += 1;
            else if (status === "completed") counts.completed += 1;
            else if (status === "failed") counts.failed += 1;
        }
        return counts;
    }, [memoryIngestJobs]);

    const milestoneProgress = milestones.length === 0 ? 0
        : Math.round((milestones.filter((m) => m.status === "completed").length / milestones.length) * 100);

    const mutationActions = useMemo(
        () => ({
            clearSelectedAgentId: () => setSelectedAgentId(""),
            resetTaskCreateForm: () => {
                setTaskForm(createProjectTaskDraft());
                setTaskCriteriaList([]);
                setTaskOwnerTouched(false);
                setTaskReviewerTouched(false);
                setTaskDrawerOpen(false);
                setTaskAdditionalOpen(false);
            },
            resetBrainstormForm: () => setBrainstormForm(EMPTY_BRAINSTORM_FORM),
            resetMilestoneForm: () => setMilestoneForm({ title: "", description: "", due_date: "" }),
            resetDecisionForm: () => setDecisionForm({ title: "", decision: "", rationale: "", author_label: "" }),
            resetAgentMemoryFields: () => setAgentMemoryForm((current) => ({ ...current, key: "", value_text: "" })),
            clearLocalRepoDraft: () => setLocalRepoForm({}),
            clearMergeResolution: () => {
                setMergeTaskId(null);
                setMergeNotes("");
            },
            clearDagDependencyDraft: (taskId: string) =>
                setDagDependencyDrafts((current) => {
                    const next = { ...current };
                    delete next[taskId];
                    return next;
                }),
        }),
        [],
    );

    const {
        addAgentMutation,
        deleteAgentMutation,
        createTaskMutation,
        runMutation,
        dagParallelMutation,
        mergeResolutionMutation,
        queueRepositoryIndexMutation,
        updateRepositoryMutation,
        updateMembershipMutation,
        removeMembershipMutation,
        updateHierarchyAgentMutation,
        saveProjectSettingsMutation,
        updateGateConfigMutation,
        brainstormMutation,
        milestoneMutation,
        toggleMilestoneMutation,
        updateDagTaskMutation,
        decisionMutation,
        uploadDocumentMutation,
        deleteDocumentMutation,
        deleteMemoryMutation,
        createMemoryMutation,
        memoryApprovalMutation,
        memorySettingsMutation,
        saveLocalRepoSettingsMutation,
    } = useProjectDetailMutations({
        projectId,
        queryClient,
        showToast,
        navigate,
        actions: mutationActions,
        agentMemoryForm,
        documentTtlDays,
        resolvedLocalRepoForm,
    });

    const pendingMemoryApprovals = approvals.filter(
        (approval) => approval.project_id === projectId && approval.approval_type === "agent_memory_write" && approval.status === "pending",
    );
    const pendingProjectApprovals = approvals.filter(
        (approval) => approval.project_id === projectId && approval.status === "pending",
    );
    const activeRuns = runs.filter((run) => ["queued", "in_progress", "running"].includes(run.status));
    const blockedTasks = tasks.filter((task) => ["blocked", "failed"].includes(task.status));
    const readyTask = tasks.find((task) => ["queued", "planned", "backlog"].includes(task.status));
    const latestDecision = decisions[0];
    const nextAction =
        pendingProjectApprovals.length > 0
            ? { label: "Review approval", detail: `${pendingProjectApprovals.length} pending`, action: () => setTab("runs") }
            : blockedTasks.length > 0
                ? { label: "Unblock task", detail: blockedTasks[0]?.title ?? "Blocked work", action: () => { setTab("board"); setWorkView("board"); } }
                : readyTask
                    ? { label: "Run next task", detail: readyTask.title, action: () => { setTab("board"); setWorkView("board"); setSelectedTaskId(readyTask.id); } }
                    : projectAgents.length === 0
                        ? { label: "Add agent", detail: "No project team yet", action: () => { setTab("agents"); setTeamView("agents"); } }
                        : { label: "Add knowledge", detail: "Upload docs or connect repo", action: () => { setTab("memory"); setKnowledgeView("sources"); } };
    const activityItems = [
        ...runs.map((run) => ({
            id: `run-${run.id}`,
            kind: "Run",
            title: `${humanizeKey(run.run_mode)} · ${humanizeKey(run.status)}`,
            detail: `${run.token_total} tokens`,
            at: run.created_at,
            action: () => navigate(`/runs/${run.id}`),
        })),
        ...syncEvents.map((event) => ({
            id: `sync-${event.id}`,
            kind: "GitHub",
            title: `${event.action} · ${event.status}`,
            detail: event.detail || "No details",
            at: event.created_at,
            action: undefined,
        })),
        ...pendingProjectApprovals.map((approval) => ({
            id: `approval-${approval.id}`,
            kind: "Approval",
            title: humanizeKey(approval.approval_type),
            detail: "Pending review",
            at: approval.created_at,
            action: () => setTab("runs"),
        })),
        ...brainstorms.map((brainstorm) => ({
            id: `brainstorm-${brainstorm.id}`,
            kind: "Brainstorm",
            title: brainstorm.topic,
            detail: humanizeKey(brainstorm.status),
            at: brainstorm.created_at,
            action: () => navigate(`/brainstorms/${brainstorm.id}`),
        })),
    ].sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
    const providerOptions: ProviderConfig[] = providers;
    const saveProjectExecutionSettings = () => {
        const escalationRules = [
            {
                condition: "stuck_for_minutes",
                value: Number(resolvedProjectTeamSettings.stuck_for_minutes || 0),
                escalate_to: resolvedProjectTeamSettings.escalation_target_agent_id || resolvedProjectTeamSettings.manager_agent_id || null,
            },
            {
                condition: "cost_exceeds_usd",
                value: Number(resolvedProjectTeamSettings.cost_exceeds_usd || 0),
                escalate_to: resolvedProjectTeamSettings.escalation_target_agent_id || resolvedProjectTeamSettings.manager_agent_id || null,
            },
            {
                condition: "no_consensus_after_rounds",
                value: Number(resolvedProjectTeamSettings.no_consensus_after_rounds || 0),
                escalate_to: resolvedProjectTeamSettings.escalation_target_agent_id || resolvedProjectTeamSettings.manager_agent_id || null,
            },
        ];
        saveProjectSettingsMutation.mutate({
            settings: {
                ...(project?.settings ?? {}),
                execution: {
                    ...executionSettings,
                    manager_agent_id: resolvedProjectTeamSettings.manager_agent_id || null,
                    reviewer_agent_ids: resolvedProjectTeamSettings.reviewer_agent_ids,
                    reviewer_chain_mode: resolvedProjectTeamSettings.reviewer_chain_mode || "sequential",
                    autonomy_level: resolvedProjectTeamSettings.autonomy_level,
                    provider_config_id: resolvedProjectTeamSettings.provider_config_id || null,
                    model_name: resolvedProjectTeamSettings.model_name || null,
                    fallback_model: resolvedProjectTeamSettings.fallback_model || null,
                    escalation_rules: escalationRules,
                    routing_mode: resolvedProjectTeamSettings.routing_mode || "capability_based",
                    sibling_load_balance: resolvedProjectTeamSettings.sibling_load_balance || "queue_depth",
                    skip_unhealthy_worker_providers: resolvedProjectTeamSettings.skip_unhealthy_worker_providers,
                    offline_local_only_mode: resolvedProjectTeamSettings.offline_local_only_mode,
                    enforce_project_model_policy: resolvedProjectTeamSettings.enforce_project_model_policy,
                    allowed_provider_types: resolvedProjectTeamSettings.allowed_provider_types_csv
                        .split(",")
                        .map((item) => item.trim().toLowerCase())
                        .filter(Boolean),
                    allowed_model_slugs: resolvedProjectTeamSettings.allowed_model_slugs_csv
                        .split(",")
                        .map((item) => item.trim())
                        .filter(Boolean),
                    blocked_handoff: {
                        mode: resolvedProjectTeamSettings.blocked_handoff_mode || "escalation_path",
                        target_agent_id: resolvedProjectTeamSettings.blocked_handoff_target_agent_id || null,
                        fallback_to_manager: resolvedProjectTeamSettings.blocked_handoff_fallback_to_manager,
                    },
                    sla: {
                        enabled: resolvedProjectTeamSettings.sla_enabled,
                        warn_hours_before_due: Number(resolvedProjectTeamSettings.sla_warn_hours || 24),
                        escalate_hours_after_due: Number(resolvedProjectTeamSettings.sla_escalate_after_due_hours || 0),
                    },
                },
            },
        });
    };

    const saveGithubIntegration = () => {
        let repoAgentPools: Record<string, unknown> = {};
        try {
            repoAgentPools = JSON.parse(resolvedGithubForm.repo_agent_pools_json || "{}") as Record<string, unknown>;
        } catch {
            showToast({ message: "Repo agent pools must be valid JSON.", severity: "error" });
            return;
        }
        saveProjectSettingsMutation.mutate({
            settings: {
                ...(project?.settings ?? {}),
                github: {
                    ...((project?.settings?.github as Record<string, unknown> | undefined) ?? {}),
                    branch_prefix: resolvedGithubForm.branch_prefix,
                    enforce_branch_naming: resolvedGithubForm.enforce_branch_naming,
                    auto_post_progress: resolvedGithubForm.auto_post_progress,
                    auto_activate_review_on_pr_open: resolvedGithubForm.auto_activate_review_on_pr_open,
                    auto_review_on_pr_review: resolvedGithubForm.auto_review_on_pr_review,
                    close_issue_with_manager_summary: resolvedGithubForm.close_issue_with_manager_summary,
                    sync_labels_to_github: resolvedGithubForm.sync_labels_to_github,
                    sync_assignees_to_github: resolvedGithubForm.sync_assignees_to_github,
                    sync_state_to_github: resolvedGithubForm.sync_state_to_github,
                    sync_milestone_to_github: resolvedGithubForm.sync_milestone_to_github,
                    repo_agent_pools: repoAgentPools,
                },
            },
        });
    };

    const saveHitlSettings = () => {
        saveProjectSettingsMutation.mutate({
            settings: {
                ...(project?.settings ?? {}),
                hitl: {
                    ...((project?.settings?.hitl as Record<string, unknown> | undefined) ?? {}),
                    sandbox_note: resolvedHitlForm.sandbox_note,
                    secret_scope: resolvedHitlForm.secret_scope,
                    sandbox_mode: resolvedHitlForm.sandbox_mode,
                },
            },
        });
    };

    if (!projectId) {
        return <ProjectDetailMissingState />;
    }

    if (projectLoading) {
        return <ProjectDetailLoadingState />;
    }

    if (projectLoadFailed || !project) {
        const message = extractApiErrorMessage(projectLoadError, "Couldn't load this project. Check your connection and try again.");
        const notFound = /not found/i.test(message);
        return <ProjectDetailErrorState
            message={message}
            notFound={notFound}
            retrying={projectFetching}
            onRetry={() => { void refetchProject(); }}
        />;
    }

    return (
        <PageShell variant="inspector">
            <DensePageMobileNotice surface="Project workspace" />
            <Paper
                sx={{
                    mb: 2,
                    borderRadius: 1,
                    p: { xs: 2, md: 2.5 },
                    border: 1,
                    borderColor: "divider",
                    position: "sticky",
                    top: { xs: 64, md: 72 },
                    zIndex: 8,
                    backgroundColor: (theme) =>
                        theme.palette.mode === "dark"
                            ? alpha(theme.palette.background.paper, 0.92)
                            : "rgba(255,255,255,0.92)",
                    backdropFilter: "blur(10px)",
                }}
            >
                <Stack direction={{ xs: "column", md: "row" }} spacing={2} justifyContent="space-between" alignItems={{ md: "center" }}>
                    <Box sx={{ minWidth: 0 }}>
                        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                            <Typography variant="h4" sx={{ fontWeight: 500 }} noWrap>
                                {project.name}
                            </Typography>
                            <StatusChip status={project.status} kind="project" />
                            {activeRuns.length > 0 ? <Chip size="small" color="warning" label={`${activeRuns.length} running`} /> : null}
                            {blockedTasks.length > 0 ? <Chip size="small" color="error" variant="outlined" label={`${blockedTasks.length} blocked`} /> : null}
                            {pendingProjectApprovals.length > 0 ? (
                                <Chip size="small" color="warning" label={`${pendingProjectApprovals.length} to approve`} />
                            ) : null}
                        </Stack>
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
                            {effectiveWorkspaceOverview.current_focus || project.description || "No current focus set."}
                        </Typography>
                    </Box>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                        <Button variant="contained" startIcon={<RunIcon />} onClick={nextAction.action}>
                            {nextAction.label}
                        </Button>
                        {pendingProjectApprovals.length > 0 ? (
                            <Button
                                variant="outlined"
                                color="warning"
                                startIcon={<ApproveIcon />}
                                onClick={() => setTab("runs")}
                            >
                                Approve ({pendingProjectApprovals.length})
                            </Button>
                        ) : null}
                        <Button variant="outlined" startIcon={<AddIcon />} onClick={() => setTaskDrawerOpen(true)}>
                            Add task
                        </Button>
                        <Tooltip title="Project settings">
                            <IconButton onClick={() => { setTab("settings"); setTeamView("settings"); }} aria-label="Project settings">
                                <MoreIcon />
                            </IconButton>
                        </Tooltip>
                    </Stack>
                </Stack>
            </Paper>

            <Paper sx={{ mb: 2, borderRadius: 1, p: 1 }}>
                <Tabs
                    value={tab}
                    onChange={(_, value: DetailTab) => {
                        setTab(value);
                        const sideEffects = projectDetailTabSideEffects(value);
                        if (sideEffects.workView) setWorkView(sideEffects.workView);
                        if (sideEffects.teamView) setTeamView(sideEffects.teamView);
                        if (sideEffects.knowledgeView) setKnowledgeView(sideEffects.knowledgeView);
                    }}
                    variant="scrollable"
                    scrollButtons="auto"
                >
                    <Tab label="Overview" value="overview" />
                    <Tab label="Board" value="board" />
                    <Tab label="Runs" value="runs" />
                    <Tab label="Agents" value="agents" />
                    <Tab label="Memory" value="memory" />
                    <Tab label="Settings" value="settings" />
                </Tabs>
            </Paper>

            {/* ── Overview ── */}
            {tab === "overview" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "repeat(3, minmax(0, 1fr))", }, alignItems: "start", }}>

                        <SectionCard title="Workspace">
                            <Stack spacing={1.5}>
                                <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                                    {effectiveWorkspaceOverview.executive_summary || project.description || "No summary yet."}
                                </Typography>
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Typography variant="caption" color="text.secondary">Current focus</Typography>
                                    <Typography variant="body2">{effectiveWorkspaceOverview.current_focus || "Not set"}</Typography>
                                </Paper>
                                {effectiveProjectGoals ? (
                                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary">Goals</Typography>
                                        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                                            {effectiveProjectGoals}
                                        </Typography>
                                    </Paper>
                                ) : null}
                                <Button variant="outlined" onClick={() => setOverviewEditOpen(true)}>
                                    Edit overview
                                </Button>
                            </Stack>
                        </SectionCard>
                        <SectionCard
                            title={`Milestones ${milestones.length > 0 ? `(${milestoneProgress}% complete)` : ""}`}
                            description="Track project milestones and overall progress."
                        >
                            {milestones.length > 0 && (
                                <Stack spacing={2} sx={{ mb: 2 }}>
                                    <Box>
                                        <LinearProgress variant="determinate" value={milestoneProgress} sx={{ height: 6, borderRadius: 1 }} />
                                        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                                            {milestones.filter((m) => m.status === "completed").length} / {milestones.length} completed
                                        </Typography>
                                    </Box>
                                    <MilestoneTimeline milestones={milestones} />
                                </Stack>
                            )}
                            <Stack spacing={1}>
                                {milestones.map((m) => (
                                    <Stack key={m.id} direction="row" spacing={1} alignItems="center">
                                        <Chip
                                            label={m.status}
                                            color={m.status === "completed" ? "success" : "default"}
                                            size="small"
                                            onClick={() => toggleMilestoneMutation.mutate({
                                                id: m.id,
                                                status: m.status === "completed" ? "open" : "completed",
                                            })}
                                            sx={{ cursor: "pointer" }}
                                        />
                                        <Box flex={1}>
                                            <Typography variant="body2">{m.title}</Typography>
                                            {m.due_date && <Typography variant="caption" color="text.secondary">Due {new Date(m.due_date).toLocaleDateString()}</Typography>}
                                        </Box>
                                    </Stack>
                                ))}
                            </Stack>
                            <Divider sx={{ my: 1.5 }} />
                            <Stack spacing={1}>
                                <TextField size="small" label="Milestone title" value={milestoneForm.title} onChange={(e) => setMilestoneForm((f) => ({ ...f, title: e.target.value }))} />
                                <TextField size="small" label="Description" value={milestoneForm.description} onChange={(e) => setMilestoneForm((f) => ({ ...f, description: e.target.value }))} multiline minRows={2} />
                                <TextField
                                    size="small" type="date" label="Due date"
                                    InputLabelProps={{ shrink: true }}
                                    value={milestoneForm.due_date}
                                    onChange={(e) => setMilestoneForm((f) => ({ ...f, due_date: e.target.value }))}
                                />
                                <Button
                                    size="small" variant="outlined"
                                    disabled={!milestoneForm.title.trim()}
                                    onClick={() => milestoneMutation.mutate({
                                        title: milestoneForm.title,
                                        description: milestoneForm.description || null,
                                        due_date: milestoneForm.due_date || null,
                                    })}
                                >
                                    Add milestone
                                </Button>
                            </Stack>
                        </SectionCard>


                        <SectionCard title="Project health">
                            <Stack spacing={1.5}>
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Typography variant="caption" color="text.secondary">Next best action</Typography>
                                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }} justifyContent="space-between">
                                        <Box sx={{ minWidth: 0 }}>
                                            <Typography variant="subtitle2">{nextAction.label}</Typography>
                                            <Typography variant="body2" color="text.secondary" noWrap>{nextAction.detail}</Typography>
                                        </Box>
                                        <Button size="small" variant="contained" onClick={nextAction.action}>Open</Button>
                                    </Stack>
                                </Paper>
                                <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                    <StatusChip status={project.status} kind="project" />
                                    <Chip label={`${tasks.length} tasks`} size="small" variant="outlined" />
                                    <Chip label={`${activeRuns.length} active runs`} size="small" color={activeRuns.length ? "warning" : "default"} variant="outlined" />
                                    <Chip label={`${pendingProjectApprovals.length} approvals`} size="small" color={pendingProjectApprovals.length ? "warning" : "default"} variant="outlined" />
                                    <Chip label={`${milestoneProgress}% milestones`} size="small" variant="outlined" />
                                </Stack>
                                <Typography variant="body2" color="text.secondary">
                                    {project.knowledge_summary || "No knowledge summary yet."}
                                </Typography>
                                {pendingProjectApprovals.length > 0 ? (
                                    <Stack spacing={1}>
                                        <Typography variant="subtitle2">Approvals</Typography>
                                        {pendingProjectApprovals.slice(0, 3).map((approval) => (
                                            <Paper key={approval.id} sx={{ p: 1.5, borderRadius: 1, border: 1, borderColor: "divider" }}>
                                                <Stack spacing={1}>
                                                    <Typography variant="body2">{humanizeKey(approval.approval_type)}</Typography>
                                                    <Typography variant="caption" color="text.secondary">Requested {formatDateTime(approval.created_at)}</Typography>
                                                    <TextField
                                                        size="small"
                                                        label="Reason"
                                                        value={approvalReasonById[approval.id] ?? ""}
                                                        onChange={(e) => setApprovalReasonById((current) => ({ ...current, [approval.id]: e.target.value }))}
                                                        placeholder="Required when rejecting"
                                                    />
                                                    <Stack direction="row" spacing={1}>
                                                        <Button size="small" variant="contained" onClick={() => memoryApprovalMutation.mutate({ approvalId: approval.id, status: "approved", reason: approvalReasonById[approval.id] || undefined })}>
                                                            Approve
                                                        </Button>
                                                        <Button
                                                            size="small"
                                                            variant="outlined"
                                                            color="error"
                                                            onClick={() => {
                                                                const reason = (approvalReasonById[approval.id] ?? "").trim();
                                                                if (!reason) {
                                                                    showToast({ message: "Rejection reason is required.", severity: "warning" });
                                                                    return;
                                                                }
                                                                memoryApprovalMutation.mutate({ approvalId: approval.id, status: "rejected", reason });
                                                            }}
                                                        >
                                                            Reject
                                                        </Button>
                                                    </Stack>
                                                </Stack>
                                            </Paper>
                                        ))}
                                    </Stack>
                                ) : null}
                                {latestDecision ? (
                                    <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary">Latest decision</Typography>
                                        <Typography variant="subtitle2">{latestDecision.title}</Typography>
                                        <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                                            {latestDecision.decision}
                                        </Typography>
                                    </Paper>
                                ) : null}
                                <Divider />
                                <Typography variant="subtitle2">Execution</Typography>
                                <Typography variant="body2" color="text.secondary">
                                    Autonomy {String(executionSettings.autonomy_level ?? "semi-autonomous")} · Gate {String(gateConfig?.autonomy_level ?? "assisted")}
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                    Manager {allAgents.find((agent) => agent.id === executionSettings.manager_agent_id)?.name || "not configured"}
                                </Typography>
                            </Stack>
                        </SectionCard>

                </Box>
            )}

            {tab === "board" && (
                <Paper sx={{ mb: 2, borderRadius: 1, p: 1 }}>
                    <Tabs value={workView} onChange={(_, value) => setWorkView(value)} variant="scrollable" scrollButtons="auto">
                        <Tab label="Kanban" value="board" />
                        <Tab label="Dependencies" value="dependencies" />
                        <Tab label="Brainstorms" value="brainstorms" />
                    </Tabs>
                </Paper>
            )}

            {tab === "memory" && (
                <Paper sx={{ mb: 2, borderRadius: 1, p: 1 }}>
                    <Tabs value={knowledgeView} onChange={(_, value) => setKnowledgeView(value)} variant="scrollable" scrollButtons="auto">
                        <Tab label="Memory" value="memory" />
                        <Tab label="Search" value="search" />
                        <Tab label="Sources" value="sources" />
                        <Tab label="Decisions" value="decisions" />
                    </Tabs>
                </Paper>
            )}

            {tab === "settings" && (
                <Paper sx={{ mb: 2, borderRadius: 1, p: 1 }}>
                    <Tabs
                        value={teamView === "settings" || knowledgeView === "integrations" ? (knowledgeView === "integrations" ? "integrations" : "settings") : "settings"}
                        onChange={(_, value) => {
                            if (value === "integrations") {
                                setKnowledgeView("integrations");
                                setTeamView("settings");
                            } else {
                                setTeamView("settings");
                                setKnowledgeView("sources");
                            }
                        }}
                        variant="scrollable"
                        scrollButtons="auto"
                    >
                        <Tab label="Execution" value="settings" />
                        <Tab label="Integrations" value="integrations" />
                    </Tabs>
                </Paper>
            )}

            {/* ── Board ── */}
            {tab === "board" && workView === "board" && (
                <Stack spacing={2}>
                    <Suspense fallback={<PageSkeleton variant="inspector" />}>
                    <KanbanBoard
                        projectId={projectId}
                        tasks={tasks}
                        allAgents={allAgents}
                        lastRunByTaskId={lastRunByTaskId}
                        onRunTask={(taskId, mode, createPr) => { setSelectedTaskId(taskId); runMutation.mutate({ taskId, runMode: mode, createPr }); }}
                        onAcceptanceCheck={(taskId) => setAcceptanceTaskId(taskId)}
                        isRunPending={runMutation.isPending}
                        selectedTaskId={selectedTaskId}
                        taskRunModes={taskRunModes}
                        taskPrModes={taskPrModes}
                        onModeChange={(taskId, mode) => setTaskRunModes((current) => ({ ...current, [taskId]: mode }))}
                        onPrModeChange={(taskId, enabled) => setTaskPrModes((current) => ({ ...current, [taskId]: enabled }))}
                    />
                    </Suspense>
                </Stack>
            )}

            <Drawer
                anchor="right"
                open={taskDrawerOpen}
                onClose={() => {
                    setTaskDrawerOpen(false);
                    setTaskCriteriaList([]);
                }}
                PaperProps={{ sx: { width: { xs: "100%", sm: 440 } } }}
            >
                <Box sx={{ p: 2.5 }}>
                    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                        <Typography variant="h6">New task</Typography>
                        <IconButton size="small" onClick={() => {
                            setTaskDrawerOpen(false);
                            setTaskCriteriaList([]);
                        }}>
                            <CloseIcon fontSize="small" />
                        </IconButton>
                    </Stack>
                    <Stack spacing={2}>
                        <TextField
                            label="Title"
                            value={taskForm.title}
                            onChange={(e) => setTaskForm((f) => ({ ...f, title: e.target.value }))}
                        />
                        <TextField
                            label="Description"
                            value={taskForm.description}
                            onChange={(e) => setTaskForm((f) => ({ ...f, description: e.target.value }))}
                            multiline
                            minRows={3}
                        />
                        <TextField
                            select
                            label="Priority"
                            value={taskForm.priority}
                            onChange={(e) => setTaskForm((f) => ({ ...f, priority: e.target.value }))}
                        >
                            {["low", "normal", "high", "urgent"].map((p) => <MenuItem key={p} value={p}>{p}</MenuItem>)}
                        </TextField>
                        <TextField
                            select
                            label="Owner agent"
                            helperText="Defaults to team manager."
                            value={effectiveTaskOwnerId}
                            onChange={(e) => {
                                setTaskOwnerTouched(true);
                                setTaskForm((f) => ({ ...f, assigned_agent_id: e.target.value }));
                            }}
                        >
                            <MenuItem value="">Unassigned</MenuItem>
                            {projectAgentProfiles.map((agent) => <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>)}
                        </TextField>
                        <TextField
                            label="Due date (ISO)"
                            helperText="Optional. Used with SLA scan and routing."
                            value={taskForm.due_date}
                            onChange={(e) => setTaskForm((f) => ({ ...f, due_date: e.target.value }))}
                            placeholder="2026-12-31T17:00:00Z"
                        />

                        <Divider />

                        <Button
                            onClick={() => setTaskAdditionalOpen((v) => !v)}
                            endIcon={taskAdditionalOpen ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                            sx={{ justifyContent: "space-between", textTransform: "none" }}
                        >
                            Additional
                        </Button>
                        <Collapse in={taskAdditionalOpen} unmountOnExit>
                            <Stack spacing={2}>
                                <TextField
                                    select
                                    fullWidth
                                    label="Task source"
                                    value={taskForm.source}
                                    onChange={(e) => setTaskForm((f) => ({ ...f, source: e.target.value }))}
                                    helperText="Keeps manual, GitHub, generated, and decomposed work distinguishable."
                                >
                                    <MenuItem value="manual">Manual</MenuItem>
                                    <MenuItem value="github">GitHub</MenuItem>
                                    <MenuItem value="generated_by_manager">Generated by manager</MenuItem>
                                    <MenuItem value="decompose">Generated from parent task</MenuItem>
                                    <MenuItem value="webhook">Webhook / incident</MenuItem>
                                </TextField>
                                <TextField
                                    fullWidth
                                    label="Task type"
                                    value={taskForm.task_type}
                                    onChange={(e) => setTaskForm((f) => ({ ...f, task_type: e.target.value }))}
                                    placeholder="bug, feature, review, incident, documentation"
                                />
                                <TextField
                                    select
                                    fullWidth
                                    label="Initial status"
                                    value={taskForm.status}
                                    onChange={(e) => setTaskForm((f) => ({ ...f, status: e.target.value }))}
                                    helperText="Matches the Work board stages."
                                >
                                    {MAIN_KANBAN_COLUMNS.map((column) => (
                                        <MenuItem key={column.status} value={column.status}>
                                            {column.label}
                                        </MenuItem>
                                    ))}
                                </TextField>
                                <TextField
                                    select
                                    fullWidth
                                    SelectProps={{ multiple: true }}
                                    label="Blocked by"
                                    value={taskForm.dependency_ids}
                                    onChange={(e) => {
                                        const nextValue = e.target.value;
                                        setTaskForm((f) => ({
                                            ...f,
                                            dependency_ids: Array.isArray(nextValue) ? nextValue : String(nextValue).split(",").filter(Boolean),
                                        }));
                                    }}
                                    helperText="Dependencies appear on cards and gate execution."
                                >
                                    {tasks.map((task) => <MenuItem key={`create-dep-${task.id}`} value={task.id}>{task.title} · {humanizeKey(task.status)}</MenuItem>)}
                                </TextField>
                                <TextField
                                    select
                                    fullWidth
                                    label="Reviewer agent"
                                    value={effectiveTaskReviewerId}
                                    onChange={(e) => {
                                        setTaskReviewerTouched(true);
                                        setTaskForm((f) => ({ ...f, reviewer_agent_id: e.target.value }));
                                    }}
                                >
                                    <MenuItem value="">None</MenuItem>
                                    {projectAgentProfiles.map((agent) => <MenuItem key={`reviewer-create-${agent.id}`} value={agent.id}>{agent.name}</MenuItem>)}
                                </TextField>
                                 <Box>
                                     <Typography variant="subtitle2" sx={{ mb: 1 }}>Acceptance Criteria</Typography>
                                     <Stack spacing={1} sx={{ mb: 1.5 }}>
                                         {taskCriteriaList.length === 0 ? (
                                             <Typography variant="caption" color="text.secondary">
                                                 No criteria added yet.
                                             </Typography>
                                         ) : (
                                             taskCriteriaList.map((criterion, index) => (
                                                 <Paper
                                                     key={index}
                                                     variant="outlined"
                                                     sx={{
                                                         p: 1.5,
                                                         borderRadius: 1,
                                                         display: "flex",
                                                         alignItems: "center",
                                                         gap: 1,
                                                     }}
                                                 >
                                                     <Checkbox
                                                         size="small"
                                                         checked={false}
                                                         disabled
                                                         sx={{ ml: -0.5 }}
                                                     />
                                                     <TextField
                                                         size="small"
                                                         fullWidth
                                                         value={criterion}
                                                         onChange={(e) => {
                                                             const newList = [...taskCriteriaList];
                                                             newList[index] = e.target.value;
                                                             setTaskCriteriaList(newList);
                                                         }}
                                                         placeholder="Enter criterion"
                                                         variant="standard"
                                                     />
                                                     <IconButton
                                                         size="small"
                                                         onClick={() => {
                                                             setTaskCriteriaList(taskCriteriaList.filter((_, i) => i !== index));
                                                         }}
                                                         sx={{ color: "error.main" }}
                                                     >
                                                         <CloseIcon fontSize="small" />
                                                     </IconButton>
                                                 </Paper>
                                             ))
                                         )}
                                     </Stack>
                                     <Button
                                         size="small"
                                         variant="outlined"
                                         onClick={() => setTaskCriteriaList([...taskCriteriaList, ""])}
                                     >
                                         Add criteria
                                     </Button>
                                 </Box>
                                <TextField
                                    fullWidth
                                    label="Response SLA (hours)"
                                    helperText="Optional. Counted from task creation if no due date; otherwise earliest of due date vs created + hours."
                                    value={taskForm.response_sla_hours}
                                    onChange={(e) => setTaskForm((f) => ({ ...f, response_sla_hours: e.target.value }))}
                                    type="number"
                                />
                                <TextField
                                    fullWidth
                                    label="Required tools"
                                    value={taskForm.required_tools}
                                    onChange={(e) => setTaskForm((f) => ({ ...f, required_tools: e.target.value }))}
                                    helperText="Comma-separated runtime tools, e.g. fs_read, code_execute, github_comment."
                                />
                            </Stack>
                        </Collapse>

                        <Divider />

                        <Button
                            variant="contained"
                            disabled={!taskForm.title.trim() || createTaskMutation.isPending}
                            onClick={() => {
                                const acceptanceCriteriaText = taskCriteriaList
                                    .filter((c) => c.trim())
                                    .map((c) => `- ${c.trim()}`)
                                    .join("\n");
                                createTaskMutation.mutate({
                                    ...normalizeProjectTaskDraft(taskForm),
                                    acceptance_criteria: acceptanceCriteriaText || null,
                                    assigned_agent_id: effectiveTaskOwnerId || null,
                                    reviewer_agent_id: effectiveTaskReviewerId || null,
                                });
                            }}
                        >
                            Save
                        </Button>
                        {createTaskMutation.isError && <Alert severity="error">Couldn't create task. Check fields and try again.</Alert>}
                    </Stack>
                </Box>
            </Drawer>

            {/* ── DAG ── */}
            {tab === "board" && workView === "dependencies" && (
                <Stack spacing={2}>
                    <SectionCard
                        title="Parallel DAG execution"
                        description="Start a run for every task whose dependencies are satisfied (backlog or planned, no active run). Celery executes runs concurrently. Use merge when several subtasks under one parent finished with different assignees."
                    >
                        <Stack spacing={1.5}>
                            <Typography variant="body2" color="text.secondary">
                                Ready now: {dagReadyList.length} task{dagReadyList.length === 1 ? "" : "s"}
                            </Typography>
                            {dagParallelMutation.data?.messages?.length ? (
                                <Alert severity="info">
                                    {dagParallelMutation.data.messages.slice(0, 4).join(" · ")}
                                </Alert>
                            ) : null}
                            <Button
                                variant="contained"
                                disabled={dagParallelMutation.isPending || dagReadyList.length === 0}
                                onClick={() => dagParallelMutation.mutate()}
                            >
                                Start parallel runs for ready tasks
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Task dependency graph" description="Nodes represent tasks; click a node to edit dependencies, inspect downstream impact, and run or merge work. Arrows point from dependency → dependent. Drag tasks on the board tab to change status.">
                        {dagReadyList.length > 0 ? (
                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
                                {dagReadyList.slice(0, 8).map((task) => (
                                    <Chip key={task.id} label={`Ready: ${task.title}`} size="small" color="info" variant="outlined" />
                                ))}
                            </Stack>
                        ) : null}
                        <Suspense fallback={<PageSkeleton variant="inspector" />}>
                            <DagView
                                tasks={tasks}
                                selectedDagTaskId={dagDrawerTaskId}
                                onSelectTask={(id) => setDagDrawerTaskId(id)}
                            />
                        </Suspense>
                    </SectionCard>
                </Stack>
            )}

            {/* ── Agents / Settings (execution) ── */}
            {(tab === "agents" || (tab === "settings" && knowledgeView !== "integrations")) && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: tab === "agents" ? "340px minmax(0, 1fr)" : "1fr" } }}>
                    <SectionCard title="Assign agent" sx={{ display: tab === "agents" ? "block" : "none" }}>
                        <Stack spacing={2}>
                            <TextField select label="Agent" value={selectedAgentId} onChange={(e) => setSelectedAgentId(e.target.value)}>
                                {availableAgents.length > 0 ? <ListSubheader>Existing agents</ListSubheader> : null}
                                {availableAgents.map((agent) => (
                                    <MenuItem key={agent.id} value={`agent:${agent.id}`}>{agent.name}</MenuItem>
                                ))}
                                {assignableTemplates.length > 0 ? <ListSubheader>Agent templates</ListSubheader> : null}
                                {assignableTemplates.map((template) => (
                                    <MenuItem key={`tpl-${template.slug}`} value={`template:${template.slug}`}>
                                        {template.name} (template)
                                    </MenuItem>
                                ))}
                            </TextField>
                            <Stack direction="row" spacing={1}>
                                <Button variant="contained" onClick={() => addAgentMutation.mutate({ selection: selectedAgentId })} disabled={!selectedAgentId}>
                                    Add agent
                                </Button>
                                <Button
                                    variant="outlined"
                                    color="error"
                                    onClick={() => deleteAgentMutation.mutate(selectedAgentId)}
                                    disabled={!selectedAgentId || deleteAgentMutation.isPending || !selectedAgentId.startsWith("agent:")}
                                >
                                    Delete selected
                                </Button>
                            </Stack>
                        </Stack>
                    </SectionCard>
                    <Stack spacing={2}>
                        <SectionCard title="Project team" sx={{ display: tab === "agents" ? "block" : "none" }}>
                            <Stack spacing={1.5}>
                                {projectAgents.map((membership) => {
                                    const agent = allAgents.find((item) => item.id === membership.agent_id);
                                    return (
                                        <Paper key={membership.id} sx={{ p: 2, borderRadius: 4 }}>
                                            <Stack direction="row" justifyContent="flex-end" sx={{ mb: 1 }}>
                                                <Tooltip title="Remove from project">
                                                    <IconButton
                                                        size="small"
                                                        color="error"
                                                        onClick={() => removeMembershipMutation.mutate(membership.id)}
                                                        disabled={removeMembershipMutation.isPending}
                                                    >
                                                        <CloseIcon fontSize="small" />
                                                    </IconButton>
                                                </Tooltip>
                                            </Stack>
                                            <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ xs: "stretch", md: "center" }}>
                                                <Box sx={{ flex: 1 }}>
                                                    <Typography variant="subtitle2">{agent?.name || membership.agent_id}</Typography>
                                                    <Typography variant="body2" color="text.secondary">{agent?.slug || membership.agent_id}</Typography>
                                                </Box>
                                                <TextField
                                                    select
                                                    size="small"
                                                    label="Role"
                                                    value={membership.role}
                                                    onChange={(event) => updateMembershipMutation.mutate({
                                                        membershipId: membership.id,
                                                        payload: { role: event.target.value },
                                                    })}
                                                    sx={{ minWidth: 170 }}
                                                >
                                                    <MenuItem value="member">Member</MenuItem>
                                                    <MenuItem value="manager">Manager</MenuItem>
                                                    <MenuItem value="reviewer">Reviewer</MenuItem>
                                                    <MenuItem value="moderator">Moderator</MenuItem>
                                                </TextField>
                                                <TextField
                                                    select
                                                    size="small"
                                                    label="Reports to"
                                                    value={agent?.parent_agent_id ?? ""}
                                                    onChange={(event) => updateHierarchyAgentMutation.mutate({
                                                        agentId: membership.agent_id,
                                                        payload: { parent_agent_id: event.target.value || null },
                                                    })}
                                                    sx={{ minWidth: 180 }}
                                                >
                                                    <MenuItem value="">None</MenuItem>
                                                    {projectAgentProfiles.filter((item) => item.id !== membership.agent_id).map((candidate) => (
                                                        <MenuItem key={`parent-${candidate.id}`} value={candidate.id}>{candidate.name}</MenuItem>
                                                    ))}
                                                </TextField>
                                                <TextField
                                                    select
                                                    size="small"
                                                    label="Reviewer"
                                                    value={agent?.reviewer_agent_id ?? ""}
                                                    onChange={(event) => updateHierarchyAgentMutation.mutate({
                                                        agentId: membership.agent_id,
                                                        payload: { reviewer_agent_id: event.target.value || null },
                                                    })}
                                                    sx={{ minWidth: 180 }}
                                                >
                                                    <MenuItem value="">None</MenuItem>
                                                    {projectAgentProfiles.filter((item) => item.id !== membership.agent_id).map((candidate) => (
                                                        <MenuItem key={`reviewer-${candidate.id}`} value={candidate.id}>{candidate.name}</MenuItem>
                                                    ))}
                                                </TextField>
                                                <Button
                                                    size="small"
                                                    variant={membership.is_default_manager ? "contained" : "outlined"}
                                                    onClick={() => updateMembershipMutation.mutate({
                                                        membershipId: membership.id,
                                                        payload: { is_default_manager: !membership.is_default_manager },
                                                    })}
                                                >
                                                    {membership.is_default_manager ? "Default manager" : "Make manager"}
                                                </Button>
                                            </Stack>
                                        </Paper>
                                    );
                                })}
                            </Stack>
                        </SectionCard>
                        <SectionCard title="Execution settings" sx={{ display: tab === "settings" ? "block" : "none" }}>
                            <Stack spacing={2}>
                                <TextField
                                    select
                                    label="Manager agent"
                                    value={resolvedProjectTeamSettings.manager_agent_id}
                                    onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), manager_agent_id: event.target.value }))}
                                >
                                    <MenuItem value="">None</MenuItem>
                                    {projectAgents.map((membership) => {
                                        const agent = allAgents.find((item) => item.id === membership.agent_id);
                                        return <MenuItem key={membership.id} value={membership.agent_id}>{agent?.name || membership.agent_id}</MenuItem>;
                                    })}
                                </TextField>
                                <TextField
                                    select
                                    SelectProps={{ multiple: true }}
                                    label="Reviewer chain"
                                    value={resolvedProjectTeamSettings.reviewer_agent_ids}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        reviewer_agent_ids: typeof event.target.value === "string" ? [event.target.value] : event.target.value,
                                    }))}
                                    helperText="Ordered reviewer roles. Each approval hands off to the next reviewer before the task is finally approved."
                                >
                                    {projectAgents.filter((membership) => ["reviewer", "manager", "team_lead"].includes(membership.role)).map((membership) => {
                                        const agent = allAgents.find((item) => item.id === membership.agent_id);
                                        return <MenuItem key={`reviewer-${membership.id}`} value={membership.agent_id}>{agent?.name || membership.agent_id}</MenuItem>;
                                    })}
                                </TextField>
                                {projectAgents.every((membership) => membership.role !== "reviewer") ? (
                                    <Alert severity="warning">
                                        This project has no reviewer role. Add a reviewer agent before saving the hierarchy.
                                    </Alert>
                                ) : null}
                                <TextField
                                    select
                                    label="Reviewer chain mode"
                                    value={resolvedProjectTeamSettings.reviewer_chain_mode}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        reviewer_chain_mode: event.target.value,
                                    }))}
                                >
                                    <MenuItem value="sequential">Sequential</MenuItem>
                                </TextField>
                                <TextField
                                    select
                                    label="Autonomy level"
                                    value={resolvedProjectTeamSettings.autonomy_level}
                                    onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), autonomy_level: event.target.value }))}
                                >
                                    <MenuItem value="assisted">Assisted</MenuItem>
                                    <MenuItem value="semi-autonomous">Semi-autonomous</MenuItem>
                                    <MenuItem value="autonomous">Autonomous</MenuItem>
                                </TextField>
                                <TextField
                                    select
                                    label="Provider override"
                                    value={resolvedProjectTeamSettings.provider_config_id}
                                    onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), provider_config_id: event.target.value }))}
                                >
                                    <MenuItem value="">Project default</MenuItem>
                                    {providerOptions.map((provider) => (
                                        <MenuItem key={provider.id} value={provider.id}>{provider.name} · {provider.default_model}</MenuItem>
                                    ))}
                                </TextField>
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField
                                        label="Model override"
                                        value={resolvedProjectTeamSettings.model_name}
                                        onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), model_name: event.target.value }))}
                                        fullWidth
                                    />
                                    <TextField
                                        label="Fallback model"
                                        value={resolvedProjectTeamSettings.fallback_model}
                                        onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), fallback_model: event.target.value }))}
                                        fullWidth
                                    />
                                </Stack>
                                <Divider />
                                <Typography variant="subtitle2">Worker routing</Typography>
                                <Typography variant="body2" color="text.secondary">
                                    Auto-assignment can optimize for capability match, deadlines, provider health, cost, or explicit pinning. User-pinned workers still win over auto-selection.
                                </Typography>
                                <TextField
                                    select
                                    label="Routing mode"
                                    value={resolvedProjectTeamSettings.routing_mode}
                                    onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), routing_mode: event.target.value }))}
                                    helperText="Matches the Stage 2 routing modes. Pinned workers still override automatic routing."
                                >
                                    <MenuItem value="capability_based">Capability-based</MenuItem>
                                    <MenuItem value="priority_sla">Priority / SLA aware</MenuItem>
                                    <MenuItem value="cost_aware">Cost-aware</MenuItem>
                                    <MenuItem value="model_availability">Model availability</MenuItem>
                                    <MenuItem value="user_pinned">User-pinned fallback mode</MenuItem>
                                    <MenuItem value="throughput">Throughput</MenuItem>
                                </TextField>
                                <TextField
                                    select
                                    label="Sibling load balance"
                                    value={resolvedProjectTeamSettings.sibling_load_balance}
                                    onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), sibling_load_balance: event.target.value }))}
                                    helperText="Among tied workers under the same manager, round_robin spreads work deterministically per task."
                                >
                                    <MenuItem value="queue_depth">Queue depth first</MenuItem>
                                    <MenuItem value="round_robin">Round robin among siblings</MenuItem>
                                </TextField>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Switch
                                        checked={resolvedProjectTeamSettings.skip_unhealthy_worker_providers}
                                        onChange={(_, checked) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            skip_unhealthy_worker_providers: checked,
                                        }))}
                                    />
                                    <Typography variant="body2">Deprioritize workers whose provider failed the last health check</Typography>
                                </Stack>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Switch
                                        checked={resolvedProjectTeamSettings.offline_local_only_mode}
                                        onChange={(_, checked) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            offline_local_only_mode: checked,
                                        }))}
                                    />
                                    <Typography variant="body2">Offline/local-only mode (restrict execution to local providers)</Typography>
                                </Stack>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Switch
                                        checked={resolvedProjectTeamSettings.enforce_project_model_policy}
                                        onChange={(_, checked) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            enforce_project_model_policy: checked,
                                        }))}
                                    />
                                    <Typography variant="body2">Enforce project model policy allowlists</Typography>
                                </Stack>
                                <TextField
                                    label="Allowed provider types (CSV)"
                                    value={resolvedProjectTeamSettings.allowed_provider_types_csv}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        allowed_provider_types_csv: event.target.value,
                                    }))}
                                    helperText="Example: openai, openai_compatible, ollama"
                                />
                                <TextField
                                    label="Allowed model slugs (CSV)"
                                    value={resolvedProjectTeamSettings.allowed_model_slugs_csv}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        allowed_model_slugs_csv: event.target.value,
                                    }))}
                                    helperText="Optional strict allowlist for model names."
                                />
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Stack spacing={1.25}>
                                        <Typography variant="subtitle2">Policy routing preview</Typography>
                                        <Typography variant="body2" color="text.secondary">
                                            Simulate routing for a sample task before starting a run.
                                        </Typography>
                                        <Stack direction={{ xs: "column", md: "row" }} spacing={1.25}>
                                            <TextField
                                                select
                                                label="Sample priority"
                                                value={policyPreviewForm.priority}
                                                onChange={(event) => setPolicyPreviewForm((current) => ({ ...current, priority: event.target.value }))}
                                                fullWidth
                                            >
                                                <MenuItem value="low">low</MenuItem>
                                                <MenuItem value="normal">normal</MenuItem>
                                                <MenuItem value="high">high</MenuItem>
                                                <MenuItem value="urgent">urgent</MenuItem>
                                            </TextField>
                                            <TextField
                                                label="Sample task type"
                                                value={policyPreviewForm.taskType}
                                                onChange={(event) => setPolicyPreviewForm((current) => ({ ...current, taskType: event.target.value }))}
                                                fullWidth
                                            />
                                        </Stack>
                                        <TextField
                                            label="Sample labels (CSV)"
                                            value={policyPreviewForm.labelsCsv}
                                            onChange={(event) => setPolicyPreviewForm((current) => ({ ...current, labelsCsv: event.target.value }))}
                                        />
                                        <Stack direction="row" alignItems="center" spacing={1}>
                                            <Switch
                                                checked={policyPreviewForm.projectSensitive}
                                                onChange={(_, checked) => setPolicyPreviewForm((current) => ({ ...current, projectSensitive: checked }))}
                                            />
                                            <Typography variant="body2">Project is sensitive</Typography>
                                        </Stack>
                                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                            <Chip
                                                size="small"
                                                color={policyRoutingPreview.routeKey ? "info" : "default"}
                                                label={
                                                    policyRoutingPreview.routeKey
                                                        ? `Matched route: ${policyRoutingPreview.routeKey}`
                                                        : "No matching route rule"
                                                }
                                            />
                                            <Chip size="small" color="success" label={`Model: ${policyRoutingPreview.selectedModel}`} />
                                            <Chip size="small" variant="outlined" label={`Provider: ${policyRoutingPreview.selectedProviderName}`} />
                                        </Stack>
                                    </Stack>
                                </Paper>
                                <Divider />
                                <Typography variant="subtitle2">Task SLA (deadline scan)</Typography>
                                <Typography variant="body2" color="text.secondary">
                                    Background job flags tasks approaching deadline and opens approvals when past due (plus grace hours). Uses each task due_date and/or response SLA hours from task creation.
                                </Typography>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Switch
                                        checked={resolvedProjectTeamSettings.sla_enabled}
                                        onChange={(_, checked) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            sla_enabled: checked,
                                        }))}
                                    />
                                    <Typography variant="body2">Enable SLA deadline scan</Typography>
                                </Stack>
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField
                                        label="Warn within (hours before due)"
                                        value={resolvedProjectTeamSettings.sla_warn_hours}
                                        onChange={(event) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            sla_warn_hours: event.target.value,
                                        }))}
                                        fullWidth
                                    />
                                    <TextField
                                        label="Escalate after due (hours)"
                                        value={resolvedProjectTeamSettings.sla_escalate_after_due_hours}
                                        onChange={(event) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            sla_escalate_after_due_hours: event.target.value,
                                        }))}
                                        helperText="0 = escalate as soon as the effective deadline passes."
                                        fullWidth
                                    />
                                </Stack>
                                <Divider />
                                <Typography variant="subtitle2">Escalation rules</Typography>
                                <TextField
                                    select
                                    label="Escalation target"
                                    value={resolvedProjectTeamSettings.escalation_target_agent_id}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        escalation_target_agent_id: event.target.value,
                                    }))}
                                    helperText="Default recipient for rule-based escalations."
                                >
                                    <MenuItem value="">Project manager</MenuItem>
                                    {projectAgents.map((membership) => {
                                        const agent = allAgents.find((item) => item.id === membership.agent_id);
                                        return <MenuItem key={`escalate-${membership.id}`} value={membership.agent_id}>{agent?.name || membership.agent_id}</MenuItem>;
                                    })}
                                </TextField>
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField
                                        label="Stuck for minutes"
                                        value={resolvedProjectTeamSettings.stuck_for_minutes}
                                        onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), stuck_for_minutes: event.target.value }))}
                                        fullWidth
                                    />
                                    <TextField
                                        label="Cost exceeds USD"
                                        value={resolvedProjectTeamSettings.cost_exceeds_usd}
                                        onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), cost_exceeds_usd: event.target.value }))}
                                        fullWidth
                                    />
                                    <TextField
                                        label="No consensus after rounds"
                                        value={resolvedProjectTeamSettings.no_consensus_after_rounds}
                                        onChange={(event) => setProjectTeamSettings((current) => ({ ...(current ?? resolvedProjectTeamSettings), no_consensus_after_rounds: event.target.value }))}
                                        fullWidth
                                    />
                                </Stack>
                                <Divider />
                                <Typography variant="subtitle2">Blocked handoff</Typography>
                                <TextField
                                    select
                                    label="Blocked-task handoff mode"
                                    value={resolvedProjectTeamSettings.blocked_handoff_mode}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        blocked_handoff_mode: event.target.value,
                                    }))}
                                >
                                    <MenuItem value="escalation_path">Worker escalation path</MenuItem>
                                    <MenuItem value="configured_agent">Configured fallback agent</MenuItem>
                                    <MenuItem value="sibling_with_capacity">Sibling with capacity</MenuItem>
                                </TextField>
                                <TextField
                                    select
                                    label="Configured handoff agent"
                                    value={resolvedProjectTeamSettings.blocked_handoff_target_agent_id}
                                    onChange={(event) => setProjectTeamSettings((current) => ({
                                        ...(current ?? resolvedProjectTeamSettings),
                                        blocked_handoff_target_agent_id: event.target.value,
                                    }))}
                                    helperText="Used when blocked-task handoff mode is configured_agent."
                                >
                                    <MenuItem value="">None</MenuItem>
                                    {projectAgents.map((membership) => {
                                        const agent = allAgents.find((item) => item.id === membership.agent_id);
                                        return <MenuItem key={`handoff-${membership.id}`} value={membership.agent_id}>{agent?.name || membership.agent_id}</MenuItem>;
                                    })}
                                </TextField>
                                <Stack direction="row" alignItems="center" spacing={1}>
                                    <Switch
                                        checked={resolvedProjectTeamSettings.blocked_handoff_fallback_to_manager}
                                        onChange={(_, checked) => setProjectTeamSettings((current) => ({
                                            ...(current ?? resolvedProjectTeamSettings),
                                            blocked_handoff_fallback_to_manager: checked,
                                        }))}
                                    />
                                    <Typography variant="body2">Fall back to project manager when the selected handoff target is unavailable</Typography>
                                </Stack>
                                <Button variant="contained" onClick={saveProjectExecutionSettings} disabled={saveProjectSettingsMutation.isPending}>
                                    Save execution settings
                                </Button>
                            </Stack>
                        </SectionCard>

                        {/* ── Gate config ── */}
                        <SectionCard
                            title="Approval gates"
                            sx={{ display: tab === "settings" ? "block" : "none" }}
                        >
                            <Stack spacing={2}>
                                <TextField
                                    select
                                    label="Autonomy level"
                                    value={gateConfig?.autonomy_level ?? "assisted"}
                                    onChange={(e) => updateGateConfigMutation.mutate({ autonomy_level: e.target.value })}
                                    disabled={updateGateConfigMutation.isPending}
                                    helperText={
                                        gateConfig?.autonomy_level === "autonomous"
                                            ? "Low-risk work may proceed automatically; protected actions always require human approval."
                                            : "Agent actions in the list below will pause for your review."
                                    }
                                >
                                    <MenuItem value="assisted">Assisted — protected actions gated</MenuItem>
                                    <MenuItem value="semi-autonomous">Semi-autonomous — protected actions gated</MenuItem>
                                    <MenuItem value="autonomous">Autonomous — protected actions gated</MenuItem>
                                </TextField>
                                <>
                                    <Alert severity="info" sx={{ py: 0.5 }}>
                                        GitHub writes, ownership changes, completion, shared memory, expensive models, and dangerous tools remain protected in every autonomy mode.
                                    </Alert>
                                    <Typography variant="subtitle2" color="text.secondary">
                                        Gated actions
                                    </Typography>
                                    {([
                                            { key: "post_to_github", label: "Post to GitHub", description: "Post comments or results to a GitHub issue" },
                                            { key: "open_pr", label: "Open pull request", description: "Create a PR from generated code" },
                                            { key: "mark_complete", label: "Mark complete", description: "Transition a task to completed status" },
                                            { key: "change_task_ownership", label: "Change task ownership", description: "Reassign task assignee/owner" },
                                            { key: "write_memory", label: "Write to memory", description: "Persist information to project memory" },
                                            { key: "use_expensive_model", label: "Use expensive model", description: "Switch to a higher-cost model mid-run" },
                                            { key: "run_tool", label: "Run external tool", description: "Execute code or call an external tool" },
                                        ] as const).map(({ key, label, description }) => {
                                            const isGated = gateConfig?.approval_gates.includes(key) ?? true;
                                            const isMandatory = gateConfig?.mandatory_approval_gates?.includes(key) ?? true;
                                            return (
                                                <Paper key={key} sx={{ p: 1.5, borderRadius: 1, border: 1, borderColor: "divider" }}>
                                                    <FormControlLabel
                                                        sx={{ m: 0, width: "100%", justifyContent: "space-between" }}
                                                        labelPlacement="start"
                                                        control={
                                                            <Switch
                                                                checked={isGated}
                                                                disabled={updateGateConfigMutation.isPending || isMandatory}
                                                                onChange={(e) => {
                                                                    const current = gateConfig?.approval_gates ?? [];
                                                                    const next = e.target.checked
                                                                        ? [...current, key]
                                                                        : current.filter((g) => g !== key);
                                                                    updateGateConfigMutation.mutate({ approval_gates: next });
                                                                }}
                                                                size="small"
                                                            />
                                                        }
                                                        label={
                                                            <Box>
                                                                <Typography variant="subtitle2">{label}</Typography>
                                                                <Typography variant="caption" color="text.secondary">{description}</Typography>
                                                            </Box>
                                                        }
                                                    />
                                                    </Paper>
                                            );
                                        })}
                                </>
                            </Stack>
                        </SectionCard>
                    </Stack>
                </Box>
            )}

            {/* ── Brainstorms ── */}
            {tab === "board" && workView === "brainstorms" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "340px minmax(0, 1fr)" } }}>
                    <SectionCard title="Start brainstorm">
                        <Stack spacing={2}>
                            <TextField label="Topic" value={brainstormForm.topic} onChange={(e) => setBrainstormForm((current) => ({ ...current, topic: e.target.value }))} />
                            <TextField
                                select
                                label="Linked task"
                                value={brainstormForm.task_id}
                                onChange={(e) => setBrainstormForm((current) => ({ ...current, task_id: e.target.value }))}
                                helperText="Optional. Use this when the brainstorm should directly support a task."
                            >
                                <MenuItem value="">None</MenuItem>
                                {tasks.map((task) => (
                                    <MenuItem key={task.id} value={task.id}>{task.title}</MenuItem>
                                ))}
                            </TextField>
                            <TextField
                                select
                                label="Moderator"
                                value={brainstormForm.moderator_agent_id}
                                onChange={(e) => setBrainstormForm((current) => ({ ...current, moderator_agent_id: e.target.value }))}
                                helperText="Leave empty to use the project manager automatically."
                            >
                                <MenuItem value="">Auto-select project manager</MenuItem>
                                {projectAgentProfiles.map((agent) => (
                                    <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>
                                ))}
                            </TextField>
                            <TextField
                                select
                                SelectProps={{ multiple: true }}
                                label="Participants"
                                value={brainstormForm.participant_agent_ids}
                                onChange={(e) => {
                                    const nextValue = e.target.value;
                                    setBrainstormForm((current) => ({
                                        ...current,
                                        participant_agent_ids: Array.isArray(nextValue) ? nextValue : String(nextValue).split(",").filter(Boolean),
                                    }));
                                }}
                                helperText="At least two agents are required."
                            >
                                {projectAgentProfiles.map((agent) => (
                                    <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>
                                ))}
                            </TextField>
                            {brainstormParticipantProfiles.length > 0 ? (
                                <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                    {brainstormParticipantProfiles.map((agent) => (
                                        <Chip key={agent.id} label={agent.name} size="small" variant="outlined" />
                                    ))}
                                </Stack>
                            ) : null}
                            <TextField
                                select
                                label="Mode"
                                value={brainstormForm.mode}
                                onChange={(e) => {
                                    const mode = e.target.value;
                                    setBrainstormForm((current) => ({
                                        ...current,
                                        mode,
                                        output_type: current.output_type === brainstormSuggestedOutput ? mode === "code_review" ? "test_plan" : mode === "incident_triage" || mode === "root_cause" ? "risk_register" : mode === "architecture_proposal" ? "adr" : "implementation_plan" : current.output_type,
                                    }));
                                }}
                            >
                                {BRAINSTORM_MODE_OPTIONS.map((option) => (
                                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                                ))}
                            </TextField>
                            <TextField
                                select
                                label="Output"
                                value={brainstormForm.output_type}
                                onChange={(e) => setBrainstormForm((current) => ({ ...current, output_type: e.target.value }))}
                                helperText={`Recommended for this mode: ${humanizeKey(brainstormSuggestedOutput)}`}
                            >
                                {BRAINSTORM_OUTPUT_OPTIONS.map((option) => (
                                    <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                                ))}
                            </TextField>
                            <Button variant="text" endIcon={brainstormAdvancedOpen ? <ExpandLessIcon /> : <ExpandMoreIcon />} onClick={() => setBrainstormAdvancedOpen((open) => !open)}>
                                Advanced
                            </Button>
                            <Collapse in={brainstormAdvancedOpen}>
                                <Stack spacing={1.5}>
                                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                        <TextField label="Max rounds" type="number" value={brainstormForm.max_rounds} onChange={(e) => setBrainstormForm((current) => ({ ...current, max_rounds: e.target.value }))} fullWidth />
                                        <TextField label="Cost cap (USD)" type="number" value={brainstormForm.max_cost_usd} onChange={(e) => setBrainstormForm((current) => ({ ...current, max_cost_usd: e.target.value }))} fullWidth />
                                    </Stack>
                                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                        <TextField label="Loop threshold" type="number" value={brainstormForm.max_repetition_score} onChange={(e) => setBrainstormForm((current) => ({ ...current, max_repetition_score: e.target.value }))} fullWidth />
                                        <TextField label="Soft consensus similarity" type="number" value={brainstormForm.soft_consensus_min_similarity} onChange={(e) => setBrainstormForm((current) => ({ ...current, soft_consensus_min_similarity: e.target.value }))} fullWidth />
                                    </Stack>
                                    <TextField label="Conflict similarity ceiling" type="number" value={brainstormForm.conflict_pairwise_max_similarity} onChange={(e) => setBrainstormForm((current) => ({ ...current, conflict_pairwise_max_similarity: e.target.value }))} />
                                    <FormControlLabel
                                        control={<Switch checked={brainstormForm.stop_on_consensus} onChange={(_, checked) => setBrainstormForm((current) => ({ ...current, stop_on_consensus: checked }))} />}
                                        label="Stop when consensus is reached"
                                    />
                                    <FormControlLabel
                                        control={<Switch checked={brainstormForm.accept_soft_consensus} onChange={(_, checked) => setBrainstormForm((current) => ({ ...current, accept_soft_consensus: checked }))} />}
                                        label="Accept soft consensus"
                                    />
                                    <FormControlLabel
                                        control={<Switch checked={brainstormForm.escalate_on_no_consensus} onChange={(_, checked) => setBrainstormForm((current) => ({ ...current, escalate_on_no_consensus: checked }))} />}
                                        label="Escalate if no consensus after the final round"
                                    />
                                </Stack>
                            </Collapse>
                            <Button
                                variant="contained"
                                disabled={!brainstormForm.topic.trim() || brainstormForm.participant_agent_ids.length < 2}
                                onClick={() =>
                                    brainstormMutation.mutate({
                                        project_id: projectId,
                                        task_id: brainstormForm.task_id || null,
                                        moderator_agent_id: brainstormForm.moderator_agent_id || null,
                                        topic: brainstormForm.topic,
                                        participant_agent_ids: brainstormForm.participant_agent_ids,
                                        mode: brainstormForm.mode,
                                        output_type: brainstormForm.output_type,
                                        max_rounds: Number(brainstormForm.max_rounds || 3),
                                        max_cost_usd: Number(brainstormForm.max_cost_usd || 10),
                                        max_repetition_score: Number(brainstormForm.max_repetition_score || 0.92),
                                        stop_conditions: {
                                            stop_on_consensus: brainstormForm.stop_on_consensus,
                                            accept_soft_consensus: brainstormForm.accept_soft_consensus,
                                            escalate_on_no_consensus: brainstormForm.escalate_on_no_consensus,
                                            soft_consensus_min_similarity: Number(brainstormForm.soft_consensus_min_similarity || 0.72),
                                            conflict_pairwise_max_similarity: Number(brainstormForm.conflict_pairwise_max_similarity || 0.38),
                                        },
                                    })
                                }
                            >
                                Launch brainstorm
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Brainstorms">
                        <Stack spacing={1.5}>
                            {brainstorms.map((brainstorm) => (
                                <Paper key={brainstorm.id} sx={{ p: 2, borderRadius: 4 }}>
                                    <Stack spacing={1.25}>
                                        <Box>
                                            <Typography variant="subtitle2">{brainstorm.topic}</Typography>
                                            <Typography variant="body2" color="text.secondary">{brainstorm.summary || brainstorm.final_recommendation || "Run pending or no summary yet."}</Typography>
                                        </Box>
                                        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                            <Chip label={humanizeKey(brainstorm.status)} size="small" />
                                            <Chip label={humanizeKey(brainstorm.mode)} size="small" variant="outlined" />
                                            <Chip label={humanizeKey(brainstorm.output_type)} size="small" variant="outlined" />
                                            <Chip label={`Round ${brainstorm.current_round}/${brainstorm.max_rounds}`} size="small" variant="outlined" />
                                            <Chip
                                                label={humanizeKey(brainstorm.consensus_status)}
                                                size="small"
                                                color={brainstorm.consensus_status === "consensus" || brainstorm.consensus_status === "soft_consensus" ? "success" : brainstorm.consensus_status === "conflict" || brainstorm.consensus_status === "loop_detected" ? "warning" : "default"}
                                            />
                                        </Stack>
                                        <Typography variant="caption" color="text.secondary">
                                            {brainstorm.participant_count} participants • updated {formatDateTime(brainstorm.updated_at)}
                                        </Typography>
                                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                            <Button size="small" variant="text" onClick={() => navigate(`/brainstorms/${brainstorm.id}`)}>
                                                Open room
                                            </Button>
                                            {brainstorm.final_recommendation && (
                                                <Button
                                                    size="small" variant="text"
                                                    onClick={() => decisionMutation.mutate({
                                                        title: brainstorm.topic,
                                                        decision: brainstorm.final_recommendation!,
                                                        rationale: brainstorm.summary || "",
                                                        author_label: "Brainstorm",
                                                        brainstorm_id: brainstorm.id,
                                                    })}
                                                >
                                                    Promote to decision
                                                </Button>
                                            )}
                                        </Stack>
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    </SectionCard>
                </Box>
            )}

            {/* ── Decisions ── */}
            {tab === "memory" && knowledgeView === "decisions" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "380px minmax(0, 1fr)" } }}>
                    <SectionCard title="Record decision">
                        <Stack spacing={2}>
                            <TextField label="Title" value={decisionForm.title} onChange={(e) => setDecisionForm((f) => ({ ...f, title: e.target.value }))} />
                            <TextField label="Decision" multiline minRows={3} value={decisionForm.decision} onChange={(e) => setDecisionForm((f) => ({ ...f, decision: e.target.value }))} />
                            <TextField label="Rationale" multiline minRows={2} value={decisionForm.rationale} onChange={(e) => setDecisionForm((f) => ({ ...f, rationale: e.target.value }))} />
                            <TextField label="Author" value={decisionForm.author_label} onChange={(e) => setDecisionForm((f) => ({ ...f, author_label: e.target.value }))} />
                            <Button
                                variant="contained"
                                disabled={!decisionForm.title.trim() || !decisionForm.decision.trim()}
                                onClick={() => decisionMutation.mutate({ ...decisionForm })}
                            >
                                Record
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Decision log">
                        {decisions.length === 0 ? (
                            <Typography color="text.secondary">No decisions recorded yet.</Typography>
                        ) : (
                            <Stack spacing={1.5}>
                                {decisions.map((d) => (
                                    <Paper key={d.id} sx={{ p: 2, borderRadius: 4 }}>
                                        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 0.5 }}>
                                            <Typography variant="subtitle2">{d.title}</Typography>
                                            {d.author_label && <Chip label={d.author_label} size="small" variant="outlined" />}
                                            {d.brainstorm_id && <Chip label="from brainstorm" size="small" color="secondary" variant="outlined" />}
                                        </Stack>
                                        <Typography variant="body2">{d.decision}</Typography>
                                        {d.rationale && <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{d.rationale}</Typography>}
                                        <Typography variant="caption" color="text.secondary">{formatDateTime(d.created_at)}</Typography>
                                    </Paper>
                                ))}
                            </Stack>
                        )}
                    </SectionCard>
                </Box>
            )}

            {/* ── GitHub ── */}
            {tab === "settings" && knowledgeView === "integrations" && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "1fr 1fr" } }}>
                    <SectionCard title="Local repo workspace">
                        <Stack spacing={2}>
                            <Stack direction="row" alignItems="center" spacing={1}>
                                <Switch
                                    checked={resolvedLocalRepoForm.enabled}
                                    onChange={(_, checked) => setLocalRepoForm((current) => ({ ...current, enabled: checked }))}
                                />
                                <Typography variant="body2">Enable local repo for code-change tasks</Typography>
                            </Stack>
                            <TextField
                                label="Local repo path"
                                value={resolvedLocalRepoForm.repo_path}
                                onChange={(event) => setLocalRepoForm((current) => ({ ...current, repo_path: event.target.value }))}
                                helperText="Agents use this Git repo for code-change tasks."
                                fullWidth
                            />
                            <TextField
                                select
                                label="Dirty worktree policy"
                                value={resolvedLocalRepoForm.dirty_worktree_policy}
                                onChange={(event) => setLocalRepoForm((current) => ({ ...current, dirty_worktree_policy: event.target.value }))}
                                helperText="Controls agent work when uncommitted changes exist."
                                fullWidth
                            >
                                <MenuItem value="block">Block agent work</MenuItem>
                                <MenuItem value="warn">Warn on dirty worktree</MenuItem>
                                <MenuItem value="allow">Allow dirty worktree</MenuItem>
                            </TextField>
                            <TextField
                                label="Allowed branches"
                                value={resolvedLocalRepoForm.allowed_branches}
                                onChange={(event) => setLocalRepoForm((current) => ({ ...current, allowed_branches: event.target.value }))}
                                helperText="Comma-separated branch patterns agents may start from or merge into."
                                fullWidth
                            />
                            <TextField
                                label="File allowlist"
                                value={resolvedLocalRepoForm.file_allowlist}
                                onChange={(event) => setLocalRepoForm((current) => ({ ...current, file_allowlist: event.target.value }))}
                                helperText="Comma-separated glob patterns agents may read/write."
                                fullWidth
                            />
                            <TextField
                                label="File denylist"
                                value={resolvedLocalRepoForm.file_denylist}
                                onChange={(event) => setLocalRepoForm((current) => ({ ...current, file_denylist: event.target.value }))}
                                helperText="Comma-separated glob patterns always blocked."
                                fullWidth
                            />
                            <TextField
                                label="Command allowlist"
                                value={resolvedLocalRepoForm.command_allowlist}
                                onChange={(event) => setLocalRepoForm((current) => ({ ...current, command_allowlist: event.target.value }))}
                                helperText="Comma-separated executable names allowed via code execution."
                                fullWidth
                            />
                            <TextField
                                label="Max diff bytes"
                                type="number"
                                value={resolvedLocalRepoForm.max_diff_bytes}
                                onChange={(event) => setLocalRepoForm((current) => ({ ...current, max_diff_bytes: event.target.value }))}
                                inputProps={{ min: 1000, max: 5000000 }}
                                helperText="Allowed range: 1,000 to 5,000,000 bytes."
                                fullWidth
                            />
                            {saveLocalRepoSettingsMutation.isError ? (
                                <Alert severity="error">
                                    {saveLocalRepoSettingsMutation.error instanceof Error
                                        ? saveLocalRepoSettingsMutation.error.message
                                        : "Could not save local repo settings."}
                                </Alert>
                            ) : null}
                            <Button
                                variant="contained"
                                disabled={saveLocalRepoSettingsMutation.isPending || (resolvedLocalRepoForm.enabled && !resolvedLocalRepoForm.repo_path.trim())}
                                onClick={() => saveLocalRepoSettingsMutation.mutate()}
                            >
                                Save local repo
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard title="GitHub integration">
                        <Stack spacing={2}>
                            <TextField
                                label="Branch name template"
                                size="small"
                                fullWidth
                                value={resolvedGithubForm.branch_prefix}
                                onChange={(e) => setGithubForm((f) => ({ ...f, branch_prefix: e.target.value }))}
                                helperText="Placeholders: {task_id}, {slug} (from task title). Used when generating PR branches."
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.enforce_branch_naming}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, enforce_branch_naming: checked }))}
                                    />
                                )}
                                label="Enforce branch naming convention on GitHub PR open events"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.auto_post_progress}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, auto_post_progress: checked }))}
                                    />
                                )}
                                label="Draft agent progress notes for approval when runs complete"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.auto_activate_review_on_pr_open}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, auto_activate_review_on_pr_open: checked }))}
                                    />
                                )}
                                label="Queue a Troop review run as soon as a GitHub PR opens"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.auto_review_on_pr_review}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, auto_review_on_pr_review: checked }))}
                                    />
                                )}
                                label="Queue a Troop review run when a GitHub PR review is submitted"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.close_issue_with_manager_summary}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, close_issue_with_manager_summary: checked }))}
                                    />
                                )}
                                label="Draft a manager-authored issue closure summary for approval on managed runs"
                            />
                            <Divider />
                            <Typography variant="subtitle2">Bidirectional sync</Typography>
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.sync_labels_to_github}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, sync_labels_to_github: checked }))}
                                    />
                                )}
                                label="Sync internal labels back to GitHub issues"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.sync_assignees_to_github}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, sync_assignees_to_github: checked }))}
                                    />
                                )}
                                label="Sync internal assignee changes back to GitHub issues"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.sync_state_to_github}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, sync_state_to_github: checked }))}
                                    />
                                )}
                                label="Sync internal task completion state back to GitHub issue state"
                            />
                            <FormControlLabel
                                control={(
                                    <Switch
                                        checked={resolvedGithubForm.sync_milestone_to_github}
                                        onChange={(_, checked) => setGithubForm((f) => ({ ...f, sync_milestone_to_github: checked }))}
                                    />
                                )}
                                label="Sync `metadata.github_milestone_number` back to GitHub issue milestone"
                            />
                            <TextField
                                label="Repo agent pools JSON"
                                size="small"
                                fullWidth
                                multiline
                                minRows={8}
                                value={resolvedGithubForm.repo_agent_pools_json}
                                onChange={(e) => setGithubForm((f) => ({ ...f, repo_agent_pools_json: e.target.value }))}
                                helperText='Map repository id or "owner/name" to routing config. Example: {"org/repo":{"worker_agent_ids":["agent-1"],"default_assignee_agent_id":"agent-1","default_reviewer_agent_id":"agent-2","github_assignee_map":{"octocat":"agent-1"}}}'
                            />
                            <Button variant="contained" onClick={saveGithubIntegration} disabled={saveProjectSettingsMutation.isPending}>
                                Save GitHub settings
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Sandbox & secret scoping">
                        <Stack spacing={2}>
                            <TextField
                                select
                                label="Sandbox execution policy"
                                size="small"
                                value={resolvedHitlForm.sandbox_mode}
                                onChange={(e) => setHitlForm((f) => ({ ...f, sandbox_mode: e.target.value }))}
                                fullWidth
                            >
                                <MenuItem value="allow_host_fallback">Allow host fallback when Docker is unavailable</MenuItem>
                                <MenuItem value="docker_required">Require Docker sandbox (block host fallback)</MenuItem>
                            </TextField>
                            <TextField
                                select
                                label="Secret scope posture"
                                size="small"
                                value={resolvedHitlForm.secret_scope}
                                onChange={(e) => setHitlForm((f) => ({ ...f, secret_scope: e.target.value }))}
                                fullWidth
                            >
                                <MenuItem value="project_default">Project default (env + provider keys)</MenuItem>
                                <MenuItem value="repo_scoped">Prefer repository-scoped tokens when available</MenuItem>
                                <MenuItem value="agent_scoped">Prefer per-agent secret slots (manual rotation)</MenuItem>
                                <MenuItem value="deny_external">Deny external network + GitHub tools</MenuItem>
                            </TextField>
                            <TextField
                                label="Sandbox / runner notes"
                                size="small"
                                multiline
                                minRows={2}
                                fullWidth
                                value={resolvedHitlForm.sandbox_note}
                                onChange={(e) => setHitlForm((f) => ({ ...f, sandbox_note: e.target.value }))}
                                placeholder="e.g. Dedicated worker queue, CPU seconds cap, egress deny list…"
                            />
                            <Button variant="outlined" onClick={saveHitlSettings} disabled={saveProjectSettingsMutation.isPending}>
                                Save HITL controls
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Imported issues">
                        <Stack spacing={1.5}>
                            {issueLinks.map((item) => (
                                <Paper key={item.id} sx={{ p: 2, borderRadius: 4 }}>
                                    <Typography variant="subtitle2">#{item.issue_number} {item.title}</Typography>
                                    <Typography variant="caption" color="text.secondary">{item.state} • {item.sync_status}</Typography>
                                </Paper>
                            ))}
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Sync events">
                        <Stack spacing={1.5}>
                            {syncEvents.map((event) => (
                                <Box key={event.id}>
                                    <Typography variant="body2">{event.action} • {event.status}</Typography>
                                    <Typography variant="caption" color="text.secondary">{event.detail || "No details"} • {formatDateTime(event.created_at)}</Typography>
                                </Box>
                            ))}
                        </Stack>
                    </SectionCard>
                </Box>
            )}

            {/* ── Knowledge base ── */}
            {tab === "memory" && (knowledgeView === "search" || knowledgeView === "sources" || knowledgeView === "memory") && (
                <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "minmax(0, 1fr) 400px" }, alignItems: "start" }}>
                    <Stack spacing={2}>
                        <SectionCard title="Sources" sx={{ display: knowledgeView === "sources" ? "block" : "none" }}>
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 2 }} alignItems={{ sm: "center" }}>
                                <TextField
                                    label="TTL days"
                                    value={documentTtlDays}
                                    onChange={(event) => setDocumentTtlDays(event.target.value)}
                                    sx={{ width: { xs: "100%", sm: 140 } }}
                                />
                                <Button variant="contained" component="label" startIcon={<UploadIcon />}>
                                    Upload document
                                    <input
                                        hidden
                                        type="file"
                                        accept=".md,.txt,.json,.yml,.yaml,.toml"
                                        onChange={(event) => {
                                            const file = event.target.files?.[0];
                                            if (file) uploadDocumentMutation.mutate(file);
                                            event.currentTarget.value = "";
                                        }}
                                    />
                                </Button>
                            </Stack>
                            {docs.length === 0 ? (
                                <Typography variant="body2" color="text.secondary">No documents yet. Upload a file to seed the knowledge base.</Typography>
                            ) : (
                                <Stack spacing={1.5}>
                                    {docs.map((doc) => (
                                        <Paper key={doc.id} sx={{ p: 2, borderRadius: 4 }}>
                                            <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                                                <Box flex={1}>
                                                    <Typography variant="subtitle2">{doc.filename}</Typography>
                                                    <Typography variant="body2" color="text.secondary">{doc.summary_text || `${doc.source_text.slice(0, 200)}…`}</Typography>
                                                </Box>
                                                <Stack direction="row" spacing={0.5} alignItems="center">
                                                    <IconButton
                                                        size="small"
                                                        aria-label="Toggle chunk preview"
                                                        onClick={() => setExpandedDocumentId((current) => (current === doc.id ? null : doc.id))}
                                                    >
                                                        {expandedDocumentId === doc.id ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                                                    </IconButton>
                                                    <Button size="small" color="error" onClick={() => deleteDocumentMutation.mutate(doc.id)}>
                                                        Remove
                                                    </Button>
                                                </Stack>
                                            </Stack>
                                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                                                <Chip size="small" variant="outlined" label={`${doc.chunk_count} chunks`} />
                                                <Chip size="small" variant="outlined" label={`${(doc.size_bytes / 1024).toFixed(1)} KB`} />
                                                <Chip size="small" variant="outlined" label={`TTL ${doc.ttl_days ?? "none"}`} />
                                                <Chip size="small" variant="outlined" label={doc.ingestion_status} />
                                            </Stack>
                                            <Collapse in={expandedDocumentId === doc.id}>
                                                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>
                                                    Source preview (chunking splits this text for embedding)
                                                </Typography>
                                                <Paper
                                                    variant="outlined"
                                                    sx={{
                                                        mt: 1,
                                                        p: 1.5,
                                                        maxHeight: 320,
                                                        overflow: "auto",
                                                        borderRadius: 1,
                                                        fontFamily: "IBM Plex Mono, monospace",
                                                        fontSize: "0.75rem",
                                                        whiteSpace: "pre-wrap",
                                                    }}
                                                >
                                                    {doc.source_text}
                                                </Paper>
                                            </Collapse>
                                        </Paper>
                                    ))}
                                </Stack>
                            )}
                        </SectionCard>
                        <SectionCard title="Connected repositories" sx={{ display: knowledgeView === "sources" ? "block" : "none" }}>
                            <Stack spacing={1.5}>
                                {repositoryIndexStatus.length === 0 && projectRepositories.length === 0 ? (
                                    <Typography variant="body2" color="text.secondary">
                                        No connected repositories yet. Link a GitHub repository on the GitHub tab to index code knowledge here.
                                    </Typography>
                                ) : (
                                    (repositoryIndexStatus.length > 0 ? repositoryIndexStatus : projectRepositories.map((repository) => ({
                                        repository_link_id: repository.id,
                                        github_repository_id: repository.github_repository_id,
                                        full_name: repository.full_name,
                                        default_branch: repository.default_branch,
                                        repository_url: repository.repository_url,
                                        index_settings: (repository.metadata.indexing as Record<string, unknown> | undefined) ?? {},
                                        indexed_files: 0,
                                        chunk_count: 0,
                                        searchable_documents: 0,
                                        last_indexed_at: null,
                                        latest_job: null,
                                        last_successful_job_id: null,
                                        pending_jobs: 0,
                                        running_jobs: 0,
                                        recent_files: [],
                                        recent_errors: [],
                                    }))).map((repository) => {
                                        const draft = repoIndexDrafts[repository.repository_link_id] ?? {
                                            scheduleLabel: String((repository.index_settings as Record<string, unknown>).schedule_label ?? ""),
                                            pathPrefixes: Array.isArray((repository.index_settings as Record<string, unknown>).path_prefixes)
                                                ? ((repository.index_settings as Record<string, unknown>).path_prefixes as string[]).join(", ")
                                                : "",
                                            autoEnabled: Boolean((repository.index_settings as Record<string, unknown>).auto_enabled),
                                        };
                                        return (
                                            <Paper key={repository.repository_link_id} sx={{ p: 2, borderRadius: 4 }}>
                                                <Stack direction={{ xs: "column", lg: "row" }} justifyContent="space-between" spacing={2}>
                                                    <Box sx={{ flex: 1 }}>
                                                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                                            <Typography variant="subtitle2">{repository.full_name}</Typography>
                                                            <Chip size="small" variant="outlined" label={repository.default_branch || "no branch"} />
                                                            <Chip size="small" color="info" variant="outlined" label={`${repository.indexed_files} files`} />
                                                            <Chip size="small" color="success" variant="outlined" label={`${repository.chunk_count} chunks`} />
                                                            {repository.latest_job ? (
                                                                <Chip size="small" color={repository.latest_job.status === "failed" ? "error" : repository.latest_job.status === "running" ? "info" : repository.latest_job.status === "pending" ? "warning" : "success"} label={`latest ${repository.latest_job.status}`} />
                                                            ) : null}
                                                        </Stack>
                                                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
                                                            {repository.last_indexed_at ? `Last indexed ${formatDateTime(repository.last_indexed_at)}` : "Not indexed yet"}
                                                            {repository.repository_url ? ` • ${repository.repository_url}` : ""}
                                                        </Typography>
                                                        <Stack direction={{ xs: "column", md: "row" }} spacing={1.25} sx={{ mt: 1.25 }}>
                                                            <TextField
                                                                size="small"
                                                                label="Schedule label"
                                                                value={draft.scheduleLabel}
                                                                onChange={(event) => setRepoIndexDrafts((current) => ({
                                                                    ...current,
                                                                    [repository.repository_link_id]: { ...draft, scheduleLabel: event.target.value },
                                                                }))}
                                                                sx={{ minWidth: 180 }}
                                                                helperText="Example: every 6h / daily / before review"
                                                            />
                                                            <TextField
                                                                size="small"
                                                                label="Incremental paths"
                                                                value={draft.pathPrefixes}
                                                                onChange={(event) => setRepoIndexDrafts((current) => ({
                                                                    ...current,
                                                                    [repository.repository_link_id]: { ...draft, pathPrefixes: event.target.value },
                                                                }))}
                                                                fullWidth
                                                                helperText="Comma-separated path prefixes for focused reindex."
                                                            />
                                                        </Stack>
                                                        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
                                                            <Switch
                                                                checked={draft.autoEnabled}
                                                                onChange={(_, checked) => setRepoIndexDrafts((current) => ({
                                                                    ...current,
                                                                    [repository.repository_link_id]: { ...draft, autoEnabled: checked },
                                                                }))}
                                                            />
                                                            <Typography variant="body2">Auto queue scheduled index for this repo</Typography>
                                                        </Stack>
                                                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1.25 }}>
                                                            <Button
                                                                size="small"
                                                                variant="contained"
                                                                onClick={() => queueRepositoryIndexMutation.mutate({
                                                                    repositoryLinkId: repository.repository_link_id,
                                                                    mode: "full",
                                                                    pathPrefixes: [],
                                                                    scheduleLabel: draft.scheduleLabel || null,
                                                                    autoEnabled: draft.autoEnabled,
                                                                })}
                                                            >
                                                                Full index
                                                            </Button>
                                                            <Button
                                                                size="small"
                                                                variant="outlined"
                                                                onClick={() => queueRepositoryIndexMutation.mutate({
                                                                    repositoryLinkId: repository.repository_link_id,
                                                                    mode: "incremental",
                                                                    pathPrefixes: draft.pathPrefixes.split(",").map((item) => item.trim()).filter(Boolean),
                                                                    scheduleLabel: draft.scheduleLabel || null,
                                                                    autoEnabled: draft.autoEnabled,
                                                                })}
                                                            >
                                                                Incremental reindex
                                                            </Button>
                                                            <Button
                                                                size="small"
                                                                onClick={() => updateRepositoryMutation.mutate({
                                                                    repositoryLinkId: repository.repository_link_id,
                                                                    metadata: {
                                                                        indexing: {
                                                                            schedule_label: draft.scheduleLabel || null,
                                                                            path_prefixes: draft.pathPrefixes.split(",").map((item) => item.trim()).filter(Boolean),
                                                                            auto_enabled: draft.autoEnabled,
                                                                        },
                                                                    },
                                                                })}
                                                            >
                                                                Save schedule
                                                            </Button>
                                                        </Stack>
                                                    </Box>
                                                    <Stack spacing={1} sx={{ width: { xs: "100%", lg: 320 } }}>
                                                        <Typography variant="caption" color="text.secondary">Recent indexed files</Typography>
                                                        {repository.recent_files.length > 0 ? repository.recent_files.slice(0, 5).map((file) => (
                                                            <Paper key={file.document_id} variant="outlined" sx={{ p: 1, borderRadius: 1 }}>
                                                                <Typography variant="body2">{file.path}</Typography>
                                                                <Typography variant="caption" color="text.secondary">
                                                                    {file.branch} • {file.chunk_count} chunks • {file.status}
                                                                </Typography>
                                                            </Paper>
                                                        )) : (
                                                            <Typography variant="body2" color="text.secondary">No indexed files yet.</Typography>
                                                        )}
                                                        {repository.recent_errors.length > 0 ? (
                                                            <>
                                                                <Typography variant="caption" color="error">Recent failures</Typography>
                                                                {repository.recent_errors.map((error) => (
                                                                    <Alert key={error.job_id} severity="error">
                                                                        {error.error_text || "Unknown indexing failure"}
                                                                    </Alert>
                                                                ))}
                                                            </>
                                                        ) : null}
                                                    </Stack>
                                                </Stack>
                                            </Paper>
                                        );
                                    })
                                )}
                            </Stack>
                        </SectionCard>
                    </Stack>
                    <SectionCard title="Memory rules" sx={{ display: knowledgeView === "memory" ? "block" : "none" }}>
                        <Stack spacing={1.25}>
                            <Stack direction="row" alignItems="center" spacing={1}>
                                <Switch
                                    checked={resolvedMemorySettings.semantic_write_requires_approval}
                                    onChange={(_, checked) =>
                                        setMemorySettingsDraft((current) => ({
                                            ...(current ?? resolvedMemorySettings),
                                            semantic_write_requires_approval: checked,
                                        }))
                                    }
                                />
                                <Typography variant="body2">Require approval before long-term semantic memory writes</Typography>
                            </Stack>
                            <Stack direction="row" alignItems="center" spacing={1}>
                                <Switch
                                    checked={resolvedMemorySettings.deep_recall_mode}
                                    onChange={(_, checked) =>
                                        setMemorySettingsDraft((current) => ({
                                            ...(current ?? resolvedMemorySettings),
                                            deep_recall_mode: checked,
                                        }))
                                    }
                                />
                                <Typography variant="body2">Enable deep recall mode for episodic retrieval</Typography>
                            </Stack>
                            <TextField
                                label="Episodic retention days"
                                value={resolvedMemorySettings.episodic_retention_days}
                                onChange={(event) =>
                                    setMemorySettingsDraft((current) => ({
                                        ...(current ?? resolvedMemorySettings),
                                        episodic_retention_days: event.target.value,
                                    }))
                                }
                                helperText="Older episodic records are archived/expired by background jobs."
                            />
                            <Button
                                variant="outlined"
                                onClick={() =>
                                    memorySettingsMutation.mutate({
                                        semantic_write_requires_approval:
                                            resolvedMemorySettings.semantic_write_requires_approval,
                                        deep_recall_mode: resolvedMemorySettings.deep_recall_mode,
                                        episodic_retention_days: Number(
                                            resolvedMemorySettings.episodic_retention_days || 90
                                        ),
                                    })
                                }
                                disabled={memorySettingsMutation.isPending}
                            >
                                Save memory rules
                            </Button>
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Ingestion jobs" sx={{ display: knowledgeView === "sources" || knowledgeView === "memory" ? "block" : "none" }}>
                        <Stack spacing={1.25}>
                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                <Chip size="small" color="warning" label={`Pending ${memoryIngestCounts.pending}`} />
                                <Chip size="small" color="info" label={`Running ${memoryIngestCounts.running}`} />
                                <Chip size="small" color="success" label={`Completed ${memoryIngestCounts.completed}`} />
                                <Chip size="small" color="error" label={`Failed ${memoryIngestCounts.failed}`} />
                            </Stack>
                            {memoryIngestJobs.slice(0, 12).map((job) => (
                                <Paper key={job.id} sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
                                        <Box>
                                            <Typography variant="body2">{job.job_type}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {formatDateTime(job.created_at)}
                                                {job.started_at ? ` • started ${formatDateTime(job.started_at)}` : ""}
                                                {job.finished_at ? ` • finished ${formatDateTime(job.finished_at)}` : ""}
                                            </Typography>
                                        </Box>
                                        <Chip size="small" label={job.status} color={job.status === "failed" ? "error" : job.status === "completed" ? "success" : job.status === "running" ? "info" : "warning"} />
                                    </Stack>
                                    {job.error_text ? (
                                        <Typography variant="caption" color="error" sx={{ display: "block", mt: 0.75, whiteSpace: "pre-wrap" }}>
                                            {job.error_text}
                                        </Typography>
                                    ) : null}
                                </Paper>
                            ))}
                            {memoryIngestJobs.length === 0 && (
                                <Typography variant="body2" color="text.secondary">
                                    No ingestion jobs yet.
                                </Typography>
                            )}
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Search" sx={{ display: knowledgeView === "search" ? "block" : "none" }}>
                        <TextField
                            label="Search knowledge"
                            value={knowledgeQuery}
                            onChange={(event) => setKnowledgeQuery(event.target.value)}
                            helperText="Matches ranked by relevance; each row is a chunk used during agent runs."
                            fullWidth
                        />
                        <Stack direction="row" alignItems="center" spacing={1} sx={{ mt: 1 }}>
                            <Switch checked={includeDecisionRecall} onChange={(_, checked) => setIncludeDecisionRecall(checked)} />
                            <Typography variant="body2">Decision recall: include project decisions ("what did we decide about X?")</Typography>
                        </Stack>
                        {debouncedKnowledgeQuery.length >= 3 && (
                            <Paper sx={{ p: 2, borderRadius: 4, mt: 2 }}>
                                <Typography variant="subtitle2">Results</Typography>
                                <Stack spacing={1.25} sx={{ mt: 1.25 }}>
                                    {knowledgeResults.length > 0 ? knowledgeResults.map((match) => (
                                        <Box key={match.chunk_id}>
                                            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                                                <Typography variant="body2">{match.filename}</Typography>
                                                <Chip size="small" label={`chunk #${match.chunk_index}`} variant="outlined" />
                                                <Chip size="small" label={`score ${match.score.toFixed(3)}`} variant="outlined" />
                                            </Stack>
                                            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "pre-wrap", display: "block", mt: 0.75 }}>
                                                {match.content}
                                            </Typography>
                                        </Box>
                                    )) : (
                                        <Typography variant="body2" color="text.secondary">No relevant chunks found.</Typography>
                                    )}
                                </Stack>
                            </Paper>
                        )}
                    </SectionCard>
                    <SectionCard title="Semantic memory" sx={{ display: knowledgeView === "memory" ? "block" : "none" }}>
                        <Stack spacing={1.25}>
                            {semanticEntries.length > 0 ? semanticEntries.map((entry) => (
                                <Paper key={entry.id} sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                                        <Typography variant="body2">{entry.title}</Typography>
                                        <Chip size="small" variant="outlined" label={entry.entry_type} />
                                        <Chip size="small" variant="outlined" label={entry.namespace} />
                                    </Stack>
                                    <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "pre-wrap", mt: 0.75, display: "block" }}>
                                        {entry.body.slice(0, 400)}
                                    </Typography>
                                </Paper>
                            )) : (
                                <Typography variant="body2" color="text.secondary">No semantic memory entries yet.</Typography>
                            )}
                        </Stack>
                    </SectionCard>
                    <SectionCard title="Agent memory" sx={{ display: knowledgeView === "memory" ? "block" : "none" }}>
                        <Stack spacing={1.5}>
                            <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                <Typography variant="subtitle2">Write agent profile memory</Typography>
                                <Typography variant="caption" color="text.secondary">
                                    Project-only notes are immediately available to the agent. Long-term notes stay pending until approved.
                                </Typography>
                                <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" }, gap: 1.5, mt: 1.5 }}>
                                    <TextField
                                        select
                                        label="Agent"
                                        value={agentMemoryForm.agent_id}
                                        onChange={(event) => setAgentMemoryForm((current) => ({ ...current, agent_id: event.target.value }))}
                                        helperText={allAgents.length === 0 ? "No agents are available in this project." : undefined}
                                    >
                                        {allAgents.map((agent) => <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>)}
                                    </TextField>
                                    <TextField
                                        label="Memory key"
                                        value={agentMemoryForm.key}
                                        onChange={(event) => setAgentMemoryForm((current) => ({ ...current, key: event.target.value }))}
                                        placeholder="preferred_style"
                                    />
                                    <TextField
                                        select
                                        label="Retention scope"
                                        value={agentMemoryForm.scope}
                                        onChange={(event) => setAgentMemoryForm((current) => ({ ...current, scope: event.target.value as "project-only" | "long-term" }))}
                                    >
                                        <MenuItem value="project-only">Project-only</MenuItem>
                                        <MenuItem value="long-term">Long-term (approval required)</MenuItem>
                                    </TextField>
                                    <TextField
                                        type="number"
                                        label="Expires after (days)"
                                        value={agentMemoryForm.ttl_days}
                                        onChange={(event) => setAgentMemoryForm((current) => ({ ...current, ttl_days: event.target.value }))}
                                        inputProps={{ min: 1, max: 3650 }}
                                    />
                                    <TextField
                                        label="Memory value"
                                        value={agentMemoryForm.value_text}
                                        onChange={(event) => setAgentMemoryForm((current) => ({ ...current, value_text: event.target.value }))}
                                        multiline
                                        minRows={3}
                                        sx={{ gridColumn: { md: "1 / -1" } }}
                                    />
                                </Box>
                                <Button
                                    sx={{ mt: 1.5 }}
                                    variant="contained"
                                    onClick={() => createMemoryMutation.mutate()}
                                    disabled={createMemoryMutation.isPending || !agentMemoryForm.agent_id || !agentMemoryForm.key.trim() || !agentMemoryForm.value_text.trim()}
                                >
                                    {createMemoryMutation.isPending ? "Saving…" : "Save agent memory"}
                                </Button>
                            </Paper>
                            {memoryEntries.map((entry) => (
                                <Paper key={entry.id} sx={{ p: 2, borderRadius: 4 }}>
                                    <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1.5}>
                                        <Box>
                                            <Typography variant="body2">{entry.key}</Typography>
                                            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                                                {entry.value_text}
                                            </Typography>
                                        </Box>
                                        <Button size="small" color="error" onClick={() => deleteMemoryMutation.mutate(entry.id)}>
                                            Remove
                                        </Button>
                                    </Stack>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                                        <Chip size="small" variant="outlined" label={entry.scope} />
                                        <Chip size="small" variant="outlined" label={entry.status} />
                                        <Chip size="small" variant="outlined" label={entry.expires_at ? `Expires ${formatDateTime(entry.expires_at)}` : "No expiry"} />
                                    </Stack>
                                </Paper>
                            ))}
                            {pendingMemoryApprovals.length > 0 ? (
                                <>
                                    <Divider />
                                    <Typography variant="subtitle2">Pending memory writes</Typography>
                                    {pendingMemoryApprovals.map((approval) => (
                                        <Paper key={approval.id} sx={{ p: 2, borderRadius: 4 }}>
                                            <Typography variant="body2">{String(approval.payload.key ?? "memory write")}</Typography>
                                            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                                                {String(approval.payload.value_text ?? "")}
                                            </Typography>
                                            <Stack direction="row" spacing={1} sx={{ mt: 1.25 }}>
                                                <Button size="small" variant="contained" onClick={() => memoryApprovalMutation.mutate({ approvalId: approval.id, status: "approved" })}>
                                                    Approve
                                                </Button>
                                                <Button size="small" variant="outlined" color="error" onClick={() => memoryApprovalMutation.mutate({ approvalId: approval.id, status: "rejected", reason: "Rejected from memory panel" })}>
                                                    Reject
                                                </Button>
                                            </Stack>
                                        </Paper>
                                    ))}
                                </>
                            ) : null}
                            {memoryEntries.length === 0 && pendingMemoryApprovals.length === 0 ? (
                                <Typography variant="body2" color="text.secondary">No memory entries yet.</Typography>
                            ) : null}
                        </Stack>
                    </SectionCard>
                </Box>
            )}

            {/* ── Runs ── */}
            {tab === "runs" && (
                <SectionCard
                    title="Runs & approvals"
                    description="Task runs, pending approvals, and sync events for this project."
                    action={
                        pendingProjectApprovals.length > 0 ? (
                            <Button size="small" variant="contained" color="warning" startIcon={<ApproveIcon />} onClick={() => navigate("/approvals")}>
                                Open approval queue
                            </Button>
                        ) : undefined
                    }
                >
                    <Stack spacing={1.25}>
                        {activityItems.filter((item) => item.kind === "Run" || item.kind === "Approval").length === 0 ? (
                            <Typography variant="body2" color="text.secondary">No runs or approvals yet.</Typography>
                        ) : activityItems.filter((item) => item.kind === "Run" || item.kind === "Approval").map((item) => (
                            <Paper key={item.id} sx={{ p: 1.5, borderRadius: 1 }}>
                                <Stack direction={{ xs: "column", sm: "row" }} spacing={1} justifyContent="space-between" alignItems={{ sm: "center" }}>
                                    <Box sx={{ minWidth: 0 }}>
                                        <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                                            <Chip size="small" variant="outlined" label={item.kind} />
                                            <Typography variant="subtitle2">{item.title}</Typography>
                                        </Stack>
                                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                                            {formatDateTime(item.at)} · {item.detail}
                                        </Typography>
                                    </Box>
                                    {item.action ? (
                                        <Button size="small" variant="text" onClick={item.action}>Open</Button>
                                    ) : null}
                                </Stack>
                            </Paper>
                        ))}
                    </Stack>
                </SectionCard>
            )}

            <Drawer
                anchor="right"
                open={overviewEditOpen}
                onClose={() => setOverviewEditOpen(false)}
                PaperProps={{ sx: { width: { xs: "100%", sm: 520 }, p: 2.5, boxSizing: "border-box" } }}
            >
                <Stack spacing={2}>
                    <Typography variant="h6" sx={{ fontWeight: 500 }}>Edit overview</Typography>
                    <TextField
                        label="Goals"
                        value={effectiveProjectGoals}
                        onChange={(event) => {
                            setProjectGoalsTouched(true);
                            setProjectGoalsDraft(event.target.value);
                        }}
                        multiline
                        minRows={4}
                    />
                    <TextField
                        label="Executive summary"
                        value={effectiveWorkspaceOverview.executive_summary}
                        onChange={(event) => {
                            setProjectOverviewTouched(true);
                            setProjectOverviewForm((current) => ({ ...current, executive_summary: event.target.value }));
                        }}
                        multiline
                        minRows={3}
                    />
                    <TextField
                        label="Current focus"
                        value={effectiveWorkspaceOverview.current_focus}
                        onChange={(event) => {
                            setProjectOverviewTouched(true);
                            setProjectOverviewForm((current) => ({ ...current, current_focus: event.target.value }));
                        }}
                        multiline
                        minRows={2}
                    />
                    <TextField
                        label="Decision / knowledge focus"
                        value={effectiveWorkspaceOverview.decision_focus}
                        onChange={(event) => {
                            setProjectOverviewTouched(true);
                            setProjectOverviewForm((current) => ({ ...current, decision_focus: event.target.value }));
                        }}
                        multiline
                        minRows={2}
                    />
                    <ExternalLinksEditor
                        links={effectiveProjectExternalLinks}
                        onChange={(links) => {
                            setProjectExternalLinksTouched(true);
                            setProjectExternalLinks(links);
                        }}
                    />
                    <Button
                        variant="contained"
                        onClick={() => {
                            saveProjectSettingsMutation.mutate({
                                goals_markdown: effectiveProjectGoals,
                                settings: {
                                    ...(project.settings ?? {}),
                                    workspace_overview: effectiveWorkspaceOverview,
                                    external_links: serializeExternalLinks(effectiveProjectExternalLinks),
                                },
                            });
                            setOverviewEditOpen(false);
                        }}
                        disabled={saveProjectSettingsMutation.isPending}
                    >
                        Save overview
                    </Button>
                </Stack>
            </Drawer>

            <Drawer
                anchor="right"
                open={Boolean(dagDrawerTaskId)}
                onClose={() => setDagDrawerTaskId(null)}
                PaperProps={{ sx: { width: { xs: "100%", sm: 420 }, p: 2.5, boxSizing: "border-box" } }}
            >
                {dagTask && (
                    <Stack spacing={2}>
                        <Typography variant="overline" color="text.secondary">Task</Typography>
                        <Typography variant="h6" sx={{ fontWeight: 500 }}>{dagTask.title}</Typography>
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <StatusChip status={dagTask.status} kind="task" size="small" />
                            <Chip label={dagTask.priority} size="small" variant="outlined" />
                        </Stack>
                        {dagTask.description ? (
                            <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-wrap" }}>
                                {dagTask.description}
                            </Typography>
                        ) : null}
                        <TextField
                            select
                            SelectProps={{ multiple: true }}
                            size="small"
                            label="Dependencies"
                            value={currentDagDependencySelection}
                            onChange={(event) => {
                                const nextValue = event.target.value;
                                if (!dagTask) return;
                                setDagDependencyDrafts((current) => ({
                                    ...current,
                                    [dagTask.id]: Array.isArray(nextValue)
                                        ? nextValue
                                        : String(nextValue).split(",").filter(Boolean),
                                }));
                            }}
                            helperText="Selected tasks must finish before this one can run."
                            fullWidth
                        >
                            {tasks
                                .filter((candidate) => candidate.id !== dagTask.id && !dagDescendantIds.has(candidate.id))
                                .map((candidate) => (
                                    <MenuItem key={candidate.id} value={candidate.id}>
                                        {candidate.title} · {humanizeKey(candidate.status)}
                                    </MenuItem>
                                ))}
                        </TextField>
                        <Button
                            variant="outlined"
                            disabled={updateDagTaskMutation.isPending}
                            onClick={() => updateDagTaskMutation.mutate({
                                taskId: dagTask.id,
                                payload: { dependency_ids: currentDagDependencySelection },
                            })}
                        >
                            Save dependencies
                        </Button>
                        {dagTaskDependents.length > 0 ? (
                            <Stack spacing={0.5}>
                                <Typography variant="caption" color="text.secondary">Downstream tasks</Typography>
                                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                    {dagTaskDependents.map((dependent) => (
                                        <Chip key={dependent.id} label={dependent.title} size="small" variant="outlined" />
                                    ))}
                                </Stack>
                            </Stack>
                        ) : null}
                        {dagBlockedSuggestion ? (
                            <Alert severity="warning">
                                Suggested handoff: {dagBlockedSuggestion.agentName} via {humanizeKey(dagBlockedSuggestion.via)}.
                                {dagBlockedSuggestion.reason ? ` ${dagBlockedSuggestion.reason}` : ""}
                            </Alert>
                        ) : null}
                        <Stack spacing={1}>
                            <Button variant="outlined" onClick={() => { setTab("board"); setWorkView("board"); setDagDrawerTaskId(null); }}>
                                Open board tab
                            </Button>
                            {dagTaskLatestRun ? (
                                <Button variant="outlined" onClick={() => navigate(`/runs/${dagTaskLatestRun.id}`)}>
                                    Open latest run
                                </Button>
                            ) : null}
                            <Button
                                variant="contained"
                                disabled={runMutation.isPending}
                                onClick={() => {
                                    setSelectedTaskId(dagTask.id);
                                    runMutation.mutate({
                                        taskId: dagTask.id,
                                        runMode: taskRunModes[dagTask.id] ?? "single_agent",
                                        createPr: taskPrModes[dagTask.id] ?? false,
                                    });
                                    setDagDrawerTaskId(null);
                                }}
                            >
                                Run this task
                            </Button>
                            {dagTaskSubtasks.length >= 2 ? (
                                <Button
                                    variant="outlined"
                                    disabled={mergeResolutionMutation.isPending}
                                    onClick={() => {
                                        const done = dagTaskSubtasks.filter((s) => s.status === "completed" || s.status === "approved");
                                        if (done.length < 2) {
                                            showToast({ message: "Need at least two completed subtasks to merge.", severity: "warning" });
                                            return;
                                        }
                                        setMergeTaskId(dagTask.id);
                                        setMergeNotes(`Synthesize the best branch outputs for "${dagTask.title}". Resolve conflicts, preserve accepted evidence, and promote one final artifact set.`);
                                        setDagDrawerTaskId(null);
                                    }}
                                >
                                    Merge completed subtasks (resolution run)
                                </Button>
                            ) : null}
                            {dagTask.metadata?.latest_reopen ? (
                                <Alert severity="warning">
                                    Latest rework checklist recorded. Re-run after addressing reviewer items.
                                </Alert>
                            ) : null}
                        </Stack>
                    </Stack>
                )}
            </Drawer>

            <Dialog open={Boolean(mergeTaskId)} onClose={() => setMergeTaskId(null)} fullWidth maxWidth="md">
                <DialogTitle>Merge branch outputs</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <Typography variant="body2" color="text.secondary">
                            Review completed branch outputs, flag conflicts, then queue one synthesis run on the parent task.
                        </Typography>
                        {mergePreview ? (
                            <>
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Typography variant="subtitle2">{String((mergePreview.parent as { title?: string } | undefined)?.title || "Parent task")}</Typography>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
                                        <Chip size="small" variant="outlined" label={`${Number(mergePreview.completed_branch_count || 0)} completed branches`} />
                                        <Chip size="small" variant="outlined" label={`${Number(mergePreview.distinct_agents_on_completed || 0)} contributing agents`} />
                                        <Chip
                                            size="small"
                                            color={mergePreview.needs_merge_agent ? "warning" : "success"}
                                            label={mergePreview.needs_merge_agent ? "conflict review needed" : "low conflict"}
                                        />
                                    </Stack>
                                </Paper>
                                <Stack spacing={1}>
                                    {Array.isArray(mergePreview.branches) ? mergePreview.branches.map((branch) => {
                                        const branchRow = branch as { id: string; title?: string; status?: string; assigned_agent_id?: string | null; result_summary?: string | null };
                                        return (
                                            <Paper key={branchRow.id} sx={{ p: 1.5, borderRadius: 1 }}>
                                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
                                                    <Typography variant="subtitle2">{branchRow.title || "Branch task"}</Typography>
                                                    <Chip size="small" variant="outlined" label={branchRow.status || "unknown"} />
                                                    {branchRow.assigned_agent_id ? <Chip size="small" variant="outlined" label={branchRow.assigned_agent_id.slice(0, 8)} /> : null}
                                                </Stack>
                                                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75, whiteSpace: "pre-wrap" }}>
                                                    {branchRow.result_summary || "No summary captured yet."}
                                                </Typography>
                                            </Paper>
                                        );
                                    }) : null}
                                </Stack>
                            </>
                        ) : (
                            <LinearProgress />
                        )}
                        <Alert severity="info">
                            Checklist: compare branch evidence, reconcile conflicts, preserve accepted artifacts, and name the promoted final output in notes.
                        </Alert>
                        <TextField
                            label="Synthesis notes"
                            multiline
                            minRows={5}
                            value={mergeNotes}
                            onChange={(event) => setMergeNotes(event.target.value)}
                            helperText="These notes become merge context for the synthesis run."
                            fullWidth
                        />
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setMergeTaskId(null)}>Cancel</Button>
                    <Button
                        variant="contained"
                        disabled={!mergeTaskId || mergeResolutionMutation.isPending}
                        onClick={() => {
                            if (!mergeTaskId) return;
                            mergeResolutionMutation.mutate({ parentTaskId: mergeTaskId, notes: mergeNotes.trim() || "Merge branches from project DAG." });
                        }}
                    >
                        Queue merge resolution run
                    </Button>
                </DialogActions>
            </Dialog>

            {/* ── Acceptance Dialog ── */}
            {acceptanceTaskId && (
                <AcceptanceDialog
                    projectId={projectId}
                    taskId={acceptanceTaskId}
                    taskTitle={tasks.find((t) => t.id === acceptanceTaskId)?.title ?? ""}
                    onClose={() => setAcceptanceTaskId(null)}
                />
            )}
        </PageShell>
    );
}

