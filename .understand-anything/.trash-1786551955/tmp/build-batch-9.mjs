import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tmp = path.join(root, ".understand-anything/tmp");
const intermediate = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-extract-results-9.json"), "utf8"));
const input = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-analyzer-input-9.json"), "utf8"));
const batches = JSON.parse(fs.readFileSync(path.join(intermediate, "batches.json"), "utf8"));
const batch = batches.batches.find((item) => item.batchIndex === 9);
if (!batch) throw new Error("Batch 9 not found");

const summaries = {
  "frontend/src/pages/BrainstormsPage.tsx": "Presents brainstorming sessions and a creation workflow with participant selection, guardrails, execution modes, and output controls.",
  "frontend/src/pages/CalendarPage.tsx": "Hosts the dashboard calendar in a dedicated page shell for schedule-focused navigation.",
  "frontend/src/pages/CompaniesPage.tsx": "Lists companies and provides create and edit workflows for names, slugs, briefs, and company settings.",
  "frontend/src/pages/CompanyMemoryPage.tsx": "Displays company-scoped semantic memory with entry metadata, provenance, confidence, and formatted timestamps.",
  "frontend/src/pages/CostAnalyticsPage.tsx": "Visualizes orchestration spend, token usage, budgets, and provider or model cost breakdowns.",
  "frontend/src/pages/DashboardPage.test.tsx": "Verifies dashboard summary rendering, notification behavior, and degraded API-state handling with mocked orchestration data.",
  "frontend/src/pages/DashboardPage.tsx": "Builds the operational dashboard from run, task, approval, notification, portfolio, cost, and calendar data with resilient loading and error states.",
  "frontend/src/pages/ExecutionInsightsPage.tsx": "Displays execution rollups, outcome trends, provider health, tool failures, and operational performance metrics.",
  "frontend/src/pages/GithubSyncPage.tsx": "Manages GitHub connections, repository synchronization, issue links, webhook activity, approvals, and live sync state.",
  "frontend/src/pages/ModelSettingsPage.tsx": "Frames model provider configuration and delegates provider management to the shared settings panel.",
  "frontend/src/pages/NotificationsPage.tsx": "Lists notification inbox items, unread statistics, mark-read actions, and delivery preference controls.",
  "frontend/src/pages/OrchestrationPortfolioPage.tsx": "Presents cross-project health, execution policy, dependencies, capacity, alerts, and live portfolio control-plane state.",
  "frontend/src/pages/OrchestrationProjectDetailPage.test.tsx": "Exercises project-detail rendering and task workflow interactions against mocked orchestration APIs.",
  "frontend/src/pages/OrchestrationProjectDetailPage.tsx": "Validates the project route parameter and lazily loads the large project-detail workspace behind a page-level fallback.",
  "frontend/src/pages/OrchestrationProjectsPage.tsx": "Manages orchestration projects, company assignment, local repository configuration, bootstrap flows, and project navigation.",
  "frontend/src/pages/PlatformPage.tsx": "Provides platform administration for modules, plans, subscriptions, API keys, webhooks, feature flags, configuration, and email templates.",
  "frontend/src/pages/ProfilePage.tsx": "Combines personal profile editing, avatar management, security and MFA controls, session management, and notification preferences.",
  "frontend/src/pages/ProviderSettingsPanel.tsx": "Manages provider credentials, local runtimes, model discovery, defaults, request timeouts, health checks, and provider comparisons.",
  "frontend/src/pages/RunInspectorPage.tsx": "Provides a deep run-debugging workspace with event timelines, tool-call pairing, conversations, traces, workflow topology, costs, and live SSE updates.",
  "frontend/src/pages/SemanticMemoryPage.tsx": "Manages semantic memory entries, search, conflicts, links, knowledge edges, episodic archives, procedural playbooks, and memory settings.",
  "frontend/src/pages/WorkflowTemplatesPage.tsx": "Lists workflow templates and applies selected orchestration blueprints to projects with validation and feedback.",
  "frontend/src/pages/projectDetail/OrchestrationProjectDetailView.tsx": "Implements the comprehensive project command center for hierarchy, agents, tasks, kanban, runs, memory, approvals, repositories, milestones, decisions, settings, and live state.",
  "frontend/src/pages/projectDetail/kanbanConstants.ts": "Defines the canonical task-status columns used by the project-detail kanban board.",
  "frontend/src/utils/apiErrors.test.ts": "Verifies extraction of human-readable API error messages from supported response shapes and fallbacks.",
  "frontend/src/utils/apiErrors.ts": "Normalizes unknown API failures into safe user-facing error messages.",
  "frontend/src/utils/formatters.ts": "Provides shared currency, date, name, initials, and key-label formatting helpers for the frontend.",
  "frontend/src/utils/orchestrationSelection.ts": "Normalizes persisted orchestration selection metadata into a stable provider and model choice."
};

