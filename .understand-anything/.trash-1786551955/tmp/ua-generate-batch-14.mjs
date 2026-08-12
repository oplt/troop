import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tmp = path.join(root, ".understand-anything/tmp");
const intermediate = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-extract-results-14.json"), "utf8"));
const batches = JSON.parse(fs.readFileSync(path.join(intermediate, "batches.json"), "utf8"));
const batch = batches.batches.find((item) => item.batchIndex === 14);
if (!batch) throw new Error("Batch 14 not found");

const meta = {
  "frontend/src/features/agentTemplateImport/AgentTemplateImportReviewDrawer.tsx": ["Renders an agent-template import review workflow for inspecting parsed fields, warnings, confidence, unmatched sections, and tool mappings before continuing.", ["component", "agent-template", "import", "validation"]],
  "frontend/src/features/agentTemplateImport/parser.test.ts": ["Verifies agent-template Markdown and frontmatter parsing, inference, issue generation, tool resolution, field updates, and form conversion.", ["test", "parser", "agent-template", "vitest"]],
  "frontend/src/features/agentTemplateImport/parser.ts": ["Parses flexible agent-template Markdown and YAML frontmatter into validated drafts with inferred capabilities, confidence, issues, unmatched sections, and tool mappings.", ["parser", "agent-template", "markdown", "validation"]],
  "frontend/src/features/agentTemplateImport/schema.ts": ["Defines Zod schemas and cross-field validation for parsed agent-template import drafts, issues, and unmatched sections.", ["schema-definition", "zod", "agent-template", "validation"]],
  "frontend/src/features/agentTemplateImport/types.ts": ["Defines the agent-template import draft, parsed content, issue, confidence, source, resolution, and target-field type contracts.", ["type-definition", "agent-template", "import", "typescript"]],
  "frontend/src/features/agentTemplates/formState.ts": ["Converts between editable agent-template form state and API payloads while normalizing lists and enforcing unique slugs.", ["form-state", "agent-template", "validation", "serialization"]],
  "frontend/src/features/hierarchy/api.ts": ["Provides the hierarchy feature with a focused facade over the broader orchestration API client.", ["api-client", "hierarchy", "orchestration", "barrel"]],
  "frontend/src/features/hierarchy/graph/graphSignature.test.ts": ["Verifies stable hierarchy graph signatures across nodes, edges, and relevant state changes.", ["test", "hierarchy", "graph", "vitest"]],
  "frontend/src/features/hierarchy/graph/graphSignature.ts": ["Computes a stable lightweight signature for hierarchy graph nodes and edges to detect meaningful state changes.", ["hierarchy", "graph", "state", "utility"]],
  "frontend/src/features/hierarchy/graph/useHierarchyGraphState.ts": ["Owns editable hierarchy nodes and edges and exposes a reset operation for replacing the current graph.", ["hook", "hierarchy", "graph", "state-management"]],
  "frontend/src/features/hierarchy/queries.ts": ["Composes the hierarchy feature's TanStack Query requests for projects, agents, templates, skills, providers, and live operating state.", ["hook", "hierarchy", "react-query", "data-fetching"]],
  "frontend/src/features/hierarchy/templates/templateState.test.ts": ["Verifies conversion from persisted skill and team templates into editable hierarchy form state.", ["test", "hierarchy", "templates", "vitest"]],
  "frontend/src/features/hierarchy/templates/templateState.ts": ["Builds editable skill and team-template form state and deduplicates associated string lists.", ["form-state", "hierarchy", "templates", "serialization"]],
  "frontend/src/features/hierarchy/validation.test.ts": ["Verifies hierarchy validation for structural, provider, connectivity, and configuration issues.", ["test", "hierarchy", "validation", "vitest"]],
  "frontend/src/features/hierarchy/validation.ts": ["Analyzes hierarchy nodes and edges for missing managers, invalid connections, provider gaps, duplicate identifiers, and incomplete runtime configuration.", ["hierarchy", "validation", "graph", "quality"]],
  "frontend/src/features/skillTemplateImport/SkillTemplateImportReviewDrawer.tsx": ["Renders a skill-template import review workflow for parsed fields, warnings, confidence, unmatched sections, and tool resolution.", ["component", "skill-template", "import", "validation"]],
  "frontend/src/features/skillTemplateImport/parser.test.ts": ["Verifies skill-template Markdown parsing, issue detection, unmatched-section handling, tool mapping, and form conversion.", ["test", "parser", "skill-template", "vitest"]],
  "frontend/src/features/skillTemplateImport/parser.ts": ["Parses skill-template Markdown into validated editable drafts with confidence, issues, unmatched sections, tool canonicalization, and field-update helpers.", ["parser", "skill-template", "markdown", "validation"]],
  "frontend/src/features/skillTemplateImport/types.ts": ["Defines the skill-template import draft, issue, source, confidence, parsed-field, and mapping type contracts.", ["type-definition", "skill-template", "import", "typescript"]],
  "frontend/src/pages/HierarchyPage.tsx": ["Implements the full agent library and hierarchy builder with template import, graph editing, validation, live status, team composition, provider settings, persistence, and runtime controls.", ["page", "hierarchy", "agent-template", "graph-editor"]],
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
  if (filePath.includes("agentTemplateImport/parser")) return ["parser", "agent-template", "validation"];
  if (filePath.includes("skillTemplateImport/parser")) return ["parser", "skill-template", "validation"];
  if (filePath.includes("/schema.ts") || filePath.includes("/validation.ts")) return ["validation", "schema-definition", "hierarchy"];
  if (filePath.includes("/formState.ts") || filePath.includes("/templateState.ts")) return ["form-state", "templates", "serialization"];
  if (filePath.includes("/graph/")) return [name.startsWith("use") ? "hook" : "graph", "hierarchy", "state-management"];
  if (filePath.includes("/queries.ts")) return ["hook", "react-query", "hierarchy"];
  if (filePath.includes("ReviewDrawer")) return ["component", "import", "validation"];
  if (filePath.includes("/pages/")) return [/^[A-Z]/.test(name) ? "component" : "utility", "hierarchy", "graph-editor"];
  return ["frontend", "typescript", "utility"];
}
function functionSummary(filePath, name) {
  const label = human(name);
  if (name === "AgentTemplateImportReviewDrawer") return "Renders the interactive agent-template import review and resolution drawer.";
  if (name === "SkillTemplateImportReviewDrawer") return "Renders the interactive skill-template import review and resolution drawer.";
  if (name === "AgentLibraryPage") return "Renders and coordinates the complete agent library and hierarchy-building workspace.";
  if (/^[A-Z]/.test(name)) return `Renders the ${label} hierarchy interface.`;
  if (filePath.includes("/parser.ts")) return `Implements ${label} within the template Markdown parsing and import pipeline.`;
  if (filePath.includes("/schema.ts") || filePath.includes("/validation.ts")) return `Validates ${label} for imported templates or hierarchy graphs.`;
  if (filePath.includes("/formState.ts") || filePath.includes("/templateState.ts")) return `Builds or normalizes ${label} template form state.`;
  if (name.startsWith("use")) return `Provides the ${label} React hook for hierarchy state and server data.`;
  if (filePath.includes("/graph/")) return `Computes ${label} for the editable hierarchy graph.`;
  if (filePath.includes("/pages/")) return `Implements ${label} behavior for the hierarchy builder.`;
  return `Implements ${label} for the frontend feature.`;
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
    if (neighbor.path.includes(".test.") || neighbor.path.includes(".spec.")) addEdge({ source: `file:${result.path}`, target: `file:${neighbor.path}`, type: "tested_by", direction: "forward", weight: 0.5 });
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
  const outputPath = path.join(intermediate, `batch-14-part-${index + 1}.json`);
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
