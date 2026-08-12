import fs from "node:fs";
import path from "node:path";

const [inputPath, outputPath] = process.argv.slice(2);

if (!inputPath || !outputPath) {
  console.error("Usage: node ua-arch-analyze.mjs <ua-arch-input.json> <ua-arch-results.json>");
  process.exit(1);
}

const normalize = (value) => String(value ?? "").replaceAll("\\", "/").replace(/^\.\//, "");
const sortedObject = (entries) => Object.fromEntries([...entries].sort(([a], [b]) => a.localeCompare(b)));

function commonDirectoryPrefix(fileNodes) {
  const directories = fileNodes.map((node) => {
    const parts = normalize(node.filePath).split("/").filter(Boolean);
    return parts.slice(0, -1);
  });
  if (!directories.length) return [];
  const prefix = [];
  for (let index = 0; ; index += 1) {
    const segment = directories[0][index];
    if (segment === undefined || !directories.every((parts) => parts[index] === segment)) break;
    prefix.push(segment);
  }
  return prefix;
}

function flatPattern(filePath) {
  const value = normalize(filePath).toLowerCase();
  const base = path.posix.basename(value);
  if (/((^|\.)test\.|\.spec\.)|(^test_)|(_test\.)/.test(base)) return "test";
  if (/\.(md|rst)$/.test(base)) return "documentation";
  if (/dockerfile|docker-compose|makefile/.test(base)) return "infrastructure";
  if (/config|settings|\.ya?ml$|\.toml$|\.json$/.test(base)) return "config";
  return path.posix.extname(base).slice(1) || "root";
}

function directoryPattern(groupName, filePaths) {
  const exact = new Map([
    ["routes", "api"], ["api", "api"], ["controllers", "api"], ["controller", "api"],
    ["endpoints", "api"], ["handlers", "api"], ["routers", "api"], ["serializers", "api"],
    ["services", "service"], ["core", "service"], ["lib", "service"], ["domain", "service"],
    ["logic", "service"], ["internal", "service"], ["signals", "service"], ["mailers", "service"],
    ["jobs", "service"], ["channels", "service"], ["composables", "service"], ["blueprints", "api"],
    ["models", "data"], ["db", "data"], ["data", "data"], ["persistence", "data"],
    ["repository", "data"], ["entities", "data"], ["entity", "data"], ["migrations", "data"],
    ["sql", "data"], ["database", "data"], ["schema", "data"],
    ["components", "ui"], ["views", "ui"], ["pages", "ui"], ["ui", "ui"],
    ["layouts", "ui"], ["screens", "ui"],
    ["middleware", "middleware"], ["plugins", "middleware"], ["interceptors", "middleware"], ["guards", "middleware"],
    ["utils", "utility"], ["helpers", "utility"], ["common", "utility"], ["shared", "utility"],
    ["tools", "utility"], ["pkg", "utility"], ["templatetags", "utility"],
    ["config", "config"], ["constants", "config"], ["env", "config"], ["settings", "config"],
    ["management", "config"], ["commands", "config"],
    ["__tests__", "test"], ["test", "test"], ["tests", "test"], ["spec", "test"], ["specs", "test"],
    ["types", "types"], ["interfaces", "types"], ["schemas", "types"], ["contracts", "types"],
    ["dtos", "types"], ["dto", "types"], ["request", "types"], ["response", "types"],
    ["hooks", "hooks"], ["store", "state"], ["state", "state"], ["reducers", "state"],
    ["actions", "state"], ["slices", "state"],
    ["assets", "assets"], ["static", "assets"], ["public", "assets"],
    ["cmd", "entry"], ["bin", "entry"],
    ["docs", "documentation"], ["documentation", "documentation"], ["wiki", "documentation"],
    ["deploy", "infrastructure"], ["deployment", "infrastructure"], ["infra", "infrastructure"],
    ["infrastructure", "infrastructure"], ["k8s", "infrastructure"], ["kubernetes", "infrastructure"],
    ["helm", "infrastructure"], ["charts", "infrastructure"], ["terraform", "infrastructure"],
    ["tf", "infrastructure"], ["docker", "infrastructure"],
    [".github", "ci-cd"], [".gitlab", "ci-cd"], [".circleci", "ci-cd"],
  ]);
  const lower = groupName.toLowerCase();
  if (exact.has(lower)) return exact.get(lower);
  const joined = filePaths.map(normalize).join("\n").toLowerCase();
  if (/(^|\/)\.github\/workflows\//m.test(joined)) return "ci-cd";
  if (/(^|\/)(dockerfile|docker-compose)|\.(tf|tfvars)$/m.test(joined)) return "infrastructure";
  if (/\.(md|rst)$/m.test(joined)) return "documentation";
  return "unclassified";
}

function filePattern(filePath) {
  const value = normalize(filePath);
  const lower = value.toLowerCase();
  const base = path.posix.basename(lower);
  if (/((^|\.)test\.|\.spec\.)|(^test_)|(_test\.)/.test(base)) return "test";
  if (base.endsWith(".d.ts")) return "types";
  if (["index.ts", "index.js", "__init__.py"].includes(base)) return "entry";
  if (base === "manage.py" || base === "config.ru") return "entry";
  if (["wsgi.py", "asgi.py"].includes(base)) return "config";
  if (/\/cmd\/[^/]+\/main\.go$/.test(`/${lower}`)) return "entry";
  if (/\/src\/(main|lib)\.rs$/.test(`/${lower}`)) return "entry";
  if (base === "application.java" || base === "program.cs") return "entry";
  if (["cargo.toml", "go.mod", "gemfile", "pom.xml", "build.gradle", "composer.json"].includes(base)) return "config";
  if (base === "dockerfile" || base.startsWith("dockerfile.") || base.startsWith("docker-compose.")) return "infrastructure";
  if (base.endsWith(".tf") || base.endsWith(".tfvars")) return "infrastructure";
  if (lower.startsWith(".github/workflows/") || base === ".gitlab-ci.yml" || base === "jenkinsfile") return "ci-cd";
  if (base.endsWith(".sql")) return "data";
  if (/\.(graphql|gql|proto)$/.test(base)) return "types";
  if (/\.(md|rst)$/.test(base)) return "documentation";
  if (base === "makefile") return "infrastructure";
  return null;
}

try {
  const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  const { fileNodes, importEdges, allEdges } = input;
  if (!Array.isArray(fileNodes) || !Array.isArray(importEdges) || !Array.isArray(allEdges)) {
    throw new Error("Input must contain fileNodes, importEdges, and allEdges arrays");
  }

  const nodesById = new Map(fileNodes.map((node) => [node.id, node]));
  const prefix = commonDirectoryPrefix(fileNodes);
  const provisional = new Map();
  for (const node of fileNodes) {
    const parts = normalize(node.filePath).split("/").filter(Boolean);
    const remaining = parts.slice(prefix.length);
    const group = remaining.length > 1 ? remaining[0] : "root";
    if (!provisional.has(group)) provisional.set(group, []);
    provisional.get(group).push(node.id);
  }
  const isFlat = provisional.size === 1 && provisional.has("root");
  const groups = new Map();
  for (const node of fileNodes) {
    const parts = normalize(node.filePath).split("/").filter(Boolean);
    const remaining = parts.slice(prefix.length);
    const group = isFlat ? flatPattern(node.filePath) : (remaining.length > 1 ? remaining[0] : "root");
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(node.id);
  }
  for (const ids of groups.values()) ids.sort();
  const groupById = new Map();
  for (const [group, ids] of groups) for (const id of ids) groupById.set(id, group);

  const typeGroups = new Map();
  for (const node of fileNodes) {
    if (!typeGroups.has(node.type)) typeGroups.set(node.type, []);
    typeGroups.get(node.type).push(node.id);
  }
  for (const ids of typeGroups.values()) ids.sort();

  const fanIn = new Map(fileNodes.map((node) => [node.id, 0]));
  const fanOut = new Map(fileNodes.map((node) => [node.id, 0]));
  const interImports = new Map();
  const groupImportsFrom = new Map([...groups.keys()].map((group) => [group, new Set()]));
  const groupImportedBy = new Map([...groups.keys()].map((group) => [group, new Set()]));
  const internal = new Map([...groups.keys()].map((group) => [group, 0]));
  const involving = new Map([...groups.keys()].map((group) => [group, 0]));

  for (const edge of importEdges) {
    if (fanOut.has(edge.source)) fanOut.set(edge.source, fanOut.get(edge.source) + 1);
    if (fanIn.has(edge.target)) fanIn.set(edge.target, fanIn.get(edge.target) + 1);
    const sourceGroup = groupById.get(edge.source);
    const targetGroup = groupById.get(edge.target);
    if (!sourceGroup || !targetGroup) continue;
    involving.set(sourceGroup, involving.get(sourceGroup) + 1);
    if (targetGroup !== sourceGroup) involving.set(targetGroup, involving.get(targetGroup) + 1);
    if (sourceGroup === targetGroup) {
      internal.set(sourceGroup, internal.get(sourceGroup) + 1);
    } else {
      const key = `${sourceGroup}\u0000${targetGroup}`;
      interImports.set(key, (interImports.get(key) ?? 0) + 1);
      groupImportsFrom.get(sourceGroup).add(targetGroup);
      groupImportedBy.get(targetGroup).add(sourceGroup);
    }
  }

  const cross = new Map();
  const nonCodeConnections = [];
  for (const edge of allEdges) {
    const source = nodesById.get(edge.source);
    const target = nodesById.get(edge.target);
    if (!source || !target) continue;
    const key = `${source.type}\u0000${target.type}\u0000${edge.type}`;
    cross.set(key, (cross.get(key) ?? 0) + 1);
    if (source.type !== "file" || target.type !== "file") {
      nonCodeConnections.push({ source: edge.source, target: edge.target, edgeType: edge.type });
    }
  }

  const interGroupImports = [...interImports]
    .map(([key, count]) => {
      const [from, to] = key.split("\u0000");
      return { from, to, count };
    })
    .sort((a, b) => b.count - a.count || a.from.localeCompare(b.from) || a.to.localeCompare(b.to));

  const pairKeys = new Set(interGroupImports.map(({ from, to }) => [from, to].sort().join("\u0000")));
  const dependencyDirection = [];
  for (const pairKey of [...pairKeys].sort()) {
    const [a, b] = pairKey.split("\u0000");
    const ab = interImports.get(`${a}\u0000${b}`) ?? 0;
    const ba = interImports.get(`${b}\u0000${a}`) ?? 0;
    if (ab > ba) dependencyDirection.push({ dependent: a, dependsOn: b, forwardCount: ab, reverseCount: ba });
    else if (ba > ab) dependencyDirection.push({ dependent: b, dependsOn: a, forwardCount: ba, reverseCount: ab });
    else dependencyDirection.push({ dependent: a, dependsOn: b, forwardCount: ab, reverseCount: ba, bidirectional: true });
  }

  const nodePaths = fileNodes.map((node) => normalize(node.filePath));
  const infraFiles = nodePaths.filter((filePath) =>
    /(^|\/)(dockerfile(?:\.[^/]*)?|docker-compose[^/]*\.ya?ml|\.github\/workflows\/|k8s\/|kubernetes\/|helm\/|terraform\/)|\.(tf|tfvars)$|jenkinsfile$/i.test(filePath),
  );
  const schemaFiles = nodePaths.filter((filePath) => /\.(sql|graphql|gql|proto|prisma)$/i.test(filePath) || /(^|\/)schema(s)?\//i.test(filePath));
  const migrationFiles = nodePaths.filter((filePath) => /(^|\/)(migrations?|alembic)(\/|$)/i.test(filePath));
  const dataModelFiles = fileNodes.filter((node) =>
    /(^|\/)(models?|entities|db|repository)(\/|\.|$)/i.test(normalize(node.filePath)) || (node.tags ?? []).some((tag) => /data-model|orm/i.test(tag)),
  ).map((node) => normalize(node.filePath));
  const apiHandlerFiles = fileNodes.filter((node) =>
    /(^|\/)(api|routes?|routers?|controllers?|endpoints?|handlers?)(\/|\.|$)/i.test(normalize(node.filePath)) || (node.tags ?? []).some((tag) => /api-handler|routing|endpoint/i.test(tag)),
  ).map((node) => normalize(node.filePath));
  const clientFiles = fileNodes.filter((node) =>
    /(^|\/)(api|services?)\//i.test(normalize(node.filePath)) && /^frontend\//i.test(normalize(node.filePath)),
  ).map((node) => normalize(node.filePath));

  const documentedGroups = new Set();
  for (const node of fileNodes) {
    const filePath = normalize(node.filePath);
    if (node.type !== "document" && !/\.(md|rst)$/i.test(filePath)) continue;
    const ownGroup = groupById.get(node.id);
    if (ownGroup) documentedGroups.add(ownGroup);
    const haystack = `${node.summary ?? ""} ${node.tags?.join(" ") ?? ""}`.toLowerCase();
    for (const group of groups.keys()) if (group !== "root" && haystack.includes(group.toLowerCase())) documentedGroups.add(group);
  }

  const results = {
    scriptCompleted: true,
    commonPathPrefix: prefix.length ? `${prefix.join("/")}/` : "",
    directoryGroups: sortedObject(groups),
    nodeTypeGroups: sortedObject(typeGroups),
    importAdjacency: {
      importsFrom: sortedObject([...groups].map(([group]) => [group, [...groupImportsFrom.get(group)].sort()])),
      importedBy: sortedObject([...groups].map(([group]) => [group, [...groupImportedBy.get(group)].sort()])),
    },
    crossCategoryEdges: [...cross].map(([key, count]) => {
      const [fromType, toType, edgeType] = key.split("\u0000");
      return { fromType, toType, edgeType, count };
    }).sort((a, b) => b.count - a.count || a.fromType.localeCompare(b.fromType) || a.toType.localeCompare(b.toType) || a.edgeType.localeCompare(b.edgeType)),
    nonCodeConnections: nonCodeConnections.sort((a, b) => a.source.localeCompare(b.source) || a.target.localeCompare(b.target)),
    interGroupImports,
    intraGroupDensity: sortedObject([...groups].map(([group]) => {
      const internalEdges = internal.get(group);
      const totalEdges = involving.get(group);
      return [group, { internalEdges, totalEdges, density: totalEdges ? Number((internalEdges / totalEdges).toFixed(4)) : 0 }];
    })),
    patternMatches: sortedObject([...groups].map(([group, ids]) => [
      group,
      directoryPattern(group, ids.map((id) => nodesById.get(id)?.filePath ?? "")),
    ])),
    filePatternMatches: sortedObject(fileNodes.map((node) => [node.id, filePattern(node.filePath)]).filter(([, pattern]) => pattern)),
    deploymentTopology: {
      hasDockerfile: nodePaths.some((value) => /(^|\/)dockerfile(?:\.[^/]*)?$/i.test(value)),
      hasCompose: nodePaths.some((value) => /(^|\/)docker-compose[^/]*\.ya?ml$/i.test(value)),
      hasK8s: nodePaths.some((value) => /(^|\/)(k8s|kubernetes|helm|charts)\//i.test(value)),
      hasTerraform: nodePaths.some((value) => /\.(tf|tfvars)$/i.test(value) || /(^|\/)terraform\//i.test(value)),
      hasCI: nodePaths.some((value) => /(^|\/)\.github\/workflows\//i.test(value) || /(^|\/)(\.gitlab-ci\.ya?ml|jenkinsfile)$/i.test(value)),
      hasMultipleEnvironments: nodePaths.some((value) => /(dev|prod|staging|local)/i.test(path.posix.basename(value)) && /docker|compose|\.env/i.test(value)),
      infraFiles: [...new Set(infraFiles)].sort(),
    },
    dataPipeline: {
      schemaFiles: [...new Set(schemaFiles)].sort(),
      migrationFiles: [...new Set(migrationFiles)].sort(),
      dataModelFiles: [...new Set(dataModelFiles)].sort(),
      apiHandlerFiles: [...new Set(apiHandlerFiles)].sort(),
      clientFiles: [...new Set(clientFiles)].sort(),
    },
    docCoverage: {
      groupsWithDocs: documentedGroups.size,
      totalGroups: groups.size,
      coverageRatio: groups.size ? Number((documentedGroups.size / groups.size).toFixed(4)) : 0,
      documentedGroups: [...documentedGroups].sort(),
      undocumentedGroups: [...groups.keys()].filter((group) => !documentedGroups.has(group)).sort(),
    },
    dependencyDirection,
    fileStats: {
      totalFileNodes: fileNodes.length,
      filesPerGroup: sortedObject([...groups].map(([group, ids]) => [group, ids.length])),
      nodeTypeCounts: sortedObject([...typeGroups].map(([type, ids]) => [type, ids.length])),
      importEdgeCount: importEdges.length,
      allFileLevelEdgeCount: allEdges.length,
    },
    fileFanIn: sortedObject([...fanIn]),
    fileFanOut: sortedObject([...fanOut]),
  };

  fs.writeFileSync(outputPath, `${JSON.stringify(results, null, 2)}\n`);
  console.log(JSON.stringify(results.fileStats));
} catch (error) {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exit(1);
}
