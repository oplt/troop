import fs from 'node:fs';
import path from 'node:path';

const root = '/home/polat/Desktop/Projects/troop';
const batchIndex = 5;
const extraction = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything/tmp/ua-file-extract-results-5.json'), 'utf8'));
const batches = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything/intermediate/batches.json'), 'utf8'));
const batch = batches.batches.find((item) => item.batchIndex === batchIndex);
if (!batch) throw new Error('Batch 5 not found');

const summaries = {
  'backend/modules/orchestration/control_plane_runtime.py': 'Builds validated agent runtime profiles from persisted agents, skill packs, providers, model capabilities, prompt templates, tool bindings, and structured-operation contracts.',
  'backend/modules/orchestration/execution/execution_service.py': 'Implements the core orchestration run lifecycle, including durable workflow checkpoints, budgets, HITL grants, manager-worker execution, tool calls, retries, events, artifacts, and task transitions.',
  'backend/modules/orchestration/execution/execution_state.py': 'Extracts stable execution snapshot views, working-memory details, and bounded checkpoint excerpts from run metadata.',
  'backend/modules/orchestration/execution/execution_workflow.py': 'Provides deterministic state-machine helpers for durable workflow steps, artifacts, signals, resume counters, query snapshots, and trace summaries.',
  'backend/modules/orchestration/execution/langgraph_runner.py': 'Adapts orchestration run modes to a compact LangGraph state graph and invokes the supplied execution callback through the selected route.',
  'backend/modules/orchestration/execution/policies.py': 'Centralizes task-transition validation and retry-number calculation using agent-specific retry policies.',
  'backend/modules/orchestration/hierarchy_policy.py': 'Normalizes, validates, reads, and applies hierarchical agent reporting and delegation policies for project execution settings.',
  'backend/modules/orchestration/hitl_policy.py': 'Normalizes human-in-the-loop approval gates and autonomy levels, evaluates gated actions, and redacts sensitive approval payloads.',
  'backend/modules/orchestration/local_repo.py': 'Implements constrained local-repository inspection, isolated worktree creation, command allowlisting, file reads, and bounded context-pack assembly.',
  'backend/modules/orchestration/markdown.py': 'Parses agent profile Markdown into normalized identity, instructions, model, memory, tool, permission, output-schema, and task-filter settings.',
  'backend/modules/orchestration/model_utils.py': 'Provides canonical embedding-vector normalization and timezone-aware UTC timestamps for orchestration models.',
  'backend/modules/orchestration/models.py': 'Defines SQLAlchemy persistence models for providers, model capabilities, task runs and events, brainstorms, approval requests, and evaluations.',
  'backend/modules/orchestration/presenters.py': 'Maps orchestration domain models and execution snapshots into stable Pydantic API response objects.',
  'backend/modules/orchestration/repository.py': 'Implements the comprehensive asynchronous persistence boundary for agents, projects, tasks, runs, providers, GitHub sync, documents, memory, approvals, evaluations, and observability queries.',
  'backend/modules/orchestration/router.py': 'Defines the primary authenticated FastAPI transport for orchestration, exposing agent, project, task, run, memory, GitHub, evaluation, brainstorm, provider, and live-stream operations.',
  'backend/modules/orchestration/routers/approvals.py': 'Defines focused FastAPI handlers for listing approval requests, recording decisions, and reporting pending approval counts.',
  'backend/modules/orchestration/schemas.py': 'Defines the complete Pydantic API contract surface for orchestration resources, commands, snapshots, metrics, memory, agents, projects, workflows, and evaluations.',
  'backend/modules/orchestration/services/__init__.py': 'Re-exports orchestration application and domain service boundaries as the public service package API.',
  'backend/modules/orchestration/services/application.py': 'Provides a narrow application-service boundary that composes common agent, task, and run use cases for interchangeable transport adapters.',
  'backend/modules/orchestration/services/approvals_domain.py': 'Composes the mixins required for human approval listing, gated decisions, and approval-triggered side effects.',
  'backend/modules/orchestration/services/approvals_service.py': 'Implements approval listing, authorization-aware decisions, audit events, memory coordination, and gate evaluation for orchestration runs.',
  'backend/modules/orchestration/services/base.py': 'Defines session-scoped orchestration dependencies, permission policy constants, and a minimal shared run-query mixin.',
  'backend/modules/orchestration/services/brainstorm_domain.py': 'Composes the domain boundary for brainstorm lifecycle management, execution, consensus telemetry, routing, and project integration.',
  'backend/modules/orchestration/services/brainstorm_service.py': 'Implements multi-agent brainstorm and debate lifecycles, guardrails, discourse metrics, round summaries, finalization, and artifact promotion.',
  'backend/modules/orchestration/services/evals_domain.py': 'Composes the evaluation domain boundary for benchmarks, PR review, schedules, providers, workflow templates, and agent testing.',
  'backend/modules/orchestration/services/evals_service.py': 'Implements evaluation records, scorecards, benchmarks, PR-assistant review, schedules, workflow templates, and test agent runs.',
  'backend/modules/orchestration/services/execution_domain.py': 'Composes the execution domain boundary from run, approval, routing, provider, GitHub, memory, task, project, and team behaviors.',
  'backend/modules/orchestration/services/github_sync_domain.py': 'Composes the GitHub synchronization boundary for repository linking, webhooks, issue synchronization, routing, and replay.'
};

