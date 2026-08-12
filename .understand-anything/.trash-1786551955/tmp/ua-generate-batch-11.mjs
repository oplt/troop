import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tmp = path.join(root, ".understand-anything/tmp");
const intermediate = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tmp, "ua-file-extract-results-11.json"), "utf8"));
const batches = JSON.parse(fs.readFileSync(path.join(intermediate, "batches.json"), "utf8"));
const batch = batches.batches.find((item) => item.batchIndex === 11);
if (!batch) throw new Error("Batch 11 not found");

const meta = {
  "backend/api/deps/rag.py": ["Builds the request-scoped RAG service dependency from the active database session.", ["api-dependency", "rag", "fastapi", "factory"]],
  "backend/core/external_http.py": ["Centralizes outbound HTTP timeouts, tracing headers, idempotency-aware retry policy, and retryable status behavior.", ["http-client", "resilience", "retry", "observability"]],
  "backend/core/http_cache.py": ["Computes stable document-list ETags and applies private conditional-request cache headers.", ["http-cache", "etag", "performance", "api"]],
  "backend/core/http_clients.py": ["Pools purpose-scoped asynchronous HTTP clients and manages application and worker shutdown lifecycles.", ["http-client", "connection-pool", "infrastructure", "lifecycle"]],
  "backend/modules/ai/providers.py": ["Defines the AI provider abstraction and local, OpenAI, and Anthropic implementations for generation, streaming, embeddings, token accounting, and structured output.", ["ai-provider", "llm", "embeddings", "service"]],
  "backend/modules/observability/decorators.py": ["Provides instrumentation decorators for measuring provider calls and streamed provider responses.", ["observability", "telemetry", "decorator", "ai-provider"]],
  "backend/modules/orchestration/local_runtime.py": ["Starts, monitors, records, and shuts down locally managed model-provider processes with health checks and captured logs.", ["local-runtime", "process-management", "ai-provider", "observability"]],
  "backend/modules/orchestration/providers.py": ["Implements provider capability discovery and prompt execution across OpenAI-compatible, Anthropic, Ollama, and local runtimes.", ["ai-provider", "llm", "capability-discovery", "orchestration"]],
  "backend/modules/orchestration/security.py": ["Encrypts provider credentials at rest, decrypts them for use, and produces safe masked representations.", ["security", "encryption", "secrets", "orchestration"]],
  "backend/modules/orchestration/services/providers_service.py": ["Coordinates provider CRUD, validation, model discovery, health checks, comparisons, capability records, cost estimates, and runtime resolution.", ["service", "ai-provider", "health-check", "orchestration"]],
  "backend/modules/orchestration/tools.py": ["Executes approval-aware orchestration tools for GitHub, web access, code, scoped filesystems, database queries, repository search, and knowledge retrieval.", ["tool-execution", "orchestration", "security", "sandbox"]],
  "backend/modules/rag/__init__.py": ["Publishes the RAG router and core request/response schemas as the module's package API.", ["barrel", "rag", "api", "entry-point"]],
  "backend/modules/rag/bulk_ingest.py": ["Ingests multiple RAG documents concurrently with bounded parallelism, per-item error capture, and optional asynchronous indexing.", ["rag", "bulk-ingest", "concurrency", "data-pipeline"]],
  "backend/modules/rag/chunking.py": ["Splits normalized document text into overlapping token-aware chunks and attaches indexing metadata.", ["rag", "chunking", "data-pipeline", "text-processing"]],
  "backend/modules/rag/citations.py": ["Transforms retrieval matches into stable source citations and formats inline reference context.", ["rag", "citations", "serialization", "service"]],
  "backend/modules/rag/config.py": ["Defines the resolved RAG runtime configuration and derives provider-specific score thresholds from application settings.", ["configuration", "rag", "pydantic", "retrieval"]],
  "backend/modules/rag/embedding.py": ["Generates document and query embeddings in retryable batches through the configured AI provider registry.", ["rag", "embeddings", "retry", "ai-provider"]],
  "backend/modules/rag/evaluation.py": ["Defines deterministic retrieval evaluation cases and scores recall, unexpected matches, and answer grounding.", ["rag", "evaluation", "quality", "testing"]],
  "backend/modules/rag/observability.py": ["Emits privacy-aware structured RAG events and provides elapsed-time measurement for pipeline stages.", ["rag", "observability", "logging", "privacy"]],
  "backend/modules/rag/parsing.py": ["Detects source formats and normalizes text, JSON, HTML, and CSV documents for RAG ingestion with checksums.", ["rag", "parsing", "data-pipeline", "normalization"]],
  "backend/modules/rag/prompt_builder.py": ["Builds bounded retrieval context blocks, grounded answer prompts, and no-context fallback responses.", ["rag", "prompt-builder", "grounding", "llm"]],
  "backend/modules/rag/reranker.py": ["Optionally reranks retrieval matches by score and query-term overlap while preserving configured limits.", ["rag", "reranking", "retrieval", "service"]],
};

