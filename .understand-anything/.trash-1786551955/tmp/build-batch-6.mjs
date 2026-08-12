import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tmp = path.join(root, ".understand-anything/tmp");
const intermediate = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-extract-results-6.json"), "utf8"));
const input = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-analyzer-input-6.json"), "utf8"));
const batches = JSON.parse(fs.readFileSync(path.join(intermediate, "batches.json"), "utf8"));
const batch = batches.batches.find((value) => value.batchIndex === 6);
if (!batch) throw new Error("Batch 6 not found");

const summaries = {
  "backend/modules/orchestration/services/knowledge_domain.py": "Provides a focused knowledge facade that delegates document and project-memory operations to the shared memory service.",
  "backend/modules/orchestration/services/memory_domain.py": "Composes the mixins needed for working, semantic, episodic, and project-scoped memory orchestration.",
  "backend/modules/orchestration/services/routing_service.py": "Implements policy-aware agent routing, capability filtering, worker ranking, delegation safeguards, parallel branch execution, and reviewer selection.",
  "backend/modules/orchestration/services/service.py": "Builds the primary orchestration facade by combining project, task, team, run-query, and domain-specific services behind one session-bound API.",
  "backend/modules/orchestration/workflow_templates.py": "Defines the built-in workflow template catalog and its supported execution defaults for common orchestration patterns.",
  "backend/modules/projects/orchestration_models.py": "Defines project, task, dependency, repository link, comment, artifact, milestone, decision, and portfolio policy persistence models.",
  "backend/modules/projects/orchestration_repository.py": "Provides bounded persistence operations for orchestration projects, tasks, dependencies, repositories, comments, artifacts, decisions, milestones, and portfolio summaries.",
  "backend/modules/projects/service.py": "Implements project lifecycle, hierarchy, membership, repository workspace, indexing, portfolio, live snapshot, configuration, and bootstrap business workflows.",
  "backend/modules/projects/tasks_service.py": "Implements task lifecycle, DAG scheduling, work sessions, merge resolution, SLA escalation, comments, artifacts, decomposition, evidence, and acceptance checking.",
  "backend/modules/team/__init__.py": "Exposes the team module's public agent, template, skill-pack, profile, membership, repository, and service types.",
  "backend/modules/team/models.py": "Defines persistent agents, versions, skill packs, team profiles, template catalogs, and project-agent memberships.",
  "backend/modules/team/repository.py": "Provides database access for agents, versions, skill packs, templates, profiles, and project memberships.",
  "backend/modules/team/service.py": "Implements agent registry, markdown contracts, inheritance, linting, templates, skill packs, profiles, duplication, hierarchy, and catalog seeding.",
  "backend/tests/test_agent_registry_contract.py": "Verifies that agent markdown normalization and model mapping preserve the complete registry contract.",
  "backend/tests/test_architectural_improvements.py": "Guards architectural single sources of truth and verifies vector retrieval remains preferred over fallback repository search.",
  "backend/tests/test_bounded_queries.py": "Verifies configured query limits and bounded run-event retrieval paths.",
  "backend/tests/test_brainstorm_contract.py": "Verifies brainstorming guardrail normalization and discourse metrics for conflict and repetition.",
  "backend/tests/test_deerflow_adapters.py": "Verifies DeerFlow-compatible agent markdown, risky-tool approval metadata, and workspace path safety.",
  "backend/tests/test_github_webhook.py": "Exercises GitHub webhook signature validation, delivery idempotency, replay behavior, and pull-request issue resolution.",
  "backend/tests/test_hierarchy_policy.py": "Verifies hierarchy policy migration, membership and cycle validation, runtime compatibility, and reviewer-chain invariants.",
  "backend/tests/test_hitl_policy.py": "Verifies protected-action approval gates, operating mode normalization, security validation, and payload redaction.",
  "backend/tests/test_orchestration_domain_services.py": "Verifies orchestration facade composition, domain delegation, shared sessions, and knowledge-to-memory forwarding.",
  "backend/tests/test_phase3_query_paths.py": "Guards the bounded query path used to load project task pages and dependencies.",
  "backend/tests/test_phase6_modularization.py": "Verifies modular execution policies, state transitions, retry counters, and presenter boundaries.",
  "backend/tests/test_rate_limit_security.py": "Verifies orchestration run rate limiting is environment-aware and enforced outside development.",
  "backend/tests/test_task_orchestration_contract.py": "Verifies task workflow fields, evidence normalization, tools, links, and state-machine paths.",
  "backend/tests/test_v2_recommendations_contract.py": "Verifies recommended workflow template defaults and registration of the template application route.",
  "backend/tools/pgvector_plan_check.py": "Runs bounded EXPLAIN checks against representative pgvector queries and fails when the expected vector indexes are not used."
};

