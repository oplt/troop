import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const intermediate = path.join(root, ".understand-anything/intermediate");
const extracted = JSON.parse(
  fs.readFileSync(path.join(root, ".understand-anything/tmp/ua-file-extract-results-1.json"), "utf8"),
);
const batches = JSON.parse(fs.readFileSync(path.join(intermediate, "batches.json"), "utf8"));
const batch = batches.batches.find((entry) => entry.batchIndex === 1);
if (!batch) throw new Error("Batch 1 not found");

const fileMeta = {
  "backend/api/deps/admin.py": [
    "Provides the FastAPI dependency that restricts administrative endpoints to authenticated administrator accounts.",
    ["authentication", "authorization", "fastapi", "api-dependency"],
  ],
  "backend/api/deps/auth.py": [
    "Resolves authenticated users from access tokens, validates cached session state, and binds identity data to the request context.",
    ["authentication", "session", "fastapi", "api-dependency"],
  ],
  "backend/api/main.py": [
    "Bootstraps the FastAPI application, registers middleware and routers, and manages telemetry, storage, database, HTTP client, and Redis lifecycle resources.",
    ["entry-point", "fastapi", "application-lifecycle", "middleware"],
  ],
  "backend/api/middleware/correlation_id.py": [
    "Assigns and propagates correlation, request, and trace identifiers so requests can be followed across logs and services.",
    ["middleware", "observability", "request-context", "correlation-id"],
  ],
  "backend/api/middleware/csrf.py": [
    "Enforces double-submit CSRF validation for state-changing requests while allowing safe HTTP methods through unchanged.",
    ["middleware", "security", "csrf", "request-validation"],
  ],
  "backend/api/middleware/public_rate_limit.py": [
    "Applies Redis-backed rate limits to unauthenticated public API traffic while exempting authenticated requests and selected paths.",
    ["middleware", "rate-limiting", "redis", "security"],
  ],
  "backend/api/middleware/request_logging.py": [
    "Records structured request completion and failure events with duration, status, and bound request-context fields.",
    ["middleware", "logging", "observability", "request-context"],
  ],
  "backend/api/middleware/security_headers.py": [
    "Rejects disallowed hosts and adds browser-facing security headers to API responses.",
    ["middleware", "security", "http-headers", "request-validation"],
  ],
  "backend/api/router.py": [
    "Aggregates the product's domain routers into the versioned FastAPI API surface.",
    ["api-handler", "fastapi", "routing", "barrel"],
  ],
  "backend/api/v1/__init__.py": [
    "Marks the version-one API namespace for Python package discovery.",
    ["entry-point", "package", "api", "python"],
  ],
  "backend/api/v1/health.py": [
    "Exposes liveness, readiness, and version endpoints, including dependency health checks and visibility controls.",
    ["api-handler", "health-check", "observability", "fastapi"],
  ],
  "backend/core/cache.py": [
    "Implements the Redis-backed cache layer, cache policies, namespace versioning, single-flight loading, metrics, and domain-specific cache helpers.",
    ["cache", "redis", "performance", "infrastructure"],
  ],
  "backend/core/config.py": [
    "Defines and validates the application's centralized environment-driven settings for runtime, security, orchestration, storage, AI, RAG, and observability.",
    ["configuration", "pydantic", "environment", "security"],
  ],
  "backend/core/distributed_lock.py": [
    "Provides a Redis lease with ownership-safe acquisition and release for coordinating distributed work.",
    ["distributed-lock", "redis", "concurrency", "infrastructure"],
  ],
  "backend/core/error_handler.py": [
    "Registers FastAPI exception handlers that normalize validation, HTTP, and unexpected failures into structured error payloads.",
    ["error-handling", "fastapi", "api", "logging"],
  ],
  "backend/core/error_payloads.py": [
    "Builds the canonical API error envelope with codes, correlation identifiers, and optional details.",
    ["error-handling", "serialization", "api", "utility"],
  ],
  "backend/core/logging.py": [
    "Configures structured application logging, sensitive-value redaction, noisy-event filtering, and daily rotating files.",
    ["logging", "observability", "security", "configuration"],
  ],
  "backend/core/rate_limit.py": [
    "Provides reusable Redis-backed rate-limit checks, counters, key construction, and HTTP error generation.",
    ["rate-limiting", "redis", "security", "utility"],
  ],
  "backend/core/request_context.py": [
    "Maintains request-scoped correlation, trace, user, project, task, run, and job metadata for logs and asynchronous task propagation.",
    ["request-context", "observability", "context-vars", "logging"],
  ],
  "backend/core/schemas.py": [
    "Defines the shared strict request-model base used by API validation schemas.",
    ["data-model", "pydantic", "validation", "type-definition"],
  ],
  "backend/core/security.py": [
    "Provides password hashing, JWT access tokens, CSRF tokens, and refresh-token generation and hashing primitives.",
    ["security", "authentication", "cryptography", "utility"],
  ],
  "backend/core/storage.py": [
    "Wraps S3-compatible object storage with bucket initialization, upload, download, deletion, public URL construction, and normalized errors.",
    ["object-storage", "s3", "infrastructure", "service"],
  ],
  "backend/core/telemetry.py": [
    "Connects application startup to the shared Sentry and OpenTelemetry instrumentation setup.",
    ["observability", "telemetry", "sentry", "opentelemetry"],
  ],
  "backend/db/session.py": [
    "Creates the asynchronous SQLAlchemy engine and session factory and exposes request-scoped database sessions.",
    ["database", "sqlalchemy", "session", "api-dependency"],
  ],
  "backend/modules/admin/router.py": [
    "Implements administrator APIs for user management, audit-log inspection, and platform metrics.",
    ["api-handler", "admin", "fastapi", "audit"],
  ],
  "backend/modules/admin/schemas.py": [
    "Defines request and response schemas for administrator user management, audit logs, and aggregate metrics.",
    ["data-model", "pydantic", "admin", "validation"],
  ],
  "backend/modules/ai/models.py": [
    "Defines SQLAlchemy persistence models for prompts, documents and chunks, AI runs, human review, feedback, and evaluation datasets.",
    ["data-model", "sqlalchemy", "ai", "database"],
  ],
  "backend/modules/ai/repository.py": [
    "Provides asynchronous persistence queries and mutations for AI prompts, documents, runs, reviews, feedback, and evaluations.",
    ["repository", "database", "sqlalchemy", "ai"],
  ],
  "backend/modules/ai/router.py": [
    "Exposes the AI module's FastAPI endpoints for prompts, providers, documents, retrieval, generation runs, reviews, feedback, and evaluations.",
    ["api-handler", "fastapi", "ai", "evaluation"],
  ],
  "backend/modules/ai/schemas.py": [
    "Defines the AI module's validated API contracts for prompts, providers, documents, retrieval, runs, review, feedback, and evaluations.",
    ["data-model", "pydantic", "ai", "validation"],
  ],
  "backend/modules/ai/service.py": [
    "Orchestrates AI providers, prompt versioning, document ingestion and retrieval, model runs, review workflows, feedback, and evaluation execution.",
    ["service", "ai", "rag", "evaluation"],
  ],
  "backend/modules/audit/repository.py": [
    "Persists structured audit events and queries recent or user-scoped audit history.",
    ["repository", "audit", "database", "security"],
  ],
  "backend/modules/calendar/router.py": [
    "Exposes authenticated CRUD endpoints for user calendar and planner items.",
    ["api-handler", "fastapi", "calendar", "crud"],
  ],
  "backend/modules/companies/router.py": [
    "Exposes authenticated company listing, creation, default-company lookup, and update endpoints.",
    ["api-handler", "fastapi", "company", "crud"],
  ],
};

