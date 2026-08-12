import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tmp = path.join(root, ".understand-anything/tmp");
const intermediate = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-extract-results-7.json"), "utf8"));
const batches = JSON.parse(fs.readFileSync(path.join(intermediate, "batches.json"), "utf8"));
const batch = batches.batches.find((item) => item.batchIndex === 7);
if (!batch) throw new Error("Batch 7 not found");

const meta = {
  "frontend/src/api/admin.ts": ["Provides typed frontend API calls for administrator user listing and status management.", ["api-client", "admin", "typescript", "http"]],
  "frontend/src/api/ai.ts": ["Defines AI-domain API types and calls for prompts, documents, retrieval, model runs, review, feedback, and evaluation.", ["api-client", "ai", "rag", "typescript"]],
  "frontend/src/api/calendar.ts": ["Provides typed CRUD requests for calendar and planner items.", ["api-client", "calendar", "typescript", "crud"]],
  "frontend/src/api/client.test.ts": ["Verifies the shared API client's authentication expiry, error parsing, retry, and response behavior.", ["test", "api-client", "authentication", "vitest"]],
  "frontend/src/api/client.ts": ["Implements the shared authenticated fetch client with CSRF headers, refresh-token retry, session-expiry notifications, and normalized request errors.", ["api-client", "authentication", "csrf", "error-handling"]],
  "frontend/src/api/companies.ts": ["Provides typed frontend requests for listing, creating, retrieving, and updating company workspaces.", ["api-client", "company", "typescript", "crud"]],
  "frontend/src/api/notifications.ts": ["Provides typed notification listing, read-state, and delivery-preference API calls.", ["api-client", "notifications", "typescript", "crud"]],
  "frontend/src/api/orchestration.ts": ["Defines the frontend's comprehensive REST contract for agents, projects, tasks, runs, memory, approvals, GitHub, providers, workflows, evaluation, and governance.", ["api-client", "orchestration", "workflow", "typescript"]],
  "frontend/src/api/orchestrationGraphql.ts": ["Implements typed GraphQL operations for the live operating hierarchy, model profiles, team membership, tasks, approvals, runs, and brainstorms.", ["api-client", "graphql", "orchestration", "hierarchy"]],
  "frontend/src/api/platform.ts": ["Provides typed platform API calls for metadata, subscriptions, API keys, webhooks, feature flags, configuration, and email templates.", ["api-client", "platform", "admin", "typescript"]],
  "frontend/src/api/settings.ts": ["Provides typed administration calls for environment-backed and database-backed runtime settings.", ["api-client", "settings", "admin", "configuration"]],
  "frontend/src/api/users.ts": ["Provides typed current-user, password, session, and directory API calls.", ["api-client", "users", "authentication", "typescript"]],
  "frontend/src/app/snackbarContext.ts": ["Defines the React context contract and hook used to publish global snackbar notifications.", ["react-context", "hook", "notifications", "type-definition"]],
  "frontend/src/components/dashboard/DashboardCalendar.tsx": ["Renders the interactive dashboard calendar with month, week, and day views plus planner item creation, editing, deletion, and orchestration context.", ["component", "calendar", "dashboard", "react"]],
  "frontend/src/components/guards/RouteErrorBoundary.tsx": ["Catches route rendering failures, reports diagnostic context, and presents a recoverable error state.", ["component", "error-boundary", "error-handling", "react"]],
  "frontend/src/components/hierarchy/AgentOperatingConsole.tsx": ["Renders the hierarchy operating console for live team state, member and task management, model selection, runs, approvals, and brainstorms.", ["component", "orchestration", "hierarchy", "react"]],
  "frontend/src/components/runInspector/RunInspectorDataViews.tsx": ["Provides reusable run-inspector views for raw JSON, structured event payloads, trace steps, outputs, and checkpoint summaries.", ["component", "run-inspector", "visualization", "react"]],
  "frontend/src/components/ui/CollapsibleSectionCard.tsx": ["Wraps section content in a reusable expandable card with counts, help text, and actions.", ["component", "design-system", "collapsible", "react"]],
  "frontend/src/components/ui/EmptyState.tsx": ["Renders a consistent empty-state presentation with an icon, guidance, and optional action.", ["component", "design-system", "empty-state", "react"]],
  "frontend/src/components/ui/PageHeader.tsx": ["Renders the shared page heading, eyebrow, description, and action layout.", ["component", "design-system", "layout", "react"]],
  "frontend/src/components/ui/PageShell.tsx": ["Provides the shared responsive content container used by application pages.", ["component", "design-system", "layout", "react"]],
  "frontend/src/components/ui/QueryState.tsx": ["Normalizes loading, error, empty, retry, and success rendering for asynchronous queries.", ["component", "data-fetching", "error-handling", "react"]],
  "frontend/src/components/ui/SectionCard.tsx": ["Renders a reusable section surface with title, description, help, action, and configurable content styling.", ["component", "design-system", "layout", "react"]],
  "frontend/src/components/ui/StatCard.tsx": ["Displays a dashboard metric with loading state, icon, color treatment, description, and explanatory help.", ["component", "design-system", "dashboard", "react"]],
  "frontend/src/config/queryKeys.test.ts": ["Verifies stable, collision-resistant query-key construction across resource and parameter combinations.", ["test", "react-query", "cache", "vitest"]],
  "frontend/src/config/queryKeys.ts": ["Centralizes hierarchical TanStack Query keys and default stale-time configuration for frontend server state.", ["configuration", "react-query", "cache", "type-definition"]],
  "frontend/src/config/queryPolicies.ts": ["Defines shared TanStack Query freshness policies for static, operational, and live data.", ["configuration", "react-query", "cache", "performance"]],
  "frontend/src/features/hierarchy/live/useHierarchyLiveState.ts": ["Combines the hierarchy query cache with a live snapshot stream to expose current operating state.", ["hook", "hierarchy", "real-time", "react-query"]],
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
function functionTags(filePath, name) {
  if (filePath.includes("/api/")) return ["api-client", "typescript", filePath.includes("orchestration") ? "orchestration" : "http"];
  if (filePath.includes("/components/ui/")) return ["component", "design-system", "react"];
  if (filePath.includes("/components/dashboard/")) return ["component", "calendar", "react"];
  if (filePath.includes("/components/hierarchy/")) return ["component", "hierarchy", "react"];
  if (filePath.includes("/components/runInspector/")) return ["component", "run-inspector", "react"];
  if (filePath.includes("/guards/")) return ["error-handling", "route-guard", "react"];
  if (name.startsWith("use")) return ["hook", "react", "real-time"];
  return ["frontend", "typescript", "utility"];
}
function functionSummary(filePath, name) {
  const label = human(name);
  if (filePath.includes("/api/orchestrationGraphql.ts")) return `Executes the typed ${label} GraphQL operation for the hierarchy control plane.`;
  if (filePath.includes("/api/")) {
    if (name === "apiFetch") return "Executes authenticated API requests, applies CSRF protection, refreshes expired access tokens once, and normalizes failures.";
    if (name === "markAuthStateChanged") return "Advances the authentication-state version used to prevent stale expiry notifications.";
    if (name === "onAuthExpired") return "Registers a listener that is notified when the current authenticated session expires.";
    if (name === "readCookie") return "Reads and decodes a named browser cookie for request construction.";
    if (name === "refreshAccessToken") return "Requests a fresh access token using the secure refresh-token flow.";
    if (name === "reportRouteError") return "Reports route rendering failures with React component-stack and request context metadata.";
    return `Calls the backend API to perform ${label}.`;
  }
  if (/^[A-Z]/.test(name)) return `Renders the ${label} React interface.`;
  if (name === "useSnackbar") return "Reads the global snackbar context and enforces use within its provider.";
  if (name === "useHierarchyLiveState") return "Combines cached hierarchy data with live stream updates for the selected project.";
  return `Computes or renders ${label} data for the surrounding React interface.`;
}

const classSummaries = {
  SessionExpiredError: "Error type signaling that authentication refresh failed and the current browser session expired.",
  ApiRequestError: "Structured HTTP request error carrying status and parsed backend error detail.",
  RouteErrorBoundary: "React error boundary that reports route failures and lets users retry the failed render tree.",
};
function classSummary(name) {
  return classSummaries[name] ?? `Implements the ${human(name)} frontend component.`;
}
function classTags(name) {
  if (name === "RouteErrorBoundary") return ["component", "error-boundary", "react"];
  return ["error-handling", "api-client", "typescript"];
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
    const lines = fn.endLine - fn.startLine + 1;
    if (!exports.has(fn.name) && lines < 10) continue;
    const id = `function:${result.path}:${fn.name}`;
    addNode({ id, type: "function", name: fn.name, filePath: result.path, lineRange: [fn.startLine, fn.endLine], summary: functionSummary(result.path, fn.name), tags: functionTags(result.path, fn.name), complexity: complexity(fn.startLine, fn.endLine) });
    fileSymbols.set(fn.name, id);
    addEdge({ source: fileId, target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(fn.name)) addEdge({ source: fileId, target: id, type: "exports", direction: "forward", weight: 0.8 });
  }
  for (const cls of result.classes ?? []) {
    const lines = cls.endLine - cls.startLine + 1;
    if (!exports.has(cls.name) && (cls.methods?.length ?? 0) < 2 && lines < 20) continue;
    const id = `class:${result.path}:${cls.name}`;
    addNode({ id, type: "class", name: cls.name, filePath: result.path, lineRange: [cls.startLine, cls.endLine], summary: classSummary(cls.name), tags: classTags(cls.name), complexity: complexity(cls.startLine, cls.endLine) });
    fileSymbols.set(cls.name, id);
    for (const method of cls.methods ?? []) fileSymbols.set(method, id);
    addEdge({ source: fileId, target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(cls.name)) addEdge({ source: fileId, target: id, type: "exports", direction: "forward", weight: 0.8 });
  }
  symbolsByFile.set(result.path, fileSymbols);
}

for (const [sourcePath, targets] of Object.entries(batch.batchImportData)) {
  for (const targetPath of targets) {
    addEdge({ source: `file:${sourcePath}`, target: `file:${targetPath}`, type: "imports", direction: "forward", weight: 0.7 });
    if (sourcePath.includes(".test.") || sourcePath.includes(".spec.")) {
      addEdge({ source: `file:${targetPath}`, target: `file:${sourcePath}`, type: "tested_by", direction: "forward", weight: 0.5 });
    }
  }
}

for (const result of extraction.results) {
  const neighbors = batch.neighborMap[result.path] ?? [];
  const crossSymbols = new Map();
  for (const neighbor of neighbors) {
    for (const symbol of neighbor.symbols ?? []) if (!crossSymbols.has(symbol)) crossSymbols.set(symbol, neighbor.path);
    if (neighbor.path.includes(".test.") || neighbor.path.includes(".spec.")) {
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
  const outputPath = path.join(intermediate, `batch-7-part-${index + 1}.json`);
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
