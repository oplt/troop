import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tmp = path.join(root, ".understand-anything/tmp");
const intermediate = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-extract-results-4.json"), "utf8"));
const batches = JSON.parse(fs.readFileSync(path.join(intermediate, "batches.json"), "utf8"));
const batch = batches.batches.find((item) => item.batchIndex === 4);
if (!batch) throw new Error("Batch 4 not found");

const meta = {
  "backend/api/deps/orchestration.py": ["Builds request-scoped orchestration application services and focused domain-service dependencies over the active database session.", ["api-dependency", "orchestration", "fastapi", "factory"]],
  "backend/app/agents/application.py": ["Coordinates planned agent runs, including task-derived planning, execution snapshots, approval gates, and run activation.", ["service", "agent-runtime", "planning", "approvals"]],
  "backend/app/agents/logging.py": ["Emits normalized structured log events for agent operations with contextual metadata.", ["logging", "agents", "observability", "utility"]],
  "backend/app/agents/router.py": ["Exposes agent profile, task, run, tool, workspace-artifact, and memory APIs through authenticated FastAPI routes.", ["api-handler", "fastapi", "agents", "memory"]],
  "backend/app/agents/tools/__init__.py": ["Publishes the agent tool registry's lookup and listing functions as the tools package API.", ["barrel", "tools", "agents", "entry-point"]],
  "backend/app/agents/tools/registry.py": ["Defines the built-in agent tool catalog with schemas, risk levels, approval requirements, and lookup helpers.", ["tool-registry", "agents", "security", "configuration"]],
  "backend/app/agents/workspace.py": ["Creates isolated run workspaces, validates paths, lists generated files, and persists run artifacts safely.", ["workspace", "filesystem", "security", "artifacts"]],
  "backend/db/base.py": ["Defines the shared SQLAlchemy declarative base inherited by all persistence models.", ["database", "sqlalchemy", "data-model", "foundation"]],
  "backend/modules/audit/models.py": ["Defines the SQLAlchemy audit-log record used to retain actor, action, resource, client, and metadata history.", ["data-model", "sqlalchemy", "audit", "database"]],
  "backend/modules/calendar/models.py": ["Defines persisted user calendar entries with schedule, type, descriptive, and audit fields.", ["data-model", "sqlalchemy", "calendar", "database"]],
  "backend/modules/calendar/repository.py": ["Queries and mutates calendar entries and collects due orchestration tasks and milestones for a user.", ["repository", "database", "calendar", "sqlalchemy"]],
  "backend/modules/calendar/schemas.py": ["Defines validated create, update, and response contracts for combined calendar and planner items.", ["data-model", "pydantic", "calendar", "validation"]],
  "backend/modules/calendar/service.py": ["Combines persisted calendar entries with orchestration tasks and milestones and implements planner CRUD behavior.", ["service", "calendar", "orchestration", "business-logic"]],
  "backend/modules/companies/models.py": ["Defines the persisted company workspace owned by a user, including its slug, brief, and settings.", ["data-model", "sqlalchemy", "company", "database"]],
  "backend/modules/companies/repository.py": ["Provides company creation, retrieval, owner-scoped listing, default lookup, and slug queries.", ["repository", "database", "company", "sqlalchemy"]],
  "backend/modules/companies/service.py": ["Implements company creation, default provisioning, updates, authorization checks, and normalized slugs.", ["service", "company", "authorization", "business-logic"]],
  "backend/modules/github/__init__.py": ["Publishes the GitHub integration router as the module's external API.", ["barrel", "github", "integration", "entry-point"]],
  "backend/modules/github/models.py": ["Defines persistence models for GitHub installations, repositories, issue links, synchronization events, entity mappings, and outbound deduplication.", ["data-model", "sqlalchemy", "github", "integration"]],
  "backend/modules/github/repository.py": ["Provides GitHub integration persistence operations for connections, repositories, issue links, sync events, mappings, and deduplication records.", ["repository", "database", "github", "integration"]],
  "backend/modules/github/service.py": ["Implements GitHub App authentication, repository and issue synchronization, webhooks, approval-gated writes, pull requests, and run-result publishing.", ["service", "github", "webhooks", "orchestration"]],
  "backend/modules/memory/entry_types.py": ["Defines supported semantic-memory entry types and validates their type-specific metadata contracts.", ["memory", "validation", "type-definition", "metadata"]],
  "backend/modules/memory/models.py": ["Defines persistence models for project documents, vector chunks, agent and semantic memory, playbooks, ingest jobs, episodic archives, and knowledge links.", ["data-model", "sqlalchemy", "memory", "vector-search"]],
  "backend/modules/memory/repository.py": ["Provides persistence and vector-retrieval operations across documents, semantic and episodic memory, playbooks, ingest jobs, and knowledge-graph relationships.", ["repository", "database", "memory", "vector-search"]],
  "backend/modules/notifications/models.py": ["Defines user notifications and per-user delivery preference persistence models.", ["data-model", "sqlalchemy", "notifications", "database"]],
  "backend/modules/notifications/repository.py": ["Creates and queries notifications, marks them read, and manages user notification preferences.", ["repository", "database", "notifications", "sqlalchemy"]],
  "backend/modules/orchestration/_helpers.py": ["Provides shared orchestration helpers for namespaces, priorities, provider aliases, text chunking, similarity, query limits, and background jobs.", ["utility", "orchestration", "vector-search", "validation"]],
  "backend/modules/orchestration/constants.py": ["Centralizes orchestration status sets, execution modes, priority values, relation types, and API limit defaults.", ["constants", "orchestration", "configuration", "type-definition"]],
  "backend/modules/orchestration/control_plane.py": ["Implements the hierarchical orchestration control plane for team members, tasks, approvals, brainstorms, runs, events, and runtime snapshots.", ["service", "orchestration", "control-plane", "event-stream"]],
};

