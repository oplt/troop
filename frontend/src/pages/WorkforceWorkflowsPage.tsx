import { useCallback, useMemo, useState } from "react";
import {
    addEdge,
    Background,
    Controls,
    MiniMap,
    ReactFlow,
    ReactFlowProvider,
    useEdgesState,
    useNodesState,
    useReactFlow,
    type Connection,
} from "@xyflow/react";
import {
    Alert,
    Box,
    Button,
    CircularProgress,
    Divider,
    Paper,
    Stack,
    Tab,
    Tabs,
    TextField,
    Typography,
} from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { getCanvasTheme } from "../features/canvas/canvasTheme";
import { Add, AutoAwesome, PlayArrow, Save, AccountTree as WorkflowIcon } from "@mui/icons-material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link as RouterLink } from "react-router-dom";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { DensePageMobileNotice } from "../components/ui/DensePageMobileNotice";
import { EmptyState } from "../components/ui/EmptyState";
import { InspectorSplit } from "../components/ui/InspectorSplit";
import { CanvasChrome } from "../components/canvas/CanvasChrome";
import {
    createWorkforceWorkflow,
    diffWorkforceWorkflow,
    diffWorkforceWorkflowEnvironment,
    generateWorkforceWorkflowDraft,
    getWorkforceWorkflow,
    listSkills,
    listWorkforceWorkflowEnvironmentHistory,
    listWorkforceWorkflowEnvironments,
    listWorkforceWorkflowVersions,
    listWorkforceWorkflows,
    promoteWorkforceWorkflowEnvironment,
    publishWorkforceWorkflow,
    rollbackWorkforceWorkflow,
    rollbackWorkforceWorkflowEnvironment,
    startWorkforceWorkflowRun,
    startWorkforceWorkflowTestRun,
    updateWorkforceWorkflowDraft,
    validateWorkforceWorkflow,
} from "../api/workforce";
import { listAgents } from "../api/orchestration";
import {
    getWorkflowRun,
    listConnectorDefinitions,
    listConnectorInstallations,
    listConnectorManifests,
    listConnectorOperations,
    listWorkflowRunSteps,
} from "../api/integrations";
import { useSnackbar } from "../app/snackbarContext";
import { queryKeys } from "../config/queryKeys";
import { queryPolicies } from "../config/queryPolicies";
import {
    isWorkflowRunTerminal,
    useWorkflowRunStepsStream,
    WORKFLOW_RUN_STEPS_FALLBACK_POLL_MS,
    workflowRunStreamHealthy,
} from "../hooks/useWorkflowRunStepsSync";
import {
    createWorkflowNode,
    emailTelegramStarter,
    toWorkflowPayload,
    WORKFLOW_NODE_TYPES,
    type WorkflowCanvasNode,
    type WorkflowNodeType,
} from "../features/workflows/builderState";
import { canvasFromWorkflowPayload } from "../features/workflows/graphFromPayload";
import { humanizeKey } from "../utils/formatters";
import { workflowNodeTypes } from "../features/workflows/workflowNodeTypes";
import { WorkflowNodeInspector } from "../features/workflows/WorkflowNodeInspector";
import { WorkflowEnvironmentPanel } from "../features/workflows/WorkflowEnvironmentPanel";
import { WorkflowScaffoldPanel } from "../features/workflows/WorkflowScaffoldPanel";
import { WorkflowValidationPanel } from "../features/workflows/WorkflowValidationPanel";
import { WorkflowVersionsPanel, WorkflowTestRunPanel } from "../features/workflows/WorkflowGovernancePanels";
import { WorkflowRunMonitor } from "../features/workflows/WorkflowRunMonitor";
import {
    buildNodeRunStatusMap,
    canSafelyRunFromNode,
} from "../features/workflows/runOverlay";
import {
    clientValidationIssues,
    mergeValidationIssues,
    serverValidationIssues,
    validationErrorCount,
} from "../features/workflows/validationIssues";

