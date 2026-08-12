import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tmp = path.join(root, ".understand-anything/tmp");
const intermediate = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-extract-results-13.json"), "utf8"));
const input = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-analyzer-input-13.json"), "utf8"));
const batches = JSON.parse(fs.readFileSync(path.join(intermediate, "batches.json"), "utf8"));
const batch = batches.batches.find((item) => item.batchIndex === 13);
if (!batch) throw new Error("Batch 13 not found");

const summaries = {
  "backend/app/agents/memory/__init__.py": "Publishes the SQL-backed agent memory store through the agent memory package.",
  "backend/app/agents/memory/base.py": "Adapts the shared memory layer to the agent-facing add, list, search, update, and delete store interface with user and project scoping.",
  "backend/modules/memory/classifier.py": "Classifies free text and run events into memory entry candidates with types, confidence, titles, tags, and structured metadata.",
  "backend/modules/memory/compaction.py": "Builds task-close working-memory snapshots and prunes checkpoint state after successful compaction.",
  "backend/modules/memory/conflict_resolver.py": "Detects duplicate, contradictory, and version-conflicting semantic memories using vector, token, polarity, and source-version signals.",
  "backend/modules/memory/coordination.py": "Extracts structured facts, decisions, artifacts, and unknowns from shared task blackboard text.",
  "backend/modules/memory/episodic.py": "Serializes episodic memory rows into compressed JSON Lines archives and derives stable archive object keys.",
  "backend/modules/memory/layer/__init__.py": "Defines the public surface of the reusable memory layer, including configuration, port, schemas, and service.",
  "backend/modules/memory/layer/config.py": "Resolves immutable memory feature, retention, extraction, embedding, and context limits from application and project settings.",
  "backend/modules/memory/layer/context.py": "Ranks memory records by relevance, confidence, importance, and recency and renders a bounded context block.",
  "backend/modules/memory/layer/dedup.py": "Provides deterministic content hashing and duplicate detection primitives for memory writes.",
  "backend/modules/memory/layer/entry_mapping.py": "Normalizes memory entry types and supplies default importance, confidence, and tags for each canonical type.",
  "backend/modules/memory/layer/extractor.py": "Extracts candidate memories with deterministic rules and parses or prompts structured LLM extraction results.",
  "backend/modules/memory/layer/observability.py": "Emits privacy-bounded memory events and measures operation latency with a lightweight timer.",
  "backend/modules/memory/layer/port.py": "Defines the asynchronous storage protocol required by memory-layer consumers.",
  "backend/modules/memory/layer/provider.py": "Defines the memory provider contract and adapts semantic memory models, repositories, namespaces, and access context to it.",
  "backend/modules/memory/layer/redaction.py": "Detects secrets and sensitive content, redacts unsafe spans, and enforces storage-safety policies.",
  "backend/modules/memory/layer/repository.py": "Defines the memory repository contract and a SQL implementation for CRUD, scoped search, vector lookup, deduplication, and embedding jobs.",
  "backend/modules/memory/layer/schemas.py": "Defines immutable access, filter, and record value objects shared across memory ports, providers, repositories, and services.",
  "backend/modules/memory/layer/service.py": "Coordinates safe memory ingestion, extraction, deduplication, embedding, search, context assembly, lifecycle hooks, and observability."
};

const complexity = (lines) => lines > 200 ? "complex" : lines >= 50 ? "moderate" : "simple";
const humanize = (name) => name.replace(/^_+/, "").replace(/([a-z0-9])([A-Z])/g, "$1 $2").replaceAll("_", " ").replace(/\bllm\b/gi, "LLM").replace(/\bjsonl\b/gi, "JSONL").trim();

