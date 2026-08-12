import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tmp = path.join(root, ".understand-anything/tmp");
const intermediate = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-extract-results-27.json"), "utf8"));
const batches = JSON.parse(fs.readFileSync(path.join(intermediate, "batches.json"), "utf8"));
const batch = batches.batches.find((item) => item.batchIndex === 27);
if (!batch) throw new Error("Batch 27 not found");

const meta = {
  "backend/modules/orchestration/execution/__init__.py": ["Marks the orchestration execution subsystem as an importable Python package.", ["package", "orchestration", "execution", "entry-point"]],
  "backend/modules/orchestration/routers/__init__.py": ["Marks the split orchestration router subsystem as an importable Python package.", ["package", "orchestration", "routing", "entry-point"]],
  "backend/modules/orchestration/templates.py": ["Defines the built-in skill packs and versioned agent templates used to bootstrap common engineering, review, planning, and incident roles.", ["templates", "agents", "skills", "configuration"]],
  "backend/modules/users/models.py": ["Documents that the canonical user entity resides in the identity-access domain while user services reuse that model.", ["data-model", "users", "identity-access", "compatibility"]],
  "backend/tests/fixtures/rag_eval_golden.json": ["Golden retrieval-evaluation cases containing representative queries, expected chunks, negative chunks, and recall thresholds.", ["test-fixture", "rag", "evaluation", "quality"]],
  "backend/tests/test_external_call_policy.py": ["Guards the runtime external-call policy by asserting that HTTP clients use the centralized shared pool.", ["test", "http-client", "policy", "pytest"]],
  "backend/tools/check_external_call_policy.py": ["Scans runtime Python files for direct HTTPX client construction outside approved infrastructure boundaries.", ["policy-check", "http-client", "security", "cli"]],
  "backend/tools/check_logging_policy.py": ["Scans runtime Python files for disallowed direct logging setup and printing outside approved CLI and test boundaries.", ["policy-check", "logging", "quality", "cli"]],
  "backend/tools/troop_cli.py": ["Implements a command-line client for creating orchestration tasks, starting runs, and streaming run events from the Troop API.", ["cli", "orchestration", "api-client", "developer-tool"]],
  "frontend/eslint.config.js": ["Configures ESLint for browser TypeScript and React code with recommended core, hooks, and Vite refresh rules.", ["configuration", "eslint", "typescript", "quality"]],
  "frontend/playwright.config.ts": ["Configures parallel browser end-to-end tests across desktop and mobile projects with retries, traces, and a managed Vite server.", ["configuration", "playwright", "e2e", "testing"]],
  "frontend/scripts/phase0-build-baseline.mjs": ["Measures frontend build output, asset sizes, language totals, and largest bundles and emits a repeatable JSON baseline.", ["script", "performance", "bundle-size", "baseline"]],
  "frontend/src/components/hierarchy/HierarchyBuilderCanvas.tsx": ["Implements the interactive hierarchy canvas with seeded records, graph layout, manager and member nodes, skill bindings, metrics, conversations, tasks, runs, and editing workflows.", ["component", "hierarchy", "graph-editor", "react"]],
  "frontend/src/components/ui/Subsection.tsx": ["Renders a reusable subsection heading and content layout with optional help, action, and style overrides.", ["component", "design-system", "layout", "react"]],
  "frontend/src/index.css": ["Defines global browser defaults for typography, color scheme, sizing, body layout, and root rendering.", ["styles", "css", "global", "theming"]],
  "frontend/src/pages/AgentLibraryPage.tsx": ["Compatibility page entry point that re-exports the hierarchy page as the agent-library route.", ["barrel", "page", "agents", "entry-point"]],
  "frontend/src/test/setup.ts": ["Loads Testing Library's DOM matchers for every Vitest frontend test.", ["test-setup", "vitest", "testing-library", "configuration"]],
  "frontend/src/types/qrcode.d.ts": ["Declares the QRCode package's typed data-URL generation interface and supported rendering options.", ["type-definition", "qrcode", "typescript", "declaration"]],
  "frontend/vite.config.ts": ["Configures the Vite React build, PWA manifest, auto-updating service worker, and stable vendor chunk partitioning.", ["configuration", "vite", "pwa", "build-system"]],
  "frontend/vitest.config.ts": ["Configures Vitest with React, jsdom, global test APIs, shared setup, V8 coverage, and exclusions.", ["configuration", "vitest", "coverage", "testing"]],
  "infra/.env.example": ["Documents required local infrastructure credentials and optional observability environment settings.", ["configuration", "environment", "infrastructure", "security"]],
  "infra/docker-compose.yml": ["Defines local PostgreSQL with pgvector, Redis, Mailpit, and MinIO services with loopback-only ports and persistent data volumes.", ["orchestration", "infrastructure", "docker-compose", "development"]],
  "infra/observability/docker-compose.observability.yml": ["Defines the optional Prometheus, Tempo, Loki, OpenTelemetry Collector, and Grafana observability stack and its mounted configuration.", ["orchestration", "observability", "docker-compose", "monitoring"]],
  "infra/observability/grafana/dashboards/troop-overview.json": ["Grafana dashboard for Troop request rate, latency, errors, worker activity, queue age, run outcomes, provider failures, and memory retrieval latency.", ["configuration", "grafana", "monitoring", "dashboard"]],
  "infra/observability/grafana/provisioning/dashboards/dashboards.yml": ["Provisions Troop's file-backed Grafana dashboards with periodic refresh and deletion protection.", ["configuration", "grafana", "provisioning", "dashboard"]],
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
function fileType(result) {
  if (result.fileCategory === "config") return ["config", `config:${result.path}`];
  if (result.fileCategory === "infra") return ["service", `service:${result.path}`];
  return ["file", `file:${result.path}`];
}
function functionTags(filePath, name) {
  if (filePath.includes("/tests/")) return ["test", "policy", "pytest"];
  if (filePath.includes("check_external")) return ["policy-check", "http-client", "cli"];
  if (filePath.includes("check_logging")) return ["policy-check", "logging", "cli"];
  if (filePath.includes("troop_cli")) return ["cli", "orchestration", "api-client"];
  if (filePath.includes("phase0-build")) return ["performance", "bundle-size", "script"];
  if (filePath.includes("HierarchyBuilderCanvas")) return [/^[A-Z]/.test(name) ? "component" : "utility", "hierarchy", "graph-editor"];
  if (filePath.includes("Subsection")) return ["component", "design-system", "react"];
  return ["backend", "python", "utility"];
}
function functionSummary(filePath, name) {
  const label = human(name);
  if (name === "test_runtime_http_clients_use_the_shared_pool") return "Asserts that runtime modules do not construct HTTPX clients outside the approved shared-client boundary.";
  if (filePath.includes("check_external")) return `Implements ${label} for the external HTTP client policy check.`;
  if (filePath.includes("check_logging")) return `Implements ${label} for the runtime logging policy check.`;
  if (filePath.includes("troop_cli")) return `Implements the ${label} command-line API workflow.`;
  if (filePath.includes("phase0-build")) return `Implements ${label} for recursive build-output size measurement.`;
  if (name === "HierarchyBuilderCanvas") return "Provides the public ReactFlow-backed hierarchy builder within its provider boundary.";
  if (name === "HierarchyBuilderInner") return "Coordinates the hierarchy builder's editing, selection, simulation, dialogs, metrics, and graph interactions.";
  if (name === "ManagerNode" || name === "TeamMemberNode") return `Renders the ${label} ReactFlow node with status and hierarchy controls.`;
  if (filePath.includes("HierarchyBuilderCanvas")) return `Implements ${label} behavior for hierarchy records, graph layout, or canvas presentation.`;
  if (name === "Subsection") return "Renders a consistent subsection heading, controls, and content surface.";
  return `Implements ${label} for the application.`;
}

const nodes = [];
const edges = [];
const ids = new Set();
const edgeKeys = new Set();
const fileIds = new Map();
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
  const [type, id] = fileType(result);
  fileIds.set(result.path, id);
  addNode({ id, type, name: path.basename(result.path), filePath: result.path, summary, tags, complexity: fileComplexity(result) });
  const exports = new Set((result.exports ?? []).map((item) => item.name));
  for (const fn of result.functions ?? []) {
    const lines = fn.endLine - fn.startLine + 1;
    if (!exports.has(fn.name) && lines < 10) continue;
    const functionId = `function:${result.path}:${fn.name}`;
    addNode({ id: functionId, type: "function", name: fn.name, filePath: result.path, lineRange: [fn.startLine, fn.endLine], summary: functionSummary(result.path, fn.name), tags: functionTags(result.path, fn.name), complexity: complexity(fn.startLine, fn.endLine) });
    addEdge({ source: id, target: functionId, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(fn.name)) addEdge({ source: id, target: functionId, type: "exports", direction: "forward", weight: 0.8 });
  }
}

for (const [sourcePath, targets] of Object.entries(batch.batchImportData)) {
  for (const targetPath of targets) addEdge({ source: fileIds.get(sourcePath), target: `file:${targetPath}`, type: "imports", direction: "forward", weight: 0.7 });
}
addEdge({ source: "file:backend/tools/check_external_call_policy.py", target: "file:backend/tests/test_external_call_policy.py", type: "tested_by", direction: "forward", weight: 0.5 });
addEdge({ source: "config:backend/tests/fixtures/rag_eval_golden.json", target: "file:backend/modules/rag/evaluation.py", type: "related", direction: "forward", weight: 0.5 });
addEdge({ source: "file:frontend/eslint.config.js", target: "file:frontend/src/main.tsx", type: "configures", direction: "forward", weight: 0.6 });
addEdge({ source: "file:frontend/vite.config.ts", target: "file:frontend/src/main.tsx", type: "configures", direction: "forward", weight: 0.6 });
addEdge({ source: "file:frontend/vitest.config.ts", target: "file:frontend/src/test/setup.ts", type: "configures", direction: "forward", weight: 0.6 });
addEdge({ source: "file:frontend/src/pages/AgentLibraryPage.tsx", target: "file:frontend/src/pages/HierarchyPage.tsx", type: "depends_on", direction: "forward", weight: 0.6 });
addEdge({ source: "file:frontend/src/index.css", target: "file:frontend/src/main.tsx", type: "related", direction: "forward", weight: 0.5 });
addEdge({ source: "config:infra/.env.example", target: "service:infra/docker-compose.yml", type: "configures", direction: "forward", weight: 0.6 });
addEdge({ source: "config:infra/observability/grafana/provisioning/dashboards/dashboards.yml", target: "service:infra/observability/docker-compose.observability.yml", type: "configures", direction: "forward", weight: 0.6 });
addEdge({ source: "config:infra/observability/grafana/dashboards/troop-overview.json", target: "service:infra/observability/docker-compose.observability.yml", type: "configures", direction: "forward", weight: 0.6 });
addEdge({ source: "service:infra/observability/docker-compose.observability.yml", target: "config:infra/observability/grafana/dashboards/troop-overview.json", type: "depends_on", direction: "forward", weight: 0.6 });

const outputPath = path.join(intermediate, "batch-27.json");
fs.writeFileSync(outputPath, `${JSON.stringify({ nodes, edges }, null, 2)}\n`);

const fragment = JSON.parse(fs.readFileSync(outputPath, "utf8"));
const outputIds = new Set(fragment.nodes.map((node) => node.id));
const allowedFiles = new Set([...Object.keys(batch.batchImportData), ...Object.values(batch.batchImportData).flat(), ...Object.keys(batch.neighborMap), ...Object.values(batch.neighborMap).flatMap((items) => items.map((item) => item.path)), "backend/modules/rag/evaluation.py", "frontend/src/main.tsx", "frontend/src/pages/HierarchyPage.tsx"]);
for (const edge of fragment.edges) {
  if (!outputIds.has(edge.source)) throw new Error(`Missing source ${edge.source}`);
  if (outputIds.has(edge.target)) continue;
  const fileMatch = /^file:(.+)$/.exec(edge.target);
  if (fileMatch && allowedFiles.has(fileMatch[1])) continue;
  throw new Error(`Unvalidated target ${edge.target}`);
}

process.stdout.write(JSON.stringify({ outputPath, nodeCount: nodes.length, edgeCount: edges.length, filesSkipped: extraction.filesSkipped ?? [] }));
