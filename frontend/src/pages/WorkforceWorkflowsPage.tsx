import { useMemo, useState } from "react";
import {
    addEdge,
    Background,
    Controls,
    MiniMap,
    ReactFlow,
    ReactFlowProvider,
    useEdgesState,
    useNodesState,
    type Connection,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
    Alert,
    Box,
    Button,
    Chip,
    CircularProgress,
    Divider,
    MenuItem,
    Paper,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import { Add, AutoAwesome, DeleteOutline, PlayArrow, Publish, Save } from "@mui/icons-material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link as RouterLink } from "react-router-dom";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import {
    createWorkforceWorkflow,
    listSkills,
    listWorkforceWorkflows,
    publishWorkforceWorkflow,
    startWorkforceWorkflowRun,
} from "../api/workforce";
import { listAgents } from "../api/orchestration";
import {
    listConnectorDefinitions,
    listConnectorInstallations,
    listConnectorOperations,
    listWorkflowRunSteps,
    type WorkflowStepRun,
} from "../api/integrations";
import { useSnackbar } from "../app/snackbarContext";
import {
    createWorkflowNode,
    emailTelegramStarter,
    safeRunValue,
    toWorkflowPayload,
    validateWorkflow,
    WORKFLOW_NODE_TYPES,
    type WorkflowCanvasNode,
    type WorkflowNodeType,
} from "../features/workflows/builderState";
import { formatDateTime, humanizeKey } from "../utils/formatters";

const initial = emailTelegramStarter();

