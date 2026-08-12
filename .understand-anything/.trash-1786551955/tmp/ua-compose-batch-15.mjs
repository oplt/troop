import fs from 'node:fs';
import path from 'node:path';

const root = '/home/polat/Desktop/Projects/troop';
const batchIndex = 15;
const extraction = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything/tmp/ua-file-extract-results-15.json'), 'utf8'));
const batches = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything/intermediate/batches.json'), 'utf8'));
const batch = batches.batches.find((item) => item.batchIndex === batchIndex);
if (!batch) throw new Error('Batch 15 not found');

const summaries = {
  'backend/modules/memory/lifecycle/__init__.py': 'Re-exports the focused memory context, retention, and semantic lifecycle boundaries as a cohesive package API.',
  'backend/modules/memory/lifecycle/context.py': 'Wraps prompt-facing memory context assembly behind a persistence-independent lifecycle service.',
  'backend/modules/memory/lifecycle/retention.py': 'Defines resolved memory retention policy values and derives bounded expiration timestamps from TTL settings.',
  'backend/modules/memory/lifecycle/semantic.py': 'Provides a provider-neutral semantic memory lifecycle for add, search, update, delete, user cleanup, and duplicate lookup operations.',
  'backend/modules/memory/metrics.py': 'Collects bounded in-process memory metrics, character-size histograms, context-packet rollups, and snapshot summaries.',
  'backend/modules/memory/namespaces.py': 'Defines and enforces the canonical scoped memory namespace taxonomy, builders, validators, and legacy namespace migration.',
  'backend/modules/memory/promotion_rules.py': 'Scores project and company memory candidates against explicit rules to decide automatic promotion, suggested review, or rejection.',
  'backend/modules/memory/provenance.py': 'Normalizes memory provenance metadata, confidence, source references, and supersession chains into a stable contract.',
  'backend/modules/memory/retrieval_scoping.py': 'Implements staged semantic and episodic vector retrieval across task, project, company, related-project, and archive scopes with early exits and metrics.',
  'backend/modules/memory/service.py': 'Implements the orchestration memory domain across working, semantic, procedural, episodic, document, knowledge-graph, lifecycle, compaction, and prompt-context workflows.',
  'backend/modules/memory/settings.py': 'Defines memory defaults and safely merges bounded project-level overrides for retrieval, retention, context, and promotion behavior.',
  'backend/modules/memory/working_memory.py': 'Defines canonical working-memory state, safe patch merging, clipping, checkpoint recovery, prompt formatting, and run-status write policy.',
  'backend/modules/orchestration/context_packet.py': 'Builds token-budgeted orchestration context packets with section deduplication, clipping, prioritization, combined prompts, and telemetry.',
  'backend/modules/orchestration/procedural_context.py': 'Formats ranked procedural playbooks into compact prompt snippets within item and character budgets.',
  'backend/tests/test_concurrency_opportunities.py': 'Tests parallel memory ingestion with separate sessions, pending-job guards, concurrent context fetches, and domain service exposure.',
  'backend/tests/test_memory_architecture_contract.py': 'Validates bounded memory write contracts, expiry constraints, long-term scope, and enabled-by-default memory layers.',
  'backend/tests/test_memory_layer.py': 'Exercises memory redaction, storage safety, deduplication, context ranking, extraction, disabled behavior, and provider-backed CRUD.',
  'backend/tests/test_memory_read_paths.py': 'Guards read paths against accidental expiration and verifies scheduled and global memory cleanup availability.',
  'backend/tests/test_phase5_memory_architecture.py': 'Tests memory access scoping, namespace validation, retention configuration, context bounds, provider isolation, and lifecycle metadata.'
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
  if (p.includes('/tests/')) return ['test', 'pytest', 'memory', 'validation'];
  if (p.endsWith('/__init__.py')) return ['barrel', 'memory', 'exports', 'lifecycle'];
  if (p.includes('/lifecycle/')) return ['service', 'memory', 'lifecycle', 'domain-logic'];
  if (p.endsWith('/metrics.py')) return ['observability', 'metrics', 'memory', 'telemetry'];
  if (p.endsWith('/namespaces.py')) return ['validation', 'namespace', 'memory', 'migration'];
  if (p.endsWith('/promotion_rules.py')) return ['policy', 'classification', 'memory', 'scoring'];
  if (p.endsWith('/provenance.py')) return ['provenance', 'normalization', 'memory', 'validation'];
  if (p.endsWith('/retrieval_scoping.py')) return ['retrieval', 'vector-search', 'memory', 'scoping'];
  if (p.endsWith('/service.py')) return ['service', 'memory', 'orchestration', 'async'];
  if (p.endsWith('/settings.py')) return ['configuration', 'memory', 'validation', 'defaults'];
  if (p.endsWith('/working_memory.py')) return ['working-memory', 'state-management', 'validation', 'serialization'];
  if (p.endsWith('/context_packet.py')) return ['context', 'token-budget', 'prompt', 'orchestration'];
  return ['context', 'memory', 'prompt', 'utility'];
}