function human(name) {
  return name.replace(/^_+/, "").replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/_/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
}
function complexity(start, end) {
  const lines = end - start + 1;
  return lines > 200 ? "complex" : lines >= 50 ? "moderate" : "simple";
}
function fileComplexity(result) {
  return result.nonEmptyLines > 200 ? "complex" : result.nonEmptyLines >= 50 ? "moderate" : "simple";
}
function functionTags(filePath) {
  if (filePath.includes("/router.py")) return ["api-handler", "fastapi", "endpoint"];
  if (filePath.includes("/deps/")) return ["api-dependency", "fastapi", "factory"];
  if (filePath.includes("/workspace.py")) return ["workspace", "filesystem", "utility"];
  if (filePath.includes("/entry_types.py")) return ["memory", "validation", "utility"];
  if (filePath.includes("/control_plane.py")) return ["orchestration", "control-plane", "utility"];
  if (filePath.includes("/_helpers.py")) return ["orchestration", "utility", "validation"];
  if (filePath.includes("/tools/")) return ["tool-registry", "agents", "utility"];
  if (filePath.includes("/logging.py")) return ["logging", "agents", "observability"];
  if (filePath.includes("/companies/service.py")) return ["company", "service", "utility"];
  return ["backend", "python", "utility"];
}
function classTags(filePath, name) {
  if (filePath.includes("/models.py") || name === "Base") return ["data-model", "sqlalchemy", "database"];
  if (filePath.includes("/schemas.py") || filePath.endsWith("agents/router.py") && /(Payload|Response|Create|Search|Update)$/.test(name)) return ["data-model", "pydantic", "validation"];
  if (name.endsWith("Repository") || name.endsWith("RepositoryMixin")) return ["repository", "database", "data-access"];
  if (name.endsWith("Service") || name.endsWith("ServiceMixin")) return ["service", "business-logic", "orchestration"];
  if (name === "ToolSpec") return ["tool-registry", "data-model", "security"];
  if (name === "BlockedExecution") return ["error-handling", "orchestration", "control-flow"];
  if (name === "ControlPlaneEvent") return ["event", "control-plane", "data-model"];
  if (name === "ControlPlanePubSub") return ["event-stream", "pub-sub", "control-plane"];
  return ["backend", "python", "class"];
}
function functionSummary(filePath, name) {
  const label = human(name);
  if (filePath.includes("/deps/")) return `Constructs the ${label} dependency from the request-scoped database session.`;
  if (filePath.includes("/router.py")) {
    if (name.startsWith("list_")) return `Handles the API operation that lists ${human(name.slice(5))}.`;
    if (name.startsWith("get_")) return `Handles the API operation that retrieves ${human(name.slice(4))}.`;
    if (name.startsWith("create_")) return `Handles the API operation that creates ${human(name.slice(7))}.`;
    if (name.startsWith("update_")) return `Handles the API operation that updates ${human(name.slice(7))}.`;
    if (name.startsWith("delete_")) return `Handles the API operation that deletes ${human(name.slice(7))}.`;
    if (name.startsWith("cancel_")) return `Handles the API operation that cancels ${human(name.slice(7))}.`;
    if (name.startsWith("approve_")) return `Handles the API operation that approves ${human(name.slice(8))}.`;
    if (name.startsWith("import_")) return `Handles the API operation that imports ${human(name.slice(7))}.`;
    if (name.startsWith("search_")) return `Handles the API operation that searches ${human(name.slice(7))}.`;
    return `Implements the ${label} API transformation or operation.`;
  }
  if (filePath.includes("/workspace.py")) return `Implements ${label} behavior for isolated agent-run workspaces and artifacts.`;
  if (filePath.includes("/entry_types.py")) return `Validates ${label} against the semantic-memory contract.`;
  if (filePath.includes("/_helpers.py")) return `Implements the shared ${label} orchestration helper.`;
  if (filePath.includes("/control_plane.py")) return `Implements ${label} behavior for the orchestration control plane.`;
  if (filePath.includes("/tools/")) return `Provides ${label} access to the built-in agent tool registry.`;
  if (filePath.includes("/logging.py")) return `Emits the ${label} structured agent log event.`;
  if (name === "_normalize_slug") return "Normalizes company names or supplied slugs into stable URL-safe identifiers.";
  return `Implements ${label} for the backend application.`;
}