const initial = emailTelegramStarter();

type InspectorTab = "node" | "validation" | "test" | "versions" | "scaffold" | "environments";

function WorkflowBuilderCanvas({
    nodes,
    edges,
    selectedId,
    nodeRunStatuses,
    onNodesChange,
    onEdgesChange,
    onConnect,
    onNodeClick,
    onPaneClick,
}: {
    nodes: WorkflowCanvasNode[];
    edges: ReturnType<typeof useEdgesState>[0];
    selectedId: string | null;
    nodeRunStatuses: Map<string, import("../features/workflows/runOverlay").WorkflowNodeRunStatus>;
    onNodesChange: ReturnType<typeof useNodesState<WorkflowCanvasNode>>[2];
    onEdgesChange: ReturnType<typeof useEdgesState>[2];
    onConnect: (connection: Connection) => void;
    onNodeClick: (nodeId: string) => void;
    onPaneClick: () => void;
}) {
    const theme = useTheme();
    const canvas = getCanvasTheme(theme);
    const flowNodes = nodes.map((node) => ({
        ...node,
        type: "workflow" as const,
        selected: selectedId === node.id,
        data: {
            ...node.data,
            runStatus: nodeRunStatuses.get(node.id) ?? "idle",
        },
    }));

    return (
        <ReactFlow
            nodes={flowNodes}
            edges={edges}
            nodeTypes={workflowNodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, node) => onNodeClick(node.id)}
            onPaneClick={onPaneClick}
            fitView
            deleteKeyCode={["Backspace", "Delete"]}
            nodesConnectable
            elementsSelectable
            proOptions={{ hideAttribution: true }}
        >
            <Background color={canvas.backgroundDot} />
            <MiniMap pannable zoomable />
            <Controls showInteractive={false} />
        </ReactFlow>
    );
}