const humanize = (name) => name
  .replace(/^_+/, "")
  .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
  .replaceAll("_", " ")
  .replace(/\bgithub\b/gi, "GitHub")
  .replace(/\bhitl\b/gi, "HITL")
  .replace(/\bdag\b/gi, "DAG")
  .replace(/\bapi\b/gi, "API")
  .replace(/\bdb\b/gi, "database")
  .trim();

const complexity = (lines) => lines > 200 ? "complex" : lines >= 50 ? "moderate" : "simple";
const domain = (filePath) => {
  if (filePath.includes("/tests/")) return "test";
  if (filePath.includes("/tools/")) return "database-tooling";
  const match = filePath.match(/backend\/modules\/([^/]+)/);
  return (match?.[1] ?? "backend").replaceAll("_", "-");
};

const fileTags = (filePath) => {
  const name = path.basename(filePath, ".py").replace(/^test_/, "").replaceAll("_", "-");
  if (filePath.includes("/tests/")) return ["test", name, "contract-verification", "pytest"];
  if (filePath.includes("/tools/")) return ["database", "pgvector", "query-plan", "diagnostics"];
  if (filePath.endsWith("/models.py") || filePath.endsWith("orchestration_models.py")) return ["data-model", "database", "sqlalchemy", domain(filePath)];
  if (filePath.endsWith("repository.py") || filePath.endsWith("orchestration_repository.py")) return ["repository", "data-access", "bounded-query", domain(filePath)];
  if (filePath.endsWith("workflow_templates.py")) return ["workflow", "template-catalog", "configuration", "orchestration"];
  if (filePath.endsWith("/__init__.py")) return ["entry-point", "barrel", "exports", domain(filePath)];
  if (filePath.endsWith("routing_service.py")) return ["service", "routing", "policy", "agent-selection"];
  return ["service", "business-logic", "orchestration", domain(filePath)];
};

const functionSummary = (filePath, name) => {
  if (name.startsWith("test_")) return `Verifies that ${humanize(name.slice(5))}.`;
  const exact = {
    _format_routing_attempt_error: "Formats a bounded diagnostic message for a failed model-routing attempt without leaking unsafe provider details.",
    _summarize_provider_chain_for_error: "Summarizes the attempted provider and model chain for a terminal routing error.",
    db_session: "Provides a mocked asynchronous database session fixture for domain-service composition tests.",
    _sign: "Computes the GitHub-compatible SHA-256 HMAC signature for a webhook body.",
    _vector_literal: "Serializes a numeric embedding into PostgreSQL vector literal syntax.",
    _fetch_plan: "Executes EXPLAIN for a representative vector query and returns the plan rows.",
    _plan_text: "Flattens structured EXPLAIN output into searchable plan text.",
    _uses_expected_index: "Checks whether an EXPLAIN plan references one of the expected vector indexes.",
    run_plan_check: "Connects to PostgreSQL, runs representative vector-query plans, reports index usage, and returns a process status.",
    main: "Parses command-line options and exits with the pgvector plan-check result."
  };
  return exact[name] ?? `${humanize(name)} helper for the ${domain(filePath).replaceAll("-", " ")} module.`;
};

const functionTags = (filePath, name) => {
  if (name.startsWith("test_")) {
    const topic = path.basename(filePath, ".py").replace(/^test_/, "").replaceAll("_", "-");
    return ["test", topic, "pytest", /security|webhook|hitl/.test(filePath) ? "security" : "contract"];
  }
  if (filePath.includes("/tools/")) return ["database", "query-plan", "diagnostics", name === "main" ? "entry-point" : "utility"];
  if (name === "db_session") return ["test", "fixture", "database"];
  return ["utility", "routing", "error-handling", "orchestration"];
};

