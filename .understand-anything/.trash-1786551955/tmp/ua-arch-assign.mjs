import fs from "node:fs";
import path from "node:path";

const [inputPath, resultsPath, outputPath] = process.argv.slice(2);
if (!inputPath || !resultsPath || !outputPath) {
  console.error("Usage: node ua-arch-assign.mjs <input.json> <results.json> <layers.json>");
  process.exit(1);
}

const definitions = [
  ["layer:backend-api", "Backend API & Contracts", "FastAPI application entry points, routers, dependency providers, middleware, and Pydantic request/response contracts expose Troop's backend capabilities."],
  ["layer:backend-domain", "Backend Domain & Orchestration", "Domain modules implement agent orchestration, approvals, GitHub synchronization, memory and RAG workflows, identity, projects, notifications, and operational policy."],
  ["layer:data", "Persistence & Data Models", "SQLAlchemy models, repositories, database sessions, Alembic migrations, and vector-store adapters manage Troop's PostgreSQL-backed operational and semantic data."],
  ["layer:backend-runtime", "Backend Runtime & Workers", "Cross-cutting backend runtime services provide configuration, security, caching, telemetry, external I/O, agent workspaces, and Celery execution."],
  ["layer:frontend-ui", "Frontend UI & Pages", "React application composition, routed pages, reusable components, feature views, styling, and the HTML shell form Troop's operational workspace."],
  ["layer:frontend-services", "Frontend Services & State", "Typed API clients, React hooks and contexts, query state, validation schemas, parsers, and utilities connect the UI to Troop's backend workflows."],
  ["layer:test", "Tests & Evaluation", "Pytest, Vitest, and Playwright suites plus quality gates and baselines verify orchestration contracts, retrieval behavior, frontend state, reliability, and performance regressions."],
  ["layer:config", "Project Tooling & Configuration", "Build manifests, dependency declarations, environment templates, compiler and lint settings, developer utilities, and generated analysis support configure the repository."],
  ["layer:infrastructure", "Infrastructure & CI/CD", "Docker Compose services, observability stacks, process definitions, build automation, and GitHub Actions operate and validate Troop across environments."],
  ["layer:documentation", "Documentation", "Project guides, design specifications, operational runbooks, architecture notes, and subsystem references explain how to develop, deploy, and operate Troop."],
];

const normalize = (value) => String(value ?? "").replaceAll("\\", "/").replace(/^\.\//, "");

function isTest(filePath, tags, summary) {
  const base = path.posix.basename(filePath).toLowerCase();
  return /(^test_|\.test\.|\.spec\.|_test\.)/.test(base)
    || /(^|\/)(tests?|e2e|__tests__)(\/|$)/i.test(filePath)
    || tags.has("test") || tags.has("pytest") || tags.has("vitest") || tags.has("playwright")
    || /\b(test suite|test fixtures|regression baseline|evaluation gate)\b/i.test(summary);
}

function assign(node) {
  const filePath = normalize(node.filePath);
  const lower = filePath.toLowerCase();
  const base = path.posix.basename(lower);
  const tags = new Set((node.tags ?? []).map((tag) => String(tag).toLowerCase()));
  const summary = String(node.summary ?? "");

  if (node.type === "document") return "layer:documentation";
  if (node.type === "pipeline" || node.type === "service" || node.type === "resource") return "layer:infrastructure";
  if (lower.startsWith(".github/") || lower.startsWith("infra/") || base.startsWith("docker-compose") || base.startsWith("dockerfile") || base === "procfile.dev") return "layer:infrastructure";

  if (isTest(filePath, tags, summary)
      || lower.startsWith("artifacts/")
      || /^backend\/tools\/(check_|phase\d+_|rag_eval_gate|pgvector_plan_check)/.test(lower)
      || lower === "frontend/scripts/phase0-build-baseline.mjs") return "layer:test";

  if (lower.startsWith("backend/alembic/") || lower.startsWith("backend/db/") || lower === "backend/app.db"
      || /\/(models?|repository)\.py$/.test(lower)
      || tags.has("data-model") || tags.has("repository") || tags.has("orm") || tags.has("data-access")
      || tags.has("vector-store") || /\.(sql|db|sqlite)$/.test(lower)
      || node.type === "table" || node.type === "schema" || node.type === "endpoint") return "layer:data";

  if (lower.startsWith("backend/api/") || /\/(router|schemas)\.py$/.test(lower)
      || tags.has("api-handler") || tags.has("api-schema") || tags.has("routing")) return "layer:backend-api";

  if (lower.startsWith("backend/core/") || lower.startsWith("backend/workers/") || lower.startsWith("backend/app/")
      || base === "celery_app.py" || tags.has("middleware")) return "layer:backend-runtime";

  if (lower.startsWith("backend/modules/") || lower === "backend/__init__.py") return "layer:backend-domain";

  if (lower === "frontend/index.html" || lower === "frontend/src/index.css" || lower === "frontend/src/main.tsx"
      || lower.endsWith(".tsx") || lower.startsWith("frontend/src/components/") || lower.startsWith("frontend/src/pages/")) return "layer:frontend-ui";

  if (lower.startsWith("frontend/src/")) return "layer:frontend-services";

  if (node.type === "config" || lower.startsWith(".understand-anything/") || lower.startsWith("backend/tools/")
      || lower.startsWith("frontend/scripts/") || lower.startsWith("frontend/") || lower.startsWith("backend/")
      || ["makefile.local"].includes(base)) return "layer:config";

  return "layer:config";
}

try {
  const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  const structural = JSON.parse(fs.readFileSync(resultsPath, "utf8"));
  if (!structural.scriptCompleted || structural.fileStats.totalFileNodes !== input.fileNodes.length) {
    throw new Error("Structural analysis results do not match the architecture input");
  }

  const idsByLayer = new Map(definitions.map(([id]) => [id, []]));
  for (const node of input.fileNodes) {
    const layerId = assign(node);
    if (!idsByLayer.has(layerId)) throw new Error(`Unknown layer ${layerId} for ${node.id}`);
    idsByLayer.get(layerId).push(node.id);
  }
  for (const ids of idsByLayer.values()) ids.sort();

  const layers = definitions.map(([id, name, description]) => ({ id, name, description, nodeIds: idsByLayer.get(id) }));
  const assigned = layers.flatMap((layer) => layer.nodeIds);
  const inputIds = input.fileNodes.map((node) => node.id);
  const inputSet = new Set(inputIds);
  const assignedSet = new Set(assigned);
  const missing = inputIds.filter((id) => !assignedSet.has(id));
  const invented = assigned.filter((id) => !inputSet.has(id));
  const duplicates = assigned.filter((id, index) => assigned.indexOf(id) !== index);

  if (layers.length < 3 || layers.length > 10) throw new Error(`Invalid layer count: ${layers.length}`);
  if (layers.some((layer) => layer.nodeIds.length === 0)) throw new Error("Empty layer detected");
  if (assigned.length !== 521 || assignedSet.size !== 521 || missing.length || invented.length || duplicates.length) {
    throw new Error(JSON.stringify({ assigned: assigned.length, unique: assignedSet.size, missing, invented, duplicates }));
  }

  fs.writeFileSync(outputPath, `${JSON.stringify(layers, null, 2)}\n`);
  console.log(JSON.stringify({
    layerCount: layers.length,
    totalAssignments: assigned.length,
    uniqueAssignments: assignedSet.size,
    counts: Object.fromEntries(layers.map((layer) => [layer.name, layer.nodeIds.length])),
  }));
} catch (error) {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exit(1);
}
