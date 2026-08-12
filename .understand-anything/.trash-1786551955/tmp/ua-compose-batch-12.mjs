import fs from 'node:fs';
import path from 'node:path';

const root = '/home/polat/Desktop/Projects/troop';
const batchIndex = 12;
const extraction = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything/tmp/ua-file-extract-results-12.json'), 'utf8'));
const batches = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything/intermediate/batches.json'), 'utf8'));
const batch = batches.batches.find((item) => item.batchIndex === batchIndex);
if (!batch) throw new Error('Batch 12 not found');

const summaries = {
  'backend/modules/rag/retrieval.py': 'Implements cached hybrid retrieval, document chunk ingestion, context construction, citation-aware answer generation, and streaming RAG responses.',
  'backend/modules/rag/router.py': 'Exposes authenticated FastAPI endpoints for RAG document ingestion, bulk upload, listing, deletion, retrieval, grounded answers, streaming, and reindexing.',
  'backend/modules/rag/schemas.py': 'Defines domain contracts for RAG filters, documents, chunks, ranked matches, citations, and grounded answers.',
  'backend/modules/rag/service.py': 'Provides the unified authorization-aware RAG facade for document lifecycle, retrieval, context building, and provider-backed answers.',
  'backend/modules/rag/vector_store.py': 'Defines the vector-store protocol and a pgvector-backed repository adapter with bounded fallback retrieval and embedding helpers.',
  'backend/tests/test_algorithm_ai_improvements.py': 'Tests RAG thresholds, parser safety, context deduplication and budgets, secret redaction, knowledge retrieval, and transient provider retries.',
  'backend/tests/test_blocking_dead_code.py': 'Guards worker retry classification and failure behavior for unknown memory-ingest job types.',
  'backend/tests/test_cache_layer.py': 'Exercises cache-key isolation, embedding and retrieval caches, ACL and memory settings, single-flight fills, negative caching, and generation-based invalidation.',
  'backend/tests/test_celery_tasks.py': 'Verifies Celery autoretry policy, CPU queue routing, and eager execution paths for orchestration and memory ingestion tasks.',
  'backend/tests/test_golden_retrieval.py': 'Validates golden retrieval ranking, recall thresholds, answer grounding and citation markers, and the committed RAG evaluation gate fixture.',
  'backend/tests/test_integration_baseline.py': 'Provides integration smoke coverage for health, Celery registration, authentication, project CRUD, RAG search, and orchestration run lifecycle.',
  'backend/tests/test_phase4_concurrency.py': 'Tests HTTP client reuse, bounded bulk-ingest concurrency, cancellation cleanup, SSE capacity release, and Celery delivery limits.',
  'backend/tests/test_provider_abstraction_contract.py': 'Checks provider capability discovery and precedence of per-request generation options over provider defaults.',
  'backend/tests/test_rag_layer.py': 'Tests the RAG pipeline components for chunking, parsing, prompt construction, reranking, disabled behavior, and secret-safe indexing.',
  'backend/tests/test_rag_request_path.py': 'Exercises RAG answer timeout and streaming paths, provider registry delegation, and parallel bulk ingestion.',
  'backend/tests/test_vector_retrieval.py': 'Verifies pgvector preference and explicitly bounded optional Python fallback paths across RAG and AI retrieval.',
  'backend/tools/rag_eval_gate.py': 'Command-line quality gate that loads retrieval cases, evaluates ranking and answer grounding, and fails when configured thresholds are missed.',
  'backend/workers/__init__.py': 'Initializes the worker package and exposes the configured Celery application.',
  'backend/workers/celery_app.py': 'Configures Celery queues, delivery guarantees, serialization, time limits, worker instrumentation, context propagation, and periodic orchestration jobs.',
  'backend/workers/retry.py': 'Classifies transient worker failures that are safe for automatic retry.',
  'backend/workers/tasks.py': 'Defines the Celery email task with transient autoretry policy and synchronous email delivery bridging.'
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
  if (p.includes('/tests/')) return ['test', 'pytest', 'backend', p.includes('rag') || p.includes('retrieval') ? 'rag' : 'reliability'];
  if (p.includes('/tools/')) return ['cli', 'evaluation', 'quality-gate', 'rag'];
  if (p.includes('/workers/')) return ['background-job', 'celery', 'reliability', 'async'];
  if (p.endsWith('/router.py')) return ['api-handler', 'fastapi', 'rag', 'routing'];
  if (p.endsWith('/schemas.py')) return ['type-definition', 'validation', 'rag', 'api-contract'];
  if (p.endsWith('/vector_store.py')) return ['repository', 'vector-search', 'pgvector', 'data-access'];
  if (p.endsWith('/retrieval.py')) return ['rag', 'retrieval', 'vector-search', 'service'];
  return ['service', 'rag', 'business-logic', 'async'];
}

function subTags(filePath, item, kind) {
  if (item.name.startsWith('test_')) return ['test', 'pytest', 'validation'];
  if (filePath.includes('/tests/')) return [kind === 'class' ? 'test-double' : 'test-helper', 'pytest', 'test'];
  if (filePath.includes('/tools/')) return ['cli', 'evaluation', 'quality-gate'];
  if (filePath.includes('/workers/')) return ['background-job', 'celery', 'reliability'];
  if (filePath.endsWith('/router.py')) return [kind === 'class' || item.name.startsWith('_') ? 'serialization' : 'api-handler', 'fastapi', 'rag'];
  if (filePath.endsWith('/schemas.py')) return ['type-definition', 'rag', 'validation'];
  if (filePath.endsWith('/vector_store.py')) return [kind === 'class' ? 'repository' : 'utility', 'vector-search', 'data-access'];
  if (filePath.endsWith('/retrieval.py')) return ['service', 'rag', item.name.includes('Ingestion') ? 'ingestion' : 'retrieval'];
  if (filePath.endsWith('/service.py')) return ['service', 'rag', 'business-logic'];
  return [kind, 'backend', 'python'];
}

