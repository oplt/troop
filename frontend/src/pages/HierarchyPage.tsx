import { useCallback, useEffect, useMemo, useState } from "react";
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
    Divider,
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
    createAgent,
    createAgentTemplate,
    createSkillPack,
    createTeamTemplate,
    deleteAgentTemplate,
    deleteSkillPack,
    deleteTeamTemplate,
    addProjectAgent,
    listAgents,
    listAgentTemplates,
    listOrchestrationProjects,
    listProjectAgents,
    listRuns,
    listSkillCatalog,
    listTeamTemplates,
    updateAgent,
    updateAgentTemplate,
    updateOrchestrationProject,
    updateProjectAgent,
    updateSkillPack,
    updateTeamTemplate,
} from "../api/orchestration";
import type {
    Agent,
    AgentTemplate,
    OrchestrationProject,
    ProjectAgentMembership,
    SkillPack,
    TeamTemplate,
} from "../api/orchestration";
import { useSnackbar } from "../app/snackbarContext";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { PageShell } from "../components/ui/PageShell";
import { SectionCard } from "../components/ui/SectionCard";
import { AgentTemplateImportReviewDrawer } from "../features/agentTemplateImport/AgentTemplateImportReviewDrawer";
import {
    createImportedSourceSummary,
    draftToAgentTemplateFormState,
    parseAgentTemplateMarkdown,
} from "../features/agentTemplateImport/parser";
import type { AgentTemplateImportDraft } from "../features/agentTemplateImport/types";
import { SkillTemplateImportReviewDrawer } from "../features/skillTemplateImport/SkillTemplateImportReviewDrawer";
import {
    createSkillImportedSourceSummary,
    draftToSkillTemplateFormState,
    parseSkillTemplateMarkdown,
} from "../features/skillTemplateImport/parser";
import type { SkillTemplateImportDraft } from "../features/skillTemplateImport/types";
import {
    EMPTY_AGENT_TEMPLATE_FORM,
    buildAgentTemplateFormFromTemplate,
    buildAgentTemplatePayloadFromForm,
    parseAgentTemplateCsv,
    parseAgentTemplateLooseList,
} from "../features/agentTemplates/formState";
import { useLiveSnapshotStream } from "../hooks/useLiveSnapshotStream";
import { formatDateTime } from "../utils/formatters";

const MEMORY_SCOPE_OPTIONS = ["none", "project-only", "long-term"] as const;
const OUTPUT_FORMAT_OPTIONS = ["checklist", "json", "patch_proposal", "issue_reply", "adr"] as const;
const PERMISSION_OPTIONS = ["read-only", "comment-only", "code-write", "merge-blocked"] as const;
const ROLE_OPTIONS = ["manager", "specialist", "reviewer"] as const;

const AGENT_ROLE_GUIDANCE: Record<(typeof ROLE_OPTIONS)[number], { summary: string; promptHint: string; filtersHint: string }> = {
    manager: {
        summary: "Owns planning, delegation, escalation, and final delivery quality.",
        promptHint: "Define how this manager decomposes work, routes tasks, asks for review, and decides when to escalate.",
        filtersHint: "Use routing rules for work this manager should own first: architecture, triage, roadmap, escalation.",
    },
    specialist: {
        summary: "Executes a scoped domain of work with clear tools, boundaries, and outputs.",
        promptHint: "Describe how this specialist approaches tasks, what depth it should go to, and when it must hand off.",
        filtersHint: "Use routing rules for domain ownership: frontend, backend, incidents, docs, tests, security.",
    },
    reviewer: {
        summary: "Audits work before handoff, catches regressions, and enforces approval standards.",
        promptHint: "Define review criteria, evidence required, failure conditions, and what counts as approval.",
        filtersHint: "Use routing rules for review-style work: QA, compliance, acceptance checks, release review.",
    },
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
    persistence: "local-only" | "project";
};

const TEAM_GRAPH_STORAGE_KEY = "troop:hierarchy-builder:team-graph-layout:v1";
const TEAM_GRAPH_PROJECT_STORAGE_KEY = "troop:hierarchy-builder:selected-project:v1";
const TEAM_GRAPH_AUTOSAVE_DELAY_MS = 700;
const RUNTIME_ALLOWED_TOOLS = new Set([
    "github_comment",
    "github_label_issue",
    "github_create_pr",
    "web_fetch",
    "web_search",
    "code_execute",
    "fs_read",
    "fs_write",
    "db_query",
    "repo_search",
]);

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
    canvas_layout: Record<string, unknown>;
};

function parseCsv(value: string): string[] {
    return parseAgentTemplateCsv(value);
}

