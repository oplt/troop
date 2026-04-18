import { useCallback, useEffect, useMemo, useState } from "react";
import {
    alpha,
    Avatar,
    Box,
    Button,
    Chip,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Divider,
    LinearProgress,
    MenuItem,
    Paper,
    Stack,
    Tab,
    Tabs,
    TextField,
    Typography,
} from "@mui/material";
import {
    Add as AddIcon,
    AssignmentTurnedIn as ApproveIcon,
    AutoAwesome as BrainstormIcon,
    CallSplit as DecomposeIcon,
    ContentCopy as CloneIcon,
    ErrorOutline as EscalateIcon,
    Forum as ChatIcon,
    RateReview as ReviewIcon,
    SmartToy as AgentIcon,
} from "@mui/icons-material";
import {
    Background,
    Controls,
    Handle,
    MarkerType,
    Position,
    ReactFlow,
    ReactFlowProvider,
    useEdgesState,
    useNodesState,
    useReactFlow,
    type Edge,
    type Node,
    type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

type HierarchyNodeKind = "manager" | "member";
type AgentStatus = "idle" | "running" | "blocked" | "needs_review";
type TaskStatus = "active" | "completed" | "blocked" | "needs_review";
type LayerTab = "organization" | "agent" | "execution";
type DetailTab = "active" | "completed" | "conversation" | "artifacts" | "runs" | "metrics";

type ModelProfile = {
    id: string;
    provider: "openai" | "anthropic" | "local" | "other";
    model: string;
    badge: string;
    temperature: number;
    maxTokens: number;
    costTier: "low" | "medium" | "high";
    supportsTools: boolean;
    supportsStructuredOutput: boolean;
};

type SkillBinding = {
    id: string;
    skill: string;
    promptInstructions: string;
    allowedTools: string[];
    outputSchema: string;
    evaluationChecks: string[];
};

type TaskItem = {
    id: string;
    title: string;
    status: TaskStatus;
    assigneeId: string;
    updatedAt: string;
};

type ConversationMessage = {
    id: string;
    author: string;
    text: string;
    timestamp: string;
};

type ArtifactItem = {
    id: string;
    name: string;
    type: string;
    status: "draft" | "ready" | "approved";
};

type RunEntry = {
    id: string;
    status: AgentStatus;
    startedAt: string;
    finishedAt: string | null;
    tokenUsage: number;
    costUsd: number;
    latencyMs: number;
    errorMessage: string | null;
    fallbackUsed: boolean;
};

type MemoryPolicy = {
    readAccess: string[];
    writeAccess: string[];
    summarizationFrequency: string;
    retentionPolicy: string;
};

type EvaluationGates = {
    validateStructure: boolean;
    validateEvidence: boolean;
    runTests: boolean;
    managerApproval: boolean;
};

type MemberRecord = {
    id: string;
    kind: HierarchyNodeKind;
    parentId: string | null;
    name: string;
    role: string;
    objective: string;
    primaryModelProfileId: string;
    fallbackModelProfileId?: string;
    allowedModelProfileIds: string[];
    toolAccess: string[];
    memoryPolicy: MemoryPolicy;
    autonomyLevel: "low" | "medium" | "high";
    approvalPolicy: "auto" | "manager_review" | "strict";
    costBudgetUsd: number;
    currentWorkload: number;
    status: AgentStatus;
    lastRunTime: string;
    successRate: number;
    averageLatencyMs: number;
    errorCount: number;
    validationFailureCount: number;
    fallbackEvents: number;
    tokenUsage: number;
    costUsageUsd: number;
    isTemporary?: boolean;
    skillBindings: SkillBinding[];
    activeTasks: TaskItem[];
    completedTasks: TaskItem[];
    conversationThread: ConversationMessage[];
    artifacts: ArtifactItem[];
    runHistory: RunEntry[];
    teamBudgetUsd?: number;
    reviewQueueCount?: number;
};

type HierarchyNodeData = {
    id: string;
    kind: HierarchyNodeKind;
    name: string;
    role: string;
    objective: string;
    status: AgentStatus;
    workload: number;
    modelBadge: string;
    costUsageUsd: number;
    tokenUsage: number;
    isTemporary?: boolean;
    reviewQueueCount?: number;
    teamBudgetUsd?: number;
    onSelect: (nodeId: string) => void;
    onEdit: (nodeId: string) => void;
    onRemove: (nodeId: string) => void;
    onAddTeamMember: () => void;
    onBrainstorm: () => void;
    onReviewQueue: () => void;
};

type MemberDraft = {
    name: string;
    role: string;
    objective: string;
    primaryModelProfileId: string;
    fallbackModelProfileId: string;
    allowedModelProfileIds: string;
    toolAccess: string;
    memoryReadAccess: string;
    memoryWriteAccess: string;
    summarizationFrequency: string;
    retentionPolicy: string;
    autonomyLevel: MemberRecord["autonomyLevel"];
    approvalPolicy: MemberRecord["approvalPolicy"];
    costBudgetUsd: string;
    currentWorkload: string;
    status: AgentStatus;
    skillBindings: string;
    evaluationGates: EvaluationGates;
};

type TeamTemplate = {
    id: string;
    name: string;
    description: string;
    manager: Partial<MemberRecord>;
    members: Array<Partial<MemberRecord> & { role: string; objective: string; skillBindings: SkillBinding[] }>;
};

const MANAGER_ID = "manager-1";
const NODE_WIDTH = 290;
const MANAGER_HEIGHT = 280;
const MEMBER_HEIGHT = 236;
const HORIZONTAL_GAP = 46;
const MANAGER_TO_MEMBER_GAP = 200;
const VERTICAL_GAP = 108;
const CANVAS_PADDING_X = 40;
const CANVAS_PADDING_Y = 32;

const MODEL_PROFILES: ModelProfile[] = [
    {
        id: "gpt-5-strategist",
        provider: "openai",
        model: "gpt-5",
        badge: "GPT-5",
        temperature: 0.2,
        maxTokens: 64000,
        costTier: "high",
        supportsTools: true,
        supportsStructuredOutput: true,
    },
    {
        id: "gpt-5-coder",
        provider: "openai",
        model: "gpt-5-codex",
        badge: "GPT-5 Codex",
        temperature: 0.15,
        maxTokens: 64000,
        costTier: "high",
        supportsTools: true,
        supportsStructuredOutput: true,
    },
    {
        id: "claude-synthesis",
        provider: "anthropic",
        model: "claude-sonnet",
        badge: "Claude",
        temperature: 0.3,
        maxTokens: 32000,
        costTier: "medium",
        supportsTools: true,
        supportsStructuredOutput: true,
    },
    {
        id: "local-private",
        provider: "local",
        model: "llama-private",
        badge: "Local Llama",
        temperature: 0.1,
        maxTokens: 16000,
        costTier: "low",
        supportsTools: true,
        supportsStructuredOutput: false,
    },
];

const DEFAULT_MEMORY_POLICY: MemoryPolicy = {
    readAccess: ["global/company memory", "project memory", "shared team memory"],
    writeAccess: ["project memory", "task memory", "private scratch memory"],
    summarizationFrequency: "Every completed task",
    retentionPolicy: "30 days + promoted summaries",
};

const DEFAULT_EVALUATION_GATES: EvaluationGates = {
    validateStructure: true,
    validateEvidence: true,
    runTests: false,
    managerApproval: true,
};

function nowIso() {
    return new Date().toISOString();
}

function createSkillBinding(
    id: string,
    skill: string,
    promptInstructions: string,
    allowedTools: string[],
    outputSchema: string,
    evaluationChecks: string[],
): SkillBinding {
    return {
        id,
        skill,
        promptInstructions,
        allowedTools,
        outputSchema,
        evaluationChecks,
    };
}

function createTask(id: string, title: string, assigneeId: string, status: TaskStatus): TaskItem {
    return { id, title, assigneeId, status, updatedAt: nowIso() };
}

function createRun(
    id: string,
    status: AgentStatus,
    tokenUsage: number,
    costUsd: number,
    latencyMs: number,
    fallbackUsed = false,
    errorMessage: string | null = null,
): RunEntry {
    const startedAt = nowIso();
    return {
        id,
        status,
        startedAt,
        finishedAt: status === "running" ? null : startedAt,
        tokenUsage,
        costUsd,
        latencyMs,
        errorMessage,
        fallbackUsed,
    };
}

function createConversation(author: string, text: string): ConversationMessage {
    return {
        id: `${author}-${Math.random().toString(36).slice(2, 7)}`,
        author,
        text,
        timestamp: nowIso(),
    };
}

function buildDefaultRecords(): MemberRecord[] {
    return [
        {
            id: MANAGER_ID,
            kind: "manager",
            parentId: null,
            name: "Alex Morgan",
            role: "AI Delivery Manager",
            objective: "Plan work, decompose project goals, orchestrate execution, and approve outputs.",
            primaryModelProfileId: "gpt-5-strategist",
            fallbackModelProfileId: "claude-synthesis",
            allowedModelProfileIds: ["gpt-5-strategist", "claude-synthesis"],
            toolAccess: ["project planner", "task board", "approval queue", "brainstorm room", "budget dashboard"],
            memoryPolicy: DEFAULT_MEMORY_POLICY,
            autonomyLevel: "high",
            approvalPolicy: "strict",
            costBudgetUsd: 300,
            currentWorkload: 48,
            status: "running",
            lastRunTime: nowIso(),
            successRate: 96,
            averageLatencyMs: 2400,
            errorCount: 1,
            validationFailureCount: 1,
            fallbackEvents: 2,
            tokenUsage: 21430,
            costUsageUsd: 38.5,
            skillBindings: [
                createSkillBinding("manager-plan", "project planning", "Turn goals into bounded tasks with acceptance criteria.", ["task board", "query_graphql"], "TaskPlan", ["validate structure", "manager approval"]),
                createSkillBinding("manager-review", "quality review", "Compare outputs against schemas, specs, and delivery standards.", ["approval queue", "request_manager_review"], "ReviewDecision", ["validate structure", "validate evidence"]),
            ],
            activeTasks: [
                createTask("task-manager-1", "Launch hierarchy builder", MANAGER_ID, "active"),
                createTask("task-manager-2", "Review blocked QA feedback", MANAGER_ID, "needs_review"),
            ],
            completedTasks: [createTask("task-manager-3", "Define orchestration policy", MANAGER_ID, "completed")],
            conversationThread: [
                createConversation("System", "Manager initialized with orchestration controls."),
                createConversation("Alex Morgan", "Breaking launch goal into research, implementation, and QA streams."),
            ],
            artifacts: [
                { id: "artifact-plan", name: "Launch task plan", type: "plan", status: "ready" },
                { id: "artifact-review", name: "Approval checklist", type: "checklist", status: "approved" },
            ],
            runHistory: [
                createRun("run-manager-1", "running", 8400, 14.2, 2200),
                createRun("run-manager-2", "idle", 3500, 6.4, 1800),
            ],
            teamBudgetUsd: 1200,
            reviewQueueCount: 2,
        },
        {
            id: "member-1",
            kind: "member",
            parentId: MANAGER_ID,
            name: "Jordan Lee",
            role: "Research Agent",
            objective: "Collect competitive intelligence with cited evidence and concise synthesis.",
            primaryModelProfileId: "claude-synthesis",
            fallbackModelProfileId: "gpt-5-strategist",
            allowedModelProfileIds: ["claude-synthesis", "gpt-5-strategist"],
            toolAccess: ["web research", "document retriever", "citation formatter", "summarizer"],
            memoryPolicy: {
                readAccess: ["global/company memory", "project memory"],
                writeAccess: ["project memory", "task memory"],
                summarizationFrequency: "After each source batch",
                retentionPolicy: "14 days + summary promotion",
            },
            autonomyLevel: "medium",
            approvalPolicy: "manager_review",
            costBudgetUsd: 180,
            currentWorkload: 52,
            status: "running",
            lastRunTime: nowIso(),
            successRate: 93,
            averageLatencyMs: 1900,
            errorCount: 2,
            validationFailureCount: 1,
            fallbackEvents: 1,
            tokenUsage: 12600,
            costUsageUsd: 12.8,
            skillBindings: [
                createSkillBinding("research-1", "competitive analysis", "Search broad landscape, compare top solutions, and cite claims.", ["web research", "document retriever", "citation formatter"], "ResearchBrief", ["validate citations", "validate structure"]),
                createSkillBinding("research-2", "brief writing", "Compress findings into executive summary and decision memo.", ["summarizer"], "DecisionMemo", ["validate structure"]),
            ],
            activeTasks: [createTask("task-research-1", "Map org-chart competitors", "member-1", "active")],
            completedTasks: [createTask("task-research-2", "Summarize user feedback", "member-1", "completed")],
            conversationThread: [
                createConversation("Alex Morgan", "Need competitor patterns for orchestration consoles."),
                createConversation("Jordan Lee", "Collecting sources and building citation-backed summary."),
            ],
            artifacts: [{ id: "artifact-research-1", name: "Competitor matrix", type: "doc", status: "ready" }],
            runHistory: [
                createRun("run-research-1", "running", 5400, 4.3, 1600),
                createRun("run-research-2", "idle", 3100, 2.7, 1400),
            ],
        },
        {
            id: "member-2",
            kind: "member",
            parentId: MANAGER_ID,
            name: "Taylor Kim",
            role: "Implementation Agent",
            objective: "Ship TypeScript features, connect tools, and keep tests green.",
            primaryModelProfileId: "gpt-5-coder",
            fallbackModelProfileId: "local-private",
            allowedModelProfileIds: ["gpt-5-coder", "local-private"],
            toolAccess: ["repo read/write", "code generator", "test runner", "build logs"],
            memoryPolicy: {
                readAccess: ["project memory", "task memory", "shared team memory"],
                writeAccess: ["task memory", "private scratch memory", "shared team memory"],
                summarizationFrequency: "On branch update",
                retentionPolicy: "Branch lifetime + promoted summaries",
            },
            autonomyLevel: "high",
            approvalPolicy: "manager_review",
            costBudgetUsd: 260,
            currentWorkload: 68,
            status: "running",
            lastRunTime: nowIso(),
            successRate: 95,
            averageLatencyMs: 2600,
            errorCount: 1,
            validationFailureCount: 2,
            fallbackEvents: 3,
            tokenUsage: 16820,
            costUsageUsd: 21.2,
            skillBindings: [
                createSkillBinding("impl-1", "TypeScript", "Implement typed UI and API changes with explicit state ownership.", ["repo read/write", "code generator", "test runner"], "PatchProposal", ["run tests", "validate structure"]),
                createSkillBinding("impl-2", "API integration", "Connect UI to orchestration APIs and preserve typed contracts.", ["repo read/write", "build logs"], "IntegrationUpdate", ["run tests"]),
            ],
            activeTasks: [
                createTask("task-impl-1", "Implement hierarchy builder console", "member-2", "active"),
                createTask("task-impl-2", "Wire node detail panel", "member-2", "needs_review"),
            ],
            completedTasks: [createTask("task-impl-3", "Install React Flow", "member-2", "completed")],
            conversationThread: [
                createConversation("Alex Morgan", "Need controlled drag-drop plus editable node profiles."),
                createConversation("Taylor Kim", "Working on controlled flow state and detail panes."),
            ],
            artifacts: [
                { id: "artifact-impl-1", name: "Hierarchy canvas patch", type: "code", status: "ready" },
                { id: "artifact-impl-2", name: "Type model contract", type: "schema", status: "draft" },
            ],
            runHistory: [
                createRun("run-impl-1", "running", 7200, 10.7, 2800, true),
                createRun("run-impl-2", "idle", 4200, 6.3, 2300),
            ],
        },
        {
            id: "member-3",
            kind: "member",
            parentId: MANAGER_ID,
            name: "Sam Rivera",
            role: "QA Agent",
            objective: "Validate behavior, find regressions, and gate release quality.",
            primaryModelProfileId: "gpt-5-strategist",
            fallbackModelProfileId: "claude-synthesis",
            allowedModelProfileIds: ["gpt-5-strategist", "claude-synthesis"],
            toolAccess: ["issue reader", "log parser", "test failure analyzer", "release checklist"],
            memoryPolicy: {
                readAccess: ["project memory", "task memory", "shared team memory"],
                writeAccess: ["task memory", "project memory"],
                summarizationFrequency: "After every validation pass",
                retentionPolicy: "30 days",
            },
            autonomyLevel: "medium",
            approvalPolicy: "strict",
            costBudgetUsd: 150,
            currentWorkload: 31,
            status: "blocked",
            lastRunTime: nowIso(),
            successRate: 90,
            averageLatencyMs: 1700,
            errorCount: 3,
            validationFailureCount: 4,
            fallbackEvents: 0,
            tokenUsage: 8800,
            costUsageUsd: 8.1,
            skillBindings: [
                createSkillBinding("qa-1", "bug triage", "Classify defects by severity, repro quality, and recommended owner.", ["issue reader", "log parser", "test failure analyzer"], "BugReport", ["validate structure", "validate evidence"]),
                createSkillBinding("qa-2", "release checks", "Run regression checklist and reject incomplete outputs.", ["release checklist", "test failure analyzer"], "ReleaseDecision", ["run tests", "manager approval"]),
            ],
            activeTasks: [createTask("task-qa-1", "Validate drag-drop reassignment", "member-3", "blocked")],
            completedTasks: [createTask("task-qa-2", "Check initial hierarchy render", "member-3", "completed")],
            conversationThread: [
                createConversation("Sam Rivera", "Drag-drop edge case found when reassigning back to manager."),
                createConversation("Alex Morgan", "Escalate once repro steps and fix validation are ready."),
            ],
            artifacts: [{ id: "artifact-qa-1", name: "Validation checklist", type: "checklist", status: "approved" }],
            runHistory: [
                createRun("run-qa-1", "blocked", 2500, 1.9, 1200, false, "Manager drop target missed hit test."),
                createRun("run-qa-2", "idle", 2100, 1.6, 1100),
            ],
        },
    ];
}

const TEAM_TEMPLATES: TeamTemplate[] = [
    {
        id: "product-team",
        name: "Product team",
        description: "PM-led trio for planning, shipping, and validating roadmap work.",
        manager: { name: "Avery Patel", role: "Product Manager", objective: "Drive goals, align scope, and approve outcomes." },
        members: [
            { role: "Research Agent", objective: "Collect market and user evidence.", skillBindings: [createSkillBinding("tpl-p1", "user research", "Synthesize interviews and market signals.", ["web research", "summarizer"], "InsightReport", ["validate evidence"])] },
            { role: "Implementation Agent", objective: "Ship front-end and workflow changes.", skillBindings: [createSkillBinding("tpl-p2", "feature delivery", "Implement scoped product updates.", ["repo read/write", "test runner"], "PatchProposal", ["run tests"])] },
            { role: "QA Agent", objective: "Protect release quality and sign-off.", skillBindings: [createSkillBinding("tpl-p3", "release QA", "Check regressions and approvals.", ["release checklist", "log parser"], "ReleaseDecision", ["manager approval"])] },
        ],
    },
    {
        id: "ai-engineering",
        name: "AI engineering team",
        description: "Orchestration-first team for agent systems and evals.",
        manager: { name: "Rowan Blake", role: "AI Systems Manager", objective: "Route multi-agent delivery and improve eval loops." },
        members: [
            { role: "Research Agent", objective: "Map tool, model, and framework tradeoffs.", skillBindings: [createSkillBinding("tpl-a1", "framework analysis", "Compare control-plane and runtime options.", ["web research", "citation formatter"], "ArchitectureBrief", ["validate evidence"])] },
            { role: "Implementation Agent", objective: "Build agent consoles and runtime integration.", skillBindings: [createSkillBinding("tpl-a2", "agent engineering", "Implement orchestration UI and execution hooks.", ["repo read/write", "run_tests"], "ImplementationPlan", ["run tests", "validate structure"])] },
            { role: "QA Agent", objective: "Run eval gates and failure analysis.", skillBindings: [createSkillBinding("tpl-a3", "eval design", "Design repeatable checks and error triage.", ["test failure analyzer", "release checklist"], "EvalReport", ["manager approval"])] },
        ],
    },
    {
        id: "research-pod",
        name: "Research pod",
        description: "Research-heavy pod with synthesis and evidence controls.",
        manager: { name: "Kai Bennett", role: "Research Lead", objective: "Coordinate research tracks and evidence quality." },
        members: [
            { role: "Competitive Research Agent", objective: "Track adjacent products and market patterns.", skillBindings: [createSkillBinding("tpl-r1", "competitive analysis", "Benchmark peers and alternatives.", ["web research", "citation formatter"], "ResearchBrief", ["validate evidence"])] },
            { role: "Evidence Synthesis Agent", objective: "Summarize long-form sources into structured memos.", skillBindings: [createSkillBinding("tpl-r2", "synthesis", "Compress inputs into decision-ready notes.", ["document retriever", "summarizer"], "DecisionMemo", ["validate structure"])] },
            { role: "QA Agent", objective: "Check sourcing and consistency.", skillBindings: [createSkillBinding("tpl-r3", "source QA", "Flag unsupported claims.", ["citation formatter", "log parser"], "SourceAudit", ["validate evidence"])] },
        ],
    },
    {
        id: "qa-pod",
        name: "QA pod",
        description: "Validation-focused team for release readiness and incident triage.",
        manager: { name: "Jules Carter", role: "QA Lead", objective: "Run release gates and manage failure recovery." },
        members: [
            { role: "Bug Triage Agent", objective: "Classify defects and route ownership.", skillBindings: [createSkillBinding("tpl-q1", "bug triage", "Prioritize issues with owner suggestions.", ["issue reader", "log parser"], "BugReport", ["validate structure"])] },
            { role: "Regression Agent", objective: "Execute structured test coverage and release checks.", skillBindings: [createSkillBinding("tpl-q2", "regression testing", "Run repeatable validation passes.", ["test runner", "release checklist"], "TestReport", ["run tests"])] },
            { role: "Review Agent", objective: "Approve deliverables against spec and evidence.", skillBindings: [createSkillBinding("tpl-q3", "quality review", "Reject incomplete outputs.", ["approval queue"], "ReviewDecision", ["manager approval"])] },
        ],
    },
    {
        id: "growth-team",
        name: "Growth team",
        description: "Growth pod for experiments, insights, and landing page delivery.",
        manager: { name: "Morgan Cruz", role: "Growth Lead", objective: "Coordinate experiments and approve campaign outputs." },
        members: [
            { role: "Research Agent", objective: "Find channel and messaging opportunities.", skillBindings: [createSkillBinding("tpl-g1", "market research", "Identify ICP and messaging gaps.", ["web research", "summarizer"], "GrowthBrief", ["validate evidence"])] },
            { role: "Implementation Agent", objective: "Ship experiments and conversion updates.", skillBindings: [createSkillBinding("tpl-g2", "experiment delivery", "Implement experiments safely.", ["repo read/write", "build logs"], "ExperimentPatch", ["run tests"])] },
            { role: "QA Agent", objective: "Validate metrics instrumentation and rollout risk.", skillBindings: [createSkillBinding("tpl-g3", "experiment QA", "Check analytics and launch criteria.", ["release checklist", "log parser"], "LaunchChecklist", ["manager approval"])] },
        ],
    },
];

function parseCsv(value: string) {
    return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

function serializeSkillBindings(skillBindings: SkillBinding[]) {
    return skillBindings
        .map((binding) => [
            binding.skill,
            binding.allowedTools.join(", "),
            binding.outputSchema,
            binding.evaluationChecks.join(", "),
            binding.promptInstructions,
        ].join(" | "))
        .join("\n");
}

function parseSkillBindings(value: string): SkillBinding[] {
    return value
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line, index) => {
            const [skill = "", tools = "", outputSchema = "StructuredOutput", checks = "", promptInstructions = ""] = line.split("|").map((item) => item.trim());
            return createSkillBinding(
                `binding-${index}-${skill.toLowerCase().replace(/\s+/g, "-") || "skill"}`,
                skill || `Skill ${index + 1}`,
                promptInstructions || "Follow role instructions and return structured output.",
                parseCsv(tools),
                outputSchema,
                parseCsv(checks),
            );
        });
}

