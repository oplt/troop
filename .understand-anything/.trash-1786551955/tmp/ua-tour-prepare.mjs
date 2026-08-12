import fs from "node:fs";

const [graphPath, layersPath, outputPath] = process.argv.slice(2);
if (!graphPath || !layersPath || !outputPath) {
  console.error("Usage: node ua-tour-prepare.mjs <graph.json> <layers.json> <input.json>");
  process.exit(1);
}

try {
  const graph = JSON.parse(fs.readFileSync(graphPath, "utf8"));
  const sourceLayers = JSON.parse(fs.readFileSync(layersPath, "utf8"));
  const acceptedTypes = new Set(["file", "config", "document", "service", "pipeline", "table", "schema", "resource", "endpoint"]);
  const nodes = graph.nodes
    .filter((node) => acceptedTypes.has(node.type))
    .map(({ id, name, filePath, summary, type }) => ({ id, name, filePath, summary, type }));
  const ids = new Set(nodes.map((node) => node.id));
  const edges = graph.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  const layers = sourceLayers.map(({ id, name, description }) => ({ id, name, description }));
  if (nodes.length !== 521 || ids.size !== 521) throw new Error(`Expected 521 unique file nodes, got ${nodes.length}/${ids.size}`);
  fs.writeFileSync(outputPath, `${JSON.stringify({ nodes, edges, layers }, null, 2)}\n`);
  console.log(JSON.stringify({ nodes: nodes.length, edges: edges.length, layers: layers.length }));
} catch (error) {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exit(1);
}