const humanize = (value) => value
  .replace(/^_+/, '')
  .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
  .replace(/[_-]+/g, ' ')
  .trim()
  .toLowerCase();
const complexityForLines = (lines) => lines > 200 ? 'complex' : lines >= 50 ? 'moderate' : 'simple';
const uniq = (items) => [...new Set(items)];

function fileTags(file) {
  const p = file.path;
  if (p.endsWith('/router.py') || p.includes('/routers/')) return ['api-handler', 'fastapi', 'routing', 'orchestration'];
  if (p.endsWith('/schemas.py')) return ['type-definition', 'pydantic', 'api-contract', 'validation'];
  if (p.endsWith('/models.py')) return ['data-model', 'sqlalchemy', 'persistence', 'orchestration'];
  if (p.endsWith('/repository.py')) return ['repository', 'data-access', 'sqlalchemy', 'async'];
  if (p.endsWith('/services/__init__.py')) return ['barrel', 'service', 'exports', 'orchestration'];
  if (p.includes('/services/')) return ['service', 'domain-logic', 'orchestration', p.includes('_domain.py') ? 'composition' : 'async'];
  if (p.includes('/execution/')) return ['execution', 'workflow', 'orchestration', 'reliability'];
  if (p.endsWith('/local_repo.py')) return ['repository-tools', 'security', 'worktree', 'command-execution'];
  if (p.endsWith('/markdown.py')) return ['parser', 'validation', 'agent-profile', 'serialization'];
  if (p.endsWith('_policy.py')) return ['policy', 'validation', 'orchestration', 'security'];
  if (p.endsWith('/presenters.py')) return ['serialization', 'presenter', 'api-contract', 'orchestration'];
  if (p.endsWith('/control_plane_runtime.py')) return ['runtime', 'agent-profile', 'llm', 'structured-output'];
  return ['utility', 'orchestration', 'python'];
}

function subTags(filePath, item, kind) {
  if (filePath.endsWith('/router.py') || filePath.includes('/routers/')) return [item.name.startsWith('_') ? 'serialization' : 'api-handler', 'fastapi', 'orchestration'];
  if (filePath.endsWith('/schemas.py')) return ['type-definition', 'pydantic', 'api-contract'];
  if (filePath.endsWith('/models.py')) return ['data-model', 'sqlalchemy', 'persistence'];
  if (filePath.endsWith('/repository.py')) return ['repository', 'data-access', 'async'];
  if (filePath.includes('/services/')) return [kind === 'class' ? 'service' : 'domain-logic', 'orchestration', filePath.includes('_domain.py') ? 'composition' : 'async'];
  if (filePath.includes('/execution/')) return [kind === 'class' ? 'workflow' : 'utility', 'execution', 'reliability'];
  if (filePath.endsWith('/local_repo.py')) return [kind === 'class' ? 'type-definition' : 'utility', 'repository-tools', 'security'];
  if (filePath.endsWith('/markdown.py')) return ['parser', 'validation', 'agent-profile'];
  if (filePath.endsWith('_policy.py')) return ['policy', 'validation', 'orchestration'];
  if (filePath.endsWith('/presenters.py')) return ['serialization', 'presenter', 'api-contract'];
  if (filePath.endsWith('/control_plane_runtime.py')) return [kind === 'class' ? 'type-definition' : 'factory', 'agent-runtime', 'llm'];
  return [kind, 'orchestration', 'python'];
}

