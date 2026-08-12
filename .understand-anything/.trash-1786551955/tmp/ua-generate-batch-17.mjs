import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tmp = path.join(root, ".understand-anything/tmp");
const intermediate = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-extract-results-17.json"), "utf8"));
const batches = JSON.parse(fs.readFileSync(path.join(intermediate, "batches.json"), "utf8"));
const batch = batches.batches.find((item) => item.batchIndex === 17);
if (!batch) throw new Error("Batch 17 not found");

const meta = {
  "backend/alembic/env.py": ["Configures Alembic's synchronous offline and asynchronous online migration environments and imports every domain model so autogeneration sees complete SQLAlchemy metadata.", ["database", "migration", "alembic", "configuration"]],
  "backend/modules/ai/__init__.py": ["Marks the AI domain as an importable Python package for application and migration discovery.", ["package", "ai", "python", "entry-point"]],
  "backend/modules/audit/__init__.py": ["Marks the audit domain as an importable Python package for application and migration discovery.", ["package", "audit", "python", "entry-point"]],
  "backend/modules/calendar/__init__.py": ["Marks the calendar domain as an importable Python package for application and migration discovery.", ["package", "calendar", "python", "entry-point"]],
  "backend/modules/companies/__init__.py": ["Marks the companies domain as an importable Python package for application and migration discovery.", ["package", "company", "python", "entry-point"]],
  "backend/modules/identity_access/__init__.py": ["Marks the identity and access domain as an importable Python package for application and migration discovery.", ["package", "identity-access", "python", "entry-point"]],
  "backend/modules/memory/__init__.py": ["Publishes the memory domain's document, vector, semantic, procedural, episodic, ingest-job, and knowledge-link SQLAlchemy models.", ["barrel", "memory", "data-model", "entry-point"]],
  "backend/modules/notifications/__init__.py": ["Marks the notifications domain as an importable Python package for application and migration discovery.", ["package", "notifications", "python", "entry-point"]],
  "backend/modules/orchestration/__init__.py": ["Marks the orchestration domain as an importable Python package for application and migration discovery.", ["package", "orchestration", "python", "entry-point"]],
  "backend/modules/platform/__init__.py": ["Marks the platform domain as an importable Python package for application and migration discovery.", ["package", "platform", "python", "entry-point"]],
  "backend/modules/profile/__init__.py": ["Marks the profile domain as an importable Python package for application and migration discovery.", ["package", "profile", "python", "entry-point"]],
  "backend/modules/projects/__init__.py": ["Marks the projects domain as an importable Python package for application and migration discovery.", ["package", "projects", "python", "entry-point"]],
  "backend/modules/settings/__init__.py": ["Marks the settings domain as an importable Python package for application and migration discovery.", ["package", "settings", "python", "entry-point"]],
  "backend/modules/users/__init__.py": ["Marks the users domain as an importable Python package for application and migration discovery.", ["package", "users", "python", "entry-point"]],
};

const functionSummaries = {
  run_migrations_offline: "Runs migrations without a live engine using literal SQL bindings and the complete model metadata.",
  do_run_migrations: "Configures Alembic on an active connection and executes migrations with type and server-default comparison enabled.",
  run_async_migrations: "Creates a temporary asynchronous migration engine, runs synchronous migration work through its connection, and disposes it.",
  run_migrations_online: "Bridges Alembic's synchronous entry point to the asynchronous online migration workflow.",
};
function complexity(start, end) {
  const lines = end - start + 1;
  return lines > 200 ? "complex" : lines >= 50 ? "moderate" : "simple";
}
function fileComplexity(result) {
  return result.nonEmptyLines > 200 ? "complex" : result.nonEmptyLines >= 50 ? "moderate" : "simple";
}

const nodes = [];
const edges = [];
const ids = new Set();
const edgeKeys = new Set();
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
  for (const fn of result.functions ?? []) {
    const lines = fn.endLine - fn.startLine + 1;
    if (!exports.has(fn.name) && lines < 10) continue;
    const id = `function:${result.path}:${fn.name}`;
    addNode({ id, type: "function", name: fn.name, filePath: result.path, lineRange: [fn.startLine, fn.endLine], summary: functionSummaries[fn.name] ?? `Implements the ${fn.name} migration operation.`, tags: ["database", "migration", "alembic"], complexity: complexity(fn.startLine, fn.endLine) });
    addEdge({ source: fileId, target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(fn.name)) addEdge({ source: fileId, target: id, type: "exports", direction: "forward", weight: 0.8 });
  }
}

for (const [sourcePath, targets] of Object.entries(batch.batchImportData)) {
  for (const targetPath of targets) addEdge({ source: `file:${sourcePath}`, target: `file:${targetPath}`, type: "imports", direction: "forward", weight: 0.7 });
}

for (const result of extraction.results) {
  for (const neighbor of batch.neighborMap[result.path] ?? []) {
    if (neighbor.path.includes("/tests/") || path.basename(neighbor.path).startsWith("test_")) addEdge({ source: `file:${result.path}`, target: `file:${neighbor.path}`, type: "tested_by", direction: "forward", weight: 0.5 });
  }
}

const outputPath = path.join(intermediate, "batch-17.json");
fs.writeFileSync(outputPath, `${JSON.stringify({ nodes, edges }, null, 2)}\n`);

const fragment = JSON.parse(fs.readFileSync(outputPath, "utf8"));
const outputIds = new Set(fragment.nodes.map((node) => node.id));
const allowedFiles = new Set([...Object.keys(batch.batchImportData), ...Object.values(batch.batchImportData).flat(), ...Object.keys(batch.neighborMap), ...Object.values(batch.neighborMap).flatMap((items) => items.map((item) => item.path))]);
for (const edge of fragment.edges) {
  if (!outputIds.has(edge.source)) throw new Error(`Missing source ${edge.source}`);
  if (outputIds.has(edge.target)) continue;
  const fileMatch = /^file:(.+)$/.exec(edge.target);
  if (fileMatch && allowedFiles.has(fileMatch[1])) continue;
  throw new Error(`Unvalidated target ${edge.target}`);
}

process.stdout.write(JSON.stringify({ outputPath, nodeCount: nodes.length, edgeCount: edges.length, filesSkipped: extraction.filesSkipped ?? [] }));
