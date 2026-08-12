import fs from "node:fs";
import path from "node:path";

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  console.error("Usage: node ua-tour-analyze.mjs <input.json> <results.json>");
  process.exit(1);
}

const normalize = (value) => String(value ?? "").replaceAll("\\", "/").replace(/^\.\//, "");

try {
  const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  const { nodes, edges, layers } = input;
  if (!Array.isArray(nodes) || !Array.isArray(edges) || !Array.isArray(layers)) throw new Error("Invalid topology input");
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const fanIn = new Map(nodes.map((node) => [node.id, 0]));
  const fanOut = new Map(nodes.map((node) => [node.id, 0]));
  for (const edge of edges) {
    fanOut.set(edge.source, (fanOut.get(edge.source) ?? 0) + 1);
    fanIn.set(edge.target, (fanIn.get(edge.target) ?? 0) + 1);
  }
  const rank = (counts, label) => [...counts]
    .map(([id, value]) => ({ id, [label]: value, name: byId.get(id)?.name ?? id }))
    .sort((a, b) => b[label] - a[label] || a.id.localeCompare(b.id));
  const fanInAll = rank(fanIn, "fanIn");
  const fanOutAll = rank(fanOut, "fanOut");
  const topOutIds = new Set(fanOutAll.slice(0, Math.max(1, Math.ceil(nodes.length * 0.1))).map((item) => item.id));
  const lowInIds = new Set([...fanIn]
    .sort((a, b) => a[1] - b[1] || a[0].localeCompare(b[0]))
    .slice(0, Math.max(1, Math.ceil(nodes.length * 0.25)))
    .map(([id]) => id));
  const codeEntryNames = new Set([
    "index.ts", "index.js", "main.ts", "main.js", "app.ts", "app.js", "server.ts", "server.js", "mod.rs",
    "main.go", "main.py", "main.rs", "manage.py", "app.py", "wsgi.py", "asgi.py", "run.py", "__main__.py",
    "application.java", "main.java", "program.cs", "config.ru", "index.php", "app.swift", "application.kt", "main.cpp", "main.c",
  ]);
  const entryPointCandidates = nodes.map((node) => {
    const filePath = normalize(node.filePath);
    const base = path.posix.basename(filePath).toLowerCase();
    const depth = filePath.split("/").filter(Boolean).length;
    let score = 0;
    if (node.type === "document") {
      if (filePath === "README.md") score += 5;
      else if (depth === 1 && /\.md$/i.test(filePath)) score += 2;
    } else if (node.type === "file") {
      if (codeEntryNames.has(base)) score += 3;
      if (depth <= 2) score += 1;
      if (topOutIds.has(node.id)) score += 1;
      if (lowInIds.has(node.id)) score += 1;
    }
    return { id: node.id, score, name: node.name, summary: node.summary, type: node.type, fanIn: fanIn.get(node.id), fanOut: fanOut.get(node.id) };
  }).filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || b.fanOut - a.fanOut || a.id.localeCompare(b.id))
    .slice(0, 5);

  const codeStart = entryPointCandidates.find((item) => item.type === "file")
    ?? nodes.filter((node) => node.type === "file").map((node) => ({ ...node, fanOut: fanOut.get(node.id) ?? 0 }))
      .sort((a, b) => b.fanOut - a.fanOut || a.id.localeCompare(b.id))[0];
  const adjacency = new Map(nodes.map((node) => [node.id, []]));
  for (const edge of edges) {
    if ((edge.type === "imports" || edge.type === "calls") && adjacency.has(edge.source)) adjacency.get(edge.source).push(edge.target);
  }
  for (const targets of adjacency.values()) targets.sort();
  const order = [];
  const depthMap = {};
  const byDepth = {};
  if (codeStart) {
    const queue = [codeStart.id];
    depthMap[codeStart.id] = 0;
    while (queue.length) {
      const current = queue.shift();
      order.push(current);
      const depth = depthMap[current];
      (byDepth[depth] ??= []).push(current);
      for (const target of adjacency.get(current) ?? []) {
        if (!(target in depthMap)) {
          depthMap[target] = depth + 1;
          queue.push(target);
        }
      }
    }
  }

  const inventory = { documentation: [], infrastructure: [], data: [], config: [] };
  for (const node of nodes) {
    const item = { id: node.id, name: node.name, type: node.type, summary: node.summary };
    if (node.type === "document") inventory.documentation.push(item);
    else if (["service", "pipeline", "resource"].includes(node.type)) inventory.infrastructure.push(item);
    else if (["table", "schema", "endpoint"].includes(node.type)) inventory.data.push(item);
    else if (node.type === "config") inventory.config.push(item);
  }
  for (const values of Object.values(inventory)) values.sort((a, b) => a.id.localeCompare(b.id));

  const relevant = edges.filter((edge) => edge.type === "imports" || edge.type === "calls");
  const directed = new Set(relevant.map((edge) => `${edge.source}\u0000${edge.target}`));
  const candidatePairs = [];
  for (const edge of relevant) {
    if (edge.source < edge.target && directed.has(`${edge.target}\u0000${edge.source}`)) candidatePairs.push([edge.source, edge.target]);
  }
  const clusters = [];
  const seenCluster = new Set();
  for (const pair of candidatePairs.sort((a, b) => a.join().localeCompare(b.join()))) {
    const cluster = new Set(pair);
    let expanded = true;
    while (expanded && cluster.size < 5) {
      expanded = false;
      const candidates = nodes.map((node) => node.id).filter((id) => !cluster.has(id)).map((id) => {
        const connected = [...cluster].filter((member) => directed.has(`${id}\u0000${member}`) || directed.has(`${member}\u0000${id}`)).length;
        return { id, connected };
      }).filter((item) => item.connected >= 2).sort((a, b) => b.connected - a.connected || a.id.localeCompare(b.id));
      if (candidates.length) { cluster.add(candidates[0].id); expanded = true; }
    }
    const clusterNodes = [...cluster].sort();
    const signature = clusterNodes.join("\u0000");
    if (seenCluster.has(signature)) continue;
    seenCluster.add(signature);
    const edgeCount = relevant.filter((edge) => cluster.has(edge.source) && cluster.has(edge.target)).length;
    clusters.push({ nodes: clusterNodes, edgeCount });
  }
  clusters.sort((a, b) => b.edgeCount - a.edgeCount || b.nodes.length - a.nodes.length || a.nodes[0].localeCompare(b.nodes[0]));

  const nodeSummaryIndex = Object.fromEntries(nodes.sort((a, b) => a.id.localeCompare(b.id)).map((node) => [
    node.id,
    { name: node.name, type: node.type, summary: node.summary, filePath: node.filePath },
  ]));
  const results = {
    scriptCompleted: true,
    entryPointCandidates,
    fanInRanking: fanInAll.slice(0, 20),
    fanOutRanking: fanOutAll.slice(0, 20),
    bfsTraversal: { startNode: codeStart?.id ?? null, order, depthMap, byDepth },
    nonCodeFiles: inventory,
    clusters: clusters.slice(0, 10),
    layers: { count: layers.length, list: layers },
    nodeSummaryIndex,
    totalNodes: nodes.length,
    totalEdges: edges.length,
  };
  fs.writeFileSync(outputPath, `${JSON.stringify(results, null, 2)}\n`);
  console.log(JSON.stringify({ totalNodes: results.totalNodes, totalEdges: results.totalEdges, startNode: results.bfsTraversal.startNode, reached: order.length, clusters: results.clusters.length }));
} catch (error) {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exit(1);
}