const specialClasses = {
  AgentRunApplicationService: "Coordinates agent-run planning and approval transitions while recording immutable execution snapshots.",
  ToolSpec: "Immutable specification of an agent tool's schemas, availability, risk level, and approval requirement.",
  Base: "Shared SQLAlchemy declarative superclass for mapped database entities.",
  CalendarRepository: "Data-access layer for calendar entries and due orchestration planning records.",
  CalendarService: "Application service that merges calendar entries, tasks, and milestones into a unified planner view.",
  CompanyRepository: "Data-access layer for owner-scoped company workspaces and slug lookup.",
  CompanyService: "Application service enforcing company ownership, defaults, slug normalization, and update rules.",
  GithubRepositoryMixin: "Repository mixin implementing persistence for GitHub connections, repositories, links, events, mappings, and deduplication.",
  OrchestrationGithubServiceMixin: "Large orchestration service mixin implementing GitHub App, webhook, synchronization, approval, issue, and pull-request workflows.",
  MemoryRepositoryMixin: "Repository mixin implementing document, vector, semantic, episodic, procedural, ingest, and knowledge-link persistence operations.",
  NotificationsRepository: "Data-access layer for notifications, read state, and delivery preferences.",
  BlockedExecution: "Domain exception signaling that orchestration execution cannot proceed under current constraints.",
  ControlPlaneEvent: "Structured event emitted when hierarchical control-plane state changes.",
  ControlPlanePubSub: "In-process asynchronous publisher and subscriber for control-plane events.",
  HierarchyControlPlaneService: "Coordinates hierarchy-aware members, tasks, runs, approvals, brainstorms, artifacts, and live control-plane snapshots.",
};
function classSummary(filePath, name) {
  if (specialClasses[name]) return specialClasses[name];
  if (filePath.includes("/models.py")) return `SQLAlchemy persistence model representing ${human(name)} records.`;
  if (filePath.includes("/schemas.py") || filePath.endsWith("agents/router.py")) return `Pydantic API schema representing ${human(name)} data.`;
  if (name.endsWith("Repository")) return `Data-access layer for ${human(name.replace(/Repository$/, ""))} persistence operations.`;
  if (name.endsWith("Service")) return `Coordinates ${human(name.replace(/Service$/, ""))} business operations.`;
  return `Implements the ${human(name)} backend component.`;
}

const nodes = [];
const edges = [];
const ids = new Set();
const edgeKeys = new Set();
const symbolsByFile = new Map();
function addNode(node) {
  if (ids.has(node.id)) throw new Error(`Duplicate node ${node.id}`);
  ids.add(node.id);
  nodes.push(node);
}
function addEdge(edge) {
  if (edge.source === edge.target) return;
  const key = `${edge.source}\0${edge.target}\0${edge.type}`;
  if (edgeKeys.has(key)) return;
  edgeKeys.add(key);
  edges.push(edge);
}