function human(name) {
  return name.replace(/^_+/, "").replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/_/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
}
function complexity(start, end) {
  const lines = end - start + 1;
  return lines > 200 ? "complex" : lines >= 50 ? "moderate" : "simple";
}
function fileComplexity(result) {
  return result.nonEmptyLines > 200 ? "complex" : result.nonEmptyLines >= 50 ? "moderate" : "simple";
}
function functionTags(filePath) {
  if (filePath.includes("/rag/")) return ["rag", "utility", "data-pipeline"];
  if (filePath.includes("/providers.py")) return ["ai-provider", "llm", "orchestration"];
  if (filePath.includes("/local_runtime.py")) return ["local-runtime", "process-management", "utility"];
  if (filePath.includes("/security.py")) return ["security", "encryption", "secrets"];
  if (filePath.includes("/observability/")) return ["observability", "telemetry", "decorator"];
  if (filePath.includes("/http_cache.py")) return ["http-cache", "etag", "utility"];
  if (filePath.includes("/external_http.py") || filePath.includes("/http_clients.py")) return ["http-client", "resilience", "infrastructure"];
  if (filePath.includes("/deps/")) return ["api-dependency", "rag", "fastapi"];
  if (filePath.includes("/tools.py")) return ["tool-execution", "security", "orchestration"];
  return ["backend", "python", "utility"];
}
function functionSummary(filePath, name) {
  const label = human(name);
  if (name === "get_rag_service") return "Constructs the request-scoped RAG service over the active database session.";
  if (filePath.includes("/providers.py")) return `Implements ${label} behavior for model-provider capability discovery or execution.`;
  if (filePath.includes("/local_runtime.py")) return `Implements ${label} behavior for locally managed provider runtimes.`;
  if (filePath.includes("/rag/")) return `Implements ${label} within the retrieval-augmented generation pipeline.`;
  if (filePath.includes("/http_cache.py")) return `Implements ${label} for conditional HTTP document-list caching.`;
  if (filePath.includes("/external_http.py") || filePath.includes("/http_clients.py")) return `Implements ${label} for resilient outbound HTTP communication.`;
  if (filePath.includes("/security.py")) return `Implements ${label} for protected provider secrets.`;
  if (filePath.includes("/observability/")) return `Instruments ${label} provider operations with metrics and tracing.`;
  if (filePath.includes("/tools.py")) return `Implements ${label} for safe orchestration tool results.`;
  return `Implements ${label} for the backend application.`;
}

