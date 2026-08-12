import fs from 'node:fs';
import path from 'node:path';

const root = '/home/polat/Desktop/Projects/troop';
const batchIndex = 3;
const extraction = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything/tmp/ua-file-extract-results-3.json'), 'utf8'));
const batches = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything/intermediate/batches.json'), 'utf8'));
const batch = batches.batches.find((item) => item.batchIndex === batchIndex);
if (!batch) throw new Error('Batch 3 not found');

const summaries = {
  'backend/modules/projects/models.py': 'Defines the SQLAlchemy Project and ProjectTask persistence models, including ownership, assignment, workflow status, priority, ordering, and lifecycle timestamps.',
  'backend/modules/projects/orchestration_schemas.py': 'Defines the extended Pydantic contracts used by orchestration-facing project, task, repository, milestone, decision, portfolio, artifact, and timeline APIs.',
  'backend/modules/projects/repository.py': 'Implements asynchronous SQLAlchemy queries for project access control and project-task persistence, including assignee joins, workflow ordering, and due-date filtering.',
  'backend/modules/projects/router.py': 'Exposes authenticated FastAPI endpoints for project CRUD and task listing, creation, update, deletion, and column reordering through ProjectsService.',
  'backend/modules/projects/schemas.py': 'Defines compact Pydantic request and response contracts for project and task APIs, including assignees and kanban reorder payloads.',
  'backend/modules/settings/models.py': 'Defines the database-backed AppSetting model for typed administrative runtime parameters.',
  'backend/modules/settings/repository.py': 'Provides asynchronous CRUD queries for persisted application settings, including prefix and key lookups.',
  'backend/modules/settings/router.py': 'Exposes administrator-only FastAPI endpoints for environment configuration and database-backed parameters, with audit logging for every mutation.',
  'backend/modules/settings/schemas.py': 'Defines Pydantic contracts for editable environment entries, persisted settings, and the supported parameter catalog.',
  'backend/modules/settings/service.py': 'Coordinates secure administration of environment-backed and database-backed settings, including typed conversion, secret masking, validation, and controlled .env rewrites.',
  'backend/modules/settings/settings_catalog.py': 'Declares the supported runtime setting catalog and provides deterministic parsing, serialization, and per-key validation for typed values.',
  'backend/modules/team/router.py': 'Exposes authenticated FastAPI endpoints for listing and managing agent memberships within a project.',
  'backend/modules/team/schemas.py': 'Defines comprehensive Pydantic contracts for agents, inheritance previews, versions, project memberships, templates, skill packs, and agent test-run traces.',
  'backend/modules/users/repository.py': 'Provides asynchronous user profile updates and active-user directory lookups over the shared identity models.',
  'backend/modules/users/router.py': 'Exposes authenticated user profile, directory, password, and session-management endpoints with security audit events.',
  'backend/modules/users/schemas.py': 'Defines request and response contracts for user profiles, directory entries, password changes, and active sessions.',
  'backend/modules/users/service.py': 'Coordinates profile updates, password verification and hashing, session revocation, and user-directory access.',
  'backend/tests/conftest.py': 'Provides pytest fixtures for service availability checks, FastAPI clients, verified users, authenticated sessions, and CSRF headers used by backend integration tests.',
  'backend/tests/test_ai_async_ingest.py': 'Verifies asynchronous and synchronous AI document ingestion paths, including queue dispatch and failed-job state handling.',
  'backend/tests/test_db_session.py': 'Checks database engine pooling behavior and validates sensible connection-pool configuration defaults.',
  'backend/tests/test_durable_execution_contract.py': 'Validates durable execution backend capability reporting and fail-closed behavior before unsupported work is enqueued.',
  'backend/tests/test_error_payloads.py': 'Verifies that API error payloads preserve legacy detail while exposing the structured error contract.',
  'backend/tests/test_phase0_context.py': 'Tests request-context scoping, sanitization, Celery header propagation, restoration, and baseline percentile calculations.',
  'backend/tests/test_phase1_operations.py': 'Tests operational safeguards for outbound HTTP timeouts, context propagation, retry policy, log redaction, and RAG preview privacy.',
  'backend/tests/test_phase2_observability.py': 'Exercises Prometheus metric rendering, gauge bounds, readiness dependency checks, and observability API behavior.',
  'backend/tests/test_phase7_queue_metrics.py': 'Validates durable queue-age calculation and bounded queue labels during metrics refresh.',
  'backend/tests/test_phase7_reliability.py': 'Tests distributed-lock ownership, SLO metadata, duplicate delivery policy, HTTP load statistics, and percentile edge cases.',
  'backend/tests/test_worker_blocking_sync.py': 'Tests Docker enforcement and host fallback for code execution plus non-blocking polling and timeout behavior for Celery results.',
  'backend/tools/phase0_baseline.py': 'Command-line diagnostics tool that benchmarks HTTP, Redis, database, queue, and process health and emits a redacted operational baseline report.',
  'backend/tools/phase7_validation.py': 'Runs bounded concurrent HTTP load checks and summarizes latency percentiles, throughput, and failures for reliability validation.',
  'backend/workers/celery_async.py': 'Provides an async polling adapter for Celery AsyncResult objects with bounded timeout handling.',
  'backend/workers/context.py': 'Propagates allowlisted request context through Celery task headers and binds and restores it around worker execution signals.',
  'backend/workers/email.py': 'Implements asynchronous SMTP delivery, synchronous bridging, Celery queue dispatch, and templated verification and password-reset emails.',
  'backend/workers/orchestration.py': 'Defines Celery-facing orchestration tasks and an async worker runtime for runs, GitHub synchronization, provider health, memory maintenance, SLA scans, semantic embedding, and code execution.'
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
  if (p.includes('/tests/') || path.basename(p).startsWith('test_')) return ['test', 'backend', 'pytest', 'reliability'];
  if (p.includes('/tools/')) return ['utility', 'observability', 'validation', 'operations'];
  if (p.includes('/workers/')) return ['background-job', 'celery', 'orchestration', 'async'];
  if (p.endsWith('/router.py')) return ['api-handler', 'fastapi', 'routing', p.includes('/settings/') ? 'admin' : 'authentication'];
  if (p.endsWith('/repository.py')) return ['repository', 'data-access', 'sqlalchemy', 'async'];
  if (p.endsWith('/models.py')) return ['data-model', 'sqlalchemy', 'database', 'persistence'];
  if (p.includes('schemas.py')) return ['type-definition', 'validation', 'pydantic', 'api-contract'];
  if (p.endsWith('/service.py')) return ['service', 'business-logic', 'async', p.includes('/settings/') ? 'configuration' : 'security'];
  if (p.endsWith('settings_catalog.py')) return ['configuration', 'validation', 'serialization', 'catalog'];
  return ['backend', 'python', 'application'];
}

