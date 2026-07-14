import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { Forum as BrainstormIcon } from "@mui/icons-material";
import { Link as RouterLink } from "react-router-dom";
import {
    createBrainstorm,
    listAgents,
    listBrainstorms,
    listOrchestrationProjects,
    listOrchestrationTasks,
    listProjectAgents,
    startBrainstorm,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime, humanizeKey } from "../utils/formatters";

const BRAINSTORM_MODES = [
    "exploration",
    "solution_design",
    "code_review",
    "incident_triage",
    "root_cause",
    "architecture_proposal",
] as const;

const OUTPUT_TYPES = ["adr", "implementation_plan", "test_plan", "issue_reply_draft", "risk_register"] as const;

function CreateBrainstormDialog({ onClose }: { onClose: () => void }) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [form, setForm] = useState({
        project_id: "",
        task_id: "",
        moderator_agent_id: "",
        topic: "",
        participant_agent_ids: [] as string[],
        mode: "exploration",
        output_type: "implementation_plan",
        max_rounds: "3",
        max_cost_usd: "10",
        max_repetition_score: "0.92",
        soft_consensus_min_similarity: "0.72",
        conflict_pairwise_max_similarity: "0.38",
        stop_on_consensus: true,
        accept_soft_consensus: true,
        conflict_requires_moderation: true,
        escalate_on_no_consensus: true,
    });

    const { data: projects = [] } = useQuery({
        queryKey: ["orchestration", "projects"],
        queryFn: listOrchestrationProjects,
    });
    const { data: agents = [] } = useQuery({
        queryKey: ["orchestration", "agents"],
        queryFn: () => listAgents(),
    });
    const { data: projectMembers = [] } = useQuery({
        queryKey: ["orchestration", "project", form.project_id, "agents"],
        queryFn: () => listProjectAgents(form.project_id),
        enabled: Boolean(form.project_id),
    });
    const projectAgentIds = useMemo(() => new Set(projectMembers.map((member) => member.agent_id)), [projectMembers]);
    const projectAgents = agents.filter((agent) => projectAgentIds.has(agent.id));
    const { data: tasks = [] } = useQuery({
        queryKey: ["orchestration", "project", form.project_id, "tasks"],
        queryFn: () => listOrchestrationTasks(form.project_id),
        enabled: Boolean(form.project_id),
    });

    const createMutation = useMutation({
        mutationFn: () =>
            createBrainstorm({
                project_id: form.project_id,
                task_id: form.task_id || null,
                moderator_agent_id: form.moderator_agent_id || null,
                topic: form.topic,
                participant_agent_ids: form.participant_agent_ids,
                mode: form.mode,
                output_type: form.output_type,
                max_rounds: Number(form.max_rounds || 3),
                max_cost_usd: Number(form.max_cost_usd || 10),
                max_repetition_score: Number(form.max_repetition_score || 0.92),
                stop_conditions: {
                    soft_consensus_min_similarity: Number(form.soft_consensus_min_similarity || 0.72),
                    conflict_pairwise_max_similarity: Number(form.conflict_pairwise_max_similarity || 0.38),
                    stop_on_consensus: form.stop_on_consensus,
                    accept_soft_consensus: form.accept_soft_consensus,
                    conflict_requires_moderation: form.conflict_requires_moderation,
                    escalate_on_no_consensus: form.escalate_on_no_consensus,
                },
            }),
        onSuccess: async (brainstorm) => {
            await startBrainstorm(brainstorm.id);
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "brainstorms"] });
            showToast({ message: "Brainstorm created.", severity: "success" });
            onClose();
        },
    });

    return (
        <Dialog open onClose={onClose} maxWidth="md" fullWidth>
            <DialogTitle>Create brainstorm</DialogTitle>
            <DialogContent>
                <Stack spacing={2} sx={{ mt: 1 }}>
                    <TextField
                        select
                        label="Project"
                        value={form.project_id}
                        onChange={(event) => setForm((current) => ({ ...current, project_id: event.target.value, task_id: "" }))}
                    >
                        {projects.map((project) => (
                            <MenuItem key={project.id} value={project.id}>{project.name}</MenuItem>
                        ))}
                    </TextField>
                    <TextField
                        label="Topic"
                        value={form.topic}
                        onChange={(event) => setForm((current) => ({ ...current, topic: event.target.value }))}
                    />
                    <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                        <TextField
                            select
                            label="Mode"
                            value={form.mode}
                            onChange={(event) => setForm((current) => ({ ...current, mode: event.target.value }))}
                            fullWidth
                        >
                            {BRAINSTORM_MODES.map((mode) => (
                                <MenuItem key={mode} value={mode}>{humanizeKey(mode)}</MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            select
                            label="Output type"
                            value={form.output_type}
                            onChange={(event) => setForm((current) => ({ ...current, output_type: event.target.value }))}
                            fullWidth
                        >
                            {OUTPUT_TYPES.map((output) => (
                                <MenuItem key={output} value={output}>{humanizeKey(output)}</MenuItem>
                            ))}
                        </TextField>
                    </Stack>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                        <TextField
                            select
                            label="Linked task"
                            value={form.task_id}
                            onChange={(event) => setForm((current) => ({ ...current, task_id: event.target.value }))}
                            fullWidth
                        >
                            <MenuItem value="">None</MenuItem>
                            {tasks.map((task) => (
                                <MenuItem key={task.id} value={task.id}>{task.title}</MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            select
                            label="Moderator agent"
                            value={form.moderator_agent_id}
                            onChange={(event) => setForm((current) => ({ ...current, moderator_agent_id: event.target.value }))}
                            fullWidth
                        >
                            <MenuItem value="">Auto / none</MenuItem>
                            {projectAgents.map((agent) => (
                                <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>
                            ))}
                        </TextField>
                    </Stack>
                    <TextField
                        select
                        SelectProps={{ multiple: true }}
                        label="Participants"
                        value={form.participant_agent_ids}
                        onChange={(event) => setForm((current) => ({
                            ...current,
                            participant_agent_ids: typeof event.target.value === "string" ? [event.target.value] : event.target.value,
                        }))}
                    >
                            {projectAgents.map((agent) => (
                            <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>
                        ))}
                    </TextField>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                        <TextField
                            label="Max rounds"
                            value={form.max_rounds}
                            onChange={(event) => setForm((current) => ({ ...current, max_rounds: event.target.value }))}
                            fullWidth
                        />
                        <TextField
                            label="Max cost USD"
                            value={form.max_cost_usd}
                            onChange={(event) => setForm((current) => ({ ...current, max_cost_usd: event.target.value }))}
                            fullWidth
                        />
                        <TextField
                            label="Max repetition score"
                            value={form.max_repetition_score}
                            onChange={(event) => setForm((current) => ({ ...current, max_repetition_score: event.target.value }))}
                            fullWidth
                        />
                    </Stack>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                        <TextField
                            label="Soft consensus floor"
                            type="number"
                            inputProps={{ min: 0, max: 1, step: 0.01 }}
                            value={form.soft_consensus_min_similarity}
                            onChange={(event) => setForm((current) => ({ ...current, soft_consensus_min_similarity: event.target.value }))}
                            helperText="Minimum pairwise similarity to accept soft consensus"
                            fullWidth
                        />
                        <TextField
                            label="Conflict similarity ceiling"
                            type="number"
                            inputProps={{ min: 0, max: 1, step: 0.01 }}
                            value={form.conflict_pairwise_max_similarity}
                            onChange={(event) => setForm((current) => ({ ...current, conflict_pairwise_max_similarity: event.target.value }))}
                            helperText="Below this, distinct positions are treated as conflict"
                            fullWidth
                        />
                    </Stack>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                        {([
                            ["stop_on_consensus", "Stop on consensus"],
                            ["accept_soft_consensus", "Accept soft consensus"],
                            ["conflict_requires_moderation", "Require moderation on conflict"],
                            ["escalate_on_no_consensus", "Escalate without consensus"],
                        ] as const).map(([key, label]) => (
                            <Button
                                key={key}
                                variant={form[key] ? "contained" : "outlined"}
                                onClick={() => setForm((current) => ({ ...current, [key]: !current[key] }))}
                                sx={{ flex: 1 }}
                            >
                                {label}: {form[key] ? "yes" : "no"}
                            </Button>
                        ))}
                    </Stack>
                    {createMutation.isError && (
                        <Alert severity="error">
                            {createMutation.error instanceof Error ? createMutation.error.message : "Couldn't start brainstorm. Try again."}
                        </Alert>
                    )}
                </Stack>
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Cancel</Button>
                <Button
                    variant="contained"
                    onClick={() => createMutation.mutate()}
                    disabled={!form.project_id || !form.topic.trim() || form.participant_agent_ids.length < 2 || createMutation.isPending}
                >
                    Create and start
                </Button>
            </DialogActions>
        </Dialog>
    );
}

export default function BrainstormsPage() {
    const [dialogOpen, setDialogOpen] = useState(false);
    const [search, setSearch] = useState("");
    const [projectFilter, setProjectFilter] = useState("");
    const [statusFilter, setStatusFilter] = useState<string>("");

    const { data: brainstorms = [] } = useQuery({
        queryKey: ["orchestration", "brainstorms"],
        queryFn: () => listBrainstorms(),
    });
    const { data: projects = [] } = useQuery({
        queryKey: ["orchestration", "projects"],
        queryFn: listOrchestrationProjects,
    });

    const filteredBrainstorms = useMemo(() => {
        return brainstorms.filter((item) => {
            if (projectFilter && item.project_id !== projectFilter) return false;
            if (statusFilter && item.status !== statusFilter) return false;
            if (search.trim()) {
                const q = search.trim().toLowerCase();
                const blob = `${item.topic} ${item.summary ?? ""} ${item.latest_round_summary ?? ""}`.toLowerCase();
                if (!blob.includes(q)) return false;
            }
            return true;
        });
    }, [brainstorms, projectFilter, statusFilter, search]);

    return (
        <PageShell maxWidth="xl">
            <Paper sx={{ p: 2, borderRadius: 1, mb: 2 }}>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                    <TextField
                        label="Search"
                        size="small"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Topic or summary"
                        fullWidth
                    />
                    <TextField
                        select
                        label="Project"
                        size="small"
                        value={projectFilter}
                        onChange={(e) => setProjectFilter(e.target.value)}
                        sx={{ minWidth: 200 }}
                    >
                        <MenuItem value="">All projects</MenuItem>
                        {projects.map((p) => (
                            <MenuItem key={p.id} value={p.id}>{p.name}</MenuItem>
                        ))}
                    </TextField>
                    <TextField
                        select
                        label="Status"
                        size="small"
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        sx={{ minWidth: 160 }}
                    >
                        <MenuItem value="">Any status</MenuItem>
                        <MenuItem value="running">Running</MenuItem>
                        <MenuItem value="completed">Completed</MenuItem>
                        <MenuItem value="draft">Draft</MenuItem>
                        <MenuItem value="paused">Paused</MenuItem>
                    </TextField>
                </Stack>
            </Paper>
            <SectionCard title="All brainstorms" description="Each room tracks mode, participants, rounds, guardrails, summaries, and promoted outputs.">
                {brainstorms.length === 0 ? (
                    <EmptyState icon={<BrainstormIcon />} title="No brainstorms yet" description="Create a room to coordinate structured discussion between multiple agents." />
                ) : filteredBrainstorms.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">No brainstorms match the current filters.</Typography>
                ) : (
                    <Stack spacing={1.5}>
                        {filteredBrainstorms.map((item) => (
                            <Paper key={item.id} sx={{ p: 2, borderRadius: 4 }}>
                                <Stack spacing={1}>
                                    <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1}>
                                        <Box>
                                            <Typography variant="subtitle1">{item.topic}</Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                {item.summary || item.latest_round_summary || item.final_recommendation || "No summary yet."}
                                            </Typography>
                                        </Box>
                                        <Button component={RouterLink} to={`/brainstorms/${item.id}`} variant="outlined" size="small">
                                            Open room
                                        </Button>
                                    </Stack>
                                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                        <Chip label={humanizeKey(item.mode)} size="small" color="secondary" variant="outlined" />
                                        <Chip label={humanizeKey(item.output_type)} size="small" variant="outlined" />
                                        <Chip label={`${item.participant_count} participants`} size="small" variant="outlined" />
                                        <Chip label={`Round ${item.current_round}/${item.max_rounds}`} size="small" variant="outlined" />
                                        <Chip label={humanizeKey(item.status)} size="small" color={item.status === "completed" ? "success" : "default"} />
                                        <Chip label={humanizeKey(item.consensus_status)} size="small" color={item.consensus_status === "consensus" ? "success" : "warning"} variant="outlined" />
                                    </Stack>
                                    <Typography variant="caption" color="text.secondary">
                                        Updated {formatDateTime(item.updated_at)}
                                    </Typography>
                                </Stack>
                            </Paper>
                        ))}
                    </Stack>
                )}
            </SectionCard>
            {dialogOpen && <CreateBrainstormDialog onClose={() => setDialogOpen(false)} />}
        </PageShell>
    );
}
