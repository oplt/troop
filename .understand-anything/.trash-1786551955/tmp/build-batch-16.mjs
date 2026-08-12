import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tmp = path.join(root, ".understand-anything/tmp");
const intermediate = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-extract-results-16.json"), "utf8"));
const input = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-analyzer-input-16.json"), "utf8"));
const batches = JSON.parse(fs.readFileSync(path.join(intermediate, "batches.json"), "utf8"));
const batch = batches.batches.find((item) => item.batchIndex === 16);
if (!batch) throw new Error("Batch 16 not found");

const summaries = {
  "frontend/src/components/templates/AgentRegistryPanel.tsx": "Lists registered agents and supports selection, expansion, editing, activation, duplication, and deletion within template workflows.",
  "frontend/src/components/templates/MyTemplatesView.tsx": "Displays the current user's template-backed agent registry in the templates workspace.",
  "frontend/src/components/templates/SkillPackPicker.tsx": "Provides searchable multi-selection of skill packs for an agent or template form.",
  "frontend/src/components/templates/SkillTemplateCard.tsx": "Presents a skill template's metadata and action controls in a reusable catalog card.",
  "frontend/src/components/templates/TeamTemplateCard.tsx": "Presents a team template, member roles, hierarchy summary, and selection actions.",
  "frontend/src/components/templates/TemplateBrowseView.tsx": "Filters and presents agent, team, and skill templates in categorized catalog sections.",
  "frontend/src/components/templates/TemplateBuilderView.tsx": "Implements the agent-template editor with identity, model, skills, markdown, inheritance, validation, and save workflows.",
  "frontend/src/components/templates/TemplateCard.tsx": "Renders an agent template summary with tags, model, capabilities, inheritance, and contextual actions.",
  "frontend/src/components/templates/TemplateDetailDrawer.tsx": "Shows detailed agent template metadata and content in a side drawer with creation or edit actions.",
  "frontend/src/components/templates/TemplateFilterToolbar.tsx": "Provides template search, category, skill, provider, sort, and view-mode controls.",
  "frontend/src/components/templates/TemplateSection.tsx": "Wraps a labeled template group in a shared section card with an optional item count.",
  "frontend/src/components/templates/TemplateTab.tsx": "Coordinates template browsing, building, importing, validation, detail, filtering, CRUD mutations, and skill or team catalog workflows.",
  "frontend/src/components/templates/TemplateTopBar.tsx": "Renders the templates workspace heading and primary create or import actions.",
  "frontend/src/components/templates/TemplateValidationPanel.tsx": "Displays template validation status, errors, warnings, and normalized output feedback.",
  "frontend/src/components/templates/templateBuilderState.ts": "Defines template builder defaults and pure transformations for forms, slugs, inheritance previews, CSV fields, and skill markdown imports.",
  "frontend/src/components/templates/types.ts": "Defines shared template browsing, filtering, layout, and builder state types for the templates feature."
};

const functionSummaries = {
  AgentRegistryPanel: "Renders the agent registry and coordinates selection, expansion, editing, state changes, duplication, and deletion actions.",
  MyTemplatesView: "Hosts the user's agent registry within the personal templates view.",
  SkillPackPicker: "Filters and toggles skill-pack selections for template builder state.",
  SkillTemplateCard: "Renders one skill template with metadata and contextual actions.",
  TeamTemplateCard: "Renders one team template with roles, hierarchy, tags, and selection controls.",
  matchesTemplate: "Checks an agent template against the active search and filter criteria.",
  matchesTeamTemplate: "Checks a team template against the active search and category criteria.",
  matchesSkillTemplate: "Checks a skill template against the active search and category criteria.",
  TemplateBrowseView: "Filters template catalogs and renders matching agent, team, and skill sections.",
  TemplateBuilderView: "Renders and updates the complete agent-template form, validation state, preview, and save actions.",
  TemplateCard: "Renders an agent template summary and its browse, edit, create, or delete actions.",
  TemplateDetailDrawer: "Displays complete template details in a dismissible side drawer.",
  TemplateFilterToolbar: "Edits template search, category, provider, skill, ordering, and layout filters.",
  TemplateSection: "Provides a reusable titled section around a group of template cards.",
  buildSkillForm: "Creates editable skill-pack form state from an existing skill template or defaults.",
  readFileAsText: "Reads an uploaded text file through a promise-based browser file reader.",
  TemplateTab: "Coordinates the templates feature's queries, mutations, browsing, editing, importing, validation, and feedback flows.",
  TemplateTopBar: "Renders the templates title and top-level create and import controls.",
  TemplateValidationPanel: "Renders normalized validation feedback with success, warning, and error states.",
  parseCsv: "Parses a comma-separated form value into normalized non-empty items.",
  mergeUnique: "Merges multiple string collections while preserving unique normalized values.",
  getTemplateBySlug: "Finds a template by its stable slug.",
  buildTemplateBuilderForm: "Builds complete template form state from a stored template or empty defaults.",
  slugifyValue: "Normalizes free text into a stable template slug.",
  createUniqueSlug: "Creates a slug that does not collide with existing template slugs.",
  buildAgentTemplateFromForm: "Converts builder form state into a validated agent template payload.",
  buildInheritancePreview: "Computes inherited, overridden, and effective template fields for preview.",
  parseSkillMarkdownDocument: "Parses a skill markdown document and frontmatter into editable skill-pack form state."
};