function formatDateLabel(value: string) {
    return new Date(value).toLocaleString();
}

function formatMoney(value: number) {
    return `$${value.toFixed(1)}`;
}

function statusColor(status: AgentStatus) {
    if (status === "running") return "primary";
    if (status === "blocked") return "error";
    if (status === "needs_review") return "warning";
    return "default";
}

function modelById(id: string | undefined) {
    return MODEL_PROFILES.find((profile) => profile.id === id) ?? MODEL_PROFILES[0];
}

function createDraft(record: MemberRecord): MemberDraft {
    return {
        name: record.name,
        role: record.role,
        objective: record.objective,
        primaryModelProfileId: record.primaryModelProfileId,
        fallbackModelProfileId: record.fallbackModelProfileId ?? "",
        allowedModelProfileIds: record.allowedModelProfileIds.join(", "),
        toolAccess: record.toolAccess.join(", "),
        memoryReadAccess: record.memoryPolicy.readAccess.join(", "),
        memoryWriteAccess: record.memoryPolicy.writeAccess.join(", "),
        summarizationFrequency: record.memoryPolicy.summarizationFrequency,
        retentionPolicy: record.memoryPolicy.retentionPolicy,
        autonomyLevel: record.autonomyLevel,
        approvalPolicy: record.approvalPolicy,
        costBudgetUsd: String(record.costBudgetUsd),
        currentWorkload: String(record.currentWorkload),
        status: record.status,
        skillBindings: serializeSkillBindings(record.skillBindings),
        evaluationGates: (record as MemberRecord & { evaluationGates?: EvaluationGates }).evaluationGates ?? DEFAULT_EVALUATION_GATES,
    };
}