const complexity = (lines) => lines > 200 ? "complex" : lines >= 50 ? "moderate" : "simple";
const humanize = (name) => name
  .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
  .replaceAll("_", " ")
  .replace(/\bmfa\b/gi, "MFA")
  .replace(/\bgithub\b/gi, "GitHub")
  .replace(/\bapi\b/gi, "API")
  .replace(/\bcsv\b/gi, "CSV")
  .trim();

const isTest = (filePath) => filePath.includes(".test.");
const fileTags = (filePath) => {
  if (isTest(filePath)) return ["test", "frontend", "react", "vitest"];
  if (filePath.includes("/utils/")) return ["utility", "frontend", "type-safe", "shared"];
  if (filePath.endsWith("kanbanConstants.ts")) return ["configuration", "kanban", "task-status", "type-definition"];
  if (filePath.includes("projectDetail/")) return ["component", "project-detail", "orchestration", "workspace"];
  const page = path.basename(filePath).replace(/Page\.tsx$/, "").replace(/Panel\.tsx$/, "").replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
  return ["component", "page", page, "react"];
};

const fileNotes = (filePath) => {
  if (filePath.endsWith(".tsx") && !isTest(filePath)) return "React functional components combine typed API models with query-driven loading, mutation, and feedback states.";
  if (isTest(filePath)) return "Vitest and Testing Library exercise user-visible behavior through mocked API boundaries.";
  return undefined;
};