const fileTags = (filePath) => {
  if (filePath.endsWith("/__init__.py")) return ["entry-point", "barrel", "exports", "memory"];
  if (filePath.endsWith("/base.py")) return ["adapter", "memory-store", "agent-runtime", "database"];
  if (filePath.endsWith("classifier.py")) return ["classification", "memory", "extraction", "heuristics"];
  if (filePath.endsWith("compaction.py")) return ["compaction", "working-memory", "retention", "snapshot"];
  if (filePath.endsWith("conflict_resolver.py")) return ["conflict-resolution", "deduplication", "semantic-memory", "similarity"];
  if (filePath.endsWith("coordination.py")) return ["coordination", "blackboard", "parsing", "memory"];
  if (filePath.endsWith("episodic.py")) return ["episodic-memory", "archive", "serialization", "compression"];
  if (filePath.endsWith("/config.py")) return ["configuration", "memory", "feature-flags", "limits"];
  if (filePath.endsWith("/context.py")) return ["context-building", "ranking", "memory", "retrieval"];
  if (filePath.endsWith("/dedup.py")) return ["deduplication", "hashing", "memory", "utility"];
  if (filePath.endsWith("entry_mapping.py")) return ["normalization", "entry-type", "metadata", "memory"];
  if (filePath.endsWith("extractor.py")) return ["extraction", "llm", "heuristics", "memory"];
  if (filePath.endsWith("observability.py")) return ["observability", "logging", "privacy", "memory"];
  if (filePath.endsWith("port.py")) return ["interface", "protocol", "memory-store", "type-definition"];
  if (filePath.endsWith("provider.py")) return ["provider", "adapter", "semantic-memory", "service"];
  if (filePath.endsWith("redaction.py")) return ["security", "redaction", "privacy", "validation"];
  if (filePath.endsWith("repository.py")) return ["repository", "database", "vector-search", "memory"];
  if (filePath.endsWith("schemas.py")) return ["data-model", "type-definition", "memory", "validation"];
  return ["service", "memory", "business-logic", "orchestration"];
};

const fileNotes = (filePath) => {
  if (filePath.endsWith("port.py") || filePath.endsWith("repository.py") || filePath.endsWith("provider.py")) return "Python Protocol types keep storage and provider contracts substitutable without runtime inheritance requirements.";
  if (filePath.endsWith("schemas.py") || filePath.endsWith("config.py")) return "Frozen dataclasses make memory configuration and cross-layer value objects explicit and mutation-resistant.";
  return undefined;
};

const functionSummaries = {
  _detect_entry_type: "Infers a canonical memory entry type from normalized text and keyword evidence.",
  classify_text: "Classifies one text fragment into a scored memory candidate with title, tags, and metadata.",
  classify_run_events: "Converts relevant orchestration run events into classified memory candidates.",
  _derive_title: "Derives a short stable title from the leading meaningful text.",
  snapshot_source_id: "Builds the stable source identifier used for a task-close memory snapshot.",
  build_task_close_snapshot_text: "Renders task state, conclusions, and checkpoint data into a compact close-out snapshot.",
  prune_checkpoint_after_compaction: "Removes compacted checkpoint sections while retaining state still needed for later execution.",
  _cosine: "Calculates cosine similarity between two numeric embedding vectors.",
  _normalize_text: "Normalizes text for lexical conflict and duplicate comparisons.",
  _polarity_clash: "Detects opposing polarity signals between otherwise related memory statements.",
  _version_clash: "Detects incompatible source-version metadata between memory records.",
  detect: "Scores a candidate against existing memories and reports duplicates, contradictions, and version conflicts.",
  _token_jaccard: "Calculates token-set Jaccard similarity for normalized memory text.",
  summarize: "Builds a concise human-readable summary of a conflict report.",
  extract_blackboard_sections: "Parses known blackboard headings into structured coordination sections.",
  build_episodic_archive_jsonl_gz: "Serializes episodic rows into gzip-compressed JSON Lines bytes.",
  _json_default: "Converts datetime-like values into JSON-safe representations during archival.",
  episodic_object_key: "Builds a stable object-storage key for an episodic archive.",
  resolve_memory_config: "Resolves effective memory configuration from global settings and optional project overrides.",
  _relevance: "Scores lexical overlap between a query and a memory record.",
  _recency: "Calculates a bounded recency score from a memory timestamp.",
  build_memory_context: "Ranks eligible memories and renders a token-bounded context block with provenance.",
  content_hash: "Computes a deterministic hash for normalized memory content.",
  is_duplicate: "Checks whether two content values normalize to the same hash.",
  normalize_entry_type: "Maps aliases and unknown values into a canonical memory entry type.",
  default_metadata_for_entry_type: "Returns default confidence, importance, and tags for a canonical memory type.",
  extract_with_rules: "Extracts memory candidates from an interaction using deterministic textual rules.",
  parse_llm_extraction: "Validates and normalizes structured LLM extraction output into memory candidates.",
  build_llm_extraction_prompt: "Builds the constrained prompt used for LLM-assisted memory extraction.",
  _safe_preview: "Creates a short redacted preview suitable for structured memory logs.",
  log_memory_event: "Emits a structured memory operation event with bounded, privacy-safe fields.",
  _parse_datetime: "Normalizes datetime values from database and serialized provider records.",
  contains_sensitive_content: "Reports whether text contains recognizable secret or sensitive-data patterns.",
  redact_sensitive_content: "Replaces sensitive spans with stable redaction markers.",
  is_safe_to_store: "Applies memory storage policy to determine whether content may be persisted.",
  sanitize_for_storage: "Returns safe memory content by rejecting or redacting sensitive values according to policy.",
  entry_to_record: "Maps a semantic memory database entity into the shared memory record value object."
};