const complexity = (lines) => lines > 200 ? "complex" : lines >= 50 ? "moderate" : "simple";
const isComponent = (name) => /^[A-Z]/.test(name);
const fileTags = (filePath) => {
  if (filePath.endsWith("types.ts")) return ["type-definition", "templates", "frontend", "shared"];
  if (filePath.endsWith("templateBuilderState.ts")) return ["state", "data-transformation", "templates", "utility"];
  return ["component", "templates", "react", "user-interface"];
};
const functionTags = (name) => {
  if (isComponent(name)) return ["component", "templates", "react", "interaction"];
  if (/matches/.test(name)) return ["filtering", "search", "templates", "utility"];
  if (/parse|slug|merge|getTemplate/.test(name)) return ["utility", "normalization", "templates", "data-transformation"];
  return ["builder", "templates", "data-transformation", "type-safe"];
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
const entitiesByFile = new Map();

for (const file of input.batchFiles) {
  const result = resultsByPath.get(file.path);
  if (!result) throw new Error(`Missing extraction result for ${file.path}`);
  const fileId = `file:${file.path}`;
  const fileNode = {id: fileId, type: "file", name: path.basename(file.path), filePath: file.path, summary: summaries[file.path], tags: fileTags(file.path), complexity: complexity(result.nonEmptyLines)};
  if (file.path.endsWith(".tsx")) fileNode.languageNotes = "Typed React components communicate through explicit props and keep catalog interactions localized to the templates feature.";
  if (!fileNode.summary) throw new Error(`Missing summary for ${file.path}`);
  addNode(fileNode);
  const exportNames = new Set((result.exports ?? []).map((item) => item.name));
  const entities = new Map();
  for (const fn of result.functions ?? []) {
    const lineCount = fn.endLine - fn.startLine + 1;
    if (lineCount < 10 && !exportNames.has(fn.name)) continue;
    const id = `function:${file.path}:${fn.name}`;
    entities.set(fn.name, id);
    addNode({id, type: "function", name: fn.name, filePath: file.path, lineRange: [fn.startLine, fn.endLine], summary: functionSummaries[fn.name] ?? `${fn.name} helper for template feature state.`, tags: functionTags(fn.name), complexity: complexity(lineCount)});
    addEdge(fileId, id, "contains", 1.0);
    if (exportNames.has(fn.name)) addEdge(fileId, id, "exports", 0.8);
  }
  entitiesByFile.set(file.path, entities);
}

for (const [sourcePath, targets] of Object.entries(input.batchImportData)) {
  for (const targetPath of targets) addEdge(`file:${sourcePath}`, `file:${targetPath}`, "imports", 0.7);
}

for (const result of extraction.results) {
  const local = entitiesByFile.get(result.path);
  const imported = new Map();
  for (const importedPath of input.batchImportData[result.path] ?? []) {
    for (const [symbol, id] of entitiesByFile.get(importedPath) ?? []) imported.set(symbol, id);
  }
  const neighbors = new Map();
  for (const neighbor of batch.neighborMap[result.path] ?? []) {
    for (const symbol of neighbor.symbols ?? []) neighbors.set(symbol, `function:${neighbor.path}:${symbol}`);
  }
  for (const call of result.callGraph ?? []) {
    const source = local.get(call.caller);
    if (!source) continue;
    const target = local.get(call.callee) ?? imported.get(call.callee) ?? neighbors.get(call.callee);
    if (target && source !== target) addEdge(source, target, "calls", 0.8);
  }
}

const containment = [
  ["frontend/src/components/templates/MyTemplatesView.tsx", "MyTemplatesView", "frontend/src/components/templates/AgentRegistryPanel.tsx", "AgentRegistryPanel"],
  ["frontend/src/components/templates/TemplateBrowseView.tsx", "TemplateBrowseView", "frontend/src/components/templates/TemplateCard.tsx", "TemplateCard"],
  ["frontend/src/components/templates/TemplateBrowseView.tsx", "TemplateBrowseView", "frontend/src/components/templates/TeamTemplateCard.tsx", "TeamTemplateCard"],
  ["frontend/src/components/templates/TemplateBrowseView.tsx", "TemplateBrowseView", "frontend/src/components/templates/SkillTemplateCard.tsx", "SkillTemplateCard"],
  ["frontend/src/components/templates/TemplateBrowseView.tsx", "TemplateBrowseView", "frontend/src/components/templates/TemplateSection.tsx", "TemplateSection"],
  ["frontend/src/components/templates/TemplateBuilderView.tsx", "TemplateBuilderView", "frontend/src/components/templates/AgentRegistryPanel.tsx", "AgentRegistryPanel"],
  ["frontend/src/components/templates/TemplateBuilderView.tsx", "TemplateBuilderView", "frontend/src/components/templates/SkillPackPicker.tsx", "SkillPackPicker"],
  ["frontend/src/components/templates/TemplateBuilderView.tsx", "TemplateBuilderView", "frontend/src/components/templates/TemplateSection.tsx", "TemplateSection"],
  ["frontend/src/components/templates/TemplateBuilderView.tsx", "TemplateBuilderView", "frontend/src/components/templates/TemplateValidationPanel.tsx", "TemplateValidationPanel"],
  ["frontend/src/components/templates/TemplateTab.tsx", "TemplateTab", "frontend/src/components/templates/TemplateBrowseView.tsx", "TemplateBrowseView"],
  ["frontend/src/components/templates/TemplateTab.tsx", "TemplateTab", "frontend/src/components/templates/TemplateBuilderView.tsx", "TemplateBuilderView"],
  ["frontend/src/components/templates/TemplateTab.tsx", "TemplateTab", "frontend/src/components/templates/TemplateDetailDrawer.tsx", "TemplateDetailDrawer"],
  ["frontend/src/components/templates/TemplateTab.tsx", "TemplateTab", "frontend/src/components/templates/TemplateFilterToolbar.tsx", "TemplateFilterToolbar"],
  ["frontend/src/components/templates/TemplateTab.tsx", "TemplateTab", "frontend/src/components/templates/TemplateTopBar.tsx", "TemplateTopBar"]
];
for (const [sourcePath, sourceName, targetPath, targetName] of containment) {
  const source = entitiesByFile.get(sourcePath)?.get(sourceName);
  const target = entitiesByFile.get(targetPath)?.get(targetName);
  if (!source || !target) throw new Error(`Missing containment ${sourceName} -> ${targetName}`);
  addEdge(source, target, "contains", 1.0);
}

for (const [sourcePath, neighbors] of Object.entries(batch.neighborMap)) {
  for (const neighbor of neighbors) if (neighbor.path.includes(".test.")) addEdge(`file:${sourcePath}`, `file:${neighbor.path}`, "tested_by", 0.5);
}

const seen = new Set();
const finalEdges = edges.filter((edge) => {
  const key = `${edge.source}\u0000${edge.target}\u0000${edge.type}`;
  if (seen.has(key)) return false;
  seen.add(key);
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
  const outputPath = path.join(intermediate, partCount === 1 ? "batch-16.json" : `batch-16-part-${index + 1}.json`);
  fs.writeFileSync(outputPath, `${JSON.stringify({nodes: partNodes, edges: partEdges}, null, 2)}\n`);
  parts.push({outputPath, nodes: partNodes.length, edges: partEdges.length, files: fileSet.size});
}
if (parts.reduce((sum, item) => sum + item.nodes, 0) !== nodes.length) throw new Error("Node partition mismatch");
if (parts.reduce((sum, item) => sum + item.edges, 0) !== finalEdges.length) throw new Error("Edge partition mismatch");

const allNodeIds = new Set(nodes.map((node) => node.id));
const importedPaths = new Set(Object.values(input.batchImportData).flat());
const neighborPaths = new Set(Object.values(batch.neighborMap).flat().map((item) => item.path));
const neighborEntityIds = new Set();
for (const neighbors of Object.values(batch.neighborMap)) for (const neighbor of neighbors) for (const symbol of neighbor.symbols ?? []) neighborEntityIds.add(`function:${neighbor.path}:${symbol}`);
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
