import fs from "node:fs";

const root = "/home/polat/Desktop/Projects/troop/.understand-anything/intermediate";
const graph = JSON.parse(fs.readFileSync(`${root}/assembled-graph.json`, "utf8"));
const scan = JSON.parse(fs.readFileSync(`${root}/scan-result.json`, "utf8"));
const nodeIds = new Set(graph.nodes.map((node) => node.id));
const duplicateNodeIds = graph.nodes.length - nodeIds.size;
const validTypes = new Set(["file", "function", "class", "module", "concept", "config", "document", "service", "table", "endpoint", "pipeline", "schema", "resource"]);
const validComplexities = new Set(["simple", "moderate", "complex"]);
const unknownTypes = graph.nodes.filter((node) => !validTypes.has(node.type)).map((node) => ({ id: node.id, type: node.type }));
const unknownComplexities = graph.nodes.filter((node) => !validComplexities.has(node.complexity)).map((node) => ({ id: node.id, complexity: node.complexity }));
const missingIds = graph.nodes.filter((node) => !node.id);
const danglingEdges = graph.edges.filter((edge) => !nodeIds.has(edge.source) || !nodeIds.has(edge.target));
const selfEdges = graph.edges.filter((edge) => edge.source === edge.target);
const edgeKeys = new Set();
const duplicateEdges = [];
for (const edge of graph.edges) {
  const key = `${edge.source}\0${edge.target}\0${edge.type}`;
  if (edgeKeys.has(key)) duplicateEdges.push(edge);
  edgeKeys.add(key);
}

const actualImports = new Set(
  graph.edges.filter((edge) => edge.type === "imports").map((edge) => `${edge.source}\0${edge.target}`),
);
const expectedImports = [];
const selfImportsInMap = [];
for (const [sourcePath, targetPaths] of Object.entries(scan.importMap)) {
  for (const targetPath of targetPaths) {
    if (sourcePath === targetPath) {
      selfImportsInMap.push(sourcePath);
      continue;
    }
    expectedImports.push(`file:${sourcePath}\0file:${targetPath}`);
  }
}
const expectedSet = new Set(expectedImports);
const missingImports = [...expectedSet].filter((key) => !actualImports.has(key));
const extraImports = [...actualImports].filter((key) => !expectedSet.has(key));

const fileLevelTypes = new Set(["file", "config", "document", "service", "pipeline", "table", "schema", "resource", "endpoint"]);
const nodePaths = new Set(graph.nodes.filter((node) => fileLevelTypes.has(node.type)).map((node) => node.filePath));
const missingFileNodes = scan.files.filter((file) => !nodePaths.has(file.path)).map((file) => file.path);
const unknownFileNodes = [...nodePaths].filter((filePath) => !scan.files.some((file) => file.path === filePath));

process.stdout.write(JSON.stringify({
  nodes: graph.nodes.length,
  edges: graph.edges.length,
  duplicateNodeIds,
  duplicateEdges: duplicateEdges.length,
  unknownTypes,
  unknownComplexities,
  missingIds: missingIds.length,
  danglingEdges: danglingEdges.length,
  selfEdges,
  importMapEdges: Object.values(scan.importMap).flat().length,
  expectedNonSelfImports: expectedSet.size,
  actualImports: actualImports.size,
  selfImportsInMap,
  missingImports,
  extraImports,
  missingFileNodes,
  unknownFileNodes,
}, null, 2));