const functionSummary = (name) => functionSummaries[name] ?? `${humanize(name)} helper for the memory subsystem.`;
const functionTags = (filePath, name) => {
  if (/sensitive|redact|safe/.test(name)) return ["security", "redaction", "privacy", "validation"];
  if (/duplicate|hash|cosine|jaccard|clash|detect/.test(name)) return ["deduplication", "similarity", "conflict-resolution", "memory"];
  if (/extract|classify|entry_type|title/.test(name)) return ["extraction", "classification", "memory", "normalization"];
  if (/context|relevance|recency/.test(name)) return ["context-building", "ranking", "retrieval", "memory"];
  if (/archive|episodic|json/.test(name)) return ["episodic-memory", "serialization", "archive", "utility"];
  if (/snapshot|checkpoint|compaction/.test(name)) return ["compaction", "working-memory", "snapshot", "retention"];
  if (/log|preview/.test(name)) return ["observability", "privacy", "logging", "memory"];
  return ["utility", "memory", "data-transformation", path.basename(filePath, ".py").replaceAll("_", "-")];
};

const classSummaries = {
  SqlMemoryStore: "Agent-facing SQL memory adapter that scopes operations by user and project and delegates persistence to the shared layer.",
  ClassifierCandidate: "Immutable classified memory candidate containing content, type, confidence, title, tags, and metadata.",
  ConflictHit: "Represents one existing memory and its duplicate, contradiction, or version-conflict scores.",
  ConflictReport: "Aggregates conflict hits and exposes the strongest duplicate candidate.",
  MemoryConfig: "Immutable effective settings for memory enablement, extraction, retention, embeddings, and context limits.",
  ExtractedMemory: "Structured candidate produced by deterministic or LLM-assisted interaction extraction.",
  MemoryTimer: "Measures elapsed milliseconds for memory operation telemetry.",
  MemoryStore: "Asynchronous storage protocol for generic get, set, delete, and search memory operations.",
  MemoryProvider: "Provider contract for scoped memory CRUD, search, deletion, and duplicate lookup.",
  SemanticMemoryProvider: "Adapts semantic memory repositories and namespaces to the shared provider contract.",
  MemoryRepository: "Persistence protocol for scoped memory CRUD, text or vector search, deduplication, and embedding enqueueing.",
  SqlMemoryRepository: "SQL-backed memory repository implementing scoped CRUD, search, vector lookup, deduplication, and embedding jobs.",
  MemoryAccessContext: "Immutable tenant and identity scope applied to every memory operation.",
  MemoryFilters: "Immutable query filters for memory type, tags, confidence, importance, and time windows.",
  MemoryRecord: "Cross-layer memory value object with content, metadata, provenance, scores, and display formatting.",
  MemoryService: "Coordinates configuration, redaction, extraction, deduplication, provider access, context building, embeddings, lifecycle, and telemetry."
};