function subSummary(filePath, item, kind) {
  const readable = humanize(item.name);
  if (filePath.endsWith('/schemas.py')) return `Pydantic API contract representing ${readable} data with validation and serialization rules.`;
  if (filePath.endsWith('/models.py')) return `SQLAlchemy persistence model for ${readable} state and its relational lifecycle.`;
  if (filePath.endsWith('/repository.py')) return 'Asynchronous repository boundary encapsulating orchestration persistence and bounded query behavior.';
  if (filePath.endsWith('/router.py') || filePath.includes('/routers/')) {
    if (item.name.startsWith('_')) return `Transport helper that builds, normalizes, or streams ${readable} API data.`;
    return `Authenticated FastAPI endpoint handler for ${readable}.`;
  }
  if (filePath.endsWith('/services/application.py')) return 'Application-layer facade that delegates stable agent, task, and run use cases to the orchestration domain service.';
  if (filePath.includes('/services/') && filePath.endsWith('_domain.py')) return `Composable domain service boundary for ${readable} operations.`;
  if (filePath.includes('/services/')) return `Service mixin implementing ${readable} orchestration behavior and domain invariants.`;
  if (filePath.endsWith('/execution_service.py')) return 'Execution-domain mixin implementing durable run lifecycle, budgets, tools, approvals, events, and workflow transitions.';
  if (filePath.endsWith('/execution_state.py')) return `Extracts or formats ${readable} from durable execution metadata.`;
  if (filePath.endsWith('/execution_workflow.py')) return `Deterministic durable-workflow helper for ${readable}.`;
  if (filePath.endsWith('/langgraph_runner.py')) return kind === 'class' ? 'Typed LangGraph state contract for orchestration run routing.' : `LangGraph adapter operation that performs ${readable}.`;
  if (filePath.endsWith('/policies.py')) return kind === 'class' ? 'Retry policy that derives attempt limits and backoff behavior from agent configuration.' : `Policy helper that computes ${readable}.`;
  if (filePath.endsWith('/hierarchy_policy.py')) return `Hierarchy-policy helper that performs ${readable}.`;
  if (filePath.endsWith('/hitl_policy.py')) return `Human-in-the-loop policy helper that performs ${readable}.`;
  if (filePath.endsWith('/local_repo.py')) return kind === 'class' ? `Structured local-repository type representing ${readable}.` : `Security-bounded local repository operation for ${readable}.`;
  if (filePath.endsWith('/markdown.py')) return `Agent Markdown parser helper that performs ${readable}.`;
  if (filePath.endsWith('/model_utils.py')) return `Model utility that computes ${readable}.`;
  if (filePath.endsWith('/presenters.py')) return `Maps domain state into the ${readable} API response contract.`;
  if (filePath.endsWith('/control_plane_runtime.py')) return kind === 'class' ? `Validated runtime contract for ${readable}.` : `Builds or resolves ${readable} for an executable agent runtime profile.`;
  return `${kind === 'class' ? 'Class' : 'Function'} implementing ${readable} orchestration behavior.`;
}

const nodes = [];
const edges = [];
const idByPathAndSymbol = new Map();

for (const result of extraction.results) {
  const fileId = `file:${result.path}`;
  const fileNode = {
    id: fileId,
    type: 'file',
    name: path.basename(result.path),
    filePath: result.path,
    summary: summaries[result.path] || `Python orchestration module for ${humanize(path.basename(result.path, '.py'))}.`,
    tags: fileTags(result),
    complexity: complexityForLines(result.nonEmptyLines ?? result.totalLines ?? 0)
  };
  if (result.path.includes('/services/') && result.path.endsWith('_domain.py')) {
    fileNode.languageNotes = 'Uses cooperative multiple inheritance to compose narrowly owned domain mixins behind a session-scoped service boundary.';
  }
  nodes.push(fileNode);

  const exported = new Set((result.exports || []).map((entry) => entry.name));
  for (const [kind, list] of [['function', result.functions || []], ['class', result.classes || []]]) {
    for (const item of list) {
      const lineCount = Math.max(1, item.endLine - item.startLine + 1);
      const significant = exported.has(item.name) || (kind === 'function' ? lineCount >= 10 : lineCount >= 20 || (item.methods || []).length >= 2);
      if (!significant) continue;
      const id = `${kind}:${result.path}:${item.name}`;
      nodes.push({
        id,
        type: kind,
        name: item.name,
        filePath: result.path,
        lineRange: [item.startLine, item.endLine],
        summary: subSummary(result.path, item, kind),
        tags: subTags(result.path, item, kind),
        complexity: complexityForLines(lineCount)
      });
      idByPathAndSymbol.set(`${result.path}\0${item.name}`, id);
      edges.push({ source: fileId, target: id, type: 'contains', direction: 'forward', weight: 1.0 });
      if (exported.has(item.name)) edges.push({ source: fileId, target: id, type: 'exports', direction: 'forward', weight: 0.8 });
    }
  }
}