function subTags(filePath, item, kind) {
  if (item.name.startsWith('test_')) return ['test', 'pytest', 'validation'];
  if (filePath.includes('/tests/')) return [kind === 'class' ? 'test-double' : 'test-helper', 'pytest', 'memory'];
  if (filePath.includes('/lifecycle/')) return ['service', 'memory', 'lifecycle'];
  if (filePath.endsWith('/metrics.py')) return ['observability', 'metrics', 'memory'];
  if (filePath.endsWith('/namespaces.py')) return ['validation', 'namespace', 'memory'];
  if (filePath.endsWith('/promotion_rules.py')) return [kind === 'class' ? 'data-model' : 'policy', 'memory', 'scoring'];
  if (filePath.endsWith('/provenance.py')) return ['provenance', 'normalization', 'memory'];
  if (filePath.endsWith('/retrieval_scoping.py')) return [kind === 'class' ? 'repository' : 'retrieval', 'vector-search', 'scoping'];
  if (filePath.endsWith('/service.py')) return ['service', 'memory', 'orchestration'];
  if (filePath.endsWith('/settings.py')) return ['configuration', 'memory', 'validation'];
  if (filePath.endsWith('/working_memory.py')) return ['working-memory', 'state-management', 'validation'];
  if (filePath.endsWith('/context_packet.py')) return [kind === 'class' ? 'data-model' : 'utility', 'context', 'token-budget'];
  return ['utility', 'context', 'prompt'];
}

function subSummary(filePath, item, kind) {
  const readable = humanize(item.name);
  if (item.name.startsWith('test_')) return `Tests that ${readable.slice(5)}.`;
  if (filePath.includes('/tests/')) return `Test double supporting ${readable} memory behavior.`;
  if (filePath.endsWith('/lifecycle/context.py')) return 'Persistence-independent lifecycle boundary for ranking and formatting memory records into prompt context.';
  if (filePath.endsWith('/lifecycle/retention.py')) return kind === 'class'
    ? 'Resolved retention policy containing TTL, expiration time, and cleanup action.'
    : 'Resolves bounded memory retention settings into a concrete expiration policy.';
  if (filePath.endsWith('/lifecycle/semantic.py')) return 'Provider-neutral service that delegates semantic memory CRUD, search, cleanup, and deduplication.';
  if (filePath.endsWith('/metrics.py')) return `Memory observability helper that records or summarizes ${readable}.`;
  if (filePath.endsWith('/namespaces.py')) return `Canonical namespace utility that performs ${readable}.`;
  if (filePath.endsWith('/promotion_rules.py')) return kind === 'class'
    ? `Structured memory promotion value representing ${readable}.`
    : `Promotion policy helper that computes ${readable}.`;
  if (filePath.endsWith('/provenance.py')) return `Memory provenance helper that performs ${readable}.`;
  if (filePath.endsWith('/retrieval_scoping.py')) return kind === 'class'
    ? 'Protocol describing the scoped semantic and episodic retrieval operations required by the staged search algorithm.'
    : `Staged memory retrieval helper that performs ${readable}.`;
  if (filePath.endsWith('/service.py')) return 'Comprehensive orchestration memory mixin owning lifecycle, retrieval, ingestion, compaction, knowledge graph, and prompt context workflows.';
  if (filePath.endsWith('/settings.py')) return 'Merges validated project memory overrides into the canonical default settings document.';
  if (filePath.endsWith('/working_memory.py')) return `Working-memory utility that performs ${readable}.`;
  if (filePath.endsWith('/context_packet.py')) return kind === 'class'
    ? 'Token-budgeted context packet that combines prioritized sections and reports allocation telemetry.'
    : `Context packet utility that performs ${readable}.`;
  if (filePath.endsWith('/procedural_context.py')) return `Procedural prompt-context helper that performs ${readable}.`;
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
  if (result.path.endsWith('/retrieval_scoping.py') || result.path.endsWith('/context_packet.py')) {
    fileNode.languageNotes = 'Uses typed staged processing with explicit bounds and early exits so memory relevance does not produce unbounded prompt or query costs.';
  }
  nodes.push(fileNode);
  const exported = new Set((result.exports || []).map((entry) => entry.name));
  for (const [kind, list] of [['function', result.functions || []], ['class', result.classes || []]]) {
    for (const item of list) {
      const lineCount = Math.max(1, item.endLine - item.startLine + 1);
      const significant = exported.has(item.name) || (kind === 'function' ? lineCount >= 10 : lineCount >= 20 || (item.methods || []).length >= 2);
      if (!significant) continue;
      const id = `${kind}:${result.path}:${item.name}`;
      nodes.push({ id, type: kind, name: item.name, filePath: result.path,
        lineRange: [item.startLine, item.endLine], summary: subSummary(result.path, item, kind),
        tags: subTags(result.path, item, kind), complexity: complexityForLines(lineCount) });
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

const batchPaths = new Set(batch.files.map((file) => file.path));
for (const testFile of batch.files.filter((file) => path.basename(file.path).startsWith('test_'))) {
  for (const imported of batch.batchImportData[testFile.path] || []) {
    if (batchPaths.has(imported) && !imported.includes('/tests/')) {
      edges.push({ source: `file:${imported}`, target: `file:${testFile.path}`, type: 'tested_by', direction: 'forward', weight: 0.5 });
    }
  }
}
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