const classTags = (filePath, name) => {
  if (name.endsWith("Repository")) return ["repository", "database", "memory", "data-access"];
  if (name.endsWith("Provider")) return ["provider", "adapter", "memory", "service"];
  if (name.endsWith("Store")) return ["memory-store", "adapter", "database", "agent-runtime"];
  if (["MemoryAccessContext", "MemoryFilters", "MemoryRecord", "MemoryConfig", "ClassifierCandidate", "ExtractedMemory", "ConflictHit", "ConflictReport"].includes(name)) return ["data-model", "type-definition", "memory", "immutable"];
  if (name === "MemoryTimer") return ["observability", "timing", "memory", "utility"];
  return ["service", "memory", "business-logic", path.basename(filePath, ".py")];
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
const entitiesByFile = new Map();

for (const file of input.batchFiles) {
  const result = resultsByPath.get(file.path);
  if (!result) throw new Error(`Missing extraction result for ${file.path}`);
  const fileId = `file:${file.path}`;
  const fileNode = {id: fileId, type: "file", name: path.basename(file.path), filePath: file.path, summary: summaries[file.path], tags: fileTags(file.path), complexity: complexity(result.nonEmptyLines)};
  const languageNotes = fileNotes(file.path);
  if (languageNotes) fileNode.languageNotes = languageNotes;
  if (!fileNode.summary) throw new Error(`Missing summary for ${file.path}`);
  addNode(fileNode);
  const exportNames = new Set((result.exports ?? []).map((item) => item.name));
  const entities = new Map();
  for (const fn of result.functions ?? []) {
    const id = `function:${file.path}:${fn.name}`;
    entities.set(fn.name, id);
    addNode({id, type: "function", name: fn.name, filePath: file.path, lineRange: [fn.startLine, fn.endLine], summary: functionSummary(fn.name), tags: functionTags(file.path, fn.name), complexity: complexity(fn.endLine - fn.startLine + 1)});
    addEdge(fileId, id, "contains", 1.0);
    if (exportNames.has(fn.name)) addEdge(fileId, id, "exports", 0.8);
  }
  for (const cls of result.classes ?? []) {
    const id = `class:${file.path}:${cls.name}`;
    entities.set(cls.name, id);
    addNode({id, type: "class", name: cls.name, filePath: file.path, lineRange: [cls.startLine, cls.endLine], summary: classSummaries[cls.name] ?? `${humanize(cls.name)} abstraction for the memory subsystem.`, tags: classTags(file.path, cls.name), complexity: complexity(cls.endLine - cls.startLine + 1)});
    addEdge(fileId, id, "contains", 1.0);
    if (exportNames.has(cls.name)) addEdge(fileId, id, "exports", 0.8);
  }
  entitiesByFile.set(file.path, entities);
}

for (const [sourcePath, targets] of Object.entries(input.batchImportData)) {
  for (const targetPath of targets) addEdge(`file:${sourcePath}`, `file:${targetPath}`, "imports", 0.7);
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
  const imported = new Map();
  for (const importedPath of input.batchImportData[result.path] ?? []) {
    for (const [symbol, id] of entitiesByFile.get(importedPath) ?? []) imported.set(symbol, id);
  }
  const neighbors = new Map();
  for (const neighbor of batch.neighborMap[result.path] ?? []) {
    for (const symbol of neighbor.symbols ?? []) neighbors.set(symbol, `${/^[A-Z]/.test(symbol) ? "class" : "function"}:${neighbor.path}:${symbol}`);
  }
  for (const call of result.callGraph ?? []) {
    const source = local.get(call.caller) ?? methodOwners.get(call.caller);
    if (!source) continue;
    const target = local.get(call.callee) ?? imported.get(call.callee) ?? neighbors.get(call.callee);
    if (target && source !== target) addEdge(source, target, "calls", 0.8);
  }
}

const implementations = [
  ["backend/modules/memory/layer/repository.py", "SqlMemoryRepository", "backend/modules/memory/layer/repository.py", "MemoryRepository"],
  ["backend/modules/memory/layer/provider.py", "SemanticMemoryProvider", "backend/modules/memory/layer/provider.py", "MemoryProvider"]
];
for (const [sourcePath, sourceName, targetPath, targetName] of implementations) {
  addEdge(`class:${sourcePath}:${sourceName}`, `class:${targetPath}:${targetName}`, "implements", 0.9);
}

for (const [sourcePath, neighbors] of Object.entries(batch.neighborMap)) {
  for (const neighbor of neighbors) if (neighbor.path.includes("/tests/")) addEdge(`file:${sourcePath}`, `file:${neighbor.path}`, "tested_by", 0.5);
}

const seenEdges = new Set();
const finalEdges = edges.filter((edge) => {
  const key = `${edge.source}\u0000${edge.target}\u0000${edge.type}`;
  if (seenEdges.has(key)) return false;
  seenEdges.add(key);
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
  const fileSet = new Set(sortedFiles.slice(index * groupSize, (index + 1) * groupSize).map((item) => item.path));
  if (!fileSet.size) continue;
  const partNodes = nodes.filter((node) => fileSet.has(node.filePath));
  const sourceIds = new Set(partNodes.map((node) => node.id));
  const partEdges = finalEdges.filter((edge) => sourceIds.has(edge.source));
  const outputPath = path.join(intermediate, `batch-13-part-${index + 1}.json`);
  fs.writeFileSync(outputPath, `${JSON.stringify({nodes: partNodes, edges: partEdges}, null, 2)}\n`);
  parts.push({outputPath, nodes: partNodes.length, edges: partEdges.length, files: fileSet.size});
}
if (parts.reduce((sum, item) => sum + item.nodes, 0) !== nodes.length) throw new Error("Node partition mismatch");
if (parts.reduce((sum, item) => sum + item.edges, 0) !== finalEdges.length) throw new Error("Edge partition mismatch");

const allNodeIds = new Set(nodes.map((node) => node.id));
const importedPaths = new Set(Object.values(input.batchImportData).flat());
const neighborPaths = new Set(Object.values(batch.neighborMap).flat().map((item) => item.path));
const neighborEntityIds = new Set();
for (const neighbors of Object.values(batch.neighborMap)) {
  for (const neighbor of neighbors) for (const symbol of neighbor.symbols ?? []) neighborEntityIds.add(`${/^[A-Z]/.test(symbol) ? "class" : "function"}:${neighbor.path}:${symbol}`);
}
for (const part of parts) {
  const parsed = JSON.parse(fs.readFileSync(part.outputPath, "utf8"));
  if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) throw new Error(`${part.outputPath} lacks arrays`);
  const sourceIds = new Set(parsed.nodes.map((node) => node.id));
  for (const node of parsed.nodes) {
    if (!node.id || !node.type || !node.name || !node.summary || !node.complexity || !Array.isArray(node.tags) || node.tags.length < 3 || node.tags.length > 5) throw new Error(`Invalid node ${node.id}`);
  }
  for (const edge of parsed.edges) {
    if (!sourceIds.has(edge.source)) throw new Error(`${part.outputPath}: unknown source ${edge.source}`);
    if (allNodeIds.has(edge.target) || neighborEntityIds.has(edge.target)) continue;
    if (edge.target.startsWith("file:")) {
      const targetPath = edge.target.slice(5);
      if (importedPaths.has(targetPath) || neighborPaths.has(targetPath)) continue;
    }
    throw new Error(`${part.outputPath}: unknown target ${edge.target}`);
  }
}

console.log(JSON.stringify({parts: parts.length, nodes: nodes.length, edges: finalEdges.length, imports: actualImports, details: parts.map((item) => ({file: path.basename(item.outputPath), nodes: item.nodes, edges: item.edges, files: item.files}))}, null, 2));
