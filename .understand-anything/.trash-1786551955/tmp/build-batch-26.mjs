import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tmp = path.join(root, ".understand-anything/tmp");
const intermediate = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-extract-results-26.json"), "utf8"));
const input = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-analyzer-input-26.json"), "utf8"));

const summaries = {
  ".understand-anything/.understandignore": "Defines the project-specific file and directory patterns excluded from knowledge-graph analysis.",
  ".understand-anything/config.json": "Stores the Understand Anything project preference to generate graph text in English.",
  "artifacts/frontend-build-baseline.json": "Captures a frontend bundle-size baseline with asset counts, total bytes, JavaScript and CSS totals, and largest generated assets.",
  "artifacts/phase0-baseline.json": "Captures the initial runtime baseline across database, HTTP endpoints, process, queue, Redis, revision, and measurement parameters.",
  "backend/__init__.py": "Marks the backend directory as the root Python package.",
  "backend/alembic/README": "Documents that the Alembic environment uses a generic asynchronous single-database configuration.",
  "backend/alembic/script.py.mako": "Defines the Mako template Alembic uses to generate typed migration revision modules with upgrade and downgrade hooks.",
  "backend/alembic/versions/9f2d1b8c4e77_agent_templates_slug_unique.py": "Adds a unique constraint for agent template slugs and provides a reversible downgrade.",
  "backend/alembic/versions/b7c3d9e2a1f4_pgvector_indexes_and_ai_chunk_vectors.py": "Adds pgvector support and vector indexes for AI document chunk similarity queries with a reversible downgrade.",
  "backend/alembic/versions/c1a8fcb8c9aa_add_team_profiles.py": "Creates persistent team profiles and their supporting constraints and indexes.",
  "backend/alembic/versions/d5e6f7a8b9c0_memory_retention_metadata.py": "Adds retention and archival metadata used by the memory lifecycle subsystem.",
  "backend/alembic/versions/e2b7c4d1a0f3_widen_episodic_search_source_id.py": "Widens the episodic search source identifier column and supports reverting its prior width.",
  "backend/alembic/versions/f4bdbfb299ae_generate_tables.py": "Creates the initial Troop relational schema and provides a full reverse-order teardown of generated tables and constraints.",
  "backend/api/__init__.py": "Marks the API directory as a Python package.",
  "backend/api/deps/__init__.py": "Marks the API dependency providers directory as a Python package.",
  "backend/api/middleware/__init__.py": "Marks the API middleware directory as a Python package.",
  "backend/app.db": "Empty SQLite database placeholder used by local backend development defaults.",
  "backend/app/__init__.py": "Marks the application compatibility namespace as a Python package.",
  "backend/app/agents/__init__.py": "Marks the application agent runtime namespace as a Python package.",
  "backend/core/__init__.py": "Marks shared backend infrastructure and configuration utilities as a Python package.",
  "backend/db/__init__.py": "Marks database base, model registration, and session infrastructure as a Python package.",
  "backend/modules/__init__.py": "Marks the backend business modules namespace as a Python package.",
  "backend/modules/admin/__init__.py": "Marks the administrative domain module as a Python package.",
  "backend/modules/observability/exceptions.py": "Defines the configuration error raised when observability setup is invalid.",
  "backend/modules/observability/README.md": "Documents the observability compatibility boundary, instrumentation responsibilities, optional exporters, and bounded metric-label policy."
};

const migrationActions = {
  "9f2d1b8c4e77_agent_templates_slug_unique.py": "the unique agent-template slug constraint",
  "b7c3d9e2a1f4_pgvector_indexes_and_ai_chunk_vectors.py": "pgvector columns and similarity indexes for AI chunks",
  "c1a8fcb8c9aa_add_team_profiles.py": "team profile tables, constraints, and indexes",
  "d5e6f7a8b9c0_memory_retention_metadata.py": "memory retention and archival metadata",
  "e2b7c4d1a0f3_widen_episodic_search_source_id.py": "the widened episodic search source identifier",
  "f4bdbfb299ae_generate_tables.py": "the initial application database schema"
};

const complexity = (lines) => lines > 200 ? "complex" : lines >= 50 ? "moderate" : "simple";
const fileTags = (filePath) => {
  if (filePath.startsWith("backend/alembic/versions/")) return ["database", "migration", "alembic", "schema-change"];
  if (filePath === "backend/alembic/script.py.mako") return ["database", "migration", "template", "alembic"];
  if (filePath === "backend/app.db") return ["database", "sqlite", "development", "placeholder"];
  if (filePath.endsWith("README.md") || filePath.endsWith("/README")) return ["documentation", "backend", "configuration"];
  if (filePath.endsWith("__init__.py")) return ["python-package", "namespace", "backend"];
  if (filePath.endsWith("exceptions.py")) return ["exception", "observability", "configuration"];
  if (filePath.endsWith(".json")) return ["configuration", "baseline", "metrics", "artifact"];
  return ["configuration", "analysis", "ignore-rules"];
};

const nodes = [];
const edges = [];
const ids = new Set();
const addNode = (node) => {
  if (ids.has(node.id)) throw new Error(`Duplicate ${node.id}`);
  ids.add(node.id);
  nodes.push(node);
};
const addEdge = (source, target, type, weight) => edges.push({source, target, type, direction: "forward", weight});
const resultMap = new Map(extraction.results.map((result) => [result.path, result]));

