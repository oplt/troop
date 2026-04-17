import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    LinearProgress,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    Add as AddIcon,
    AutoAwesome as BrainstormIcon,
    Chat as ChatIcon,
    PlayArrow as RunIcon,
    PauseCircleOutline as PauseIcon,
    PlaylistAddCheckCircle as ApproveIcon,
    RateReview as RevisionIcon,
    SwapHoriz as ReassignIcon,
    DeleteOutline as RemoveIcon,
} from "@mui/icons-material";

import { useSnackbar } from "../../app/snackbarContext";
import {
    approveTaskOutput,
    assignHierarchyTask,
    createHierarchyTask,
    createTeamMember,
    fetchOperatingHierarchy,
    fetchOperatingModelProfiles,
    launchHierarchyTaskRun,
    removeTeamMember,
    requestTaskRevision,
    startHierarchyBrainstorm,
    type OperatingMember,
    type TeamMemberInput,
    updateTeamMember,
} from "../../api/orchestrationGraphql";
import { listOrchestrationProjects } from "../../api/orchestration";
import { formatDateTime } from "../../utils/formatters";
import { SectionCard } from "../ui/SectionCard";

type AgentOperatingConsoleProps = {
    projectId?: string;
};

const DEFAULT_MEMBER_FORM: TeamMemberInput = {
    project_id: "",
    name: "",
    role: "specialist",
    objective: "",
    skills: [],
    tool_access: [],
    memory_scope: "project",
    autonomy_level: "medium",
    approval_policy: "manager_review",
    is_manager: false,
};

const DEFAULT_TASK_FORM = {
    title: "",
    description: "",
    acceptance_criteria: "",
    assigned_member_id: "",
    reviewer_member_id: "",
    priority: "normal",
    task_type: "general",
    labels: "",
};

function statusColor(status: string) {
    if (status === "running" || status === "in_progress") return "success";
    if (status === "blocked") return "error";
    if (status === "needs_review" || status === "queued") return "warning";
    return "default";
}

function formatCost(micros: number) {
    return `$${(micros / 1_000_000).toFixed(4)}`;
}