function parseLooseList(value: string): string[] {
    return parseAgentTemplateLooseList(value);
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

function createUniqueNodeId(value: string, existingIds: string[]) {
    const base = slugify(value) || "team-node";
    if (!existingIds.includes(base)) {
        return base;
    }
    let index = 2;
    while (existingIds.includes(`${base}-${index}`)) {
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
        canvas_layout: template?.canvas_layout ?? {},
    };
}

function uniqueStrings(items: string[]): string[] {
    return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
}

function buildNodeDataFromTemplate(template: AgentTemplate): TeamGraphNodeData {
    return {
        name: template.name,
        slug: template.slug,
        role: (template.role === "manager" || template.role === "reviewer" ? template.role : "specialist"),
        description: template.description ?? "",
        linkedTemplateSlug: template.slug,
        linkedAgentId: "",
        capabilities: template.capabilities,
        allowedTools: template.allowed_tools,
        tags: template.tags,
        projectAssignments: [],
        taskFilters: Array.isArray(template.metadata?.task_filters)
            ? template.metadata.task_filters.filter((item): item is string => typeof item === "string")
            : [],
        model: String((template.model_policy?.model as string | undefined) || ""),
        fallbackModel: String((template.model_policy?.fallback_model as string | undefined) || ""),
        escalationPath: String((template.model_policy?.escalation_path as string | undefined) || ""),
        permission: String((template.model_policy?.permissions as string | undefined) || "read-only"),
        memoryScope: String((template.memory_policy?.scope as string | undefined) || "project-only"),
        outputFormat: String((template.output_schema?.format as string | undefined) || "json"),
        tokenBudget: String((template.budget?.token_budget as number | undefined) || 8000),
        timeBudgetSeconds: String((template.budget?.time_budget_seconds as number | undefined) || 300),
        retryBudget: String((template.budget?.retry_budget as number | undefined) || 1),
        status: "draft",
        subtitle: template.parent_template_slug ? `template ${template.parent_template_slug}` : template.slug,
    };
}

function buildTeamTemplateCanvasGraph(selectedTemplates: AgentTemplate[]): { nodes: TeamGraphNode[]; edges: TeamGraphEdge[] } {
    const nodes = autoLayoutGraph(
        selectedTemplates.map((template, index) => ({
            id: `team-template-${template.slug}`,
            type: template.role === "manager" || template.role === "reviewer" ? template.role : "specialist",
            position: { x: 120 + index * 80, y: 120 },
            data: buildNodeDataFromTemplate(template),
        })),
    );
    const rootManager = nodes.find((node) => node.data.role === "manager") ?? null;
    const edges = rootManager
        ? nodes
            .filter((node) => node.id !== rootManager.id)
            .map((node) => createSemanticEdge(rootManager.id, node.id, node.data.role === "reviewer" ? "reviews" : "delegates_to"))
        : [];
    return { nodes, edges };
}

function extractTeamTemplateCanvasLayout(nodes: TeamGraphNode[], edges: TeamGraphEdge[]): Record<string, unknown> {
    return {
        nodes: nodes.map((node) => ({
            slug: node.data.slug,
            x: node.position.x,
            y: node.position.y,
            role: node.data.role,
        })),
        edges: edges.map((edge) => ({
            source_slug: edge.source.replace("team-template-", ""),
            target_slug: edge.target.replace("team-template-", ""),
            semantic: edge.data?.semantic ?? "delegates_to",
        })),
    };
}

function applyTeamTemplateCanvasLayout(
    graph: { nodes: TeamGraphNode[]; edges: TeamGraphEdge[] },
    canvasLayout: Record<string, unknown> | null | undefined,
): { nodes: TeamGraphNode[]; edges: TeamGraphEdge[] } {
    const layoutNodes = Array.isArray(canvasLayout?.nodes) ? canvasLayout.nodes : [];
    const positionBySlug = new Map<string, { x: number; y: number }>();

    for (const item of layoutNodes) {
        if (!item || typeof item !== "object") continue;
        const slug = String((item as { slug?: unknown }).slug || "").trim();
        const x = Number((item as { x?: unknown }).x);
        const y = Number((item as { y?: unknown }).y);
        if (!slug || Number.isNaN(x) || Number.isNaN(y)) continue;
        positionBySlug.set(slug, { x, y });
    }

    const nodes = graph.nodes.map((node) => {
        const saved = positionBySlug.get(node.data.slug);
        if (!saved) return node;
        return {
            ...node,
            position: saved,
        };
    });

    const layoutEdges = Array.isArray(canvasLayout?.edges) ? canvasLayout.edges : [];
    if (layoutEdges.length === 0) {
        return { nodes, edges: graph.edges };
    }

    const bySlug = new Map(nodes.map((node) => [node.data.slug, node]));
    const edges: TeamGraphEdge[] = [];
    for (const item of layoutEdges) {
        if (!item || typeof item !== "object") continue;
        const sourceSlug = String((item as { source_slug?: unknown }).source_slug || "").trim();
        const targetSlug = String((item as { target_slug?: unknown }).target_slug || "").trim();
        const semantic = String((item as { semantic?: unknown }).semantic || "delegates_to") as TeamGraphEdgeSemantic;
        const source = bySlug.get(sourceSlug);
        const target = bySlug.get(targetSlug);
        if (!source || !target) continue;
        edges.push(createSemanticEdge(source.id, target.id, semantic));
    }

    return { nodes, edges: edges.length > 0 ? edges : graph.edges };
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
    const centerX = 360;
    const managerY = 80;
    const childRowY = 320;
    const gapX = 280;
    const managers = nodes.filter((node) => node.data.role === "manager");
    const nonManagers = nodes.filter((node) => node.data.role !== "manager");

    if (managers.length === 1 && nonManagers.length === 3) {
        const childStartX = centerX - gapX;
        return nodes.map((node) => {
            if (node.data.role === "manager") {
                return {
                    ...node,
                    position: {
                        x: centerX,
                        y: managerY,
                    },
                };
            }

            const childIndex = nonManagers.findIndex((item) => item.id === node.id);
            return {
                ...node,
                position: {
                    x: childStartX + Math.max(0, childIndex) * gapX,
                    y: childRowY,
                },
            };
        });
    }

    const grouped: Record<TeamGraphRole, TeamGraphNode[]> = {
        manager: [],
        specialist: [],
        reviewer: [],
    };
    nodes.forEach((node) => {
        grouped[node.data.role].push(node);
    });
    const rowY: Record<TeamGraphRole, number> = {
        manager: managerY,
        specialist: 300,
        reviewer: 520,
    };

    return nodes.map((node) => {
        const siblings = grouped[node.data.role];
        const index = siblings.findIndex((item) => item.id === node.id);
        const rowStartX = centerX - ((Math.max(siblings.length, 1) - 1) * gapX) / 2;
        return {
            ...node,
            position: {
                x: rowStartX + Math.max(0, index) * gapX,
                y: rowY[node.data.role],
            },
        };
    });
}

function createDefaultNodeData(
    role: TeamGraphRole,
    name: string,
    slug: string,
    description: string,
    capabilities: string[],
    model: string,
): TeamGraphNodeData {
    return {
        name,
        slug,
        role,
        description,
        linkedTemplateSlug: "",
        linkedAgentId: "",
        capabilities,
        allowedTools: [],
        tags: [],
        projectAssignments: [],
        taskFilters: [],
        model,
        fallbackModel: "",
        escalationPath: "",
        permission: "read-only",
        memoryScope: "project-only",
        outputFormat: "json",
        tokenBudget: "8000",
        timeBudgetSeconds: "300",
        retryBudget: "1",
        status: "draft",
        subtitle: slug,
    };
}

function buildDefaultTeamGraph(): { nodes: TeamGraphNode[]; edges: TeamGraphEdge[] } {
    const managerId = "default-manager";
    const children: {
        id: string;
        role: TeamGraphRole;
        name: string;
        slug: string;
        description: string;
        capabilities: string[];
        model: string;
    }[] = [
        {
            id: "default-planner",
            role: "specialist",
            name: "Planner",
            slug: "planner",
            description: "Breaks goals into ordered subtasks with clear acceptance criteria.",
            capabilities: ["planning", "decomposition"],
            model: "claude-sonnet-4-6",
        },
        {
            id: "default-builder",
            role: "specialist",
            name: "Builder",
            slug: "builder",
            description: "Implements subtasks end-to-end, writes code and tests.",
            capabilities: ["code-write", "refactor"],
            model: "claude-opus-4-7",
        },
        {
            id: "default-reviewer",
            role: "reviewer",
            name: "Reviewer",
            slug: "reviewer",
            description: "Audits output for correctness and policy compliance.",
            capabilities: ["qa", "review"],
            model: "claude-haiku-4-5-20251001",
        },
    ];

    const managerNode: TeamGraphNode = {
        id: managerId,
        type: "manager",
        position: { x: 0, y: 0 },
        data: createDefaultNodeData(
            "manager",
            "Lead Manager",
            "lead-manager",
            "Coordinates the team, routes tasks, and owns final delivery.",
            ["orchestration", "delegation"],
            "claude-opus-4-7",
        ),
    };
    const childNodes: TeamGraphNode[] = children.map((child) => ({
        id: child.id,
        type: child.role,
        position: { x: 0, y: 0 },
        data: createDefaultNodeData(child.role, child.name, child.slug, child.description, child.capabilities, child.model),
    }));
    const nodes = autoLayoutGraph([managerNode, ...childNodes]);
    const edges: TeamGraphEdge[] = children.map((child) =>
        createSemanticEdge(managerId, child.id, child.role === "reviewer" ? "reviews" : "delegates_to"),
    );
    return { nodes, edges };
}

const DEFAULT_TEAM_GRAPH = buildDefaultTeamGraph();

function cloneNodeData(data: TeamGraphNodeData): TeamGraphNodeData {
    return {
        ...data,
        capabilities: [...data.capabilities],
        allowedTools: [...data.allowedTools],
        tags: [...data.tags],
        projectAssignments: [...data.projectAssignments],
        taskFilters: [...data.taskFilters],
    };
}

function buildNodeSubtitle(data: Pick<TeamGraphNodeData, "linkedTemplateSlug" | "linkedAgentId" | "slug">) {
    if (data.linkedTemplateSlug) {
        return `template ${data.linkedTemplateSlug}`;
    }
    if (data.linkedAgentId) {
        return data.slug;
    }
    return "local draft";
}

function ensureMinimumHierarchy(
    graph: { nodes: TeamGraphNode[]; edges: TeamGraphEdge[] },
): { nodes: TeamGraphNode[]; edges: TeamGraphEdge[] } {
    const nodes = graph.nodes.map((node) => ({ ...node, data: cloneNodeData(node.data) }));
    const edges = [...graph.edges];
    const existingIds = new Set(nodes.map((node) => node.id));
    const existingSlugs = new Set(nodes.map((node) => node.data.slug));
    const existingNames = new Set(nodes.map((node) => node.data.name));
    const defaultManager = DEFAULT_TEAM_GRAPH.nodes.find((node) => node.data.role === "manager")!;
    const defaultWorkers = DEFAULT_TEAM_GRAPH.nodes.filter((node) => node.data.role !== "manager");

    function nextNodeId(baseId: string) {
        let nextId = baseId;
        let index = 2;
        while (existingIds.has(nextId)) {
            nextId = `${baseId}-${index}`;
            index += 1;
        }
        existingIds.add(nextId);
        return nextId;
    }

    function nextName(baseName: string) {
        if (!existingNames.has(baseName)) {
            existingNames.add(baseName);
            return baseName;
        }
        let index = 2;
        let nextNameValue = `${baseName} ${index}`;
        while (existingNames.has(nextNameValue)) {
            index += 1;
            nextNameValue = `${baseName} ${index}`;
        }
        existingNames.add(nextNameValue);
        return nextNameValue;
    }

    function nextSlug(baseSlug: string) {
        if (!existingSlugs.has(baseSlug)) {
            existingSlugs.add(baseSlug);
            return baseSlug;
        }
        let index = 2;
        let nextSlugValue = `${baseSlug}-${index}`;
        while (existingSlugs.has(nextSlugValue)) {
            index += 1;
            nextSlugValue = `${baseSlug}-${index}`;
        }
        existingSlugs.add(nextSlugValue);
        return nextSlugValue;
    }

    let rootManager = nodes.find((node) => node.data.role === "manager") ?? null;
    if (!rootManager) {
        rootManager = {
            ...defaultManager,
            id: nextNodeId(defaultManager.id),
            data: {
                ...cloneNodeData(defaultManager.data),
                name: nextName(defaultManager.data.name),
                slug: nextSlug(defaultManager.data.slug),
            },
        };
        rootManager.data.subtitle = buildNodeSubtitle(rootManager.data);
        nodes.push(rootManager);
    }

    let subAgentCount = nodes.filter((node) => node.data.role !== "manager").length;
    let workerIndex = 0;
    while (subAgentCount < 3) {
        const templateNode = defaultWorkers[workerIndex % defaultWorkers.length];
        const nextNode: TeamGraphNode = {
            ...templateNode,
            id: nextNodeId(templateNode.id),
            data: {
                ...cloneNodeData(templateNode.data),
                name: nextName(templateNode.data.name),
                slug: nextSlug(templateNode.data.slug),
            },
        };
        nextNode.data.subtitle = buildNodeSubtitle(nextNode.data);
        nodes.push(nextNode);
        edges.push(
            createSemanticEdge(
                rootManager.id,
                nextNode.id,
                nextNode.data.role === "reviewer" ? "reviews" : "delegates_to",
            ),
        );
        subAgentCount += 1;
        workerIndex += 1;
    }

    return { nodes: autoLayoutGraph(nodes), edges };
}

function buildInitialTeamGraph(
    agents: Agent[],
    liveStatus: Map<string, "running" | "blocked" | "queued" | "idle">,
): { nodes: TeamGraphNode[]; edges: TeamGraphEdge[] } {
    if (agents.length === 0) {
        return ensureMinimumHierarchy(DEFAULT_TEAM_GRAPH);
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

    return ensureMinimumHierarchy({ nodes, edges });
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

function graphSignature(nodes: TeamGraphNode[], edges: TeamGraphEdge[]): string {
    return JSON.stringify({
        nodes: nodes.map((node) => ({
            id: node.id,
            type: node.type,
            position: node.position,
            data: node.data,
        })),
        edges: edges.map((edge) => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
            data: edge.data,
            label: edge.label,
        })),
    });
}

function readSavedTeamLayoutSnapshot(): TeamLayoutSnapshot | null {
    if (typeof window === "undefined") {
        return null;
    }
    try {
        const raw = window.localStorage.getItem(TEAM_GRAPH_STORAGE_KEY);
        if (!raw) {
            return null;
        }
        const parsed = JSON.parse(raw) as TeamLayoutSnapshot;
        if (!parsed || !Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges) || typeof parsed.savedAt !== "string") {
            return null;
        }
        return {
            savedAt: parsed.savedAt,
            nodes: parsed.nodes,
            edges: parsed.edges,
            persistence: "local-only",
        };
    } catch {
        return null;
    }
}