function canAssignParent(records: MemberRecord[], movingId: string, nextParentId: string) {
    if (movingId === MANAGER_ID || movingId === nextParentId) {
        return false;
    }

    let currentParentId: string | null = nextParentId;
    while (currentParentId) {
        if (currentParentId === movingId) {
            return false;
        }
        currentParentId = records.find((record) => record.id === currentParentId)?.parentId ?? null;
    }

    return true;
}

function findParentTarget(
    nodes: Node<HierarchyNodeData>[],
    movingNode: Node<HierarchyNodeData>,
    records: MemberRecord[],
) {
    const movingWidth = movingNode.measured?.width ?? NODE_WIDTH;
    const movingHeight = movingNode.measured?.height ?? (movingNode.type === "manager" ? MANAGER_HEIGHT : MEMBER_HEIGHT);
    const centerX = movingNode.position.x + movingWidth / 2;
    const centerY = movingNode.position.y + movingHeight / 2;

    return nodes.find((candidate) => {
        if (candidate.id === movingNode.id) {
            return false;
        }

        if (!canAssignParent(records, movingNode.id, candidate.id)) {
            return false;
        }

        const candidateWidth = candidate.measured?.width ?? NODE_WIDTH;
        const candidateHeight = candidate.measured?.height ?? (candidate.type === "manager" ? MANAGER_HEIGHT : MEMBER_HEIGHT);
        const withinX = centerX >= candidate.position.x && centerX <= candidate.position.x + candidateWidth;
        const withinY = centerY >= candidate.position.y && centerY <= candidate.position.y + candidateHeight;

        return withinX && withinY;
    });
}


function nodeYForDepth(depth: number) {
    if (depth === 0) {
        return CANVAS_PADDING_Y;
    }

    return CANVAS_PADDING_Y + MANAGER_HEIGHT + MANAGER_TO_MEMBER_GAP + (depth - 1) * (MEMBER_HEIGHT + VERTICAL_GAP);
}

