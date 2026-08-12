import fs from 'node:fs';
import path from 'node:path';

const root = '/home/polat/Desktop/Projects/troop';
const batchIndex = 8;
const extraction = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything/tmp/ua-file-extract-results-8.json'), 'utf8'));
const batches = JSON.parse(fs.readFileSync(path.join(root, '.understand-anything/intermediate/batches.json'), 'utf8'));
const batch = batches.batches.find((item) => item.batchIndex === batchIndex);
if (!batch) throw new Error('Batch 8 not found');

const summaries = {
  'frontend/src/features/orchestration/project/ProjectDetailState.tsx': 'Provides consistent missing, loading, and error-state views for orchestration project detail screens.',
  'frontend/src/features/orchestration/project/api.ts': 'Defines a narrow project-detail API facade over the broader orchestration client for project, task, membership, milestone, and decision operations.',
  'frontend/src/features/orchestration/project/components/AcceptanceDialog.tsx': 'Renders a task acceptance review dialog that checks acceptance criteria through a mutation and presents pass/fail evidence with resilient API errors.',
  'frontend/src/features/orchestration/project/components/ExternalLinksEditor.tsx': 'Provides a controlled editor for adding, updating, labeling, and removing task-related external links.',
  'frontend/src/features/orchestration/project/components/MilestoneTimeline.tsx': 'Renders project milestones as a status-colored timeline with due dates and descriptions.',
  'frontend/src/features/orchestration/project/components/SubtaskPanel.tsx': 'Displays task subtasks and triggers AI-assisted task decomposition while refreshing project query state and surfacing failures.',
  'frontend/src/features/orchestration/project/mutations.test.ts': 'Verifies that project mutation invalidation covers the expected project-scoped TanStack Query keys.',
  'frontend/src/features/orchestration/project/mutations.ts': 'Centralizes project-scoped TanStack Query invalidation after orchestration mutations.',
  'frontend/src/features/orchestration/project/queries.test.ts': 'Verifies project-detail section activation logic and guards against unnecessary query execution.',
  'frontend/src/features/orchestration/project/queries.ts': 'Composes section-aware TanStack Query hooks for a project detail view, loading only the orchestration data required by the active section.',
  'frontend/src/features/orchestration/project/taskForm.ts': 'Creates and normalizes project task form drafts, including dates, labels, assignments, dependencies, and optional execution metadata.',
  'frontend/src/hooks/projectLiveSnapshotSync.test.ts': 'Tests live project snapshot validation, change detection, and targeted query invalidation behavior.',
  'frontend/src/hooks/projectLiveSnapshotSync.ts': 'Validates live project snapshots and maps section-level changes to targeted TanStack Query cache invalidations.',
  'frontend/src/hooks/useDebounce.test.ts': 'Tests delayed value updates and timer replacement behavior for the debounce hook.',
  'frontend/src/hooks/useDebounce.ts': 'Provides a small React hook that emits a value only after a configurable quiet period.',
  'frontend/src/hooks/useLiveSnapshotStream.ts': 'Maintains a reconnecting authenticated project snapshot stream with visibility-aware backoff and lifecycle cleanup.',
  'frontend/src/hooks/usePlatformMetadata.ts': 'Loads platform metadata through a shared TanStack Query key and cache policy.',
  'frontend/src/hooks/useSseStream.test.ts': 'Tests Server-Sent Events data-block parsing and malformed payload handling.',
  'frontend/src/hooks/useSseStream.ts': 'Provides a generic reconnecting Server-Sent Events React hook with JSON parsing, authentication, backoff, visibility handling, and cleanup.',
  'frontend/src/pages/ActivityAuditPage.tsx': 'Presents searchable audit and approval activity, including status filters, date bounds, decision actions, and richly formatted event details.',
  'frontend/src/pages/AdminPlatformPage.tsx': 'Provides the administrator control plane for platform configuration, module plans, feature flags, app templates, cloning, and operational metadata.',
  'frontend/src/pages/AdminSettingsPage.tsx': 'Combines configuration, database parameters, platform, companies, GitHub, providers, users, and profile administration into a tabbed settings workspace.',
  'frontend/src/pages/AdminUsersPage.tsx': 'Provides an administrative user directory with debounced search, status filtering, pagination, statistics, and account management actions.',
  'frontend/src/pages/AgentProfilesPage.tsx': 'Lists and edits agent profiles, validates contracts, manages activation state, and coordinates agent creation through orchestration queries.',
  'frontend/src/pages/AgentRunDetailPage.tsx': 'Displays an agent run plan, step timeline, artifacts, approval controls, status, and cancellation state with periodic refresh.',
  'frontend/src/pages/AiStudioPage.tsx': 'Offers a comprehensive AI operations workspace for prompts, versions, documents, retrieval, runs, reviews, feedback, datasets, and evaluations.',
  'frontend/src/pages/BenchmarkPage.tsx': 'Manages evaluation records and benchmarks, presents comparative scores and leaderboards, and launches current or historical benchmark runs.',
  'frontend/src/pages/BrainstormDetailPage.tsx': 'Coordinates a multi-agent brainstorm workspace with participants, messages, rounds, consensus insights, finalization, and artifact promotion.'
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
  if (p.includes('.test.')) return ['test', 'vitest', 'frontend', 'validation'];
  if (p.includes('/pages/')) return ['component', 'page', 'react', 'frontend'];
  if (p.includes('/components/')) return ['component', 'react', 'orchestration', 'ui'];
  if (p.includes('/hooks/')) return ['hook', 'react', p.includes('Sse') || p.includes('Snapshot') ? 'real-time' : 'state-management', 'frontend'];
  if (p.endsWith('/queries.ts')) return ['hook', 'tanstack-query', 'data-fetching', 'orchestration'];
  if (p.endsWith('/mutations.ts')) return ['mutation', 'tanstack-query', 'cache-invalidation', 'orchestration'];
  if (p.endsWith('/api.ts')) return ['api-client', 'facade', 'orchestration', 'data-fetching'];
  if (p.endsWith('/taskForm.ts')) return ['form', 'validation', 'serialization', 'task-management'];
  return ['component', 'react', 'frontend'];
}