const classSummary = (filePath, name) => {
  const exact = {
    KnowledgeService: "Delegates document and project-memory APIs to an injected memory-domain service.",
    MemoryService: "Composes run-query, memory, project, and task behaviors into a session-bound memory service.",
    OrchestrationRoutingServiceMixin: "Implements policy normalization, eligibility checks, cost-aware ranking, delegation, branching, and reviewer routing for orchestration work.",
    OrchestrationService: "Primary orchestration facade that composes domain services and compatibility mixins around one database session.",
    OrchestrationProjectsRepositoryMixin: "Encapsulates project and task persistence plus bounded portfolio aggregation queries.",
    ProjectsService: "Provides core project and task CRUD workflows with assignment and status notifications.",
    OrchestrationProjectsServiceMixin: "Implements advanced project hierarchy, membership, repository, indexing, configuration, portfolio, snapshot, and bootstrap workflows.",
    OrchestrationTasksServiceMixin: "Implements task DAG execution, work sessions, evidence, acceptance, decomposition, merge resolution, and SLA workflows.",
    TeamRepositoryMixin: "Encapsulates persistence for the agent registry, catalogs, templates, profiles, skill packs, and memberships.",
    TeamServiceMixin: "Implements the agent registry and its markdown, inheritance, linting, template, skill, profile, hierarchy, and catalog rules.",
    TeamService: "Concrete session-bound team service built from the team domain mixin.",
    _GithubHarness: "Minimal GitHub service harness with mocked persistence used by webhook contract tests.",
    _ExecutionHarness: "Minimal execution service harness used to isolate rate-limit behavior in tests."
  };
  if (exact[name]) return exact[name];
  if (filePath.endsWith("orchestration_models.py") || filePath.endsWith("/models.py")) {
    return `Persists ${humanize(name).toLowerCase()} state as a SQLAlchemy database entity.`;
  }
  return `Defines ${humanize(name).toLowerCase()} behavior for the ${domain(filePath).replaceAll("-", " ")} module.`;
};

const classTags = (filePath, name) => {
  if (filePath.includes("/tests/")) return ["test", "harness", "mock", domain(filePath)];
  if (filePath.endsWith("orchestration_models.py") || filePath.endsWith("/models.py")) return ["data-model", "database", "sqlalchemy", domain(filePath)];
  if (name.includes("Repository")) return ["repository", "data-access", "database", domain(filePath)];
  if (name.includes("Routing")) return ["service", "routing", "policy", "agent-selection"];
  return ["service", "business-logic", "orchestration", domain(filePath)];
};