function layoutHierarchy(
    records: MemberRecord[],
    selectedId: string,
    onSelect: (nodeId: string) => void,
    onEdit: (nodeId: string) => void,
    onRemove: (nodeId: string) => void,
    onAddTeamMember: () => void,
    onBrainstorm: () => void,
    onReviewQueue: () => void,
) {
    const recordOrder = new Map(records.map((record, index) => [record.id, index] as const));
    const childrenByParent = new Map<string, MemberRecord[]>();

    records.forEach((record) => {
        if (!record.parentId) {
            return;
        }

        const siblings = childrenByParent.get(record.parentId) ?? [];
        siblings.push(record);
        childrenByParent.set(record.parentId, siblings);
    });

    childrenByParent.forEach((siblings) => {
        siblings.sort((left, right) => (recordOrder.get(left.id) ?? 0) - (recordOrder.get(right.id) ?? 0));
    });

    const subtreeWidthById = new Map<string, number>();

    const getSubtreeWidth = (nodeId: string): number => {
        const cached = subtreeWidthById.get(nodeId);
        if (cached) {
            return cached;
        }

        const children = childrenByParent.get(nodeId) ?? [];
        if (children.length === 0) {
            subtreeWidthById.set(nodeId, NODE_WIDTH);
            return NODE_WIDTH;
        }

        const childrenWidth = children.reduce((total, child, index) => {
            return total + getSubtreeWidth(child.id) + (index > 0 ? HORIZONTAL_GAP : 0);
        }, 0);

        const width = Math.max(NODE_WIDTH, childrenWidth);
        subtreeWidthById.set(nodeId, width);
        return width;
    };

    const positions = new Map<string, { x: number; y: number }>();

    const placeSubtree = (nodeId: string, left: number, depth: number) => {
        const subtreeWidth = subtreeWidthById.get(nodeId) ?? NODE_WIDTH;
        positions.set(nodeId, {
            x: left + (subtreeWidth - NODE_WIDTH) / 2,
            y: nodeYForDepth(depth),
        });

        const children = childrenByParent.get(nodeId) ?? [];
        if (children.length === 0) {
            return;
        }

        const childrenWidth = children.reduce((total, child, index) => {
            return total + (subtreeWidthById.get(child.id) ?? NODE_WIDTH) + (index > 0 ? HORIZONTAL_GAP : 0);
        }, 0);

        let cursor = left + (subtreeWidth - childrenWidth) / 2;
        children.forEach((child) => {
            const childWidth = subtreeWidthById.get(child.id) ?? NODE_WIDTH;
            placeSubtree(child.id, cursor, depth + 1);
            cursor += childWidth + HORIZONTAL_GAP;
        });
    };

    getSubtreeWidth(MANAGER_ID);
    placeSubtree(MANAGER_ID, CANVAS_PADDING_X, 0);

    const edges: Edge[] = records
        .filter((record) => record.parentId)
        .map((record) => ({
            id: `${record.parentId}-${record.id}`,
            source: record.parentId as string,
            target: record.id,
            type: "smoothstep",
            markerEnd: { type: MarkerType.ArrowClosed },
            style: { strokeWidth: 1.5, stroke: "#64748b" },
        }));

    const nodes: Node<HierarchyNodeData>[] = records.map((record) => {
        const model = modelById(record.primaryModelProfileId);
        const position = positions.get(record.id) ?? { x: CANVAS_PADDING_X, y: CANVAS_PADDING_Y };

        return {
            id: record.id,
            type: record.kind,
            position,
            selected: record.id === selectedId,
            draggable: record.kind === "member",
            data: {
                id: record.id,
                kind: record.kind,
                name: record.name,
                role: record.role,
                objective: record.objective,
                status: record.status,
                workload: record.currentWorkload,
                modelBadge: model.badge,
                costUsageUsd: record.costUsageUsd,
                tokenUsage: record.tokenUsage,
                isTemporary: record.isTemporary,
                reviewQueueCount: record.reviewQueueCount,
                teamBudgetUsd: record.teamBudgetUsd,
                onSelect,
                onEdit,
                onRemove,
                onAddTeamMember,
                onBrainstorm,
                onReviewQueue,
            },
        };
    });

    return { nodes, edges };
}

