import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    createWorkforceWorkflow,
    listWorkforceWorkflows,
    publishWorkforceWorkflow,
    startWorkforceWorkflowRun,
} from "../api/workforce";
import { useSnackbar } from "../app/snackbarContext";
import { PageShell } from "../components/ui/PageShell";

const NODE_TYPES = [
    "agent",
    "skill",
    "tool",
    "condition",
    "approval",
    "human_input",
    "parallel",
    "delay",
    "trigger",
] as const;

type DraftNode = { id: string; type: string; label: string };

export default function WorkforceWorkflowsPage() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [name, setName] = useState("Research workflow");
    const [slug, setSlug] = useState("research-workflow");
    const [nodes, setNodes] = useState<DraftNode[]>([
        { id: "n1", type: "agent", label: "Analyze" },
        { id: "n2", type: "skill", label: "Apply skills" },
        { id: "n3", type: "approval", label: "Human review" },
    ]);

    const { data: workflows = [], isLoading } = useQuery({
        queryKey: ["workforce", "workflows"],
        queryFn: listWorkforceWorkflows,
    });

    const createMutation = useMutation({
        mutationFn: () =>
            createWorkforceWorkflow({
                name,
                slug,
                description: "Workforce graph workflow",
                category: "general",
                nodes: nodes.map((n) => ({ id: n.id, type: n.type, label: n.label, config: {} })),
                edges: nodes.slice(0, -1).map((n, i) => ({
                    from: n.id,
                    to: nodes[i + 1].id,
                })),
                entry_node_id: nodes[0]?.id,
            }),
        onSuccess: () => {
            showToast({ message: "Workflow draft created", severity: "success" });
            queryClient.invalidateQueries({ queryKey: ["workforce", "workflows"] });
        },
        onError: (error: Error) => {
            showToast({ message: error.message, severity: "error" });
        },
    });

    const publishMutation = useMutation({
        mutationFn: (workflowId: string) => publishWorkforceWorkflow(workflowId),
        onSuccess: () => {
            showToast({ message: "Workflow published", severity: "success" });
            queryClient.invalidateQueries({ queryKey: ["workforce", "workflows"] });
        },
        onError: (error: Error) => {
            showToast({ message: error.message, severity: "error" });
        },
    });

    const runMutation = useMutation({
        mutationFn: (workflowId: string) => startWorkforceWorkflowRun(workflowId, { input: {} }),
        onSuccess: (run) => {
            showToast({
                message: `Run ${String(run.id)} status=${String(run.status)}`,
                severity: "success",
            });
        },
        onError: (error: Error) => {
            showToast({ message: error.message, severity: "error" });
        },
    });

    const palette = useMemo(() => NODE_TYPES, []);

    function addNode(type: string) {
        const id = `n${nodes.length + 1}`;
        setNodes((prev) => [...prev, { id, type, label: type }]);
    }

    return (
        <PageShell>
            <Stack spacing={3} sx={{ py: 3 }}>
                <Box>
                    <Typography variant="h4" gutterBottom>
                        Workforce workflows
                    </Typography>
                    <Typography color="text.secondary">
                        Create, publish, and run graph workflows (agent / skill / tool / approval nodes).
                    </Typography>
                </Box>

                <Paper sx={{ p: 3 }}>
                    <Stack spacing={2}>
                        <Typography variant="h6">Builder</Typography>
                        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                            <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} fullWidth />
                            <TextField label="Slug" value={slug} onChange={(e) => setSlug(e.target.value)} fullWidth />
                        </Stack>
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            {palette.map((type) => (
                                <Button key={type} size="small" variant="outlined" onClick={() => addNode(type)}>
                                    Add {type}
                                </Button>
                            ))}
                        </Stack>
                        <Stack spacing={1}>
                            {nodes.map((node, index) => (
                                <Stack key={node.id} direction="row" spacing={1} alignItems="center">
                                    <Chip label={node.id} size="small" />
                                    <TextField
                                        select
                                        size="small"
                                        label="Type"
                                        value={node.type}
                                        onChange={(e) =>
                                            setNodes((prev) =>
                                                prev.map((n, i) =>
                                                    i === index ? { ...n, type: e.target.value } : n
                                                )
                                            )
                                        }
                                        sx={{ minWidth: 160 }}
                                    >
                                        {palette.map((type) => (
                                            <MenuItem key={type} value={type}>
                                                {type}
                                            </MenuItem>
                                        ))}
                                    </TextField>
                                    <TextField
                                        size="small"
                                        label="Label"
                                        value={node.label}
                                        onChange={(e) =>
                                            setNodes((prev) =>
                                                prev.map((n, i) =>
                                                    i === index ? { ...n, label: e.target.value } : n
                                                )
                                            )
                                        }
                                        fullWidth
                                    />
                                </Stack>
                            ))}
                        </Stack>
                        <Button
                            variant="contained"
                            onClick={() => createMutation.mutate()}
                            disabled={createMutation.isPending || nodes.length === 0}
                        >
                            Save draft
                        </Button>
                    </Stack>
                </Paper>

                <Paper sx={{ p: 3 }}>
                    <Typography variant="h6" gutterBottom>
                        Definitions
                    </Typography>
                    {isLoading ? (
                        <CircularProgress />
                    ) : workflows.length === 0 ? (
                        <Alert severity="info">No workforce workflows yet.</Alert>
                    ) : (
                        <Stack spacing={1}>
                            {workflows.map((wf) => (
                                <Stack
                                    key={wf.id}
                                    direction={{ xs: "column", sm: "row" }}
                                    spacing={1}
                                    alignItems={{ sm: "center" }}
                                    justifyContent="space-between"
                                >
                                    <Box>
                                        <Typography fontWeight={600}>{wf.name}</Typography>
                                        <Typography variant="body2" color="text.secondary">
                                            {wf.id} · {wf.status || "draft"}
                                        </Typography>
                                    </Box>
                                    <Stack direction="row" spacing={1}>
                                        <Button
                                            size="small"
                                            onClick={() => publishMutation.mutate(wf.id)}
                                            disabled={publishMutation.isPending}
                                        >
                                            Publish
                                        </Button>
                                        <Button
                                            size="small"
                                            variant="contained"
                                            onClick={() => runMutation.mutate(wf.id)}
                                            disabled={runMutation.isPending}
                                        >
                                            Run
                                        </Button>
                                    </Stack>
                                </Stack>
                            ))}
                        </Stack>
                    )}
                </Paper>
            </Stack>
        </PageShell>
    );
}