const specialClasses = {
  ExternalRetryPolicy: "Immutable outbound HTTP retry policy describing attempt limits, statuses, timeout behavior, and rationale.",
  ExternalHttpClientPool: "Caches purpose-scoped HTTPX clients and closes them safely during application shutdown.",
  ProviderGenerateRequest: "Normalized generation request shared by AI provider implementations.",
  ProviderGenerateResult: "Normalized provider response carrying text or JSON output and token accounting.",
  BaseAiProvider: "Abstract interface for provider generation, streaming, and embedding operations.",
  LocalHeuristicProvider: "Deterministic local provider used for heuristic generation and embeddings without an external model service.",
  OpenAIProvider: "OpenAI-compatible provider implementing generation, streaming, structured output, and embeddings.",
  AnthropicProvider: "Anthropic provider implementing message generation and compatibility embeddings behavior.",
  AiProviderRegistry: "Selects configured AI providers and delegates generation, streaming, and embedding requests.",
  ProviderExecutionResult: "Normalized orchestration provider result with output, token usage, and latency measurements.",
  OrchestrationProvidersServiceMixin: "Application-service mixin coordinating provider configuration, health, discovery, comparisons, cost, and execution resolution.",
  ToolExecutionError: "Normalized exception raised when an orchestration tool cannot execute safely or successfully.",
  OrchestrationToolbox: "Approval-aware dispatcher implementing GitHub, web, code, filesystem, database, repository, and knowledge tools.",
  ChunkingOptions: "Chunk-size and overlap parameters used by the document chunking pipeline.",
  ChunkingService: "Token-aware text chunker that emits indexed RAG chunks with source metadata.",
  SourceCitationService: "Builds structured citations and inline references from retrieval results.",
  RagConfig: "Resolved RAG settings model covering providers, chunking, retrieval, reranking, context, and fallbacks.",
  EmbeddingService: "Batches and retries embedding requests through the AI provider registry.",
  RetrievalEvalCase: "Expected and negative chunk identifiers plus recall threshold for one retrieval evaluation.",
  RetrievalEvalResult: "Measured retrieval outcome with returned, missing, unexpected, and recall values.",
  RagTimer: "Monotonic elapsed-time helper for RAG pipeline observability.",
  DocumentParser: "Normalizes supported document formats into text and structured metadata for ingestion.",
  RagPromptBuilder: "Builds grounded prompts and bounded context blocks from retrieval matches.",
  RerankerService: "Reranks retrieved chunks using score and lexical overlap signals when enabled.",
};
function classSummary(filePath, name) {
  return specialClasses[name] ?? `Implements the ${human(name)} backend component.`;
}
function classTags(filePath, name) {
  if (filePath.includes("/rag/")) return ["rag", name.includes("Config") ? "configuration" : "service", "data-pipeline"];
  if (filePath.includes("/providers.py")) return ["ai-provider", "llm", "service"];
  if (filePath.includes("/tools.py")) return ["tool-execution", "orchestration", "security"];
  if (filePath.includes("/http")) return ["http-client", "infrastructure", "resilience"];
  return ["backend", "python", "class"];
}

const nodes = [];
const edges = [];
const ids = new Set();
const edgeKeys = new Set();
const symbolsByFile = new Map();
function addNode(node) {
  if (ids.has(node.id)) throw new Error(`Duplicate node ${node.id}`);
  ids.add(node.id);
  nodes.push(node);
}
function addEdge(edge) {
  if (edge.source === edge.target) return;
  const key = `${edge.source}\0${edge.target}\0${edge.type}`;
  if (edgeKeys.has(key)) return;
  edgeKeys.add(key);
  edges.push(edge);
}

