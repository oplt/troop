// @ts-nocheck
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ReactElement } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import {
    Alert,
    Autocomplete,
    Box,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Drawer,
    IconButton,
    ListSubheader,
    MenuItem,
    Paper,
    Stack,
    Tab,
    Tabs,
    TextField,
    Tooltip,
    Typography,
    useMediaQuery,
} from "@mui/material";
import {
    Add as AddIcon,
    AutoGraph as LayoutIcon,
    Close as CloseIcon,
    CloudUpload as UploadIcon,
    ContentCopy as DuplicateIcon,
    DeleteOutline as DeleteIcon,
    DragIndicator as DragIndicatorIcon,
    Hub as GraphIcon,
    Save as SaveIcon,
    Engineering as SpecialistIcon,
    RestartAlt as ResetIcon,
    SmartToy as AgentIcon,
    TaskAlt as ValidateIcon,
} from "@mui/icons-material";
import { useTheme } from "@mui/material/styles";
import { getCanvasTheme } from "../../features/canvas/canvasTheme";
import {
    addEdge,
    ReactFlowProvider,
    useEdgesState,
    useNodesState,
    type Connection,
    type ReactFlowInstance,
} from "@xyflow/react";
import { AgentOperatingConsole } from "../../components/hierarchy/AgentOperatingConsole";
import {
    createAgent,
    createAgentTemplate,
    createTeamProfileFromTemplate,
    createTeamTemplate,
    deleteAgentTemplate,
    deleteSkillPack,
    deleteTeamTemplate,
    addProjectAgent,
    listAgents,
    listProjectAgents,
    updateAgent,
    updateAgentTemplate,
    updateHierarchyPolicy,
    updateOrchestrationProject,
    updateProjectAgent,
    updateSkillPack,
    updateTeamTemplate,
} from "../../api/orchestration";
import type {
    Agent,
    AgentTemplate,
    ProjectAgentMembership,
    SkillPack,
    TeamProfile,
    TeamTemplate,
} from "../../api/orchestration";
import { useSnackbar } from "../../app/snackbarContext";
import { queryKeys } from "../../config/queryKeys";
import { EmptyState } from "../../components/ui/EmptyState";
import { PageShell } from "../../components/ui/PageShell";
import { PageHeader } from "../../components/ui/PageHeader";
import { DensePageMobileNotice } from "../../components/ui/DensePageMobileNotice";
import { PageSkeleton } from "../../components/ui/PageSkeleton";
import { useDrawerFocus } from "../../hooks/useDrawerFocus";
import { SectionCard } from "../../components/ui/SectionCard";
import { AgentTemplateImportReviewDrawer } from "../../features/agentTemplateImport/AgentTemplateImportReviewDrawer";
import {
    createImportedSourceSummary,
    draftToAgentTemplateFormState,
    parseAgentTemplateMarkdown,
} from "../../features/agentTemplateImport/parser";
import type { AgentTemplateImportDraft } from "../../features/agentTemplateImport/types";
import { SkillTemplateImportReviewDrawer } from "../../features/skillTemplateImport/SkillTemplateImportReviewDrawer";
import { useHierarchyQueries } from "../../features/hierarchy/queries";
import { useHierarchyGraphState } from "../../features/hierarchy/graph/useHierarchyGraphState";
import { graphSignature } from "../../features/hierarchy/graph/graphSignature";
import {
    buildSkillForm,
    buildTeamTemplateForm,
    uniqueStrings,
    type SkillTemplateFormState,
    type TeamTemplateFormState,
} from "../../features/hierarchy/templates/templateState";
import {
    createSkillImportedSourceSummary,
    draftToSkillTemplateFormState,
    parseSkillTemplateMarkdown,
} from "../../features/skillTemplateImport/parser";
import type { SkillTemplateImportDraft } from "../../features/skillTemplateImport/types";
import {
    EMPTY_AGENT_TEMPLATE_FORM,
    buildAgentTemplateFormFromTemplate,
    buildAgentTemplatePayloadFromForm,
} from "../../features/agentTemplates/formState";
import { useHierarchyLiveState } from "../../features/hierarchy/live/useHierarchyLiveState";
import { buildHierarchyValidationIssues } from "../../features/hierarchy/validation";
import { formatDateTime } from "../../utils/formatters";


import {
    normalizeTeamGraphRole,
    parseCsv,
    parseLooseList,
    createUniqueSlug,
    createUniqueNodeId,
    normalizeAgentName,
    normalizeAgentSlug,
    clamp,
    normalizePermission,
    normalizeMemoryScope,
    normalizeOutputFormat,
    normalizeTaskFilters,
    stringifyCommaList,
    skillDisplayName,
    getTemplateBySlug,
    getRoleColor,
    buildNodeDataFromTemplate,
    buildTeamTemplateCanvasGraph,
    extractTeamTemplateCanvasLayout,
    applyTeamTemplateCanvasLayout,
    buildNodeDataFromAgent,
    autoLayoutGraph,
    createDefaultNodeData,
    cloneNodeData,
    buildNodeSubtitle,
    buildInitialTeamGraph,
    createSemanticEdge,
    readSavedTeamLayoutSnapshot,
    readSelectedHierarchyProjectId,
    persistSelectedHierarchyProjectId,
    readProjectTeamLayoutSnapshot,
    parsePositiveInteger,
    findManagerRootNode,
    sanitizeRuntimeTools,
    persistTeamLayoutSnapshot
} from "./hierarchyGraphUtils";
import {
    AGENT_ROLE_GUIDANCE,
    MEMORY_SCOPE_OPTIONS,
    OUTPUT_FORMAT_OPTIONS,
    PERMISSION_OPTIONS,
    ROLE_OPTIONS,
    TEAM_GRAPH_AUTOSAVE_DELAY_MS,
} from "./hierarchyTypes";
import type {
    BuilderTab,
    TeamGraphEdge,
    TeamGraphEdgeSemantic,
    TeamGraphNode,
    TeamGraphNodeData,
    TeamGraphRole,
    TeamLayoutSnapshot,
} from "./hierarchyTypes";
import { TeamGraphNodeCard } from "./TeamGraphNodeCard";

const HierarchyTeamReactFlow = lazy(() =>
    import("./HierarchyReactFlowCanvas").then((m) => ({ default: m.HierarchyTeamReactFlow })),
);
const HierarchyTemplatePreviewFlow = lazy(() =>
    import("./HierarchyReactFlowCanvas").then((m) => ({ default: m.HierarchyTemplatePreviewFlow })),
);

import { StringListField, TaskFiltersField, AgentEditorSection, ExpandableSection } from "./HierarchyFormFields";

const nodeTypes = {
    manager: TeamGraphNodeCard,
    team_lead: TeamGraphNodeCard,
    specialist: TeamGraphNodeCard,
    reviewer: TeamGraphNodeCard,
};

