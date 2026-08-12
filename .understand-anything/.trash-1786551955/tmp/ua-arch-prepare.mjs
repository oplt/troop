import fs from "node:fs";

const [graphPath, outputPath] = process.argv.slice(2);

if (!graphPath || !outputPath) {
  console.error("Usage: node ua-arch-prepare.mjs <assembled-graph.json> <ua-arch-input.json>");
  process.exit(1);
}

try {
  const graph = JSON.parse(fs.readFileSync(graphPath, "utf8"));
  const fileTypes = new Set([
    "file",
    "config",
    "document",
    "service",
    "pipeline",
    "table",
    "schema",
    "resource",
    "endpoint",
  ]);
  const fileNodes = graph.nodes
    .filter((node) => fileTypes.has(node.type))
    .map(({ id, type, name, filePath, summary, tags }) => ({
      id,
      type,
      name,
      filePath,
      summary,
      tags,
    }));
  const fileIds = new Set(fileNodes.map((node) => node.id));
  const importEdges = graph.edges.filter((edge) => edge.type === "imports");
  const allEdges = graph.edges.filter(
    (edge) => fileIds.has(edge.source) && fileIds.has(edge.target),
  );

  if (fileNodes.length !== 521) {
    throw new Error(`Expected 521 file-level nodes, found ${fileNodes.length}`);
  }
  if (new Set(fileNodes.map((node) => node.id)).size !== fileNodes.length) {
    throw new Error("Duplicate file-level node IDs detected");
  }
  fs.writeFileSync(
    outputPath,
    `${JSON.stringify({ fileNodes, importEdges, allEdges }, null, 2)}\n`,
  );
  console.log(
    JSON.stringify({
      fileNodes: fileNodes.length,
      importEdges: importEdges.length,
      allEdges: allEdges.length,
    }),
  );
} catch (error) {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exit(1);
}