function ManagerNode({ data, selected }: NodeProps<Node<HierarchyNodeData>>) {
    return (
        <Paper
            elevation={0}
            onClick={() => data.onSelect(data.id)}
            sx={{
                width: NODE_WIDTH,
                minHeight: MANAGER_HEIGHT,
                p: 2,
                borderRadius: 4,
                cursor: "pointer",
                border: "1px solid",
                borderColor: selected ? "primary.main" : alpha("#0f172a", 0.12),
                bgcolor: alpha("#0a7f5a", 0.08),
                boxShadow: selected ? "0 0 0 3px rgba(14, 165, 233, 0.16)" : "0 18px 40px rgba(15, 23, 42, 0.08)",
            }}
        >
            <Handle type="source" position={Position.Bottom} style={{ background: "#0a7f5a", width: 10, height: 10 }} />
            <Stack spacing={1.25}>
                <Stack direction="row" justifyContent="space-between" spacing={1} alignItems="flex-start">
                    <Box>
                        <Typography variant="overline" sx={{ color: "success.dark", letterSpacing: "0.12em" }}>
                            Manager
                        </Typography>
                        <Typography variant="h6" sx={{ lineHeight: 1.1 }}>
                            {data.name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            {data.role}
                        </Typography>
                    </Box>
                    <Chip label={data.modelBadge} size="small" color="primary" variant="outlined" />
                </Stack>

                <Typography variant="body2" color="text.secondary">
                    {data.objective}
                </Typography>

                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Chip label={data.status.replace("_", " ")} size="small" color={statusColor(data.status)} />
                    <Chip label={`Review queue ${data.reviewQueueCount ?? 0}`} size="small" variant="outlined" />
                    <Chip label={`Team budget ${formatMoney(data.teamBudgetUsd ?? 0)}`} size="small" variant="outlined" />
                </Stack>

                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Button
                        size="small"
                        variant="contained"
                        startIcon={<AddIcon />}
                        onClick={(event) => {
                            event.stopPropagation();
                            data.onAddTeamMember();
                        }}
                    >
                        Add member
                    </Button>
                    <Button
                        size="small"
                        variant="outlined"
                        startIcon={<BrainstormIcon />}
                        onClick={(event) => {
                            event.stopPropagation();
                            data.onBrainstorm();
                        }}
                    >
                        Brainstorm
                    </Button>
                    <Button
                        size="small"
                        variant="text"
                        startIcon={<ReviewIcon />}
                        onClick={(event) => {
                            event.stopPropagation();
                            data.onReviewQueue();
                        }}
                    >
                        Review
                    </Button>
                </Stack>
            </Stack>
        </Paper>
    );
}

function TeamMemberNode({ data, selected }: NodeProps<Node<HierarchyNodeData>>) {
    return (
        <Paper
            elevation={0}
            onClick={() => data.onSelect(data.id)}
            sx={{
                width: NODE_WIDTH,
                minHeight: MEMBER_HEIGHT,
                p: 2,
                borderRadius: 4,
                cursor: "pointer",
                border: "1px solid",
                borderColor: selected ? "primary.main" : alpha("#0f172a", 0.12),
                bgcolor: "background.paper",
                boxShadow: selected ? "0 0 0 3px rgba(14, 165, 233, 0.16)" : "0 18px 40px rgba(15, 23, 42, 0.08)",
            }}
        >
            <Handle type="target" position={Position.Top} style={{ background: "#64748b", width: 10, height: 10 }} />
            <Handle type="source" position={Position.Bottom} style={{ background: "#2563eb", width: 10, height: 10 }} />
            <Stack spacing={1.25}>
                <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                    <Box>
                        <Typography variant="subtitle1" sx={{ lineHeight: 1.15 }}>
                            {data.name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            {data.role}
                        </Typography>
                    </Box>
                    <Stack spacing={0.75}>
                        <Button
                            size="small"
                            variant="outlined"
                            onClick={(event) => {
                                event.stopPropagation();
                                data.onEdit(data.id);
                            }}
                        >
                            Edit
                        </Button>
                        <Button
                            size="small"
                            variant="text"
                            color="error"
                            onClick={(event) => {
                                event.stopPropagation();
                                data.onRemove(data.id);
                            }}
                        >
                            Remove
                        </Button>
                    </Stack>
                </Stack>

                <Typography variant="body2" color="text.secondary">
                    {data.objective}
                </Typography>

                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    <Chip label={data.modelBadge} size="small" variant="outlined" />
                    <Chip label={data.status.replace("_", " ")} size="small" color={statusColor(data.status)} />
                    <Chip label={`Load ${data.workload}%`} size="small" variant="outlined" />
                    {data.isTemporary && <Chip label="Temporary" size="small" color="secondary" />}
                </Stack>

                <Typography variant="caption" color="text.secondary">
                    {`${data.tokenUsage.toLocaleString()} tokens • ${formatMoney(data.costUsageUsd)}`}
                </Typography>
            </Stack>
        </Paper>
    );
}

const nodeTypes = {
    manager: ManagerNode,
    member: TeamMemberNode,
};

function buildTemplateRecords(template: TeamTemplate): MemberRecord[] {
    const base = buildDefaultRecords();
    const manager = { ...base[0], ...template.manager };
    const members = template.members.map((member, index) => {
        const baseMember = base[index + 1];
        return {
            ...baseMember,
            id: `member-${index + 1}`,
            parentId: MANAGER_ID,
            name: baseMember.name,
            role: member.role,
            objective: member.objective,
            skillBindings: member.skillBindings,
            status: "idle" as AgentStatus,
            currentWorkload: 20 + index * 12,
        };
    });

    return [manager, ...members];
}

function metricCard(label: string, value: string, tone: string) {
    return (
        <Paper
            elevation={0}
            sx={{
                p: 1.5,
                borderRadius: 3,
                border: "1px solid",
                borderColor: "divider",
                bgcolor: alpha(tone, 0.08),
            }}
        >
            <Typography variant="caption" color="text.secondary">
                {label}
            </Typography>
            <Typography variant="h6">{value}</Typography>
        </Paper>
    );
}

function HierarchyBuilderInner() {
    const reactFlow = useReactFlow<Node<HierarchyNodeData>, Edge>();
    const [records, setRecords] = useState<MemberRecord[]>(buildDefaultRecords);
    const [selectedId, setSelectedId] = useState(MANAGER_ID);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [layerTab, setLayerTab] = useState<LayerTab>("organization");
    const [detailTab, setDetailTab] = useState<DetailTab>("active");
    const [draft, setDraft] = useState<MemberDraft | null>(null);
    const [nextMemberNumber, setNextMemberNumber] = useState(4);
    const [nextTaskNumber, setNextTaskNumber] = useState(10);



    const selectedRecord = useMemo(
        () => records.find((record) => record.id === selectedId) ?? records[0],
        [records, selectedId],
    );

    const selectNode = useCallback((nodeId: string) => {
        setSelectedId(nodeId);
    }, []);

    const openEditor = useCallback((nodeId: string) => {
        const record = records.find((item) => item.id === nodeId);
        if (!record) {
            return;
        }
        setSelectedId(nodeId);
        setDraft(createDraft(record));
        setEditingId(nodeId);
    }, [records]);

    const addConversationToMember = useCallback((memberId: string, author: string, text: string) => {
        setRecords((current) =>
            current.map((record) =>
                record.id === memberId
                    ? { ...record, conversationThread: [createConversation(author, text), ...record.conversationThread] }
                    : record,
            ),
        );
    }, []);

    const handleAddTeamMember = useCallback((temporary = false) => {
        const nextId = `member-${nextMemberNumber}`;

        const nextRecord: MemberRecord = {
            ...buildDefaultRecords()[1],
            id: nextId,
            parentId: MANAGER_ID,
            name: temporary ? `Specialist ${nextMemberNumber}` : `Team Member ${nextMemberNumber}`,
            role: temporary ? "Temporary Specialist Agent" : "New Team Member",
            objective: temporary ? "Handle overflow specialist work for current sprint." : "Configure new agent profile and assign scoped work.",
            status: "idle",
            currentWorkload: temporary ? 22 : 10,
            tokenUsage: 0,
            costUsageUsd: 0,
            errorCount: 0,
            validationFailureCount: 0,
            fallbackEvents: 0,
            activeTasks: [],
            completedTasks: [],
            conversationThread: [createConversation("System", temporary ? "Temporary specialist created from template." : "Team member added to manager layer.")],
            artifacts: [],
            runHistory: [],
            isTemporary: temporary,
            skillBindings: [
                createSkillBinding("new-skill-1", "custom capability", "Define new prompt instructions and tools.", ["query_graphql"], "StructuredOutput", ["validate structure"]),
            ],
        };

        setRecords((current) => [...current, nextRecord]);
        setSelectedId(nextId);
        setDraft(createDraft(nextRecord));
        setEditingId(nextId);
        setNextMemberNumber((current) => current + 1);
    }, [nextMemberNumber]);

    const addPermanentMember = useCallback(() => {
        handleAddTeamMember(false);
    }, [handleAddTeamMember]);

    const removeMember = useCallback((nodeId: string) => {
        setRecords((current) => {
            const target = current.find((record) => record.id === nodeId);
            if (!target || target.kind !== "member") {
                return current;
            }

            const fallbackParentId = target.parentId ?? MANAGER_ID;

            return current
                .filter((record) => record.id !== nodeId)
                .map((record) =>
                    record.parentId === nodeId ? { ...record, parentId: fallbackParentId } : record,
                );
        });

        // Only update selectedId if the deleted node was selected
        setSelectedId(prevId => prevId === nodeId ? MANAGER_ID : prevId);
        setEditingId((current) => (current === nodeId ? null : current));
    }, []);

    const cloneMember = useCallback((nodeId: string) => {
        const source = records.find((record) => record.id === nodeId);
        if (!source || source.kind !== "member") {
            return;
        }

        const nextId = `member-${nextMemberNumber}`;
        setNextMemberNumber((current) => current + 1);

        const clone: MemberRecord = {
            ...source,
            id: nextId,
            name: `${source.name} Clone`,
            currentWorkload: Math.max(0, source.currentWorkload - 15),
            status: "idle",
            activeTasks: [],
            completedTasks: [],
            conversationThread: [createConversation("System", `Cloned from ${source.name}.`)],
            artifacts: [],
            runHistory: [],
        };

        setRecords((current) => [...current, clone]);
        setSelectedId(nextId);
    }, [nextMemberNumber, records]);

    const applyTemplate = useCallback((templateId: string) => {
        const template = TEAM_TEMPLATES.find((item) => item.id === templateId);
        if (!template) {
            return;
        }

        setRecords(buildTemplateRecords(template));
        setSelectedId(MANAGER_ID);
        setNextMemberNumber(4);
        setLayerTab("organization");
        setDetailTab("active");
    }, []);

    const updateParent = useCallback((movingId: string, nextParentId: string) => {
        setRecords((current) => {
            if (!canAssignParent(current, movingId, nextParentId)) {
                return current;
            }

            return current.map((record) =>
                record.id === movingId ? { ...record, parentId: nextParentId } : record,
            );
        });
    }, []);

    const runBrainstorm = useCallback(() => {
        const directReports = records.filter((record) => record.parentId === MANAGER_ID);
        setRecords((current) =>
            current.map((record) => {
                if (record.id === MANAGER_ID) {
                    return {
                        ...record,
                        status: "running",
                        currentWorkload: Math.min(100, record.currentWorkload + 8),
                        conversationThread: [
                            createConversation("Alex Morgan", `Brainstorm started with ${directReports.map((item) => item.name).join(", ")}.`),
                            ...record.conversationThread,
                        ],
                    };
                }

                if (directReports.some((item) => item.id === record.id)) {
                    return {
                        ...record,
                        conversationThread: [
                            createConversation(record.name, "Contributing scoped ideas and constraints to brainstorm."),
                            ...record.conversationThread,
                        ],
                    };
                }

                return record;
            }),
        );
        setSelectedId(MANAGER_ID);
        setLayerTab("execution");
        setDetailTab("conversation");
    }, [records]);

    const focusReviewQueue = useCallback(() => {
        setSelectedId(MANAGER_ID);
        setLayerTab("execution");
        setDetailTab("active");
    }, []);

    const createManagerTask = useCallback(() => {
        const newTask = createTask(`task-${nextTaskNumber}`, "Define next project goal", MANAGER_ID, "active");

        setRecords((current) =>
            current.map((record) =>
                record.id === MANAGER_ID
                    ? {
                        ...record,
                        activeTasks: [newTask, ...record.activeTasks],
                        currentWorkload: Math.min(100, record.currentWorkload + 6),
                        conversationThread: [createConversation("System", "Manager created new project goal task."), ...record.conversationThread],
                    }
                    : record,
            ),
        );
        setLayerTab("execution");
        setDetailTab("active");
        setNextTaskNumber((current) => current + 1);
    }, [nextTaskNumber]);

    const decomposeManagerWork = useCallback(() => {
        const workers = records.filter((record) => record.kind === "member").slice(0, 3);
        setRecords((current) =>
            current.map((record, index) => {
                const worker = workers.find((item) => item.id === record.id);
                if (worker) {
                    const task = createTask(`task-${nextTaskNumber + index}`, `Subtask for ${worker.role}`, worker.id, "active");
                    return {
                        ...record,
                        activeTasks: [task, ...record.activeTasks],
                        currentWorkload: Math.min(100, record.currentWorkload + 10),
                        status: "running",
                    };
                }

                if (record.id === MANAGER_ID) {
                    return {
                        ...record,
                        conversationThread: [createConversation("System", "Manager decomposed goal into role-based subtasks."), ...record.conversationThread],
                    };
                }

                return record;
            }),
        );
        setNextTaskNumber((current) => current + workers.length);
        setLayerTab("execution");
        setDetailTab("active");
    }, [nextTaskNumber, records]);

    const requestRevision = useCallback(() => {
        if (selectedRecord.kind === "manager") {
            return;
        }

        setRecords((current) =>
            current.map((record) =>
                record.id === selectedRecord.id
                    ? {
                        ...record,
                        status: "needs_review",
                        activeTasks: record.activeTasks.map((task, index) => index === 0 ? { ...task, status: "needs_review", updatedAt: nowIso() } : task),
                        conversationThread: [createConversation("Manager", "Revision requested: tighten validation and evidence."), ...record.conversationThread],
                    }
                    : record,
            ),
        );
        setLayerTab("execution");
        setDetailTab("conversation");
    }, [selectedRecord]);

    const approveOutputs = useCallback(() => {
        if (selectedRecord.kind === "manager") {
            return;
        }

        setRecords((current) =>
            current.map((record) => {
                if (record.id !== selectedRecord.id || record.activeTasks.length === 0) {
                    return record;
                }

                const [approvedTask, ...remaining] = record.activeTasks;
                return {
                    ...record,
                    status: "idle",
                    activeTasks: remaining,
                    completedTasks: [{ ...approvedTask, status: "completed", updatedAt: nowIso() }, ...record.completedTasks],
                    conversationThread: [createConversation("Manager", `Approved output for "${approvedTask.title}".`), ...record.conversationThread],
                };
            }),
        );
        setLayerTab("execution");
        setDetailTab("completed");
    }, [selectedRecord]);

    const escalateBlocked = useCallback(() => {
        const blockedMembers = records.filter((record) => record.status === "blocked");
        if (blockedMembers.length === 0) {
            return;
        }

        const escalatedTask = createTask(`task-${nextTaskNumber}`, `Escalation: ${blockedMembers[0].role}`, MANAGER_ID, "active");

        setRecords((current) =>
            current.map((record) => {
                if (record.id === MANAGER_ID) {
                    return {
                        ...record,
                        activeTasks: [escalatedTask, ...record.activeTasks],
                        reviewQueueCount: (record.reviewQueueCount ?? 0) + blockedMembers.length,
                        conversationThread: [createConversation("System", `Escalated ${blockedMembers.length} blocked task(s) to manager.`), ...record.conversationThread],
                    };
                }
                return record.status === "blocked" ? { ...record, status: "needs_review" } : record;
            }),
        );
        setSelectedId(MANAGER_ID);
        setLayerTab("execution");
        setDetailTab("active");
        setNextTaskNumber((current) => current + 1);
    }, [nextTaskNumber, records]);

    const reassignTask = useCallback((taskId: string, targetId: string) => {
        if (targetId === selectedRecord.id) {
            return;
        }

        let reassignedTask: TaskItem | null = null;
        setRecords((current) =>
            current.map((record) => {
                if (record.id === selectedRecord.id) {
                    const remaining = record.activeTasks.filter((task) => {
                        if (task.id === taskId) {
                            reassignedTask = { ...task, assigneeId: targetId, updatedAt: nowIso() };
                            return false;
                        }
                        return true;
                    });
                    return { ...record, activeTasks: remaining, currentWorkload: Math.max(0, record.currentWorkload - 8) };
                }

                if (record.id === targetId && reassignedTask) {
                    return {
                        ...record,
                        activeTasks: [reassignedTask, ...record.activeTasks],
                        currentWorkload: Math.min(100, record.currentWorkload + 8),
                        conversationThread: [createConversation("Manager", `Task reassigned: ${reassignedTask.title}.`), ...record.conversationThread],
                    };
                }

                return record;
            }),
        );
    }, [selectedRecord.id]);

    const saveDraft = useCallback(() => {
        if (!editingId || !draft) {
            return;
        }

        setRecords((current) =>
            current.map((record) =>
                record.id === editingId
                    ? {
                        ...record,
                        name: draft.name.trim() || record.name,
                        role: draft.role.trim() || record.role,
                        objective: draft.objective.trim() || record.objective,
                        primaryModelProfileId: draft.primaryModelProfileId,
                        fallbackModelProfileId: draft.fallbackModelProfileId || undefined,
                        allowedModelProfileIds: parseCsv(draft.allowedModelProfileIds),
                        toolAccess: parseCsv(draft.toolAccess),
                        memoryPolicy: {
                            readAccess: parseCsv(draft.memoryReadAccess),
                            writeAccess: parseCsv(draft.memoryWriteAccess),
                            summarizationFrequency: draft.summarizationFrequency,
                            retentionPolicy: draft.retentionPolicy,
                        },
                        autonomyLevel: draft.autonomyLevel,
                        approvalPolicy: draft.approvalPolicy,
                        costBudgetUsd: Number(draft.costBudgetUsd) || record.costBudgetUsd,
                        currentWorkload: Number(draft.currentWorkload) || record.currentWorkload,
                        status: draft.status,
                        skillBindings: parseSkillBindings(draft.skillBindings),
                        evaluationGates: draft.evaluationGates,
                    }
                    : record,
            ),
        );
        setEditingId(null);
        setDraft(null);
    }, [draft, editingId]);

    const layoutedFlow = useMemo(
        () =>
            layoutHierarchy(
                records,
                selectedId,
                selectNode,
                openEditor,
                removeMember,
                addPermanentMember,
                runBrainstorm,
                focusReviewQueue,
            ),
        [addPermanentMember, focusReviewQueue, openEditor, records, removeMember, runBrainstorm, selectNode, selectedId],
    );

    const [nodes, setNodes, onNodesChange] = useNodesState<Node<HierarchyNodeData>>([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

    useEffect(() => {
        setNodes(layoutedFlow.nodes);
        setEdges(layoutedFlow.edges);
    }, [layoutedFlow, setNodes, setEdges]);

    // Fit view after layout changes, but with debounce to prevent excessive calls
    useEffect(() => {
        const timeout = window.setTimeout(() => {
            if (reactFlow && nodes.length > 0) {
                void reactFlow.fitView({ padding: 0.18, duration: 200 });
            }
        }, 100);

        return () => window.clearTimeout(timeout);
    }, [layoutedFlow.nodes, layoutedFlow.edges, reactFlow, nodes.length]);

    const handleNodeDragStop = useCallback((_event: unknown, node: Node<HierarchyNodeData>) => {
        if (node.id === MANAGER_ID) return;

        const nextParent = findParentTarget(
            reactFlow.getNodes() as Node<HierarchyNodeData>[],
            node,
            records,
        );

        const currentParentId = records.find((record) => record.id === node.id)?.parentId ?? null;

        if (nextParent && nextParent.id !== currentParentId) {
            updateParent(node.id, nextParent.id);
        }
    }, [reactFlow, records, updateParent]);


    const managerChildren = useMemo(
        () => records.filter((record) => record.parentId === MANAGER_ID && record.id !== MANAGER_ID),
        [records],
    );
    const selectedModel = modelById(selectedRecord.primaryModelProfileId);
    const availableAssignees = useMemo(
        () => records.filter((record) => record.id !== selectedRecord.id),
        [records, selectedRecord.id],
    );
    const evaluationGates = (selectedRecord as MemberRecord & { evaluationGates?: EvaluationGates }).evaluationGates ?? DEFAULT_EVALUATION_GATES;

    return (
        <>
            <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", xl: "minmax(0, 1.7fr) 430px" }, alignItems: "start" }}>
                <Stack spacing={2}>
                    <Paper sx={{ p: 2.5, borderRadius: 5 }}>
                        <Stack spacing={2}>
                            <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" spacing={1.5} alignItems={{ xs: "flex-start", md: "center" }}>
                                <Box>
                                    <Typography variant="h6">Multi-agent operating console</Typography>
                                    <Typography variant="body2" color="text.secondary">
                                        Organization layer defines structure. Agent layer defines identity, tools, models, and memory. Execution layer shows live work, runs, and approvals.
                                    </Typography>
                                </Box>
                                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                    <Button variant="contained" startIcon={<AddIcon />} onClick={() => handleAddTeamMember(false)}>
                                        Add Team Member
                                    </Button>
                                    <Button variant="outlined" startIcon={<BrainstormIcon />} onClick={runBrainstorm}>
                                        Brainstorm
                                    </Button>
                                </Stack>
                            </Stack>

                            <Box
                                sx={{
                                    height: 760,
                                    borderRadius: 5,
                                    overflow: "hidden",
                                    border: "1px solid",
                                    borderColor: "divider",
                                    bgcolor: alpha("#eff6ff", 0.5),
                                }}
                            >
                                <ReactFlow
                                    nodes={nodes}
                                    edges={edges}
                                    nodeTypes={nodeTypes}
                                    onNodesChange={onNodesChange}
                                    onEdgesChange={onEdgesChange}
                                    onNodeClick={(_, node) => setSelectedId(node.id)}
                                    onNodeDragStop={handleNodeDragStop}
                                    nodesDraggable
                                    nodesConnectable={false}
                                    elementsSelectable
                                    minZoom={0.45}
                                    maxZoom={1.6}
                                    proOptions={{ hideAttribution: true }}
                                >
                                    <Background color="#cbd5e1" gap={20} size={1.2} />

                                    <Controls showInteractive={false} />
                                </ReactFlow>
                            </Box>
                        </Stack>
                    </Paper>
                </Stack>

                <Stack spacing={2}>
                    <Paper sx={{ p: 2, borderRadius: 5 }}>
                        <Stack direction="row" spacing={1.5} alignItems="center">
                            <Avatar sx={{ bgcolor: selectedRecord.kind === "manager" ? "success.main" : "primary.main" }}>
                                <AgentIcon fontSize="small" />
                            </Avatar>
                            <Box sx={{ minWidth: 0, flex: 1 }}>
                                <Typography variant="subtitle1">{selectedRecord.name}</Typography>
                                <Typography variant="body2" color="text.secondary">
                                    {selectedRecord.role}
                                </Typography>
                            </Box>
                            <Chip label={selectedRecord.status.replace("_", " ")} color={statusColor(selectedRecord.status)} size="small" />
                        </Stack>

                        <Tabs
                            value={layerTab}
                            onChange={(_, value) => setLayerTab(value)}
                            variant="fullWidth"
                            sx={{ mt: 2 }}
                        >
                            <Tab value="organization" label="Organization" />
                            <Tab value="agent" label="Agent" />
                            <Tab value="execution" label="Execution" />
                        </Tabs>
                    </Paper>

                    {layerTab === "organization" && (
                        <Stack spacing={2}>
                            <Paper sx={{ p: 2, borderRadius: 5 }}>
                                <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
                                    Organization layer
                                </Typography>
                                <Stack spacing={1.25}>
                                    <Typography variant="body2" color="text.secondary">
                                        Members define reporting lines, ownership, and capacity. Drag any member onto another node to change hierarchy.
                                    </Typography>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                        <Chip label={`${managerChildren.length} direct reports`} size="small" variant="outlined" />
                                        <Chip label={`${records.filter((record) => record.isTemporary).length} temporary specialists`} size="small" variant="outlined" />
                                        <Chip label={`Selected load ${selectedRecord.currentWorkload}%`} size="small" variant="outlined" />
                                    </Stack>
                                    <LinearProgress variant="determinate" value={Math.min(100, selectedRecord.currentWorkload)} sx={{ borderRadius: 999, height: 8 }} />
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                        <Button size="small" startIcon={<AddIcon />} variant="contained" onClick={() => handleAddTeamMember(false)}>
                                            Add member
                                        </Button>
                                        <Button size="small" startIcon={<CloneIcon />} variant="outlined" disabled={selectedRecord.kind === "manager"} onClick={() => cloneMember(selectedRecord.id)}>
                                            Clone member
                                        </Button>
                                        <Button size="small" variant="outlined" onClick={() => handleAddTeamMember(true)}>
                                            Temporary specialist
                                        </Button>
                                        <Button size="small" variant="text" onClick={() => openEditor(selectedRecord.id)}>
                                            Edit profile
                                        </Button>
                                    </Stack>
                                </Stack>
                            </Paper>

                            <Paper sx={{ p: 2, borderRadius: 5 }}>
                                <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
                                    Team templates
                                </Typography>
                                <Stack spacing={1}>
                                    {TEAM_TEMPLATES.map((template) => (
                                        <Paper key={template.id} variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                            <Stack direction="row" justifyContent="space-between" spacing={1}>
                                                <Box>
                                                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                                        {template.name}
                                                    </Typography>
                                                    <Typography variant="caption" color="text.secondary">
                                                        {template.description}
                                                    </Typography>
                                                </Box>
                                                <Button size="small" onClick={() => applyTemplate(template.id)}>
                                                    Apply
                                                </Button>
                                            </Stack>
                                        </Paper>
                                    ))}
                                </Stack>
                            </Paper>
                        </Stack>
                    )}

                    {layerTab === "agent" && (
                        <Stack spacing={2}>
                            <Paper sx={{ p: 2, borderRadius: 5 }}>
                                <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
                                    Agent identity and operating profile
                                </Typography>
                                <Stack spacing={1.25}>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                        <Chip label={selectedModel.badge} size="small" color="primary" variant="outlined" />
                                        <Chip label={`Autonomy ${selectedRecord.autonomyLevel}`} size="small" variant="outlined" />
                                        <Chip label={`Approval ${selectedRecord.approvalPolicy.replace("_", " ")}`} size="small" variant="outlined" />
                                        <Chip label={`Budget ${formatMoney(selectedRecord.costBudgetUsd)}`} size="small" variant="outlined" />
                                    </Stack>
                                    <Typography variant="body2" color="text.secondary">
                                        {selectedRecord.objective}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        Primary model: {selectedModel.model} · provider {selectedModel.provider} · fallback {selectedRecord.fallbackModelProfileId ? modelById(selectedRecord.fallbackModelProfileId).badge : "none"}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        Allowed models: {selectedRecord.allowedModelProfileIds.map((id) => modelById(id).badge).join(", ")}
                                    </Typography>
                                    <Button size="small" variant="outlined" onClick={() => openEditor(selectedRecord.id)}>
                                        Edit operating profile
                                    </Button>
                                </Stack>
                            </Paper>

                            <Paper sx={{ p: 2, borderRadius: 5 }}>
                                <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
                                    Skill-to-tool mapping
                                </Typography>
                                <Stack spacing={1}>
                                    {selectedRecord.skillBindings.map((binding) => (
                                        <Paper key={binding.id} variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                                {binding.skill}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
                                                {binding.promptInstructions}
                                            </Typography>
                                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mb: 0.75 }}>
                                                {binding.allowedTools.map((tool) => (
                                                    <Chip key={`${binding.id}-${tool}`} label={tool} size="small" variant="outlined" />
                                                ))}
                                            </Stack>
                                            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                                                Output schema: {binding.outputSchema}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                                                Evaluation: {binding.evaluationChecks.join(", ")}
                                            </Typography>
                                        </Paper>
                                    ))}
                                </Stack>
                            </Paper>

                            <Paper sx={{ p: 2, borderRadius: 5 }}>
                                <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
                                    Memory and evaluation controls
                                </Typography>
                                <Stack spacing={1}>
                                    <Typography variant="caption" color="text.secondary">
                                        Read access: {selectedRecord.memoryPolicy.readAccess.join(", ")}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        Write access: {selectedRecord.memoryPolicy.writeAccess.join(", ")}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        Summarization: {selectedRecord.memoryPolicy.summarizationFrequency}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary">
                                        Retention: {selectedRecord.memoryPolicy.retentionPolicy}
                                    </Typography>
                                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                        {evaluationGates.validateStructure && <Chip label="Validate structure" size="small" variant="outlined" />}
                                        {evaluationGates.validateEvidence && <Chip label="Validate citations/evidence" size="small" variant="outlined" />}
                                        {evaluationGates.runTests && <Chip label="Run tests" size="small" variant="outlined" />}
                                        {evaluationGates.managerApproval && <Chip label="Manager approval" size="small" variant="outlined" />}
                                    </Stack>
                                </Stack>
                            </Paper>
                        </Stack>
                    )}

                    {layerTab === "execution" && (
                        <Stack spacing={2}>
                            <Paper sx={{ p: 2, borderRadius: 5 }}>
                                <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
                                    Execution layer
                                </Typography>
                                <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
                                    {metricCard("Last run", formatDateLabel(selectedRecord.lastRunTime), "#0ea5e9")}
                                    {metricCard("Cost usage", formatMoney(selectedRecord.costUsageUsd), "#22c55e")}
                                    {metricCard("Success rate", `${selectedRecord.successRate}%`, "#8b5cf6")}
                                    {metricCard("Avg latency", `${selectedRecord.averageLatencyMs} ms`, "#f97316")}
                                    {metricCard("Errors", String(selectedRecord.errorCount), "#ef4444")}
                                    {metricCard("Fallback events", String(selectedRecord.fallbackEvents), "#6366f1")}
                                </Box>
                            </Paper>

                            {selectedRecord.kind === "manager" ? (
                                <Paper sx={{ p: 2, borderRadius: 5 }}>
                                    <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
                                        Manager workflows
                                    </Typography>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                        <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={createManagerTask}>
                                            Create project goal
                                        </Button>
                                        <Button size="small" variant="outlined" startIcon={<DecomposeIcon />} onClick={decomposeManagerWork}>
                                            Decompose work
                                        </Button>
                                        <Button size="small" variant="outlined" startIcon={<BrainstormIcon />} onClick={runBrainstorm}>
                                            Brainstorm mode
                                        </Button>
                                        <Button size="small" variant="outlined" startIcon={<EscalateIcon />} onClick={escalateBlocked}>
                                            Escalate blocked
                                        </Button>
                                    </Stack>
                                </Paper>
                            ) : (
                                <Paper sx={{ p: 2, borderRadius: 5 }}>
                                    <Typography variant="subtitle2" sx={{ mb: 1.25 }}>
                                        Task controls
                                    </Typography>
                                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                        <Button size="small" variant="contained" startIcon={<ApproveIcon />} onClick={approveOutputs}>
                                            Approve output
                                        </Button>
                                        <Button size="small" variant="outlined" startIcon={<ReviewIcon />} onClick={requestRevision}>
                                            Request revision
                                        </Button>
                                        <Button size="small" variant="outlined" startIcon={<ChatIcon />} onClick={() => addConversationToMember(selectedRecord.id, "Manager", "Open chat requested from execution console.")}>
                                            Open chat
                                        </Button>
                                    </Stack>
                                </Paper>
                            )}

                            <Paper sx={{ p: 2, borderRadius: 5 }}>
                                <Tabs value={detailTab} onChange={(_, value) => setDetailTab(value)} variant="scrollable" scrollButtons="auto">
                                    <Tab value="active" label="Active tasks" />
                                    <Tab value="completed" label="Completed" />
                                    <Tab value="conversation" label="Conversation" />
                                    <Tab value="artifacts" label="Artifacts" />
                                    <Tab value="runs" label="Run history" />
                                    <Tab value="metrics" label="Metrics" />
                                </Tabs>

                                <Box sx={{ mt: 2 }}>
                                    {detailTab === "active" && (
                                        <Stack spacing={1}>
                                            {selectedRecord.activeTasks.length === 0 && (
                                                <Typography variant="body2" color="text.secondary">
                                                    No active tasks.
                                                </Typography>
                                            )}
                                            {selectedRecord.activeTasks.map((task) => (
                                                <Paper key={task.id} variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                                    <Stack direction="row" justifyContent="space-between" spacing={1} alignItems="center">
                                                        <Box>
                                                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                                                {task.title}
                                                            </Typography>
                                                            <Typography variant="caption" color="text.secondary">
                                                                {task.status.replace("_", " ")} · {formatDateLabel(task.updatedAt)}
                                                            </Typography>
                                                        </Box>
                                                        {selectedRecord.kind !== "manager" && availableAssignees.length > 0 && (
                                                            <TextField
                                                                select
                                                                size="small"
                                                                label="Reassign"
                                                                value=""
                                                                sx={{ minWidth: 150 }}
                                                                onChange={(event) => {
                                                                    if (event.target.value) {
                                                                        reassignTask(task.id, event.target.value);
                                                                    }
                                                                }}
                                                            >
                                                                <MenuItem value="">None</MenuItem>
                                                                {availableAssignees.map((assignee) => (
                                                                    <MenuItem key={assignee.id} value={assignee.id}>
                                                                        {assignee.name}
                                                                    </MenuItem>
                                                                ))}
                                                            </TextField>
                                                        )}
                                                    </Stack>
                                                </Paper>
                                            ))}
                                        </Stack>
                                    )}

                                    {detailTab === "completed" && (
                                        <Stack spacing={1}>
                                            {selectedRecord.completedTasks.length === 0 && (
                                                <Typography variant="body2" color="text.secondary">
                                                    No completed tasks yet.
                                                </Typography>
                                            )}
                                            {selectedRecord.completedTasks.map((task) => (
                                                <Paper key={task.id} variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                                        {task.title}
                                                    </Typography>
                                                    <Typography variant="caption" color="text.secondary">
                                                        Completed · {formatDateLabel(task.updatedAt)}
                                                    </Typography>
                                                </Paper>
                                            ))}
                                        </Stack>
                                    )}

                                    {detailTab === "conversation" && (
                                        <Stack spacing={1}>
                                            {selectedRecord.conversationThread.map((message) => (
                                                <Paper key={message.id} variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                                    <Typography variant="caption" color="text.secondary">
                                                        {message.author} · {formatDateLabel(message.timestamp)}
                                                    </Typography>
                                                    <Typography variant="body2">{message.text}</Typography>
                                                </Paper>
                                            ))}
                                        </Stack>
                                    )}

                                    {detailTab === "artifacts" && (
                                        <Stack spacing={1}>
                                            {selectedRecord.artifacts.length === 0 && (
                                                <Typography variant="body2" color="text.secondary">
                                                    No artifacts yet.
                                                </Typography>
                                            )}
                                            {selectedRecord.artifacts.map((artifact) => (
                                                <Paper key={artifact.id} variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                                        {artifact.name}
                                                    </Typography>
                                                    <Typography variant="caption" color="text.secondary">
                                                        {artifact.type} · {artifact.status}
                                                    </Typography>
                                                </Paper>
                                            ))}
                                        </Stack>
                                    )}

                                    {detailTab === "runs" && (
                                        <Stack spacing={1}>
                                            {selectedRecord.runHistory.length === 0 && (
                                                <Typography variant="body2" color="text.secondary">
                                                    No run history yet.
                                                </Typography>
                                            )}
                                            {selectedRecord.runHistory.map((run) => (
                                                <Paper key={run.id} variant="outlined" sx={{ p: 1.5, borderRadius: 3 }}>
                                                    <Stack direction="row" justifyContent="space-between" spacing={1}>
                                                        <Box>
                                                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                                                {run.id}
                                                            </Typography>
                                                            <Typography variant="caption" color="text.secondary">
                                                                {run.status.replace("_", " ")} · {run.latencyMs} ms · {run.tokenUsage.toLocaleString()} tokens · {formatMoney(run.costUsd)}
                                                            </Typography>
                                                        </Box>
                                                        {run.fallbackUsed && <Chip label="Fallback used" size="small" color="warning" />}
                                                    </Stack>
                                                    {run.errorMessage && (
                                                        <Typography variant="caption" color="error.main" sx={{ display: "block", mt: 0.75 }}>
                                                            {run.errorMessage}
                                                        </Typography>
                                                    )}
                                                </Paper>
                                            ))}
                                        </Stack>
                                    )}

                                    {detailTab === "metrics" && (
                                        <Stack spacing={1}>
                                            <Typography variant="body2" color="text.secondary">
                                                Tokens: {selectedRecord.tokenUsage.toLocaleString()}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                Cost usage: {formatMoney(selectedRecord.costUsageUsd)} of {formatMoney(selectedRecord.costBudgetUsd)}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                Success rate: {selectedRecord.successRate}%
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                Average latency: {selectedRecord.averageLatencyMs} ms
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                Error count: {selectedRecord.errorCount}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                Failed validations: {selectedRecord.validationFailureCount}
                                            </Typography>
                                            <Typography variant="body2" color="text.secondary">
                                                Model fallback events: {selectedRecord.fallbackEvents}
                                            </Typography>
                                        </Stack>
                                    )}
                                </Box>
                            </Paper>
                        </Stack>
                    )}
                </Stack>
            </Box>

            <Dialog open={Boolean(editingId && draft)} onClose={() => { setEditingId(null); setDraft(null); }} maxWidth="md" fullWidth>
                <DialogTitle>Edit agent control panel</DialogTitle>
                <DialogContent>
                    {draft && (
                        <Stack spacing={2} sx={{ mt: 1 }}>
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Name" value={draft.name} onChange={(event) => setDraft((current) => current ? { ...current, name: event.target.value } : current)} fullWidth />
                                <TextField label="Role" value={draft.role} onChange={(event) => setDraft((current) => current ? { ...current, role: event.target.value } : current)} fullWidth />
                            </Stack>
                            <TextField label="Agent objective" value={draft.objective} onChange={(event) => setDraft((current) => current ? { ...current, objective: event.target.value } : current)} multiline minRows={3} fullWidth />

                            <Divider />

                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField select label="Primary model profile" value={draft.primaryModelProfileId} onChange={(event) => setDraft((current) => current ? { ...current, primaryModelProfileId: event.target.value } : current)} fullWidth>
                                    {MODEL_PROFILES.map((profile) => (
                                        <MenuItem key={profile.id} value={profile.id}>
                                            {profile.badge} · {profile.model}
                                        </MenuItem>
                                    ))}
                                </TextField>
                                <TextField select label="Fallback model profile" value={draft.fallbackModelProfileId} onChange={(event) => setDraft((current) => current ? { ...current, fallbackModelProfileId: event.target.value } : current)} fullWidth>
                                    <MenuItem value="">None</MenuItem>
                                    {MODEL_PROFILES.map((profile) => (
                                        <MenuItem key={`fallback-${profile.id}`} value={profile.id}>
                                            {profile.badge}
                                        </MenuItem>
                                    ))}
                                </TextField>
                            </Stack>

                            <TextField
                                label="Allowed model profile ids"
                                helperText="Comma-separated. Supports primary, fallback, and future routing."
                                value={draft.allowedModelProfileIds}
                                onChange={(event) => setDraft((current) => current ? { ...current, allowedModelProfileIds: event.target.value } : current)}
                                fullWidth
                            />
                            <TextField label="Tool access" helperText="Comma-separated tool registry access." value={draft.toolAccess} onChange={(event) => setDraft((current) => current ? { ...current, toolAccess: event.target.value } : current)} fullWidth />

                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Autonomy level" select value={draft.autonomyLevel} onChange={(event) => setDraft((current) => current ? { ...current, autonomyLevel: event.target.value as MemberDraft["autonomyLevel"] } : current)} fullWidth>
                                    <MenuItem value="low">Low</MenuItem>
                                    <MenuItem value="medium">Medium</MenuItem>
                                    <MenuItem value="high">High</MenuItem>
                                </TextField>
                                <TextField label="Approval policy" select value={draft.approvalPolicy} onChange={(event) => setDraft((current) => current ? { ...current, approvalPolicy: event.target.value as MemberDraft["approvalPolicy"] } : current)} fullWidth>
                                    <MenuItem value="auto">Auto</MenuItem>
                                    <MenuItem value="manager_review">Manager review</MenuItem>
                                    <MenuItem value="strict">Strict</MenuItem>
                                </TextField>
                                <TextField label="Status" select value={draft.status} onChange={(event) => setDraft((current) => current ? { ...current, status: event.target.value as AgentStatus } : current)} fullWidth>
                                    <MenuItem value="idle">Idle</MenuItem>
                                    <MenuItem value="running">Running</MenuItem>
                                    <MenuItem value="blocked">Blocked</MenuItem>
                                    <MenuItem value="needs_review">Needs review</MenuItem>
                                </TextField>
                            </Stack>

                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Cost budget (USD)" value={draft.costBudgetUsd} onChange={(event) => setDraft((current) => current ? { ...current, costBudgetUsd: event.target.value } : current)} fullWidth />
                                <TextField label="Current workload %" value={draft.currentWorkload} onChange={(event) => setDraft((current) => current ? { ...current, currentWorkload: event.target.value } : current)} fullWidth />
                            </Stack>

                            <Divider />

                            <TextField label="Memory read access" helperText="Comma-separated scopes: global/company memory, project memory, task memory, private scratch memory, shared team memory." value={draft.memoryReadAccess} onChange={(event) => setDraft((current) => current ? { ...current, memoryReadAccess: event.target.value } : current)} fullWidth />
                            <TextField label="Memory write access" value={draft.memoryWriteAccess} onChange={(event) => setDraft((current) => current ? { ...current, memoryWriteAccess: event.target.value } : current)} fullWidth />
                            <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                                <TextField label="Summarization frequency" value={draft.summarizationFrequency} onChange={(event) => setDraft((current) => current ? { ...current, summarizationFrequency: event.target.value } : current)} fullWidth />
                                <TextField label="Retention policy" value={draft.retentionPolicy} onChange={(event) => setDraft((current) => current ? { ...current, retentionPolicy: event.target.value } : current)} fullWidth />
                            </Stack>

                            <Divider />

                            <TextField
                                label="Skill to tool mapping"
                                helperText="One line per skill: skill | tool1, tool2 | output schema | evaluation1, evaluation2 | prompt instructions"
                                value={draft.skillBindings}
                                onChange={(event) => setDraft((current) => current ? { ...current, skillBindings: event.target.value } : current)}
                                multiline
                                minRows={7}
                                fullWidth
                            />

                            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                <Chip
                                    clickable
                                    color={draft.evaluationGates.validateStructure ? "primary" : "default"}
                                    variant={draft.evaluationGates.validateStructure ? "filled" : "outlined"}
                                    label="Validate structure"
                                    onClick={() => setDraft((current) => current ? { ...current, evaluationGates: { ...current.evaluationGates, validateStructure: !current.evaluationGates.validateStructure } } : current)}
                                />
                                <Chip
                                    clickable
                                    color={draft.evaluationGates.validateEvidence ? "primary" : "default"}
                                    variant={draft.evaluationGates.validateEvidence ? "filled" : "outlined"}
                                    label="Validate citations/evidence"
                                    onClick={() => setDraft((current) => current ? { ...current, evaluationGates: { ...current.evaluationGates, validateEvidence: !current.evaluationGates.validateEvidence } } : current)}
                                />
                                <Chip
                                    clickable
                                    color={draft.evaluationGates.runTests ? "primary" : "default"}
                                    variant={draft.evaluationGates.runTests ? "filled" : "outlined"}
                                    label="Run tests"
                                    onClick={() => setDraft((current) => current ? { ...current, evaluationGates: { ...current.evaluationGates, runTests: !current.evaluationGates.runTests } } : current)}
                                />
                                <Chip
                                    clickable
                                    color={draft.evaluationGates.managerApproval ? "primary" : "default"}
                                    variant={draft.evaluationGates.managerApproval ? "filled" : "outlined"}
                                    label="Manager approval"
                                    onClick={() => setDraft((current) => current ? { ...current, evaluationGates: { ...current.evaluationGates, managerApproval: !current.evaluationGates.managerApproval } } : current)}
                                />
                            </Stack>
                        </Stack>
                    )}
                </DialogContent>
                <DialogActions sx={{ px: 3, pb: 3 }}>
                    {editingId && editingId !== MANAGER_ID && (
                        <Button color="error" onClick={() => removeMember(editingId)}>
                            Remove
                        </Button>
                    )}
                    <Box sx={{ flex: 1 }} />
                    <Button onClick={() => { setEditingId(null); setDraft(null); }}>Cancel</Button>
                    <Button variant="contained" onClick={saveDraft}>
                        Save
                    </Button>
                </DialogActions>
            </Dialog>
        </>
    );
}

export function HierarchyBuilderCanvas() {
    return (
        <ReactFlowProvider>
            <HierarchyBuilderInner />
        </ReactFlowProvider>
    );
}