for (const result of extraction.results) {
  const [summary, tags] = meta[result.path];
  const fileId = `file:${result.path}`;
  addNode({ id: fileId, type: "file", name: path.basename(result.path), filePath: result.path, summary, tags, complexity: fileComplexity(result) });
  const exports = new Set((result.exports ?? []).map((item) => item.name));
  const fileSymbols = new Map();
  for (const fn of result.functions ?? []) {
    const length = fn.endLine - fn.startLine + 1;
    if (!exports.has(fn.name) && length < 10) continue;
    const id = `function:${result.path}:${fn.name}`;
    addNode({ id, type: "function", name: fn.name, filePath: result.path, lineRange: [fn.startLine, fn.endLine], summary: functionSummary(result.path, fn.name), tags: functionTags(result.path), complexity: complexity(fn.startLine, fn.endLine) });
    fileSymbols.set(fn.name, id);
    addEdge({ source: fileId, target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(fn.name)) addEdge({ source: fileId, target: id, type: "exports", direction: "forward", weight: 0.8 });
  }
  for (const cls of result.classes ?? []) {
    const length = cls.endLine - cls.startLine + 1;
    if (!exports.has(cls.name) && (cls.methods?.length ?? 0) < 2 && length < 20) continue;
    const id = `class:${result.path}:${cls.name}`;
    addNode({ id, type: "class", name: cls.name, filePath: result.path, lineRange: [cls.startLine, cls.endLine], summary: classSummary(result.path, cls.name), tags: classTags(result.path, cls.name), complexity: complexity(cls.startLine, cls.endLine) });
    fileSymbols.set(cls.name, id);
    for (const method of cls.methods ?? []) fileSymbols.set(method, id);
    addEdge({ source: fileId, target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(cls.name)) addEdge({ source: fileId, target: id, type: "exports", direction: "forward", weight: 0.8 });
  }
  symbolsByFile.set(result.path, fileSymbols);
}

for (const [sourcePath, targetPaths] of Object.entries(batch.batchImportData)) {
  for (const targetPath of targetPaths) {
    addEdge({ source: `file:${sourcePath}`, target: `file:${targetPath}`, type: "imports", direction: "forward", weight: 0.7 });
  }
}

for (const result of extraction.results) {
  const neighbors = batch.neighborMap[result.path] ?? [];
  const crossSymbols = new Map();
  for (const neighbor of neighbors) {
    for (const symbol of neighbor.symbols ?? []) if (!crossSymbols.has(symbol)) crossSymbols.set(symbol, neighbor.path);
    if (neighbor.path.includes("/tests/") || path.basename(neighbor.path).startsWith("test_")) {
      addEdge({ source: `file:${result.path}`, target: `file:${neighbor.path}`, type: "tested_by", direction: "forward", weight: 0.5 });
    }
  }
  const localSymbols = symbolsByFile.get(result.path) ?? new Map();
  for (const call of result.callGraph ?? []) {
    const targetPath = crossSymbols.get(call.callee);
    if (!targetPath) continue;
    const prefix = /^[A-Z]/.test(call.callee) ? "class" : "function";
    addEdge({ source: localSymbols.get(call.caller) ?? `file:${result.path}`, target: `${prefix}:${targetPath}:${call.callee}`, type: "calls", direction: "forward", weight: 0.8 });
  }
}

const partCount = Math.ceil(Math.max(nodes.length / 60, edges.length / 120));
const files = [...batch.files].sort((left, right) => left.path.localeCompare(right.path));
const chunkSize = Math.ceil(files.length / partCount);
const outputs = [];
for (let index = 0; index < partCount; index += 1) {
  const filePaths = new Set(files.slice(index * chunkSize, (index + 1) * chunkSize).map((item) => item.path));
  if (!filePaths.size) continue;
  const partNodes = nodes.filter((node) => filePaths.has(node.filePath));
  const partIds = new Set(partNodes.map((node) => node.id));
  const partEdges = edges.filter((edge) => partIds.has(edge.source));
  const outputPath = path.join(intermediate, `batch-4-part-${index + 1}.json`);
  fs.writeFileSync(outputPath, `${JSON.stringify({ nodes: partNodes, edges: partEdges }, null, 2)}\n`);
  outputs.push({ outputPath, nodes: partNodes.length, edges: partEdges.length });
}

const allowedFiles = new Set([...Object.keys(batch.batchImportData), ...Object.values(batch.batchImportData).flat(), ...Object.keys(batch.neighborMap), ...Object.values(batch.neighborMap).flatMap((items) => items.map((item) => item.path))]);
const neighborSymbols = new Map();
for (const items of Object.values(batch.neighborMap)) for (const neighbor of items) neighborSymbols.set(neighbor.path, new Set(neighbor.symbols ?? []));
for (const output of outputs) {
  const fragment = JSON.parse(fs.readFileSync(output.outputPath, "utf8"));
  const partIds = new Set(fragment.nodes.map((node) => node.id));
  for (const edge of fragment.edges) {
    if (!partIds.has(edge.source)) throw new Error(`Missing source ${edge.source}`);
    if (partIds.has(edge.target)) continue;
    const fileMatch = /^file:(.+)$/.exec(edge.target);
    if (fileMatch && allowedFiles.has(fileMatch[1])) continue;
    const symbolMatch = /^(?:function|class):(.+):([^:]+)$/.exec(edge.target);
    if (symbolMatch && neighborSymbols.get(symbolMatch[1])?.has(symbolMatch[2])) continue;
    throw new Error(`Unvalidated target ${edge.target}`);
  }
}

process.stdout.write(JSON.stringify({ outputs, nodeCount: nodes.length, edgeCount: edges.length, filesSkipped: extraction.filesSkipped ?? [] }));
