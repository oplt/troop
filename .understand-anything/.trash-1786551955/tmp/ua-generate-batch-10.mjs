import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tmp = path.join(root, ".understand-anything/tmp");
const intermediate = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-extract-results-10.json"), "utf8"));
const batches = JSON.parse(fs.readFileSync(path.join(intermediate, "batches.json"), "utf8"));
const batch = batches.batches.find((item) => item.batchIndex === 10);
if (!batch) throw new Error("Batch 10 not found");

const meta = {
  "frontend/src/api/auth.ts": ["Provides typed authentication requests for registration, sign-in, token refresh, password recovery, email verification, and MFA management.", ["api-client", "authentication", "security", "typescript"]],
  "frontend/src/api/profile.ts": ["Provides typed profile retrieval, update, avatar upload, and avatar deletion requests.", ["api-client", "profile", "typescript", "crud"]],
  "frontend/src/app/SnackbarProvider.tsx": ["Implements the global snackbar provider and renders transient severity-aware application notifications.", ["component", "react-context", "notifications", "provider"]],
  "frontend/src/app/colorModeContext.ts": ["Defines the color-mode context contract and hook used to toggle light and dark themes.", ["react-context", "theming", "hook", "type-definition"]],
  "frontend/src/app/providers.tsx": ["Composes the application-wide query, authentication, theme, CSS baseline, and snackbar providers while persisting color-mode choice.", ["provider", "react", "theming", "data-fetching"]],
  "frontend/src/app/router.tsx": ["Defines the lazy-loaded application route tree with authentication, administrator, MFA, layout, suspense, and error-boundary guards.", ["routing", "react", "authentication", "lazy-loading"]],
  "frontend/src/app/theme.ts": ["Defines shared design tokens and builds comprehensive light and dark Material UI themes for typography, color, shape, and component overrides.", ["theming", "design-system", "material-ui", "configuration"]],
  "frontend/src/components/auth/AuthMarketingPanel.tsx": ["Renders the branded marketing panel shared by authentication flows, including highlights and product value points.", ["component", "authentication", "marketing", "react"]],
  "frontend/src/components/auth/AuthShell.tsx": ["Provides the responsive split-screen shell used by sign-in, registration, verification, and password-recovery pages.", ["component", "authentication", "layout", "react"]],
  "frontend/src/components/guards/ProtectedRoute.test.tsx": ["Verifies route access decisions for readiness, authentication, administrator, MFA, and redirect requirements.", ["test", "route-guard", "authentication", "vitest"]],
  "frontend/src/components/guards/ProtectedRoute.tsx": ["Guards route content by authentication readiness, sign-in status, administrator role, and MFA enrollment requirements.", ["component", "route-guard", "authentication", "authorization"]],
  "frontend/src/components/layout/AppLayout.accessibility.test.tsx": ["Checks that the application layout exposes accessible landmark labeling and navigation structure.", ["test", "accessibility", "layout", "vitest"]],
  "frontend/src/components/layout/AppLayout.tsx": ["Renders the authenticated application shell with responsive navigation, breadcrumbs, command palette, user controls, theme toggle, and nested route content.", ["component", "layout", "navigation", "react"]],
  "frontend/src/components/layout/CommandPalette.tsx": ["Implements keyboard-driven route discovery and navigation with fuzzy filtering and dialog focus management.", ["component", "command-palette", "navigation", "accessibility"]],
  "frontend/src/components/ui/StatCard.test.tsx": ["Verifies accessible labeling and descriptive content in the shared statistics card.", ["test", "component", "accessibility", "vitest"]],
  "frontend/src/config/queryClient.ts": ["Configures the shared TanStack Query client with cache defaults, retry behavior, and mutation policies.", ["configuration", "react-query", "cache", "data-fetching"]],
  "frontend/src/features/auth/context/AuthContext.tsx": ["Implements authentication state hydration, sign-in, sign-up, sign-out, and session-expiry coordination for the React application.", ["provider", "authentication", "react-context", "session"]],
  "frontend/src/features/auth/context/authContext.ts": ["Defines the authentication context state contract and guarded consumer hook.", ["react-context", "authentication", "hook", "type-definition"]],
  "frontend/src/features/auth/schemas.ts": ["Defines Zod validation schemas for sign-in, registration, and password-recovery forms.", ["validation", "authentication", "zod", "schema-definition"]],
  "frontend/src/hooks/useAuth.ts": ["Re-exports the canonical authentication hook for convenient feature imports.", ["barrel", "hook", "authentication", "entry-point"]],
  "frontend/src/hooks/useCanonicalUser.ts": ["Combines authentication context with a cached profile query to expose the canonical current user and refresh state.", ["hook", "authentication", "profile", "react-query"]],
  "frontend/src/main.tsx": ["Bootstraps the React application, mounting the global providers and router into the browser root.", ["entry-point", "react", "bootstrap", "provider"]],
  "frontend/src/pages/AuthHomePage.tsx": ["Renders the combined sign-in and registration experience with validation, MFA handling, redirects, and branded product context.", ["page", "authentication", "forms", "react"]],
  "frontend/src/pages/ResetPasswordPage.tsx": ["Renders the token-based password reset workflow with validation, submission feedback, and navigation back to authentication.", ["page", "authentication", "password-reset", "react"]],
  "frontend/src/pages/VerifyEmailPage.tsx": ["Processes email verification tokens and renders success, error, resend, and navigation states.", ["page", "authentication", "email-verification", "react"]],
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
  if (filePath.includes("/api/")) return ["api-client", "authentication", "typescript"];
  if (filePath.includes("/app/theme.ts")) return ["theming", "design-system", "material-ui"];
  if (filePath.includes("/app/router.tsx")) return ["routing", "react", "lazy-loading"];
  if (filePath.includes("/app/")) return [name.startsWith("use") ? "hook" : "provider", "react", "application-shell"];
  if (filePath.includes(".test.")) return ["test", "frontend", "vitest"];
  if (filePath.includes("/guards/")) return ["route-guard", "authentication", "react"];
  if (filePath.includes("/layout/")) return ["component", "layout", "react"];
  if (filePath.includes("/components/auth/")) return ["component", "authentication", "react"];
  if (filePath.includes("/pages/")) return ["page", "authentication", "react"];
  if (name.startsWith("use")) return ["hook", "authentication", "react-query"];
  return ["frontend", "typescript", "utility"];
}
function functionSummary(filePath, name) {
  const label = human(name);
  if (filePath.includes("/api/")) return `Calls the authentication or profile API to perform ${label}.`;
  if (name === "buildTheme") return "Builds the complete Material UI theme for the selected color mode from shared design tokens and component overrides.";
  if (name === "readStoredColorMode") return "Reads and validates the user's persisted light or dark color-mode preference.";
  if (name === "buildBreadcrumbs") return "Derives linked breadcrumb items and readable labels from the current route path and navigation model.";
  if (name === "formatPathSegment") return "Converts a URL path segment into a readable breadcrumb label.";
  if (name === "renderGuard") return "Renders the protected-route test harness with configurable authentication requirements.";
  if (/^[A-Z]/.test(name)) return `Renders the ${label} React interface.`;
  if (name.startsWith("use")) return `Provides the ${label} React hook behavior.`;
  return `Implements ${label} behavior for the frontend application.`;
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
  const localSymbols = new Map();
  for (const fn of result.functions ?? []) {
    const lines = fn.endLine - fn.startLine + 1;
    if (!exports.has(fn.name) && lines < 10) continue;
    const id = `function:${result.path}:${fn.name}`;
    addNode({ id, type: "function", name: fn.name, filePath: result.path, lineRange: [fn.startLine, fn.endLine], summary: functionSummary(result.path, fn.name), tags: functionTags(result.path, fn.name), complexity: complexity(fn.startLine, fn.endLine) });
    localSymbols.set(fn.name, id);
    addEdge({ source: fileId, target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(fn.name)) addEdge({ source: fileId, target: id, type: "exports", direction: "forward", weight: 0.8 });
  }
  for (const cls of result.classes ?? []) {
    const lines = cls.endLine - cls.startLine + 1;
    if (!exports.has(cls.name) && (cls.methods?.length ?? 0) < 2 && lines < 20) continue;
    const id = `class:${result.path}:${cls.name}`;
    addNode({ id, type: "class", name: cls.name, filePath: result.path, lineRange: [cls.startLine, cls.endLine], summary: `Implements the ${human(cls.name)} frontend component.`, tags: ["frontend", "typescript", "class"], complexity: complexity(cls.startLine, cls.endLine) });
    localSymbols.set(cls.name, id);
    for (const method of cls.methods ?? []) localSymbols.set(method, id);
    addEdge({ source: fileId, target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(cls.name)) addEdge({ source: fileId, target: id, type: "exports", direction: "forward", weight: 0.8 });
  }
  symbolsByFile.set(result.path, localSymbols);
}

const batchFilePaths = new Set(batch.files.map((item) => item.path));
for (const [sourcePath, targets] of Object.entries(batch.batchImportData)) {
  for (const targetPath of targets) {
    addEdge({ source: `file:${sourcePath}`, target: `file:${targetPath}`, type: "imports", direction: "forward", weight: 0.7 });
    if (sourcePath.includes(".test.") || sourcePath.includes(".spec.")) {
      addEdge(batchFilePaths.has(targetPath)
        ? { source: `file:${targetPath}`, target: `file:${sourcePath}`, type: "tested_by", direction: "forward", weight: 0.5 }
        : { source: `file:${sourcePath}`, target: `file:${targetPath}`, type: "tested_by", direction: "forward", weight: 0.5 });
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
  const outputPath = path.join(intermediate, `batch-10-part-${index + 1}.json`);
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