function subTags(filePath, item) {
  if (item.name.startsWith('use')) return ['hook', 'react', 'state-management'];
  if (filePath.includes('/pages/')) return [item.name.endsWith('Page') || item.name.endsWith('Content') || item.name.endsWith('Card') || item.name.endsWith('Panel') ? 'component' : 'utility', 'react', 'frontend'];
  if (filePath.includes('/components/') || filePath.endsWith('.tsx')) return [item.name[0] === item.name[0].toUpperCase() ? 'component' : 'utility', 'react', 'ui'];
  if (filePath.endsWith('/queries.ts')) return ['hook', 'tanstack-query', 'data-fetching'];
  if (filePath.endsWith('/mutations.ts')) return ['mutation', 'tanstack-query', 'cache-invalidation'];
  if (filePath.includes('Snapshot')) return ['utility', 'real-time', 'cache-invalidation'];
  if (filePath.includes('SseStream')) return ['hook', 'server-sent-events', 'real-time'];
  if (filePath.endsWith('/taskForm.ts')) return ['form', 'normalization', 'task-management'];
  return ['utility', 'typescript', 'frontend'];
}

function subSummary(filePath, item) {
  const readable = humanize(item.name);
  if (item.name.startsWith('use')) return `React hook that coordinates ${readable.slice(4)} state and lifecycle behavior.`;
  if (filePath.includes('/pages/')) {
    if (/Page$|Content$|Card$|Panel$/.test(item.name)) return `React view component responsible for the ${readable} interface and interactions.`;
    return `Page-level helper that computes or formats ${readable}.`;
  }
  if (filePath.includes('/components/') || filePath.endsWith('ProjectDetailState.tsx')) {
    if (/^[A-Z]/.test(item.name)) return `React component rendering the ${readable} project workflow interface.`;
    return `UI helper that computes ${readable}.`;
  }
  if (filePath.endsWith('/queries.ts')) return item.name.startsWith('use')
    ? 'Composes section-aware project detail queries with shared cache keys and enablement rules.'
    : `Determines ${readable} for project-detail query activation.`;
  if (filePath.endsWith('/mutations.ts')) return `TanStack Query cache helper that performs ${readable}.`;
  if (filePath.endsWith('/taskForm.ts')) return `Task form utility that performs ${readable}.`;
  if (filePath.includes('projectLiveSnapshotSync.ts')) return `Live-snapshot synchronization helper that performs ${readable}.`;
  if (filePath.includes('useSseStream.ts')) return item.name === 'useSseStream'
    ? 'Maintains a generic reconnecting SSE subscription and exposes its connection state to React consumers.'
    : `Server-Sent Events helper that performs ${readable}.`;
  if (filePath.includes('useLiveSnapshotStream.ts')) return item.name === 'useLiveSnapshotStream'
    ? 'Maintains a reconnecting authenticated live-snapshot stream with backoff and visibility-aware recovery.'
    : `Live-stream helper that performs ${readable}.`;
  if (filePath.includes('useDebounce.ts')) return 'Delays propagation of a changing value until the configured quiet period elapses.';
  if (filePath.includes('usePlatformMetadata.ts')) return 'Loads and caches platform metadata through TanStack Query.';
  return `Frontend utility implementing ${readable}.`;
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
    summary: summaries[result.path] || `Frontend module for ${humanize(path.basename(result.path).replace(/\.(tsx?|jsx?)$/, ''))}.`,
    tags: fileTags(result),
    complexity: complexityForLines(result.nonEmptyLines ?? result.totalLines ?? 0)
  };
  if (result.path.includes('SseStream') || result.path.includes('LiveSnapshot')) {
    fileNode.languageNotes = 'Combines React effect cleanup with bounded reconnect backoff to avoid duplicate streams and stale state updates.';
  }
  nodes.push(fileNode);

  const exported = new Set((result.exports || []).map((entry) => entry.name));
  for (const item of result.functions || []) {
    const lineCount = Math.max(1, item.endLine - item.startLine + 1);
    if (!exported.has(item.name) && lineCount < 10) continue;
    const id = `function:${result.path}:${item.name}`;
    nodes.push({
      id,
      type: 'function',
      name: item.name,
      filePath: result.path,
      lineRange: [item.startLine, item.endLine],
      summary: subSummary(result.path, item),
      tags: subTags(result.path, item),
      complexity: complexityForLines(lineCount)
    });
    idByPathAndSymbol.set(`${result.path}\0${item.name}`, id);
    edges.push({ source: fileId, target: id, type: 'contains', direction: 'forward', weight: 1.0 });
    if (exported.has(item.name)) edges.push({ source: fileId, target: id, type: 'exports', direction: 'forward', weight: 0.8 });
  }
  for (const item of result.classes || []) {
    const lineCount = Math.max(1, item.endLine - item.startLine + 1);
    if (!exported.has(item.name) && lineCount < 20 && (item.methods || []).length < 2) continue;
    const id = `class:${result.path}:${item.name}`;
    nodes.push({
      id,
      type: 'class',
      name: item.name,
      filePath: result.path,
      lineRange: [item.startLine, item.endLine],
      summary: subSummary(result.path, item),
      tags: subTags(result.path, item),
      complexity: complexityForLines(lineCount)
    });
    idByPathAndSymbol.set(`${result.path}\0${item.name}`, id);
    edges.push({ source: fileId, target: id, type: 'contains', direction: 'forward', weight: 1.0 });
    if (exported.has(item.name)) edges.push({ source: fileId, target: id, type: 'exports', direction: 'forward', weight: 0.8 });
  }
}

