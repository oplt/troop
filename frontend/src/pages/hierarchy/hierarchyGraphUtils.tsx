import {
    FactCheck as ReviewerIcon,
    ManageAccounts as ManagerIcon,
    Engineering as SpecialistIcon,
} from "@mui/icons-material";
import type { Agent, AgentTemplate, OrchestrationProject, SkillPack } from "../../api/orchestration";
import { MarkerType } from "@xyflow/react";
import {
    parseAgentTemplateCsv,
    parseAgentTemplateLooseList,
} from "../../features/agentTemplates/formState";
import { uniqueStrings } from "../../features/hierarchy/templates/templateState";
import {
    MEMORY_SCOPE_OPTIONS,
    OUTPUT_FORMAT_OPTIONS,
    PERMISSION_OPTIONS,
    ROLE_OPTIONS,
    RUNTIME_ALLOWED_TOOLS,
    TEAM_GRAPH_PROJECT_STORAGE_KEY,
    TEAM_GRAPH_STORAGE_KEY,
    type TeamGraphEdge,
    type TeamGraphEdgeSemantic,
    type TeamGraphNode,
    type TeamGraphNodeData,
    type TeamGraphNodeStatus,
    type TeamGraphRole,
    type TeamLayoutSnapshot,
} from "./hierarchyTypes";

export function normalizeTeamGraphRole(value: string | undefined): TeamGraphRole {
    return ROLE_OPTIONS.includes(value as (typeof ROLE_OPTIONS)[number])
        ? (value as TeamGraphRole)
        : "specialist";
}



export type StringListFieldProps = {
    label: string;
    value: string[];
    onChange: (nextValue: string[]) => void;
    helperText?: string;
    placeholder?: string;
    options?: string[];
};

export function parseCsv(value: string): string[] {
    return parseAgentTemplateCsv(value);
}

export function parseLooseList(value: string): string[] {
    return parseAgentTemplateLooseList(value);
}

export function slugify(value: string) {
    return value
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/(^-|-$)/g, "");
}

