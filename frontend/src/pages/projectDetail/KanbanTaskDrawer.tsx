import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert, Box, Button, Chip, CircularProgress, Divider, Drawer, FormControlLabel, IconButton, Link, MenuItem,
    Paper, Stack, Switch, TextField, Typography,
} from "@mui/material";
import { alpha } from "@mui/material/styles";
import { Close as CloseIcon, Check as CheckSimpleIcon, PlayArrow as RunIcon } from "@mui/icons-material";
import {
    deleteOrchestrationTask, getOrchestrationTask, getTaskBlockers, getTaskExecutionState, getTaskTimeline,
    listTaskArtifacts, updateOrchestrationTask,
    type OrchestrationTask, type RunListItem, type TaskListItem,
} from "../../api/orchestration";
import { useSnackbar } from "../../app/snackbarContext";
import { queryKeys } from "../../config/queryKeys";
import { ConfirmDestructiveDialog } from "../../components/ui/ConfirmDestructiveDialog";
import { useDrawerFocus } from "../../hooks/useDrawerFocus";
import { ExternalLinksEditor, type ExternalLinkRecord } from "../../features/orchestration/project/components/ExternalLinksEditor";
import { SubtaskPanel } from "../../features/orchestration/project/components/SubtaskPanel";
import { TaskIntelligencePanel } from "../../features/workforce/TaskIntelligencePanel";
import { extractApiErrorMessage } from "../../utils/apiErrors";
import { formatDateTime, humanizeKey } from "../../utils/formatters";
import { readOrchestrationSelectionMeta } from "../../utils/orchestrationSelection";
import { ArtifactPanel } from "./ArtifactPanel";
import { TaskMemoryInspector } from "./TaskMemoryInspector";
import {
    type AcceptanceCheckerConfig,
    type EvidenceBundleDraft,
    type ExecutionMode,
    buildEvidenceBundlePayload,
    buildTransitionOptions,
    readAcceptanceCheckerConfig,
    readEvidenceBundle,
    readExternalLinks,
    serializeExternalLinks,
    splitCsv,
} from "./projectDetailShared";

type KanbanTaskDrawerProps = {
    projectId: string;
    tasks: TaskListItem[];
    allAgents: Array<{ id: string; name: string }>;
    lastRunByTaskId: Record<string, RunListItem>;
    expandedTask: string | null;
    setExpandedTask: (id: string | null) => void;
    taskRunModes: Record<string, ExecutionMode>;
    taskPrModes: Record<string, boolean>;
    onModeChange: (taskId: string, mode: ExecutionMode) => void;
    onPrModeChange: (taskId: string, enabled: boolean) => void;
    onRunTask: (taskId: string, mode: ExecutionMode, createPr: boolean) => void;
    onAcceptanceCheck: (taskId: string) => void;
    isRunPending: boolean;
};