export default function AgentLibraryPage() {
    const location = useLocation();
    const navigate = useNavigate();
    const theme = useTheme();
    const canvas = getCanvasTheme(theme);
    const routeTab: BuilderTab = location.pathname === "/agent-hierarchy" || location.pathname === "/hierarchy-builder" || location.pathname === "/hierarchy"
        ? "hierarchy"
        : "library";
    const isCompact = useMediaQuery("(max-width:1199px)");
    const isWideHierarchyLayout = useMediaQuery("(min-width:1200px)");
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();

    const [form, setForm] = useState(EMPTY_AGENT_TEMPLATE_FORM);
    const [manualTab, setManualTab] = useState<BuilderTab | null>(null);
    const [addAgentDialogOpen, setAddAgentDialogOpen] = useState(false);
    const [agentToAddId, setAgentToAddId] = useState("");
    const [agentTemplateDrawerOpen, setAgentTemplateDrawerOpen] = useState(false);
    const [editingAgentTemplateSlug, setEditingAgentTemplateSlug] = useState<string | null>(null);
    const [agentTemplateImportDraft, setAgentTemplateImportDraft] = useState<AgentTemplateImportDraft | null>(null);
    const [agentTemplateImportReviewOpen, setAgentTemplateImportReviewOpen] = useState(false);
    const [agentTemplateImportBanner, setAgentTemplateImportBanner] = useState<{
        fileName: string;
        rawMarkdown: string;
        bannerText: string;
        warningCount: number;
    } | null>(null);
    const [skillTemplateDrawerOpen, setSkillTemplateDrawerOpen] = useState(false);
    const [editingSkillSlug, setEditingSkillSlug] = useState<string | null>(null);
    const [skillTemplateImportDraft, setSkillTemplateImportDraft] = useState<SkillTemplateImportDraft | null>(null);
    const [skillTemplateImportReviewOpen, setSkillTemplateImportReviewOpen] = useState(false);
    const [skillTemplateImportBanner, setSkillTemplateImportBanner] = useState<{
        fileName: string;
        rawMarkdown: string;
        bannerText: string;
        warningCount: number;
    } | null>(null);
    const [teamTemplateDrawerOpen, setTeamTemplateDrawerOpen] = useState(false);
    const [editingTeamTemplateId, setEditingTeamTemplateId] = useState<string | null>(null);
    const [skillForm, setSkillForm] = useState<SkillTemplateFormState>(buildSkillForm());
    const [teamTemplateForm, setTeamTemplateForm] = useState<TeamTemplateFormState>(buildTeamTemplateForm());
    const [teamTemplateCanvasNodes, setTeamTemplateCanvasNodes, onTeamTemplateCanvasNodesChange] = useNodesState<TeamGraphNode>([]);
    const [teamTemplateCanvasEdges, setTeamTemplateCanvasEdges] = useEdgesState<TeamGraphEdge>([]);
    const [selectedTeamTemplateCanvasNodeId, setSelectedTeamTemplateCanvasNodeId] = useState<string | null>(null);
    const [draggingItem, setDraggingItem] = useState<{ type: "skill" | "agent-template"; slug: string } | null>(null);
    const [activeDropTarget, setActiveDropTarget] = useState<{ kind: "agent-template" | "team-template"; id: string } | null>(null);
    const [edgeSemanticDraft, setEdgeSemanticDraft] = useState<TeamGraphEdgeSemantic>("delegates_to");
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
    const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
    const [savedLayout, setSavedLayout] = useState<TeamLayoutSnapshot | null>(() => readSavedTeamLayoutSnapshot());
    const [selectedHierarchyProjectId, setSelectedHierarchyProjectId] = useState<string>(() => readSelectedHierarchyProjectId());
    const [showValidationPanel, setShowValidationPanel] = useState(false);
    const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<TeamGraphNode, TeamGraphEdge> | null>(null);
    const [graphDirty, setGraphDirty] = useState(false);
    const [showMiniMap, setShowMiniMap] = useState(true);
    const [consoleOpen, setConsoleOpen] = useState(false);
    const consolePanelRef = useRef(null);
    useDrawerFocus(consoleOpen, consolePanelRef);
    const [inspectorWidth, setInspectorWidth] = useState(360);
    const [isResizingInspector, setIsResizingInspector] = useState(false);
    const [teamNodeDrawerOpen, setTeamNodeDrawerOpen] = useState(false);
    const [editingTeamNodeId, setEditingTeamNodeId] = useState<string | null>(null);
    const [teamNodeDraft, setTeamNodeDraft] = useState<TeamGraphNodeData | null>(null);
    const [teamNodeSaving, setTeamNodeSaving] = useState(false);

    useEffect(() => {
        if (!isResizingInspector || !isWideHierarchyLayout) {
            return undefined;
        }

        function handlePointerMove(event: MouseEvent) {
            const nextWidth = Math.min(520, Math.max(300, window.innerWidth - event.clientX - 32));
            setInspectorWidth(nextWidth);
        }

        function stopResizing() {
            setIsResizingInspector(false);
        }

        window.addEventListener("mousemove", handlePointerMove);
        window.addEventListener("mouseup", stopResizing);

        return () => {
            window.removeEventListener("mousemove", handlePointerMove);
            window.removeEventListener("mouseup", stopResizing);
        };
    }, [isResizingInspector, isWideHierarchyLayout]);

    const hierarchyQueries = useHierarchyQueries(selectedHierarchyProjectId);
    const { data: agents = [], isLoading: agentsLoading } = hierarchyQueries.agents;
    const { data: runs = [] } = hierarchyQueries.runs;
    const { data: templates = [], isLoading: templatesLoading } = hierarchyQueries.templates;
    const { data: skills = [] } = hierarchyQueries.skills;
    const { data: teamTemplates = [] } = hierarchyQueries.teamTemplates;
    const { data: teamProfiles = [] } = hierarchyQueries.teamProfiles;
    const { data: orchestrationProjects = [], isLoading: projectsLoading } = hierarchyQueries.orchestrationProjects;
    const hierarchyBootstrapping = agentsLoading || templatesLoading || projectsLoading;
    const effectiveHierarchyProjectId = selectedHierarchyProjectId && orchestrationProjects.some((project) => project.id === selectedHierarchyProjectId)
        ? selectedHierarchyProjectId
        : (orchestrationProjects[0]?.id ?? "");
    const selectedHierarchyProject = useMemo(
        () => orchestrationProjects.find((project) => project.id === effectiveHierarchyProjectId) ?? null,
        [effectiveHierarchyProjectId, orchestrationProjects],
    );
    const projectSavedLayout = useMemo(
        () => readProjectTeamLayoutSnapshot(selectedHierarchyProject),
        [selectedHierarchyProject],
    );
    const { data: hierarchyAgents = [] } = hierarchyQueries.hierarchyAgents;
    const { data: providerConfigs = [] } = hierarchyQueries.providerConfigs;
    const { data: modelCapabilities = [] } = hierarchyQueries.modelCapabilities;
    const savedProviderModelGroups = useMemo(() => {
        const perProvider = new Map<string, { label: string; models: string[] }>();
        for (const provider of providerConfigs) {
            const bucket =
                perProvider.get(provider.id) ?? {
                    label: `${provider.name} (${provider.provider_type})`,
                    models: [],
                };
            if (provider.default_model && !bucket.models.includes(provider.default_model)) {
                bucket.models.push(provider.default_model);
            }
            if (provider.fallback_model && !bucket.models.includes(provider.fallback_model)) {
                bucket.models.push(provider.fallback_model);
            }
            perProvider.set(provider.id, bucket);
        }
        for (const capability of modelCapabilities) {
            if (!capability.provider_id) continue;
            const bucket = perProvider.get(capability.provider_id);
            if (!bucket) continue;
            if (!bucket.models.includes(capability.model_slug)) {
                bucket.models.push(capability.model_slug);
            }
        }
        return [...perProvider.values()].filter((bucket) => bucket.models.length > 0);
    }, [providerConfigs, modelCapabilities]);
    const savedProviderModelsFlat = useMemo(
        () => new Set(savedProviderModelGroups.flatMap((bucket) => bucket.models)),
        [savedProviderModelGroups],
    );
    const renderSavedProviderModelMenuItems = useCallback(
        (currentValue: string, mode: "primary" | "fallback") => {
            const items: ReactElement[] = [];
            if (mode === "fallback") {
                items.push(
                    <MenuItem key="__provider-models-none" value="">
                        None
                    </MenuItem>,
                );
            } else {
                items.push(
                    <MenuItem key="__provider-model-unset" value="">
                        Not set (use project or agent default)
                    </MenuItem>,
                );
            }
            for (const bucket of savedProviderModelGroups) {
                items.push(
                    <ListSubheader key={`__provider-header-${bucket.label}`} disableSticky>
                        {bucket.label}
                    </ListSubheader>,
                );
                for (const model of bucket.models) {
                    items.push(
                        <MenuItem key={`${bucket.label}:${model}`} value={model}>
                            {model}
                        </MenuItem>,
                    );
                }
            }
            if (currentValue && !savedProviderModelsFlat.has(currentValue)) {
                items.push(
                    <MenuItem key={`__provider-custom-${currentValue}`} value={currentValue}>
                        {currentValue} (custom)
                    </MenuItem>,
                );
            }
            return items;
        },
        [savedProviderModelGroups, savedProviderModelsFlat],
    );

    useHierarchyLiveState(effectiveHierarchyProjectId || null);

    useEffect(() => {
        persistSelectedHierarchyProjectId(selectedHierarchyProjectId);
    }, [selectedHierarchyProjectId]);

    const activeTab = manualTab ?? routeTab;
    const agentRoleGuidance = AGENT_ROLE_GUIDANCE[form.role as keyof typeof AGENT_ROLE_GUIDANCE] ?? AGENT_ROLE_GUIDANCE.specialist;
    const selectedTeamAgentTemplates = useMemo(
        () => teamTemplateForm.agent_template_slugs
            .map((slug) => templates.find((item) => item.slug === slug) ?? null)
            .filter((item): item is AgentTemplate => Boolean(item)),
        [teamTemplateForm.agent_template_slugs, templates],
    );
    const selectedTeamTemplateCanvasNode = useMemo(
        () => teamTemplateCanvasNodes.find((node) => node.id === selectedTeamTemplateCanvasNodeId) ?? null,
        [selectedTeamTemplateCanvasNodeId, teamTemplateCanvasNodes],
    );
    const derivedTeamTemplateSummary = useMemo(() => {
        const roles = uniqueStrings(selectedTeamAgentTemplates.map((item) => item.role));
        const tools = uniqueStrings(selectedTeamAgentTemplates.flatMap((item) => item.allowed_tools));
        const skillsUsed = uniqueStrings(selectedTeamAgentTemplates.flatMap((item) => item.skills));
        return {
            roles,
            tools,
            skillsUsed,
        };
    }, [selectedTeamAgentTemplates]);

    const agentLiveStatus = useMemo(() => {
        const map = new Map<string, "running" | "blocked" | "queued" | "idle">();
        for (const run of runs) {
            const status = String((run as { status?: string }).status || "");
            const worker = String((run as { worker_agent_id?: string | null }).worker_agent_id || "");
            if (!worker) continue;
            if (status === "blocked") {
                map.set(worker, "blocked");
                continue;
            }
            if (status === "in_progress" && map.get(worker) !== "blocked") {
                map.set(worker, "running");
                continue;
            }
            if (status === "queued" && !map.has(worker)) {
                map.set(worker, "queued");
            }
        }
        return map;
    }, [runs]);

    const initialGraph = useMemo(() => buildInitialTeamGraph(hierarchyAgents, agentLiveStatus), [agentLiveStatus, hierarchyAgents]);
    const { nodes, setNodes, onNodesChange, edges, setEdges, onEdgesChange } =
        useHierarchyGraphState<TeamGraphNode, TeamGraphEdge>(initialGraph);
    const initialGraphStateSignature = useMemo(
        () => graphSignature(initialGraph.nodes, initialGraph.edges),
        [initialGraph],
    );
    const effectiveSavedLayout = projectSavedLayout ?? savedLayout;
    const savedLayoutSignature = useMemo(
        () => effectiveSavedLayout ? graphSignature(effectiveSavedLayout.nodes, effectiveSavedLayout.edges) : null,
        [effectiveSavedLayout],
    );
    const currentGraphStateSignature = useMemo(
        () => graphSignature(nodes, edges),
        [edges, nodes],
    );

    useEffect(() => {
        if (effectiveSavedLayout && !graphDirty && savedLayoutSignature && currentGraphStateSignature !== savedLayoutSignature) {
            setNodes(effectiveSavedLayout.nodes);
            setEdges(effectiveSavedLayout.edges);
            return;
        }
        if (!effectiveSavedLayout && !graphDirty && currentGraphStateSignature !== initialGraphStateSignature) {
            setNodes(initialGraph.nodes);
            setEdges(initialGraph.edges);
        }
    }, [
        currentGraphStateSignature,
        effectiveSavedLayout,
        graphDirty,
        initialGraph,
        initialGraphStateSignature,
        savedLayoutSignature,
        setEdges,
        setNodes,
    ]);

    useEffect(() => {
        if (!graphDirty) {
            return undefined;
        }

        const timeout = window.setTimeout(() => {
            const snapshot: TeamLayoutSnapshot = {
                savedAt: new Date().toISOString(),
                nodes,
                edges,
                persistence: "local-only",
            };
            setSavedLayout(snapshot);
            persistTeamLayoutSnapshot(snapshot);
            setGraphDirty(false);
        }, TEAM_GRAPH_AUTOSAVE_DELAY_MS);

        return () => window.clearTimeout(timeout);
    }, [edges, graphDirty, nodes]);

    useEffect(() => {
        if (selectedNodeId) {
            setConsoleOpen(true);
        }
    }, [selectedNodeId]);

    useEffect(() => {
        if (!consoleOpen) return undefined;
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                setConsoleOpen(false);
            }
        };
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [consoleOpen]);

    const handleFlowNodesChange = useCallback<typeof onNodesChange>((changes) => {
        onNodesChange(changes);
        setGraphDirty(true);
    }, [onNodesChange]);

    const handleFlowEdgesChange = useCallback<typeof onEdgesChange>((changes) => {
        onEdgesChange(changes);
        setGraphDirty(true);
    }, [onEdgesChange]);

    const handleFlowConnect = useCallback((connection: Connection) => {
        if (!connection.source || !connection.target) return;

        setEdges((current) =>
            addEdge(createSemanticEdge(connection.source, connection.target, edgeSemanticDraft), current),
        );
        setGraphDirty(true);
    }, [edgeSemanticDraft, setEdges]);

    const workspaceHasProviders = providerConfigs.length > 0;
    const validationIssues = useMemo(
        () => buildHierarchyValidationIssues(nodes, edges, workspaceHasProviders),
        [nodes, edges, workspaceHasProviders],
    );
    const selectedNode = useMemo(() => nodes.find((node) => node.id === selectedNodeId) ?? null, [nodes, selectedNodeId]);
    const selectedEdge = useMemo(() => edges.find((edge) => edge.id === selectedEdgeId) ?? null, [edges, selectedEdgeId]);

    const stringOptions = useMemo(() => ({
        capabilities: Array.from(new Set([...templates.flatMap((item) => item.capabilities), ...skills.flatMap((item) => item.capabilities), ...agents.flatMap((item) => item.capabilities), ...hierarchyAgents.flatMap((item) => item.capabilities)])).sort(),
        tools: Array.from(new Set([...templates.flatMap((item) => item.allowed_tools), ...skills.flatMap((item) => item.allowed_tools), ...agents.flatMap((item) => item.allowed_tools), ...hierarchyAgents.flatMap((item) => item.allowed_tools)])).sort(),
        tags: Array.from(new Set([...templates.flatMap((item) => item.tags), ...skills.flatMap((item) => item.tags), ...agents.flatMap((item) => item.tags), ...hierarchyAgents.flatMap((item) => item.tags)])).sort(),
        projects: orchestrationProjects.map((project) => project.name),
    }), [agents, hierarchyAgents, orchestrationProjects, skills, templates]);

    const createAgentTemplateMutation = useMutation({
        mutationFn: createAgentTemplate,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agentTemplates });
            showToast({ message: "Agent template created.", severity: "success" });
        },
    });

    const updateAgentTemplateMutation = useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<Omit<AgentTemplate, "id">> }) =>
            updateAgentTemplate(id, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agentTemplates });
            showToast({ message: "Agent template updated.", severity: "success" });
        },
    });

    const deleteAgentTemplateMutation = useMutation({
        mutationFn: deleteAgentTemplate,
        onSuccess: async () => {
            await Promise.all([
                queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agentTemplates }),
                queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agents() }),
                queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projectRoot }),
            ]);
            showToast({ message: "Agent template removed.", severity: "success" });
        },
        onError: (err) => {
            showToast({ message: err instanceof Error ? err.message : "Template removal failed.", severity: "error" });
        },
    });

    const updateSkillMutation = useMutation({
        mutationFn: ({ slug, payload }: { slug: string; payload: Partial<Omit<SkillPack, "id" | "slug">> }) => updateSkillPack(slug, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.skillCatalog });
            showToast({ message: "Skill template updated.", severity: "success" });
        },
    });
    const deleteSkillMutation = useMutation({
        mutationFn: deleteSkillPack,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.skillCatalog });
            showToast({ message: "Skill template removed.", severity: "success" });
        },
    });
    const createTeamTemplateMutation = useMutation({
        mutationFn: createTeamTemplate,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.teamTemplates });
            showToast({ message: "Team template created.", severity: "success" });
        },
    });
    const updateTeamTemplateMutation = useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<Omit<TeamTemplate, "id" | "slug">> }) => updateTeamTemplate(id, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.teamTemplates });
            showToast({ message: "Team template updated.", severity: "success" });
        },
    });
    const deleteTeamTemplateMutation = useMutation({
        mutationFn: deleteTeamTemplate,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.teamTemplates });
            showToast({ message: "Team template removed.", severity: "success" });
        },
    });
    const createTeamProfileMutation = useMutation({
        mutationFn: ({ templateId, name }: { templateId: string; name?: string }) =>
            createTeamProfileFromTemplate({ template_id: templateId, name }),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.teamProfiles });
            showToast({ message: "Team profile saved from template.", severity: "success" });
        },
    });
    const saveTeamGraphMutation = useMutation({
        mutationFn: async () => {
            if (!effectiveHierarchyProjectId || !selectedHierarchyProject) {
                throw new Error("Select a project before saving this team graph.");
            }
            const managerRoot = findManagerRootNode(nodes, edges);
            if (!managerRoot) {
                throw new Error("Team graph needs one manager before it can be saved.");
            }

            const memberships = await listProjectAgents(effectiveHierarchyProjectId);
            const membershipByAgentId = new Map<string, ProjectAgentMembership>(
                memberships.map((membership) => [membership.agent_id, membership]),
            );
            const existingGraphAgents = new Map(hierarchyAgents.map((agent) => [agent.id, agent]));
            const reservedSlugs = new Set([...agents, ...hierarchyAgents].map((agent) => agent.slug));
            const nodeToAgentId = new Map<string, string>();
            const savedAgentById = new Map<string, Agent>();
            const sortedNodes = [...nodes].sort((left, right) => {
                if (left.data.role === "manager" && right.data.role !== "manager") return -1;
                if (left.data.role !== "manager" && right.data.role === "manager") return 1;
                return left.data.name.localeCompare(right.data.name);
            });
            const templateSlugSet = new Set(templates.map((template) => template.slug));

            const membershipSaveOrder = [...sortedNodes].sort((a, b) => {
                const aReviewer = a.data.role === "reviewer" ? 0 : 1;
                const bReviewer = b.data.role === "reviewer" ? 0 : 1;
                return aReviewer - bReviewer;
            });
            for (const node of membershipSaveOrder) {
                const existingAgent = node.data.linkedAgentId
                    ? existingGraphAgents.get(node.data.linkedAgentId) ?? agents.find((agent) => agent.id === node.data.linkedAgentId) ?? null
                    : null;
                const normalizedName = normalizeAgentName(node.data.name, existingAgent?.name ?? "Untitled agent");
                const resolvedTemplateSlug = node.data.linkedTemplateSlug && templateSlugSet.has(node.data.linkedTemplateSlug)
                    ? node.data.linkedTemplateSlug
                    : null;
                const normalizedSlug = normalizeAgentSlug(
                    node.data.slug,
                    existingAgent?.slug ?? normalizedName,
                );
                const normalizedPermission = normalizePermission(node.data.permission);
                const normalizedMemoryScope = normalizeMemoryScope(node.data.memoryScope);
                const normalizedOutputFormat = normalizeOutputFormat(node.data.outputFormat);
                const normalizedTaskFilters = normalizeTaskFilters(node.data.taskFilters);
                const normalizedBudget = {
                    ...(existingAgent?.budget ?? {}),
                    token_budget: clamp(parsePositiveInteger(node.data.tokenBudget, 8000), 1, 1_000_000),
                    time_budget_seconds: clamp(parsePositiveInteger(node.data.timeBudgetSeconds, 300), 10, 86_400),
                    retry_budget: clamp(parsePositiveInteger(node.data.retryBudget, 1), 0, 20),
                };
                const modelPolicy = {
                    ...(existingAgent?.model_policy ?? {}),
                    model: node.data.model || null,
                    fallback_model: node.data.fallbackModel || null,
                    escalation_path: node.data.escalationPath || null,
                    permissions: normalizedPermission,
                };
                const memoryPolicy = {
                    ...(existingAgent?.memory_policy ?? {}),
                    scope: normalizedMemoryScope,
                };
                const outputSchema = {
                    ...(existingAgent?.output_schema ?? {}),
                    format: normalizedOutputFormat,
                };
                const metadata = {
                    ...(existingAgent?.metadata ?? {}),
                    task_filters: normalizedTaskFilters,
                    hierarchy_builder: {
                        node_id: node.id,
                        project_id: effectiveHierarchyProjectId,
                        saved_at: new Date().toISOString(),
                        desired_model: node.data.model || null,
                        desired_fallback_model: node.data.fallbackModel || null,
                    },
                };

                let savedAgent: Agent;
                if (existingAgent) {
                    savedAgent = await updateAgent(existingAgent.id, {
                        name: normalizedName,
                        slug: normalizedSlug,
                        description: node.data.description.trim(),
                        role: node.data.role,
                        parent_template_slug: resolvedTemplateSlug || existingAgent.parent_template_slug || null,
                        capabilities: node.data.capabilities,
                        allowed_tools: sanitizeRuntimeTools(node.data.allowedTools),
                        tags: node.data.tags,
                        model_policy: modelPolicy,
                        memory_policy: memoryPolicy,
                        output_schema: outputSchema,
                        budget: normalizedBudget,
                        timeout_seconds: clamp(parsePositiveInteger(node.data.timeBudgetSeconds, existingAgent.timeout_seconds || 300), 10, 14400),
                        retry_limit: clamp(parsePositiveInteger(node.data.retryBudget, existingAgent.retry_limit || 1), 0, 10),
                        task_filters: normalizedTaskFilters,
                        metadata,
                    });
                } else {
                    const preferredSlug = normalizeAgentSlug(node.data.slug || normalizedName, normalizedName);
                    let nextSlug = reservedSlugs.has(preferredSlug)
                        ? createUniqueSlug(preferredSlug, Array.from(reservedSlugs))
                        : preferredSlug;
                    let createAttempt = 0;
                    while (true) {
                        createAttempt += 1;
                        try {
                            savedAgent = await createAgent({
                                project_id: effectiveHierarchyProjectId,
                                parent_template_slug: resolvedTemplateSlug,
                                name: normalizedName,
                                slug: nextSlug,
                                description: node.data.description.trim(),
                                role: node.data.role,
                                capabilities: node.data.capabilities,
                                allowed_tools: sanitizeRuntimeTools(node.data.allowedTools),
                                tags: node.data.tags,
                                model_policy: modelPolicy,
                                memory_policy: memoryPolicy,
                                output_schema: outputSchema,
                                budget: normalizedBudget,
                                timeout_seconds: clamp(parsePositiveInteger(node.data.timeBudgetSeconds, 300), 10, 14400),
                                retry_limit: clamp(parsePositiveInteger(node.data.retryBudget, 1), 0, 10),
                                task_filters: normalizedTaskFilters,
                                metadata,
                            });
                            reservedSlugs.add(savedAgent.slug);
                            break;
                        } catch (error) {
                            const message = error instanceof Error ? error.message : "";
                            const isSlugConflict = message.toLowerCase().includes("slug already exists");
                            if (!isSlugConflict || createAttempt >= 3) {
                                throw error;
                            }
                            const latestAgents = await listAgents();
                            for (const existing of latestAgents) {
                                reservedSlugs.add(existing.slug);
                            }
                            nextSlug = createUniqueSlug(preferredSlug, Array.from(reservedSlugs));
                        }
                    }
                }

                nodeToAgentId.set(node.id, savedAgent.id);
                savedAgentById.set(savedAgent.id, savedAgent);

                const existingMembership = membershipByAgentId.get(savedAgent.id);
                const shouldBeDefaultManager = node.id === managerRoot.id;
                if (existingMembership) {
                    if (existingMembership.role !== node.data.role || existingMembership.is_default_manager !== shouldBeDefaultManager) {
                        const updatedMembership = await updateProjectAgent(effectiveHierarchyProjectId, existingMembership.id, {
                            role: node.data.role,
                            is_default_manager: shouldBeDefaultManager,
                        });
                        membershipByAgentId.set(savedAgent.id, updatedMembership);
                    }
                } else {
                    const membership = await addProjectAgent(effectiveHierarchyProjectId, {
                        agent_id: savedAgent.id,
                        role: node.data.role,
                        is_default_manager: shouldBeDefaultManager,
                    });
                    membershipByAgentId.set(savedAgent.id, membership);
                }
            }

            for (const node of sortedNodes) {
                const agentId = nodeToAgentId.get(node.id);
                if (!agentId) {
                    continue;
                }
                const currentAgent = savedAgentById.get(agentId);
                if (!currentAgent) {
                    continue;
                }
                const incomingHierarchyEdges = edges.filter(
                    (edge) =>
                        edge.target === node.id &&
                        (edge.data?.semantic === "delegates_to" || edge.data?.semantic === "escalates_to"),
                );
                const reviewerEdges = edges.filter(
                    (edge) => edge.target === node.id && edge.data?.semantic === "reviews",
                );
                const parentAgentId = incomingHierarchyEdges.length > 0 ? nodeToAgentId.get(incomingHierarchyEdges[0].source) ?? null : null;
                const reviewerAgentId = reviewerEdges.length > 0 ? nodeToAgentId.get(reviewerEdges[0].source) ?? null : null;
                const escalationTarget = nodes.find(
                    (candidate) =>
                        candidate.id === node.data.escalationPath ||
                        candidate.data.slug === node.data.escalationPath ||
                        candidate.data.name === node.data.escalationPath,
                );
                const escalationSlug = escalationTarget?.data.slug || node.data.escalationPath || null;
                const updatedAgent = await updateAgent(agentId, {
                    parent_agent_id: node.data.role === "manager" ? null : parentAgentId,
                    reviewer_agent_id: node.data.role === "reviewer" ? null : reviewerAgentId,
                    model_policy: {
                        ...(currentAgent.model_policy ?? {}),
                        model: node.data.model || null,
                        fallback_model: node.data.fallbackModel || null,
                        escalation_path: escalationSlug,
                        permissions: normalizePermission(node.data.permission),
                    },
                });
                savedAgentById.set(agentId, updatedAgent);
            }

            const reviewerAgentIds = sortedNodes
                .filter((node) => node.data.role === "reviewer")
                .map((node) => nodeToAgentId.get(node.id))
                .filter((item): item is string => Boolean(item));
            const managerAgentId = nodeToAgentId.get(managerRoot.id) ?? null;
            const updatedNodes = nodes.map((node) => {
                const resolvedAgentId = nodeToAgentId.get(node.id);
                const savedAgent = resolvedAgentId ? savedAgentById.get(resolvedAgentId) ?? null : null;
                return {
                    ...node,
                    id: savedAgent?.id ?? node.id,
                    data: {
                        ...node.data,
                        linkedAgentId: savedAgent?.id ?? node.data.linkedAgentId,
                        slug: savedAgent?.slug ?? node.data.slug,
                        subtitle: buildNodeSubtitle({
                            linkedAgentId: savedAgent?.id ?? node.data.linkedAgentId,
                            linkedTemplateSlug: node.data.linkedTemplateSlug,
                            slug: savedAgent?.slug ?? node.data.slug,
                        }),
                        status: savedAgent ? "inactive" : node.data.status,
                    },
                } as TeamGraphNode;
            });
            const remappedEdges = edges.map((edge) =>
                createSemanticEdge(
                    nodeToAgentId.get(edge.source) ?? edge.source,
                    nodeToAgentId.get(edge.target) ?? edge.target,
                    edge.data?.semantic ?? "delegates_to",
                ),
            );
            const snapshot: TeamLayoutSnapshot = {
                savedAt: new Date().toISOString(),
                nodes: updatedNodes,
                edges: remappedEdges,
                persistence: "project",
            };
            const currentExecution = ((selectedHierarchyProject.settings?.execution as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
            await updateOrchestrationProject(effectiveHierarchyProjectId, {
                settings: {
                    execution: {
                        ...currentExecution,
                        manager_agent_id: managerAgentId,
                        reviewer_agent_ids: reviewerAgentIds,
                        team_graph_agent_ids: Array.from(nodeToAgentId.values()),
                        team_graph_layout: {
                            savedAt: snapshot.savedAt,
                            nodes: snapshot.nodes,
                            edges: snapshot.edges,
                        },
                    },
                },
            });
            await updateHierarchyPolicy(effectiveHierarchyProjectId, {
                manager_agent_id: managerAgentId,
                edges: remappedEdges.map((edge) => ({
                    source_agent_id: edge.source,
                    target_agent_id: edge.target,
                    relationship: edge.data?.semantic ?? "delegates_to",
                })),
                reviewer_agent_ids: reviewerAgentIds,
            });

            return snapshot;
        },
        onSuccess: async (snapshot) => {
            setNodes(snapshot.nodes);
            setEdges(snapshot.edges);
            setSavedLayout(snapshot);
            persistTeamLayoutSnapshot(snapshot);
            setGraphDirty(false);
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agents() });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agents(effectiveHierarchyProjectId || "global") });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.projects });
            await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.githubIssues });
            showToast({ message: "Team graph saved to project. Agents and manager routing are now persistent.", severity: "success" });
        },
        onError: (error) => {
            let message = error instanceof Error ? error.message : "Couldn't save project team graph.";
            if (error && typeof error === "object" && "message" in error && typeof error.message === "string") {
                message = error.message;
            }
            showToast({ message, severity: "error" });
        },
    });

    function openAgentTemplateDrawer(template?: AgentTemplate) {
        setEditingAgentTemplateSlug(template?.slug ?? null);
        setForm(template ? buildAgentTemplateFormFromTemplate(template) : EMPTY_AGENT_TEMPLATE_FORM);
        setAgentTemplateImportBanner(null);
        setAgentTemplateDrawerOpen(true);
    }

    async function importAgentTemplateMarkdown(file: File) {
        const markdown = await file.text();
        const draft = parseAgentTemplateMarkdown({
            markdown,
            fileName: file.name,
            toolCatalog: stringOptions.tools,
        });
        setAgentTemplateImportDraft(draft);
        setAgentTemplateImportReviewOpen(true);
    }

    function continueImportedAgentTemplateDraft(draft: AgentTemplateImportDraft) {
        setEditingAgentTemplateSlug(null);
        setForm(draftToAgentTemplateFormState(draft));
        setAgentTemplateImportBanner(createImportedSourceSummary(draft));
        setAgentTemplateImportDraft(draft);
        setAgentTemplateImportReviewOpen(false);
        setAgentTemplateDrawerOpen(true);
    }

    function saveAgentTemplate() {
        const existingTemplate = editingAgentTemplateSlug
            ? templates.find((item) => item.slug === editingAgentTemplateSlug) ?? null
            : null;
        const payload = buildAgentTemplatePayloadFromForm(
            form,
            existingTemplate,
            templates.map((item) => item.slug),
        );

        if (existingTemplate) {
            if (!existingTemplate.id) {
                showToast({ message: "Template id missing. Refresh and retry.", severity: "error" });
                return;
            }
            updateAgentTemplateMutation.mutate({ id: existingTemplate.id, payload });
        } else {
            createAgentTemplateMutation.mutate(payload);
        }
        setAgentTemplateImportBanner(null);
        setAgentTemplateDrawerOpen(false);
    }

    function openSkillTemplateDrawer(skill?: SkillPack) {
        setEditingSkillSlug(skill?.slug ?? null);
        setSkillForm(buildSkillForm(skill));
        setSkillTemplateImportBanner(null);
        setSkillTemplateDrawerOpen(true);
    }

    async function importSkillTemplateMarkdown(file: File) {
        const markdown = await file.text();
        const draft = parseSkillTemplateMarkdown({
            markdown,
            fileName: file.name,
            toolCatalog: stringOptions.tools,
        });
        setSkillTemplateImportDraft(draft);
        setSkillTemplateImportReviewOpen(true);
    }

    function continueImportedSkillTemplateDraft(draft: SkillTemplateImportDraft) {
        setEditingSkillSlug(null);
        setSkillForm(buildSkillForm(draftToSkillTemplateFormState(draft)));
        setSkillTemplateImportBanner(createSkillImportedSourceSummary(draft));
        setSkillTemplateImportDraft(draft);
        setSkillTemplateImportReviewOpen(false);
        setSkillTemplateDrawerOpen(true);
    }

    function saveSkillTemplate() {
        const existingSkill = editingSkillSlug ? skills.find((item) => item.slug === editingSkillSlug) ?? null : null;
        const nextSlug = existingSkill?.slug ?? (skillForm.slug.trim() || createUniqueSlug(skillForm.name || "Untitled skill", skills.map((item) => item.slug)));
        // Canonical path: SkillDraft (not SkillPack). Legacy pack update remains only for edits of already-imported packs.
        if (existingSkill) {
            updateSkillMutation.mutate({
                slug: existingSkill.slug,
                payload: {
                    name: skillForm.name.trim() || existingSkill.name || "Untitled skill",
                    description: skillForm.description.trim(),
                    capabilities: skillForm.capabilities,
                    allowed_tools: skillForm.allowed_tools,
                    tags: skillForm.tags,
                    rules_markdown: skillForm.rules_markdown.trim(),
                },
            });
            setSkillTemplateImportBanner(null);
            setSkillTemplateDrawerOpen(false);
            return;
        }

        void (async () => {
            try {
                const { createSkillDraft } = await import("../../api/workforce");
                const draft = await createSkillDraft({
                    name: skillForm.name.trim() || "Untitled skill",
                    slug: nextSlug,
                    scope: "organization",
                    purpose: skillForm.description.trim() || skillForm.name.trim() || "Imported skill",
                    when_to_use: "Use when the task matches this skill's capabilities.",
                    instructions: skillForm.rules_markdown.trim() || skillForm.description.trim() || "Follow the skill instructions.",
                    capabilities: skillForm.capabilities,
                    tools: skillForm.allowed_tools,
                    risk_level: "medium",
                });
                showToast({ message: "Saved as SkillDraft (canonical). Open Skills Builder to validate/publish.", severity: "success" });
                setSkillTemplateImportBanner(null);
                setSkillTemplateDrawerOpen(false);
                navigate(`/skills/builder?draftId=${draft.id}`);
            } catch (error) {
                showToast({
                    message: error instanceof Error ? error.message : "Failed to save skill draft",
                    severity: "error",
                });
            }
        })();
    }

    function openTeamTemplateDrawer(template?: TeamTemplate) {
        const draft = buildTeamTemplateForm(template);
        const draftTemplates = draft.agent_template_slugs
            .map((slug) => templates.find((item) => item.slug === slug) ?? null)
            .filter((item): item is AgentTemplate => Boolean(item));
        const graph = applyTeamTemplateCanvasLayout(
            buildTeamTemplateCanvasGraph(draftTemplates),
            draft.canvas_layout,
        );
        setEditingTeamTemplateId(template?.id ?? null);
        setTeamTemplateForm(draft);
        setTeamTemplateCanvasNodes(graph.nodes);
        setTeamTemplateCanvasEdges(graph.edges);
        setSelectedTeamTemplateCanvasNodeId(graph.nodes[0]?.id ?? null);
        setTeamTemplateDrawerOpen(true);
    }

    function attachAgentTemplateToTeamTemplateDraft(templateSlug: string) {
        const nextSlugs = uniqueStrings([...teamTemplateForm.agent_template_slugs, templateSlug]);
        const graph = buildTeamTemplateCanvasGraph(
            nextSlugs
                .map((slug) => templates.find((item) => item.slug === slug) ?? null)
                .filter((item): item is AgentTemplate => Boolean(item)),
        );
        setTeamTemplateForm((current) => ({
            ...current,
            agent_template_slugs: nextSlugs,
        }));
        setTeamTemplateCanvasNodes(graph.nodes);
        setTeamTemplateCanvasEdges(graph.edges);
        setSelectedTeamTemplateCanvasNodeId((current) => current ?? graph.nodes[0]?.id ?? null);
    }

    function removeAgentTemplateFromTeamTemplateDraft(templateSlug: string) {
        const nextSlugs = teamTemplateForm.agent_template_slugs.filter((item) => item !== templateSlug);
        const graph = buildTeamTemplateCanvasGraph(
            nextSlugs
                .map((slug) => templates.find((item) => item.slug === slug) ?? null)
                .filter((item): item is AgentTemplate => Boolean(item)),
        );
        setTeamTemplateForm((current) => ({
            ...current,
            agent_template_slugs: nextSlugs,
        }));
        setTeamTemplateCanvasNodes(graph.nodes);
        setTeamTemplateCanvasEdges(graph.edges);
        setSelectedTeamTemplateCanvasNodeId(graph.nodes[0]?.id ?? null);
    }

    function saveTeamTemplate() {
        const existingTemplate = editingTeamTemplateId
            ? teamTemplates.find((item) => item.id === editingTeamTemplateId) ?? null
            : null;
        const selectedTemplates = teamTemplateForm.agent_template_slugs
            .map((slug) => templates.find((item) => item.slug === slug) ?? null)
            .filter((item): item is AgentTemplate => Boolean(item));
        const derivedRoles = uniqueStrings(selectedTemplates.map((item) => item.role));
        const derivedTools = uniqueStrings(selectedTemplates.flatMap((item) => item.allowed_tools));
        const nextSlug = existingTemplate?.slug ?? (teamTemplateForm.slug.trim() || createUniqueSlug(teamTemplateForm.name || "Untitled team template", teamTemplates.map((item) => item.slug)));
        const payload: Omit<TeamTemplate, "id"> = {
            slug: nextSlug,
            name: teamTemplateForm.name.trim() || existingTemplate?.name || "Untitled team template",
            description: teamTemplateForm.description.trim(),
            outcome: teamTemplateForm.outcome.trim(),
            roles: derivedRoles,
            tools: derivedTools,
            autonomy: existingTemplate?.autonomy ?? "custom",
            visibility: teamTemplateForm.visibility.trim() || "private",
            agent_template_slugs: teamTemplateForm.agent_template_slugs,
            canvas_layout: extractTeamTemplateCanvasLayout(teamTemplateCanvasNodes, teamTemplateCanvasEdges),
        };

        if (existingTemplate) {
            updateTeamTemplateMutation.mutate({ id: existingTemplate.id, payload });
        } else {
            createTeamTemplateMutation.mutate(payload);
        }
        setTeamTemplateDrawerOpen(false);
    }

    function attachSkillToAgentTemplate(templateSlug: string, skillSlug: string) {
        const template = templates.find((item) => item.slug === templateSlug);
        if (!template || template.skills.includes(skillSlug)) {
            return;
        }
        if (!template.id) {
            showToast({ message: "Template id missing. Refresh and retry.", severity: "error" });
            return;
        }
        updateAgentTemplateMutation.mutate({
            id: template.id,
            payload: { skills: [...template.skills, skillSlug] },
        });
    }

    function removeSkillFromAgentTemplate(templateSlug: string, skillSlug: string) {
        const template = templates.find((item) => item.slug === templateSlug);
        if (!template) {
            return;
        }
        if (!template.id) {
            showToast({ message: "Template id missing. Refresh and retry.", severity: "error" });
            return;
        }
        updateAgentTemplateMutation.mutate({
            id: template.id,
            payload: { skills: template.skills.filter((item) => item !== skillSlug) },
        });
    }

    function attachAgentTemplateToTeamTemplate(teamTemplateId: string, templateSlug: string) {
        const teamTemplate = teamTemplates.find((item) => item.id === teamTemplateId);
        if (!teamTemplate || teamTemplate.agent_template_slugs.includes(templateSlug)) {
            return;
        }
        updateTeamTemplateMutation.mutate({
            id: teamTemplateId,
            payload: { agent_template_slugs: [...teamTemplate.agent_template_slugs, templateSlug] },
        });
    }

    function removeAgentTemplateFromTeamTemplate(teamTemplateId: string, templateSlug: string) {
        const teamTemplate = teamTemplates.find((item) => item.id === teamTemplateId);
        if (!teamTemplate) {
            return;
        }
        updateTeamTemplateMutation.mutate({
            id: teamTemplateId,
            payload: { agent_template_slugs: teamTemplate.agent_template_slugs.filter((item) => item !== templateSlug) },
        });
    }

    function fitCanvas() {
        window.requestAnimationFrame(() => {
            flowInstance?.fitView({ padding: 0.18, duration: 240 });
        });
    }

    function createDraftNode(role: TeamGraphRole = "specialist") {
        const count = nodes.filter((node) => node.data.role === role).length + 1;
        const nextNode: TeamGraphNode = {
            id: createUniqueNodeId(`draft-${role}`, nodes.map((node) => node.id)),
            type: role,
            position: { x: 120 + count * 40, y: role === "manager" ? 80 : role === "reviewer" ? 520 : 300 },
            data: {
                ...createDefaultNodeData(
                    role,
                    role === "manager" ? "Manager" : role === "team_lead" ? "Team Lead" : role === "reviewer" ? "Reviewer" : "Specialist",
                    createUniqueSlug(`${role}-${count}`, nodes.map((node) => node.data.slug)),
                    role === "manager"
                        ? "Routes work, resolves escalation, and owns delivery."
                        : role === "reviewer"
                            ? "Reviews outputs before handoff."
                            : "Executes scoped tasks inside the team.",
                    role === "manager" ? ["orchestration", "delegation"] : role === "reviewer" ? ["qa", "review"] : ["execution"],
                    "",
                ),
                subtitle: "local draft",
            },
        };
        setNodes((current) => autoLayoutGraph([...current, nextNode]));
        setGraphDirty(true);
        setSelectedNodeId(nextNode.id);
        setSelectedEdgeId(null);
        openTeamNodeDrawer(nextNode.id, nextNode.data);
        showToast({ message: "Draft agent added to team graph.", severity: "success" });
        fitCanvas();
    }

    function computeDefaultNodePosition(role: TeamGraphRole, currentNodes: TeamGraphNode[]): { x: number; y: number } {
        const MANAGER_GAP_X = 640;
        const MANAGER_Y = 80;
        const SPECIALIST_Y = 300;
        const REVIEWER_Y = 520;
        if (role === "manager") {
            const existingManagers = currentNodes.filter((node) => node.data.role === "manager").length;
            return { x: 600 + existingManagers * MANAGER_GAP_X, y: MANAGER_Y };
        }
        return { x: 600, y: role === "reviewer" ? REVIEWER_Y : SPECIALIST_Y };
    }

    function reflowChildRows(
        currentNodes: TeamGraphNode[],
        options?: { anchorManagerId?: string; childIds?: Set<string> },
    ): TeamGraphNode[] {
        const CHILD_GAP_X = 280;
        const SPECIALIST_OFFSET_Y = 220;
        const REVIEWER_OFFSET_Y = 440;
        const anchorId = options?.anchorManagerId;
        const manager = anchorId
            ? currentNodes.find((node) => node.id === anchorId && node.data.role === "manager")
            : currentNodes.find((node) => node.data.role === "manager");
        if (!manager) {
            return currentNodes;
        }
        const inScope = (node: TeamGraphNode) =>
            !options?.childIds || options.childIds.has(node.id);
        const specialists = currentNodes.filter((node) => node.data.role === "specialist" && inScope(node));
        const reviewers = currentNodes.filter((node) => node.data.role === "reviewer" && inScope(node));
        const centerX = manager.position.x;
        const managerY = manager.position.y;
        const positions = new Map<string, { x: number; y: number }>();
        const placeRow = (items: TeamGraphNode[], rowY: number) => {
            if (items.length === 0) return;
            const totalWidth = (items.length - 1) * CHILD_GAP_X;
            const startX = centerX - totalWidth / 2;
            items.forEach((item, idx) => {
                positions.set(item.id, { x: startX + idx * CHILD_GAP_X, y: rowY });
            });
        };
        placeRow(specialists, managerY + SPECIALIST_OFFSET_Y);
        placeRow(reviewers, managerY + REVIEWER_OFFSET_Y);
        return currentNodes.map((node) => {
            const pos = positions.get(node.id);
            return pos ? { ...node, position: pos } : node;
        });
    }

    function addAgentNode(agentId: string) {
        const agent = hierarchyAgents.find((item) => item.id === agentId);
        if (!agent) {
            return;
        }
        const role = normalizeTeamGraphRole(agent.role);
        const nextNode: TeamGraphNode = {
            id: createUniqueNodeId(`${agent.id}-team-node`, nodes.map((node) => node.id)),
            type: role,
            position: computeDefaultNodePosition(role, nodes),
            data: buildNodeDataFromAgent(agent, agentLiveStatus),
        };
        const manager = role !== "manager" ? nodes.find((node) => node.data.role === "manager") ?? null : null;
        setNodes((current) => reflowChildRows([...current, nextNode]));
        if (manager) {
            setEdges((current) => [...current, createSemanticEdge(manager.id, nextNode.id, role === "reviewer" ? "reviews" : "delegates_to")]);
        }
        setGraphDirty(true);
        setSelectedNodeId(nextNode.id);
        setSelectedEdgeId(null);
        setAddAgentDialogOpen(false);
        setAgentToAddId("");
        openTeamNodeDrawer(nextNode.id, nextNode.data);
        showToast({ message: `${agent.name} added to team graph.`, severity: "success" });
        fitCanvas();
    }

    function addAgentTemplateNode(templateSlug: string, dropPosition?: { x: number; y: number }) {
        const template = templates.find((item) => item.slug === templateSlug);
        if (!template) {
            return;
        }
        const role = normalizeTeamGraphRole(template.role);
        const nextNode: TeamGraphNode = {
            id: createUniqueNodeId(`template-${template.slug}`, nodes.map((node) => node.id)),
            type: role,
            position: dropPosition ?? computeDefaultNodePosition(role, nodes),
            data: buildNodeDataFromTemplate(template),
        };
        const manager = role !== "manager" ? nodes.find((node) => node.data.role === "manager") ?? null : null;
        setNodes((current) => reflowChildRows([...current, nextNode]));
        if (manager) {
            setEdges((current) => [...current, createSemanticEdge(manager.id, nextNode.id, role === "reviewer" ? "reviews" : "delegates_to")]);
        }
        setGraphDirty(true);
        setSelectedNodeId(nextNode.id);
        setSelectedEdgeId(null);
        setAddAgentDialogOpen(false);
        setAgentToAddId("");
        showToast({ message: `${template.name} added to team graph.`, severity: "success" });
        fitCanvas();
    }

    function insertTeamTemplateInHierarchy(teamTemplate: TeamTemplate) {
        const selected = teamTemplate.agent_template_slugs
            .map((slug) => templates.find((item) => item.slug === slug) ?? null)
            .filter((item): item is AgentTemplate => Boolean(item));
        if (selected.length === 0) {
            showToast({ message: "Team template has no agent templates attached.", severity: "warning" });
            return;
        }
        const graph = buildTeamTemplateCanvasGraph(selected);
        setNodes(graph.nodes);
        setEdges(graph.edges);
        setSelectedNodeId(graph.nodes[0]?.id ?? null);
        setSelectedEdgeId(null);
        setGraphDirty(true);
        setManualTab("hierarchy");
        showToast({ message: `Team "${teamTemplate.name}" loaded into graph.`, severity: "success" });
        fitCanvas();
    }

    function updateNodeData(nodeId: string, patch: Partial<TeamGraphNodeData>) {
        setNodes((current) =>
            current.map((node) =>
                node.id === nodeId
                    ? {
                        ...node,
                        type: patch.role ?? node.type,
                        data: {
                            ...node.data,
                            ...patch,
                            subtitle: buildNodeSubtitle({
                                linkedTemplateSlug: patch.linkedTemplateSlug ?? node.data.linkedTemplateSlug,
                                linkedAgentId: patch.linkedAgentId ?? node.data.linkedAgentId,
                                slug: patch.slug ?? node.data.slug,
                            }),
                        },
                    }
                    : node,
            ),
        );
        setGraphDirty(true);
    }

    function openTeamNodeDrawer(nodeId: string, initialData?: TeamGraphNodeData) {
        const node = nodes.find((item) => item.id === nodeId);
        const nextData = initialData ?? node?.data;
        if (!nextData) {
            return;
        }
        setEditingTeamNodeId(nodeId);
        setTeamNodeDraft(cloneNodeData(nextData));
        setTeamNodeDrawerOpen(true);
    }

    function closeTeamNodeDrawer() {
        setTeamNodeDrawerOpen(false);
        setEditingTeamNodeId(null);
        setTeamNodeDraft(null);
    }

    function hydrateTeamNodeDraftFromAgent(agentId: string) {
        const agent = hierarchyAgents.find((item) => item.id === agentId);
        if (!agent) {
            return;
        }
        const hydrated = buildNodeDataFromAgent(agent, agentLiveStatus);
        setTeamNodeDraft((current) => {
            if (!current) {
                return hydrated;
            }
            return {
                ...hydrated,
                linkedTemplateSlug: current.linkedTemplateSlug || hydrated.linkedTemplateSlug,
                linkedAgentId: agentId,
                projectAssignments: current.projectAssignments.length > 0 ? current.projectAssignments : hydrated.projectAssignments,
                subtitle: buildNodeSubtitle({
                    linkedTemplateSlug: current.linkedTemplateSlug || hydrated.linkedTemplateSlug,
                    linkedAgentId: agentId,
                    slug: hydrated.slug,
                }),
            };
        });
    }

    async function saveTeamNode() {
        if (!editingTeamNodeId || !teamNodeDraft) {
            return;
        }
        const nextNodeData = {
            ...teamNodeDraft,
            subtitle: buildNodeSubtitle(teamNodeDraft),
        };
        const existingAgent = teamNodeDraft.linkedAgentId
            ? hierarchyAgents.find((agent) => agent.id === teamNodeDraft.linkedAgentId) ?? agents.find((agent) => agent.id === teamNodeDraft.linkedAgentId) ?? null
            : null;

        setTeamNodeSaving(true);
        try {
            if (existingAgent) {
                await updateAgent(existingAgent.id, {
                    name: normalizeAgentName(teamNodeDraft.name, existingAgent.name),
                    slug: normalizeAgentSlug(teamNodeDraft.slug, existingAgent.slug),
                    description: teamNodeDraft.description.trim(),
                    role: teamNodeDraft.role,
                    parent_template_slug: teamNodeDraft.linkedTemplateSlug || null,
                    capabilities: teamNodeDraft.capabilities,
                    allowed_tools: sanitizeRuntimeTools(teamNodeDraft.allowedTools),
                    tags: teamNodeDraft.tags,
                    model_policy: {
                        ...(existingAgent.model_policy ?? {}),
                        model: teamNodeDraft.model || null,
                        fallback_model: teamNodeDraft.fallbackModel || null,
                        escalation_path: teamNodeDraft.escalationPath || null,
                        permissions: normalizePermission(teamNodeDraft.permission),
                    },
                    memory_policy: {
                        ...(existingAgent.memory_policy ?? {}),
                        scope: normalizeMemoryScope(teamNodeDraft.memoryScope),
                    },
                    output_schema: {
                        ...(existingAgent.output_schema ?? {}),
                        format: normalizeOutputFormat(teamNodeDraft.outputFormat),
                    },
                    budget: {
                        ...(existingAgent.budget ?? {}),
                        token_budget: clamp(parsePositiveInteger(teamNodeDraft.tokenBudget, 8000), 1, 1_000_000),
                        time_budget_seconds: clamp(parsePositiveInteger(teamNodeDraft.timeBudgetSeconds, 300), 10, 86_400),
                        retry_budget: clamp(parsePositiveInteger(teamNodeDraft.retryBudget, 1), 0, 20),
                    },
                    timeout_seconds: clamp(parsePositiveInteger(teamNodeDraft.timeBudgetSeconds, existingAgent.timeout_seconds || 300), 10, 14400),
                    retry_limit: clamp(parsePositiveInteger(teamNodeDraft.retryBudget, existingAgent.retry_limit || 1), 0, 10),
                    task_filters: normalizeTaskFilters(teamNodeDraft.taskFilters),
                });
                await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agents() });
                await queryClient.invalidateQueries({ queryKey: queryKeys.orchestration.agents(effectiveHierarchyProjectId || "global") });
            }
            updateNodeData(editingTeamNodeId, nextNodeData);
            closeTeamNodeDrawer();
            showToast({ message: existingAgent ? "Agent saved." : "Team graph agent updated.", severity: "success" });
        } catch (error) {
            showToast({ message: error instanceof Error ? error.message : "Could not save agent.", severity: "error" });
        } finally {
            setTeamNodeSaving(false);
        }
    }

    function deleteNode(nodeId: string) {
        setNodes((current) => current.filter((node) => node.id !== nodeId));
        setEdges((current) => current.filter((edge) => edge.source !== nodeId && edge.target !== nodeId));
        if (selectedNodeId === nodeId) {
            setSelectedNodeId(null);
        }
        if (editingTeamNodeId === nodeId) {
            closeTeamNodeDrawer();
        }
        setGraphDirty(true);
    }

    function duplicateNode(nodeId: string) {
        const source = nodes.find((node) => node.id === nodeId);
        if (!source) return;
        const nextNode: TeamGraphNode = {
            ...source,
            id: `${source.id}-copy-${Date.now()}`,
            position: {
                x: source.position.x + 40,
                y: source.position.y + 40,
            },
            data: {
                ...source.data,
                name: `${source.data.name} Copy`,
                slug: `${source.data.slug}-copy`,
                status: "draft",
                linkedAgentId: "",
                subtitle: source.data.linkedTemplateSlug ? `template ${source.data.linkedTemplateSlug}` : "local draft",
            },
        };
        setNodes((current) => [...current, nextNode]);
        setSelectedNodeId(nextNode.id);
        setSelectedEdgeId(null);
        setGraphDirty(true);
        fitCanvas();
    }

    function autoLayout() {
        setNodes((current) => autoLayoutGraph(current));
        setGraphDirty(true);
        fitCanvas();
    }

    function resetLayout() {
        setNodes(initialGraph.nodes);
        setEdges(initialGraph.edges);
        setSelectedNodeId(null);
        setSelectedEdgeId(null);
        setSavedLayout(null);
        persistTeamLayoutSnapshot(null);
        setGraphDirty(false);
        showToast({ message: "Team layout reset to agent-derived defaults.", severity: "success" });
        fitCanvas();
    }

    function saveLayout() {
        saveTeamGraphMutation.mutate();
    }

    function removeSelectedEdge() {
        if (!selectedEdgeId) return;
        setEdges((current) => current.filter((edge) => edge.id !== selectedEdgeId));
        setSelectedEdgeId(null);
        setGraphDirty(true);
    }

    function validateTeamGraph() {
        setShowValidationPanel(true);
        showToast({
            message: validationIssues.length ? `${validationIssues.length} validation issues found.` : "Team graph passed client validation.",
            severity: validationIssues.length ? "warning" : "success",
        });
    }

    const inspectorContent = selectedNode ? (
        <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                <Box>
                    <Typography variant="h6">{selectedNode.data.name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                        Select node, then open builder from right drawer to edit contract and runtime.
                    </Typography>
                </Box>
                {isCompact ? (
                    <IconButton onClick={() => setSelectedNodeId(null)}>
                        <CloseIcon fontSize="small" />
                    </IconButton>
                ) : null}
            </Stack>

            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Button size="small" variant="contained" onClick={() => openTeamNodeDrawer(selectedNode.id)}>
                    Edit
                </Button>
                <Button size="small" variant="outlined" startIcon={<DuplicateIcon />} onClick={() => duplicateNode(selectedNode.id)}>
                    Duplicate
                </Button>
                <Button size="small" color="error" variant="outlined" startIcon={<DeleteIcon />} onClick={() => deleteNode(selectedNode.id)}>
                    Delete
                </Button>
            </Stack>
            <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                <Chip size="small" label={selectedNode.data.role} color={getRoleColor(selectedNode.data.role)} variant="outlined" />
                <Chip size="small" label={selectedNode.data.status} variant="outlined" />
                {selectedNode.data.linkedTemplateSlug ? <Chip size="small" label={`template ${selectedNode.data.linkedTemplateSlug}`} variant="outlined" /> : null}
                {selectedNode.data.linkedAgentId ? <Chip size="small" label="linked saved agent" variant="outlined" /> : null}
            </Stack>
            <TextField
                label="Description"
                value={selectedNode.data.description || "No contract description yet."}
                multiline
                minRows={4}
                fullWidth
                InputProps={{ readOnly: true }}
            />
            <TextField
                label="Capabilities"
                value={selectedNode.data.capabilities.join(", ")}
                fullWidth
                InputProps={{ readOnly: true }}
            />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField
                    label="Primary model"
                    value={selectedNode.data.model || "—"}
                    fullWidth
                    InputProps={{ readOnly: true }}
                    helperText="Read-only here. Edit opens the drawer with models from Admin → Settings → Providers."
                />
                <TextField
                    label="Fallback model"
                    value={selectedNode.data.fallbackModel || "—"}
                    fullWidth
                    InputProps={{ readOnly: true }}
                    helperText="Optional; same picker in Edit."
                />
            </Stack>
        </Stack>
    ) : (
        <EmptyState
            icon={<GraphIcon />}
            title="No node selected"
            description="Select a node to edit its operational contract, model policy, routing, and project assignments."
        />
    );

    return (
        <ReactFlowProvider>
        <PageShell variant="inspector">
            <PageHeader
                eyebrow="Agents"
                title="Hierarchy"
                description="Compose teams from templates, wire reporting lines on the canvas, and publish operational contracts."
            />
            <DensePageMobileNotice surface="Hierarchy builder" />
            {hierarchyBootstrapping ? (
                <PageSkeleton variant="canvas" />
            ) : (
            <>
            {graphDirty ? (
                <Alert severity="warning" sx={{ mb: 2 }}>
                    Unsaved hierarchy changes. Save or publish before leaving this project graph.
                </Alert>
            ) : null}

            <Paper sx={{ mb: 2, borderRadius: 1, p: 1 }}>
                <Tabs value={activeTab} onChange={(_, value: BuilderTab) => setManualTab(value)} variant="scrollable" scrollButtons="auto">
                    <Tab value="hierarchy" label="Team Builder" />
                    <Tab value="library" label="Templates" />
                </Tabs>
            </Paper>

            {activeTab === "library" ? (
                <Stack spacing={2}>
                    <Alert severity="info">
                        Drag skill templates onto agent templates. Drag agent templates onto team templates.
                    </Alert>

                    <ExpandableSection
                        title="Agent templates"
                        description="Template contracts for manager, specialist, and reviewer agents. Drop skill templates onto any card to attach reusable skills."
                        action={(
                            <Stack direction="row" spacing={1}>
                                <Button variant="outlined" component="label" startIcon={<UploadIcon />}>
                                    Import .md
                                    <input
                                        hidden
                                        type="file"
                                        accept=".md,.markdown,text/markdown"
                                        onChange={(event) => {
                                            const file = event.target.files?.[0];
                                            event.target.value = "";
                                            if (file) {
                                                void importAgentTemplateMarkdown(file);
                                            }
                                        }}
                                    />
                                </Button>
                                <Button variant="contained" startIcon={<AddIcon />} onClick={() => openAgentTemplateDrawer()}>Add</Button>
                            </Stack>
                        )}
                    >
                        {templates.length === 0 ? (
                            <EmptyState
                                icon={<AgentIcon />}
                                title="No agent templates yet"
                                description="Create the first reusable agent contract for your orchestration library."
                            />
                        ) : (
                            <Box sx={{ display: "flex", gap: 2, overflowX: "auto", pb: 1 }}>
                                {templates.map((template) => (
                                    <Paper
                                        key={template.slug}
                                        draggable
                                        onDragStart={() => setDraggingItem({ type: "agent-template", slug: template.slug })}
                                        onDragEnd={() => {
                                            setDraggingItem(null);
                                            setActiveDropTarget(null);
                                        }}
                                        onDragOver={(event) => {
                                            if (draggingItem?.type !== "skill") return;
                                            event.preventDefault();
                                            setActiveDropTarget({ kind: "agent-template", id: template.slug });
                                        }}
                                        onDragLeave={() => {
                                            if (activeDropTarget?.kind === "agent-template" && activeDropTarget.id === template.slug) {
                                                setActiveDropTarget(null);
                                            }
                                        }}
                                        onDrop={() => {
                                            if (draggingItem?.type === "skill") {
                                                attachSkillToAgentTemplate(template.slug, draggingItem.slug);
                                            }
                                            setDraggingItem(null);
                                            setActiveDropTarget(null);
                                        }}
                                        sx={{
                                            minWidth: 340,
                                            p: 2,
                                            borderRadius: 4,
                                            border: "1px solid",
                                            borderColor: activeDropTarget?.kind === "agent-template" && activeDropTarget.id === template.slug ? "primary.main" : "divider",
                                            bgcolor: activeDropTarget?.kind === "agent-template" && activeDropTarget.id === template.slug ? "action.hover" : "background.paper",
                                        }}
                                    >
                                        <Stack spacing={1.5}>
                                            <Stack direction="row" justifyContent="space-between" spacing={1}>
                                                <Box>
                                                    <Typography variant="subtitle1">{template.name}</Typography>
                                                    <Typography variant="body2" color="text.secondary">
                                                        {template.role} • {template.slug}
                                                    </Typography>
                                                </Box>
                                                <Chip size="small" label={template.role} color={getRoleColor(template.role as TeamGraphRole)} variant="outlined" />
                                            </Stack>
                                            <Typography variant="body2" color="text.secondary">
                                                {template.description || "No description provided."}
                                            </Typography>
                                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                                {template.skills.length === 0 ? (
                                                    <Chip size="small" label="Drop skills here" variant="outlined" />
                                                ) : (
                                                    template.skills.map((skillSlug) => (
                                                        <Chip
                                                            key={`${template.slug}-${skillSlug}`}
                                                            size="small"
                                                            label={skillDisplayName(skillSlug, skills)}
                                                            onDelete={() => removeSkillFromAgentTemplate(template.slug, skillSlug)}
                                                        />
                                                    ))
                                                )}
                                            </Stack>
                                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                                {template.capabilities.slice(0, 3).map((item) => (
                                                    <Chip key={`${template.slug}-${item}`} size="small" label={item} variant="outlined" />
                                                ))}
                                            </Stack>
                                            <Stack direction="row" spacing={1}>
                                                <Button size="small" variant="outlined" onClick={() => openAgentTemplateDrawer(template)}>
                                                    Edit
                                                </Button>
                                                <Button
                                                    size="small"
                                                    color="error"
                                                    onClick={() => {
                                                        if (!template.id) {
                                                            showToast({ message: "Template id missing. Refresh and retry.", severity: "error" });
                                                            return;
                                                        }
                                                        deleteAgentTemplateMutation.mutate(template.id);
                                                    }}
                                                >
                                                    Remove
                                                </Button>
                                            </Stack>
                                        </Stack>
                                    </Paper>
                                ))}
                            </Box>
                        )}
                    </ExpandableSection>

                    <ExpandableSection
                        title="Team templates"
                        description="Reusable multi-agent team canvases. Drop agent templates onto a team card to add them to the team."
                        action={<Button variant="contained" startIcon={<AddIcon />} onClick={() => openTeamTemplateDrawer()}>Add</Button>}
                        defaultExpanded={false}
                    >
                        {teamTemplates.length === 0 ? (
                            <EmptyState
                                icon={<GraphIcon />}
                                title="No team templates yet"
                                description="Create a team template and start dropping agent templates into it."
                            />
                        ) : (
                            <Box sx={{ display: "flex", gap: 2, overflowX: "auto", pb: 1 }}>
                                {teamTemplates.map((teamTemplate) => (
                                    <Paper
                                        key={teamTemplate.id}
                                        onDragOver={(event) => {
                                            if (draggingItem?.type !== "agent-template") return;
                                            event.preventDefault();
                                            setActiveDropTarget({ kind: "team-template", id: teamTemplate.id });
                                        }}
                                        onDragLeave={() => {
                                            if (activeDropTarget?.kind === "team-template" && activeDropTarget.id === teamTemplate.id) {
                                                setActiveDropTarget(null);
                                            }
                                        }}
                                        onDrop={() => {
                                            if (draggingItem?.type === "agent-template") {
                                                attachAgentTemplateToTeamTemplate(teamTemplate.id, draggingItem.slug);
                                            }
                                            setDraggingItem(null);
                                            setActiveDropTarget(null);
                                        }}
                                        sx={{
                                            minWidth: 380,
                                            p: 2,
                                            borderRadius: 4,
                                            border: "1px solid",
                                            borderColor: activeDropTarget?.kind === "team-template" && activeDropTarget.id === teamTemplate.id ? "primary.main" : "divider",
                                            bgcolor: activeDropTarget?.kind === "team-template" && activeDropTarget.id === teamTemplate.id ? "action.hover" : "background.paper",
                                        }}
                                    >
                                        <Stack spacing={1.5}>
                                            <Stack direction="row" justifyContent="space-between" spacing={1}>
                                                <Box>
                                                    <Typography variant="subtitle1">{teamTemplate.name}</Typography>
                                                    <Typography variant="body2" color="text.secondary">
                                                        {teamTemplate.slug} • {teamTemplate.visibility}
                                                    </Typography>
                                                </Box>
                                                <Chip size="small" label={teamTemplate.autonomy} variant="outlined" />
                                            </Stack>
                                            <Typography variant="body2" color="text.secondary">
                                                {teamTemplate.description || "No description provided."}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                Outcome: {teamTemplate.outcome || "Not set"}
                                            </Typography>
                                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                                {teamTemplate.agent_template_slugs.length === 0 ? (
                                                    <Chip size="small" label="Drop agent templates here" variant="outlined" />
                                                ) : (
                                                    teamTemplate.agent_template_slugs.map((slug) => (
                                                        <Chip
                                                            key={`${teamTemplate.id}-${slug}`}
                                                            size="small"
                                                            label={getTemplateBySlug(templates, slug)?.name ?? slug}
                                                            onDelete={() => removeAgentTemplateFromTeamTemplate(teamTemplate.id, slug)}
                                                        />
                                                    ))
                                                )}
                                            </Stack>
                                            <Stack direction="row" spacing={1}>
                                                <Button
                                                    size="small"
                                                    variant="contained"
                                                    startIcon={<GraphIcon />}
                                                    onClick={() => insertTeamTemplateInHierarchy(teamTemplate)}
                                                    disabled={teamTemplate.agent_template_slugs.length === 0}
                                                >
                                                    Use
                                                </Button>
                                                <Button size="small" variant="outlined" onClick={() => openTeamTemplateDrawer(teamTemplate)}>
                                                    Edit
                                                </Button>
                                                <Button
                                                    size="small"
                                                    variant="outlined"
                                                    onClick={() => createTeamProfileMutation.mutate({
                                                        templateId: teamTemplate.id,
                                                        name: `${teamTemplate.name} profile`,
                                                    })}
                                                    disabled={createTeamProfileMutation.isPending}
                                                >
                                                    Save as profile
                                                </Button>
                                                <Button size="small" color="error" onClick={() => deleteTeamTemplateMutation.mutate(teamTemplate.id)}>
                                                    Remove
                                                </Button>
                                            </Stack>
                                        </Stack>
                                    </Paper>
                                ))}
                            </Box>
                        )}
                    </ExpandableSection>

                    <ExpandableSection
                        title="Skill templates"
                        description="Reusable capability packs. Drag any skill card onto an agent template to attach it."
                        action={(
                            <Stack direction="row" spacing={1}>
                                <Button variant="outlined" component="label" startIcon={<UploadIcon />}>
                                    Import .md
                                    <input
                                        hidden
                                        type="file"
                                        accept=".md,.markdown,text/markdown"
                                        onChange={(event) => {
                                            const file = event.target.files?.[0];
                                            event.target.value = "";
                                            if (file) {
                                                void importSkillTemplateMarkdown(file);
                                            }
                                        }}
                                    />
                                </Button>
                                <Button variant="contained" startIcon={<AddIcon />} onClick={() => openSkillTemplateDrawer()}>Add</Button>
                            </Stack>
                        )}
                        defaultExpanded={false}
                    >
                        {skills.length === 0 ? (
                            <EmptyState
                                icon={<SpecialistIcon />}
                                title="No skill templates yet"
                                description="Create reusable skill packs and drop them into agent templates."
                            />
                        ) : (
                            <Box sx={{ display: "flex", gap: 2, overflowX: "auto", pb: 1 }}>
                                {skills.map((skill) => (
                                    <Paper
                                        key={skill.slug}
                                        draggable
                                        onDragStart={() => setDraggingItem({ type: "skill", slug: skill.slug })}
                                        onDragEnd={() => {
                                            setDraggingItem(null);
                                            setActiveDropTarget(null);
                                        }}
                                        sx={{ minWidth: 320, p: 2, borderRadius: 4, border: "1px solid", borderColor: "divider" }}
                                    >
                                        <Stack spacing={1.5}>
                                            <Box>
                                                <Typography variant="subtitle1">{skill.name}</Typography>
                                                <Typography variant="body2" color="text.secondary">
                                                    {skill.slug}
                                                </Typography>
                                            </Box>
                                            <Typography variant="body2" color="text.secondary">
                                                {skill.description || "No description provided."}
                                            </Typography>
                                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                                {skill.capabilities.map((item) => (
                                                    <Chip key={`${skill.slug}-${item}`} size="small" label={item} variant="outlined" />
                                                ))}
                                            </Stack>
                                            <Stack direction="row" spacing={1}>
                                                <Button size="small" variant="outlined" onClick={() => openSkillTemplateDrawer(skill)}>
                                                    Edit
                                                </Button>
                                                <Button size="small" color="error" onClick={() => deleteSkillMutation.mutate(skill.slug)}>
                                                    Remove
                                                </Button>
                                            </Stack>
                                        </Stack>
                                    </Paper>
                                ))}
                            </Box>
                        )}
                    </ExpandableSection>

                    <ExpandableSection
                        title="Team profiles"
                        description="Project-ready snapshots created from team templates. Use these when creating new projects."
                        action={(
                            <Button
                                variant="outlined"
                                onClick={() => navigate("/projects")}
                            >
                                Open Agent Projects
                            </Button>
                        )}
                        defaultExpanded={false}
                    >
                        {teamProfiles.length === 0 ? (
                            <EmptyState
                                icon={<GraphIcon />}
                                title="No team profiles yet"
                                description="Create one using “Save as profile” on a team template card."
                            />
                        ) : (
                            <Box sx={{ display: "flex", gap: 2, overflowX: "auto", pb: 1 }}>
                                {teamProfiles.map((teamProfile: TeamProfile) => (
                                    <Paper key={teamProfile.id} sx={{ minWidth: 360, p: 2, borderRadius: 4, border: "1px solid", borderColor: "divider" }}>
                                        <Stack spacing={1.25}>
                                            <Stack direction="row" justifyContent="space-between" spacing={1}>
                                                <Box>
                                                    <Typography variant="subtitle1">{teamProfile.name}</Typography>
                                                    <Typography variant="body2" color="text.secondary">
                                                        {teamProfile.slug} • from {teamProfile.source_team_template_slug}
                                                    </Typography>
                                                </Box>
                                                <Chip size="small" label={teamProfile.autonomy} variant="outlined" />
                                            </Stack>
                                            <Typography variant="body2" color="text.secondary">
                                                {teamProfile.description || "No description provided."}
                                            </Typography>
                                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                                <Chip size="small" variant="outlined" label={`${teamProfile.agent_template_slugs.length} agents`} />
                                                {teamProfile.roles.slice(0, 3).map((role) => (
                                                    <Chip key={`${teamProfile.id}-${role}`} size="small" variant="outlined" label={role} />
                                                ))}
                                            </Stack>
                                        </Stack>
                                    </Paper>
                                ))}
                            </Box>
                        )}
                    </ExpandableSection>
                </Stack>
            ) : (
                <Stack spacing={2}>
                    <Paper
                        sx={{
                            position: "sticky",
                            top: 16,
                            zIndex: 5,
                            p: 1.25,
                            borderRadius: 4,
                            border: "1px solid",
                            borderColor: "divider",
                        }}
                    >
                        <Stack direction={{ xs: "column", lg: "row" }} spacing={1.25} alignItems={{ lg: "center" }} justifyContent="space-between">
                            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                                <Button
                                    size="small"
                                    variant="contained"
                                    startIcon={<AddIcon />}
                                    onClick={() => {
                                        if (hierarchyAgents.length === 0 && templates.length === 0) {
                                            createDraftNode();
                                            return;
                                        }
                                        setAgentToAddId(hierarchyAgents[0] ? `agent:${hierarchyAgents[0].id}` : templates[0] ? `template:${templates[0].slug}` : "");
                                        setAddAgentDialogOpen(true);
                                    }}
                                >
                                    Add agent
                                </Button>
                                <Button size="small" variant="outlined" startIcon={<LayoutIcon />} onClick={autoLayout}>
                                    Auto-layout
                                </Button>
                                <Button size="small" variant="outlined" startIcon={<ValidateIcon />} onClick={validateTeamGraph}>
                                    Validate team
                                </Button>
                                <Button size="small" variant="outlined" startIcon={<SaveIcon />} onClick={saveLayout} disabled={saveTeamGraphMutation.isPending}>
                                    Save layout
                                </Button>
                                <Button size="small" variant="text" startIcon={<ResetIcon />} onClick={resetLayout}>
                                    Reset layout
                                </Button>
                                <Button
                                    size="small"
                                    variant={consoleOpen ? "contained" : "outlined"}
                                    startIcon={<AgentIcon />}
                                    onClick={() => setConsoleOpen((open) => !open)}
                                >
                                    Console
                                </Button>
                            </Stack>
                            <Stack direction="row" spacing={1} alignItems="center">
                                <TextField
                                    select
                                    size="small"
                                    label="Project"
                                    value={effectiveHierarchyProjectId}
                                    onChange={(event) => setSelectedHierarchyProjectId(event.target.value)}
                                    sx={{ minWidth: 220 }}
                                >
                                    {orchestrationProjects.map((project) => (
                                        <MenuItem key={project.id} value={project.id}>{project.name}</MenuItem>
                                    ))}
                                </TextField>
                                <TextField
                                    select
                                    size="small"
                                    label="Edge semantic"
                                    value={edgeSemanticDraft}
                                    onChange={(event) => setEdgeSemanticDraft(event.target.value as TeamGraphEdgeSemantic)}
                                    sx={{ minWidth: 180 }}
                                >
                                    <MenuItem value="delegates_to">delegates_to</MenuItem>
                                    <MenuItem value="reviews">reviews</MenuItem>
                                    <MenuItem value="escalates_to">escalates_to</MenuItem>
                                    <MenuItem value="collaborates_with">collaborates_with</MenuItem>
                                </TextField>
                                {selectedEdge ? (
                                    <Tooltip title="Disconnect selected edge">
                                        <IconButton color="error" onClick={removeSelectedEdge}>
                                            <DeleteIcon fontSize="small" />
                                        </IconButton>
                                    </Tooltip>
                                ) : null}
                            </Stack>
                        </Stack>
                    </Paper>

                    <Box
                        sx={{
                            display: "grid",
                            gap: 2,
                            gridTemplateColumns: {
                                xs: "1fr",
                                xl: `minmax(0, 1fr) 12px ${inspectorWidth}px`,
                            },
                            alignItems: "start",
                        }}
                    >


                        <SectionCard title="Team graph" description="React Flow orchestration editor with semantic edges, fit view, and client-side validation.">
                            {nodes.length === 0 ? (
                                <Box
                                    onDragOver={(event) => {
                                        if (draggingItem?.type === "agent-template") {
                                            event.preventDefault();
                                            event.dataTransfer.dropEffect = "copy";
                                        }
                                    }}
                                    onDrop={(event) => {
                                        if (draggingItem?.type !== "agent-template") return;
                                        event.preventDefault();
                                        addAgentTemplateNode(draggingItem.slug);
                                        setDraggingItem(null);
                                    }}
                                    sx={{
                                        borderRadius: 4,
                                        border: "2px dashed",
                                        borderColor: draggingItem?.type === "agent-template" ? "primary.main" : "divider",
                                        bgcolor: draggingItem?.type === "agent-template" ? "action.hover" : "transparent",
                                        p: 2,
                                        transition: "border-color 120ms ease, background-color 120ms ease",
                                    }}
                                >
                                    <EmptyState
                                        icon={<GraphIcon />}
                                        title="No team graph yet"
                                        description="Drop an agent template from the Agent library here, or add one manually."
                                        action={
                                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                                <Button
                                                    variant="contained"
                                                    onClick={() => {
                                                        if (hierarchyAgents.length === 0 && templates.length === 0) {
                                                            createDraftNode();
                                                            return;
                                                        }
                                                        setAgentToAddId(hierarchyAgents[0] ? `agent:${hierarchyAgents[0].id}` : templates[0] ? `template:${templates[0].slug}` : "");
                                                        setAddAgentDialogOpen(true);
                                                    }}
                                                >
                                                    Add agent
                                                </Button>
                                                <Button variant="outlined" onClick={() => setManualTab("library")}>
                                                    Open library
                                                </Button>
                                            </Stack>
                                        }
                                    />
                                </Box>
                            ) : (
                                <Suspense fallback={<PageSkeleton variant="canvas" />}>
                                    <HierarchyTeamReactFlow
                                        canvas={canvas}
                                        nodes={nodes}
                                        edges={edges}
                                        nodeTypes={nodeTypes}
                                        graphDirty={graphDirty}
                                        validationCount={validationIssues.length}
                                        showMiniMap={showMiniMap}
                                        onShowMiniMapChange={setShowMiniMap}
                                        onInit={setFlowInstance}
                                        onNodesChange={handleFlowNodesChange}
                                        onEdgesChange={handleFlowEdgesChange}
                                        onConnect={handleFlowConnect}
                                        onNodeClick={(nodeId) => {
                                            setSelectedNodeId(nodeId);
                                            setSelectedEdgeId(null);
                                        }}
                                        onEdgeClick={(edgeId) => {
                                            setSelectedEdgeId(edgeId);
                                            setSelectedNodeId(null);
                                        }}
                                        onPaneClick={() => {
                                            setSelectedNodeId(null);
                                            setSelectedEdgeId(null);
                                            setConsoleOpen(false);
                                        }}
                                        onNodesDelete={(deletedIds) => {
                                            const deleted = new Set(deletedIds);
                                            if (selectedNodeId && deleted.has(selectedNodeId)) {
                                                setSelectedNodeId(null);
                                            }
                                            if (editingTeamNodeId && deleted.has(editingTeamNodeId)) {
                                                closeTeamNodeDrawer();
                                            }
                                            setGraphDirty(true);
                                        }}
                                        onEdgesDelete={(deletedIds) => {
                                            if (selectedEdgeId && deletedIds.includes(selectedEdgeId)) {
                                                setSelectedEdgeId(null);
                                            }
                                            setGraphDirty(true);
                                        }}
                                        draggingHighlight={draggingItem?.type === "agent-template"}
                                        onDragOver={(event) => {
                                            if (draggingItem?.type === "agent-template") {
                                                event.preventDefault();
                                                event.dataTransfer.dropEffect = "copy";
                                            }
                                        }}
                                        onDrop={(event) => {
                                            if (draggingItem?.type !== "agent-template" || !flowInstance) {
                                                return;
                                            }
                                            event.preventDefault();
                                            const position = flowInstance.screenToFlowPosition({
                                                x: event.clientX,
                                                y: event.clientY,
                                            });
                                            addAgentTemplateNode(draggingItem.slug, position);
                                            setDraggingItem(null);
                                        }}
                                    />
                                </Suspense>
                            )}
                        </SectionCard>
                        {isWideHierarchyLayout ? (
                            <Box
                                role="separator"
                                aria-orientation="vertical"
                                aria-label="Resize inspector"
                                onMouseDown={() => setIsResizingInspector(true)}
                                sx={{
                                    display: { xs: "none", xl: "block" },
                                    alignSelf: "stretch",
                                    minHeight: 720,
                                    borderRadius: 1,
                                    cursor: "col-resize",
                                    bgcolor: isResizingInspector ? "primary.main" : "divider",
                                    transition: "background-color 120ms ease",
                                    "&:hover": {
                                        bgcolor: "primary.main",
                                    },
                                }}
                            />
                        ) : null}
                        <Stack spacing={1}>
                            <ExpandableSection title="Team overview" description="Node counts, saved layout state, and validation summary.">
                                <Stack spacing={1.5}>
                                    <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                                        <Chip label={`${nodes.filter((node) => node.data.role === "manager").length} managers`} variant="outlined" />
                                        <Chip label={`${nodes.filter((node) => node.data.role === "specialist").length} specialists`} variant="outlined" />
                                        <Chip label={`${nodes.filter((node) => node.data.role === "reviewer").length} reviewers`} variant="outlined" />
                                        <Chip label={`${edges.length} relationships`} variant="outlined" />
                                    </Stack>
                                    <Typography variant="body2" color="text.secondary">
                                        {savedLayout
                                            ? `Last saved ${formatDateTime(savedLayout.savedAt)} • ${savedLayout.persistence}`
                                            : "Layout not saved yet. Save stores a typed local snapshot until backend persistence exists."}
                                    </Typography>
                                    {selectedEdge ? (
                                        <Alert severity="info">
                                            Selected edge: {selectedEdge.data?.semantic?.replaceAll("_", " ")} from {selectedEdge.source} to {selectedEdge.target}
                                        </Alert>
                                    ) : null}
                                </Stack>
                            </ExpandableSection>

                            {(showValidationPanel || validationIssues.length > 0) ? (
                                <ExpandableSection
                                    title="Validation issues"
                                    description="Client-side checks for common team topology mistakes."
                                    defaultExpanded={validationIssues.length > 0}
                                >
                                    {validationIssues.length === 0 ? (
                                        <Alert severity="success">No client validation issues detected.</Alert>
                                    ) : (
                                        <Stack spacing={1}>
                                            {validationIssues.map((issue) => (
                                                <Alert key={issue.id} severity={issue.severity}>
                                                    {issue.message}
                                                </Alert>
                                            ))}
                                        </Stack>
                                    )}
                                </ExpandableSection>
                            ) : null}

                            <ExpandableSection title="Project scope" description="Available execution projects for local team assignment metadata." defaultExpanded={false}>
                                <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                                    {orchestrationProjects.map((project) => (
                                        <Chip key={project.id} size="small" label={project.name} variant="outlined" />
                                    ))}
                                </Stack>
                            </ExpandableSection>
                            {!isCompact ? (
                                <ExpandableSection title="Inspector" description="Selected node contract editor." defaultExpanded={Boolean(selectedNode)}>
                                    {inspectorContent}
                                </ExpandableSection>
                            ) : null}
                            <ExpandableSection
                                title="Agent library"
                                description="Drag any agent template onto the canvas to add it as a draft node."
                                defaultExpanded={false}
                            >
                                {templates.length === 0 ? (
                                    <Typography variant="body2" color="text.secondary">
                                        No agent templates in library yet.
                                    </Typography>
                                ) : (
                                    <Stack spacing={0.75} sx={{ maxHeight: 320, overflowY: "auto", pr: 0.5 }}>
                                        {templates.map((template) => (
                                            <Paper
                                                key={template.slug}
                                                draggable
                                                onDragStart={() => setDraggingItem({ type: "agent-template", slug: template.slug })}
                                                onDragEnd={() => {
                                                    setDraggingItem(null);
                                                    setActiveDropTarget(null);
                                                }}
                                                variant="outlined"
                                                sx={{
                                                    px: 1.25,
                                                    py: 0.75,
                                                    borderRadius: 1,
                                                    cursor: "grab",
                                                    "&:active": { cursor: "grabbing" },
                                                    "&:hover": { borderColor: "primary.main" },
                                                }}
                                            >
                                                <Stack direction="row" alignItems="center" spacing={1}>
                                                    <DragIndicatorIcon fontSize="small" sx={{ color: "text.disabled" }} />
                                                    <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }} noWrap>
                                                        {template.name}
                                                    </Typography>
                                                    <Chip size="small" label={template.role} variant="outlined" />
                                                </Stack>
                                            </Paper>
                                        ))}
                                    </Stack>
                                )}
                            </ExpandableSection>
                        </Stack>


                    </Box>
                </Stack>
            )}

            {isCompact ? (
                <Drawer anchor="right" open={Boolean(selectedNode)} onClose={() => setSelectedNodeId(null)}>
                    <Box sx={{ width: { xs: 360, sm: 420 }, p: 2.5 }}>
                        {inspectorContent}
                    </Box>
                </Drawer>
            ) : null}

            <AgentTemplateImportReviewDrawer
                key={agentTemplateImportDraft ? `${agentTemplateImportDraft.source_filename ?? "import"}-${agentTemplateImportDraft.raw_markdown}` : "import-empty"}
                open={agentTemplateImportReviewOpen}
                draft={agentTemplateImportDraft}
                toolCatalog={stringOptions.tools}
                onClose={() => setAgentTemplateImportReviewOpen(false)}
                onContinue={continueImportedAgentTemplateDraft}
            />

            <SkillTemplateImportReviewDrawer
                key={skillTemplateImportDraft ? `${skillTemplateImportDraft.source_filename ?? "skill-import"}-${skillTemplateImportDraft.raw_markdown}` : "skill-import-empty"}
                open={skillTemplateImportReviewOpen}
                draft={skillTemplateImportDraft}
                toolCatalog={stringOptions.tools}
                onClose={() => setSkillTemplateImportReviewOpen(false)}
                onContinue={continueImportedSkillTemplateDraft}
            />

            <Drawer
                anchor="right"
                open={agentTemplateDrawerOpen}
                onClose={() => setAgentTemplateDrawerOpen(false)}
                PaperProps={{ sx: { width: { xs: "100vw", lg: 760 } } }}
            >
                <Stack spacing={2} sx={{ p: 3 }}>
                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
                        <Box>
                            <Typography variant="h6">{editingAgentTemplateSlug ? "Edit agent template" : "Add agent template"}</Typography>
                            <Typography variant="body2" color="text.secondary">
                                Build a reusable agent contract: purpose, scope, routing surface, and runtime guardrails.
                            </Typography>
                        </Box>
                        <Stack direction="row" spacing={1}>
                            <Button onClick={() => setAgentTemplateDrawerOpen(false)}>Close</Button>
                            <Button variant="contained" onClick={saveAgentTemplate}>Save</Button>
                        </Stack>
                    </Stack>
                    <Stack spacing={2}>
                        {agentTemplateImportBanner ? (
                            <Alert severity={agentTemplateImportBanner.warningCount > 0 ? "warning" : "success"}>
                                {agentTemplateImportBanner.bannerText}
                            </Alert>
                        ) : null}
                        <Alert severity="info">
                            Start with mission and scope. Then define what work this agent should receive, which tools it may use, and how strict its runtime policy should be.
                        </Alert>
                        <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                            <Stack spacing={1.5}>
                                <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} justifyContent="space-between">
                                    <Box>
                                        <Typography variant="overline" sx={{ letterSpacing: 1.2, color: "text.secondary" }}>
                                            Agent builder flow
                                        </Typography>
                                        <Typography variant="subtitle1">
                                            {form.name.trim() || "Untitled agent template"}
                                        </Typography>
                                        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 72 + "ch" }}>
                                            {form.description.trim() || form.mission_markdown.trim() || "Define the mission first. A strong template starts with clear ownership, then narrows into routing, tooling, and runtime policy."}
                                        </Typography>
                                    </Box>
                                    <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ alignItems: "flex-start", justifyContent: { md: "flex-end" } }}>
                                        <Chip size="small" label="1 Identity" variant="outlined" />
                                        <Chip size="small" label="2 Work" variant="outlined" />
                                        <Chip size="small" label="3 Runtime" variant="outlined" />
                                        <Chip size="small" label="4 Contract" variant="outlined" />
                                    </Stack>
                                </Stack>
                                <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, 1fr)" }, gap: 1 }}>
                                    <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary">Role</Typography>
                                        <Typography variant="body2" sx={{ mt: 0.5 }}>{form.role}</Typography>
                                    </Paper>
                                    <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary">Routing surface</Typography>
                                        <Typography variant="body2" sx={{ mt: 0.5 }}>{parseCsv(form.capabilities).length || 0} capabilities</Typography>
                                    </Paper>
                                    <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary">Runtime</Typography>
                                        <Typography variant="body2" sx={{ mt: 0.5 }}>{form.model || "No primary model set"}</Typography>
                                    </Paper>
                                    <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                        <Typography variant="caption" color="text.secondary">Output</Typography>
                                        <Typography variant="body2" sx={{ mt: 0.5 }}>{form.output_format || "json"}</Typography>
                                    </Paper>
                                </Box>
                            </Stack>
                        </Paper>
                        <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                            <Stack spacing={0.75}>
                                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                                    <Chip size="small" label={form.role} color={getRoleColor(form.role as TeamGraphRole)} variant="outlined" />
                                    {form.parent_template_slug ? <Chip size="small" label={`inherits ${form.parent_template_slug}`} variant="outlined" /> : null}
                                    {form.model ? <Chip size="small" label={`primary ${form.model}`} variant="outlined" /> : null}
                                    {form.output_format ? <Chip size="small" label={`output ${form.output_format}`} variant="outlined" /> : null}
                                </Stack>
                                <Typography variant="body2">{agentRoleGuidance.summary}</Typography>
                                <Typography variant="caption" color="text.secondary">
                                    Strong agent templates are specific about ownership, escalation, and output quality. Weak templates only list a role and a model.
                                </Typography>
                            </Stack>
                        </Paper>
                        <AgentEditorSection step="Step 1" title="Identity & role" description="Name the agent, define its seat in the template tree, and set its broad responsibility.">
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Agent name" placeholder="Backend Builder" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} fullWidth helperText="Human-readable role name shown across orchestration views." />
                                <TextField label="Template slug" placeholder="backend-builder" value={form.slug} onChange={(event) => setForm((current) => ({ ...current, slug: event.target.value }))} fullWidth helperText="Stable identifier used for inheritance and routing references." />
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField select label="Role in team" value={form.role} onChange={(event) => setForm((current) => ({ ...current, role: event.target.value }))} fullWidth helperText="Choose how this agent behaves by default inside a hierarchy.">
                                    {ROLE_OPTIONS.map((role) => (
                                        <MenuItem key={role} value={role}>{role}</MenuItem>
                                    ))}
                                </TextField>
                                <TextField select label="Parent template" value={form.parent_template_slug} onChange={(event) => setForm((current) => ({ ...current, parent_template_slug: event.target.value }))} fullWidth helperText="Optional base template to inherit rules, capabilities, and policy from.">
                                    <MenuItem value="">None</MenuItem>
                                    {templates.filter((item) => item.slug !== editingAgentTemplateSlug).map((template) => (
                                        <MenuItem key={template.slug} value={template.slug}>{template.name}</MenuItem>
                                    ))}
                                </TextField>
                            </Stack>
                            <TextField
                                label="Short description"
                                placeholder="Backend implementation template for API, data, and integration work."
                                multiline
                                minRows={2}
                                helperText="Compact summary shown in libraries and builder cards."
                                value={form.description}
                                onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                            />
                            <TextField
                                label="Mission and scope"
                                placeholder="Own backend implementation for API and data tasks. Deliver tested changes, note tradeoffs, and escalate cross-service risks early."
                                multiline
                                minRows={4}
                                helperText="Long-form mission contract imported from Markdown when available."
                                value={form.mission_markdown}
                                onChange={(event) => setForm((current) => ({ ...current, mission_markdown: event.target.value }))}
                            />
                            <TextField
                                label="Operating instructions"
                                placeholder={agentRoleGuidance.promptHint}
                                multiline
                                minRows={6}
                                helperText="Write the core decision rules this agent should follow on every run."
                                value={form.system_prompt}
                                onChange={(event) => setForm((current) => ({ ...current, system_prompt: event.target.value }))}
                            />
                        </AgentEditorSection>
                        <AgentEditorSection step="Step 2" title="Work surface" description="Define what work this agent is good at, what skills it carries, and which tasks should route here.">
                            <Autocomplete
                                multiple
                                options={skills.map((skill) => skill.slug)}
                                value={form.skills}
                                onChange={(_, nextValue) => setForm((current) => ({ ...current, skills: nextValue }))}
                                getOptionLabel={(option) => skillDisplayName(option, skills)}
                                renderTags={(tagValue, getTagProps) =>
                                    tagValue.map((option, index) => {
                                        const { key, ...tagProps } = getTagProps({ index });
                                        return <Chip key={key} label={skillDisplayName(option, skills)} size="small" {...tagProps} />;
                                    })
                                }
                                renderInput={(params) => <TextField {...params} label="Attached skills" helperText="Reusable skill packs attached to this template." />}
                            />
                            <StringListField
                                label="Capabilities"
                                value={parseCsv(form.capabilities)}
                                onChange={(nextValue: string[]) => setForm((current) => ({ ...current, capabilities: stringifyCommaList(nextValue) }))}
                                helperText="Use concise verbs or domains users can route against: planning, code-review, incident-triage."
                                options={stringOptions.capabilities}
                            />
                            <StringListField
                                label="Allowed tools"
                                value={parseCsv(form.allowed_tools)}
                                onChange={(nextValue: string[]) => setForm((current) => ({ ...current, allowed_tools: stringifyCommaList(nextValue) }))}
                                helperText="Only grant tools this agent genuinely needs."
                                options={stringOptions.tools}
                            />
                            <StringListField
                                label="Tags"
                                value={parseCsv(form.tags)}
                                onChange={(nextValue: string[]) => setForm((current) => ({ ...current, tags: stringifyCommaList(nextValue) }))}
                                helperText="Use tags for domain or governance metadata, not core capability matching."
                                options={stringOptions.tags}
                            />
                            <TaskFiltersField
                                value={parseLooseList(form.task_filters)}
                                onChange={(nextValue: string[]) => setForm((current) => ({ ...current, task_filters: nextValue.join(", ") }))}
                                helperText={agentRoleGuidance.filtersHint}
                            />
                        </AgentEditorSection>
                        <AgentEditorSection step="Step 3" title="Runtime policy" description="Control how this agent runs, escalates, accesses memory, and spends budget.">
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField
                                    select
                                    label="Primary model"
                                    value={form.model}
                                    onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
                                    fullWidth
                                    helperText={
                                        savedProviderModelGroups.length === 0
                                            ? "No saved providers. Add one under Admin → Settings → Providers."
                                            : "Models from your saved providers and discovered model list."
                                    }
                                >
                                    {renderSavedProviderModelMenuItems(form.model, "primary")}
                                </TextField>
                                <TextField
                                    select
                                    label="Fallback model"
                                    value={form.fallback_model}
                                    onChange={(event) => setForm((current) => ({ ...current, fallback_model: event.target.value }))}
                                    fullWidth
                                    helperText="Optional. Used when the primary model is unavailable or unsuitable."
                                >
                                    {renderSavedProviderModelMenuItems(form.fallback_model, "fallback")}
                                </TextField>
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Escalation path" placeholder="lead-manager" helperText="Who should receive work this agent cannot safely complete?" value={form.escalation_path} onChange={(event) => setForm((current) => ({ ...current, escalation_path: event.target.value }))} fullWidth />
                                <TextField select label="Permission level" value={form.permission} onChange={(event) => setForm((current) => ({ ...current, permission: event.target.value }))} fullWidth helperText="Keep this as low as possible for the role.">
                                    {PERMISSION_OPTIONS.map((item) => (
                                        <MenuItem key={item} value={item}>{item}</MenuItem>
                                    ))}
                                </TextField>
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField select label="Memory scope" value={form.memory_scope} onChange={(event) => setForm((current) => ({ ...current, memory_scope: event.target.value }))} fullWidth helperText="How much prior context this agent may retain or recall.">
                                    {MEMORY_SCOPE_OPTIONS.map((item) => (
                                        <MenuItem key={item} value={item}>{item}</MenuItem>
                                    ))}
                                </TextField>
                                <TextField select label="Default output contract" value={form.output_format} onChange={(event) => setForm((current) => ({ ...current, output_format: event.target.value }))} fullWidth helperText="Default structure downstream systems should expect from this agent.">
                                    {OUTPUT_FORMAT_OPTIONS.map((item) => (
                                        <MenuItem key={item} value={item}>{item}</MenuItem>
                                    ))}
                                </TextField>
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Token budget" helperText="Ceiling for prompt + completion tokens per run." value={form.token_budget} onChange={(event) => setForm((current) => ({ ...current, token_budget: event.target.value }))} fullWidth />
                                <TextField label="Time budget (s)" helperText="Maximum runtime before the system should fail or escalate." value={form.time_budget_seconds} onChange={(event) => setForm((current) => ({ ...current, time_budget_seconds: event.target.value }))} fullWidth />
                                <TextField label="Retry budget" helperText="How many automatic retries are allowed before escalation." value={form.retry_budget} onChange={(event) => setForm((current) => ({ ...current, retry_budget: event.target.value }))} fullWidth />
                            </Stack>
                            <TextField
                                label="Rules markdown"
                                placeholder="Non-negotiable guardrails, review gates, and operating constraints."
                                helperText="Keep durable rules here so imported guardrails are not lost."
                                value={form.rules_markdown}
                                onChange={(event) => setForm((current) => ({ ...current, rules_markdown: event.target.value }))}
                                multiline
                                minRows={4}
                            />
                        </AgentEditorSection>
                        <AgentEditorSection step="Step 4" title="Contract preview" description="Final check of what this template tells the system about ownership, runtime behavior, and expected output." defaultExpanded={false}>
                            <Stack spacing={1.25}>
                                <TextField
                                    label="Mission summary"
                                    value={form.mission_markdown.trim() || form.description.trim() || "No mission defined yet."}
                                    multiline
                                    minRows={3}
                                    fullWidth
                                    InputProps={{ readOnly: true }}
                                />
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField label="Primary model" value={form.model || "Not set"} fullWidth InputProps={{ readOnly: true }} />
                                    <TextField label="Escalates to" value={form.escalation_path || "Not set"} fullWidth InputProps={{ readOnly: true }} />
                                </Stack>
                                <TextField
                                    label="Routing surface"
                                    value={parseCsv(form.capabilities).join(", ") || "No capabilities defined yet."}
                                    fullWidth
                                    InputProps={{ readOnly: true }}
                                />
                                <TextField
                                    label="Output contract"
                                    value={`${form.output_format || "json"} • permission ${form.permission} • memory ${form.memory_scope}`}
                                    fullWidth
                                    InputProps={{ readOnly: true }}
                                />
                                <TextField
                                    label="Output contract markdown"
                                    value={form.output_contract_markdown.trim() || "No explicit output contract yet."}
                                    multiline
                                    minRows={3}
                                    fullWidth
                                    onChange={(event) => setForm((current) => ({ ...current, output_contract_markdown: event.target.value }))}
                                />
                            </Stack>
                        </AgentEditorSection>
                    </Stack>
                </Stack>
            </Drawer>

            <Drawer
                anchor="right"
                open={teamNodeDrawerOpen}
                onClose={closeTeamNodeDrawer}
                PaperProps={{ sx: { width: { xs: "100vw", lg: 760 } } }}
            >
                <Stack spacing={2} sx={{ p: 3 }}>
                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
                        <Box>
                            <Typography variant="h6">Edit team graph agent</Typography>
                            <Typography variant="body2" color="text.secondary">
                                Builder drawer for selected graph node, same right-side workflow as library.
                            </Typography>
                        </Box>
                        <Stack direction="row" spacing={1}>
                            <Button onClick={closeTeamNodeDrawer}>Close</Button>
                            <Button variant="contained" onClick={saveTeamNode} disabled={!teamNodeDraft || teamNodeSaving}>
                                Save
                            </Button>
                        </Stack>
                    </Stack>
                    {teamNodeDraft ? (
                        <Stack spacing={2}>
                            <AgentEditorSection title="Basics" description="Identity, role, and local graph linkage.">
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField
                                        label="Name"
                                        value={teamNodeDraft.name}
                                        onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, name: event.target.value } : current)}
                                        fullWidth
                                    />
                                    <TextField
                                        label="Slug"
                                        value={teamNodeDraft.slug}
                                        onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, slug: event.target.value } : current)}
                                        fullWidth
                                    />
                                </Stack>
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField
                                        select
                                        label="Role"
                                        value={teamNodeDraft.role}
                                        onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, role: event.target.value as TeamGraphRole } : current)}
                                        fullWidth
                                    >
                                        {ROLE_OPTIONS.map((role) => (
                                            <MenuItem key={role} value={role}>{role}</MenuItem>
                                        ))}
                                    </TextField>
                                    <TextField
                                        select
                                        label="Linked template"
                                        value={teamNodeDraft.linkedTemplateSlug}
                                        onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, linkedTemplateSlug: event.target.value } : current)}
                                        fullWidth
                                    >
                                        <MenuItem value="">None</MenuItem>
                                        {templates.map((template) => (
                                            <MenuItem key={template.slug} value={template.slug}>{template.name}</MenuItem>
                                        ))}
                                    </TextField>
                                </Stack>
                                <TextField
                                    select
                                    label="Linked saved agent"
                                    value={teamNodeDraft.linkedAgentId}
                                    onChange={(event) => {
                                        const linkedAgentId = event.target.value;
                                        setTeamNodeDraft((current) => current ? { ...current, linkedAgentId } : current);
                                        if (linkedAgentId) {
                                            hydrateTeamNodeDraftFromAgent(linkedAgentId);
                                        }
                                    }}
                                    fullWidth
                                >
                                    <MenuItem value="">None</MenuItem>
                                    {hierarchyAgents.map((agent) => (
                                        <MenuItem key={agent.id} value={agent.id}>{agent.name}</MenuItem>
                                    ))}
                                </TextField>
                                <TextField
                                    label="Description"
                                    multiline
                                    minRows={4}
                                    value={teamNodeDraft.description}
                                    onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, description: event.target.value } : current)}
                                />
                            </AgentEditorSection>
                            <AgentEditorSection title="Skills & capabilities" description="Graph-level capability, tool, tag, and routing metadata.">
                                <StringListField
                                    label="Capabilities"
                                    value={teamNodeDraft.capabilities}
                                    onChange={(nextValue: string[]) => setTeamNodeDraft((current) => current ? { ...current, capabilities: nextValue } : current)}
                                    helperText="Capability chips describe owned work."
                                    placeholder="Type capability, press Enter"
                                    options={stringOptions.capabilities}
                                />
                                <StringListField
                                    label="Allowed tools"
                                    value={teamNodeDraft.allowedTools}
                                    onChange={(nextValue: string[]) => setTeamNodeDraft((current) => current ? { ...current, allowedTools: nextValue } : current)}
                                    helperText="Grant only tools this node needs."
                                    options={stringOptions.tools}
                                />
                                <StringListField
                                    label="Tags"
                                    value={teamNodeDraft.tags}
                                    onChange={(nextValue: string[]) => setTeamNodeDraft((current) => current ? { ...current, tags: nextValue } : current)}
                                    helperText="Use tags for domain or routing metadata."
                                    options={stringOptions.tags}
                                />
                                <StringListField
                                    label="Project assignments"
                                    value={teamNodeDraft.projectAssignments}
                                    onChange={(nextValue: string[]) => setTeamNodeDraft((current) => current ? { ...current, projectAssignments: nextValue } : current)}
                                    helperText="Local mapping until backend team layout persistence exists."
                                    options={stringOptions.projects}
                                />
                                <TaskFiltersField
                                    value={teamNodeDraft.taskFilters}
                                    onChange={(nextValue: string[]) => setTeamNodeDraft((current) => current ? { ...current, taskFilters: nextValue } : current)}
                                    helperText="One routing rule per line."
                                />
                            </AgentEditorSection>
                            <AgentEditorSection title="Execution" description="Model routing, permissions, memory, and output expectations.">
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField
                                        select
                                        label="Primary model"
                                        value={teamNodeDraft.model}
                                        onChange={(event) =>
                                            setTeamNodeDraft((current) => (current ? { ...current, model: event.target.value } : current))
                                        }
                                        fullWidth
                                        helperText={
                                            savedProviderModelGroups.length === 0
                                                ? "No saved providers. Add one under Admin → Settings → Providers."
                                                : "Models from saved providers."
                                        }
                                    >
                                        {renderSavedProviderModelMenuItems(teamNodeDraft.model, "primary")}
                                    </TextField>
                                    <TextField
                                        select
                                        label="Fallback model"
                                        value={teamNodeDraft.fallbackModel}
                                        onChange={(event) =>
                                            setTeamNodeDraft((current) =>
                                                current ? { ...current, fallbackModel: event.target.value } : current,
                                            )
                                        }
                                        fullWidth
                                        helperText="Optional secondary model slug."
                                    >
                                        {renderSavedProviderModelMenuItems(teamNodeDraft.fallbackModel, "fallback")}
                                    </TextField>
                                </Stack>
                                <TextField
                                    label="Escalation path"
                                    value={teamNodeDraft.escalationPath}
                                    onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, escalationPath: event.target.value } : current)}
                                    helperText="Target node id, slug, or name."
                                    fullWidth
                                />
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField
                                        select
                                        label="Permission"
                                        value={teamNodeDraft.permission}
                                        onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, permission: event.target.value } : current)}
                                        fullWidth
                                    >
                                        {PERMISSION_OPTIONS.map((item) => (
                                            <MenuItem key={item} value={item}>{item}</MenuItem>
                                        ))}
                                    </TextField>
                                    <TextField
                                        select
                                        label="Memory scope"
                                        value={teamNodeDraft.memoryScope}
                                        onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, memoryScope: event.target.value } : current)}
                                        fullWidth
                                    >
                                        {MEMORY_SCOPE_OPTIONS.map((item) => (
                                            <MenuItem key={item} value={item}>{item}</MenuItem>
                                        ))}
                                    </TextField>
                                </Stack>
                                <TextField
                                    select
                                    label="Output format"
                                    value={teamNodeDraft.outputFormat}
                                    onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, outputFormat: event.target.value } : current)}
                                    fullWidth
                                >
                                    {OUTPUT_FORMAT_OPTIONS.map((item) => (
                                        <MenuItem key={item} value={item}>{item}</MenuItem>
                                    ))}
                                </TextField>
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField
                                        label="Token budget"
                                        value={teamNodeDraft.tokenBudget}
                                        onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, tokenBudget: event.target.value } : current)}
                                        fullWidth
                                    />
                                    <TextField
                                        label="Time budget (s)"
                                        value={teamNodeDraft.timeBudgetSeconds}
                                        onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, timeBudgetSeconds: event.target.value } : current)}
                                        fullWidth
                                    />
                                    <TextField
                                        label="Retry budget"
                                        value={teamNodeDraft.retryBudget}
                                        onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, retryBudget: event.target.value } : current)}
                                        fullWidth
                                    />
                                </Stack>
                            </AgentEditorSection>
                        </Stack>
                    ) : null}
                </Stack>
            </Drawer>

            <Drawer
                anchor="right"
                open={skillTemplateDrawerOpen}
                onClose={() => setSkillTemplateDrawerOpen(false)}
                PaperProps={{ sx: { width: { xs: "100vw", sm: 640 } } }}
            >
                <Stack spacing={2} sx={{ p: 3 }}>
                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
                        <Box>
                            <Typography variant="h6">{editingSkillSlug ? "Edit skill template" : "Add skill template"}</Typography>
                            <Typography variant="body2" color="text.secondary">
                                Build a reusable skill pack: what it adds to an agent, which tools it assumes, and what behavioral rules it injects.
                            </Typography>
                        </Box>
                        <Stack direction="row" spacing={1}>
                            <Button onClick={() => setSkillTemplateDrawerOpen(false)}>Close</Button>
                            <Button variant="contained" onClick={saveSkillTemplate}>Save</Button>
                        </Stack>
                    </Stack>
                    {skillTemplateImportBanner ? (
                        <Alert severity="success">
                            {skillTemplateImportBanner.bannerText}
                        </Alert>
                    ) : null}
                    <Alert severity="info">
                        Good skills are narrow and reusable. They should add a recognizable behavior pattern to many agents, not duplicate the full identity of one agent.
                    </Alert>
                    <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                        <Stack spacing={1.5}>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} justifyContent="space-between">
                                <Box>
                                    <Typography variant="overline" sx={{ letterSpacing: 1.2, color: "text.secondary" }}>
                                        Skill builder flow
                                    </Typography>
                                    <Typography variant="subtitle1">
                                        {skillForm.name.trim() || "Untitled skill template"}
                                    </Typography>
                                    <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 72 + "ch" }}>
                                        {skillForm.description.trim() || "Define the reusable behavior this skill adds to an agent. Strong skills are composable, focused, and explicit about tools and rules."}
                                    </Typography>
                                </Box>
                                <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ alignItems: "flex-start", justifyContent: { md: "flex-end" } }}>
                                    <Chip size="small" label="1 Identity" variant="outlined" />
                                    <Chip size="small" label="2 Surface" variant="outlined" />
                                    <Chip size="small" label="3 Rules" variant="outlined" />
                                </Stack>
                            </Stack>
                            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, 1fr)" }, gap: 1 }}>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                    <Typography variant="caption" color="text.secondary">Capabilities</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{skillForm.capabilities.length} linked</Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                    <Typography variant="caption" color="text.secondary">Allowed tools</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{skillForm.allowed_tools.length} required</Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                    <Typography variant="caption" color="text.secondary">Tags</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{skillForm.tags.length} labels</Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                    <Typography variant="caption" color="text.secondary">Instruction depth</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{skillForm.rules_markdown.trim() ? "Defined" : "Missing"}</Typography>
                                </Paper>
                            </Box>
                        </Stack>
                    </Paper>
                    <AgentEditorSection step="Step 1" title="Identity" description="Name the skill and define the reusable behavior it adds to any agent template.">
                        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                            <TextField
                                label="Skill name"
                                placeholder="PR review discipline"
                                value={skillForm.name}
                                onChange={(event) => setSkillForm((current) => ({ ...current, name: event.target.value }))}
                                helperText="Human-readable name shown when attaching this skill to agents."
                                fullWidth
                            />
                            <TextField
                                label="Skill slug"
                                placeholder="pr-review-discipline"
                                value={skillForm.slug}
                                onChange={(event) => setSkillForm((current) => ({ ...current, slug: event.target.value }))}
                                helperText="Stable identifier used across templates."
                                fullWidth
                            />
                        </Stack>
                            <TextField
                                label="What this skill adds"
                                placeholder="Adds a disciplined PR review loop: inspect changed files, identify concrete risks, demand evidence, and separate findings from summaries."
                                multiline
                                minRows={3}
                                value={skillForm.description}
                                onChange={(event) => setSkillForm((current) => ({ ...current, description: event.target.value }))}
                                helperText="Describe the reusable behavior or operating pattern this skill injects. Imported Markdown should land here as the short human summary."
                            />
                        </AgentEditorSection>
                    <AgentEditorSection step="Step 2" title="Skill surface" description="Define the capability signals, tools, and metadata that make this skill attachable and discoverable.">
                        <StringListField
                            label="Capabilities added"
                            value={skillForm.capabilities}
                            onChange={(nextValue: string[]) => setSkillForm((current) => ({ ...current, capabilities: nextValue }))}
                            helperText="Use concise routing-friendly labels like qa, decomposition, repo-triage, benchmark-design."
                            options={stringOptions.capabilities}
                        />
                        <StringListField
                            label="Required tools"
                            value={skillForm.allowed_tools}
                            onChange={(nextValue: string[]) => setSkillForm((current) => ({ ...current, allowed_tools: nextValue }))}
                            helperText="List only the tools this skill assumes the host agent can use."
                            options={stringOptions.tools}
                        />
                        <StringListField
                            label="Tags"
                            value={skillForm.tags}
                            onChange={(nextValue: string[]) => setSkillForm((current) => ({ ...current, tags: nextValue }))}
                            helperText="Optional metadata for domain, governance, or workflow grouping."
                            options={stringOptions.tags}
                        />
                    </AgentEditorSection>
                    <AgentEditorSection step="Step 3" title="Injected rules" description="Write the instructions that should merge into an agent whenever this skill is attached.">
                        <TextField
                            label="Skill rules"
                            placeholder={"When reviewing code:\n- prioritize concrete bugs and regressions\n- cite affected files or functions\n- separate findings from suggestions\n- do not approve without evidence"}
                            multiline
                            minRows={8}
                            value={skillForm.rules_markdown}
                            onChange={(event) => setSkillForm((current) => ({ ...current, rules_markdown: event.target.value }))}
                            helperText="Write reusable rules, not full agent identity. Imported Markdown instructions should be trimmed into durable, attachable behavior here."
                        />
                        <TextField
                            label="Preview"
                            value={
                                skillForm.rules_markdown.trim()
                                    ? `${skillForm.capabilities.length} capabilities • ${skillForm.allowed_tools.length} tools • injects explicit behavior rules`
                                    : "Add rules so this skill changes how an agent behaves, not just how it is labeled."
                            }
                            fullWidth
                            InputProps={{ readOnly: true }}
                        />
                    </AgentEditorSection>
                </Stack>
            </Drawer>

            <Drawer
                anchor="right"
                open={teamTemplateDrawerOpen}
                onClose={() => setTeamTemplateDrawerOpen(false)}
                PaperProps={{ sx: { width: { xs: "100vw", sm: 760 } } }}
            >
                <Stack spacing={2} sx={{ p: 3 }}>
                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
                        <Box>
                            <Typography variant="h6">{editingTeamTemplateId ? "Edit team template" : "Add team template"}</Typography>
                            <Typography variant="body2" color="text.secondary">
                                Compose reusable teams by combining agent templates. Team metadata stays minimal; roles and tools are derived from the agents you include.
                            </Typography>
                        </Box>
                        <Stack direction="row" spacing={1}>
                            <Button onClick={() => setTeamTemplateDrawerOpen(false)}>Close</Button>
                            <Button variant="contained" onClick={saveTeamTemplate}>Save</Button>
                        </Stack>
                    </Stack>
                    <Alert severity="info">
                        Best practice: build the team from agent templates first. Use extra metadata only to explain the team’s purpose and sharing model.
                    </Alert>
                    <Paper variant="outlined" sx={{ p: 2, borderRadius: 1 }}>
                        <Stack spacing={1.5}>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} justifyContent="space-between">
                                <Box>
                                    <Typography variant="overline" sx={{ letterSpacing: 1.2, color: "text.secondary" }}>
                                        Team builder flow
                                    </Typography>
                                    <Typography variant="subtitle1">
                                        {teamTemplateForm.name.trim() || "Untitled team template"}
                                    </Typography>
                                    <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 72 + "ch" }}>
                                        {teamTemplateForm.outcome.trim() || "Define team purpose, then compose the team from agent templates. Roles, tools, and skill coverage will be derived automatically."}
                                    </Typography>
                                </Box>
                                <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" sx={{ alignItems: "flex-start", justifyContent: { md: "flex-end" } }}>
                                    <Chip size="small" label="1 Metadata" variant="outlined" />
                                    <Chip size="small" label="2 Composition" variant="outlined" />
                                    <Chip size="small" label="3 Derived summary" variant="outlined" />
                                </Stack>
                            </Stack>
                            <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "repeat(4, 1fr)" }, gap: 1 }}>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                    <Typography variant="caption" color="text.secondary">Agents</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{selectedTeamAgentTemplates.length} selected</Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                    <Typography variant="caption" color="text.secondary">Roles</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{derivedTeamTemplateSummary.roles.length} derived</Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                    <Typography variant="caption" color="text.secondary">Tools</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{derivedTeamTemplateSummary.tools.length} derived</Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 1 }}>
                                    <Typography variant="caption" color="text.secondary">Visibility</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{teamTemplateForm.visibility || "private"}</Typography>
                                </Paper>
                            </Box>
                        </Stack>
                    </Paper>
                    <AgentEditorSection step="Step 1" title="Minimal metadata" description="Only keep metadata users actually need: name, purpose, and sharing model.">
                        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                            <TextField label="Team name" placeholder="Release strike team" value={teamTemplateForm.name} onChange={(event) => setTeamTemplateForm((current) => ({ ...current, name: event.target.value }))} fullWidth helperText="Display name for this reusable team." />
                            <TextField label="Template slug" placeholder="release-strike-team" value={teamTemplateForm.slug} onChange={(event) => setTeamTemplateForm((current) => ({ ...current, slug: event.target.value }))} fullWidth helperText="Stable identifier for the team template." />
                        </Stack>
                        <TextField label="What this team is for" placeholder="Coordinates planning, implementation, and review for high-risk releases." multiline minRows={3} value={teamTemplateForm.description} onChange={(event) => setTeamTemplateForm((current) => ({ ...current, description: event.target.value }))} helperText="Describe the team’s mission and usage context." />
                        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                            <TextField label="Outcome" placeholder="Ship release work with planning, implementation, and review coverage." value={teamTemplateForm.outcome} onChange={(event) => setTeamTemplateForm((current) => ({ ...current, outcome: event.target.value }))} fullWidth helperText="Short statement of what this team should reliably deliver." />
                            <TextField select label="Visibility" value={teamTemplateForm.visibility} onChange={(event) => setTeamTemplateForm((current) => ({ ...current, visibility: event.target.value }))} fullWidth helperText="Whether other users should reuse this team template.">
                                <MenuItem value="private">private</MenuItem>
                                <MenuItem value="shared">shared</MenuItem>
                                <MenuItem value="public">public</MenuItem>
                            </TextField>
                        </Stack>
                    </AgentEditorSection>
                    <AgentEditorSection step="Step 2" title="Team composition" description="Build the team by selecting or dragging agent templates. The team should be defined by its members, not by extra knobs.">
                        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", xl: "minmax(0, 1fr) 280px" }, gap: 2 }}>
                            <Paper
                                variant="outlined"
                                onDragOver={(event) => {
                                    if (draggingItem?.type !== "agent-template") return;
                                    event.preventDefault();
                                }}
                                onDrop={() => {
                                    if (draggingItem?.type === "agent-template") {
                                        attachAgentTemplateToTeamTemplateDraft(draggingItem.slug);
                                    }
                                    setDraggingItem(null);
                                    setActiveDropTarget(null);
                                }}
                                sx={{
                                    p: 1,
                                    borderRadius: 1,
                                    borderStyle: "dashed",
                                    bgcolor: draggingItem?.type === "agent-template" ? "action.hover" : "background.paper",
                                }}
                            >
                                {teamTemplateCanvasNodes.length === 0 ? (
                                    <EmptyState
                                        icon={<GraphIcon />}
                                        title="Empty team canvas"
                                        description="Drag agent templates here to compose the team visually."
                                    />
                                ) : (
                                    <Suspense fallback={<PageSkeleton variant="canvas" />}>
                                        <HierarchyTemplatePreviewFlow
                                            canvas={canvas}
                                            nodes={teamTemplateCanvasNodes}
                                            edges={teamTemplateCanvasEdges}
                                            nodeTypes={nodeTypes}
                                            onNodesChange={onTeamTemplateCanvasNodesChange}
                                            onNodeClick={(nodeId) => setSelectedTeamTemplateCanvasNodeId(nodeId)}
                                            onPaneClick={() => setSelectedTeamTemplateCanvasNodeId(null)}
                                        />
                                    </Suspense>
                                )}
                                <Typography variant="caption" color="text.secondary" sx={{ display: "block", px: 1, pt: 1 }}>
                                    Canvas is composition-first preview. Saved template persists included agent templates; exact node coordinates are not stored yet.
                                </Typography>
                            </Paper>
                            <Stack spacing={1.25}>
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Typography variant="subtitle2">Canvas inspector</Typography>
                                    {selectedTeamTemplateCanvasNode ? (
                                        <Stack spacing={1} sx={{ mt: 1 }}>
                                            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                                                <Typography variant="body2">{selectedTeamTemplateCanvasNode.data.name}</Typography>
                                                <Chip size="small" label={selectedTeamTemplateCanvasNode.data.role} color={getRoleColor(selectedTeamTemplateCanvasNode.data.role)} variant="outlined" />
                                            </Stack>
                                            <Typography variant="body2" color="text.secondary">
                                                {selectedTeamTemplateCanvasNode.data.description || "No description provided."}
                                            </Typography>
                                            <Button color="error" onClick={() => removeAgentTemplateFromTeamTemplateDraft(selectedTeamTemplateCanvasNode.data.slug)}>
                                                Remove from team
                                            </Button>
                                        </Stack>
                                    ) : (
                                        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                                            Select a node in the canvas to inspect or remove it.
                                        </Typography>
                                    )}
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 1 }}>
                                    <Typography variant="subtitle2">Agent template library</Typography>
                                    <Stack spacing={1} sx={{ mt: 1 }}>
                                        {templates.length === 0 ? (
                                            <Typography variant="body2" color="text.secondary">No agent templates available.</Typography>
                                        ) : templates.map((template) => {
                                            const isIncluded = teamTemplateForm.agent_template_slugs.includes(template.slug);
                                            return (
                                                <Paper
                                                    key={template.slug}
                                                    variant="outlined"
                                                    draggable={!isIncluded}
                                                    onDragStart={() => !isIncluded && setDraggingItem({ type: "agent-template", slug: template.slug })}
                                                    onDragEnd={() => setDraggingItem(null)}
                                                    sx={{ p: 1.25, borderRadius: 1, opacity: isIncluded ? 0.6 : 1 }}
                                                >
                                                    <Stack direction="row" justifyContent="space-between" spacing={1}>
                                                        <Box>
                                                            <Typography variant="body2">{template.name}</Typography>
                                                            <Typography variant="caption" color="text.secondary">
                                                                {template.role} • {template.slug}
                                                            </Typography>
                                                        </Box>
                                                        <Button
                                                            size="small"
                                                            variant={isIncluded ? "outlined" : "contained"}
                                                            onClick={() => isIncluded ? removeAgentTemplateFromTeamTemplateDraft(template.slug) : attachAgentTemplateToTeamTemplateDraft(template.slug)}
                                                        >
                                                            {isIncluded ? "Remove" : "Add"}
                                                        </Button>
                                                    </Stack>
                                                </Paper>
                                            );
                                        })}
                                    </Stack>
                                </Paper>
                            </Stack>
                        </Box>
                    </AgentEditorSection>
                    <AgentEditorSection step="Step 3" title="Derived summary" description="These fields are inferred from the selected agent templates and saved automatically.">
                        <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                            {derivedTeamTemplateSummary.roles.length > 0 ? derivedTeamTemplateSummary.roles.map((role) => (
                                <Chip key={role} size="small" label={`role ${role}`} variant="outlined" />
                            )) : <Chip size="small" label="No roles derived yet" variant="outlined" />}
                        </Stack>
                        <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                            {derivedTeamTemplateSummary.tools.length > 0 ? derivedTeamTemplateSummary.tools.map((tool) => (
                                <Chip key={tool} size="small" label={`tool ${tool}`} variant="outlined" />
                            )) : <Chip size="small" label="No tools derived yet" variant="outlined" />}
                        </Stack>
                        <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
                            {derivedTeamTemplateSummary.skillsUsed.length > 0 ? derivedTeamTemplateSummary.skillsUsed.map((slug) => (
                                <Chip key={slug} size="small" label={`skill ${skillDisplayName(slug, skills)}`} variant="outlined" />
                            )) : <Chip size="small" label="No attached skills derived yet" variant="outlined" />}
                        </Stack>
                        <TextField
                            label="Saved team contract"
                            value={
                                selectedTeamAgentTemplates.length > 0
                                    ? `${selectedTeamAgentTemplates.length} agents • ${derivedTeamTemplateSummary.roles.length} roles • ${derivedTeamTemplateSummary.tools.length} tools derived`
                                    : "Select agent templates to construct the team."
                            }
                            fullWidth
                            InputProps={{ readOnly: true }}
                        />
                    </AgentEditorSection>
                </Stack>
            </Drawer>

            <Dialog open={addAgentDialogOpen} onClose={() => setAddAgentDialogOpen(false)} maxWidth="sm" fullWidth>
                <DialogTitle>Add agent to team</DialogTitle>
                <DialogContent>
                    <Stack spacing={2} sx={{ mt: 1 }}>
                        <Alert severity="info">
                            Pick saved agent, template from library, or create local draft.
                        </Alert>
                        <TextField
                            select
                            label="Agent or template"
                            value={agentToAddId}
                            onChange={(event) => setAgentToAddId(event.target.value)}
                            fullWidth
                            helperText="Saved agents bind to a live contract. Templates insert as draft nodes."
                        >
                            {hierarchyAgents.length === 0 && templates.length === 0 ? (
                                <MenuItem value="" disabled>
                                    No agents or templates available.
                                </MenuItem>
                            ) : null}
                            {hierarchyAgents.length > 0 ? (
                                <ListSubheader>Saved agents</ListSubheader>
                            ) : null}
                            {hierarchyAgents.map((agent) => (
                                <MenuItem key={`agent:${agent.id}`} value={`agent:${agent.id}`}>
                                    {agent.name} • {agent.role} • {agent.slug}
                                </MenuItem>
                            ))}
                            {templates.length > 0 ? (
                                <ListSubheader>Library templates</ListSubheader>
                            ) : null}
                            {templates.map((template) => (
                                <MenuItem key={`template:${template.slug}`} value={`template:${template.slug}`}>
                                    {template.name} • {template.role} • {template.slug}
                                </MenuItem>
                            ))}
                        </TextField>
                    </Stack>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => {
                        setAddAgentDialogOpen(false);
                        createDraftNode();
                    }}>
                        New draft
                    </Button>
                    <Button onClick={() => setAddAgentDialogOpen(false)}>Cancel</Button>
                    <Button
                        variant="contained"
                        onClick={() => {
                            if (agentToAddId.startsWith("template:")) {
                                addAgentTemplateNode(agentToAddId.slice("template:".length));
                            } else if (agentToAddId.startsWith("agent:")) {
                                addAgentNode(agentToAddId.slice("agent:".length));
                            }
                        }}
                        disabled={!agentToAddId}
                    >
                        Add agent
                    </Button>
                </DialogActions>
            </Dialog>

            <Drawer
                anchor="right"
                open={consoleOpen}
                onClose={() => setConsoleOpen(false)}
                variant={isWideHierarchyLayout ? "persistent" : "temporary"}
                ModalProps={{ keepMounted: true }}
                PaperProps={{
                    sx: {
                        width: { xs: "100%", sm: 420 },
                        p: 2,
                        boxSizing: "border-box",
                        top: { md: 64 },
                        height: { md: "calc(100% - 64px)" },
                    },
                }}
            >
                <Box ref={consolePanelRef}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                        <Typography variant="subtitle1">Operating console</Typography>
                        <IconButton size="small" aria-label="Close console" onClick={() => setConsoleOpen(false)}>
                            <CloseIcon fontSize="small" />
                        </IconButton>
                    </Stack>
                    <AgentOperatingConsole projectId={effectiveHierarchyProjectId || undefined} />
                </Box>
            </Drawer>

            </>
            )}

        </PageShell>
        </ReactFlowProvider>
    );
}