// Emit scanner-resolved internal imports 1:1.
for (const file of batch.files) {
  for (const target of batch.batchImportData[file.path] || []) {
    edges.push({ source: `file:${file.path}`, target: `file:${target}`, type: 'imports', direction: 'forward', weight: 0.7 });
  }
}

// High-confidence calls: exact extracted callee names constrained to imported files or the same file.
const localSymbols = new Map();
for (const [key, id] of idByPathAndSymbol) {
  const separator = key.indexOf('\0');
  const filePath = key.slice(0, separator);
  const symbol = key.slice(separator + 1);
  if (!localSymbols.has(symbol)) localSymbols.set(symbol, []);
  localSymbols.get(symbol).push({ id, filePath });
}
function sourceForCaller(result, caller) {
  const own = idByPathAndSymbol.get(`${result.path}\0${caller}`);
  if (own) return own;
  const cls = (result.classes || []).find((entry) => (entry.methods || []).includes(caller));
  return cls ? idByPathAndSymbol.get(`${result.path}\0${cls.name}`) : undefined;
}
for (const result of extraction.results) {
  const importedPaths = new Set(batch.batchImportData[result.path] || []);
  const neighbors = batch.neighborMap[result.path] || [];
  for (const call of result.callGraph || []) {
    const callee = call.callee;
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(callee)) continue;
    const source = sourceForCaller(result, call.caller);
    if (!source) continue;
    const targets = (localSymbols.get(callee) || [])
      .filter((target) => target.filePath === result.path || importedPaths.has(target.filePath))
      .map((target) => target.id);
    for (const neighbor of neighbors) {
      if (!neighbor.symbols.includes(callee)) continue;
      const kind = /^_*[A-Z]/.test(callee) ? 'class' : 'function';
      targets.push(`${kind}:${neighbor.path}:${callee}`);
    }
    for (const target of uniq(targets)) {
      if (source !== target) edges.push({ source, target, type: 'calls', direction: 'forward', weight: 0.8 });
    }
  }
}

// Explicit service-composition inheritance discovered from the domain class declarations.
const inheritance = {
  'backend/modules/orchestration/services/approvals_domain.py:ApprovalsService': [
    'backend/modules/orchestration/services/base.py:OrchestrationRunQueryMixin',
    'backend/modules/orchestration/services/base.py:OrchestrationServiceBase',
    'backend/modules/orchestration/services/approvals_service.py:OrchestrationApprovalsServiceMixin',
    'backend/modules/orchestration/execution/execution_service.py:OrchestrationExecutionServiceMixin',
    'backend/modules/github/service.py:OrchestrationGithubServiceMixin',
    'backend/modules/memory/service.py:OrchestrationMemoryServiceMixin',
    'backend/modules/projects/service.py:OrchestrationProjectsServiceMixin',
    'backend/modules/projects/tasks_service.py:OrchestrationTasksServiceMixin',
    'backend/modules/orchestration/services/routing_service.py:OrchestrationRoutingServiceMixin',
    'backend/modules/team/service.py:TeamServiceMixin'
  ],
  'backend/modules/orchestration/services/brainstorm_domain.py:BrainstormService': [
    'backend/modules/orchestration/services/base.py:OrchestrationRunQueryMixin',
    'backend/modules/orchestration/services/base.py:OrchestrationServiceBase',
    'backend/modules/orchestration/services/brainstorm_service.py:OrchestrationBrainstormServiceMixin',
    'backend/modules/orchestration/execution/execution_service.py:OrchestrationExecutionServiceMixin',
    'backend/modules/github/service.py:OrchestrationGithubServiceMixin',
    'backend/modules/projects/service.py:OrchestrationProjectsServiceMixin',
    'backend/modules/projects/tasks_service.py:OrchestrationTasksServiceMixin',
    'backend/modules/orchestration/services/routing_service.py:OrchestrationRoutingServiceMixin',
    'backend/modules/team/service.py:TeamServiceMixin'
  ],
  'backend/modules/orchestration/services/evals_domain.py:EvalsService': [
    'backend/modules/orchestration/services/base.py:OrchestrationRunQueryMixin',
    'backend/modules/orchestration/services/base.py:OrchestrationServiceBase',
    'backend/modules/orchestration/services/evals_service.py:OrchestrationEvalsServiceMixin',
    'backend/modules/orchestration/execution/execution_service.py:OrchestrationExecutionServiceMixin',
    'backend/modules/orchestration/services/providers_service.py:OrchestrationProvidersServiceMixin',
    'backend/modules/github/service.py:OrchestrationGithubServiceMixin',
    'backend/modules/projects/service.py:OrchestrationProjectsServiceMixin',
    'backend/modules/projects/tasks_service.py:OrchestrationTasksServiceMixin',
    'backend/modules/team/service.py:TeamServiceMixin'
  ],
  'backend/modules/orchestration/services/execution_domain.py:ExecutionService': [
    'backend/modules/orchestration/services/base.py:OrchestrationRunQueryMixin',
    'backend/modules/orchestration/services/base.py:OrchestrationServiceBase',
    'backend/modules/orchestration/execution/execution_service.py:OrchestrationExecutionServiceMixin',
    'backend/modules/orchestration/services/approvals_service.py:OrchestrationApprovalsServiceMixin',
    'backend/modules/orchestration/services/routing_service.py:OrchestrationRoutingServiceMixin',
    'backend/modules/orchestration/services/providers_service.py:OrchestrationProvidersServiceMixin',
    'backend/modules/github/service.py:OrchestrationGithubServiceMixin',
    'backend/modules/memory/service.py:OrchestrationMemoryServiceMixin',
    'backend/modules/projects/tasks_service.py:OrchestrationTasksServiceMixin',
    'backend/modules/projects/service.py:OrchestrationProjectsServiceMixin',
    'backend/modules/team/service.py:TeamServiceMixin'
  ],
  'backend/modules/orchestration/services/github_sync_domain.py:GithubSyncService': [
    'backend/modules/orchestration/services/base.py:OrchestrationServiceBase',
    'backend/modules/github/service.py:OrchestrationGithubServiceMixin',
    'backend/modules/projects/service.py:OrchestrationProjectsServiceMixin',
    'backend/modules/projects/tasks_service.py:OrchestrationTasksServiceMixin',
    'backend/modules/orchestration/services/routing_service.py:OrchestrationRoutingServiceMixin',
    'backend/modules/orchestration/execution/execution_service.py:OrchestrationExecutionServiceMixin'
  ]
};
for (const [sourceRef, targets] of Object.entries(inheritance)) {
  const split = sourceRef.lastIndexOf(':');
  const source = `class:${sourceRef.slice(0, split)}:${sourceRef.slice(split + 1)}`;
  for (const targetRef of targets) {
    const targetSplit = targetRef.lastIndexOf(':');
    const target = `class:${targetRef.slice(0, targetSplit)}:${targetRef.slice(targetSplit + 1)}`;
    edges.push({ source, target, type: 'inherits', direction: 'forward', weight: 0.9 });
  }
}