for (const file of input.batchFiles) {
  const result = resultMap.get(file.path);
  if (!result) throw new Error(`Missing result for ${file.path}`);
  const type = file.fileCategory === "config" ? "config" : file.fileCategory === "docs" ? "document" : "file";
  const prefix = type;
  const fileId = `${prefix}:${file.path}`;
  const node = {id: fileId, type, name: path.basename(file.path), filePath: file.path, summary: summaries[file.path], tags: fileTags(file.path), complexity: complexity(result.nonEmptyLines)};
  if (file.path.startsWith("backend/alembic/versions/")) node.languageNotes = "Alembic revision identifiers and down-revision links define a reversible linear migration chain.";
  if (!node.summary) throw new Error(`Missing summary ${file.path}`);
  addNode(node);
  const exportNames = new Set((result.exports ?? []).map((item) => item.name));
  for (const fn of result.functions ?? []) {
    const id = `function:${file.path}:${fn.name}`;
    const action = migrationActions[path.basename(file.path)] ?? "the migration's schema changes";
    const verb = fn.name === "upgrade" ? "Applies" : "Reverts";
    addNode({id, type: "function", name: fn.name, filePath: file.path, lineRange: [fn.startLine, fn.endLine], summary: `${verb} ${action}.`, tags: ["database", "migration", "alembic", fn.name], complexity: complexity(fn.endLine - fn.startLine + 1)});
    addEdge(fileId, id, "contains", 1.0);
    if (exportNames.has(fn.name)) addEdge(fileId, id, "exports", 0.8);
  }
  for (const cls of result.classes ?? []) {
    const id = `class:${file.path}:${cls.name}`;
    addNode({id, type: "class", name: cls.name, filePath: file.path, lineRange: [cls.startLine, cls.endLine], summary: "Signals invalid or unsupported observability configuration during application startup.", tags: ["exception", "observability", "configuration", "error-handling"], complexity: complexity(cls.endLine - cls.startLine + 1)});
    addEdge(fileId, id, "contains", 1.0);
    if (exportNames.has(cls.name)) addEdge(fileId, id, "exports", 0.8);
  }
}

const revisions = [
  ["backend/alembic/versions/9f2d1b8c4e77_agent_templates_slug_unique.py", "backend/alembic/versions/f4bdbfb299ae_generate_tables.py"],
  ["backend/alembic/versions/c1a8fcb8c9aa_add_team_profiles.py", "backend/alembic/versions/9f2d1b8c4e77_agent_templates_slug_unique.py"],
  ["backend/alembic/versions/e2b7c4d1a0f3_widen_episodic_search_source_id.py", "backend/alembic/versions/c1a8fcb8c9aa_add_team_profiles.py"],
  ["backend/alembic/versions/b7c3d9e2a1f4_pgvector_indexes_and_ai_chunk_vectors.py", "backend/alembic/versions/e2b7c4d1a0f3_widen_episodic_search_source_id.py"],
  ["backend/alembic/versions/d5e6f7a8b9c0_memory_retention_metadata.py", "backend/alembic/versions/b7c3d9e2a1f4_pgvector_indexes_and_ai_chunk_vectors.py"]
];
for (const [source, target] of revisions) addEdge(`file:${source}`, `file:${target}`, "depends_on", 0.6);

for (const filePath of Object.keys(migrationActions).map((name) => `backend/alembic/versions/${name}`)) {
  addEdge("file:backend/alembic/script.py.mako", `file:${filePath}`, "configures", 0.6);
}
addEdge("config:artifacts/frontend-build-baseline.json", "config:artifacts/phase0-baseline.json", "related", 0.5);
addEdge("file:.understand-anything/.understandignore", "config:.understand-anything/config.json", "related", 0.5);

const seen = new Set();
const finalEdges = edges.filter((edge) => {
  const key = `${edge.source}\u0000${edge.target}\u0000${edge.type}`;
  if (seen.has(key)) return false;
  seen.add(key);
  return true;
});
const expectedImports = Object.values(input.batchImportData).reduce((sum, values) => sum + values.length, 0);
const actualImports = finalEdges.filter((edge) => edge.type === "imports").length;
if (actualImports !== expectedImports) throw new Error(`Import mismatch ${actualImports}/${expectedImports}`);

const outputPath = path.join(intermediate, "batch-26.json");
fs.writeFileSync(outputPath, `${JSON.stringify({nodes, edges: finalEdges}, null, 2)}\n`);
const parsed = JSON.parse(fs.readFileSync(outputPath, "utf8"));
const nodeIds = new Set(parsed.nodes.map((node) => node.id));
if (parsed.nodes.length > 60 || parsed.edges.length > 120) throw new Error("Single output exceeds split limits");
for (const node of parsed.nodes) {
  if (!node.id || !node.type || !node.name || !node.summary || !node.complexity || !Array.isArray(node.tags) || node.tags.length < 3 || node.tags.length > 5) throw new Error(`Invalid node ${node.id}`);
}
for (const edge of parsed.edges) {
  if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) throw new Error(`Invalid edge ${edge.source} -> ${edge.target}`);
}
console.log(JSON.stringify({file: path.basename(outputPath), nodes: nodes.length, edges: finalEdges.length, imports: actualImports}, null, 2));