export function KanbanTaskDrawer({
    projectId,
    tasks,
    allAgents,
    lastRunByTaskId,
    expandedTask,
    setExpandedTask,
    taskRunModes,
    taskPrModes,
    onModeChange,
    onPrModeChange,
    onRunTask,
    onAcceptanceCheck,
    isRunPending,
}: KanbanTaskDrawerProps) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [deleteTaskTarget, setDeleteTaskTarget] = useState<{ id: string; title: string } | null>(null);
    const panelRef = useRef(null);
    useDrawerFocus(Boolean(expandedTask), panelRef);
    const [taskLinkDrafts, setTaskLinkDrafts] = useState<Record<string, ExternalLinkRecord[]>>({});
    const [evidenceDrafts, setEvidenceDrafts] = useState<Record<string, EvidenceBundleDraft>>({});
    const [nextStatusByTask, setNextStatusByTask] = useState<Record<string, string>>({});

    const taskUpdateMutation = useMutation({
        mutationFn: ({ taskId, payload }: { taskId: string; payload: Record<string, unknown> }) =>
            updateOrchestrationTask(projectId, taskId, payload),
        onSuccess: async (_data, vars) => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTasks(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTask(projectId, vars.taskId) });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Couldn't update task. Try again."), severity: "error" });
        },
    });
    const acceptanceConfigMutation = useMutation({
        mutationFn: ({ taskId, metadata }: { taskId: string; metadata: Record<string, unknown> }) =>
            updateOrchestrationTask(projectId, taskId, { metadata }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTasks(projectId) });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTaskExecution(projectId, expandedTask || undefined) });
            if (expandedTask) {
                await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTask(projectId, expandedTask) });
            }
            showToast({ message: "Acceptance checker updated.", severity: "success" });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Couldn't save acceptance checker. Try again."), severity: "error" });
        },
    });
    const deleteTaskMutation = useMutation({
        mutationFn: (taskId: string) => deleteOrchestrationTask(projectId, taskId),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectTasks(projectId) });
            showToast({ message: "Task deleted.", severity: "success" });
        },
        onError: (error) => {
            showToast({ message: extractApiErrorMessage(error, "Couldn't delete task. Try again."), severity: "error" });
        },
    });

    const { data: timeline = [] } = useQuery({
        queryKey: queryKeys.orchestration.projectTaskTimeline(projectId, expandedTask || ""),
        queryFn: () => (expandedTask ? getTaskTimeline(projectId, expandedTask) : Promise.resolve([])),
        enabled: Boolean(expandedTask),
    });
    const { data: detailedTask } = useQuery({
        queryKey: queryKeys.orchestration.projectTask(projectId, expandedTask || ""),
        queryFn: () => getOrchestrationTask(projectId, expandedTask as string),
        enabled: Boolean(expandedTask),
    });
    const { data: expandedExecSnapshot } = useQuery({
        queryKey: queryKeys.orchestration.projectTaskExecution(projectId, expandedTask || ""),
        queryFn: () => (expandedTask ? getTaskExecutionState(projectId, expandedTask) : Promise.resolve(null)),
        enabled: Boolean(expandedTask),
    });
    const { data: expandedArtifacts = [] } = useQuery({
        queryKey: queryKeys.orchestration.projectTaskArtifacts(projectId, expandedTask || ""),
        queryFn: () => (expandedTask ? listTaskArtifacts(expandedTask) : Promise.resolve([])),
        enabled: Boolean(expandedTask),
    });
    const { data: expandedBlockers } = useQuery({
        queryKey: queryKeys.orchestration.projectTaskBlockers(projectId, expandedTask || ""),
        queryFn: () => (expandedTask ? getTaskBlockers(projectId, expandedTask) : Promise.resolve(null)),
        enabled: Boolean(expandedTask),
    });

    function updateAcceptanceConfig(task: OrchestrationTask, patch: Partial<AcceptanceCheckerConfig>) {
        acceptanceConfigMutation.mutate({
            taskId: task.id,
            metadata: {
                ...task.metadata,
                acceptance_checker: {
                    ...readAcceptanceCheckerConfig(task),
                    ...patch,
                },
            },
        });
    }

    return (
        <>
            <Drawer
                anchor="right"
                open={Boolean(expandedTask)}
                onClose={() => setExpandedTask(null)}
                slotProps={{ backdrop: { sx: { bgcolor: alpha("#000", 0.2) } } }}
                sx={{ "& .MuiDrawer-paper": { width: { xs: "92vw", sm: 480, md: 540 }, p: 2.5 } }}
            >
                <Box ref={panelRef} sx={{ height: "100%" }}>
                {(() => {
                    const listTask = expandedTask ? tasks.find((t) => t.id === expandedTask) : null;
                    if (!listTask) return null;
                    const drawerTask = detailedTask;
                    if (!drawerTask) {
                        return (
                            <Stack alignItems="center" spacing={1.5} sx={{ py: 6 }} role="status" aria-live="polite">
                                <CircularProgress />
                                <Typography variant="body2" color="text.secondary">
                                    Loading {listTask.title}…
                                </Typography>
                            </Stack>
                        );
                    }

                    const agent = allAgents.find((a) => a.id === drawerTask.assigned_agent_id);
                    const lastRun = lastRunByTaskId[drawerTask.id];
                    const runMeta = readOrchestrationSelectionMeta(lastRun);
                    const acceptanceConfig = readAcceptanceCheckerConfig(drawerTask);
                    const taskLinks = taskLinkDrafts[drawerTask.id] ?? readExternalLinks(drawerTask.metadata?.external_links);
                    const evidenceDraft = evidenceDrafts[drawerTask.id] ?? readEvidenceBundle(drawerTask);
                    const dependencyTasks = tasks.filter((candidate) => (drawerTask.dependency_ids ?? []).includes(candidate.id));
                    const incompleteDependencies = dependencyTasks.filter((candidate) => !["approved", "completed", "synced_to_github", "archived"].includes(candidate.status));
                    const acceptancePassed = Boolean(expandedExecSnapshot?.acceptance_summary?.passed);
                    const acceptedArtifactsCount = evidenceDraft.accepted_artifact_ids.filter((artifactId) => expandedArtifacts.some((artifact) => artifact.id === artifactId)).length;
                    const acceptedLinksCount = evidenceDraft.accepted_external_link_ids.filter((linkId) => taskLinks.some((link) => link.id === linkId)).length;
                    const evidenceReadyForSync =
                        acceptedArtifactsCount > 0 &&
                        acceptedLinksCount > 0 &&
                        Boolean(evidenceDraft.reviewer_decision_status) &&
                        Boolean(evidenceDraft.sync_summary.trim());
                    const evidenceReadyForArchive =
                        (acceptedArtifactsCount > 0 &&
                            acceptedLinksCount > 0 &&
                            Boolean(evidenceDraft.reviewer_decision_status) &&
                            (Boolean(evidenceDraft.sync_summary.trim()) || drawerTask.status === "synced_to_github"))
                        || drawerTask.status === "archived";
                    const transitionOptions = buildTransitionOptions({
                        task: drawerTask,
                        acceptancePassed,
                        evidenceReadyForSync,
                        evidenceReadyForArchive,
                        hasIncompleteDependencies: incompleteDependencies.length > 0,
                    });
                    const selectedNextStatus = nextStatusByTask[drawerTask.id] ?? transitionOptions[0]?.status ?? "";
                    const workerTip =
                        runMeta.worker_agent_rationale
                        || "The worker comes from the task assignment, an explicit run payload, or automatic routing. Run again to capture a fresh routing note.";
                    return (
                        <>
                            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                                <Box sx={{ minWidth: 0, flex: 1 }}>
                                    <Typography variant="h6" sx={{ fontWeight: 500, wordBreak: "break-word" }}>
                                        {drawerTask.title}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        {humanizeKey(drawerTask.status)} · {agent?.name ?? "Unassigned"}
                                    </Typography>
                                </Box>
                                <IconButton size="small" onClick={() => setExpandedTask(null)}>
                                    <CloseIcon />
                                </IconButton>
                            </Stack>

                            {drawerTask.description ? (
                                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                                    {drawerTask.description}
                                </Typography>
                            ) : null}
                            {expandedBlockers && (expandedBlockers.blockers.length > 0 || expandedBlockers.warnings.length > 0) ? (
                                <Stack spacing={0.75} sx={{ mb: 2 }}>
                                    {expandedBlockers.blockers.map((blocker, index) => (
                                        <Alert key={`blocker-${index}`} severity="warning">
                                            {String(blocker.message || "Task cannot start yet.")}
                                        </Alert>
                                    ))}
                                    {expandedBlockers.warnings.map((warning, index) => (
                                        <Alert key={`warning-${index}`} severity="info">
                                            {String(warning.message || "Task has an execution warning.")}
                                        </Alert>
                                    ))}
                                </Stack>
                            ) : null}
                            <Button
                                size="small"
                                color="error"
                                variant="outlined"
                                onClick={() => {
                                    setDeleteTaskTarget({ id: drawerTask.id, title: drawerTask.title });
                                }}
                                sx={{ mb: 2 }}
                            >
                                Delete task
                            </Button>

                            <Stack spacing={1.5} sx={{ overflowY: "auto", flex: 1, pb: 2 }}>
                                <TextField
                                    size="small"
                                    label="Task source"
                                    key={`${drawerTask.id}-source`}
                                    defaultValue={drawerTask.source}
                                    onBlur={(event) => {
                                        const source = event.target.value.trim();
                                        if (source && source !== drawerTask.source) {
                                            taskUpdateMutation.mutate({ taskId: drawerTask.id, payload: { source } });
                                        }
                                    }}
                                    helperText="manual, GitHub, manager-generated, decomposition, or webhook"
                                    fullWidth
                                />

                                <TextField
                                    size="small"
                                    label="Task type"
                                    key={`${drawerTask.id}-type`}
                                    defaultValue={drawerTask.task_type}
                                    onBlur={(event) => {
                                        const taskType = event.target.value.trim();
                                        if (taskType && taskType !== drawerTask.task_type) {
                                            taskUpdateMutation.mutate({ taskId: drawerTask.id, payload: { task_type: taskType } });
                                        }
                                    }}
                                    helperText="bug, feature, review, incident, documentation, or another domain type"
                                    fullWidth
                                />

                                <TextField
                                    size="small"
                                    label="Required tools"
                                    key={`${drawerTask.id}-tools`}
                                    defaultValue={drawerTask.required_tools.join(", ")}
                                    onBlur={(event) => {
                                        const requiredTools = splitCsv(event.target.value);
                                        if (requiredTools.join(",") !== drawerTask.required_tools.join(",")) {
                                            taskUpdateMutation.mutate({ taskId: drawerTask.id, payload: { required_tools: requiredTools } });
                                        }
                                    }}
                                    helperText="Comma-separated tools checked against the selected owner's tool policy"
                                    fullWidth
                                />

                                <TextField
                                    select
                                    size="small"
                                    label="Owner agent"
                                    value={drawerTask.assigned_agent_id ?? ""}
                                    onChange={(event) => taskUpdateMutation.mutate({
                                        taskId: drawerTask.id,
                                        payload: { assigned_agent_id: event.target.value || null },
                                    })}
                                    fullWidth
                                >
                                    <MenuItem value="">Unassigned</MenuItem>
                                    {allAgents.map((currentAgent) => (
                                        <MenuItem key={currentAgent.id} value={currentAgent.id}>{currentAgent.name}</MenuItem>
                                    ))}
                                </TextField>

                                <TextField
                                    select
                                    size="small"
                                    label="Reviewer agent"
                                    value={drawerTask.reviewer_agent_id ?? ""}
                                    onChange={(event) => taskUpdateMutation.mutate({
                                        taskId: drawerTask.id,
                                        payload: { reviewer_agent_id: event.target.value || null },
                                    })}
                                    fullWidth
                                >
                                    <MenuItem value="">None</MenuItem>
                                    {allAgents.map((currentAgent) => (
                                        <MenuItem key={`review-${currentAgent.id}`} value={currentAgent.id}>{currentAgent.name}</MenuItem>
                                    ))}
                                </TextField>

                                <TextField
                                    select
                                    SelectProps={{ multiple: true }}
                                    size="small"
                                    label="Blocked by"
                                    value={drawerTask.dependency_ids ?? []}
                                    onChange={(event) => {
                                        const nextValue = event.target.value;
                                        taskUpdateMutation.mutate({
                                            taskId: drawerTask.id,
                                            payload: {
                                                dependency_ids: Array.isArray(nextValue) ? nextValue : String(nextValue).split(",").filter(Boolean),
                                            },
                                        });
                                    }}
                                    helperText="Main task flow dependencies."
                                    fullWidth
                                >
                                    {tasks.filter((candidate) => candidate.id !== drawerTask.id).map((candidate) => (
                                        <MenuItem key={`dep-${candidate.id}`} value={candidate.id}>
                                            {candidate.title} · {humanizeKey(candidate.status)}
                                        </MenuItem>
                                    ))}
                                </TextField>

                                {dependencyTasks.length > 0 ? (
                                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                        {dependencyTasks.map((dependencyTask) => (
                                            <Chip
                                                key={dependencyTask.id}
                                                label={`${dependencyTask.title} · ${humanizeKey(dependencyTask.status)}`}
                                                size="small"
                                                color={incompleteDependencies.some((item) => item.id === dependencyTask.id) ? "warning" : "success"}
                                                variant="outlined"
                                            />
                                        ))}
                                    </Stack>
                                ) : null}

                                <TextField
                                    select
                                    size="small"
                                    label="Execution mode"
                                    value={taskRunModes[drawerTask.id] ?? "single_agent"}
                                    onChange={(event) => onModeChange(drawerTask.id, event.target.value as ExecutionMode)}
                                    fullWidth
                                >
                                    <MenuItem value="single_agent">Single agent: fast, cheap</MenuItem>
                                    <MenuItem value="manager_worker">Managed team: manager routes work</MenuItem>
                                    <MenuItem value="debate">Debate: two agents propose, moderator resolves</MenuItem>
                                </TextField>

                                <Button
                                    size="small"
                                    variant={taskPrModes[drawerTask.id] ? "contained" : "outlined"}
                                    onClick={() => onPrModeChange(drawerTask.id, !(taskPrModes[drawerTask.id] ?? false))}
                                >
                                    {taskPrModes[drawerTask.id] ? "PR generation on" : "Generate PR"}
                                </Button>

                                <Divider />

                                <TextField
                                    select
                                    size="small"
                                    label="Next valid status"
                                    value={selectedNextStatus}
                                    onChange={(event) => setNextStatusByTask((current) => ({ ...current, [drawerTask.id]: event.target.value }))}
                                    fullWidth
                                >
                                    {transitionOptions.map((option) => (
                                        <MenuItem key={`${drawerTask.id}-${option.status}`} value={option.status} disabled={option.blocked}>
                                            {humanizeKey(option.status)}{option.reason ? ` — ${option.reason}` : ""}
                                        </MenuItem>
                                    ))}
                                </TextField>

                                {transitionOptions.filter((option) => option.blocked).map((option) => (
                                    <Alert key={`${drawerTask.id}-${option.status}-blocked`} severity="warning">
                                        {humanizeKey(option.status)} blocked: {option.reason}
                                    </Alert>
                                ))}

                                <Button
                                    size="small"
                                    variant="contained"
                                    disabled={!selectedNextStatus || Boolean(transitionOptions.find((option) => option.status === selectedNextStatus)?.blocked)}
                                    onClick={() => taskUpdateMutation.mutate({
                                        taskId: drawerTask.id,
                                        payload: { status: selectedNextStatus },
                                    })}
                                >
                                    Apply transition
                                </Button>

                                <Divider />

                                <Typography variant="subtitle2">Run & acceptance</Typography>

                                <Stack direction="row" spacing={1}>
                                    <Button
                                        size="small"
                                        variant="outlined"
                                        startIcon={<RunIcon />}
                                        disabled={isRunPending}
                                        onClick={() => onRunTask(
                                            drawerTask.id,
                                            taskRunModes[drawerTask.id] ?? "single_agent",
                                            taskPrModes[drawerTask.id] ?? false,
                                        )}
                                    >
                                        Run
                                    </Button>
                                    <Button
                                        size="small"
                                        variant="outlined"
                                        startIcon={<CheckSimpleIcon />}
                                        onClick={() => onAcceptanceCheck(drawerTask.id)}
                                    >
                                        Check acceptance
                                    </Button>
                                </Stack>

                                <Typography variant="caption" color="text.secondary">
                                    Model source: {runMeta.model_source ?? "N/A"}
                                </Typography>

                                {lastRun ? (
                                    <Stack direction="row" spacing={0.5} alignItems="center">
                                        <Typography variant="caption" color="text.secondary">
                                            Last run:
                                        </Typography>
                                        <Chip
                                            size="small"
                                            color={lastRun.status === "failed" ? "error" : "success"}
                                            variant="outlined"
                                            label={lastRun.status}
                                        />
                                    </Stack>
                                ) : null}

                                <Divider />

                                <Typography variant="subtitle2">Routing</Typography>

                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Typography variant="caption" color="text.secondary">Agent selection</Typography>
                                    <Typography variant="body2" sx={{ mb: 1 }}>
                                        {String(expandedExecSnapshot?.routing_explainability?.agent_selection_reason || workerTip)}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">Model selection</Typography>
                                    <Typography variant="body2">
                                        {String(expandedExecSnapshot?.routing_explainability?.model_selection_reason || runMeta.model_rationale || "No explicit model explanation captured yet.")}
                                    </Typography>
                                    {expandedExecSnapshot?.routing_explainability?.routing_policy_snapshot ? (
                                        <Box
                                            component="pre"
                                            sx={{ m: 0, mt: 1, p: 1, typography: "caption", bgcolor: (theme) => alpha(theme.palette.text.primary, 0.04), whiteSpace: "pre-wrap" }}
                                        >
                                            {JSON.stringify(expandedExecSnapshot.routing_explainability.routing_policy_snapshot, null, 2)}
                                        </Box>
                                    ) : null}
                                </Paper>

                                <Divider />

                                <Typography variant="subtitle2">Acceptance checker</Typography>

                                <Stack spacing={1}>
                                    <TextField
                                        size="small"
                                        label="Required artifact kinds"
                                        defaultValue={acceptanceConfig.required_artifact_kinds.join(", ")}
                                        helperText="Comma-separated kinds enforced before approve/complete."
                                        onBlur={(event) => updateAcceptanceConfig(drawerTask, {
                                            required_artifact_kinds: event.target.value.split(",").map((item) => item.trim()).filter(Boolean),
                                        })}
                                        fullWidth
                                    />
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                        <FormControlLabel
                                            control={<Switch checked={acceptanceConfig.require_github_comment} onChange={(_, checked) => updateAcceptanceConfig(drawerTask, { require_github_comment: checked })} />}
                                            label="Need GitHub comment"
                                        />
                                        <FormControlLabel
                                            control={<Switch checked={acceptanceConfig.require_github_pr} onChange={(_, checked) => updateAcceptanceConfig(drawerTask, { require_github_pr: checked })} />}
                                            label="Need GitHub PR"
                                        />
                                        <FormControlLabel
                                            control={<Switch checked={acceptanceConfig.require_reviewer_approval} onChange={(_, checked) => updateAcceptanceConfig(drawerTask, { require_reviewer_approval: checked })} />}
                                            label="Need reviewer approval"
                                        />
                                    </Stack>
                                    {expandedExecSnapshot?.acceptance_summary ? (
                                        <Alert severity={expandedExecSnapshot.acceptance_summary.passed ? "success" : "warning"}>
                                            {expandedExecSnapshot.acceptance_summary.passed ? "Acceptance gate currently passes." : "Acceptance gate currently fails."}
                                        </Alert>
                                    ) : null}
                                </Stack>

                                <Divider />

                                <Typography variant="subtitle2">External links</Typography>

                                <ExternalLinksEditor
                                    links={taskLinks}
                                    onChange={(links) => setTaskLinkDrafts((current) => ({ ...current, [drawerTask.id]: links }))}
                                    compact
                                />

                                <Button
                                    size="small"
                                    variant="outlined"
                                    onClick={() => taskUpdateMutation.mutate({
                                        taskId: drawerTask.id,
                                        payload: {
                                            metadata: {
                                                ...drawerTask.metadata,
                                                external_links: serializeExternalLinks(taskLinks),
                                                evidence_bundle: buildEvidenceBundlePayload(evidenceDraft),
                                            },
                                        },
                                    })}
                                >
                                    Save links
                                </Button>

                                <Divider />

                                <Typography variant="subtitle2">Task Intelligence</Typography>

                                <TaskIntelligencePanel
                                    projectId={projectId}
                                    taskId={drawerTask.id}
                                />

                                <Divider />

                                <Typography variant="subtitle2">Final evidence bundle</Typography>

                                <Stack spacing={1}>
                                    <TextField
                                        select
                                        SelectProps={{ multiple: true }}
                                        size="small"
                                        label="Accepted artifacts"
                                        value={evidenceDraft.accepted_artifact_ids}
                                        onChange={(event) => {
                                            const nextValue = event.target.value;
                                            setEvidenceDrafts((current) => ({
                                                ...current,
                                                [drawerTask.id]: {
                                                    ...evidenceDraft,
                                                    accepted_artifact_ids: Array.isArray(nextValue) ? nextValue : String(nextValue).split(",").filter(Boolean),
                                                },
                                            }));
                                        }}
                                        fullWidth
                                    >
                                        {expandedArtifacts.map((artifact) => (
                                            <MenuItem key={artifact.id} value={artifact.id}>{artifact.title} · {artifact.kind}</MenuItem>
                                        ))}
                                    </TextField>

                                    <TextField
                                        select
                                        SelectProps={{ multiple: true }}
                                        size="small"
                                        label="Accepted external links"
                                        value={evidenceDraft.accepted_external_link_ids}
                                        onChange={(event) => {
                                            const nextValue = event.target.value;
                                            setEvidenceDrafts((current) => ({
                                                ...current,
                                                [drawerTask.id]: {
                                                    ...evidenceDraft,
                                                    accepted_external_link_ids: Array.isArray(nextValue) ? nextValue : String(nextValue).split(",").filter(Boolean),
                                                },
                                            }));
                                        }}
                                        fullWidth
                                    >
                                        {taskLinks.map((link) => (
                                            <MenuItem key={`accepted-link-${link.id}`} value={link.id}>{link.label} · {humanizeKey(link.kind)}</MenuItem>
                                        ))}
                                    </TextField>

                                    <TextField
                                        select
                                        size="small"
                                        label="Reviewer decision"
                                        value={evidenceDraft.reviewer_decision_status}
                                        onChange={(event) => setEvidenceDrafts((current) => ({
                                            ...current,
                                            [drawerTask.id]: {
                                                ...evidenceDraft,
                                                reviewer_decision_status: event.target.value,
                                            },
                                        }))}
                                        fullWidth
                                    >
                                        <MenuItem value="">Not recorded</MenuItem>
                                        <MenuItem value="approved">Approved</MenuItem>
                                        <MenuItem value="changes_requested">Changes requested</MenuItem>
                                        <MenuItem value="rejected">Rejected</MenuItem>
                                    </TextField>

                                    <TextField
                                        size="small"
                                        label="Reviewer notes"
                                        value={evidenceDraft.reviewer_decision_notes}
                                        onChange={(event) => setEvidenceDrafts((current) => ({
                                            ...current,
                                            [drawerTask.id]: {
                                                ...evidenceDraft,
                                                reviewer_decision_notes: event.target.value,
                                            },
                                        }))}
                                        multiline
                                        minRows={2}
                                        fullWidth
                                    />

                                    <TextField
                                        size="small"
                                        label="Sync summary"
                                        value={evidenceDraft.sync_summary}
                                        onChange={(event) => setEvidenceDrafts((current) => ({
                                            ...current,
                                            [drawerTask.id]: {
                                                ...evidenceDraft,
                                                sync_summary: event.target.value,
                                            },
                                        }))}
                                        multiline
                                        minRows={2}
                                        helperText="Required before `synced_to_github`; reused for archive notes."
                                        fullWidth
                                    />

                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                        <Chip label={evidenceReadyForSync ? "Ready for sync" : "Sync evidence incomplete"} size="small" color={evidenceReadyForSync ? "success" : "warning"} />
                                        <Chip label={evidenceReadyForArchive ? "Ready for archive" : "Archive evidence incomplete"} size="small" color={evidenceReadyForArchive ? "success" : "warning"} />
                                    </Stack>

                                    <Button
                                        size="small"
                                        variant="outlined"
                                        onClick={() => taskUpdateMutation.mutate({
                                            taskId: drawerTask.id,
                                            payload: {
                                                metadata: {
                                                    ...drawerTask.metadata,
                                                    external_links: serializeExternalLinks(taskLinks),
                                                    evidence_bundle: buildEvidenceBundlePayload(evidenceDraft),
                                                },
                                            },
                                        })}
                                    >
                                        Save evidence bundle
                                    </Button>
                                </Stack>

                                <Divider />

                                <Typography variant="subtitle2">What changed since last run</Typography>

                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                    {String(expandedExecSnapshot?.execution_memory?.since_last_run_unified_diff || "").trim() ? (
                                        <Box component="pre" sx={{ m: 0, whiteSpace: "pre-wrap", typography: "caption" }}>
                                            {String(expandedExecSnapshot?.execution_memory?.since_last_run_unified_diff || "")}
                                        </Box>
                                    ) : (
                                        <Typography variant="body2" color="text.secondary">
                                            No diff captured yet.
                                        </Typography>
                                    )}
                                    <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                                        {expandedExecSnapshot?.last_run_id ? (
                                            <Link href={`/runs/${expandedExecSnapshot.last_run_id}`} underline="hover">Latest run</Link>
                                        ) : null}
                                    </Stack>
                                </Paper>

                                <Divider />

                                <Typography variant="subtitle2">Changed artifacts</Typography>

                                <Stack spacing={0.75}>
                                    {(expandedExecSnapshot?.changed_artifacts as Array<Record<string, unknown>> | undefined)?.length ? (
                                        (expandedExecSnapshot?.changed_artifacts as Array<Record<string, unknown>>).map((artifact) => (
                                            <Paper key={String(artifact.id)} variant="outlined" sx={{ p: 1, borderRadius: 1 }}>
                                                <Typography variant="body2">{String(artifact.title || artifact.id)}</Typography>
                                                <Typography variant="caption" color="text.secondary">
                                                    {String(artifact.kind || "artifact")} · {artifact.created_at ? formatDateTime(String(artifact.created_at)) : "no timestamp"}
                                                </Typography>
                                            </Paper>
                                        ))
                                    ) : expandedArtifacts.length > 0 ? (
                                        expandedArtifacts.slice(0, 4).map((artifact) => (
                                            <Paper key={artifact.id} variant="outlined" sx={{ p: 1, borderRadius: 1 }}>
                                                <Typography variant="body2">{artifact.title}</Typography>
                                                <Typography variant="caption" color="text.secondary">
                                                    {artifact.kind} · {formatDateTime(artifact.created_at)}
                                                </Typography>
                                            </Paper>
                                        ))
                                    ) : (
                                        <Typography variant="caption" color="text.secondary">No artifacts yet.</Typography>
                                    )}
                                </Stack>

                                <Divider />

                                <Typography variant="subtitle2">Timeline</Typography>

                                <Stack spacing={0.75} sx={{ maxHeight: 220, overflow: "auto" }}>
                                    {timeline.length === 0 ? (
                                        <Typography variant="caption" color="text.secondary">
                                            No comments or GitHub sync events yet.
                                        </Typography>
                                    ) : (
                                        timeline.map((row) => (
                                            <Paper key={`${row.kind}-${row.id}`} variant="outlined" sx={{ p: 1, borderRadius: 1 }}>
                                                <Typography variant="caption" color="text.secondary">
                                                    {formatDateTime(row.created_at)} · {row.kind}
                                                </Typography>
                                                <Typography variant="body2">{row.title}</Typography>
                                                {row.body ? (
                                                    <Typography variant="caption" sx={{ display: "block", whiteSpace: "pre-wrap" }}>
                                                        {row.body}
                                                    </Typography>
                                                ) : null}
                                            </Paper>
                                        ))
                                    )}
                                </Stack>

                                <Divider />

                                <SubtaskPanel projectId={projectId} taskId={drawerTask.id} taskTitle={drawerTask.title} />

                                <Divider />

                                <ArtifactPanel taskId={drawerTask.id} />

                                <Divider />

                                <TaskMemoryInspector
                                    projectId={projectId}
                                    taskId={drawerTask.id}
                                    lastRunId={lastRun?.id}
                                />
                            </Stack>
                        </>
                    );
                })()}
                </Box>
            </Drawer>
            <ConfirmDestructiveDialog
                open={Boolean(deleteTaskTarget)}
                title="Delete task"
                description={
                    deleteTaskTarget
                        ? `Delete “${deleteTaskTarget.title}”? This cannot be undone.`
                        : ""
                }
                confirmLabel="Delete task"
                loading={deleteTaskMutation.isPending}
                onClose={() => setDeleteTaskTarget(null)}
                onConfirm={() => {
                    if (!deleteTaskTarget) return;
                    deleteTaskMutation.mutate(deleteTaskTarget.id, {
                        onSettled: () => {
                            setDeleteTaskTarget(null);
                            setExpandedTask(null);
                        },
                    });
                }}
            />
        </>
    );
}