function subSummary(filePath, item, kind) {
  const readable = humanize(item.name);
  if (item.name.startsWith('test_')) return `Tests that ${readable.slice(5)}.`;
  if (filePath.includes('/tests/')) return `Test helper providing ${readable} behavior for backend reliability checks.`;
  if (filePath.includes('/tools/')) return item.name === 'main'
    ? 'Command-line entry point for the RAG evaluation quality gate.'
    : `Evaluation helper that performs ${readable}.`;
  if (filePath.endsWith('/workers/celery_app.py')) return 'Builds the service-scoped Celery task routing table from runtime queue configuration.';
  if (filePath.endsWith('/workers/retry.py')) return 'Returns whether an exception represents a transient worker failure eligible for retry.';
  if (filePath.endsWith('/workers/tasks.py')) return 'Celery task that sends email through the synchronous worker bridge with bounded transient retries.';
  if (filePath.endsWith('/router.py')) {
    if (kind === 'class') return `Pydantic transport contract for ${readable}.`;
    if (item.name.startsWith('_')) return `RAG transport helper that converts or normalizes ${readable}.`;
    return `Authenticated FastAPI endpoint handler for ${readable}.`;
  }
  if (filePath.endsWith('/schemas.py')) return `RAG domain contract representing ${readable} data with validation and serialization rules.`;
  if (filePath.endsWith('/retrieval.py')) {
    if (item.name === 'RetrieverService') return 'Coordinates cached embedding search, optional fallback ranking, reranking, decisions, and context construction.';
    if (item.name === 'DocumentIngestionService') return 'Parses, chunks, embeds, and atomically stores project document content for retrieval.';
    if (item.name === 'RagAnswerService') return 'Builds grounded prompts and produces citation-aware complete or streaming provider answers.';
  }
  if (filePath.endsWith('/service.py')) return 'Unified RAG service facade coordinating authorization, ingestion, retrieval, provider selection, cache invalidation, and document lifecycle.';
  if (filePath.endsWith('/vector_store.py')) return item.name === 'VectorStoreRepository'
    ? 'Protocol defining the vector persistence, search, deletion, and bounded fallback contract.'
    : 'Pgvector-backed repository adapter for document chunk persistence and similarity retrieval.';
  return `${kind === 'class' ? 'Class' : 'Function'} implementing ${readable}.`;
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
    summary: summaries[result.path] || `Python module supporting ${humanize(path.basename(result.path, '.py'))}.`,
    tags: fileTags(result),
    complexity: complexityForLines(result.nonEmptyLines ?? result.totalLines ?? 0)
  };
  if (result.path.endsWith('/retrieval.py') || result.path.endsWith('/vector_store.py')) {
    fileNode.languageNotes = 'Uses async repository boundaries and typed domain objects to keep vector retrieval infrastructure replaceable and testable.';
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

for (const file of batch.files) {
  for (const target of batch.batchImportData[file.path] || []) {
    edges.push({ source: `file:${file.path}`, target: `file:${target}`, type: 'imports', direction: 'forward', weight: 0.7 });
  }
}

const localSymbols = new Map();
for (const [key, id] of idByPathAndSymbol) {
  const separator = key.indexOf('\0');
  const filePath = key.slice(0, separator);
  const symbol = key.slice(separator + 1);
  if (!localSymbols.has(symbol)) localSymbols.set(symbol, []);
  localSymbols.get(symbol).push({ id, filePath });
}
function sourceForCaller(result, caller) {
  const direct = idByPathAndSymbol.get(`${result.path}\0${caller}`);
  if (direct) return direct;
  const cls = (result.classes || []).find((entry) => (entry.methods || []).includes(caller));
  return cls ? idByPathAndSymbol.get(`${result.path}\0${cls.name}`) : undefined;
}
for (const result of extraction.results) {
  const imports = new Set(batch.batchImportData[result.path] || []);
  const neighbors = batch.neighborMap[result.path] || [];
  for (const call of result.callGraph || []) {
    const callee = call.callee;
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(callee)) continue;
    const source = sourceForCaller(result, call.caller);
    if (!source) continue;
    const targets = (localSymbols.get(callee) || [])
      .filter((target) => target.filePath === result.path || imports.has(target.filePath))
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

// PgVectorStoreRepository structurally fulfills the vector-store protocol.
edges.push({
  source: 'class:backend/modules/rag/vector_store.py:PgVectorStoreRepository',
  target: 'class:backend/modules/rag/vector_store.py:VectorStoreRepository',
  type: 'implements',
  direction: 'forward',
  weight: 0.9
});

// Canonical production -> test coverage for imported files represented in this batch.
const batchPaths = new Set(batch.files.map((file) => file.path));
for (const testFile of batch.files.filter((file) => path.basename(file.path).startsWith('test_'))) {
  for (const imported of batch.batchImportData[testFile.path] || []) {
    if (batchPaths.has(imported) && !imported.includes('/tests/')) {
      edges.push({ source: `file:${imported}`, target: `file:${testFile.path}`, type: 'tested_by', direction: 'forward', weight: 0.5 });
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