function subTags(filePath, item, kind) {
  const name = item.name;
  if (name.startsWith('test_')) return ['test', 'pytest', 'validation'];
  if (filePath.includes('/tests/')) return [kind === 'class' ? 'test-double' : 'test-fixture', 'pytest', 'test'];
  if (filePath.includes('/router.py')) return [name.startsWith('_') ? 'serialization' : 'api-handler', 'fastapi', 'routing'];
  if (filePath.includes('/schemas.py')) return ['type-definition', 'pydantic', 'validation'];
  if (filePath.includes('/models.py')) return ['data-model', 'sqlalchemy', 'persistence'];
  if (filePath.includes('/repository.py')) return ['repository', 'data-access', 'sqlalchemy'];
  if (filePath.includes('/settings_catalog.py')) return [kind === 'class' ? 'type-definition' : 'utility', 'configuration', 'validation'];
  if (filePath.includes('/settings/service.py')) return ['service', 'configuration', 'security'];
  if (filePath.includes('/users/service.py')) return ['service', 'identity', 'security'];
  if (filePath.includes('/tools/')) return ['utility', 'observability', name === 'main' || name === 'parse_args' ? 'cli' : 'benchmark'];
  if (filePath.includes('/workers/')) return [kind === 'class' ? 'service' : 'background-job', 'celery', 'async'];
  return [kind, 'backend', 'python'];
}