const exactFunctionSummaries = {
  CreateBrainstormDialog: "Collects brainstorming participants, goals, modes, rounds, consensus thresholds, and output options before creating a session.",
  BrainstormsPage: "Lists brainstorming sessions and coordinates creation, selection, and status presentation.",
  CalendarPage: "Renders the shared operational calendar inside a dedicated page shell.",
  CompanyEditor: "Edits company identity, markdown brief, slug, and structured settings with create and update mutations.",
  CompaniesPanel: "Loads the company catalog and coordinates selection, creation, editing, empty states, and feedback.",
  CompaniesPage: "Provides the routed companies page around the reusable companies panel.",
  CompanyMemoryPage: "Loads and presents semantic memory shared at company scope.",
  BarRow: "Renders one proportional analytics bar with label, value, and relative magnitude.",
  CostAnalyticsPage: "Aggregates and visualizes orchestration cost, token, budget, provider, and model statistics.",
  renderDashboard: "Renders the dashboard under the required test providers and query client.",
  DashboardPage: "Coordinates dashboard queries and renders operational summaries, calendars, queues, approvals, notifications, and failure states.",
  RollupTable: "Renders a compact table for grouped execution metrics and outcomes.",
  ExecutionInsightsPage: "Loads execution insights and presents rollups, provider health, failure counts, and diagnostic states.",
  LinkedIssueAssignmentField: "Edits the agent assignment associated with a linked GitHub issue.",
  GithubSyncPanel: "Coordinates GitHub installation, repository sync, issue imports, approval actions, webhook replay, and live updates.",
  GithubSyncPage: "Provides the routed GitHub synchronization page around the reusable sync panel.",
  ModelSettingsPage: "Hosts provider and model configuration within the model-settings route.",
  PreferenceItem: "Renders one labeled preference toggle with explanatory copy.",
  NotificationsPage: "Coordinates notification queries, read actions, unread summaries, and preference updates.",
  OrchestrationPortfolioPage: "Loads cross-project orchestration state and renders health, policy, dependency, capacity, and alert views.",
  renderProjectDetail: "Renders the project-detail view with the query and routing providers required by tests.",
  OrchestrationProjectDetailPage: "Validates the route identifier and lazy-loads the project-detail implementation.",
  buildLocalRepoPayload: "Normalizes local repository form fields into the backend workspace payload.",
  OrchestrationProjectsPage: "Coordinates project listing, creation, bootstrap, company selection, repository setup, and navigation.",
  PlatformPanel: "Implements platform administration workflows across plans, modules, credentials, webhooks, flags, and templates.",
  PlatformPage: "Provides the routed platform administration page around the reusable platform panel.",
  MfaQrCode: "Renders an MFA enrollment QR code from the supplied provisioning URI.",
  ProfileContent: "Coordinates profile, avatar, password, MFA, session, and notification-preference workflows.",
  ProfilePage: "Hosts the authenticated user's profile and security workspace.",
  buildProviderCreatePayload: "Normalizes provider form state into a typed provider creation payload.",
  ProviderRequestTimeoutEditor: "Edits provider request timeout policy with bounded numeric controls.",
  getProviderModels: "Returns the discovered models applicable to a provider configuration.",
  ProviderSettingsPanel: "Coordinates provider creation, updates, health checks, model discovery, defaults, and comparison workflows.",
  ProviderSettingsPage: "Provides a page wrapper around the reusable provider settings panel.",
  RunStatusChip: "Renders a compact visual indicator for an orchestration run status.",
  RunEventRow: "Displays one run event with timing, level, payload, and expandable detail.",
  ToolCallPair: "Pairs a tool invocation with its corresponding result for inspection.",
  ConversationViewer: "Builds the chronological run conversation from messages and paired tool calls.",
  ConversationBubble: "Renders one role-aware conversation message and its structured content.",
  RunMeta: "Displays run identity, status, timing, provider, model, token, and cost metadata.",
  RunTraceView: "Renders ordered trace spans and their timing or status details.",
  WorkflowGraphView: "Visualizes the execution workflow graph and step relationships.",
  RunInspectorPage: "Coordinates run selection, polling, SSE updates, events, traces, conversations, workflow, retry, replay, and cancellation controls.",
  SemanticMemoryPage: "Coordinates the full semantic memory workspace, including entries, search, settings, conflicts, links, graphs, archives, and playbooks.",
  WorkflowTemplatesPage: "Loads workflow templates and applies selected templates to target projects.",
  toastQueuedRunWithOptionalWarnings: "Reports a queued run and includes any non-fatal scheduling warnings in the snackbar message.",
  readExternalLinks: "Normalizes unknown task metadata into a typed list of external links.",
  serializeExternalLinks: "Serializes editable external links into task metadata form values.",
  readEvidenceBundle: "Normalizes unknown task metadata into a typed evidence bundle.",
  buildEvidenceBundlePayload: "Builds the persisted evidence-bundle payload from editable form state.",
  readWorkspaceOverview: "Extracts a stable workspace summary from local repository inspection data.",
  buildTransitionOptions: "Derives permitted task status transitions from the current state and workflow rules.",
  policyFieldValue: "Reads a nested routing-policy field using a dotted path.",
  readAcceptanceCheckerConfig: "Normalizes project settings into the task acceptance checker configuration.",
  ArtifactPanel: "Lists task artifacts and supports inspecting or adding evidence attachments.",
  TaskMemoryInspector: "Displays and edits task memory coordination, working memory, and retrieved context.",
  OrchestrationProjectDetailView: "Coordinates the complete project workspace across tasks, hierarchy, agents, execution, memory, repositories, governance, settings, and live synchronization.",
  extractApiErrorMessage: "Extracts a safe message from common API error response shapes with a deterministic fallback.",
  formatCurrency: "Formats numeric values as compact US-dollar currency.",
  formatDate: "Formats a date-like value into a localized short date.",
  formatDateOnly: "Formats a date-like value without a time component.",
  formatDateTime: "Formats a date-like value with localized date and time components.",
  getInitials: "Derives stable display initials from a person's name.",
  getFirstName: "Extracts the first display name token from a full name.",
  humanizeKey: "Converts an identifier-style key into a readable title.",
  readOrchestrationSelectionMeta: "Normalizes unknown selection metadata into a supported provider and model selection."
};