export function createUniqueSlug(value: string, existingSlugs: string[]) {
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

export function createUniqueNodeId(value: string, existingIds: string[]) {
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

export function normalizeAgentName(value: string, fallback = "Untitled agent"): string {
    const cleaned = value.trim();
    if (cleaned.length >= 2) {
        return cleaned;
    }
    const fallbackCleaned = fallback.trim();
    if (fallbackCleaned.length >= 2) {
        return fallbackCleaned;
    }
    return "Untitled agent";
}

export function normalizeAgentSlug(value: string, fallback = "agent"): string {
    const candidate = slugify(value);
    if (candidate.length >= 2) {
        return candidate;
    }
    if (candidate.length === 1) {
        return `${candidate}-agent`;
    }
    const fallbackSlug = slugify(fallback);
    if (fallbackSlug.length >= 2) {
        return fallbackSlug;
    }
    if (fallbackSlug.length === 1) {
        return `${fallbackSlug}-agent`;
    }
    return "agent";
}

export function clamp(value: number, min: number, max: number): number {
    return Math.min(max, Math.max(min, value));
}

export function normalizePermission(value: string): string {
    const normalized = value.trim().toLowerCase().replace(/[_\s]+/g, "-");
    if (normalized === "readonly") return "read-only";
    if (normalized === "commentonly") return "comment-only";
    if (normalized === "codewrite") return "code-write";
    if (normalized === "mergeblocked") return "merge-blocked";
    return PERMISSION_OPTIONS.includes(normalized as (typeof PERMISSION_OPTIONS)[number]) ? normalized : "read-only";
}

export function normalizeMemoryScope(value: string): string {
    return MEMORY_SCOPE_OPTIONS.includes(value as (typeof MEMORY_SCOPE_OPTIONS)[number]) ? value : "project-only";
}

export function normalizeOutputFormat(value: string): string {
    return OUTPUT_FORMAT_OPTIONS.includes(value as (typeof OUTPUT_FORMAT_OPTIONS)[number]) ? value : "json";
}

export function normalizeTaskFilters(values: string[]): string[] {
    return values
        .map((value) => value.trim())
        .filter((value) => {
            if (!value) {
                return false;
            }
            if (!/[\\^$[\]().*+?{}|]/.test(value)) {
                return true;
            }
            try {
                new RegExp(value);
                return true;
            } catch {
                return false;
            }
        });
}

export function stringifyCommaList(items: readonly string[]): string {
    return items
        .map((item) => item.trim())
        .filter(Boolean)
        .join(", ");
}

export function skillDisplayName(slug: string, catalog: SkillPack[]) {
    return catalog.find((item) => item.slug === slug)?.name ?? slug;
}

export function getTemplateBySlug(templates: AgentTemplate[], slug: string) {
    return templates.find((item) => item.slug === slug) ?? null;
}

export function getRoleIcon(role: TeamGraphRole) {
    if (role === "manager" || role === "team_lead") return <ManagerIcon fontSize="small" />;
    if (role === "reviewer") return <ReviewerIcon fontSize="small" />;
    return <SpecialistIcon fontSize="small" />;
}

export function getRoleColor(role: TeamGraphRole) {
    if (role === "manager" || role === "team_lead") return "primary";
    if (role === "reviewer") return "warning";
    return "info";
}

export function buildNodeDataFromTemplate(template: AgentTemplate): TeamGraphNodeData {
    return {
        name: template.name,
        slug: template.slug,
        role: normalizeTeamGraphRole(template.role),
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

export function buildTeamTemplateCanvasGraph(selectedTemplates: AgentTemplate[]): { nodes: TeamGraphNode[]; edges: TeamGraphEdge[] } {
    const nodes = autoLayoutGraph(
        selectedTemplates.map((template, index) => ({
            id: `team-template-${template.slug}`,
            type: normalizeTeamGraphRole(template.role),
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

export function extractTeamTemplateCanvasLayout(nodes: TeamGraphNode[], edges: TeamGraphEdge[]): Record<string, unknown> {
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

export function applyTeamTemplateCanvasLayout(
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

export function buildNodeDataFromAgent(
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
        role: normalizeTeamGraphRole(agent.role),
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

export function autoLayoutGraph(nodes: TeamGraphNode[]): TeamGraphNode[] {
    const centerX = 0;
    const managerY = 0;
    const childRowY = 500;
    const gapX = 400;
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
        team_lead: [],
        specialist: [],
        reviewer: [],
    };
    nodes.forEach((node) => {
        grouped[node.data.role].push(node);
    });
    const rowY: Record<TeamGraphRole, number> = {
        manager: managerY,
        team_lead: 180,
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

export function createDefaultNodeData(
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

export function buildDefaultTeamGraph(): { nodes: TeamGraphNode[]; edges: TeamGraphEdge[] } {
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
            model: "",
        },
        {
            id: "default-builder",
            role: "specialist",
            name: "Builder",
            slug: "builder",
            description: "Implements subtasks end-to-end, writes code and tests.",
            capabilities: ["code-write", "refactor"],
            model: "",
        },
        {
            id: "default-reviewer",
            role: "reviewer",
            name: "Reviewer",
            slug: "reviewer",
            description: "Audits output for correctness and policy compliance.",
            capabilities: ["qa", "review"],
            model: "",
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
            "",
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

export const DEFAULT_TEAM_GRAPH = buildDefaultTeamGraph();

export function cloneNodeData(data: TeamGraphNodeData): TeamGraphNodeData {
    return {
        ...data,
        capabilities: [...data.capabilities],
        allowedTools: [...data.allowedTools],
        tags: [...data.tags],
        projectAssignments: [...data.projectAssignments],
        taskFilters: [...data.taskFilters],
    };
}

export function buildNodeSubtitle(data: Pick<TeamGraphNodeData, "linkedTemplateSlug" | "linkedAgentId" | "slug">) {
    if (data.linkedTemplateSlug) {
        return `template ${data.linkedTemplateSlug}`;
    }
    if (data.linkedAgentId) {
        return data.slug;
    }
    return "local draft";
}

export function ensureMinimumHierarchy(
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

export function buildInitialTeamGraph(
    agents: Agent[],
    liveStatus: Map<string, "running" | "blocked" | "queued" | "idle">,
): { nodes: TeamGraphNode[]; edges: TeamGraphEdge[] } {
    if (agents.length === 0) {
        return ensureMinimumHierarchy(DEFAULT_TEAM_GRAPH);
    }

    const nodes = autoLayoutGraph(
        agents.map((agent, index) => ({
            id: agent.id,
            type: normalizeTeamGraphRole(agent.role),
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

export function createSemanticEdge(source: string, target: string, semantic: TeamGraphEdgeSemantic): TeamGraphEdge {
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

export function readSavedTeamLayoutSnapshot(): TeamLayoutSnapshot | null {
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

export function readSelectedHierarchyProjectId(): string {
    if (typeof window === "undefined") {
        return "";
    }
    return window.localStorage.getItem(TEAM_GRAPH_PROJECT_STORAGE_KEY) ?? "";
}

export function persistSelectedHierarchyProjectId(projectId: string) {
    if (typeof window === "undefined") {
        return;
    }
    if (!projectId) {
        window.localStorage.removeItem(TEAM_GRAPH_PROJECT_STORAGE_KEY);
        return;
    }
    window.localStorage.setItem(TEAM_GRAPH_PROJECT_STORAGE_KEY, projectId);
}

export function readProjectTeamLayoutSnapshot(project: OrchestrationProject | null | undefined): TeamLayoutSnapshot | null {
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

export function parsePositiveInteger(value: string, fallback: number): number {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function findManagerRootNode(nodes: TeamGraphNode[], edges: TeamGraphEdge[]): TeamGraphNode | null {
    const managers = nodes.filter((node) => node.data.role === "manager");
    if (managers.length === 0) {
        return null;
    }
    const delegatedTargets = new Set(
        edges.filter((edge) => edge.data?.semantic === "delegates_to").map((edge) => edge.target),
    );
    return managers.find((node) => !delegatedTargets.has(node.id)) ?? managers[0] ?? null;
}

export function sanitizeRuntimeTools(tools: string[]): string[] {
    return uniqueStrings(tools).filter((tool) => RUNTIME_ALLOWED_TOOLS.has(tool));
}

export function persistTeamLayoutSnapshot(snapshot: TeamLayoutSnapshot | null) {
    if (typeof window === "undefined") {
        return;
    }
    if (!snapshot) {
        window.localStorage.removeItem(TEAM_GRAPH_STORAGE_KEY);
        return;
    }
    window.localStorage.setItem(TEAM_GRAPH_STORAGE_KEY, JSON.stringify(snapshot));
}