function subSummary(filePath, item, kind) {
  const readable = humanize(item.name);
  if (item.name.startsWith('test_')) return `Tests that ${readable.slice(5)}.`;
  if (filePath.includes('/schemas.py')) return `Pydantic API contract representing ${readable} data with validation and serialization rules.`;
  if (filePath.includes('/models.py')) return `SQLAlchemy persistence model representing ${readable} records and their database fields.`;
  if (filePath.includes('/repository.py')) return `${kind === 'class' ? 'Async repository encapsulating' : 'Data-access operation for'} ${readable} persistence and query behavior.`;
  if (filePath.includes('/router.py')) {
    if (item.name === '_project_to_response' || item.name === '_task_to_response' || item.name === '_project_agent') return `Converts domain data into the ${readable} API representation.`;
    if (item.name === '_log_admin_settings_action') return 'Records an auditable administrative settings mutation with actor and change metadata.';
    return `FastAPI endpoint handler for ${readable}.`;
  }
  if (filePath.includes('/settings_catalog.py')) {
    if (kind === 'class') return 'Immutable specification for a typed runtime setting, its default, and operator-facing description.';
    const special = {
      '_positive_int': 'Validates that a configured numeric value is strictly positive.',
      '_fraction_0_1': 'Validates that a configured numeric value is within the inclusive zero-to-one range.',
      'list_catalog': 'Returns the supported runtime settings in stable key order.',
      'get_spec': 'Looks up the typed specification for a runtime setting key.',
      'serialize_value': 'Serializes a typed runtime value into its canonical persisted string form.',
      'parse_value': 'Parses a persisted setting string according to its declared runtime type.',
      'normalize_value_for_key': 'Parses, validates, and canonically serializes a value for a known setting key.'
    };
    return special[item.name] || `Handles ${readable} for the runtime settings catalog.`;
  }
  if (filePath.includes('/settings/service.py')) return 'Service coordinating validated, typed, and secret-aware application settings administration.';
  if (filePath.includes('/users/service.py')) return 'Service coordinating authenticated user profile, password, session, and directory operations.';
  if (filePath.endsWith('/conftest.py')) return `Pytest fixture or helper providing ${readable} for backend integration tests.`;
  if (filePath.includes('/tools/')) {
    if (item.name === 'main') return 'Command-line entry point that runs the validation workflow and emits its report.';
    if (item.name === 'parse_args') return 'Parses command-line options for the operational validation tool.';
    if (kind === 'class') return `Structured result model for ${readable}.`;
    return `Operational diagnostics helper that computes or collects ${readable}.`;
  }
  if (filePath.endsWith('/celery_async.py')) return 'Polls a Celery result without blocking the event loop and raises on timeout.';
  if (filePath.endsWith('/context.py')) return `Worker context helper that handles ${readable} across Celery task boundaries.`;
  if (filePath.endsWith('/email.py')) return `Email worker operation that performs ${readable}.`;
  if (filePath.endsWith('/orchestration.py')) {
    if (kind === 'class') return 'Async orchestration worker runtime that opens service sessions and serializes singleton maintenance jobs with distributed leases.';
    return `Celery task or dispatch helper that performs ${readable} work.`;
  }
  return `${kind === 'class' ? 'Class' : 'Function'} implementing ${readable} behavior.`;
}

const nodes = [];
const edges = [];
const idByPathAndSymbol = new Map();
const itemById = new Map();