function words(name) {
  return name
    .replace(/^_+/, "")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function complexity(start, end) {
  const lines = Math.max(1, end - start + 1);
  if (lines > 200) return "complex";
  if (lines >= 50) return "moderate";
  return "simple";
}

function fileComplexity(result) {
  if (result.nonEmptyLines > 200) return "complex";
  if (result.nonEmptyLines >= 50) return "moderate";
  return "simple";
}

function functionTags(filePath) {
  if (filePath.includes("/router.py") || filePath.includes("/health.py")) {
    return ["api-handler", "fastapi", "endpoint"];
  }
  if (filePath.includes("/cache.py")) return ["cache", "redis", "utility"];
  if (filePath.includes("/security.py")) return ["security", "authentication", "utility"];
  if (filePath.includes("/logging.py")) return ["logging", "observability", "utility"];
  if (filePath.includes("/request_context.py")) return ["request-context", "observability", "utility"];
  if (filePath.includes("/rate_limit.py")) return ["rate-limiting", "redis", "security"];
  if (filePath.includes("/telemetry.py")) return ["telemetry", "observability", "configuration"];
  if (filePath.includes("/error")) return ["error-handling", "api", "serialization"];
  if (filePath.includes("/deps/")) return ["api-dependency", "authentication", "fastapi"];
  if (filePath.endsWith("/main.py")) return ["entry-point", "application-lifecycle", "fastapi"];
  if (filePath.includes("/ai/service.py")) return ["service", "ai", "business-logic"];
  return ["utility", "python", "backend"];
}

function classTags(filePath, name) {
  if (name.endsWith("Middleware")) return ["middleware", "fastapi", "request-processing"];
  if (filePath.includes("/models.py")) return ["data-model", "sqlalchemy", "database"];
  if (filePath.includes("/schemas.py")) return ["data-model", "pydantic", "validation"];
  if (name.endsWith("Repository")) return ["repository", "database", "data-access"];
  if (name.endsWith("Service")) return ["service", "business-logic", "orchestration"];
  if (filePath.includes("/cache.py")) return ["cache", "redis", "infrastructure"];
  if (filePath.includes("/storage.py")) return ["object-storage", "s3", "infrastructure"];
  if (filePath.includes("/config.py")) return ["configuration", "pydantic", "environment"];
  if (filePath.includes("/request_context.py")) return ["request-context", "observability", "data-model"];
  if (filePath.includes("/distributed_lock.py")) return ["distributed-lock", "redis", "concurrency"];
  if (filePath.includes("/logging.py")) return ["logging", "observability", "filter"];
  return ["class", "python", "backend"];
}

function functionSummary(filePath, name) {
  const label = words(name);
  if (name.endsWith("_to_response") || name.includes("_to_response")) {
    return `Converts ${label.replace(/ to response$/, "")} domain data into its API response representation.`;
  }
  if (filePath.includes("/router.py") || filePath.includes("/health.py")) {
    if (name.startsWith("list_")) return `Handles the API operation that lists ${words(name.slice(5))}.`;
    if (name.startsWith("get_")) return `Handles the API operation that retrieves ${words(name.slice(4))}.`;
    if (name.startsWith("create_")) return `Handles the API operation that creates ${words(name.slice(7))}.`;
    if (name.startsWith("update_")) return `Handles the API operation that updates ${words(name.slice(7))}.`;
    if (name.startsWith("delete_")) return `Handles the API operation that deletes ${words(name.slice(7))}.`;
    if (name.startsWith("run_")) return `Handles the API operation that runs ${words(name.slice(4))}.`;
    return `Implements the ${label} API operation.`;
  }
  if (filePath.includes("/cache.py")) return `Implements ${label} behavior for the shared Redis-backed cache layer.`;
  if (filePath.includes("/security.py")) return `Implements the ${label} security primitive used by authentication flows.`;
  if (filePath.includes("/rate_limit.py")) return `Implements ${label} behavior for reusable request throttling.`;
  if (filePath.includes("/request_context.py")) return `Implements ${label} behavior for request-scoped metadata propagation.`;
  if (filePath.includes("/logging.py")) return `Implements ${label} behavior for the structured logging configuration.`;
  if (filePath.includes("/telemetry.py")) return `Configures ${label} as part of application telemetry startup.`;
  if (filePath.includes("/error")) return `Implements ${label} behavior for normalized API error handling.`;
  if (filePath.includes("/deps/")) return `Resolves ${label} as a FastAPI request dependency.`;
  if (filePath.endsWith("/main.py")) return `Manages ${label} resources across FastAPI application startup and shutdown.`;
  if (filePath.includes("/ai/service.py")) return `Implements ${label} within the AI application service.`;
  return `Implements ${label} for the backend application.`;
}

const specialClassSummaries = {
  CorrelationIdMiddleware: "ASGI middleware that normalizes or generates request identifiers and binds them to the request context.",
  CSRFMiddleware: "ASGI middleware that validates matching CSRF cookie and header values for unsafe HTTP methods.",
  PublicRateLimitMiddleware: "ASGI middleware that meters unauthenticated public traffic with Redis counters and retry metadata.",
  RequestLoggingMiddleware: "ASGI middleware that emits structured success and exception logs with timing and request context.",
  SecurityHeadersMiddleware: "ASGI middleware that validates hosts and attaches protective browser response headers.",
  CacheKey: "Value object describing a cache namespace, raw key value, and optional namespace versioning.",
  CachePolicy: "Cache behavior definition containing TTL, negative caching, jitter, and fail-open settings.",
  CacheStore: "Abstract asynchronous cache-store contract for lookup, mutation, deletion, and counters.",
  RedisCacheStore: "Redis implementation of the shared asynchronous cache-store contract.",
  AsyncSingleFlight: "Coalesces concurrent requests for the same cache key into one in-flight loader operation.",
  Settings: "Central Pydantic settings model that validates operational, security, infrastructure, and AI runtime configuration.",
  RedisLease: "Ownership-aware Redis lease supporting explicit and asynchronous-context-manager lifecycle operations.",
  _RedactSensitiveValues: "Logging filter that recursively redacts sensitive values before records are emitted.",
  _IgnoreSqlalchemyPoolCancelledTerminate: "Logging filter that suppresses expected SQLAlchemy pool cancellation noise.",
  RequestContext: "Immutable request metadata model that serializes identifiers into log fields and task headers.",
  RequestModel: "Strict Pydantic base model that rejects undeclared request fields.",
  StorageNotConfiguredError: "Signals that an object-storage operation was attempted without usable storage configuration.",
  ObjectStorageError: "Normalizes failures raised by the S3-compatible object-storage adapter.",
  ObjectStorage: "Asynchronous facade over S3-compatible bucket, object, and public URL operations.",
  AiRepository: "Asynchronous data-access layer for AI prompt, document, run, review, feedback, and evaluation records.",
  AiService: "Application service coordinating AI providers, retrieval, document ingestion, generation, review, and evaluation workflows.",
  AuditRepository: "Asynchronous data-access layer for writing and querying structured audit events.",
};

function classSummary(filePath, name) {
  if (specialClassSummaries[name]) return specialClassSummaries[name];
  if (filePath.includes("/models.py")) return `SQLAlchemy persistence model representing ${words(name)} records.`;
  if (filePath.includes("/schemas.py")) return `Pydantic API schema representing ${words(name)} data.`;
  if (name.endsWith("Repository")) return `Data-access abstraction for ${words(name.replace(/Repository$/, ""))} persistence operations.`;
  if (name.endsWith("Service")) return `Coordinates ${words(name.replace(/Service$/, ""))} business operations.`;
  return `Implements the ${words(name)} backend component.`;
}

const nodes = [];
const edges = [];
const nodeIds = new Set();
const symbolIdsByFile = new Map();

function addNode(node) {
  if (nodeIds.has(node.id)) throw new Error(`Duplicate node ID: ${node.id}`);
  nodeIds.add(node.id);
  nodes.push(node);
}

function addEdge(edge) {
  if (edge.source === edge.target) return;
  const key = `${edge.source}\0${edge.target}\0${edge.type}`;
  if (!addEdge.seen) addEdge.seen = new Set();
  if (addEdge.seen.has(key)) return;
  addEdge.seen.add(key);
  edges.push(edge);
}

for (const result of extracted.results) {
  const [summary, tags] = fileMeta[result.path];
  const fileId = `file:${result.path}`;
  addNode({
    id: fileId,
    type: "file",
    name: path.basename(result.path),
    filePath: result.path,
    summary,
    tags,
    complexity: fileComplexity(result),
  });

  const exports = new Set((result.exports ?? []).map((entry) => entry.name));
  const fileSymbols = new Map();
  for (const fn of result.functions ?? []) {
    const length = fn.endLine - fn.startLine + 1;
    if (!exports.has(fn.name) && length < 10) continue;
    const id = `function:${result.path}:${fn.name}`;
    addNode({
      id,
      type: "function",
      name: fn.name,
      filePath: result.path,
      lineRange: [fn.startLine, fn.endLine],
      summary: functionSummary(result.path, fn.name),
      tags: functionTags(result.path),
      complexity: complexity(fn.startLine, fn.endLine),
    });
    fileSymbols.set(fn.name, id);
    addEdge({ source: fileId, target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(fn.name)) {
      addEdge({ source: fileId, target: id, type: "exports", direction: "forward", weight: 0.8 });
    }
  }

  for (const cls of result.classes ?? []) {
    const length = cls.endLine - cls.startLine + 1;
    if (!exports.has(cls.name) && (cls.methods?.length ?? 0) < 2 && length < 20) continue;
    const id = `class:${result.path}:${cls.name}`;
    addNode({
      id,
      type: "class",
      name: cls.name,
      filePath: result.path,
      lineRange: [cls.startLine, cls.endLine],
      summary: classSummary(result.path, cls.name),
      tags: classTags(result.path, cls.name),
      complexity: complexity(cls.startLine, cls.endLine),
    });
    fileSymbols.set(cls.name, id);
    for (const method of cls.methods ?? []) fileSymbols.set(method, id);
    addEdge({ source: fileId, target: id, type: "contains", direction: "forward", weight: 1.0 });
    if (exports.has(cls.name)) {
      addEdge({ source: fileId, target: id, type: "exports", direction: "forward", weight: 0.8 });
    }
  }
  symbolIdsByFile.set(result.path, fileSymbols);
}

let omittedSelfImports = 0;
for (const [sourcePath, targets] of Object.entries(batch.batchImportData)) {
  for (const targetPath of targets) {
    if (sourcePath === targetPath) {
      omittedSelfImports += 1;
      continue;
    }
    addEdge({
      source: `file:${sourcePath}`,
      target: `file:${targetPath}`,
      type: "imports",
      direction: "forward",
      weight: 0.7,
    });
  }
}

for (const result of extracted.results) {
  const localSymbols = symbolIdsByFile.get(result.path) ?? new Map();
  const neighbors = batch.neighborMap[result.path] ?? [];
  const crossSymbols = new Map();
  for (const neighbor of neighbors) {
    for (const symbol of neighbor.symbols ?? []) {
      if (!crossSymbols.has(symbol)) crossSymbols.set(symbol, neighbor.path);
    }
    if (neighbor.path.includes("/tests/") || path.basename(neighbor.path).startsWith("test_")) {
      addEdge({
        source: `file:${result.path}`,
        target: `file:${neighbor.path}`,
        type: "tested_by",
        direction: "forward",
        weight: 0.5,
      });
    }
  }
  for (const call of result.callGraph ?? []) {
    const targetPath = crossSymbols.get(call.callee);
    if (!targetPath) continue;
    const sourceId = localSymbols.get(call.caller) ?? `file:${result.path}`;
    const targetPrefix = /^[A-Z]/.test(call.callee) ? "class" : "function";
    addEdge({
      source: sourceId,
      target: `${targetPrefix}:${targetPath}:${call.callee}`,
      type: "calls",
      direction: "forward",
      weight: 0.8,
    });
  }
}

const nodeCount = nodes.length;
const edgeCount = edges.length;
const parts = Math.ceil(Math.max(nodeCount / 60, edgeCount / 120));
const sortedFiles = [...batch.files].sort((a, b) => a.path.localeCompare(b.path));
const chunkSize = Math.ceil(sortedFiles.length / parts);
const written = [];

for (let index = 0; index < parts; index += 1) {
  const paths = new Set(sortedFiles.slice(index * chunkSize, (index + 1) * chunkSize).map((entry) => entry.path));
  if (paths.size === 0) continue;
  const partNodes = nodes.filter((node) => paths.has(node.filePath));
  const partNodeIds = new Set(partNodes.map((node) => node.id));
  const partEdges = edges.filter((edge) => partNodeIds.has(edge.source));
  const outputPath = path.join(intermediate, `batch-1-part-${index + 1}.json`);
  fs.writeFileSync(outputPath, `${JSON.stringify({ nodes: partNodes, edges: partEdges }, null, 2)}\n`);
  written.push({ outputPath, nodes: partNodes.length, edges: partEdges.length });
}

const allowedExternalFiles = new Set([
  ...Object.keys(batch.batchImportData),
  ...Object.values(batch.batchImportData).flat(),
  ...Object.keys(batch.neighborMap),
  ...Object.values(batch.neighborMap).flatMap((entries) => entries.map((entry) => entry.path)),
]);
const neighborSymbols = new Map();
for (const entries of Object.values(batch.neighborMap)) {
  for (const neighbor of entries) neighborSymbols.set(neighbor.path, new Set(neighbor.symbols ?? []));
}

for (const entry of written) {
  const fragment = JSON.parse(fs.readFileSync(entry.outputPath, "utf8"));
  const ids = new Set(fragment.nodes.map((node) => node.id));
  for (const edge of fragment.edges) {
    if (!ids.has(edge.source)) throw new Error(`Part source missing: ${edge.source}`);
    if (ids.has(edge.target)) continue;
    const fileMatch = /^file:(.+)$/.exec(edge.target);
    if (fileMatch && allowedExternalFiles.has(fileMatch[1])) continue;
    const symbolMatch = /^(?:function|class):(.+):([^:]+)$/.exec(edge.target);
    if (symbolMatch && neighborSymbols.get(symbolMatch[1])?.has(symbolMatch[2])) continue;
    throw new Error(`Part target is not validated: ${edge.target}`);
  }
}

process.stdout.write(
  JSON.stringify({ parts: written, nodeCount, edgeCount, omittedSelfImports, filesSkipped: extracted.filesSkipped ?? [] }),
);