const functionSummary = (name) => exactFunctionSummaries[name] ?? `${humanize(name)} component or helper used by its enclosing page.`;
const functionTags = (filePath, name) => {
  if (isTest(filePath) || name.startsWith("render")) return ["test", "fixture", "react", "vitest"];
  if (filePath.includes("/utils/")) return ["utility", "formatting", "frontend", "type-safe"];
  if (/^(read|build|serialize|toast)/.test(name)) return ["utility", "data-transformation", "project-detail", "type-safe"];
  if (/Page$/.test(name)) return ["component", "page", "react", "data-fetching"];
  if (/Panel$|Dialog$|Editor$|View$|Viewer$|Row$|Bubble$|Chip$|Field$|Table$|QrCode$|Content$|Inspector$/.test(name)) return ["component", "react", "user-interface", "interaction"];
  return ["utility", "frontend", "type-safe", "shared"];
};

const nodes = [];
const edges = [];
const nodeIds = new Set();
const addNode = (node) => {
  if (nodeIds.has(node.id)) throw new Error(`Duplicate node ${node.id}`);
  nodeIds.add(node.id);
  nodes.push(node);
};
const addEdge = (source, target, type, weight) => edges.push({source, target, type, direction: "forward", weight});
const resultsByPath = new Map(extraction.results.map((result) => [result.path, result]));
const significantByFile = new Map();

for (const file of input.batchFiles) {
  const result = resultsByPath.get(file.path);
  if (!result) throw new Error(`Missing extraction result for ${file.path}`);
  const fileId = `file:${file.path}`;
  const fileNode = {id: fileId, type: "file", name: path.basename(file.path), filePath: file.path, summary: summaries[file.path], tags: fileTags(file.path), complexity: complexity(result.nonEmptyLines)};
  const languageNotes = fileNotes(file.path);
  if (languageNotes) fileNode.languageNotes = languageNotes;
  if (!fileNode.summary) throw new Error(`Missing summary for ${file.path}`);
  addNode(fileNode);

  const exportNames = new Set((result.exports ?? []).map((item) => item.name));
  const significant = new Map();
  for (const fn of result.functions ?? []) {
    const lineCount = fn.endLine - fn.startLine + 1;
    if (lineCount < 10 && !exportNames.has(fn.name)) continue;
    const id = `function:${file.path}:${fn.name}`;
    significant.set(fn.name, id);
    addNode({id, type: "function", name: fn.name, filePath: file.path, lineRange: [fn.startLine, fn.endLine], summary: functionSummary(fn.name), tags: functionTags(file.path, fn.name), complexity: complexity(lineCount)});
    addEdge(fileId, id, "contains", 1.0);
    if (exportNames.has(fn.name)) addEdge(fileId, id, "exports", 0.8);
  }
  significantByFile.set(file.path, significant);
}

for (const [sourcePath, targets] of Object.entries(input.batchImportData)) {
  for (const targetPath of targets) addEdge(`file:${sourcePath}`, `file:${targetPath}`, "imports", 0.7);
  for (const targetPath of targets.filter((target) => target.includes("/hooks/"))) addEdge(`file:${sourcePath}`, `file:${targetPath}`, "depends_on", 0.6);
}

for (const result of extraction.results) {
  const local = significantByFile.get(result.path);
  const imported = new Map();
  for (const importedPath of input.batchImportData[result.path] ?? []) {
    for (const [symbol, id] of significantByFile.get(importedPath) ?? []) imported.set(symbol, id);
  }
  const neighbors = new Map();
  for (const neighbor of batch.neighborMap[result.path] ?? []) {
    for (const symbol of neighbor.symbols ?? []) neighbors.set(symbol, `function:${neighbor.path}:${symbol}`);
  }
  for (const call of result.callGraph ?? []) {
    const source = local.get(call.caller);
    if (!source) continue;
    const target = local.get(call.callee) ?? imported.get(call.callee) ?? neighbors.get(call.callee);
    if (target && target !== source) addEdge(source, target, "calls", 0.8);
  }
}

