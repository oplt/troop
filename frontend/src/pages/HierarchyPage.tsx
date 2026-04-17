import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import {
    Alert,
    Accordion,
    AccordionDetails,
    AccordionSummary,
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
    ContentCopy as DuplicateIcon,
    DeleteOutline as DeleteIcon,
    ExpandMore as ExpandMoreIcon,
    FactCheck as ReviewerIcon,
    Hub as GraphIcon,
    ManageAccounts as ManagerIcon,
    Save as SaveIcon,
    Engineering as SpecialistIcon,
    RestartAlt as ResetIcon,
    SmartToy as AgentIcon,
    TaskAlt as ValidateIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import {
    addEdge,
    Background,
    Controls,
    Handle,
    MarkerType,
    Position,
    ReactFlow,
    useEdgesState,
    useNodesState,
    type Connection,
    type Edge,
    type Node,
    type NodeProps,
    type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
    createAgentTemplate,
    createSkillPack,
    createTeamTemplate,
    deleteAgentTemplate,
    deleteSkillPack,
    deleteTeamTemplate,
    listAgents,
    listAgentTemplates,
    listOrchestrationProjects,
    listRuns,
    listSkillCatalog,
    listTeamTemplates,
    updateAgentTemplate,
    updateSkillPack,
    updateTeamTemplate,
} from "../api/orchestration";
import type {
    Agent,
    AgentTemplate,
    SkillPack,
    TeamTemplate,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { formatDateTime } from "../utils/formatters";

const MEMORY_SCOPE_OPTIONS = ["none", "project-only", "long-term"] as const;
const OUTPUT_FORMAT_OPTIONS = ["checklist", "json", "patch_proposal", "issue_reply", "adr"] as const;
const PERMISSION_OPTIONS = ["read-only", "comment-only", "code-write", "merge-blocked"] as const;
const ROLE_OPTIONS = ["manager", "specialist", "reviewer"] as const;

const EMPTY_FORM = {
    name: "",
    slug: "",
    description: "",
    role: "specialist",
    system_prompt: "",
    parent_template_slug: "",
    capabilities: "",
    allowed_tools: "",
    skills: [] as string[],
    tags: "",
    task_filters: "",
    model: "",
    fallback_model: "",
    escalation_path: "",
    permission: "read-only",
    memory_scope: "project-only",
    output_format: "json",
    token_budget: "8000",
    time_budget_seconds: "300",
    retry_budget: "1",
};

type BuilderTab = "library" | "hierarchy";
type TeamGraphRole = "manager" | "specialist" | "reviewer";
type TeamGraphEdgeSemantic = "delegates_to" | "reviews" | "escalates_to" | "collaborates_with";
type TeamGraphNodeStatus = "active" | "inactive" | "running" | "blocked" | "queued" | "draft";
type ValidationSeverity = "error" | "warning";

type TeamGraphNodeData = {
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

type TeamGraphNode = Node<TeamGraphNodeData, TeamGraphRole>;
type TeamGraphEdge = Edge<{ semantic: TeamGraphEdgeSemantic }>;

type TeamGraphValidationIssue = {
    id: string;
    severity: ValidationSeverity;
    message: string;
    nodeId?: string;
    edgeId?: string;
};

type TeamLayoutSnapshot = {
    savedAt: string;
    nodes: TeamGraphNode[];
    edges: TeamGraphEdge[];
    persistence: "local-only";
};

type StringListFieldProps = {
    label: string;
    value: string[];
    onChange: (nextValue: string[]) => void;
    helperText?: string;
    placeholder?: string;
    options?: string[];
};

type SkillTemplateFormState = {
    name: string;
    slug: string;
    description: string;
    capabilities: string[];
    allowed_tools: string[];
    tags: string[];
    rules_markdown: string;
};

type TeamTemplateFormState = {
    name: string;
    slug: string;
    description: string;
    outcome: string;
    roles: string[];
    tools: string[];
    autonomy: string;
    visibility: string;
    agent_template_slugs: string[];
};

function parseCsv(value: string): string[] {
    return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

function parseLooseList(value: string): string[] {
    return value
        .split(/[\n,]/g)
        .map((item) => item.trim())
        .filter(Boolean);
}

function slugify(value: string) {
    return value
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/(^-|-$)/g, "");
}

function createUniqueSlug(value: string, existingSlugs: string[]) {
    const base = slugify(value) || "untitled-template";
    if (!existingSlugs.includes(base)) {
        return base;
    }
    let index = 2;
    while (existingSlugs.includes(`${base}-${index}`)) {
        index += 1;
    }
    return `${base}-${index}`;
}

function stringifyCommaList(items: readonly string[]): string {
    return items
        .map((item) => item.trim())
        .filter(Boolean)
        .join(", ");
}

function skillDisplayName(slug: string, catalog: SkillPack[]) {
    return catalog.find((item) => item.slug === slug)?.name ?? slug;
}

function getTemplateBySlug(templates: AgentTemplate[], slug: string) {
    return templates.find((item) => item.slug === slug) ?? null;
}

function getRoleIcon(role: TeamGraphRole) {
    if (role === "manager") return <ManagerIcon fontSize="small" />;
    if (role === "reviewer") return <ReviewerIcon fontSize="small" />;
    return <SpecialistIcon fontSize="small" />;
}

function getRoleColor(role: TeamGraphRole) {
    if (role === "manager") return "primary";
    if (role === "reviewer") return "warning";
    return "info";
}

function getStatusChipColor(status: TeamGraphNodeStatus) {
    if (status === "running" || status === "active") return "success";
    if (status === "blocked") return "warning";
    if (status === "queued") return "secondary";
    return "default";
}

function StringListField({
    label,
    value,
    onChange,
    helperText,
    placeholder,
    options = [],
}: StringListFieldProps) {
    return (
        <Autocomplete
            multiple
            freeSolo
            options={options}
            value={value}
            onChange={(_, nextValue) => onChange(Array.from(new Set(nextValue.map((item) => item.trim()).filter(Boolean))))}
            renderTags={(tagValue, getTagProps) =>
                tagValue.map((option, index) => {
                    const { key, ...tagProps } = getTagProps({ index });
                    return <Chip key={key} label={option} size="small" {...tagProps} />;
                })
            }
            renderInput={(params) => (
                <TextField
                    {...params}
                    label={label}
                    helperText={helperText}
                    placeholder={placeholder}
                />
            )}
        />
    );
}

function TaskFiltersField({
    value,
    onChange,
    helperText,
}: {
    value: string[];
    onChange: (nextValue: string[]) => void;
    helperText: string;
}) {
    return (
        <TextField
            label="Task filters"
            value={value.join("\n")}
            onChange={(event) => onChange(parseLooseList(event.target.value))}
            helperText={helperText}
            multiline
            minRows={4}
            fullWidth
        />
    );
}

function buildFormFromTemplate(template: AgentTemplate): typeof EMPTY_FORM {
    const taskFilters = Array.isArray(template.metadata?.task_filters)
        ? template.metadata.task_filters.filter((item): item is string => typeof item === "string")
        : [];

    return {
        name: template.name,
        slug: template.slug,
        description: template.description ?? "",
        role: template.role,
        system_prompt: template.system_prompt ?? "",
        parent_template_slug: template.parent_template_slug ?? "",
        capabilities: template.capabilities.join(", "),
        allowed_tools: template.allowed_tools.join(", "),
        skills: template.skills,
        tags: template.tags.join(", "),
        task_filters: taskFilters.join("\n"),
        model: String((template.model_policy?.model as string | undefined) || ""),
        fallback_model: String((template.model_policy?.fallback_model as string | undefined) || ""),
        escalation_path: String((template.model_policy?.escalation_path as string | undefined) || ""),
        permission: String((template.model_policy?.permissions as string | undefined) || "read-only"),
        memory_scope: String((template.memory_policy?.scope as string | undefined) || "project-only"),
        output_format: String((template.output_schema?.format as string | undefined) || "json"),
        token_budget: String((template.budget?.token_budget as number | undefined) || 8000),
        time_budget_seconds: String((template.budget?.time_budget_seconds as number | undefined) || 300),
        retry_budget: String((template.budget?.retry_budget as number | undefined) || 1),
    };
}

function buildSkillForm(skill?: SkillPack): SkillTemplateFormState {
    return {
        name: skill?.name ?? "",
        slug: skill?.slug ?? "",
        description: skill?.description ?? "",
        capabilities: skill?.capabilities ?? [],
        allowed_tools: skill?.allowed_tools ?? [],
        tags: skill?.tags ?? [],
        rules_markdown: skill?.rules_markdown ?? "",
    };
}

function buildTeamTemplateForm(template?: TeamTemplate): TeamTemplateFormState {
    return {
        name: template?.name ?? "",
        slug: template?.slug ?? "",
        description: template?.description ?? "",
        outcome: template?.outcome ?? "",
        roles: template?.roles ?? [],
        tools: template?.tools ?? [],
        autonomy: template?.autonomy ?? "custom",
        visibility: template?.visibility ?? "private",
        agent_template_slugs: template?.agent_template_slugs ?? [],
    };
}

function buildNodeDataFromAgent(
    agent: Agent,
    liveStatus: Map<string, "running" | "blocked" | "queued" | "idle">,
): TeamGraphNodeData {
    const effectiveCapabilities = agent.inheritance?.effective.capabilities ?? agent.capabilities;
    const statusMap = liveStatus.get(agent.id);
    const status: TeamGraphNodeStatus = statusMap && statusMap !== "idle"
        ? statusMap
        : agent.is_active
            ? "active"
            : "inactive";
    const taskFilters = Array.isArray(agent.metadata?.task_filters)
        ? agent.metadata.task_filters.filter((item): item is string => typeof item === "string")
        : [];

    return {
        name: agent.name,
        slug: agent.slug,
        role: (agent.role === "manager" || agent.role === "reviewer" ? agent.role : "specialist"),
        description: agent.description ?? "",
        linkedTemplateSlug: agent.parent_template_slug ?? "",
        linkedAgentId: agent.id,
        capabilities: effectiveCapabilities,
        allowedTools: agent.allowed_tools,
        tags: agent.tags,
        projectAssignments: agent.project_id ? [agent.project_id] : [],
        taskFilters,
        model: String((agent.model_policy?.model as string | undefined) || ""),
        fallbackModel: String((agent.model_policy?.fallback_model as string | undefined) || ""),
        escalationPath: String((agent.model_policy?.escalation_path as string | undefined) || ""),
        permission: String((agent.model_policy?.permissions as string | undefined) || "read-only"),
        memoryScope: String((agent.memory_policy?.scope as string | undefined) || "project-only"),
        outputFormat: String((agent.output_schema?.format as string | undefined) || "json"),
        tokenBudget: String((agent.budget?.token_budget as number | undefined) || 8000),
        timeBudgetSeconds: String((agent.budget?.time_budget_seconds as number | undefined) || agent.timeout_seconds || 300),
        retryBudget: String((agent.budget?.retry_budget as number | undefined) || agent.retry_limit || 1),
        status,
        subtitle: agent.parent_template_slug ? `template ${agent.parent_template_slug}` : agent.slug,
    };
}

function autoLayoutGraph(nodes: TeamGraphNode[]): TeamGraphNode[] {
    const grouped: Record<TeamGraphRole, TeamGraphNode[]> = {
        manager: [],
        specialist: [],
        reviewer: [],
    };
    nodes.forEach((node) => {
        grouped[node.data.role].push(node);
    });
    const rowY: Record<TeamGraphRole, number> = {
        manager: 80,
        specialist: 300,
        reviewer: 520,
    };
    const gapX = 280;
    const startX = 80;

    return nodes.map((node) => {
        const siblings = grouped[node.data.role];
        const index = siblings.findIndex((item) => item.id === node.id);
        return {
            ...node,
            position: {
                x: startX + Math.max(0, index) * gapX,
                y: rowY[node.data.role],
            },
        };
    });
}

function buildInitialTeamGraph(
    agents: Agent[],
    liveStatus: Map<string, "running" | "blocked" | "queued" | "idle">,
): { nodes: TeamGraphNode[]; edges: TeamGraphEdge[] } {
    if (agents.length === 0) {
        return { nodes: [], edges: [] };
    }

    const nodes = autoLayoutGraph(
        agents.map((agent, index) => ({
            id: agent.id,
            type: agent.role === "manager" || agent.role === "reviewer" ? agent.role : "specialist",
            position: { x: 80 + index * 220, y: 120 },
            data: buildNodeDataFromAgent(agent, liveStatus),
        })),
    );

    const byId = new Map(agents.map((agent) => [agent.id, agent]));
    const bySlug = new Map(agents.map((agent) => [agent.slug, agent]));
    const edges: TeamGraphEdge[] = [];

    agents.forEach((agent) => {
        if (agent.parent_agent_id && byId.has(agent.parent_agent_id)) {
            edges.push(createSemanticEdge(agent.parent_agent_id, agent.id, "delegates_to"));
        }
        if (agent.reviewer_agent_id && byId.has(agent.reviewer_agent_id)) {
            edges.push(createSemanticEdge(agent.reviewer_agent_id, agent.id, "reviews"));
        }
        const escalationPath = String((agent.model_policy?.escalation_path as string | undefined) || "");
        const escalationTarget = bySlug.get(escalationPath);
        if (escalationTarget) {
            edges.push(createSemanticEdge(agent.id, escalationTarget.id, "escalates_to"));
        }
    });

    if (edges.length === 0) {
        const rootManager = nodes.find((node) => node.data.role === "manager");
        if (rootManager) {
            nodes
                .filter((node) => node.id !== rootManager.id)
                .forEach((node) => {
                    edges.push(createSemanticEdge(rootManager.id, node.id, "delegates_to"));
                });
        }
    }

    return { nodes, edges };
}

function createSemanticEdge(source: string, target: string, semantic: TeamGraphEdgeSemantic): TeamGraphEdge {
    const color =
        semantic === "reviews"
            ? "#b26a00"
            : semantic === "escalates_to"
                ? "#b42318"
                : semantic === "collaborates_with"
                    ? "#667085"
                    : "#175cd3";

    return {
        id: `${semantic}-${source}-${target}-${Math.random().toString(36).slice(2, 8)}`,
        source,
        target,
        label: semantic.replaceAll("_", " "),
        type: "smoothstep",
        animated: semantic === "collaborates_with",
        markerEnd: { type: MarkerType.ArrowClosed, color },
        style: {
            stroke: color,
            strokeWidth: semantic === "reviews" ? 2.2 : 1.9,
            strokeDasharray: semantic === "collaborates_with" ? "6 4" : undefined,
        },
        data: { semantic },
    };
}

function buildValidationIssues(nodes: TeamGraphNode[], edges: TeamGraphEdge[]): TeamGraphValidationIssue[] {
    const issues: TeamGraphValidationIssue[] = [];
    const incomingByNode = new Map<string, TeamGraphEdge[]>();

    edges.forEach((edge) => {
        incomingByNode.set(edge.target, [...(incomingByNode.get(edge.target) ?? []), edge]);
        if (edge.source === edge.target) {
            issues.push({
                id: `self-loop-${edge.id}`,
                severity: "error",
                edgeId: edge.id,
                nodeId: edge.source,
                message: "Self-loops are not allowed in the team graph.",
            });
        }
    });

    const managerRoots = nodes.filter((node) => {
        if (node.data.role !== "manager") return false;
        const incoming = incomingByNode.get(node.id) ?? [];
        return !incoming.some((edge) => edge.data?.semantic === "delegates_to");
    });

    if (nodes.some((node) => node.data.role === "manager") && managerRoots.length !== 1) {
        issues.push({
            id: "manager-root-count",
            severity: "warning",
            message: `Expected one manager root, found ${managerRoots.length}.`,
        });
    }

    nodes.forEach((node) => {
        if (node.data.role === "manager") return;
        const incoming = incomingByNode.get(node.id) ?? [];
        const hasHierarchyParent = incoming.some((edge) => edge.data?.semantic !== "collaborates_with");
        if (!hasHierarchyParent) {
            issues.push({
                id: `orphan-${node.id}`,
                severity: "error",
                nodeId: node.id,
                message: `${node.data.name} has no incoming manager, reviewer, or escalation relationship.`,
            });
        }

        if (node.data.escalationPath) {
            const match = nodes.some(
                (candidate) =>
                    candidate.id === node.data.escalationPath ||
                    candidate.data.slug === node.data.escalationPath ||
                    candidate.data.name === node.data.escalationPath,
            );
            if (!match) {
                issues.push({
                    id: `invalid-escalation-${node.id}`,
                    severity: "warning",
                    nodeId: node.id,
                    message: `${node.data.name} has an escalation target that does not exist in this team graph.`,
                });
            }
        }
    });

    return issues;
}

function TeamGraphNodeCard({ data, selected }: NodeProps<TeamGraphNode>) {
    const tone = data.role === "manager" ? "#175cd3" : data.role === "reviewer" ? "#b26a00" : "#087443";
    return (
        <Paper
            elevation={0}
            sx={{
                width: 260,
                borderRadius: 4,
                border: "1px solid",
                borderColor: selected ? tone : alpha("#101828", 0.12),
                bgcolor: data.status === "inactive" ? alpha("#101828", 0.02) : "background.paper",
                boxShadow: selected ? `0 0 0 3px ${alpha(tone, 0.12)}` : "0 12px 32px rgba(16, 24, 40, 0.08)",
                transition: "all 160ms ease",
                opacity: data.status === "inactive" ? 0.8 : 1,
                "&:hover": {
                    transform: "translateY(-2px)",
                    boxShadow: "0 16px 36px rgba(16, 24, 40, 0.12)",
                },
            }}
        >
            <Handle type="target" position={Position.Top} style={{ background: tone, width: 10, height: 10 }} />
            <Stack spacing={1.2} sx={{ p: 1.75 }}>
                <Stack direction="row" justifyContent="space-between" spacing={1}>
                    <Stack direction="row" spacing={1} alignItems="center">
                        <Box
                            sx={{
                                width: 34,
                                height: 34,
                                borderRadius: 2.5,
                                display: "grid",
                                placeItems: "center",
                                bgcolor: alpha(tone, 0.1),
                                color: tone,
                            }}
                        >
                            {getRoleIcon(data.role)}
                        </Box>
                        <Box sx={{ minWidth: 0 }}>
                            <Typography variant="subtitle2" noWrap>
                                {data.name}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" noWrap>
                                {data.subtitle || data.slug || data.role}
                            </Typography>
                        </Box>
                    </Stack>
                    <Chip
                        size="small"
                        label={data.status.replaceAll("_", " ")}
                        color={getStatusChipColor(data.status)}
                        variant="outlined"
                    />
                </Stack>

                <Typography variant="body2" color="text.secondary" sx={{ minHeight: 40 }}>
                    {data.description || "No contract description yet."}
                </Typography>

                <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                    {data.capabilities.slice(0, 2).map((item) => (
                        <Chip key={`${data.slug}-${item}`} size="small" label={item} variant="outlined" />
                    ))}
                    {data.allowedTools.length > 0 ? (
                        <Chip size="small" label={`${data.allowedTools.length} tools`} color="secondary" variant="outlined" />
                    ) : null}
                    {data.projectAssignments.length > 0 ? (
                        <Chip size="small" label={`${data.projectAssignments.length} projects`} color="default" variant="outlined" />
                    ) : null}
                </Stack>
            </Stack>
            <Handle type="source" position={Position.Bottom} style={{ background: tone, width: 10, height: 10 }} />
        </Paper>
    );
}

const nodeTypes = {
    manager: TeamGraphNodeCard,
    specialist: TeamGraphNodeCard,
    reviewer: TeamGraphNodeCard,
};


function AgentEditorSection({
    title,
    description,
    children,
    defaultExpanded = true,
}: {
    title: string;
    description: string;
    children: React.ReactNode;
    defaultExpanded?: boolean;
}) {
    return (
        <Accordion defaultExpanded={defaultExpanded} disableGutters elevation={0} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 3, overflow: "hidden", "&:before": { display: "none" } }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Stack spacing={0.25}>
                    <Typography variant="subtitle2">{title}</Typography>
                    <Typography variant="body2" color="text.secondary">
                        {description}
                    </Typography>
                </Stack>
            </AccordionSummary>
            <AccordionDetails>
                <Stack spacing={2}>{children}</Stack>
            </AccordionDetails>
        </Accordion>
    );
}

function ExpandableSection({
    title,
    description,
    children,
    defaultExpanded = true,
    action,
}: {
    title: string;
    description: string;
    children: React.ReactNode;
    defaultExpanded?: boolean;
    action?: React.ReactNode;
}) {
    return (
        <SectionCard sx={{ p: 0, overflow: "hidden" }}>
            <Accordion
                defaultExpanded={defaultExpanded}
                disableGutters
                elevation={0}
                sx={{
                    boxShadow: "none",
                    bgcolor: "transparent",
                    "&:before": { display: "none" },
                }}
            >
                <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ px: 2.25, py: 0.5 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2} sx={{ width: "100%", pr: 1 }}>
                        <Stack spacing={0.25}>
                            <Typography variant="subtitle2">{title}</Typography>
                            <Typography variant="body2" color="text.secondary">
                                {description}
                            </Typography>
                        </Stack>
                        {action ? (
                            <Box onClick={(event) => event.stopPropagation()}>
                                {action}
                            </Box>
                        ) : null}
                    </Stack>
                </AccordionSummary>
                <AccordionDetails sx={{ px: 2.25, pb: 2.25, pt: 0 }}>
                    <Stack spacing={2}>{children}</Stack>
                </AccordionDetails>
            </Accordion>
        </SectionCard>
    );
}

export default function AgentLibraryPage() {
    const location = useLocation();
    const routeTab: BuilderTab = location.pathname === "/agent-hierarchy" || location.pathname === "/hierarchy-builder" || location.pathname === "/hierarchy"
        ? "hierarchy"
        : "library";
    const isCompact = useMediaQuery("(max-width:1199px)");
    const isWideHierarchyLayout = useMediaQuery("(min-width:1200px)");
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();

    const [form, setForm] = useState(EMPTY_FORM);
    const [manualTab, setManualTab] = useState<BuilderTab | null>(null);
    const [addAgentDialogOpen, setAddAgentDialogOpen] = useState(false);
    const [agentToAddId, setAgentToAddId] = useState("");
    const [agentTemplateDrawerOpen, setAgentTemplateDrawerOpen] = useState(false);
    const [editingAgentTemplateSlug, setEditingAgentTemplateSlug] = useState<string | null>(null);
    const [skillTemplateDrawerOpen, setSkillTemplateDrawerOpen] = useState(false);
    const [editingSkillSlug, setEditingSkillSlug] = useState<string | null>(null);
    const [teamTemplateDrawerOpen, setTeamTemplateDrawerOpen] = useState(false);
    const [editingTeamTemplateId, setEditingTeamTemplateId] = useState<string | null>(null);
    const [skillForm, setSkillForm] = useState<SkillTemplateFormState>(buildSkillForm());
    const [teamTemplateForm, setTeamTemplateForm] = useState<TeamTemplateFormState>(buildTeamTemplateForm());
    const [draggingItem, setDraggingItem] = useState<{ type: "skill" | "agent-template"; slug: string } | null>(null);
    const [activeDropTarget, setActiveDropTarget] = useState<{ kind: "agent-template" | "team-template"; id: string } | null>(null);
    const [edgeSemanticDraft, setEdgeSemanticDraft] = useState<TeamGraphEdgeSemantic>("delegates_to");
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
    const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
    const [savedLayout, setSavedLayout] = useState<TeamLayoutSnapshot | null>(null);
    const [showValidationPanel, setShowValidationPanel] = useState(false);
    const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<TeamGraphNode, TeamGraphEdge> | null>(null);
    const [graphDirty, setGraphDirty] = useState(false);
    const [inspectorWidth, setInspectorWidth] = useState(360);
    const [isResizingInspector, setIsResizingInspector] = useState(false);

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

    const { data: agents = [] } = useQuery({
        queryKey: ["orchestration", "agents"],
        queryFn: () => listAgents(),
    });
    const { data: runs = [] } = useQuery({
        queryKey: ["orchestration", "runs"],
        queryFn: () => listRuns(),
        refetchInterval: 5000,
    });
    const { data: templates = [] } = useQuery({
        queryKey: ["orchestration", "agent-templates"],
        queryFn: listAgentTemplates,
    });
    const { data: skills = [] } = useQuery({
        queryKey: ["orchestration", "skill-catalog"],
        queryFn: listSkillCatalog,
    });
    const { data: teamTemplates = [] } = useQuery({
        queryKey: ["orchestration", "team-templates"],
        queryFn: listTeamTemplates,
    });
    const { data: orchestrationProjects = [] } = useQuery({
        queryKey: ["orchestration", "projects"],
        queryFn: listOrchestrationProjects,
    });

    const activeTab = manualTab ?? routeTab;

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

    const initialGraph = useMemo(() => buildInitialTeamGraph(agents, agentLiveStatus), [agents, agentLiveStatus]);
    const [nodes, setNodes, onNodesChange] = useNodesState<TeamGraphNode>(initialGraph.nodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState<TeamGraphEdge>(initialGraph.edges);

    useEffect(() => {
        if (!graphDirty) {
            setNodes(initialGraph.nodes);
            setEdges(initialGraph.edges);
        }
    }, [graphDirty, initialGraph, setEdges, setNodes]);

    const validationIssues = useMemo(() => buildValidationIssues(nodes, edges), [nodes, edges]);
    const selectedNode = useMemo(() => nodes.find((node) => node.id === selectedNodeId) ?? null, [nodes, selectedNodeId]);
    const selectedEdge = useMemo(() => edges.find((edge) => edge.id === selectedEdgeId) ?? null, [edges, selectedEdgeId]);

    const stringOptions = useMemo(() => ({
        capabilities: Array.from(new Set([...templates.flatMap((item) => item.capabilities), ...skills.flatMap((item) => item.capabilities), ...agents.flatMap((item) => item.capabilities)])).sort(),
        tools: Array.from(new Set([...templates.flatMap((item) => item.allowed_tools), ...skills.flatMap((item) => item.allowed_tools), ...agents.flatMap((item) => item.allowed_tools)])).sort(),
        tags: Array.from(new Set([...templates.flatMap((item) => item.tags), ...skills.flatMap((item) => item.tags), ...agents.flatMap((item) => item.tags)])).sort(),
        projects: orchestrationProjects.map((project) => project.name),
    }), [agents, orchestrationProjects, skills, templates]);

    const createAgentTemplateMutation = useMutation({
        mutationFn: createAgentTemplate,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agent-templates"] });
            showToast({ message: "Agent template created.", severity: "success" });
        },
    });

    const updateAgentTemplateMutation = useMutation({
        mutationFn: ({ slug, payload }: { slug: string; payload: Partial<Omit<AgentTemplate, "id">> }) => updateAgentTemplate(slug, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agent-templates"] });
            showToast({ message: "Agent template updated.", severity: "success" });
        },
    });

    const deleteAgentTemplateMutation = useMutation({
        mutationFn: deleteAgentTemplate,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agent-templates"] });
            showToast({ message: "Agent template removed.", severity: "success" });
        },
        onError: (err) => {
            showToast({ message: err instanceof Error ? err.message : "Template removal failed.", severity: "error" });
        },
    });

    const createSkillMutation = useMutation({
        mutationFn: createSkillPack,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "skill-catalog"] });
            showToast({ message: "Skill template created.", severity: "success" });
        },
    });
    const updateSkillMutation = useMutation({
        mutationFn: ({ slug, payload }: { slug: string; payload: Partial<Omit<SkillPack, "id" | "slug">> }) => updateSkillPack(slug, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "skill-catalog"] });
            showToast({ message: "Skill template updated.", severity: "success" });
        },
    });
    const deleteSkillMutation = useMutation({
        mutationFn: deleteSkillPack,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "skill-catalog"] });
            showToast({ message: "Skill template removed.", severity: "success" });
        },
    });
    const createTeamTemplateMutation = useMutation({
        mutationFn: createTeamTemplate,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "team-templates"] });
            showToast({ message: "Team template created.", severity: "success" });
        },
    });
    const updateTeamTemplateMutation = useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: Partial<Omit<TeamTemplate, "id" | "slug">> }) => updateTeamTemplate(id, payload),
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "team-templates"] });
            showToast({ message: "Team template updated.", severity: "success" });
        },
    });
    const deleteTeamTemplateMutation = useMutation({
        mutationFn: deleteTeamTemplate,
        onSuccess: async () => {
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "team-templates"] });
            showToast({ message: "Team template removed.", severity: "success" });
        },
    });

    function openAgentTemplateDrawer(template?: AgentTemplate) {
        setEditingAgentTemplateSlug(template?.slug ?? null);
        setForm(template ? buildFormFromTemplate(template) : EMPTY_FORM);
        setAgentTemplateDrawerOpen(true);
    }

    function saveAgentTemplate() {
        const existingTemplate = editingAgentTemplateSlug
            ? templates.find((item) => item.slug === editingAgentTemplateSlug) ?? null
            : null;
        const nextSlug = existingTemplate?.slug ?? (form.slug.trim() || createUniqueSlug(form.name || "Untitled agent template", templates.map((item) => item.slug)));
        const payload: Omit<AgentTemplate, "id"> = {
            slug: nextSlug,
            name: form.name.trim() || existingTemplate?.name || "Untitled agent template",
            role: form.role,
            description: form.description.trim(),
            system_prompt: form.system_prompt.trim(),
            parent_template_slug: form.parent_template_slug.trim() || null,
            mission_markdown: existingTemplate?.mission_markdown ?? form.description.trim(),
            rules_markdown: existingTemplate?.rules_markdown ?? "",
            output_contract_markdown: existingTemplate?.output_contract_markdown ?? "",
            capabilities: parseCsv(form.capabilities),
            allowed_tools: parseCsv(form.allowed_tools),
            skills: form.skills,
            tags: parseCsv(form.tags),
            model_policy: {
                ...(existingTemplate?.model_policy ?? {}),
                model: form.model || null,
                fallback_model: form.fallback_model || null,
                escalation_path: form.escalation_path || null,
                permissions: form.permission,
            },
            budget: {
                ...(existingTemplate?.budget ?? {}),
                token_budget: Number(form.token_budget || 0),
                time_budget_seconds: Number(form.time_budget_seconds || 0),
                retry_budget: Number(form.retry_budget || 0),
            },
            memory_policy: { scope: form.memory_scope },
            output_schema: { format: form.output_format },
            metadata: {
                ...(existingTemplate?.metadata ?? {}),
                task_filters: parseLooseList(form.task_filters),
            },
        };

        if (existingTemplate) {
            updateAgentTemplateMutation.mutate({ slug: existingTemplate.slug, payload });
        } else {
            createAgentTemplateMutation.mutate(payload);
        }
        setAgentTemplateDrawerOpen(false);
    }

    function openSkillTemplateDrawer(skill?: SkillPack) {
        setEditingSkillSlug(skill?.slug ?? null);
        setSkillForm(buildSkillForm(skill));
        setSkillTemplateDrawerOpen(true);
    }

    function saveSkillTemplate() {
        const existingSkill = editingSkillSlug ? skills.find((item) => item.slug === editingSkillSlug) ?? null : null;
        const nextSlug = existingSkill?.slug ?? (skillForm.slug.trim() || createUniqueSlug(skillForm.name || "Untitled skill", skills.map((item) => item.slug)));
        const payload: Omit<SkillPack, "id"> = {
            slug: nextSlug,
            name: skillForm.name.trim() || existingSkill?.name || "Untitled skill",
            description: skillForm.description.trim(),
            capabilities: skillForm.capabilities,
            allowed_tools: skillForm.allowed_tools,
            tags: skillForm.tags,
            rules_markdown: skillForm.rules_markdown.trim(),
        };

        if (existingSkill) {
            updateSkillMutation.mutate({
                slug: existingSkill.slug,
                payload: {
                    name: payload.name,
                    description: payload.description,
                    capabilities: payload.capabilities,
                    allowed_tools: payload.allowed_tools,
                    tags: payload.tags,
                    rules_markdown: payload.rules_markdown,
                },
            });
        } else {
            createSkillMutation.mutate(payload);
        }
        setSkillTemplateDrawerOpen(false);
    }

    function openTeamTemplateDrawer(template?: TeamTemplate) {
        setEditingTeamTemplateId(template?.id ?? null);
        setTeamTemplateForm(buildTeamTemplateForm(template));
        setTeamTemplateDrawerOpen(true);
    }

    function saveTeamTemplate() {
        const existingTemplate = editingTeamTemplateId
            ? teamTemplates.find((item) => item.id === editingTeamTemplateId) ?? null
            : null;
        const nextSlug = existingTemplate?.slug ?? (teamTemplateForm.slug.trim() || createUniqueSlug(teamTemplateForm.name || "Untitled team template", teamTemplates.map((item) => item.slug)));
        const payload: Omit<TeamTemplate, "id"> = {
            slug: nextSlug,
            name: teamTemplateForm.name.trim() || existingTemplate?.name || "Untitled team template",
            description: teamTemplateForm.description.trim(),
            outcome: teamTemplateForm.outcome.trim(),
            roles: teamTemplateForm.roles,
            tools: teamTemplateForm.tools,
            autonomy: teamTemplateForm.autonomy.trim() || "custom",
            visibility: teamTemplateForm.visibility.trim() || "private",
            agent_template_slugs: teamTemplateForm.agent_template_slugs,
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
        updateAgentTemplateMutation.mutate({
            slug: templateSlug,
            payload: { skills: [...template.skills, skillSlug] },
        });
    }

    function removeSkillFromAgentTemplate(templateSlug: string, skillSlug: string) {
        const template = templates.find((item) => item.slug === templateSlug);
        if (!template) {
            return;
        }
        updateAgentTemplateMutation.mutate({
            slug: templateSlug,
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

    function addAgentNode(agentId: string) {
        const agent = agents.find((item) => item.id === agentId);
        if (!agent) {
            return;
        }
        const role = agent.role === "manager" || agent.role === "reviewer" ? agent.role : "specialist";
        const count = nodes.filter((node) => node.data.role === role).length + 1;
        const nextNode: TeamGraphNode = {
            id: `${agent.id}-team-node-${Date.now()}`,
            type: role,
            position: { x: 120 + count * 40, y: role === "manager" ? 80 : role === "reviewer" ? 520 : 300 },
            data: buildNodeDataFromAgent(agent, agentLiveStatus),
        };
        setNodes((current) => [...current, nextNode]);
        setGraphDirty(true);
        setSelectedNodeId(nextNode.id);
        setSelectedEdgeId(null);
        setAddAgentDialogOpen(false);
        setAgentToAddId("");
        showToast({ message: `${agent.name} added to team graph.`, severity: "success" });
        fitCanvas();
    }

    function updateNodeData(nodeId: string, patch: Partial<TeamGraphNodeData>) {
        setNodes((current) =>
            current.map((node) =>
                node.id === nodeId
                    ? {
                        ...node,
                        type: patch.role ?? node.type,
                        data: { ...node.data, ...patch, subtitle: patch.linkedTemplateSlug ? `template ${patch.linkedTemplateSlug}` : node.data.subtitle },
                    }
                    : node,
            ),
        );
        setGraphDirty(true);
    }

    function deleteNode(nodeId: string) {
        setNodes((current) => current.filter((node) => node.id !== nodeId));
        setEdges((current) => current.filter((edge) => edge.source !== nodeId && edge.target !== nodeId));
        if (selectedNodeId === nodeId) {
            setSelectedNodeId(null);
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
        setGraphDirty(false);
        showToast({ message: "Team layout reset to agent-derived defaults.", severity: "success" });
        fitCanvas();
    }

    function saveLayout() {
        const snapshot: TeamLayoutSnapshot = {
            savedAt: new Date().toISOString(),
            nodes,
            edges,
            persistence: "local-only",
        };
        setSavedLayout(snapshot);
        setGraphDirty(true);
        // TODO: persist layout once backend team graph storage exists.
        showToast({ message: "Team layout saved locally. Backend persistence is TODO.", severity: "success" });
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

    function hydrateSelectedNodeFromAgent(agentId: string) {
        const agent = agents.find((item) => item.id === agentId);
        if (!agent || !selectedNodeId) return;
        updateNodeData(selectedNodeId, buildNodeDataFromAgent(agent, agentLiveStatus));
    }

    const inspectorContent = selectedNode ? (
        <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                <Box>
                    <Typography variant="h6">{selectedNode.data.name}</Typography>
                    <Typography variant="body2" color="text.secondary">
                        Configure role contract, routing, runtime, and memory policy.
                    </Typography>
                </Box>
                {isCompact ? (
                    <IconButton onClick={() => setSelectedNodeId(null)}>
                        <CloseIcon fontSize="small" />
                    </IconButton>
                ) : null}
            </Stack>

            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Button size="small" variant="outlined" startIcon={<DuplicateIcon />} onClick={() => duplicateNode(selectedNode.id)}>
                    Duplicate
                </Button>
                <Button size="small" color="error" variant="outlined" startIcon={<DeleteIcon />} onClick={() => deleteNode(selectedNode.id)}>
                    Delete
                </Button>
            </Stack>

            <TextField
                label="Name"
                value={selectedNode.data.name}
                onChange={(event) => updateNodeData(selectedNode.id, { name: event.target.value })}
                fullWidth
            />
            <TextField
                label="Slug"
                value={selectedNode.data.slug}
                onChange={(event) => updateNodeData(selectedNode.id, { slug: event.target.value })}
                fullWidth
            />
            <TextField
                select
                label="Role"
                value={selectedNode.data.role}
                onChange={(event) => updateNodeData(selectedNode.id, { role: event.target.value as TeamGraphRole })}
                fullWidth
            >
                {ROLE_OPTIONS.map((role) => (
                    <MenuItem key={role} value={role}>
                        {role}
                    </MenuItem>
                ))}
            </TextField>
            <TextField
                label="Description"
                multiline
                minRows={3}
                value={selectedNode.data.description}
                onChange={(event) => updateNodeData(selectedNode.id, { description: event.target.value })}
                fullWidth
            />
            <TextField
                select
                label="Linked template"
                value={selectedNode.data.linkedTemplateSlug}
                onChange={(event) => updateNodeData(selectedNode.id, { linkedTemplateSlug: event.target.value })}
                fullWidth
            >
                <MenuItem value="">None</MenuItem>
                {templates.map((template) => (
                    <MenuItem key={template.slug} value={template.slug}>
                        {template.name}
                    </MenuItem>
                ))}
            </TextField>
            <TextField
                select
                label="Linked agent"
                value={selectedNode.data.linkedAgentId}
                onChange={(event) => {
                    const linkedAgentId = event.target.value;
                    updateNodeData(selectedNode.id, { linkedAgentId });
                    if (linkedAgentId) {
                        hydrateSelectedNodeFromAgent(linkedAgentId);
                    }
                }}
                fullWidth
            >
                <MenuItem value="">None</MenuItem>
                {agents.map((agent) => (
                    <MenuItem key={agent.id} value={agent.id}>
                        {agent.name}
                    </MenuItem>
                ))}
            </TextField>
            <StringListField
                label="Capabilities"
                value={selectedNode.data.capabilities}
                onChange={(nextValue) => updateNodeData(selectedNode.id, { capabilities: nextValue })}
                helperText="Capability chips describe owned work."
                placeholder="Type capability, press Enter"
                options={stringOptions.capabilities}
            />
            <StringListField
                label="Allowed tools"
                value={selectedNode.data.allowedTools}
                onChange={(nextValue) => updateNodeData(selectedNode.id, { allowedTools: nextValue })}
                helperText="Grant only the tools this node needs."
                options={stringOptions.tools}
            />
            <StringListField
                label="Tags"
                value={selectedNode.data.tags}
                onChange={(nextValue) => updateNodeData(selectedNode.id, { tags: nextValue })}
                helperText="Use tags for domain or routing metadata."
                options={stringOptions.tags}
            />
            <StringListField
                label="Project assignments"
                value={selectedNode.data.projectAssignments}
                onChange={(nextValue) => updateNodeData(selectedNode.id, { projectAssignments: nextValue })}
                helperText="TODO-ready local mapping until backend team layout storage exists."
                options={stringOptions.projects}
            />
            <TaskFiltersField
                value={selectedNode.data.taskFilters}
                onChange={(nextValue) => updateNodeData(selectedNode.id, { taskFilters: nextValue })}
                helperText="One routing condition per line."
            />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField
                    label="Primary model"
                    value={selectedNode.data.model}
                    onChange={(event) => updateNodeData(selectedNode.id, { model: event.target.value })}
                    fullWidth
                />
                <TextField
                    label="Fallback model"
                    value={selectedNode.data.fallbackModel}
                    onChange={(event) => updateNodeData(selectedNode.id, { fallbackModel: event.target.value })}
                    fullWidth
                />
            </Stack>
            <TextField
                label="Escalation path"
                value={selectedNode.data.escalationPath}
                onChange={(event) => updateNodeData(selectedNode.id, { escalationPath: event.target.value })}
                helperText="Target node id, slug, or name."
                fullWidth
            />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField
                    select
                    label="Permission"
                    value={selectedNode.data.permission}
                    onChange={(event) => updateNodeData(selectedNode.id, { permission: event.target.value })}
                    fullWidth
                >
                    {PERMISSION_OPTIONS.map((item) => (
                        <MenuItem key={item} value={item}>
                            {item}
                        </MenuItem>
                    ))}
                </TextField>
                <TextField
                    select
                    label="Memory scope"
                    value={selectedNode.data.memoryScope}
                    onChange={(event) => updateNodeData(selectedNode.id, { memoryScope: event.target.value })}
                    fullWidth
                >
                    {MEMORY_SCOPE_OPTIONS.map((item) => (
                        <MenuItem key={item} value={item}>
                            {item}
                        </MenuItem>
                    ))}
                </TextField>
            </Stack>
            <TextField
                select
                label="Output format"
                value={selectedNode.data.outputFormat}
                onChange={(event) => updateNodeData(selectedNode.id, { outputFormat: event.target.value })}
                fullWidth
            >
                {OUTPUT_FORMAT_OPTIONS.map((item) => (
                    <MenuItem key={item} value={item}>
                        {item}
                    </MenuItem>
                ))}
            </TextField>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                <TextField
                    label="Token budget"
                    value={selectedNode.data.tokenBudget}
                    onChange={(event) => updateNodeData(selectedNode.id, { tokenBudget: event.target.value })}
                    fullWidth
                />
                <TextField
                    label="Time budget (s)"
                    value={selectedNode.data.timeBudgetSeconds}
                    onChange={(event) => updateNodeData(selectedNode.id, { timeBudgetSeconds: event.target.value })}
                    fullWidth
                />
                <TextField
                    label="Retry budget"
                    value={selectedNode.data.retryBudget}
                    onChange={(event) => updateNodeData(selectedNode.id, { retryBudget: event.target.value })}
                    fullWidth
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
        <PageShell maxWidth="xl">
            <PageHeader
                eyebrow="Control plane"
                title="Team Builder"
                description="Production-grade orchestration builder for templates, agents, and multi-agent team graphs."
            />

            <Paper sx={{ mb: 2, borderRadius: 4, p: 1 }}>
                <Tabs value={activeTab} onChange={(_, value: BuilderTab) => setManualTab(value)} variant="scrollable" scrollButtons="auto">
                    <Tab value="hierarchy" label="Hierarchy" />
                    <Tab value="library" label="Library" />
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
                        action={<Button variant="contained" startIcon={<AddIcon />} onClick={() => openAgentTemplateDrawer()}>Add</Button>}
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
                                                <Button size="small" color="error" onClick={() => deleteAgentTemplateMutation.mutate(template.slug)}>
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
                                                <Button size="small" variant="outlined" onClick={() => openTeamTemplateDrawer(teamTemplate)}>
                                                    Edit
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
                        action={<Button variant="contained" startIcon={<AddIcon />} onClick={() => openSkillTemplateDrawer()}>Add</Button>}
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
                                        if (agents.length === 0) {
                                            setManualTab("library");
                                            return;
                                        }
                                        setAgentToAddId(agents[0]?.id ?? "");
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
                                <Button size="small" variant="outlined" startIcon={<SaveIcon />} onClick={saveLayout}>
                                    Save layout
                                </Button>
                                <Button size="small" variant="text" startIcon={<ResetIcon />} onClick={resetLayout}>
                                    Reset layout
                                </Button>
                            </Stack>
                            <Stack direction="row" spacing={1} alignItems="center">
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
                                <EmptyState
                                    icon={<GraphIcon />}
                                    title="No team graph yet"
                                    description="No agents were available to seed the graph. Add a manager manually or switch to the library to create agents first."
                                    action={
                                        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                                            <Button
                                                variant="contained"
                                                onClick={() => {
                                                    if (agents.length === 0) {
                                                        setManualTab("library");
                                                        return;
                                                    }
                                                    setAgentToAddId(agents[0]?.id ?? "");
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
                            ) : (
                                <Box
                                    sx={{
                                        height: { xs: 560, xl: 720 },
                                        borderRadius: 4,
                                        overflow: "hidden",
                                        border: "1px solid",
                                        borderColor: "divider",
                                        bgcolor: alpha("#f8fafc", 0.85),
                                    }}
                                >
                                    <ReactFlow
                                        nodes={nodes}
                                        edges={edges}
                                        nodeTypes={nodeTypes}
                                        onInit={setFlowInstance}
                                        onNodesChange={(changes) => {
                                            onNodesChange(changes);
                                            setGraphDirty(true);
                                        }}
                                        onEdgesChange={(changes) => {
                                            onEdgesChange(changes);
                                            setGraphDirty(true);
                                        }}
                                        onConnect={(connection: Connection) => {
                                            if (!connection.source || !connection.target) return;
                                            setEdges((current) => addEdge(createSemanticEdge(connection.source!, connection.target!, edgeSemanticDraft), current));
                                            setGraphDirty(true);
                                        }}
                                        onNodeClick={(_, node) => {
                                            setSelectedNodeId(node.id);
                                            setSelectedEdgeId(null);
                                        }}
                                        onEdgeClick={(_, edge) => {
                                            setSelectedEdgeId(edge.id);
                                            setSelectedNodeId(null);
                                        }}
                                        onPaneClick={() => {
                                            setSelectedNodeId(null);
                                            setSelectedEdgeId(null);
                                        }}
                                        fitView
                                        selectionOnDrag
                                        deleteKeyCode={["Backspace", "Delete"]}
                                        onNodesDelete={(deletedNodes) => {
                                            const deletedIds = new Set(deletedNodes.map((node) => node.id));
                                            if (selectedNodeId && deletedIds.has(selectedNodeId)) {
                                                setSelectedNodeId(null);
                                            }
                                            setGraphDirty(true);
                                        }}
                                        onEdgesDelete={(deletedEdges) => {
                                            if (selectedEdgeId && deletedEdges.some((edge) => edge.id === selectedEdgeId)) {
                                                setSelectedEdgeId(null);
                                            }
                                            setGraphDirty(true);
                                        }}
                                        proOptions={{ hideAttribution: true }}
                                    >
                                        <Background color="#d0d5dd" gap={18} size={1.1} />

                                        <Controls />
                                    </ReactFlow>
                                </Box>
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
                                    borderRadius: 999,
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
                                Update reusable contract fields. Dropped skills also appear here.
                            </Typography>
                        </Box>
                        <Stack direction="row" spacing={1}>
                            <Button onClick={() => setAgentTemplateDrawerOpen(false)}>Close</Button>
                            <Button variant="contained" onClick={saveAgentTemplate}>Save</Button>
                        </Stack>
                    </Stack>
                    <Stack spacing={2}>
                        <AgentEditorSection title="Basics" description="Identity, inheritance, and prompt contract.">
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Name" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} fullWidth />
                                <TextField label="Slug" value={form.slug} onChange={(event) => setForm((current) => ({ ...current, slug: event.target.value }))} fullWidth />
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField select label="Role" value={form.role} onChange={(event) => setForm((current) => ({ ...current, role: event.target.value }))} fullWidth>
                                    {ROLE_OPTIONS.map((role) => (
                                        <MenuItem key={role} value={role}>{role}</MenuItem>
                                    ))}
                                </TextField>
                                <TextField select label="Parent template" value={form.parent_template_slug} onChange={(event) => setForm((current) => ({ ...current, parent_template_slug: event.target.value }))} fullWidth>
                                    <MenuItem value="">None</MenuItem>
                                    {templates.filter((item) => item.slug !== editingAgentTemplateSlug).map((template) => (
                                        <MenuItem key={template.slug} value={template.slug}>{template.name}</MenuItem>
                                    ))}
                                </TextField>
                            </Stack>
                            <TextField label="Description" multiline minRows={3} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} />
                            <TextField label="System prompt" multiline minRows={5} value={form.system_prompt} onChange={(event) => setForm((current) => ({ ...current, system_prompt: event.target.value }))} />
                        </AgentEditorSection>
                        <AgentEditorSection title="Skills & capabilities" description="Template skill packs, capabilities, tools, tags, and task filters.">
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
                                renderInput={(params) => <TextField {...params} label="Skills" helperText="Drop skill templates onto agent cards or edit here." />}
                            />
                            <StringListField
                                label="Capabilities"
                                value={parseCsv(form.capabilities)}
                                onChange={(nextValue) => setForm((current) => ({ ...current, capabilities: stringifyCommaList(nextValue) }))}
                                options={stringOptions.capabilities}
                            />
                            <StringListField
                                label="Allowed tools"
                                value={parseCsv(form.allowed_tools)}
                                onChange={(nextValue) => setForm((current) => ({ ...current, allowed_tools: stringifyCommaList(nextValue) }))}
                                options={stringOptions.tools}
                            />
                            <StringListField
                                label="Tags"
                                value={parseCsv(form.tags)}
                                onChange={(nextValue) => setForm((current) => ({ ...current, tags: stringifyCommaList(nextValue) }))}
                                options={stringOptions.tags}
                            />
                            <TaskFiltersField
                                value={parseLooseList(form.task_filters)}
                                onChange={(nextValue) => setForm((current) => ({ ...current, task_filters: nextValue.join(", ") }))}
                                helperText="One routing rule per line."
                            />
                        </AgentEditorSection>
                        <AgentEditorSection title="Execution" description="Model routing, permissions, memory, and output expectations.">
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Primary model" value={form.model} onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))} fullWidth />
                                <TextField label="Fallback model" value={form.fallback_model} onChange={(event) => setForm((current) => ({ ...current, fallback_model: event.target.value }))} fullWidth />
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Escalation path" value={form.escalation_path} onChange={(event) => setForm((current) => ({ ...current, escalation_path: event.target.value }))} fullWidth />
                                <TextField select label="Permission" value={form.permission} onChange={(event) => setForm((current) => ({ ...current, permission: event.target.value }))} fullWidth>
                                    {PERMISSION_OPTIONS.map((item) => (
                                        <MenuItem key={item} value={item}>{item}</MenuItem>
                                    ))}
                                </TextField>
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField select label="Memory scope" value={form.memory_scope} onChange={(event) => setForm((current) => ({ ...current, memory_scope: event.target.value }))} fullWidth>
                                    {MEMORY_SCOPE_OPTIONS.map((item) => (
                                        <MenuItem key={item} value={item}>{item}</MenuItem>
                                    ))}
                                </TextField>
                                <TextField select label="Output format" value={form.output_format} onChange={(event) => setForm((current) => ({ ...current, output_format: event.target.value }))} fullWidth>
                                    {OUTPUT_FORMAT_OPTIONS.map((item) => (
                                        <MenuItem key={item} value={item}>{item}</MenuItem>
                                    ))}
                                </TextField>
                            </Stack>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Token budget" value={form.token_budget} onChange={(event) => setForm((current) => ({ ...current, token_budget: event.target.value }))} fullWidth />
                                <TextField label="Time budget (s)" value={form.time_budget_seconds} onChange={(event) => setForm((current) => ({ ...current, time_budget_seconds: event.target.value }))} fullWidth />
                                <TextField label="Retry budget" value={form.retry_budget} onChange={(event) => setForm((current) => ({ ...current, retry_budget: event.target.value }))} fullWidth />
                            </Stack>
                        </AgentEditorSection>
                    </Stack>
                </Stack>
            </Drawer>

            <Drawer
                anchor="right"
                open={skillTemplateDrawerOpen}
                onClose={() => setSkillTemplateDrawerOpen(false)}
                PaperProps={{ sx: { width: { xs: "100vw", sm: 520 } } }}
            >
                <Stack spacing={2} sx={{ p: 3 }}>
                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
                        <Box>
                            <Typography variant="h6">{editingSkillSlug ? "Edit skill template" : "Add skill template"}</Typography>
                            <Typography variant="body2" color="text.secondary">
                                Reusable skill packs can be dropped into agent templates.
                            </Typography>
                        </Box>
                        <Stack direction="row" spacing={1}>
                            <Button onClick={() => setSkillTemplateDrawerOpen(false)}>Close</Button>
                            <Button variant="contained" onClick={saveSkillTemplate}>Save</Button>
                        </Stack>
                    </Stack>
                    <TextField label="Name" value={skillForm.name} onChange={(event) => setSkillForm((current) => ({ ...current, name: event.target.value }))} />
                    <TextField label="Slug" value={skillForm.slug} onChange={(event) => setSkillForm((current) => ({ ...current, slug: event.target.value }))} />
                    <TextField label="Description" multiline minRows={3} value={skillForm.description} onChange={(event) => setSkillForm((current) => ({ ...current, description: event.target.value }))} />
                    <StringListField label="Capabilities" value={skillForm.capabilities} onChange={(nextValue) => setSkillForm((current) => ({ ...current, capabilities: nextValue }))} options={stringOptions.capabilities} />
                    <StringListField label="Allowed tools" value={skillForm.allowed_tools} onChange={(nextValue) => setSkillForm((current) => ({ ...current, allowed_tools: nextValue }))} options={stringOptions.tools} />
                    <StringListField label="Tags" value={skillForm.tags} onChange={(nextValue) => setSkillForm((current) => ({ ...current, tags: nextValue }))} options={stringOptions.tags} />
                    <TextField label="Rules" multiline minRows={5} value={skillForm.rules_markdown} onChange={(event) => setSkillForm((current) => ({ ...current, rules_markdown: event.target.value }))} />
                </Stack>
            </Drawer>

            <Drawer
                anchor="right"
                open={teamTemplateDrawerOpen}
                onClose={() => setTeamTemplateDrawerOpen(false)}
                PaperProps={{ sx: { width: { xs: "100vw", sm: 560 } } }}
            >
                <Stack spacing={2} sx={{ p: 3 }}>
                    <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
                        <Box>
                            <Typography variant="h6">{editingTeamTemplateId ? "Edit team template" : "Add team template"}</Typography>
                            <Typography variant="body2" color="text.secondary">
                                Reusable team canvases built from agent templates.
                            </Typography>
                        </Box>
                        <Stack direction="row" spacing={1}>
                            <Button onClick={() => setTeamTemplateDrawerOpen(false)}>Close</Button>
                            <Button variant="contained" onClick={saveTeamTemplate}>Save</Button>
                        </Stack>
                    </Stack>
                    <TextField label="Name" value={teamTemplateForm.name} onChange={(event) => setTeamTemplateForm((current) => ({ ...current, name: event.target.value }))} />
                    <TextField label="Slug" value={teamTemplateForm.slug} onChange={(event) => setTeamTemplateForm((current) => ({ ...current, slug: event.target.value }))} />
                    <TextField label="Description" multiline minRows={3} value={teamTemplateForm.description} onChange={(event) => setTeamTemplateForm((current) => ({ ...current, description: event.target.value }))} />
                    <TextField label="Outcome" value={teamTemplateForm.outcome} onChange={(event) => setTeamTemplateForm((current) => ({ ...current, outcome: event.target.value }))} />
                    <StringListField label="Roles" value={teamTemplateForm.roles} onChange={(nextValue) => setTeamTemplateForm((current) => ({ ...current, roles: nextValue }))} options={[...ROLE_OPTIONS]} />
                    <StringListField label="Tools" value={teamTemplateForm.tools} onChange={(nextValue) => setTeamTemplateForm((current) => ({ ...current, tools: nextValue }))} options={stringOptions.tools} />
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
                        <TextField label="Autonomy" value={teamTemplateForm.autonomy} onChange={(event) => setTeamTemplateForm((current) => ({ ...current, autonomy: event.target.value }))} fullWidth />
                        <TextField label="Visibility" value={teamTemplateForm.visibility} onChange={(event) => setTeamTemplateForm((current) => ({ ...current, visibility: event.target.value }))} fullWidth />
                    </Stack>
                </Stack>
            </Drawer>

            <Dialog open={addAgentDialogOpen} onClose={() => setAddAgentDialogOpen(false)} maxWidth="sm" fullWidth>
                <DialogTitle>Add agent to team</DialogTitle>
                <DialogContent>
                    {agents.length === 0 ? (
                        <Alert severity="info" sx={{ mt: 1 }}>
                            No saved agents available yet. Create one in the library first.
                        </Alert>
                    ) : (
                        <TextField
                            select
                            margin="normal"
                            label="Agent"
                            value={agentToAddId}
                            onChange={(event) => setAgentToAddId(event.target.value)}
                            fullWidth
                            helperText="Adds a saved agent contract into the current team graph."
                        >
                            {agents.map((agent) => (
                                <MenuItem key={agent.id} value={agent.id}>
                                    {agent.name} • {agent.role} • {agent.slug}
                                </MenuItem>
                            ))}
                        </TextField>
                    )}
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setAddAgentDialogOpen(false)}>Cancel</Button>
                    <Button
                        variant="contained"
                        onClick={() => addAgentNode(agentToAddId)}
                        disabled={!agentToAddId || agents.length === 0}
                    >
                        Add agent
                    </Button>
                </DialogActions>
            </Dialog>

        </PageShell>
    );
}