// Neighboring tests that import these modules provide direct production -> test coverage evidence.
for (const file of batch.files) {
  for (const neighbor of batch.neighborMap[file.path] || []) {
    if (neighbor.path.includes('/tests/') && path.basename(neighbor.path).startsWith('test_')) {
      edges.push({ source: `file:${file.path}`, target: `file:${neighbor.path}`, type: 'tested_by', direction: 'forward', weight: 0.5 });
    }
  }
}

const uniqueEdges = [...new Map(edges.map((edge) => [`${edge.source}\0${edge.target}\0${edge.type}`, edge])).values()];
const importExpected = Object.values(batch.batchImportData).reduce((sum, values) => sum + values.length, 0);
const importActual = uniqueEdges.filter((edge) => edge.type === 'imports').length;
if (importActual !== importExpected) throw new Error(`Import edge mismatch: expected ${importExpected}, got ${importActual}`);

const parts = Math.ceil(Math.max(nodes.length / 60, uniqueEdges.length / 120));
const sortedPaths = batch.files.map((file) => file.path).sort();
const baseChunkSize = Math.floor(sortedPaths.length / parts);
const largerChunkCount = sortedPaths.length % parts;
const written = [];
let pathOffset = 0;
for (let index = 0; index < parts; index += 1) {
  const groupSize = baseChunkSize + (index < largerChunkCount ? 1 : 0);
  const paths = new Set(sortedPaths.slice(pathOffset, pathOffset + groupSize));
  pathOffset += groupSize;
  const partNodes = nodes.filter((node) => paths.has(node.filePath));
  const sourceIds = new Set(partNodes.map((node) => node.id));
  const partEdges = uniqueEdges.filter((edge) => sourceIds.has(edge.source));
  const outputPath = path.join(root, `.understand-anything/intermediate/batch-${batchIndex}-part-${index + 1}.json`);
  fs.writeFileSync(outputPath, `${JSON.stringify({ nodes: partNodes, edges: partEdges }, null, 2)}\n`);
  written.push({ outputPath, nodes: partNodes.length, edges: partEdges.length });
}

console.log(JSON.stringify({ totalNodes: nodes.length, totalEdges: uniqueEdges.length, importExpected, importActual, parts, written }, null, 2));