// Emit every scanner-resolved project import exactly once.
for (const file of batch.files) {
  for (const target of batch.batchImportData[file.path] || []) {
    edges.push({ source: `file:${file.path}`, target: `file:${target}`, type: 'imports', direction: 'forward', weight: 0.7 });
  }
}

// High-confidence call edges constrained to exact extracted names and scanner-provided neighbors.
const localSymbols = new Map();
for (const [key, id] of idByPathAndSymbol) {
  const separator = key.indexOf('\0');
  const filePath = key.slice(0, separator);
  const symbol = key.slice(separator + 1);
  if (!localSymbols.has(symbol)) localSymbols.set(symbol, []);
  localSymbols.get(symbol).push({ id, filePath });
}
for (const result of extraction.results) {
  const imports = new Set(batch.batchImportData[result.path] || []);
  const neighbors = batch.neighborMap[result.path] || [];
  for (const call of result.callGraph || []) {
    const callee = call.callee;
    if (!/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(callee)) continue;
    const source = idByPathAndSymbol.get(`${result.path}\0${call.caller}`);
    if (!source) continue;
    const targets = (localSymbols.get(callee) || [])
      .filter((target) => target.filePath === result.path || imports.has(target.filePath))
      .map((target) => target.id);
    for (const neighbor of neighbors) {
      if (neighbor.symbols.includes(callee)) targets.push(`function:${neighbor.path}:${callee}`);
    }
    for (const target of uniq(targets)) {
      if (source !== target) edges.push({ source, target, type: 'calls', direction: 'forward', weight: 0.8 });
    }
  }
}

// Canonical production -> test relationships for colocated unit tests.
const batchPaths = new Set(batch.files.map((file) => file.path));
for (const testFile of batch.files.filter((file) => file.path.includes('.test.'))) {
  for (const imported of batch.batchImportData[testFile.path] || []) {
    if (batchPaths.has(imported) && !imported.includes('.test.')) {
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