const componentContainment = [
  ["frontend/src/pages/BrainstormsPage.tsx", "BrainstormsPage", "frontend/src/pages/BrainstormsPage.tsx", "CreateBrainstormDialog"],
  ["frontend/src/pages/CompaniesPage.tsx", "CompaniesPage", "frontend/src/pages/CompaniesPage.tsx", "CompaniesPanel"],
  ["frontend/src/pages/CompaniesPage.tsx", "CompaniesPanel", "frontend/src/pages/CompaniesPage.tsx", "CompanyEditor"],
  ["frontend/src/pages/CostAnalyticsPage.tsx", "CostAnalyticsPage", "frontend/src/pages/CostAnalyticsPage.tsx", "BarRow"],
  ["frontend/src/pages/ExecutionInsightsPage.tsx", "ExecutionInsightsPage", "frontend/src/pages/ExecutionInsightsPage.tsx", "RollupTable"],
  ["frontend/src/pages/GithubSyncPage.tsx", "GithubSyncPage", "frontend/src/pages/GithubSyncPage.tsx", "GithubSyncPanel"],
  ["frontend/src/pages/GithubSyncPage.tsx", "GithubSyncPanel", "frontend/src/pages/GithubSyncPage.tsx", "LinkedIssueAssignmentField"],
  ["frontend/src/pages/ModelSettingsPage.tsx", "ModelSettingsPage", "frontend/src/pages/ProviderSettingsPanel.tsx", "ProviderSettingsPanel"],
  ["frontend/src/pages/NotificationsPage.tsx", "NotificationsPage", "frontend/src/pages/NotificationsPage.tsx", "PreferenceItem"],
  ["frontend/src/pages/PlatformPage.tsx", "PlatformPage", "frontend/src/pages/PlatformPage.tsx", "PlatformPanel"],
  ["frontend/src/pages/ProfilePage.tsx", "ProfilePage", "frontend/src/pages/ProfilePage.tsx", "ProfileContent"],
  ["frontend/src/pages/ProfilePage.tsx", "ProfileContent", "frontend/src/pages/ProfilePage.tsx", "PreferenceItem"],
  ["frontend/src/pages/ProfilePage.tsx", "ProfileContent", "frontend/src/pages/ProfilePage.tsx", "MfaQrCode"],
  ["frontend/src/pages/ProviderSettingsPanel.tsx", "ProviderSettingsPage", "frontend/src/pages/ProviderSettingsPanel.tsx", "ProviderSettingsPanel"],
  ["frontend/src/pages/ProviderSettingsPanel.tsx", "ProviderSettingsPanel", "frontend/src/pages/ProviderSettingsPanel.tsx", "ProviderRequestTimeoutEditor"],
  ["frontend/src/pages/RunInspectorPage.tsx", "RunInspectorPage", "frontend/src/pages/RunInspectorPage.tsx", "RunMeta"],
  ["frontend/src/pages/RunInspectorPage.tsx", "RunInspectorPage", "frontend/src/pages/RunInspectorPage.tsx", "ConversationViewer"],
  ["frontend/src/pages/RunInspectorPage.tsx", "RunInspectorPage", "frontend/src/pages/RunInspectorPage.tsx", "RunTraceView"],
  ["frontend/src/pages/RunInspectorPage.tsx", "RunInspectorPage", "frontend/src/pages/RunInspectorPage.tsx", "WorkflowGraphView"],
  ["frontend/src/pages/RunInspectorPage.tsx", "ConversationViewer", "frontend/src/pages/RunInspectorPage.tsx", "ToolCallPair"],
  ["frontend/src/pages/RunInspectorPage.tsx", "ConversationViewer", "frontend/src/pages/RunInspectorPage.tsx", "ConversationBubble"],
  ["frontend/src/pages/RunInspectorPage.tsx", "RunInspectorPage", "frontend/src/pages/RunInspectorPage.tsx", "RunEventRow"],
  ["frontend/src/pages/projectDetail/OrchestrationProjectDetailView.tsx", "OrchestrationProjectDetailView", "frontend/src/pages/projectDetail/OrchestrationProjectDetailView.tsx", "ArtifactPanel"],
  ["frontend/src/pages/projectDetail/OrchestrationProjectDetailView.tsx", "OrchestrationProjectDetailView", "frontend/src/pages/projectDetail/OrchestrationProjectDetailView.tsx", "TaskMemoryInspector"]
];
for (const [sourcePath, sourceName, targetPath, targetName] of componentContainment) {
  const source = significantByFile.get(sourcePath)?.get(sourceName);
  const target = significantByFile.get(targetPath)?.get(targetName);
  if (!source || !target) throw new Error(`Missing component containment node ${sourceName} -> ${targetName}`);
  addEdge(source, target, "contains", 1.0);
}