function ConfigEditor({
    node,
    installations,
    operations,
    agents,
    skills,
    workflows,
    onChange,
    onDelete,
}: {
    node: WorkflowCanvasNode;
    installations: Array<{ id: string; name: string; status: string }>;
    operations: Array<{ slug: string; name: string }>;
    agents: Array<{ id: string; name: string }>;
    skills: Array<{ id: string; name: string }>;
    workflows: Array<{ id: string; name: string }>;
    onChange: (node: WorkflowCanvasNode) => void;
    onDelete: () => void;
}) {
    const config = node.data.config;
    const setConfig = (key: string, value: unknown) => onChange({
        ...node,
        data: { ...node.data, config: { ...config, [key]: value } },
    });
    const commonConnection = ["trigger", "tool"].includes(node.data.nodeType);

    return (
        <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="h6">Node configuration</Typography>
                <Button color="error" size="small" startIcon={<DeleteOutline />} onClick={onDelete}>Delete</Button>
            </Stack>
            <TextField
                label="Label"
                value={node.data.label}
                onChange={(event) => onChange({ ...node, data: { ...node.data, label: event.target.value } })}
                fullWidth
                size="small"
            />
            <TextField
                select
                label="Node type"
                value={node.data.nodeType}
                onChange={(event) => onChange({
                    ...node,
                    data: { ...node.data, nodeType: event.target.value as WorkflowNodeType },
                })}
                fullWidth
                size="small"
            >
                {WORKFLOW_NODE_TYPES.map((type) => <MenuItem key={type} value={type}>{humanizeKey(type)}</MenuItem>)}
            </TextField>
            {commonConnection && (
                <TextField
                    select
                    required
                    label="Connection"
                    value={String(config.connector_installation_id ?? "")}
                    onChange={(event) => setConfig("connector_installation_id", event.target.value)}
                    helperText="External actions fail closed without an explicit connector_installation_id."
                    fullWidth
                    size="small"
                >
                    <MenuItem value="">Select a connection</MenuItem>
                    {installations.map((item) => (
                        <MenuItem key={item.id} value={item.id}>{item.name} · {humanizeKey(item.status)}</MenuItem>
                    ))}
                </TextField>
            )}
            {node.data.nodeType === "trigger" && (
                <TextField
                    select
                    label="Event type"
                    value={String(config.event_type ?? "")}
                    onChange={(event) => setConfig("event_type", event.target.value)}
                    size="small"
                >
                    <MenuItem value="gmail_new_message">Gmail · new message</MenuItem>
                    <MenuItem value="manual">Manual</MenuItem>
                    <MenuItem value="schedule">Schedule</MenuItem>
                </TextField>
            )}
            {node.data.nodeType === "agent" && (
                <>
                    <TextField select label="Agent" value={String(config.agent_id ?? "")} onChange={(event) => setConfig("agent_id", event.target.value)} size="small">
                        <MenuItem value="">Runtime selection</MenuItem>
                        {agents.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
                    </TextField>
                    <TextField select label="Skill" value={String(config.skill_id ?? config.skill ?? "")} onChange={(event) => setConfig("skill_id", event.target.value)} size="small">
                        <MenuItem value="">No fixed skill</MenuItem>
                        {skills.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
                    </TextField>
                    <TextField label="Input mapping" value={String(config.input_mapping ?? "")} onChange={(event) => setConfig("input_mapping", event.target.value)} size="small" />
                </>
            )}
            {node.data.nodeType === "skill" && (
                <TextField select label="Skill" value={String(config.skill_id ?? "")} onChange={(event) => setConfig("skill_id", event.target.value)} size="small">
                    <MenuItem value="">Select skill</MenuItem>
                    {skills.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
                </TextField>
            )}
            {node.data.nodeType === "tool" && (
                <>
                    <TextField select label="Operation" value={String(config.operation ?? "")} onChange={(event) => setConfig("operation", event.target.value)} size="small">
                        <MenuItem value="">Select operation</MenuItem>
                        {operations.map((item) => <MenuItem key={item.slug} value={item.slug}>{item.name || item.slug}</MenuItem>)}
                    </TextField>
                    <TextField label="Argument mapping" value={String(config.argument_mapping ?? "")} onChange={(event) => setConfig("argument_mapping", event.target.value)} size="small" multiline minRows={2} />
                </>
            )}
            {["condition", "router"].includes(node.data.nodeType) && (
                <TextField label="Expression / routing rules" value={String(config.expression ?? config.rules ?? "")} onChange={(event) => setConfig(node.data.nodeType === "condition" ? "expression" : "rules", event.target.value)} multiline minRows={3} size="small" />
            )}
            {node.data.nodeType === "parallel" && (
                <TextField label="Completion policy" value={String(config.completion_policy ?? "all")} onChange={(event) => setConfig("completion_policy", event.target.value)} helperText="Examples: all, any, quorum" size="small" />
            )}
            {node.data.nodeType === "approval" && (
                <>
                    <TextField label="Action" required value={String(config.action ?? "")} onChange={(event) => setConfig("action", event.target.value)} size="small" helperText="For email sending use gmail.send_draft." />
                    <TextField select label="Delivery channel" value={String(config.delivery_channel ?? "troop")} onChange={(event) => setConfig("delivery_channel", event.target.value)} size="small">
                        <MenuItem value="troop">Troop</MenuItem>
                        <MenuItem value="telegram">Telegram</MenuItem>
                    </TextField>
                    <TextField label="Approver IDs" value={String(config.approvers ?? "")} onChange={(event) => setConfig("approvers", event.target.value)} size="small" helperText="Comma-separated IDs, or leave empty for policy resolution." />
                </>
            )}
            {node.data.nodeType === "human_input" && (
                <TextField label="Prompt" value={String(config.prompt ?? "")} onChange={(event) => setConfig("prompt", event.target.value)} multiline minRows={2} size="small" />
            )}
            {node.data.nodeType === "delay" && (
                <TextField label="Delay seconds" type="number" value={Number(config.delay_seconds ?? 60)} onChange={(event) => setConfig("delay_seconds", Number(event.target.value))} size="small" />
            )}
            {node.data.nodeType === "subworkflow" && (
                <TextField select label="Workflow" value={String(config.workflow_id ?? "")} onChange={(event) => setConfig("workflow_id", event.target.value)} size="small">
                    <MenuItem value="">Select workflow</MenuItem>
                    {workflows.map((item) => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
                </TextField>
            )}
            <Alert severity="info" sx={{ "& .MuiAlert-message": { overflow: "hidden" } }}>
                Saved as <code>config</code> on this node. Connections are serialized to <code>connector_installation_id</code>.
            </Alert>
        </Stack>
    );
}

function StepTimeline({ steps }: { steps: WorkflowStepRun[] }) {
    if (!steps.length) return <Alert severity="info">No workflow steps have been recorded yet.</Alert>;
    return (
        <Stack component="ol" spacing={1} sx={{ m: 0, pl: 3 }}>
            {steps.map((step) => {
                const started = step.started_at ? new Date(step.started_at).getTime() : null;
                const finished = step.finished_at ? new Date(step.finished_at).getTime() : null;
                const duration = started !== null && finished !== null ? Math.max(0, finished - started) : null;
                return (
                    <Paper component="li" key={step.id} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                        <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" gap={1}>
                            <Box>
                                <Typography variant="subtitle2">{step.node_id} · {humanizeKey(step.node_type)}</Typography>
                                <Typography variant="caption" color="text.secondary">
                                    {step.started_at ? formatDateTime(step.started_at) : "Not started"}
                                    {duration !== null ? ` · ${duration} ms` : ""} · retries {step.retry_count}
                                </Typography>
                            </Box>
                            <Chip label={humanizeKey(step.status)} size="small" color={step.status === "completed" ? "success" : step.status === "failed" ? "error" : step.status.includes("waiting") ? "warning" : "default"} />
                        </Stack>
                        {step.error && <Alert severity="error" sx={{ mt: 1 }}>{step.error}</Alert>}
                        {(Object.keys(step.input_json).length > 0 || Object.keys(step.output_json).length > 0) && (
                            <Box component="pre" sx={{ mt: 1, mb: 0, p: 1, bgcolor: "action.hover", borderRadius: 1, overflow: "auto", fontSize: "0.72rem", whiteSpace: "pre-wrap" }}>
                                {JSON.stringify(safeRunValue({ input: step.input_json, output: step.output_json }), null, 2)}
                            </Box>
                        )}
                    </Paper>
                );
            })}
        </Stack>
    );
}

function WorkflowBuilder() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [name, setName] = useState("Email Reply with Telegram Approval");
    const [slug, setSlug] = useState("email-reply-telegram-approval");
    const [nodes, setNodes, onNodesChange] = useNodesState<WorkflowCanvasNode>(initial.nodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);
    const [selectedId, setSelectedId] = useState<string | null>(initial.nodes[0].id);
    const [lastRunId, setLastRunId] = useState<string | null>(null);

    const workflows = useQuery({ queryKey: ["workforce", "workflows"], queryFn: listWorkforceWorkflows });
    const installations = useQuery({ queryKey: ["integrations", "installations"], queryFn: listConnectorInstallations, retry: false });
    const definitions = useQuery({ queryKey: ["integrations", "definitions"], queryFn: listConnectorDefinitions, retry: false });
    const operations = useQuery({ queryKey: ["integrations", "operations"], queryFn: () => listConnectorOperations(), retry: false });
    const agents = useQuery({ queryKey: ["orchestration", "agents"], queryFn: () => listAgents() });
    const skills = useQuery({ queryKey: ["workforce", "skills"], queryFn: listSkills });
    const runSteps = useQuery({
        queryKey: ["workforce", "workflow-runs", lastRunId, "steps"],
        queryFn: () => listWorkflowRunSteps(lastRunId!),
        enabled: Boolean(lastRunId),
        retry: false,
        refetchInterval: 3000,
    });

    const selected = nodes.find((node) => node.id === selectedId) ?? null;
    const errors = useMemo(() => validateWorkflow(nodes, edges), [nodes, edges]);
    const definitionById = new Map((definitions.data ?? []).map((item) => [item.id, item]));
    const safeInstallations = (installations.data ?? []).map((item) => ({
        id: item.id,
        name: `${definitionById.get(item.connector_definition_id)?.name ?? "Connector"} · ${item.name}`,
        status: item.status,
    }));

    const createMutation = useMutation({
        mutationFn: () => {
            const graph = toWorkflowPayload(nodes, edges);
            return createWorkforceWorkflow({
                name,
                slug,
                description: "Visual workforce graph workflow",
                category: "integration",
                ...graph,
            });
        },
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["workforce", "workflows"] });
            showToast({ message: "Workflow draft saved.", severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Save failed.", severity: "error" }),
    });
    const publishMutation = useMutation({
        mutationFn: (id: string) => publishWorkforceWorkflow(id),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["workforce", "workflows"] });
            showToast({ message: "Workflow published. Trigger registration will be validated by the server.", severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Publish failed.", severity: "error" }),
    });
    const runMutation = useMutation({
        mutationFn: (id: string) => startWorkforceWorkflowRun(id, { input: {} }),
        onSuccess: (run) => {
            const id = typeof run.id === "string" ? run.id : null;
            setLastRunId(id);
            showToast({ message: id ? `Workflow run ${id.slice(0, 8)} started.` : "Workflow started.", severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Run failed.", severity: "error" }),
    });

    const addNode = (type: WorkflowNodeType) => {
        const node = createWorkflowNode(type, nodes.length);
        setNodes((current) => [...current, node]);
        setSelectedId(node.id);
    };
    const useStarter = () => {
        const starter = emailTelegramStarter();
        setNodes(starter.nodes);
        setEdges(starter.edges);
        setSelectedId(starter.nodes[0].id);
        setName("Email Reply with Telegram Approval");
        setSlug("email-reply-telegram-approval");
    };
    const updateSelected = (node: WorkflowCanvasNode) => setNodes((current) => current.map((item) => item.id === node.id ? node : item));
    const deleteSelected = () => {
        if (!selectedId) return;
        setNodes((current) => current.filter((item) => item.id !== selectedId));
        setEdges((current) => current.filter((edge) => edge.source !== selectedId && edge.target !== selectedId));
        setSelectedId(null);
    };

    return (
        <PageShell maxWidth="xl">
            <Stack spacing={3} sx={{ py: 3 }}>
                <PageHeader
                    title="Workforce workflows"
                    description="Runnable event → agent → action graphs (instances). Blueprints live under Workflow templates."
                    actions={
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Button component={RouterLink} to="/workflow-templates" variant="outlined">
                                Workflow templates
                            </Button>
                            <Button startIcon={<AutoAwesome />} variant="outlined" onClick={useStarter}>
                                Email + Telegram starter
                            </Button>
                        </Stack>
                    }
                />
                {errors.length > 0 ? (
                    <Alert severity="error" role="alert">
                        Validation: {errors.join(" · ")}
                    </Alert>
                ) : null}
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                    <Stack spacing={2}>
                        <Stack direction={{ xs: "column", sm: "row" }} gap={2}>
                            <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} fullWidth size="small" />
                            <TextField label="Slug" value={slug} onChange={(event) => setSlug(event.target.value)} fullWidth size="small" />
                        </Stack>
                        <Stack direction="row" gap={0.75} flexWrap="wrap" useFlexGap aria-label="Workflow node palette">
                            {WORKFLOW_NODE_TYPES.map((type) => (
                                <Button key={type} size="small" variant="outlined" startIcon={<Add />} onClick={() => addNode(type)}>
                                    {humanizeKey(type)}
                                </Button>
                            ))}
                        </Stack>
                        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1fr) 360px" }, gap: 2 }}>
                            <Box
                                sx={{ height: { xs: 520, lg: 680 }, border: 1, borderColor: "divider", borderRadius: 1, overflow: "hidden" }}
                                aria-label="Workflow graph editor"
                            >
                                <ReactFlow
                                    nodes={nodes.map((node) => ({
                                        ...node,
                                        style: {
                                            border: selectedId === node.id ? "2px solid #2563eb" : "1px solid #94a3b8",
                                            borderRadius: 8,
                                            padding: 4,
                                            width: 190,
                                        },
                                        data: { ...node.data, label: `${humanizeKey(node.data.nodeType)}\n${node.data.label}` },
                                    }))}
                                    edges={edges}
                                    onNodesChange={onNodesChange}
                                    onEdgesChange={onEdgesChange}
                                    onConnect={(connection: Connection) => setEdges((current) => addEdge(connection, current))}
                                    onNodeClick={(_, node) => setSelectedId(node.id)}
                                    onPaneClick={() => setSelectedId(null)}
                                    fitView
                                    deleteKeyCode={["Backspace", "Delete"]}
                                    nodesConnectable
                                    elementsSelectable
                                >
                                    <Background />
                                    <MiniMap pannable zoomable />
                                    <Controls showInteractive />
                                </ReactFlow>
                            </Box>
                            <Paper variant="outlined" sx={{ p: 2, borderRadius: 1, minWidth: 0 }}>
                                {selected ? (
                                    <ConfigEditor
                                        node={selected}
                                        installations={safeInstallations}
                                        operations={operations.data ?? []}
                                        agents={agents.data ?? []}
                                        skills={skills.data ?? []}
                                        workflows={workflows.data ?? []}
                                        onChange={updateSelected}
                                        onDelete={deleteSelected}
                                    />
                                ) : <Alert severity="info">Select a node to edit its configuration. Drag from a node handle to create an edge.</Alert>}
                            </Paper>
                        </Box>
                        {errors.length > 0 && <Alert severity="warning">{errors.join(" ")}</Alert>}
                        {(installations.isError || operations.isError) && (
                            <Alert severity="info">Connector metadata is unavailable. You can design the graph now, but publishing requires valid explicit connections.</Alert>
                        )}
                        <Button startIcon={<Save />} variant="contained" onClick={() => createMutation.mutate()} disabled={createMutation.isPending || errors.length > 0 || !name.trim() || !slug.trim()}>
                            Save draft
                        </Button>
                    </Stack>
                </Paper>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                    <Typography variant="h6">Definitions</Typography>
                    <Divider sx={{ my: 2 }} />
                    {workflows.isLoading ? <CircularProgress size={24} /> : workflows.isError ? (
                        <Alert severity="error">Could not load workflow definitions.</Alert>
                    ) : !workflows.data?.length ? <Alert severity="info">No workflows yet.</Alert> : (
                        <Stack spacing={1}>
                            {workflows.data.map((workflow) => (
                                <Paper key={workflow.id} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" gap={1} alignItems={{ sm: "center" }}>
                                        <Box>
                                            <Typography variant="subtitle2">{workflow.name}</Typography>
                                            <Typography variant="caption" color="text.secondary">{workflow.id} · {humanizeKey(workflow.status ?? "draft")}</Typography>
                                        </Box>
                                        <Stack direction="row" gap={1}>
                                            <Button startIcon={<Publish />} onClick={() => publishMutation.mutate(workflow.id)} disabled={publishMutation.isPending}>Publish</Button>
                                            <Button startIcon={<PlayArrow />} variant="contained" onClick={() => runMutation.mutate(workflow.id)} disabled={runMutation.isPending}>Run</Button>
                                        </Stack>
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    )}
                </Paper>
                {lastRunId && (
                    <Paper component="section" aria-labelledby="workflow-run-heading" variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                        <Typography id="workflow-run-heading" variant="h6">Workflow run {lastRunId.slice(0, 8)}</Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Step metadata is redacted before rendering.</Typography>
                        {runSteps.isLoading ? <CircularProgress size={24} /> : runSteps.isError ? (
                            <Alert severity="warning">The workflow step endpoint is not available on this server yet.</Alert>
                        ) : <StepTimeline steps={runSteps.data ?? []} />}
                    </Paper>
                )}
            </Stack>
        </PageShell>
    );
}

export default function WorkforceWorkflowsPage() {
    return <ReactFlowProvider><WorkflowBuilder /></ReactFlowProvider>;
}