for (const result of extraction.results) {
  const [summary, tags] = meta[result.path];
  const fileId = `file:${result.path}`;
  addNode({ id: fileId, type: "file", name: path.basename(result.path), filePath: result.path, summary, tags, complexity: fileComplexity(result) });
  const exports = new Set((result.exports ?? []).map((item) => item.name));
  const localSymbols = new Map();
  for (const fn of result.functions ?? []) {
    const lines = fn.endLine - fn.startLine + 1;
    if (!exports.has(fn.name) && lines < 10) continue;
    const id = `function:${result.path}:${fn.name}`;
    addNode({ id, type: "function", name: fn.name, filePath: result.path, lineRange: [fn.startLine, fn.endLine], summary: functionSummary(result.path, fn.name), tags: functionTags(result.path), complexity: complexity(fn.startLine, fn.endLine) });
    localSymbols.set(fn.name, id);
    addEdge({ source: fileId, target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(fn.name)) addEdge({ source: fileId, target: id, type: "exports", direction: "forward", weight: 0.8 });
  }
  for (const cls of result.classes ?? []) {
    const lines = cls.endLine - cls.startLine + 1;
    if (!exports.has(cls.name) && (cls.methods?.length ?? 0) < 2 && lines < 20) continue;
    const id = `class:${result.path}:${cls.name}`;
    addNode({ id, type: "class", name: cls.name, filePath: result.path, lineRange: [cls.startLine, cls.endLine], summary: classSummary(result.path, cls.name), tags: classTags(result.path, cls.name), complexity: complexity(cls.startLine, cls.endLine) });
    localSymbols.set(cls.name, id);
    for (const method of cls.methods ?? []) localSymbols.set(method, id);
    addEdge({ source: fileId, target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(cls.name)) addEdge({ source: fileId, target: id, type: "exports", direction: "forward", weight: 0.8 });
  }
  symbolsByFile.set(result.path, localSymbols);
}

for (const [sourcePath, targets] of Object.entries(batch.batchImportData)) {
  for (const targetPath of targets) addEdge({ source: `file:${sourcePath}`, target: `file:${targetPath}`, type: "imports", direction: "forward", weight: 0.7 });
}

for (const result of extraction.results) {
  const neighbors = batch.neighborMap[result.path] ?? [];
  const crossSymbols = new Map();
  for (const neighbor of neighbors) {
    for (const symbol of neighbor.symbols ?? []) if (!crossSymbols.has(symbol)) crossSymbols.set(symbol, neighbor.path);
    if (neighbor.path.includes("/tests/") || path.basename(neighbor.path).startsWith("test_")) addEdge({ source: `file:${result.path}`, target: `file:${neighbor.path}`, type: "tested_by", direction: "forward", weight: 0.5 });
  }
  const localSymbols = symbolsByFile.get(result.path) ?? new Map();
  for (const call of result.callGraph ?? []) {
    const targetPath = crossSymbols.get(call.callee);
    if (!targetPath) continue;
    const prefix = /^[A-Z]/.test(call.callee) ? "class" : "function";
    addEdge({ source: localSymbols.get(call.caller) ?? `file:${result.path}`, target: `${prefix}:${targetPath}:${call.callee}`, type: "calls", direction: "forward", weight: 0.8 });
  }
}

const partCount = Math.ceil(Math.max(nodes.length / 60, edges.length / 120));
const files = [...batch.files].sort((left, right) => left.path.localeCompare(right.path));
const chunkSize = Math.ceil(files.length / partCount);
const outputs = [];
for (let index = 0; index < partCount; index += 1) {
  const filePaths = new Set(files.slice(index * chunkSize, (index + 1) * chunkSize).map((item) => item.path));
  if (!filePaths.size) continue;
  const partNodes = nodes.filter((node) => filePaths.has(node.filePath));
  const partIds = new Set(partNodes.map((node) => node.id));
  const partEdges = edges.filter((edge) => partIds.has(edge.source));
  const outputPath = path.join(intermediate, `batch-11-part-${index + 1}.json`);
  fs.writeFileSync(outputPath, `${JSON.stringify({ nodes: partNodes, edges: partEdges }, null, 2)}\n`);
  outputs.push({ outputPath, nodes: partNodes.length, edges: partEdges.length });
}

const allowedFiles = new Set([...Object.keys(batch.batchImportData), ...Object.values(batch.batchImportData).flat(), ...Object.keys(batch.neighborMap), ...Object.values(batch.neighborMap).flatMap((items) => items.map((item) => item.path))]);
const neighborSymbols = new Map();
for (const items of Object.values(batch.neighborMap)) for (const neighbor of items) neighborSymbols.set(neighbor.path, new Set(neighbor.symbols ?? []));
for (const output of outputs) {
  const fragment = JSON.parse(fs.readFileSync(output.outputPath, "utf8"));
  const partIds = new Set(fragment.nodes.map((node) => node.id));
  for (const edge of fragment.edges) {
    if (!partIds.has(edge.source)) throw new Error(`Missing source ${edge.source}`);
    if (partIds.has(edge.target)) continue;
    const fileMatch = /^file:(.+)$/.exec(edge.target);
    if (fileMatch && allowedFiles.has(fileMatch[1])) continue;
    const symbolMatch = /^(?:function|class):(.+):([^:]+)$/.exec(edge.target);
    if (symbolMatch && neighborSymbols.get(symbolMatch[1])?.has(symbolMatch[2])) continue;
    throw new Error(`Unvalidated target ${edge.target}`);
  }
}

process.stdout.write(JSON.stringify({ outputs, nodeCount: nodes.length, edgeCount: edges.length, filesSkipped: extraction.filesSkipped ?? [] }));