for (const [testPath, targets] of Object.entries(input.batchImportData)) {
  if (!isTest(testPath)) continue;
  for (const targetPath of targets) addEdge(`file:${testPath}`, `file:${targetPath}`, "tested_by", 0.5);
}

const seenEdges = new Set();
const finalEdges = edges.filter((edge) => {
  const key = `${edge.source}\u0000${edge.target}\u0000${edge.type}`;
  if (seenEdges.has(key)) return false;
  seenEdges.add(key);
  return true;
});

const expectedImports = Object.values(input.batchImportData).reduce((sum, values) => sum + values.length, 0);
const actualImports = finalEdges.filter((edge) => edge.type === "imports").length;
if (actualImports !== expectedImports) throw new Error(`Expected ${expectedImports} imports, got ${actualImports}`);

const partCount = Math.ceil(Math.max(nodes.length / 60, finalEdges.length / 120));
const sortedFiles = [...input.batchFiles].sort((a, b) => a.path.localeCompare(b.path));
const groupSize = Math.ceil(sortedFiles.length / partCount);
const parts = [];
for (let index = 0; index < partCount; index += 1) {
  const fileSet = new Set(sortedFiles.slice(index * groupSize, (index + 1) * groupSize).map((item) => item.path));
  if (!fileSet.size) continue;
  const partNodes = nodes.filter((node) => fileSet.has(node.filePath));
  const sourceIds = new Set(partNodes.map((node) => node.id));
  const partEdges = finalEdges.filter((edge) => sourceIds.has(edge.source));
  const outputPath = path.join(intermediate, `batch-9-part-${index + 1}.json`);
  fs.writeFileSync(outputPath, `${JSON.stringify({nodes: partNodes, edges: partEdges}, null, 2)}\n`);
  parts.push({outputPath, nodes: partNodes.length, edges: partEdges.length, files: fileSet.size});
}

if (parts.reduce((sum, item) => sum + item.nodes, 0) !== nodes.length) throw new Error("Node partition mismatch");
if (parts.reduce((sum, item) => sum + item.edges, 0) !== finalEdges.length) throw new Error("Edge partition mismatch");

const allNodeIds = new Set(nodes.map((node) => node.id));
const importedPaths = new Set(Object.values(input.batchImportData).flat());
const neighborPaths = new Set(Object.values(batch.neighborMap).flat().map((item) => item.path));
const neighborEntityIds = new Set();
for (const neighborList of Object.values(batch.neighborMap)) {
  for (const neighbor of neighborList) for (const symbol of neighbor.symbols ?? []) neighborEntityIds.add(`function:${neighbor.path}:${symbol}`);
}
for (const part of parts) {
  const parsed = JSON.parse(fs.readFileSync(part.outputPath, "utf8"));
  if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) throw new Error(`${part.outputPath} lacks arrays`);
  const sourceIds = new Set(parsed.nodes.map((node) => node.id));
  for (const node of parsed.nodes) {
    if (!node.id || !node.type || !node.name || !node.summary || !node.complexity || !Array.isArray(node.tags) || node.tags.length < 3 || node.tags.length > 5) throw new Error(`Invalid node ${node.id}`);
  }
  for (const edge of parsed.edges) {
    if (!sourceIds.has(edge.source)) throw new Error(`${part.outputPath}: unknown source ${edge.source}`);
    if (allNodeIds.has(edge.target) || neighborEntityIds.has(edge.target)) continue;
    if (edge.target.startsWith("file:")) {
      const targetPath = edge.target.slice(5);
      if (importedPaths.has(targetPath) || neighborPaths.has(targetPath)) continue;
    }
    throw new Error(`${part.outputPath}: unknown target ${edge.target}`);
  }
}

console.log(JSON.stringify({parts: parts.length, nodes: nodes.length, edges: finalEdges.length, imports: actualImports, details: parts.map((item) => ({file: path.basename(item.outputPath), nodes: item.nodes, edges: item.edges, files: item.files}))}, null, 2));