for (const result of extraction.results) {
  const fileId = `file:${result.path}`;
  nodes.push({
    id: fileId,
    type: 'file',
    name: path.basename(result.path),
    filePath: result.path,
    summary: summaries[result.path] || `Python module supporting ${humanize(path.basename(result.path, '.py'))}.`,
    tags: fileTags(result),
    complexity: complexityForLines(result.nonEmptyLines ?? result.totalLines ?? 0),
    languageNotes: result.path.includes('/workers/') ? 'Uses async boundaries around Celery workers so blocking result polling and synchronous task entry points do not stall the application event loop.' : undefined
  });

  const exported = new Set((result.exports || []).map((entry) => entry.name));
  for (const [kind, list] of [['function', result.functions || []], ['class', result.classes || []]]) {
    for (const item of list) {
      const lineCount = Math.max(1, item.endLine - item.startLine + 1);
      const significant = exported.has(item.name) || (kind === 'function' ? lineCount >= 10 : (lineCount >= 20 || (item.methods || []).length >= 2));
      if (!significant) continue;
      const id = `${kind}:${result.path}:${item.name}`;
      const node = {
        id,
        type: kind,
        name: item.name,
        filePath: result.path,
        lineRange: [item.startLine, item.endLine],
        summary: subSummary(result.path, item, kind),
        tags: subTags(result.path, item, kind),
        complexity: complexityForLines(lineCount)
      };
      nodes.push(node);
      itemById.set(id, { result, item, kind });
      idByPathAndSymbol.set(`${result.path}\0${item.name}`, id);
      edges.push({ source: fileId, target: id, type: 'contains', direction: 'forward', weight: 1.0 });
      if (exported.has(item.name)) edges.push({ source: fileId, target: id, type: 'exports', direction: 'forward', weight: 0.8 });
    }
  }
}

// Emit every scanner-resolved project import exactly once.
for (const file of batch.files) {
  for (const target of batch.batchImportData[file.path] || []) {
    edges.push({ source: `file:${file.path}`, target: `file:${target}`, type: 'imports', direction: 'forward', weight: 0.7 });
  }
}

// Add high-confidence call edges where extracted callees exactly match exports in this batch or neighborMap.
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
  const neighbors = batch.neighborMap[result.path] || [];
  for (const call of result.callGraph || []) {
    const callee = call.callee;
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(callee)) continue;
    const source = sourceForCaller(result, call.caller);
    if (!source) continue;
    const importedPaths = new Set(batch.batchImportData[result.path] || []);
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

// Canonical production -> test coverage edges for production files represented in this batch.
const batchPaths = new Set(batch.files.map((file) => file.path));
for (const file of batch.files) {
  if (!path.basename(file.path).startsWith('test_')) continue;
  for (const imported of batch.batchImportData[file.path] || []) {
    if (batchPaths.has(imported) && !imported.includes('/tests/')) {
      edges.push({ source: `file:${imported}`, target: `file:${file.path}`, type: 'tested_by', direction: 'forward', weight: 0.5 });
    }
  }
}

// Deduplicate relationships produced by repeated call sites.
const uniqueEdges = [...new Map(edges.map((edge) => [`${edge.source}\0${edge.target}\0${edge.type}`, edge])).values()];
const importExpected = Object.values(batch.batchImportData).reduce((sum, paths) => sum + paths.length, 0);
const importActual = uniqueEdges.filter((edge) => edge.type === 'imports').length;
if (importActual !== importExpected) throw new Error(`Import edge mismatch: expected ${importExpected}, got ${importActual}`);

const parts = Math.ceil(Math.max(nodes.length / 60, uniqueEdges.length / 120));
const sortedPaths = batch.files.map((file) => file.path).sort();
const chunkSize = Math.ceil(sortedPaths.length / parts);
const written = [];
for (let index = 0; index < parts; index += 1) {
  const paths = new Set(sortedPaths.slice(index * chunkSize, (index + 1) * chunkSize));
  const partNodes = nodes.filter((node) => paths.has(node.filePath));
  const sourceIds = new Set(partNodes.map((node) => node.id));
  const partEdges = uniqueEdges.filter((edge) => sourceIds.has(edge.source));
  const output = { nodes: partNodes, edges: partEdges };
  const outputPath = path.join(root, `.understand-anything/intermediate/batch-${batchIndex}-part-${index + 1}.json`);
  fs.writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`);
  written.push({ outputPath, nodes: partNodes.length, edges: partEdges.length });
}

console.log(JSON.stringify({ totalNodes: nodes.length, totalEdges: uniqueEdges.length, importExpected, importActual, parts, written }, null, 2));