function WorkflowBuilderInner() {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const { setCenter } = useReactFlow();
    const [name, setName] = useState("Email Reply with Telegram Approval");
    const [slug, setSlug] = useState("email-reply-telegram-approval");
    const [activeWorkflowId, setActiveWorkflowId] = useState<string | null>(null);
    const [publishedVersionId, setPublishedVersionId] = useState<string | null>(null);
    const [nodes, setNodes, onNodesChange] = useNodesState<WorkflowCanvasNode>(initial.nodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);
    const [selectedId, setSelectedId] = useState<string | null>(initial.nodes[0]?.id ?? null);
    const [lastRunId, setLastRunId] = useState<string | null>(null);
    const [inspectorTab, setInspectorTab] = useState<InspectorTab>("node");
    const [fixtureJson, setFixtureJson] = useState("{}");
    const [selectedEnvironment, setSelectedEnvironment] = useState("dev");
    const [promoteVersionId, setPromoteVersionId] = useState("");

    const workflows = useQuery({ queryKey: ["workforce", "workflows"], queryFn: listWorkforceWorkflows });
    const installations = useQuery({ queryKey: ["integrations", "installations"], queryFn: listConnectorInstallations, retry: false });
    const definitions = useQuery({ queryKey: ["integrations", "definitions"], queryFn: listConnectorDefinitions, retry: false });
    const manifests = useQuery({ queryKey: ["integrations", "manifests"], queryFn: listConnectorManifests, retry: false });
    const operations = useQuery({ queryKey: ["integrations", "operations"], queryFn: () => listConnectorOperations(), retry: false });
    const agents = useQuery({ queryKey: ["orchestration", "agents"], queryFn: () => listAgents() });
    const skills = useQuery({ queryKey: ["workforce", "skills"], queryFn: listSkills });

    const serverValidation = useQuery({
        queryKey: queryKeys.workforce.workflowValidate(activeWorkflowId ?? ""),
        queryFn: () => validateWorkforceWorkflow(activeWorkflowId!),
        enabled: Boolean(activeWorkflowId),
        ...queryPolicies.operational,
        retry: false,
    });
    const workflowDiff = useQuery({
        queryKey: queryKeys.workforce.workflowDiff(activeWorkflowId ?? ""),
        queryFn: () => diffWorkforceWorkflow(activeWorkflowId!),
        enabled: Boolean(activeWorkflowId),
        ...queryPolicies.operational,
        retry: false,
    });
    const workflowVersions = useQuery({
        queryKey: queryKeys.workforce.workflowVersions(activeWorkflowId ?? ""),
        queryFn: () => listWorkforceWorkflowVersions(activeWorkflowId!),
        enabled: Boolean(activeWorkflowId),
        ...queryPolicies.operational,
        retry: false,
    });
    const workflowEnvironments = useQuery({
        queryKey: ["workforce", "workflow-environments", activeWorkflowId ?? ""],
        queryFn: () => listWorkforceWorkflowEnvironments(activeWorkflowId!),
        enabled: Boolean(activeWorkflowId),
        ...queryPolicies.operational,
        retry: false,
    });
    const workflowEnvironmentHistory = useQuery({
        queryKey: ["workforce", "workflow-environment-history", activeWorkflowId ?? "", selectedEnvironment],
        queryFn: () => listWorkforceWorkflowEnvironmentHistory(activeWorkflowId!, selectedEnvironment),
        enabled: Boolean(activeWorkflowId),
        ...queryPolicies.operational,
        retry: false,
    });
    const workflowEnvironmentDiff = useQuery({
        queryKey: ["workforce", "workflow-environment-diff", activeWorkflowId ?? "", selectedEnvironment, promoteVersionId],
        queryFn: () => diffWorkforceWorkflowEnvironment(activeWorkflowId!, selectedEnvironment, { version_id: promoteVersionId }),
        enabled: Boolean(activeWorkflowId && promoteVersionId),
        ...queryPolicies.operational,
        retry: false,
    });

    const workflowRun = useQuery({
        queryKey: queryKeys.workforce.workflowRun(lastRunId ?? ""),
        queryFn: () => getWorkflowRun(lastRunId!),
        enabled: Boolean(lastRunId),
        ...queryPolicies.operational,
        retry: false,
    });
    const runStatus = workflowRun.data?.status ?? null;
    const runMonitorActive = Boolean(lastRunId) && !isWorkflowRunTerminal(runStatus);
    const runStepsStream = useWorkflowRunStepsStream(lastRunId, runStatus, Boolean(lastRunId));
    const streamHealthy = workflowRunStreamHealthy(runStepsStream.status);
    const runSteps = useQuery({
        queryKey: queryKeys.workforce.workflowRunSteps(lastRunId ?? ""),
        queryFn: () => listWorkflowRunSteps(lastRunId!),
        enabled: Boolean(lastRunId),
        ...queryPolicies.operational,
        retry: false,
        refetchInterval: runMonitorActive && !streamHealthy ? WORKFLOW_RUN_STEPS_FALLBACK_POLL_MS : false,
    });

    const selected = nodes.find((node) => node.id === selectedId) ?? null;
    const clientIssues = useMemo(() => clientValidationIssues(nodes, edges), [nodes, edges]);
    const mergedIssues = useMemo(
        () => mergeValidationIssues(
            clientIssues,
            serverValidation.data ? serverValidationIssues(serverValidation.data) : [],
        ),
        [clientIssues, serverValidation.data],
    );
    const errorCount = validationErrorCount(mergedIssues);

    const graphSignature = useMemo(
        () => JSON.stringify({ name, slug, nodes: nodes.map((n) => ({ id: n.id, pos: n.position, data: n.data })), edges }),
        [name, slug, nodes, edges],
    );
    const [savedSignature, setSavedSignature] = useState(graphSignature);
    const graphDirty = graphSignature !== savedSignature;

    const nodeRunStatuses = useMemo(
        () => buildNodeRunStatusMap(
            nodes,
            runSteps.data ?? [],
            workflowRun.data?.current_node_id,
            workflowRun.data?.status,
        ),
        [nodes, runSteps.data, workflowRun.data?.current_node_id, workflowRun.data?.status],
    );

    const definitionById = new Map((definitions.data ?? []).map((item) => [item.id, item]));
    const safeInstallations = (installations.data ?? [])
        .filter((item) => !item.environment || item.environment === selectedEnvironment || selectedEnvironment === "dev")
        .map((item) => ({
        id: item.id,
        name: `${definitionById.get(item.connector_definition_id)?.name ?? "Connector"} · ${item.name} · ${item.environment ?? "dev"}`,
        status: item.status,
        providerSlug: definitionById.get(item.connector_definition_id)?.slug,
    }));

    const invalidateWorkflowGovernance = useCallback(async (workflowId: string) => {
        await Promise.all([
            queryClient.invalidateQueries({ queryKey: queryKeys.workforce.workflowValidate(workflowId) }),
            queryClient.invalidateQueries({ queryKey: queryKeys.workforce.workflowDiff(workflowId) }),
            queryClient.invalidateQueries({ queryKey: queryKeys.workforce.workflowVersions(workflowId) }),
            queryClient.invalidateQueries({ queryKey: ["workforce", "workflows"] }),
        ]);
    }, [queryClient]);

    const saveMutation = useMutation({
        mutationFn: async () => {
            const graph = toWorkflowPayload(nodes, edges);
            if (activeWorkflowId) {
                return updateWorkforceWorkflowDraft(activeWorkflowId, graph);
            }
            return createWorkforceWorkflow({
                name,
                slug,
                description: "Visual workforce graph workflow",
                category: "integration",
                ...graph,
            });
        },
        onSuccess: async (workflow) => {
            setActiveWorkflowId(workflow.id);
            setPublishedVersionId(workflow.published_version_id ?? null);
            setSavedSignature(graphSignature);
            await invalidateWorkflowGovernance(workflow.id);
            showToast({ message: "Workflow draft saved.", severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Save failed.", severity: "error" }),
    });

    const publishMutation = useMutation({
        mutationFn: () => publishWorkforceWorkflow(activeWorkflowId!),
        onSuccess: async (workflow) => {
            setPublishedVersionId(workflow.published_version_id ?? null);
            await invalidateWorkflowGovernance(workflow.id);
            showToast({ message: "Workflow published.", severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Publish failed.", severity: "error" }),
    });

    const rollbackMutation = useMutation({
        mutationFn: (versionId: string) => rollbackWorkforceWorkflow(activeWorkflowId!, versionId),
        onSuccess: async (workflow) => {
            setPublishedVersionId(workflow.published_version_id ?? null);
            await invalidateWorkflowGovernance(workflow.id);
            showToast({ message: "Workflow rolled back.", severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Rollback failed.", severity: "error" }),
    });

    const promoteEnvironmentMutation = useMutation({
        mutationFn: () => promoteWorkforceWorkflowEnvironment(activeWorkflowId!, selectedEnvironment, {
            version_id: promoteVersionId,
        }),
        onSuccess: async () => {
            await Promise.all([
                queryClient.invalidateQueries({ queryKey: ["workforce", "workflow-environments", activeWorkflowId] }),
                queryClient.invalidateQueries({ queryKey: ["workforce", "workflow-environment-history", activeWorkflowId, selectedEnvironment] }),
                invalidateWorkflowGovernance(activeWorkflowId!),
            ]);
            showToast({ message: `Promoted to ${selectedEnvironment}.`, severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Promotion failed.", severity: "error" }),
    });

    const rollbackEnvironmentMutation = useMutation({
        mutationFn: () => rollbackWorkforceWorkflowEnvironment(activeWorkflowId!, selectedEnvironment),
        onSuccess: async () => {
            await Promise.all([
                queryClient.invalidateQueries({ queryKey: ["workforce", "workflow-environments", activeWorkflowId] }),
                queryClient.invalidateQueries({ queryKey: ["workforce", "workflow-environment-history", activeWorkflowId, selectedEnvironment] }),
            ]);
            showToast({ message: `${selectedEnvironment} deployment rolled back.`, severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Environment rollback failed.", severity: "error" }),
    });

    const testRunMutation = useMutation({
        mutationFn: () => {
            let input: Record<string, unknown> = {};
            try {
                input = JSON.parse(fixtureJson || "{}") as Record<string, unknown>;
            } catch {
                throw new Error("Test fixture must be valid JSON.");
            }
            return startWorkforceWorkflowTestRun(activeWorkflowId!, { input });
        },
        onSuccess: (run) => {
            setLastRunId(run.id);
            void queryClient.invalidateQueries({ queryKey: queryKeys.workforce.workflowRun(run.id) });
            void queryClient.invalidateQueries({ queryKey: queryKeys.workforce.workflowRunSteps(run.id) });
            showToast({ message: `Test run ${run.id.slice(0, 8)} started (external writes simulated).`, severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Test run failed.", severity: "error" }),
    });

    const runMutation = useMutation({
        mutationFn: () => startWorkforceWorkflowRun(activeWorkflowId!, { input: {}, environment: selectedEnvironment }),
        onSuccess: (run) => {
            const id = typeof run.id === "string" ? run.id : null;
            setLastRunId(id);
            if (id) {
                void queryClient.invalidateQueries({ queryKey: queryKeys.workforce.workflowRun(id) });
                void queryClient.invalidateQueries({ queryKey: queryKeys.workforce.workflowRunSteps(id) });
            }
            showToast({ message: id ? `Workflow run ${id.slice(0, 8)} started.` : "Workflow started.", severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Run failed.", severity: "error" }),
    });

    const loadWorkflow = useMutation({
        mutationFn: (workflowId: string) => getWorkforceWorkflow(workflowId),
        onSuccess: (detail) => {
            setActiveWorkflowId(detail.id);
            setPublishedVersionId(detail.published_version_id ?? null);
            setName(detail.name);
            setSlug(detail.slug ?? detail.id);
            if (detail.draft) {
                const loaded = canvasFromWorkflowPayload(
                    detail.draft.nodes as Array<Record<string, unknown> & { id: string }>,
                    detail.draft.edges as Array<Record<string, unknown>>,
                );
                setNodes(loaded.nodes);
                setEdges(loaded.edges);
                setSelectedId(loaded.nodes[0]?.id ?? null);
            }
            const signature = JSON.stringify({
                name: detail.name,
                slug: detail.slug ?? detail.id,
                nodes: detail.draft?.nodes ?? [],
                edges: detail.draft?.edges ?? [],
            });
            setSavedSignature(signature);
            showToast({ message: `Loaded ${detail.name}.`, severity: "success" });
        },
        onError: (error) => showToast({ message: error instanceof Error ? error.message : "Load failed.", severity: "error" }),
    });

    const focusNode = useCallback((nodeId: string) => {
        setSelectedId(nodeId);
        setInspectorTab("node");
        const node = nodes.find((item) => item.id === nodeId);
        if (node) {
            setCenter(node.position.x + 98, node.position.y + 40, { zoom: 1.1, duration: 300 });
        }
    }, [nodes, setCenter]);

    const addNode = (type: WorkflowNodeType) => {
        const node = createWorkflowNode(type, nodes.length);
        setNodes((current) => [...current, node]);
        setSelectedId(node.id);
    };

    const useStarter = () => {
        const starter = emailTelegramStarter();
        setNodes(starter.nodes);
        setEdges(starter.edges);
        setSelectedId(starter.nodes[0]?.id ?? null);
        setName("Email Reply with Telegram Approval");
        setSlug("email-reply-telegram-approval");
        setActiveWorkflowId(null);
        setPublishedVersionId(null);
    };

    const applyScaffoldResult = useCallback((result: Awaited<ReturnType<typeof generateWorkforceWorkflowDraft>>) => {
        const loaded = canvasFromWorkflowPayload(
            result.draft.nodes as Array<Record<string, unknown> & { id: string }>,
            result.draft.edges as Array<Record<string, unknown>>,
        );
        setNodes(loaded.nodes);
        setEdges(loaded.edges);
        setSelectedId(loaded.nodes[0]?.id ?? null);
        setName(result.name);
        setSlug(result.slug);
        setActiveWorkflowId(result.workflow_id);
        setPublishedVersionId(null);
        const signature = JSON.stringify({
            name: result.name,
            slug: result.slug,
            nodes: result.draft.nodes,
            edges: result.draft.edges,
        });
        setSavedSignature(signature);
        void invalidateWorkflowGovernance(result.workflow_id);
        showToast({ message: "Generated draft loaded. Review gaps, test, then publish.", severity: "success" });
    }, [invalidateWorkflowGovernance, setEdges, setNodes, showToast]);

    const updateSelected = (node: WorkflowCanvasNode) => {
        setNodes((current) => current.map((item) => (item.id === node.id ? node : item)));
    };

    const deleteSelected = () => {
        if (!selectedId) return;
        setNodes((current) => current.filter((item) => item.id !== selectedId));
        setEdges((current) => current.filter((edge) => edge.source !== selectedId && edge.target !== selectedId));
        setSelectedId(null);
    };

    const canRunFromSelected = canSafelyRunFromNode(selectedId, nodes, edges);

    return (
        <PageShell maxWidth="xl">
            <Stack spacing={2}>
                <PageHeader
                    title="Workforce workflows"
                    description="Runnable event → agent → action graphs (instances). Blueprints live under Workflow templates."
                    actions={
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Button component={RouterLink} to="/workflow-templates" variant="outlined">
                                Workflow templates
                            </Button>
                            <Button startIcon={<AutoAwesome />} variant="outlined" onClick={() => setInspectorTab("scaffold")}>
                                Generate from prompt
                            </Button>
                            <Button startIcon={<AutoAwesome />} variant="outlined" onClick={useStarter}>
                                Email + Telegram starter
                            </Button>
                        </Stack>
                    }
                />
                <DensePageMobileNotice surface="Workforce workflows" />
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                    <Stack spacing={2}>
                        <Stack direction={{ xs: "column", sm: "row" }} gap={2} alignItems={{ sm: "center" }}>
                            <TextField label="Name" value={name} onChange={(event) => setName(event.target.value)} fullWidth size="small" />
                            <TextField label="Slug" value={slug} onChange={(event) => setSlug(event.target.value)} fullWidth size="small" />
                            {activeWorkflowId && (
                                <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
                                    Editing {activeWorkflowId.slice(0, 8)} · {humanizeKey(workflows.data?.find((w) => w.id === activeWorkflowId)?.status ?? "draft")}
                                </Typography>
                            )}
                        </Stack>
                        <Stack direction="row" gap={0.75} flexWrap="wrap" useFlexGap aria-label="Workflow node palette">
                            {WORKFLOW_NODE_TYPES.map((type) => (
                                <Button key={type} size="small" variant="outlined" startIcon={<Add />} onClick={() => addNode(type)}>
                                    {humanizeKey(type)}
                                </Button>
                            ))}
                        </Stack>
                        <InspectorSplit
                            hideSecondaryOnMobile={false}
                            secondaryWidth={380}
                            primary={
                                <CanvasChrome
                                    dirty={graphDirty}
                                    validationCount={errorCount}
                                    height={{ xs: 520, lg: 680 }}
                                    aria-label="Workflow graph editor"
                                >
                                    {() => (
                                        <WorkflowBuilderCanvas
                                            nodes={nodes}
                                            edges={edges}
                                            selectedId={selectedId}
                                            nodeRunStatuses={nodeRunStatuses}
                                            onNodesChange={onNodesChange}
                                            onEdgesChange={onEdgesChange}
                                            onConnect={(connection: Connection) => setEdges((current) => addEdge(connection, current))}
                                            onNodeClick={setSelectedId}
                                            onPaneClick={() => setSelectedId(null)}
                                        />
                                    )}
                                </CanvasChrome>
                            }
                            secondary={
                                <Paper variant="outlined" sx={{ p: 0, borderRadius: 1, minWidth: 0, overflow: "hidden" }}>
                                    <Tabs
                                        value={inspectorTab}
                                        onChange={(_, value: InspectorTab) => setInspectorTab(value)}
                                        variant="scrollable"
                                        scrollButtons="auto"
                                    >
                                        <Tab value="environments" label="Environments" />
                                        <Tab value="scaffold" label="Generate" />
                                        <Tab value="node" label="Inspector" />
                                        <Tab value="validation" label={`Validation${errorCount ? ` (${errorCount})` : ""}`} />
                                        <Tab value="test" label="Test" />
                                        <Tab value="versions" label="Versions" />
                                    </Tabs>
                                    <Box sx={{ p: 2 }}>
                                        {inspectorTab === "environments" && (
                                            <WorkflowEnvironmentPanel
                                                workflowId={activeWorkflowId}
                                                selectedEnvironment={selectedEnvironment}
                                                onEnvironmentChange={setSelectedEnvironment}
                                                environments={workflowEnvironments.data}
                                                environmentsLoading={workflowEnvironments.isLoading}
                                                versions={workflowVersions.data ?? []}
                                                promoteVersionId={promoteVersionId}
                                                onPromoteVersionChange={setPromoteVersionId}
                                                envDiff={workflowEnvironmentDiff.data ?? null}
                                                envDiffLoading={workflowEnvironmentDiff.isLoading}
                                                history={workflowEnvironmentHistory.data}
                                                onPromote={() => promoteEnvironmentMutation.mutate()}
                                                onRollback={() => rollbackEnvironmentMutation.mutate()}
                                                promotePending={promoteEnvironmentMutation.isPending}
                                                rollbackPending={rollbackEnvironmentMutation.isPending}
                                            />
                                        )}
                                        {inspectorTab === "scaffold" && (
                                            <WorkflowScaffoldPanel
                                                busy={saveMutation.isPending}
                                                onGenerate={(prompt) => generateWorkforceWorkflowDraft({
                                                    prompt,
                                                    workflow_id: activeWorkflowId,
                                                    name: name.trim() || undefined,
                                                    slug: slug.trim() || undefined,
                                                })}
                                                onApply={applyScaffoldResult}
                                                onFocusNode={focusNode}
                                            />
                                        )}
                                        {inspectorTab === "node" && (
                                            selected ? (
                                                <WorkflowNodeInspector
                                                    node={selected}
                                                    installations={safeInstallations}
                                                    operations={operations.data ?? []}
                                                    manifests={manifests.data ?? []}
                                                    agents={agents.data ?? []}
                                                    skills={skills.data ?? []}
                                                    workflows={workflows.data ?? []}
                                                    onChange={updateSelected}
                                                    onDelete={deleteSelected}
                                                />
                                            ) : (
                                                <Alert severity="info">
                                                    Select a node to edit its configuration. Drag from a handle to create an edge.
                                                </Alert>
                                            )
                                        )}
                                        {inspectorTab === "validation" && (
                                            <WorkflowValidationPanel
                                                issues={mergedIssues}
                                                serverValid={serverValidation.data?.valid ?? null}
                                                onFocusNode={focusNode}
                                            />
                                        )}
                                        {inspectorTab === "test" && (
                                            <WorkflowTestRunPanel
                                                workflowId={activeWorkflowId}
                                                selectedNodeId={selectedId}
                                                canRunFromSelected={canRunFromSelected}
                                                fixtureJson={fixtureJson}
                                                onFixtureChange={setFixtureJson}
                                                onTestRun={() => testRunMutation.mutate()}
                                                pending={testRunMutation.isPending}
                                            />
                                        )}
                                        {inspectorTab === "versions" && (
                                            <WorkflowVersionsPanel
                                                workflowId={activeWorkflowId}
                                                versions={workflowVersions.data ?? []}
                                                diff={workflowDiff.data ?? null}
                                                diffLoading={workflowDiff.isLoading}
                                                publishedVersionId={publishedVersionId}
                                                onPublish={() => publishMutation.mutate()}
                                                publishPending={publishMutation.isPending}
                                                onRollback={(versionId) => rollbackMutation.mutate(versionId)}
                                                rollbackPending={rollbackMutation.isPending}
                                            />
                                        )}
                                    </Box>
                                </Paper>
                            }
                        />
                        {(installations.isError || operations.isError) && (
                            <Alert severity="info">Connector metadata is unavailable. You can design the graph now, but publishing requires valid explicit connections.</Alert>
                        )}
                        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            <Button
                                startIcon={<Save />}
                                variant="contained"
                                onClick={() => saveMutation.mutate()}
                                disabled={saveMutation.isPending || errorCount > 0 || !name.trim() || !slug.trim()}
                            >
                                {activeWorkflowId ? "Save draft" : "Create draft"}
                            </Button>
                            {activeWorkflowId && (
                                <>
                                    <Button
                                        startIcon={<PlayArrow />}
                                        variant="outlined"
                                        onClick={() => runMutation.mutate()}
                                        disabled={runMutation.isPending}
                                    >
                                        Run published
                                    </Button>
                                    <Button
                                        variant="outlined"
                                        onClick={() => {
                                            setInspectorTab("test");
                                            testRunMutation.mutate();
                                        }}
                                        disabled={testRunMutation.isPending}
                                    >
                                        Quick test
                                    </Button>
                                </>
                            )}
                        </Stack>
                    </Stack>
                </Paper>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                    <Typography variant="h6">Definitions</Typography>
                    <Divider sx={{ my: 2 }} />
                    {workflows.isLoading ? <CircularProgress size={24} /> : workflows.isError ? (
                        <Alert severity="error">Could not load workflow definitions.</Alert>
                    ) : !workflows.data?.length ? (
                        <EmptyState
                            icon={<WorkflowIcon />}
                            title="No workflows yet"
                            description="Save a draft from the canvas, or load the Email + Telegram starter to begin."
                            action={
                                <Button startIcon={<AutoAwesome />} variant="contained" onClick={useStarter}>
                                    Email + Telegram starter
                                </Button>
                            }
                        />
                    ) : (
                        <Stack spacing={1}>
                            {workflows.data.map((workflow) => (
                                <Paper key={workflow.id} variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" gap={1} alignItems={{ sm: "center" }}>
                                        <Box>
                                            <Typography variant="subtitle2">{workflow.name}</Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {workflow.id} · {humanizeKey(workflow.status ?? "draft")}
                                                {workflow.published_version_id ? " · published" : ""}
                                            </Typography>
                                        </Box>
                                        <Stack direction="row" gap={1}>
                                            <Button
                                                variant={activeWorkflowId === workflow.id ? "contained" : "outlined"}
                                                onClick={() => loadWorkflow.mutate(workflow.id)}
                                                disabled={loadWorkflow.isPending}
                                            >
                                                {activeWorkflowId === workflow.id ? "Loaded" : "Load"}
                                            </Button>
                                        </Stack>
                                    </Stack>
                                </Paper>
                            ))}
                        </Stack>
                    )}
                </Paper>
                {lastRunId && (
                    <WorkflowRunMonitor
                        runId={lastRunId}
                        loading={runSteps.isLoading}
                        error={runSteps.isError}
                        steps={runSteps.data ?? []}
                    />
                )}
            </Stack>
        </PageShell>
    );
}

export default function WorkforceWorkflowsPage() {
    return (
        <ReactFlowProvider>
            <WorkflowBuilderInner />
        </ReactFlowProvider>
    );
}