function readSelectedHierarchyProjectId(): string {
    if (typeof window === "undefined") {
        return "";
    }
    return window.localStorage.getItem(TEAM_GRAPH_PROJECT_STORAGE_KEY) ?? "";
}

function persistSelectedHierarchyProjectId(projectId: string) {
    if (typeof window === "undefined") {
        return;
    }
    if (!projectId) {
        window.localStorage.removeItem(TEAM_GRAPH_PROJECT_STORAGE_KEY);
        return;
    }
    window.localStorage.setItem(TEAM_GRAPH_PROJECT_STORAGE_KEY, projectId);
}

function readProjectTeamLayoutSnapshot(project: OrchestrationProject | null | undefined): TeamLayoutSnapshot | null {
    const execution = ((project?.settings?.execution as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    const rawLayout = execution.team_graph_layout as Record<string, unknown> | undefined;
    if (!rawLayout) {
        return null;
    }
    const nodes = rawLayout.nodes;
    const edges = rawLayout.edges;
    const savedAt = rawLayout.savedAt;
    if (!Array.isArray(nodes) || !Array.isArray(edges) || typeof savedAt !== "string") {
        return null;
    }
    return {
        savedAt,
        nodes: nodes as TeamGraphNode[],
        edges: edges as TeamGraphEdge[],
        persistence: "project",
    };
}

function parsePositiveInteger(value: string, fallback: number): number {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function findManagerRootNode(nodes: TeamGraphNode[], edges: TeamGraphEdge[]): TeamGraphNode | null {
    const managers = nodes.filter((node) => node.data.role === "manager");
    if (managers.length === 0) {
        return null;
    }
    const delegatedTargets = new Set(
        edges.filter((edge) => edge.data?.semantic === "delegates_to").map((edge) => edge.target),
    );
    return managers.find((node) => !delegatedTargets.has(node.id)) ?? managers[0] ?? null;
}

function sanitizeRuntimeTools(tools: string[]): string[] {
    return uniqueStrings(tools).filter((tool) => RUNTIME_ALLOWED_TOOLS.has(tool));
}

function persistTeamLayoutSnapshot(snapshot: TeamLayoutSnapshot | null) {
    if (typeof window === "undefined") {
        return;
    }
    if (!snapshot) {
        window.localStorage.removeItem(TEAM_GRAPH_STORAGE_KEY);
        return;
    }
    window.localStorage.setItem(TEAM_GRAPH_STORAGE_KEY, JSON.stringify(snapshot));
}

function TeamGraphNodeCard({ data, selected }: NodeProps<TeamGraphNode>) {
    const tone = data.role === "manager" ? "#175cd3" : data.role === "reviewer" ? "#b26a00" : "#087443";
    const statusDotColor =
        data.status === "running" || data.status === "active"
            ? "#12b76a"
            : data.status === "blocked"
                ? "#f79009"
                : data.status === "queued"
                    ? "#667085"
                    : data.status === "draft"
                        ? "#9e77ed"
                        : "#d0d5dd";
    const isPulsing = data.status === "running";
    const hiddenCaps = Math.max(0, data.capabilities.length - 2);

    return (
        <Paper
            elevation={0}
            sx={{
                width: 284,
                borderRadius: 3,
                border: "1px solid",
                borderColor: selected ? tone : alpha("#101828", 0.1),
                bgcolor: data.status === "inactive" ? alpha("#101828", 0.02) : "background.paper",
                boxShadow: selected
                    ? `0 0 0 3px ${alpha(tone, 0.18)}, 0 14px 32px rgba(16,24,40,0.14)`
                    : "0 10px 28px rgba(16,24,40,0.08)",
                transition: "all 160ms ease",
                opacity: data.status === "inactive" ? 0.75 : 1,
                overflow: "hidden",
                position: "relative",
                "&:hover": {
                    transform: "translateY(-2px)",
                    boxShadow: "0 18px 38px rgba(16,24,40,0.14)",
                },
            }}
        >
            <Handle
                type="target"
                position={Position.Top}
                style={{ background: tone, width: 10, height: 10, border: "2px solid white" }}
            />
            <Box
                sx={{
                    position: "absolute",
                    left: 0,
                    top: 0,
                    bottom: 0,
                    width: 4,
                    bgcolor: tone,
                    background: `linear-gradient(180deg, ${tone} 0%, ${alpha(tone, 0.55)} 100%)`,
                }}
            />
            <Box
                sx={{
                    px: 1.75,
                    pt: 1.5,
                    pb: 1.1,
                    background: `linear-gradient(135deg, ${alpha(tone, 0.14)} 0%, ${alpha(tone, 0)} 70%)`,
                }}
            >
                <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
                    <Stack direction="row" spacing={1.25} alignItems="center" sx={{ minWidth: 0 }}>
                        <Box
                            sx={{
                                width: 38,
                                height: 38,
                                borderRadius: 2,
                                display: "grid",
                                placeItems: "center",
                                bgcolor: alpha(tone, 0.15),
                                color: tone,
                                boxShadow: `inset 0 0 0 1px ${alpha(tone, 0.22)}`,
                            }}
                        >
                            {getRoleIcon(data.role)}
                        </Box>
                        <Box sx={{ minWidth: 0 }}>
                            <Typography variant="subtitle2" fontWeight={700} noWrap>
                                {data.name || "Untitled agent"}
                            </Typography>
                            <Typography
                                variant="caption"
                                color="text.secondary"
                                sx={{ fontFamily: "IBM Plex Mono, monospace", display: "block" }}
                                noWrap
                            >
                                {data.subtitle || data.slug || data.role}
                            </Typography>
                        </Box>
                    </Stack>
                    <Stack direction="row" alignItems="center" spacing={0.6}>
                        <Box
                            sx={{
                                width: 8,
                                height: 8,
                                borderRadius: "50%",
                                bgcolor: statusDotColor,
                                boxShadow: isPulsing ? `0 0 0 3px ${alpha(statusDotColor, 0.25)}` : "none",
                                animation: isPulsing ? "troop-pulse 1.4s ease-in-out infinite" : "none",
                                "@keyframes troop-pulse": {
                                    "0%, 100%": { opacity: 1 },
                                    "50%": { opacity: 0.5 },
                                },
                            }}
                        />
                        <Typography
                            variant="caption"
                            sx={{
                                textTransform: "uppercase",
                                letterSpacing: 0.6,
                                fontWeight: 600,
                                color: "text.secondary",
                            }}
                        >
                            {data.status}
                        </Typography>
                    </Stack>
                </Stack>
            </Box>

            <Stack spacing={1} sx={{ px: 1.75, pb: 1.5, pt: 1.25 }}>
                <Typography variant="body2" color="text.secondary" sx={{ minHeight: 36, lineHeight: 1.45 }}>
                    {data.description || "No contract description yet."}
                </Typography>

                {data.model ? (
                    <Stack direction="row" spacing={0.75} alignItems="center">
                        <Typography
                            variant="caption"
                            sx={{ fontWeight: 700, color: "text.secondary", textTransform: "uppercase", letterSpacing: 0.5 }}
                        >
                            model
                        </Typography>
                        <Typography
                            variant="caption"
                            sx={{ fontFamily: "IBM Plex Mono, monospace", color: "text.primary" }}
                            noWrap
                        >
                            {data.model}
                        </Typography>
                    </Stack>
                ) : null}

                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                    <Chip
                        size="small"
                        label={data.role}
                        sx={{
                            height: 22,
                            bgcolor: alpha(tone, 0.12),
                            color: tone,
                            fontWeight: 700,
                            textTransform: "capitalize",
                            border: `1px solid ${alpha(tone, 0.25)}`,
                        }}
                    />
                    {data.capabilities.slice(0, 2).map((item) => (
                        <Chip
                            key={`${data.slug}-${item}`}
                            size="small"
                            label={item}
                            variant="outlined"
                            sx={{ height: 22 }}
                        />
                    ))}
                    {hiddenCaps > 0 ? (
                        <Chip size="small" label={`+${hiddenCaps}`} variant="outlined" sx={{ height: 22 }} />
                    ) : null}
                </Stack>

                {(data.allowedTools.length > 0 ||
                    data.projectAssignments.length > 0 ||
                    data.tags.length > 0) && (
                    <>
                        <Divider flexItem sx={{ borderStyle: "dashed", opacity: 0.6 }} />
                        <Stack
                            direction="row"
                            spacing={1.5}
                            sx={{ color: "text.secondary", fontSize: 11 }}
                            divider={<Box sx={{ width: "1px", bgcolor: alpha("#101828", 0.1) }} />}
                        >
                            {data.allowedTools.length > 0 ? (
                                <Typography variant="caption">
                                    <Box component="strong" sx={{ color: "text.primary" }}>
                                        {data.allowedTools.length}
                                    </Box>{" "}
                                    tools
                                </Typography>
                            ) : null}
                            {data.projectAssignments.length > 0 ? (
                                <Typography variant="caption">
                                    <Box component="strong" sx={{ color: "text.primary" }}>
                                        {data.projectAssignments.length}
                                    </Box>{" "}
                                    projects
                                </Typography>
                            ) : null}
                            {data.tags.length > 0 ? (
                                <Typography variant="caption">
                                    <Box component="strong" sx={{ color: "text.primary" }}>
                                        {data.tags.length}
                                    </Box>{" "}
                                    tags
                                </Typography>
                            ) : null}
                        </Stack>
                    </>
                )}
            </Stack>
            <Handle
                type="source"
                position={Position.Bottom}
                style={{ background: tone, width: 10, height: 10, border: "2px solid white" }}
            />
        </Paper>
    );
}

const nodeTypes = {
    manager: TeamGraphNodeCard,
    specialist: TeamGraphNodeCard,
    reviewer: TeamGraphNodeCard,
};


function AgentEditorSection({
    step,
    title,
    description,
    children,
    defaultExpanded = true,
}: {
    step?: string;
    title: string;
    description: string;
    children: React.ReactNode;
    defaultExpanded?: boolean;
}) {
    return (
        <Accordion defaultExpanded={defaultExpanded} disableGutters elevation={0} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 3, overflow: "hidden", "&:before": { display: "none" } }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Stack spacing={0.25}>
                    {step ? (
                        <Typography variant="caption" sx={{ textTransform: "uppercase", letterSpacing: 1, color: "text.secondary", fontWeight: 700 }}>
                            {step}
                        </Typography>
                    ) : null}
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
    const [inspectorWidth, setInspectorWidth] = useState(360);
    const [isResizingInspector, setIsResizingInspector] = useState(false);
    const [teamNodeDrawerOpen, setTeamNodeDrawerOpen] = useState(false);
    const [editingTeamNodeId, setEditingTeamNodeId] = useState<string | null>(null);
    const [teamNodeDraft, setTeamNodeDraft] = useState<TeamGraphNodeData | null>(null);

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
    const { data: hierarchyAgents = [] } = useQuery({
        queryKey: ["orchestration", "agents", effectiveHierarchyProjectId || "global"],
        queryFn: () => listAgents(effectiveHierarchyProjectId || undefined),
    });

    useLiveSnapshotStream("/orchestration/hierarchy/stream", {
        onSnapshot: () => {
            void queryClient.invalidateQueries({ queryKey: ["orchestration", "agents"] });
            void queryClient.invalidateQueries({ queryKey: ["orchestration", "agents", effectiveHierarchyProjectId || "global"] });
            void queryClient.invalidateQueries({ queryKey: ["orchestration", "runs"] });
            void queryClient.invalidateQueries({ queryKey: ["orchestration", "projects"] });
        },
    });

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
    const [nodes, setNodes, onNodesChange] = useNodesState<TeamGraphNode>(initialGraph.nodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState<TeamGraphEdge>(initialGraph.edges);
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

    const validationIssues = useMemo(() => buildValidationIssues(nodes, edges), [nodes, edges]);
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

            for (const node of sortedNodes) {
                const existingAgent = node.data.linkedAgentId
                    ? existingGraphAgents.get(node.data.linkedAgentId) ?? agents.find((agent) => agent.id === node.data.linkedAgentId) ?? null
                    : null;
                const resolvedTemplateSlug = node.data.linkedTemplateSlug && templateSlugSet.has(node.data.linkedTemplateSlug)
                    ? node.data.linkedTemplateSlug
                    : null;
                const modelPolicy = {
                    ...(existingAgent?.model_policy ?? {}),
                    escalation_path: node.data.escalationPath || null,
                    permissions: node.data.permission || "read-only",
                };
                const memoryPolicy = {
                    ...(existingAgent?.memory_policy ?? {}),
                    scope: node.data.memoryScope || "project-only",
                };
                const outputSchema = {
                    ...(existingAgent?.output_schema ?? {}),
                    format: node.data.outputFormat || "json",
                };
                const budget = {
                    ...(existingAgent?.budget ?? {}),
                    token_budget: parsePositiveInteger(node.data.tokenBudget, 8000),
                    time_budget_seconds: parsePositiveInteger(node.data.timeBudgetSeconds, 300),
                    retry_budget: parsePositiveInteger(node.data.retryBudget, 1),
                };
                const metadata = {
                    ...(existingAgent?.metadata ?? {}),
                    task_filters: node.data.taskFilters,
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
                        name: node.data.name.trim() || existingAgent.name,
                        slug: node.data.slug.trim() || existingAgent.slug,
                        description: node.data.description.trim(),
                        role: node.data.role,
                        parent_template_slug: resolvedTemplateSlug || existingAgent.parent_template_slug || null,
                        capabilities: node.data.capabilities,
                        allowed_tools: sanitizeRuntimeTools(node.data.allowedTools),
                        tags: node.data.tags,
                        model_policy: modelPolicy,
                        memory_policy: memoryPolicy,
                        output_schema: outputSchema,
                        budget,
                        timeout_seconds: parsePositiveInteger(node.data.timeBudgetSeconds, existingAgent.timeout_seconds || 300),
                        retry_limit: parsePositiveInteger(node.data.retryBudget, existingAgent.retry_limit || 1),
                        task_filters: node.data.taskFilters,
                        metadata,
                    });
                } else {
                    const preferredSlug = node.data.slug.trim() || slugify(node.data.name) || "agent";
                    const nextSlug = reservedSlugs.has(preferredSlug)
                        ? createUniqueSlug(preferredSlug, Array.from(reservedSlugs))
                        : preferredSlug;
                    reservedSlugs.add(nextSlug);
                    savedAgent = await createAgent({
                        project_id: effectiveHierarchyProjectId,
                        parent_template_slug: resolvedTemplateSlug,
                        name: node.data.name.trim() || "Untitled agent",
                        slug: nextSlug,
                        description: node.data.description.trim(),
                        role: node.data.role,
                        capabilities: node.data.capabilities,
                        allowed_tools: sanitizeRuntimeTools(node.data.allowedTools),
                        tags: node.data.tags,
                        model_policy: modelPolicy,
                        memory_policy: memoryPolicy,
                        output_schema: outputSchema,
                        budget,
                        timeout_seconds: parsePositiveInteger(node.data.timeBudgetSeconds, 300),
                        retry_limit: parsePositiveInteger(node.data.retryBudget, 1),
                        task_filters: node.data.taskFilters,
                        metadata,
                    });
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
                        escalation_path: escalationSlug,
                        permissions: node.data.permission || "read-only",
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

            return snapshot;
        },
        onSuccess: async (snapshot) => {
            setNodes(snapshot.nodes);
            setEdges(snapshot.edges);
            setSavedLayout(snapshot);
            persistTeamLayoutSnapshot(snapshot);
            setGraphDirty(false);
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agents"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "agents", effectiveHierarchyProjectId || "global"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "projects"] });
            await queryClient.invalidateQueries({ queryKey: ["orchestration", "github", "issues"] });
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
            updateAgentTemplateMutation.mutate({ slug: existingTemplate.slug, payload });
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
        setSkillTemplateImportBanner(null);
        setSkillTemplateDrawerOpen(false);
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

    function createDraftNode(role: TeamGraphRole = "specialist") {
        const count = nodes.filter((node) => node.data.role === role).length + 1;
        const nextNode: TeamGraphNode = {
            id: createUniqueNodeId(`draft-${role}`, nodes.map((node) => node.id)),
            type: role,
            position: { x: 120 + count * 40, y: role === "manager" ? 80 : role === "reviewer" ? 520 : 300 },
            data: {
                ...createDefaultNodeData(
                    role,
                    role === "manager" ? "Manager" : role === "reviewer" ? "Reviewer" : "Specialist",
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
        const role = agent.role === "manager" || agent.role === "reviewer" ? agent.role : "specialist";
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

    function addAgentTemplateNode(templateSlug: string) {
        const template = templates.find((item) => item.slug === templateSlug);
        if (!template) {
            return;
        }
        const role = template.role === "manager" || template.role === "reviewer" ? template.role : "specialist";
        const nextNode: TeamGraphNode = {
            id: createUniqueNodeId(`template-${template.slug}`, nodes.map((node) => node.id)),
            type: role,
            position: computeDefaultNodePosition(role, nodes),
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
        const existingIds = new Set(nodes.map((node) => node.id));
        const resolveRole = (template: AgentTemplate): TeamGraphRole =>
            template.role === "manager" || template.role === "reviewer" ? template.role : "specialist";
        const newNodes: TeamGraphNode[] = selected.map((template) => {
            const role = resolveRole(template);
            const nextId = createUniqueNodeId(`${teamTemplate.slug}-${template.slug}`, Array.from(existingIds));
            existingIds.add(nextId);
            return {
                id: nextId,
                type: role,
                position: { x: 0, y: 0 },
                data: buildNodeDataFromTemplate(template),
            } as TeamGraphNode;
        });
        const templateManager = newNodes.find((node) => node.data.role === "manager");
        const existingManager = !templateManager ? nodes.find((node) => node.data.role === "manager") ?? null : null;
        const managerNode = templateManager ?? existingManager;
        if (templateManager) {
            templateManager.position = computeDefaultNodePosition("manager", nodes);
        }
        const combined = [...nodes, ...newNodes];
        const newChildIds = new Set(newNodes.filter((node) => node.id !== templateManager?.id).map((node) => node.id));
        const reflowed = templateManager
            ? reflowChildRows(combined, { anchorManagerId: templateManager.id, childIds: newChildIds })
            : reflowChildRows(combined);
        const newEdges: TeamGraphEdge[] = [];
        if (managerNode) {
            for (const child of newNodes) {
                if (child.id === managerNode.id) continue;
                const semantic = child.data.role === "reviewer" ? "reviews" : "delegates_to";
                newEdges.push(createSemanticEdge(managerNode.id, child.id, semantic));
            }
        }
        setNodes(reflowed);
        if (newEdges.length > 0) {
            setEdges((current) => [...current, ...newEdges]);
        }
        setGraphDirty(true);
        setManualTab("hierarchy");
        showToast({ message: `Team "${teamTemplate.name}" inserted into graph.`, severity: "success" });
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

    function saveTeamNode() {
        if (!editingTeamNodeId || !teamNodeDraft) {
            return;
        }
        updateNodeData(editingTeamNodeId, {
            ...teamNodeDraft,
            subtitle: buildNodeSubtitle(teamNodeDraft),
        });
        closeTeamNodeDrawer();
        showToast({ message: "Team graph agent updated.", severity: "success" });
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
                <TextField label="Primary model" value={selectedNode.data.model} fullWidth InputProps={{ readOnly: true }} />
                <TextField label="Fallback model" value={selectedNode.data.fallbackModel} fullWidth InputProps={{ readOnly: true }} />
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
                                <Box
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
                                    sx={{
                                        height: { xs: 560, xl: 720 },
                                        borderRadius: 4,
                                        overflow: "hidden",
                                        border: "1px solid",
                                        borderColor: draggingItem?.type === "agent-template" ? "primary.main" : "divider",
                                        bgcolor: alpha("#f8fafc", 0.85),
                                    }}
                                >
                                    <ReactFlow
                                        nodes={nodes}
                                        edges={edges}
                                        nodeTypes={nodeTypes}
                                        onInit={setFlowInstance}
                                        onNodesChange={handleFlowNodesChange}
                                        onEdgesChange={handleFlowEdgesChange}
                                        onConnect={handleFlowConnect}
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
                                            if (editingTeamNodeId && deletedIds.has(editingTeamNodeId)) {
                                                closeTeamNodeDrawer();
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
                                                    borderRadius: 2,
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
                        <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
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
                                    <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                                        <Typography variant="caption" color="text.secondary">Role</Typography>
                                        <Typography variant="body2" sx={{ mt: 0.5 }}>{form.role}</Typography>
                                    </Paper>
                                    <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                                        <Typography variant="caption" color="text.secondary">Routing surface</Typography>
                                        <Typography variant="body2" sx={{ mt: 0.5 }}>{parseCsv(form.capabilities).length || 0} capabilities</Typography>
                                    </Paper>
                                    <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                                        <Typography variant="caption" color="text.secondary">Runtime</Typography>
                                        <Typography variant="body2" sx={{ mt: 0.5 }}>{form.model || "No primary model set"}</Typography>
                                    </Paper>
                                    <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                                        <Typography variant="caption" color="text.secondary">Output</Typography>
                                        <Typography variant="body2" sx={{ mt: 0.5 }}>{form.output_format || "json"}</Typography>
                                    </Paper>
                                </Box>
                            </Stack>
                        </Paper>
                        <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
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
                                onChange={(nextValue) => setForm((current) => ({ ...current, capabilities: stringifyCommaList(nextValue) }))}
                                helperText="Use concise verbs or domains users can route against: planning, code-review, incident-triage."
                                options={stringOptions.capabilities}
                            />
                            <StringListField
                                label="Allowed tools"
                                value={parseCsv(form.allowed_tools)}
                                onChange={(nextValue) => setForm((current) => ({ ...current, allowed_tools: stringifyCommaList(nextValue) }))}
                                helperText="Only grant tools this agent genuinely needs."
                                options={stringOptions.tools}
                            />
                            <StringListField
                                label="Tags"
                                value={parseCsv(form.tags)}
                                onChange={(nextValue) => setForm((current) => ({ ...current, tags: stringifyCommaList(nextValue) }))}
                                helperText="Use tags for domain or governance metadata, not core capability matching."
                                options={stringOptions.tags}
                            />
                            <TaskFiltersField
                                value={parseLooseList(form.task_filters)}
                                onChange={(nextValue) => setForm((current) => ({ ...current, task_filters: nextValue.join(", ") }))}
                                helperText={agentRoleGuidance.filtersHint}
                            />
                        </AgentEditorSection>
                        <AgentEditorSection step="Step 3" title="Runtime policy" description="Control how this agent runs, escalates, accesses memory, and spends budget.">
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Primary model" placeholder="gpt-5-codex" helperText="Default model for normal execution." value={form.model} onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))} fullWidth />
                                <TextField label="Fallback model" placeholder="claude-sonnet-4-6" helperText="Used when the primary model is unavailable or unsuitable." value={form.fallback_model} onChange={(event) => setForm((current) => ({ ...current, fallback_model: event.target.value }))} fullWidth />
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
                            <Button variant="contained" onClick={saveTeamNode} disabled={!teamNodeDraft}>
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
                                    onChange={(nextValue) => setTeamNodeDraft((current) => current ? { ...current, capabilities: nextValue } : current)}
                                    helperText="Capability chips describe owned work."
                                    placeholder="Type capability, press Enter"
                                    options={stringOptions.capabilities}
                                />
                                <StringListField
                                    label="Allowed tools"
                                    value={teamNodeDraft.allowedTools}
                                    onChange={(nextValue) => setTeamNodeDraft((current) => current ? { ...current, allowedTools: nextValue } : current)}
                                    helperText="Grant only tools this node needs."
                                    options={stringOptions.tools}
                                />
                                <StringListField
                                    label="Tags"
                                    value={teamNodeDraft.tags}
                                    onChange={(nextValue) => setTeamNodeDraft((current) => current ? { ...current, tags: nextValue } : current)}
                                    helperText="Use tags for domain or routing metadata."
                                    options={stringOptions.tags}
                                />
                                <StringListField
                                    label="Project assignments"
                                    value={teamNodeDraft.projectAssignments}
                                    onChange={(nextValue) => setTeamNodeDraft((current) => current ? { ...current, projectAssignments: nextValue } : current)}
                                    helperText="Local mapping until backend team layout persistence exists."
                                    options={stringOptions.projects}
                                />
                                <TaskFiltersField
                                    value={teamNodeDraft.taskFilters}
                                    onChange={(nextValue) => setTeamNodeDraft((current) => current ? { ...current, taskFilters: nextValue } : current)}
                                    helperText="One routing rule per line."
                                />
                            </AgentEditorSection>
                            <AgentEditorSection title="Execution" description="Model routing, permissions, memory, and output expectations.">
                                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                    <TextField
                                        label="Primary model"
                                        value={teamNodeDraft.model}
                                        onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, model: event.target.value } : current)}
                                        fullWidth
                                    />
                                    <TextField
                                        label="Fallback model"
                                        value={teamNodeDraft.fallbackModel}
                                        onChange={(event) => setTeamNodeDraft((current) => current ? { ...current, fallbackModel: event.target.value } : current)}
                                        fullWidth
                                    />
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
                    <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
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
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                                    <Typography variant="caption" color="text.secondary">Capabilities</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{skillForm.capabilities.length} linked</Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                                    <Typography variant="caption" color="text.secondary">Allowed tools</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{skillForm.allowed_tools.length} required</Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                                    <Typography variant="caption" color="text.secondary">Tags</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{skillForm.tags.length} labels</Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
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
                            onChange={(nextValue) => setSkillForm((current) => ({ ...current, capabilities: nextValue }))}
                            helperText="Use concise routing-friendly labels like qa, decomposition, repo-triage, benchmark-design."
                            options={stringOptions.capabilities}
                        />
                        <StringListField
                            label="Required tools"
                            value={skillForm.allowed_tools}
                            onChange={(nextValue) => setSkillForm((current) => ({ ...current, allowed_tools: nextValue }))}
                            helperText="List only the tools this skill assumes the host agent can use."
                            options={stringOptions.tools}
                        />
                        <StringListField
                            label="Tags"
                            value={skillForm.tags}
                            onChange={(nextValue) => setSkillForm((current) => ({ ...current, tags: nextValue }))}
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
                    <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
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
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                                    <Typography variant="caption" color="text.secondary">Agents</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{selectedTeamAgentTemplates.length} selected</Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                                    <Typography variant="caption" color="text.secondary">Roles</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{derivedTeamTemplateSummary.roles.length} derived</Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
                                    <Typography variant="caption" color="text.secondary">Tools</Typography>
                                    <Typography variant="body2" sx={{ mt: 0.5 }}>{derivedTeamTemplateSummary.tools.length} derived</Typography>
                                </Paper>
                                <Paper variant="outlined" sx={{ p: 1.25, borderRadius: 2 }}>
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
                                    borderRadius: 3,
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
                                    <Box sx={{ height: 420, borderRadius: 2, overflow: "hidden", bgcolor: alpha("#f8fafc", 0.7) }}>
                                        <ReactFlow
                                            nodes={teamTemplateCanvasNodes}
                                            edges={teamTemplateCanvasEdges}
                                            nodeTypes={nodeTypes}
                                            onNodesChange={onTeamTemplateCanvasNodesChange}
                                            onNodeClick={(_, node) => setSelectedTeamTemplateCanvasNodeId(node.id)}
                                            onPaneClick={() => setSelectedTeamTemplateCanvasNodeId(null)}
                                            fitView
                                            deleteKeyCode={null}
                                            selectionOnDrag={false}
                                            proOptions={{ hideAttribution: true }}
                                        >
                                            <Background color="#d0d5dd" gap={18} size={1.1} />
                                            <Controls showInteractive={false} />
                                        </ReactFlow>
                                    </Box>
                                )}
                                <Typography variant="caption" color="text.secondary" sx={{ display: "block", px: 1, pt: 1 }}>
                                    Canvas is composition-first preview. Saved template persists included agent templates; exact node coordinates are not stored yet.
                                </Typography>
                            </Paper>
                            <Stack spacing={1.25}>
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
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
                                <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
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
                                                    sx={{ p: 1.25, borderRadius: 2, opacity: isIncluded ? 0.6 : 1 }}
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

        </PageShell>
    );
}