function MemberDialog({
    open,
    onClose,
    onSubmit,
    projectId,
    modelOptions,
    initial,
}: {
    open: boolean;
    onClose: () => void;
    onSubmit: (payload: TeamMemberInput) => void;
    projectId: string;
    modelOptions: Array<{ id: string; display_name: string; provider_name: string | null; model_slug: string; provider_config_id: string | null }>;
    initial?: OperatingMember | null;
}) {
    const [form, setForm] = useState<TeamMemberInput>(() => ({
        ...DEFAULT_MEMBER_FORM,
        project_id: projectId,
        name: initial?.name ?? "",
        role: initial?.role ?? "specialist",
        objective: initial?.objective ?? "",
        skills: initial?.skills ?? [],
        tool_access: initial?.tool_access ?? [],
        memory_scope: initial?.memory_scope ?? "project",
        memory_policy: initial?.memory_policy ?? {},
        autonomy_level: initial?.autonomy_level ?? "medium",
        approval_policy: initial?.approval_policy ?? "manager_review",
        parent_member_id: initial?.parent_id ?? null,
        model_profile: initial?.model_profile
            ? {
                  provider_config_id: initial.model_profile.provider_config_id,
                  model_slug: initial.model_profile.model_slug,
              }
            : null,
        fallback_model_profile: initial?.fallback_model_profile
            ? {
                  provider_config_id: initial.fallback_model_profile.provider_config_id,
                  model_slug: initial.fallback_model_profile.model_slug,
              }
            : null,
        is_active: initial?.is_active ?? true,
    }));

    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>{initial ? "Edit team member" : "Add team member"}</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    <TextField label="Name" value={form.name ?? ""} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
                    <TextField label="Role" value={form.role ?? ""} onChange={(event) => setForm((current) => ({ ...current, role: event.target.value }))} />
                    <TextField label="Objective" multiline minRows={3} value={form.objective ?? ""} onChange={(event) => setForm((current) => ({ ...current, objective: event.target.value }))} />
                    <TextField label="Skills" helperText="Comma-separated" value={(form.skills ?? []).join(", ")} onChange={(event) => setForm((current) => ({ ...current, skills: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) }))} />
                    <TextField label="Tool access" helperText="Comma-separated" value={(form.tool_access ?? []).join(", ")} onChange={(event) => setForm((current) => ({ ...current, tool_access: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) }))} />
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                        <TextField select label="Primary model" fullWidth value={(form.model_profile as { id?: string; model_slug?: string } | null)?.model_slug ?? ""} onChange={(event) => {
                            const option = modelOptions.find((item) => item.model_slug === event.target.value);
                            setForm((current) => ({
                                ...current,
                                model_profile: option ? { provider_config_id: option.provider_config_id, model_slug: option.model_slug } : null,
                            }));
                        }}>
                            <MenuItem value="">None</MenuItem>
                            {modelOptions.map((item) => (
                                <MenuItem key={item.id} value={item.model_slug}>
                                    {item.display_name} {item.provider_name ? `• ${item.provider_name}` : ""}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField select label="Approval policy" fullWidth value={form.approval_policy ?? "manager_review"} onChange={(event) => setForm((current) => ({ ...current, approval_policy: event.target.value }))}>
                            <MenuItem value="auto">Auto</MenuItem>
                            <MenuItem value="manager_review">Manager review</MenuItem>
                            <MenuItem value="strict">Strict</MenuItem>
                        </TextField>
                    </Stack>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                        <TextField select label="Autonomy" fullWidth value={form.autonomy_level ?? "medium"} onChange={(event) => setForm((current) => ({ ...current, autonomy_level: event.target.value }))}>
                            <MenuItem value="low">Low</MenuItem>
                            <MenuItem value="medium">Medium</MenuItem>
                            <MenuItem value="high">High</MenuItem>
                        </TextField>
                        <TextField select label="Memory scope" fullWidth value={form.memory_scope ?? "project"} onChange={(event) => setForm((current) => ({ ...current, memory_scope: event.target.value }))}>
                            <MenuItem value="project">Project</MenuItem>
                            <MenuItem value="task">Task</MenuItem>
                            <MenuItem value="shared-team">Shared team</MenuItem>
                            <MenuItem value="private">Private</MenuItem>
                        </TextField>
                    </Stack>
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Cancel</Button>
                <Button variant="contained" onClick={() => onSubmit(form)}>
                    {initial ? "Save" : "Create"}
                </Button>
            </DialogActions>
        </Dialog>
    );
}

function TaskDialog({
    open,
    onClose,
    onSubmit,
    members,
}: {
    open: boolean;
    onClose: () => void;
    onSubmit: (payload: typeof DEFAULT_TASK_FORM) => void;
    members: OperatingMember[];
}) {
    const [form, setForm] = useState(DEFAULT_TASK_FORM);

    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>Create task</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    <TextField label="Title" value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
                    <TextField label="Description" multiline minRows={3} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} />
                    <TextField label="Acceptance criteria" multiline minRows={3} value={form.acceptance_criteria} onChange={(event) => setForm((current) => ({ ...current, acceptance_criteria: event.target.value }))} />
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                        <TextField select label="Assign to" fullWidth value={form.assigned_member_id} onChange={(event) => setForm((current) => ({ ...current, assigned_member_id: event.target.value }))}>
                            <MenuItem value="">Unassigned</MenuItem>
                            {members.map((member) => (
                                <MenuItem key={member.id} value={member.id}>
                                    {member.name}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField select label="Priority" fullWidth value={form.priority} onChange={(event) => setForm((current) => ({ ...current, priority: event.target.value }))}>
                            <MenuItem value="low">Low</MenuItem>
                            <MenuItem value="normal">Normal</MenuItem>
                            <MenuItem value="high">High</MenuItem>
                            <MenuItem value="urgent">Urgent</MenuItem>
                        </TextField>
                    </Stack>
                    <TextField label="Labels" helperText="Comma-separated" value={form.labels} onChange={(event) => setForm((current) => ({ ...current, labels: event.target.value }))} />
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Cancel</Button>
                <Button variant="contained" onClick={() => onSubmit(form)}>Create</Button>
            </DialogActions>
        </Dialog>
    );
}

function BrainstormDialog({
    open,
    onClose,
    members,
    onSubmit,
}: {
    open: boolean;
    onClose: () => void;
    members: OperatingMember[];
    onSubmit: (topic: string, participantIds: string[]) => void;
}) {
    const [topic, setTopic] = useState("");
    const [participantIds, setParticipantIds] = useState<string[]>(members.map((item) => item.id));

    return (
        <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
            <DialogTitle>Start brainstorm</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    <TextField label="Topic" value={topic} onChange={(event) => setTopic(event.target.value)} />
                    <TextField
                        select
                        SelectProps={{ multiple: true }}
                        label="Participants"
                        value={participantIds}
                        onChange={(event) => setParticipantIds(typeof event.target.value === "string" ? [event.target.value] : event.target.value)}
                    >
                        {members.map((member) => (
                            <MenuItem key={member.id} value={member.id}>
                                {member.name}
                            </MenuItem>
                        ))}
                    </TextField>
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Cancel</Button>
                <Button variant="contained" onClick={() => onSubmit(topic, participantIds)}>Start</Button>
            </DialogActions>
        </Dialog>
    );
}

export function AgentOperatingConsole({ projectId }: AgentOperatingConsoleProps) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
    const [memberDialogOpen, setMemberDialogOpen] = useState(false);
    const [editingMember, setEditingMember] = useState<OperatingMember | null>(null);
    const [taskDialogOpen, setTaskDialogOpen] = useState(false);
    const [brainstormDialogOpen, setBrainstormDialogOpen] = useState(false);

    const projectsQuery = useQuery({
        queryKey: ["orchestration", "projects", "control-plane-selector"],
        queryFn: listOrchestrationProjects,
    });
    const resolvedProjectId = projectId ?? projectsQuery.data?.[0]?.id ?? null;

    const hierarchyQuery = useQuery({
        queryKey: ["orchestration", "control-plane", resolvedProjectId],
        queryFn: () => fetchOperatingHierarchy(resolvedProjectId as string),
        enabled: Boolean(resolvedProjectId),
        refetchInterval: 5000,
    });
    const modelProfilesQuery = useQuery({
        queryKey: ["orchestration", "control-plane-models", resolvedProjectId],
        queryFn: () => fetchOperatingModelProfiles(resolvedProjectId as string),
        enabled: Boolean(resolvedProjectId),
    });

    const snapshot = hierarchyQuery.data;
    const members = snapshot?.members ?? [];
    const manager = members.find((member) => member.id === snapshot?.manager_id) ?? members[0] ?? null;
    const selectedMember = members.find((member) => member.id === (selectedMemberId ?? manager?.id)) ?? manager ?? null;
    const backlogTasks = members
        .flatMap((member) => member.tasks)
        .filter((task, index, list) => list.findIndex((item) => item.id === task.id) === index);

    async function refresh() {
        await queryClient.invalidateQueries({ queryKey: ["orchestration", "control-plane", resolvedProjectId] });
    }

    const createMemberMutation = useMutation({
        mutationFn: createTeamMember,
        onSuccess: async () => {
            await refresh();
            setMemberDialogOpen(false);
            setEditingMember(null);
            showToast({ message: "Team member created.", severity: "success" });
        },
        onError: (error) => {
            showToast({ message: error instanceof Error ? error.message : "Create member failed.", severity: "error" });
        },
    });
    const updateMemberMutation = useMutation({
        mutationFn: ({ memberId, input }: { memberId: string; input: TeamMemberInput }) => updateTeamMember(memberId, input),
        onSuccess: async () => {
            await refresh();
            setMemberDialogOpen(false);
            setEditingMember(null);
            showToast({ message: "Team member updated.", severity: "success" });
        },
    });
    const removeMemberMutation = useMutation({
        mutationFn: ({ memberId }: { memberId: string }) => removeTeamMember(resolvedProjectId as string, memberId),
        onSuccess: async () => {
            await refresh();
            showToast({ message: "Team member removed from hierarchy.", severity: "success" });
        },
    });
    const createTaskMutation = useMutation({
        mutationFn: createHierarchyTask,
        onSuccess: async () => {
            await refresh();
            setTaskDialogOpen(false);
            showToast({ message: "Task created.", severity: "success" });
        },
    });
    const brainstormMutation = useMutation({
        mutationFn: ({ topic, participantIds }: { topic: string; participantIds: string[] }) => startHierarchyBrainstorm(resolvedProjectId as string, topic, participantIds),
        onSuccess: async () => {
            await refresh();
            setBrainstormDialogOpen(false);
            showToast({ message: "Brainstorm started.", severity: "success" });
        },
    });
    const assignTaskMutation = useMutation({
        mutationFn: ({ taskId, memberId }: { taskId: string; memberId: string }) => assignHierarchyTask(resolvedProjectId as string, taskId, memberId),
        onSuccess: async () => {
            await refresh();
            showToast({ message: "Task reassigned.", severity: "success" });
        },
    });
    const runTaskMutation = useMutation({
        mutationFn: ({ taskId, memberId }: { taskId: string; memberId?: string }) => launchHierarchyTaskRun(resolvedProjectId as string, taskId, memberId),
        onSuccess: async () => {
            await refresh();
            showToast({ message: "Run queued.", severity: "success" });
        },
    });
    const approveTaskMutation = useMutation({
        mutationFn: ({ taskId }: { taskId: string }) => approveTaskOutput(resolvedProjectId as string, taskId),
        onSuccess: async () => {
            await refresh();
            showToast({ message: "Task approved.", severity: "success" });
        },
    });
    const revisionMutation = useMutation({
        mutationFn: ({ taskId, notes }: { taskId: string; notes: string }) => requestTaskRevision(resolvedProjectId as string, taskId, notes),
        onSuccess: async () => {
            await refresh();
            showToast({ message: "Revision requested.", severity: "success" });
        },
    });

    if (projectsQuery.isLoading || hierarchyQuery.isLoading) {
        return (
            <Stack spacing={2} alignItems="center" sx={{ py: 6 }}>
                <CircularProgress />
                <Typography color="text.secondary">Loading operating console...</Typography>
            </Stack>
        );
    }

    if (!resolvedProjectId) {
        return <Alert severity="info">Create orchestration project first. Control-plane console binds to project hierarchy.</Alert>;
    }

    if (hierarchyQuery.isError || !snapshot || !manager) {
        return (
            <Alert severity="error">
                {hierarchyQuery.error instanceof Error ? hierarchyQuery.error.message : "Control-plane hierarchy failed to load."}
            </Alert>
        );
    }

    return (
        <Stack spacing={2.5}>
            {(createMemberMutation.isPending || updateMemberMutation.isPending || createTaskMutation.isPending || brainstormMutation.isPending) && <LinearProgress />}

            <SectionCard
                title="Multi-agent operating console"
                description="GraphQL-backed control plane over project hierarchy, model routing, task assignment, run state, and review queue."
                action={
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Button startIcon={<AddIcon />} variant="contained" onClick={() => {
                            setEditingMember(null);
                            setMemberDialogOpen(true);
                        }}>
                            Add Team Member
                        </Button>
                        <Button startIcon={<AddIcon />} variant="outlined" onClick={() => setTaskDialogOpen(true)}>
                            Create Task
                        </Button>
                        <Button startIcon={<BrainstormIcon />} variant="outlined" onClick={() => setBrainstormDialogOpen(true)}>
                            Start Brainstorm
                        </Button>
                    </Stack>
                }
            >
                <Stack spacing={2.5}>
                    <Paper sx={{ p: 2.5, borderRadius: 4, border: "1px solid", borderColor: "divider", bgcolor: "rgba(34, 197, 94, 0.06)" }}>
                        <Stack direction={{ xs: "column", lg: "row" }} spacing={2} justifyContent="space-between">
                            <Box>
                                <Typography variant="overline" color="success.main">Manager</Typography>
                                <Typography variant="h5">{manager.name}</Typography>
                                <Typography variant="body2" color="text.secondary">{manager.role}</Typography>
                                <Typography variant="body2" sx={{ mt: 1 }}>{manager.objective || "No objective defined."}</Typography>
                            </Box>
                            <Stack spacing={1} alignItems={{ xs: "flex-start", lg: "flex-end" }}>
                                <Chip label={manager.model_profile?.display_name ?? "No model"} size="small" color="primary" variant="outlined" />
                                <Chip label={`Review queue ${snapshot.pending_approvals.filter((item) => item.status === "pending").length}`} size="small" variant="outlined" />
                                <Chip label={`Brainstorms ${snapshot.brainstorms.length}`} size="small" variant="outlined" />
                            </Stack>
                        </Stack>
                    </Paper>

                    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", xl: "minmax(0, 1.6fr) minmax(360px, 1fr)" }, gap: 2 }}>
                        <Box sx={{ display: "grid", gap: 1.5, gridTemplateColumns: { xs: "1fr", md: "repeat(2, minmax(0, 1fr))" } }}>
                            {members.filter((member) => member.id !== manager.id).map((member) => (
                                <Paper key={member.id} sx={{ p: 2, borderRadius: 4, border: "1px solid", borderColor: selectedMember?.id === member.id ? "primary.main" : "divider", boxShadow: selectedMember?.id === member.id ? "0 0 0 2px rgba(25, 118, 210, 0.12)" : "none" }}>
                                    <Stack spacing={1.25}>
                                        <Stack direction="row" justifyContent="space-between" spacing={1}>
                                            <Box onClick={() => setSelectedMemberId(member.id)} sx={{ cursor: "pointer" }}>
                                                <Typography variant="subtitle1">{member.name}</Typography>
                                                <Typography variant="body2" color="text.secondary">{member.role}</Typography>
                                            </Box>
                                            <Chip label={member.current_status.replaceAll("_", " ")} size="small" color={statusColor(member.current_status) as never} />
                                        </Stack>
                                        <Typography variant="body2" color="text.secondary">{member.objective || "No objective defined."}</Typography>
                                        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                            <Chip label={member.model_profile?.display_name ?? "No model"} size="small" variant="outlined" />
                                            <Chip label={`Workload ${member.workload_count}`} size="small" variant="outlined" />
                                            <Chip label={`${member.active_task_count} active`} size="small" variant="outlined" />
                                        </Stack>
                                        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                            {member.skills.slice(0, 4).map((skill) => (
                                                <Chip key={`${member.id}-${skill}`} label={skill} size="small" color="secondary" variant="outlined" />
                                            ))}
                                        </Stack>
                                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                            <Button size="small" onClick={() => {
                                                setEditingMember(member);
                                                setMemberDialogOpen(true);
                                            }}>
                                                Edit
                                            </Button>
                                            <Button size="small" onClick={() => setSelectedMemberId(member.id)}>View Tasks</Button>
                                            <Button size="small" startIcon={<ChatIcon />} onClick={() => setSelectedMemberId(member.id)}>Open Chat</Button>
                                            <Button size="small" startIcon={<ReassignIcon />} onClick={() => {
                                                const openTask = member.tasks.find((item) => item.status !== "completed" && item.status !== "approved");
                                                if (openTask) {
                                                    assignTaskMutation.mutate({ taskId: openTask.id, memberId: manager.id });
                                                }
                                            }}>
                                                Reassign
                                            </Button>
                                            <Button size="small" color="error" startIcon={<RemoveIcon />} onClick={() => removeMemberMutation.mutate({ memberId: member.id })}>
                                                Remove
                                            </Button>
                                            <Button
                                                size="small"
                                                startIcon={member.is_active ? <PauseIcon /> : <RunIcon />}
                                                onClick={() => updateMemberMutation.mutate({
                                                    memberId: member.id,
                                                    input: {
                                                        project_id: resolvedProjectId,
                                                        is_active: !member.is_active,
                                                    },
                                                })}
                                            >
                                                {member.is_active ? "Pause" : "Run"}
                                            </Button>
                                        </Stack>
                                    </Stack>
                                </Paper>
                            ))}
                        </Box>

                        <Paper sx={{ p: 2.5, borderRadius: 4, border: "1px solid", borderColor: "divider" }}>
                            {selectedMember ? (
                                <Stack spacing={2}>
                                    <Box>
                                        <Typography variant="overline" color="text.secondary">Selected agent</Typography>
                                        <Typography variant="h6">{selectedMember.name}</Typography>
                                        <Typography variant="body2" color="text.secondary">{selectedMember.role}</Typography>
                                    </Box>
                                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                        <Chip label={selectedMember.model_profile?.display_name ?? "No primary model"} size="small" variant="outlined" />
                                        <Chip label={`Autonomy ${selectedMember.autonomy_level}`} size="small" variant="outlined" />
                                        <Chip label={`Approval ${selectedMember.approval_policy}`} size="small" variant="outlined" />
                                        <Chip label={`Memory ${selectedMember.memory_scope}`} size="small" variant="outlined" />
                                    </Stack>
                                    <Typography variant="body2">{selectedMember.objective || "No objective defined."}</Typography>
                                    <Divider />
                                    <Box>
                                        <Typography variant="subtitle2" sx={{ mb: 1 }}>Tool access</Typography>
                                        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                            {selectedMember.tool_access.map((tool) => <Chip key={`${selectedMember.id}-${tool}`} label={tool} size="small" />)}
                                        </Stack>
                                    </Box>
                                    <Box>
                                        <Typography variant="subtitle2" sx={{ mb: 1 }}>Tasks</Typography>
                                        <Stack spacing={1}>
                                            {selectedMember.tasks.slice(0, 5).map((task) => (
                                                <Paper key={task.id} variant="outlined" sx={{ p: 1.25, borderRadius: 3 }}>
                                                    <Stack spacing={1}>
                                                        <Stack direction="row" justifyContent="space-between" spacing={1}>
                                                            <Typography variant="body2">{task.title}</Typography>
                                                            <Chip label={task.status.replaceAll("_", " ")} size="small" color={statusColor(task.status) as never} />
                                                        </Stack>
                                                        <Typography variant="caption" color="text.secondary">
                                                            Updated {formatDateTime(task.updated_at)}
                                                        </Typography>
                                                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                                                            <Button size="small" startIcon={<RunIcon />} onClick={() => runTaskMutation.mutate({ taskId: task.id, memberId: selectedMember.id })}>
                                                                Run
                                                            </Button>
                                                            <Button size="small" startIcon={<ApproveIcon />} onClick={() => approveTaskMutation.mutate({ taskId: task.id })}>
                                                                Approve
                                                            </Button>
                                                            <Button size="small" startIcon={<RevisionIcon />} onClick={() => revisionMutation.mutate({ taskId: task.id, notes: "Revision requested from hierarchy console." })}>
                                                                Revision
                                                            </Button>
                                                        </Stack>
                                                    </Stack>
                                                </Paper>
                                            ))}
                                            {selectedMember.tasks.length === 0 && (
                                                <Typography variant="body2" color="text.secondary">No assigned tasks.</Typography>
                                            )}
                                        </Stack>
                                    </Box>
                                    <Box>
                                        <Typography variant="subtitle2" sx={{ mb: 1 }}>Recent runs</Typography>
                                        <Stack spacing={1}>
                                            {selectedMember.runs.slice(0, 4).map((run) => (
                                                <Paper key={run.id} variant="outlined" sx={{ p: 1.25, borderRadius: 3 }}>
                                                    <Stack direction="row" justifyContent="space-between" spacing={1}>
                                                        <Box>
                                                            <Typography variant="body2">{run.run_mode}</Typography>
                                                            <Typography variant="caption" color="text.secondary">
                                                                {run.model_name || selectedMember.model_profile?.model_slug || "model pending"}
                                                            </Typography>
                                                        </Box>
                                                        <Stack spacing={0.5} alignItems="flex-end">
                                                            <Chip label={run.status.replaceAll("_", " ")} size="small" color={statusColor(run.status) as never} />
                                                            <Typography variant="caption" color="text.secondary">
                                                                {run.token_total.toLocaleString()} tokens • {formatCost(run.estimated_cost_micros)}
                                                            </Typography>
                                                        </Stack>
                                                    </Stack>
                                                </Paper>
                                            ))}
                                        </Stack>
                                    </Box>
                                </Stack>
                            ) : (
                                <Typography color="text.secondary">Select team member.</Typography>
                            )}
                        </Paper>
                    </Box>

                    <SectionCard title="Review queue" description="Pending approvals surfaced through GraphQL control plane.">
                        <Stack spacing={1}>
                            {snapshot.pending_approvals.length === 0 && (
                                <Typography variant="body2" color="text.secondary">No approvals pending.</Typography>
                            )}
                            {snapshot.pending_approvals.map((approval) => (
                                <Paper key={approval.id} variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                    <Stack direction="row" justifyContent="space-between" spacing={1}>
                                        <Box>
                                            <Typography variant="body2">{approval.approval_type}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {approval.task_id ? `Task ${approval.task_id}` : "No task"} • {formatDateTime(approval.created_at)}
                                            </Typography>
                                        </Box>
                                        <Chip label={approval.status} size="small" color={statusColor(approval.status) as never} />
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    </SectionCard>

                    <SectionCard title="Assignable backlog" description="Quick reassignment queue for manager-level routing.">
                        <Stack spacing={1}>
                            {backlogTasks.map((task) => (
                                <Paper key={task.id} variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                    <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1.5}>
                                        <Box>
                                            <Typography variant="body2">{task.title}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {task.task_type} • {task.priority} • {task.status}
                                            </Typography>
                                        </Box>
                                        <TextField
                                            select
                                            size="small"
                                            label="Assign"
                                            sx={{ minWidth: 220 }}
                                            defaultValue=""
                                            onChange={(event) => {
                                                if (event.target.value) {
                                                    assignTaskMutation.mutate({ taskId: task.id, memberId: event.target.value });
                                                }
                                            }}
                                        >
                                            <MenuItem value="">Choose agent</MenuItem>
                                            {members.map((member) => (
                                                <MenuItem key={`${task.id}-${member.id}`} value={member.id}>
                                                    {member.name}
                                                </MenuItem>
                                            ))}
                                        </TextField>
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    </SectionCard>
                </Stack>
            </SectionCard>

            <MemberDialog
                open={memberDialogOpen}
                onClose={() => {
                    setMemberDialogOpen(false);
                    setEditingMember(null);
                }}
                onSubmit={(payload) => {
                    if (editingMember) {
                        updateMemberMutation.mutate({ memberId: editingMember.id, input: { ...payload, project_id: resolvedProjectId } });
                    } else {
                        createMemberMutation.mutate({ ...payload, project_id: resolvedProjectId });
                    }
                }}
                projectId={resolvedProjectId}
                modelOptions={(modelProfilesQuery.data ?? []).map((item) => ({
                    id: item.id,
                    display_name: item.display_name,
                    provider_name: item.provider_name,
                    model_slug: item.model_slug,
                    provider_config_id: item.provider_config_id,
                }))}
                initial={editingMember}
            />

            <TaskDialog
                open={taskDialogOpen}
                onClose={() => setTaskDialogOpen(false)}
                onSubmit={(payload) => createTaskMutation.mutate({
                    project_id: resolvedProjectId,
                    title: payload.title,
                    description: payload.description || undefined,
                    assigned_member_id: payload.assigned_member_id || undefined,
                    reviewer_member_id: payload.reviewer_member_id || undefined,
                    acceptance_criteria: payload.acceptance_criteria || undefined,
                    priority: payload.priority,
                    task_type: payload.task_type,
                    labels: payload.labels.split(",").map((item) => item.trim()).filter(Boolean),
                })}
                members={members}
            />

            <BrainstormDialog
                open={brainstormDialogOpen}
                onClose={() => setBrainstormDialogOpen(false)}
                members={members}
                onSubmit={(topic, participantIds) => brainstormMutation.mutate({ topic, participantIds })}
            />
        </Stack>
    );
}