const notes = (filePath) => {
  if (filePath.includes("/tests/")) return "Pytest tests express behavioral contracts with focused mocks and asynchronous fixtures where needed.";
  if (filePath.endsWith("orchestration_models.py") || filePath.endsWith("/models.py")) return "SQLAlchemy declarative mappings use typed attributes, JSON payloads, foreign keys, and explicit indexes.";
  if (filePath.endsWith("routing_service.py")) return "A mixin isolates a large routing policy surface while keeping it composable in the orchestration facade.";
  return undefined;
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

for (const file of input.batchFiles) {
  const result = resultsByPath.get(file.path);
  if (!result) throw new Error(`Missing extraction result for ${file.path}`);
  const fileId = `file:${file.path}`;
  const fileNode = {
    id: fileId,
    type: "file",
    name: path.basename(file.path),
    filePath: file.path,
    summary: summaries[file.path],
    tags: fileTags(file.path),
    complexity: complexity(result.nonEmptyLines)
  };
  const languageNotes = notes(file.path);
  if (languageNotes) fileNode.languageNotes = languageNotes;
  if (!fileNode.summary) throw new Error(`Missing summary for ${file.path}`);
  addNode(fileNode);
  const exportNames = new Set((result.exports ?? []).map((value) => value.name));
  for (const fn of result.functions ?? []) {
    const id = `function:${file.path}:${fn.name}`;
    addNode({id, type: "function", name: fn.name, filePath: file.path, lineRange: [fn.startLine, fn.endLine], summary: functionSummary(file.path, fn.name), tags: functionTags(file.path, fn.name), complexity: complexity(fn.endLine - fn.startLine + 1)});
    addEdge(fileId, id, "contains", 1.0);
    if (exportNames.has(fn.name)) addEdge(fileId, id, "exports", 0.8);
  }
  for (const cls of result.classes ?? []) {
    const id = `class:${file.path}:${cls.name}`;
    addNode({id, type: "class", name: cls.name, filePath: file.path, lineRange: [cls.startLine, cls.endLine], summary: classSummary(file.path, cls.name), tags: classTags(file.path, cls.name), complexity: complexity(cls.endLine - cls.startLine + 1)});
    addEdge(fileId, id, "contains", 1.0);
    if (exportNames.has(cls.name)) addEdge(fileId, id, "exports", 0.8);
  }
}

for (const [sourcePath, targets] of Object.entries(input.batchImportData)) {
  for (const targetPath of targets) addEdge(`file:${sourcePath}`, `file:${targetPath}`, "imports", 0.7);
}

const entitiesByFile = new Map();
for (const result of extraction.results) {
  const entities = new Map();
  for (const fn of result.functions ?? []) entities.set(fn.name, `function:${result.path}:${fn.name}`);
  for (const cls of result.classes ?? []) entities.set(cls.name, `class:${result.path}:${cls.name}`);
  entitiesByFile.set(result.path, entities);
}

for (const result of extraction.results) {
  const local = entitiesByFile.get(result.path);
  const methodOwners = new Map();
  for (const cls of result.classes ?? []) {
    for (const method of cls.methods ?? []) {
      if (!methodOwners.has(method)) methodOwners.set(method, `class:${result.path}:${cls.name}`);
      else methodOwners.set(method, null);
    }
  }
  const importedEntities = new Map();
  for (const importedPath of input.batchImportData[result.path] ?? []) {
    for (const [symbol, id] of entitiesByFile.get(importedPath) ?? []) importedEntities.set(symbol, id);
  }
  const neighborEntities = new Map();
  for (const neighbor of batch.neighborMap[result.path] ?? []) {
    for (const symbol of neighbor.symbols ?? []) {
      neighborEntities.set(symbol, `${/^[A-Z]/.test(symbol) ? "class" : "function"}:${neighbor.path}:${symbol}`);
    }
  }
  for (const call of result.callGraph ?? []) {
    const source = local.get(call.caller) ?? methodOwners.get(call.caller);
    if (!source) continue;
    const target = local.get(call.callee) ?? importedEntities.get(call.callee) ?? neighborEntities.get(call.callee);
    if (target && source !== target) addEdge(source, target, "calls", 0.8);
  }
}

const modelFiles = ["backend/modules/projects/orchestration_models.py", "backend/modules/team/models.py"];
for (const filePath of modelFiles) {
  for (const cls of resultsByPath.get(filePath).classes ?? []) {
    addEdge(`class:${filePath}:${cls.name}`, "class:backend/db/base.py:Base", "inherits", 0.9);
  }
}

const inheritance = [
  ["backend/modules/orchestration/services/memory_domain.py", "MemoryService", "backend/modules/memory/service.py", "OrchestrationMemoryServiceMixin"],
  ["backend/modules/orchestration/services/memory_domain.py", "MemoryService", "backend/modules/orchestration/services/base.py", "OrchestrationRunQueryMixin"],
  ["backend/modules/orchestration/services/memory_domain.py", "MemoryService", "backend/modules/orchestration/services/base.py", "OrchestrationServiceBase"],
  ["backend/modules/orchestration/services/memory_domain.py", "MemoryService", "backend/modules/projects/service.py", "OrchestrationProjectsServiceMixin"],
  ["backend/modules/orchestration/services/memory_domain.py", "MemoryService", "backend/modules/projects/tasks_service.py", "OrchestrationTasksServiceMixin"],
  ["backend/modules/orchestration/services/service.py", "OrchestrationService", "backend/modules/orchestration/services/base.py", "OrchestrationRunQueryMixin"],
  ["backend/modules/orchestration/services/service.py", "OrchestrationService", "backend/modules/projects/service.py", "OrchestrationProjectsServiceMixin"],
  ["backend/modules/orchestration/services/service.py", "OrchestrationService", "backend/modules/projects/tasks_service.py", "OrchestrationTasksServiceMixin"],
  ["backend/modules/orchestration/services/service.py", "OrchestrationService", "backend/modules/team/service.py", "TeamServiceMixin"],
  ["backend/modules/orchestration/services/service.py", "OrchestrationService", "backend/modules/orchestration/services/base.py", "OrchestrationServiceBase"],
  ["backend/modules/team/service.py", "TeamService", "backend/modules/team/service.py", "TeamServiceMixin"],
  ["backend/tests/test_github_webhook.py", "_GithubHarness", "backend/modules/github/service.py", "OrchestrationGithubServiceMixin"],
  ["backend/tests/test_rate_limit_security.py", "_ExecutionHarness", "backend/modules/orchestration/execution/execution_service.py", "OrchestrationExecutionServiceMixin"]
];
for (const [sourcePath, sourceName, targetPath, targetName] of inheritance) {
  addEdge(`class:${sourcePath}:${sourceName}`, `class:${targetPath}:${targetName}`, "inherits", 0.9);
}

for (const [testPath, targets] of Object.entries(input.batchImportData)) {
  if (!testPath.includes("/tests/")) continue;
  for (const targetPath of targets) addEdge(`file:${testPath}`, `file:${targetPath}`, "tested_by", 0.5);
}
for (const [sourcePath, neighbors] of Object.entries(batch.neighborMap)) {
  if (sourcePath.includes("/tests/")) continue;
  for (const neighbor of neighbors) {
    if (neighbor.path.includes("/tests/")) addEdge(`file:${sourcePath}`, `file:${neighbor.path}`, "tested_by", 0.5);
  }
}

const edgeKeys = new Set();
const finalEdges = edges.filter((edge) => {
  const key = `${edge.source}\u0000${edge.target}\u0000${edge.type}`;
  if (edgeKeys.has(key)) return false;
  edgeKeys.add(key);
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
  const fileSet = new Set(sortedFiles.slice(index * groupSize, (index + 1) * groupSize).map((value) => value.path));
  if (!fileSet.size) continue;
  const partNodes = nodes.filter((node) => fileSet.has(node.filePath));
  const sources = new Set(partNodes.map((node) => node.id));
  const partEdges = finalEdges.filter((edge) => sources.has(edge.source));
  const outputPath = path.join(intermediate, `batch-6-part-${index + 1}.json`);
  fs.writeFileSync(outputPath, `${JSON.stringify({nodes: partNodes, edges: partEdges}, null, 2)}\n`);
  parts.push({outputPath, nodes: partNodes.length, edges: partEdges.length, files: fileSet.size});
}

if (parts.reduce((sum, part) => sum + part.nodes, 0) !== nodes.length) throw new Error("Node partition mismatch");
if (parts.reduce((sum, part) => sum + part.edges, 0) !== finalEdges.length) throw new Error("Edge partition mismatch");

const knownNodeIds = new Set(nodes.map((node) => node.id));
const neighborFilePaths = new Set(Object.values(batch.neighborMap).flat().map((value) => value.path));
const importedFilePaths = new Set(Object.values(input.batchImportData).flat());
const neighborEntityIds = new Set();
for (const neighbors of Object.values(batch.neighborMap)) {
  for (const neighbor of neighbors) {
    for (const symbol of neighbor.symbols ?? []) neighborEntityIds.add(`${/^[A-Z]/.test(symbol) ? "class" : "function"}:${neighbor.path}:${symbol}`);
  }
}
for (const part of parts) {
  const parsed = JSON.parse(fs.readFileSync(part.outputPath, "utf8"));
  if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) throw new Error(`${part.outputPath} has invalid arrays`);
  const sourceIds = new Set(parsed.nodes.map((node) => node.id));
  for (const node of parsed.nodes) {
    if (!node.id || !node.type || !node.name || !node.summary || !node.complexity || !Array.isArray(node.tags) || node.tags.length < 3 || node.tags.length > 5) throw new Error(`Invalid node ${node.id}`);
  }
  for (const edge of parsed.edges) {
    if (!sourceIds.has(edge.source)) throw new Error(`${part.outputPath}: unknown source ${edge.source}`);
    if (knownNodeIds.has(edge.target) || neighborEntityIds.has(edge.target)) continue;
    if (edge.target.startsWith("file:")) {
      const targetPath = edge.target.slice(5);
      if (importedFilePaths.has(targetPath) || neighborFilePaths.has(targetPath)) continue;
    }
    throw new Error(`${part.outputPath}: unknown target ${edge.target}`);
  }
}

console.log(JSON.stringify({parts: parts.length, nodes: nodes.length, edges: finalEdges.length, imports: actualImports, details: parts.map((part) => ({file: path.basename(part.outputPath), nodes: part.nodes, edges: part.edges, files: part.files}))}, null, 2));
