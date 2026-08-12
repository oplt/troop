import fs from "node:fs";
import path from "node:path";

const root = "/home/polat/Desktop/Projects/troop";
const tempDir = path.join(root, ".understand-anything/tmp");
const outputDir = path.join(root, ".understand-anything/intermediate");
const extraction = JSON.parse(fs.readFileSync(path.join(tempDir, "ua-file-extract-results-2.json"), "utf8"));
const input = JSON.parse(fs.readFileSync(path.join(tempDir, "ua-file-analyzer-input-2.json"), "utf8"));
const batches = JSON.parse(fs.readFileSync(path.join(outputDir, "batches.json"), "utf8"));
const batch = batches.batches.find((item) => item.batchIndex === 2);

if (!batch) throw new Error("Batch 2 is missing from batches.json");

const fileSummaries = {
  "backend/modules/companies/schemas.py": "Defines request and response models for creating, updating, and returning company records.",
  "backend/modules/github/router.py": "Exposes authenticated GitHub integration endpoints for connections, repositories, issue imports, approval-backed writes, sync replay, and webhook ingestion.",
  "backend/modules/github/schemas.py": "Defines validation and serialization contracts for GitHub connections, repositories, issue links, synchronization events, pull requests, comments, and webhooks.",
  "backend/modules/identity_access/models.py": "Defines persistent user accounts and refresh sessions, including identity, verification, MFA, and token lifecycle fields.",
  "backend/modules/identity_access/repository.py": "Encapsulates database queries and mutations for users and refresh sessions used by the authentication service.",
  "backend/modules/identity_access/router.py": "Implements the authentication HTTP surface, including signup, login, token refresh, logout, email verification, password recovery, MFA, and secure cookie management.",
  "backend/modules/identity_access/schemas.py": "Defines validated authentication requests and serialized user, session, MFA, and generic message responses.",
  "backend/modules/identity_access/service.py": "Coordinates account creation, credential checks, token rotation, email verification, password resets, MFA enrollment, session revocation, and notification delivery.",
  "backend/modules/memory/schemas.py": "Defines the API contracts for working, semantic, episodic, procedural, document, coordination, ingestion, and agent memory workflows.",
  "backend/modules/notifications/router.py": "Provides authenticated endpoints for listing notifications, marking them read, and managing delivery preferences.",
  "backend/modules/notifications/schemas.py": "Defines response and update models for notifications and per-user notification preferences.",
  "backend/modules/observability/__init__.py": "Publishes the observability package's shared metrics registry as its public entry point.",
  "backend/modules/observability/config.py": "Builds an immutable observability configuration from application settings for metrics, tracing, sampling, and service identity.",
  "backend/modules/observability/context.py": "Bridges request-scoped correlation identifiers into the observability context used by logs and traces.",
  "backend/modules/observability/exporters.py": "Provides the Prometheus text exporter backed by the application's in-process metrics registry.",
  "backend/modules/observability/health.py": "Checks database and Redis readiness with bounded timeouts and returns a structured dependency health report.",
  "backend/modules/observability/instrumentation.py": "Installs database, worker, logging, metrics, and tracing instrumentation while preventing duplicate registration.",
  "backend/modules/observability/logging.py": "Emits structured application events enriched with the active request and tracing context.",
  "backend/modules/observability/metrics.py": "Implements a bounded-label metrics registry and domain-specific recorders for HTTP, workers, providers, databases, caches, queues, runs, memory, SSE, and locks.",
  "backend/modules/observability/middleware.py": "Measures HTTP request latency and outcomes while recording bounded route labels and response metadata.",
  "backend/modules/observability/queue.py": "Queries queued and active orchestration runs to refresh durable queue depth and oldest-age gauges.",
  "backend/modules/observability/router.py": "Serves the application's Prometheus metrics endpoint with the correct exposition content type.",
  "backend/modules/observability/slo.py": "Defines owned service-level objectives, error budgets, alert windows, and runbook metadata for critical platform capabilities.",
  "backend/modules/observability/tracing.py": "Configures Sentry and OpenTelemetry integrations and supplies a safe span context manager for application code.",
  "backend/modules/orchestration/execution/cpu_executor.py": "Runs CPU-bound or untrusted code jobs through Docker with resource limits, controlled host fallback, timeouts, and an async adapter.",
  "backend/modules/orchestration/execution/durable_execution.py": "Defines durable execution capability checks and submits orchestration runs only when the configured backend satisfies delivery guarantees.",
  "backend/modules/orchestration/graphql_router.py": "Defines the Strawberry GraphQL schema, resolvers, mutations, subscription stream, and context bridge for the orchestration control plane.",
  "backend/modules/platform/models.py": "Defines subscription, API key, webhook, feature flag, and email template persistence models for platform administration.",
  "backend/modules/platform/repository.py": "Provides database access for plans, subscriptions, API keys, webhooks, feature flags, and email templates.",
  "backend/modules/platform/router.py": "Exposes user and administrator platform APIs for metadata, subscriptions, API keys, webhooks, feature flags, configuration, plans, and email templates.",
  "backend/modules/platform/schemas.py": "Defines platform administration request and response contracts for modules, plans, subscriptions, API keys, webhooks, flags, and email templates.",
  "backend/modules/platform/service.py": "Implements platform administration rules for defaults, modules, subscriptions, API keys, outbound webhooks, feature rollout, configuration, and email templates.",
  "backend/modules/profile/router.py": "Provides profile retrieval and update endpoints plus validated avatar upload, replacement, and deletion through object storage.",
  "backend/modules/profile/schemas.py": "Defines the public profile representation and the editable profile fields accepted by the API."
};

const domainFor = (filePath) => {
  const match = filePath.match(/backend\/modules\/([^/]+)/);
  return (match?.[1] ?? "backend").replaceAll("_", "-");
};

const humanize = (name) => name
  .replace(/^_+/, "")
  .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
  .replaceAll("_", " ")
  .replace(/\bapi\b/gi, "API")
  .replace(/\bmfa\b/gi, "MFA")
  .replace(/\bcsrf\b/gi, "CSRF")
  .replace(/\bsse\b/gi, "SSE")
  .replace(/\bdb\b/gi, "database")
  .replace(/\bslo\b/gi, "SLO")
  .replace(/\bgithub\b/gi, "GitHub")
  .trim();

const sentence = (value) => value.charAt(0).toUpperCase() + value.slice(1);

const fileTags = (filePath) => {
  const domain = domainFor(filePath);
  if (filePath.endsWith("/schemas.py")) return ["api-schema", "validation", "serialization", domain];
  if (filePath.endsWith("/models.py")) return ["data-model", "database", "sqlalchemy", domain];
  if (filePath.endsWith("/repository.py")) return ["repository", "data-access", "database", domain];
  if (filePath.endsWith("/service.py")) return ["service", "business-logic", "transaction-boundary", domain];
  if (filePath.endsWith("/router.py")) return ["api-handler", "routing", "fastapi", domain];
  if (filePath.endsWith("graphql_router.py")) return ["api-handler", "graphql", "strawberry", "control-plane"];
  if (filePath.endsWith("cpu_executor.py")) return ["execution", "sandbox", "docker", "worker"];
  if (filePath.endsWith("durable_execution.py")) return ["execution", "durability", "queue", "reliability"];
  if (filePath.includes("/observability/")) return ["observability", "monitoring", "telemetry", path.basename(filePath, ".py")];
  return ["backend", "python", domain];
};

const fileNotes = (filePath) => {
  if (filePath.endsWith("/schemas.py")) return "Pydantic models separate validated request payloads from serialized response shapes.";
  if (filePath.endsWith("/models.py")) return "SQLAlchemy declarative models map typed Python attributes to relational columns and indexes.";
  if (filePath.endsWith("/router.py")) return "FastAPI dependency injection supplies authenticated users and database sessions at endpoint boundaries.";
  if (filePath.endsWith("graphql_router.py")) return "Strawberry decorators derive the GraphQL schema directly from typed Python classes and resolver methods.";
  if (filePath.endsWith("metrics.py")) return "Metrics constrain label cardinality before producing Prometheus-compatible samples.";
  return undefined;
};

const complexityForLines = (lines) => lines > 200 ? "complex" : lines >= 50 ? "moderate" : "simple";

const functionSummary = (filePath, name) => {
  const label = humanize(name);
  const domain = domainFor(filePath).replaceAll("-", " ");
  const exact = {
    _github_connection: "Maps a stored GitHub connection and installation metadata to its API response.",
    _github_repository: "Maps a synchronized GitHub repository record to its API response.",
    _github_issue_link: "Maps a GitHub issue-to-task link and synchronization state to its API response.",
    _github_sync_event: "Maps a persisted GitHub synchronization event to its API response.",
    _approval: "Serializes an approval request while redacting sensitive approval payload fields.",
    _task: "Builds a task response enriched with its linked GitHub issue summary.",
    _tasks_to_responses: "Bulk-loads GitHub issue summaries and converts task records to API responses without per-item lookups.",
    _cookie_kwargs: "Returns the shared secure cookie attributes used for authentication cookies.",
    _delete_cookie: "Deletes an authentication cookie using the same scope and security attributes used when setting it.",
    _clear_cookie_variants: "Clears all supported variants of an authentication cookie.",
    _set_refresh_cookie: "Writes the refresh token to a protected browser cookie.",
    _set_access_cookie: "Writes the access token to a protected browser cookie.",
    _set_csrf_cookie: "Writes the browser-readable CSRF token used to protect cookie-authenticated requests.",
    _clear_auth_cookies: "Removes access, refresh, and CSRF cookies after logout or failed refresh.",
    _build_user: "Serializes a persisted account into the authenticated-user response model.",
    _hash_token: "Hashes a raw security token before it is stored or compared.",
    bind_observability_context: "Binds correlation identifiers into the current structured logging and tracing context.",
    current_context: "Returns the active request correlation context for telemetry enrichment.",
    prometheus_payload: "Renders the current metrics registry in Prometheus exposition format.",
    _check: "Runs a dependency health probe with a timeout and converts failures into a structured check result.",
    readiness_report: "Combines database and Redis health probes into the service readiness status.",
    instrument_database: "Registers database timing hooks and records bounded query telemetry for an engine.",
    register_worker_observability_signals: "Attaches telemetry callbacks to worker lifecycle and task signals.",
    setup_observability: "Initializes the configured tracing, metrics, logging, and database instrumentation stack.",
    log_event: "Emits a structured log event enriched with current observability context fields.",
    bounded_route: "Normalizes dynamic HTTP paths into bounded route labels for metrics.",
    bounded_label: "Constrains arbitrary metric label values to a stable bounded representation.",
    _sample: "Creates or updates one metric sample for a canonical label set.",
    record_http_request: "Records request count, latency, status, method, and bounded route metrics.",
    record_worker_task: "Records worker task duration and outcome metrics.",
    record_provider_call: "Records provider request latency, outcome, model, token, and cost metrics.",
    record_db_query: "Records database operation latency and outcome with bounded operation labels.",
    record_cache_operation: "Records cache hit, miss, failure, and latency metrics for a bounded cache name.",
    record_sse_event: "Records server-sent event delivery counts and connection state.",
    record_queue_state: "Updates queue depth, active work, and oldest pending age gauges.",
    record_run_outcome: "Records orchestration run completion outcomes.",
    record_memory_retrieval: "Records memory retrieval latency, result count, and outcome.",
    record_distributed_lock: "Records distributed lock acquisition and contention outcomes.",
    _age_seconds: "Calculates a non-negative age in seconds across naive and timezone-aware timestamps.",
    refresh_queue_metrics: "Aggregates queued and active runs by bounded queue name and refreshes their depth and age gauges.",
    metrics: "Returns the Prometheus metrics payload from the HTTP metrics endpoint.",
    slo_catalog: "Returns the immutable catalog of service-level objectives and runbook ownership.",
    setup_sentry: "Configures Sentry error reporting when its dependency and data source are available.",
    setup_tracing: "Configures OpenTelemetry tracing and exporters according to observability settings.",
    span: "Provides a no-op-safe context manager for creating application trace spans.",
    docker_available: "Checks whether the Docker runtime is reachable before sandboxed execution.",
    execute_code_job: "Selects the permitted execution backend and runs a code job with fail-closed production safeguards.",
    execute_code_job_docker: "Executes a code job inside a resource-limited Docker container and captures its bounded result.",
    execute_code_job_async: "Runs the blocking code executor through an asynchronous thread boundary.",
    is_run_execution_claimable: "Reports whether a run state may be claimed by a durable worker.",
    durable_backend_status: "Describes whether the configured queue backend satisfies durable execution requirements.",
    submit_orchestration_run: "Validates durable delivery support and submits an orchestration run to the worker queue.",
    graphql_context: "Builds the authenticated database-backed context supplied to GraphQL resolvers.",
    _model_profile: "Maps a provider model profile into its GraphQL representation.",
    _run: "Maps an orchestration run into its GraphQL representation.",
    _brainstorm: "Maps a brainstorming session into its GraphQL representation.",
    _member: "Maps a team member and hierarchy data into its GraphQL representation.",
    _snapshot: "Maps the hierarchy control-plane snapshot into its GraphQL representation.",
    _artifact: "Maps a task artifact into its GraphQL representation.",
    _log_admin_action: "Writes a structured audit record for a platform administrator action.",
    _plan_to_response: "Maps a subscription plan record to its public response.",
    _subscription_to_response: "Maps a user subscription record to its public response.",
    _api_key_to_response: "Maps an API key record to a response without exposing the secret.",
    _webhook_to_response: "Maps an outbound webhook record to its public response.",
    _feature_flag_to_response: "Maps a feature flag record to its API response.",
    _email_template_to_response: "Maps an email template record to its API response.",
    _to_response: `Maps a persisted ${domain} record to its API response.`,
    _build_avatar_object_key: "Builds a collision-resistant object-storage key while preserving a safe avatar file extension.",
    upload_avatar: "Validates avatar type and size, uploads it to object storage, updates the profile, and cleans up replaced objects."
  };
  if (exact[name]) return exact[name];
  if (name.startsWith("list_")) return `Lists ${label.slice(5)} visible to the current caller.`;
  if (name.startsWith("get_")) return `Retrieves ${label.slice(4)} for the current caller.`;
  if (name.startsWith("create_")) return `Validates and creates ${label.slice(7)}.`;
  if (name.startsWith("update_")) return `Validates and updates ${label.slice(7)}.`;
  if (name.startsWith("delete_")) return `Deletes ${label.slice(7)} after authorization checks.`;
  if (name.startsWith("revoke_")) return `Revokes ${label.slice(7)} and persists the change.`;
  if (name.startsWith("mark_")) return `Marks ${label.slice(5)} and persists the notification state.`;
  if (name.startsWith("request_")) return `Creates an approval-backed request to ${label.slice(8)}.`;
  if (name.startsWith("refresh_")) return `Refreshes ${label.slice(8)} from its authoritative state.`;
  if (name.startsWith("sync_")) return `Synchronizes ${label.slice(5)} with the external GitHub state.`;
  if (name.startsWith("import_")) return `Imports ${label.slice(7)} into orchestration tasks.`;
  if (name.startsWith("replay_")) return `Replays ${label.slice(7)} using the stored event payload.`;
  if (name.startsWith("setup_")) return `Initializes ${label.slice(6)} for the current process.`;
  if (name.startsWith("register_")) return `Registers ${label.slice(9)} with the runtime.`;
  if (name.startsWith("record_")) return `Records ${label.slice(7)} in the shared metrics registry.`;
  if (name.startsWith("_")) return `${sentence(label)} helper used internally by the module.`;
  return `${sentence(label)} operation for the ${domain} module.`;
};

const functionTags = (filePath, name) => {
  const tags = [];
  if (filePath.endsWith("router.py") || filePath.endsWith("graphql_router.py")) tags.push("api-handler");
  if (name.startsWith("_") || ["bounded_route", "bounded_label", "span"].includes(name)) tags.push("utility");
  if (/sign|logout|password|mfa|cookie|csrf|verification|refresh$/.test(name)) tags.push("authentication", "security");
  if (/github|webhook|issue|pr/.test(name)) tags.push("github", "integration");
  if (/metric|record_|observability|tracing|sentry|span|log_event|readiness|check/.test(name)) tags.push("observability", "telemetry");
  if (/execute|docker|durable|submit|claimable/.test(name)) tags.push("execution", "reliability");
  if (/avatar|profile/.test(name)) tags.push("profile", "storage");
  if (/notification|preferences|mark_/.test(name)) tags.push("notification", "user-preference");
  if (/graphql|snapshot|artifact|member|brainstorm|model_profile/.test(name) || filePath.endsWith("graphql_router.py")) tags.push("graphql", "control-plane");
  if (/plan|subscription|api_key|feature_flag|email_template|platform|webhook/.test(name) && filePath.includes("/platform/")) tags.push("platform", "business-logic");
  tags.push(domainFor(filePath));
  const uniqueTags = [...new Set(tags)];
  if (uniqueTags.length < 3) uniqueTags.push("business-logic");
  if (uniqueTags.length < 3) uniqueTags.push("python");
  return uniqueTags.slice(0, 5);
};

const classSummary = (filePath, name) => {
  const label = humanize(name);
  const exact = {
    IdentityRepository: "Encapsulates user and refresh-session persistence operations behind a session-bound repository.",
    IdentityService: "Coordinates authentication, session, verification, recovery, MFA, cache, platform, and email workflows.",
    ObservabilityConfig: "Immutable runtime settings for metrics, tracing, sampling, exporters, and service identity.",
    DependencyCheck: "Represents one readiness probe result with latency, status, and optional failure detail.",
    _Metric: "Stores one metric definition and its labeled samples for the in-process registry.",
    MetricsRegistry: "Maintains thread-safe counters, gauges, and histograms and renders them as Prometheus samples.",
    ObservabilityMiddleware: "ASGI middleware that measures HTTP requests and records status-aware telemetry.",
    ServiceLevelObjective: "Describes an owned SLO and calculates its allowable error budget.",
    Query: "Provides read-only GraphQL resolvers for hierarchy, models, runtime profiles, and task artifacts.",
    Mutation: "Provides GraphQL commands for team hierarchy, task lifecycle, approvals, runs, and brainstorming.",
    Subscription: "Streams hierarchy control-plane events over GraphQL subscriptions.",
    PlatformRepository: "Encapsulates persistence operations for all platform administration entities.",
    PlatformService: "Coordinates platform configuration, subscription, credential, webhook, feature flag, and template business rules."
  };
  if (exact[name]) return exact[name];
  if (filePath.endsWith("/models.py")) return `Persists ${label.toLowerCase()} state as a SQLAlchemy database entity.`;
  if (filePath.endsWith("graphql_router.py")) {
    if (name.endsWith("Input")) return `Defines the GraphQL input fields for ${label.slice(0, -6).toLowerCase()} operations.`;
    return `Defines the GraphQL representation of ${label.replace(/ type$/i, "").toLowerCase()} data.`;
  }
  if (name.endsWith("Response")) return `Serializes ${label.slice(0, -9).toLowerCase()} data returned by the API.`;
  if (/(Create|Update|Request|Patch|Input)$/.test(name)) return `Validates the ${label.toLowerCase()} payload accepted by the API.`;
  return `Defines the ${label.toLowerCase()} contract used by the ${domainFor(filePath).replaceAll("-", " ")} module.`;
};

const classTags = (filePath, name) => {
  const tags = [];
  if (filePath.endsWith("/schemas.py")) tags.push("api-schema", "validation", "serialization");
  if (filePath.endsWith("/models.py")) tags.push("data-model", "database", "sqlalchemy");
  if (filePath.endsWith("/repository.py")) tags.push("repository", "data-access", "database");
  if (filePath.endsWith("/service.py")) tags.push("service", "business-logic", "transaction-boundary");
  if (filePath.endsWith("graphql_router.py")) tags.push("graphql", name.endsWith("Input") ? "input-type" : "object-type", "control-plane");
  if (filePath.includes("/observability/")) tags.push("observability", "telemetry", "monitoring");
  tags.push(domainFor(filePath));
  if (tags.length < 3) tags.push("python", "backend");
  return [...new Set(tags)].slice(0, 5);
};

const nodes = [];
const edges = [];
const nodeIds = new Set();

const addNode = (node) => {
  if (nodeIds.has(node.id)) throw new Error(`Duplicate node ${node.id}`);
  nodeIds.add(node.id);
  nodes.push(node);
};

const addEdge = (source, target, type, weight) => {
  edges.push({source, target, type, direction: "forward", weight});
};

const resultsByPath = new Map(extraction.results.map((result) => [result.path, result]));
for (const batchFile of input.batchFiles) {
  const result = resultsByPath.get(batchFile.path);
  if (!result) throw new Error(`Missing extraction result for ${batchFile.path}`);
  const fileId = `file:${batchFile.path}`;
  const fileNode = {
    id: fileId,
    type: "file",
    name: path.basename(batchFile.path),
    filePath: batchFile.path,
    summary: fileSummaries[batchFile.path],
    tags: fileTags(batchFile.path),
    complexity: complexityForLines(result.nonEmptyLines)
  };
  const notes = fileNotes(batchFile.path);
  if (notes) fileNode.languageNotes = notes;
  if (!fileNode.summary) throw new Error(`Missing file summary for ${batchFile.path}`);
  addNode(fileNode);

  const exportNames = new Set((result.exports ?? []).map((item) => item.name));
  for (const fn of result.functions ?? []) {
    const id = `function:${batchFile.path}:${fn.name}`;
    addNode({
      id,
      type: "function",
      name: fn.name,
      filePath: batchFile.path,
      lineRange: [fn.startLine, fn.endLine],
      summary: functionSummary(batchFile.path, fn.name),
      tags: functionTags(batchFile.path, fn.name),
      complexity: complexityForLines(fn.endLine - fn.startLine + 1)
    });
    addEdge(fileId, id, "contains", 1.0);
    if (exportNames.has(fn.name)) addEdge(fileId, id, "exports", 0.8);
  }
  for (const cls of result.classes ?? []) {
    const id = `class:${batchFile.path}:${cls.name}`;
    addNode({
      id,
      type: "class",
      name: cls.name,
      filePath: batchFile.path,
      lineRange: [cls.startLine, cls.endLine],
      summary: classSummary(batchFile.path, cls.name),
      tags: classTags(batchFile.path, cls.name),
      complexity: complexityForLines(cls.endLine - cls.startLine + 1)
    });
    addEdge(fileId, id, "contains", 1.0);
    if (exportNames.has(cls.name)) addEdge(fileId, id, "exports", 0.8);
  }
}

for (const [sourcePath, targets] of Object.entries(input.batchImportData)) {
  for (const targetPath of targets) addEdge(`file:${sourcePath}`, `file:${targetPath}`, "imports", 0.7);
}

const localEntitiesByFile = new Map();
for (const result of extraction.results) {
  const entityMap = new Map();
  for (const fn of result.functions ?? []) entityMap.set(fn.name, `function:${result.path}:${fn.name}`);
  for (const cls of result.classes ?? []) entityMap.set(cls.name, `class:${result.path}:${cls.name}`);
  localEntitiesByFile.set(result.path, entityMap);
}

for (const result of extraction.results) {
  const localEntities = localEntitiesByFile.get(result.path);
  const methodOwners = new Map();
  for (const cls of result.classes ?? []) {
    for (const method of cls.methods ?? []) {
      if (!methodOwners.has(method)) methodOwners.set(method, `class:${result.path}:${cls.name}`);
      else methodOwners.set(method, null);
    }
  }
  const neighbors = batch.neighborMap[result.path] ?? [];
  const neighborSymbols = new Map();
  for (const neighbor of neighbors) {
    for (const symbol of neighbor.symbols ?? []) neighborSymbols.set(symbol, neighbor.path);
  }
  for (const call of result.callGraph ?? []) {
    const source = localEntities.get(call.caller) ?? methodOwners.get(call.caller);
    if (!source) continue;
    const localTarget = localEntities.get(call.callee);
    if (localTarget && localTarget !== source) {
      addEdge(source, localTarget, "calls", 0.8);
      continue;
    }
    const neighborPath = neighborSymbols.get(call.callee);
    if (neighborPath) {
      const prefix = /^[A-Z]/.test(call.callee) ? "class" : "function";
      addEdge(source, `${prefix}:${neighborPath}:${call.callee}`, "calls", 0.8);
    }
  }
}

const requestModels = {
  "backend/modules/companies/schemas.py": ["CompanyCreate", "CompanyUpdate"],
  "backend/modules/github/schemas.py": ["GithubConnectionCreate", "GithubIssueImportRequest", "GithubCommentRequest", "GithubPrRequest", "GithubSyncReplayRequest"],
  "backend/modules/identity_access/schemas.py": ["SignUpRequest", "SignInRequest", "VerifyEmailRequest", "ResendVerificationRequest", "ForgotPasswordRequest", "ResetPasswordRequest", "MfaVerifyRequest", "MfaDisableRequest"],
  "backend/modules/memory/schemas.py": ["WorkingMemoryPatch", "SemanticMemoryEntryCreate", "SemanticMemoryEntryUpdate", "PromoteWorkingMemoryRequest", "MemorySettingsPatch", "SemanticMergeRequest", "SemanticMemoryLinkCreate", "ProceduralPlaybookCreate", "ProceduralPlaybookUpdate", "TaskMemoryCoordinationPatch"],
  "backend/modules/notifications/schemas.py": ["NotificationPreferenceUpdate"],
  "backend/modules/platform/schemas.py": ["PlatformConfigUpdateRequest", "SubscriptionPlanCreate", "SubscriptionPlanUpdate", "SubscriptionSelectionRequest", "ApiKeyCreateRequest", "WebhookEndpointCreate", "WebhookEndpointUpdate", "FeatureFlagCreate", "FeatureFlagUpdate", "EmailTemplateCreate", "EmailTemplateUpdate"],
  "backend/modules/profile/schemas.py": ["ProfileUpdate"]
};
for (const [filePath, classNames] of Object.entries(requestModels)) {
  for (const className of classNames) {
    addEdge(`class:${filePath}:${className}`, "class:backend/core/schemas.py:RequestModel", "inherits", 0.9);
  }
}

for (const filePath of ["backend/modules/identity_access/models.py", "backend/modules/platform/models.py"]) {
  for (const cls of resultsByPath.get(filePath).classes ?? []) {
    addEdge(`class:${filePath}:${cls.name}`, "class:backend/db/base.py:Base", "inherits", 0.9);
  }
}

const sameFileInheritance = [
  ["PlatformConfigResponse", "PlatformMetadataResponse"],
  ["ApiKeyCreateResponse", "ApiKeyResponse"],
  ["WebhookEndpointCreateResponse", "WebhookEndpointResponse"],
  ["EffectiveFeatureFlagResponse", "FeatureFlagResponse"]
];
for (const [child, parent] of sameFileInheritance) {
  const filePath = "backend/modules/platform/schemas.py";
  addEdge(`class:${filePath}:${child}`, `class:${filePath}:${parent}`, "inherits", 0.9);
}

for (const [sourcePath, neighbors] of Object.entries(batch.neighborMap)) {
  for (const neighbor of neighbors) {
    if (neighbor.path.includes("/tests/") && neighbor.path.endsWith(".py")) {
      addEdge(`file:${sourcePath}`, `file:${neighbor.path}`, "tested_by", 0.5);
    }
  }
}

const edgeKeys = new Set();
const dedupedEdges = edges.filter((edge) => {
  const key = `${edge.source}\u0000${edge.target}\u0000${edge.type}`;
  if (edgeKeys.has(key)) return false;
  edgeKeys.add(key);
  return true;
});

const importExpected = Object.values(input.batchImportData).reduce((sum, values) => sum + values.length, 0);
const importActual = dedupedEdges.filter((edge) => edge.type === "imports").length;
if (importActual !== importExpected) throw new Error(`Import count mismatch: expected ${importExpected}, got ${importActual}`);

const partCount = Math.ceil(Math.max(nodes.length / 60, dedupedEdges.length / 120));
const sortedFiles = [...input.batchFiles].sort((a, b) => a.path.localeCompare(b.path));
const groupSize = Math.ceil(sortedFiles.length / partCount);
const parts = [];

for (let index = 0; index < partCount; index += 1) {
  const fileGroup = new Set(sortedFiles.slice(index * groupSize, (index + 1) * groupSize).map((item) => item.path));
  if (fileGroup.size === 0) continue;
  const partNodes = nodes.filter((node) => fileGroup.has(node.filePath));
  const sourceIds = new Set(partNodes.map((node) => node.id));
  const partEdges = dedupedEdges.filter((edge) => sourceIds.has(edge.source));
  const outputPath = path.join(outputDir, `batch-2-part-${index + 1}.json`);
  fs.writeFileSync(outputPath, `${JSON.stringify({nodes: partNodes, edges: partEdges}, null, 2)}\n`);
  parts.push({outputPath, nodes: partNodes.length, edges: partEdges.length, files: [...fileGroup]});
}

const allOutputNodes = parts.reduce((sum, part) => sum + part.nodes, 0);
const allOutputEdges = parts.reduce((sum, part) => sum + part.edges, 0);
if (allOutputNodes !== nodes.length || allOutputEdges !== dedupedEdges.length) {
  throw new Error(`Partition mismatch nodes ${allOutputNodes}/${nodes.length}, edges ${allOutputEdges}/${dedupedEdges.length}`);
}

const neighborFilePaths = new Set(Object.values(batch.neighborMap).flat().map((item) => item.path));
const importedFilePaths = new Set(Object.values(input.batchImportData).flat());
const neighborEntityIds = new Set();
for (const neighbors of Object.values(batch.neighborMap)) {
  for (const neighbor of neighbors) {
    for (const symbol of neighbor.symbols ?? []) {
      neighborEntityIds.add(`${/^[A-Z]/.test(symbol) ? "class" : "function"}:${neighbor.path}:${symbol}`);
    }
  }
}
for (const part of parts) {
  const parsed = JSON.parse(fs.readFileSync(part.outputPath, "utf8"));
  if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) throw new Error(`${part.outputPath} lacks graph arrays`);
  const partNodeIds = new Set(parsed.nodes.map((node) => node.id));
  for (const node of parsed.nodes) {
    if (!node.summary || !Array.isArray(node.tags) || node.tags.length < 3 || node.tags.length > 5) {
      throw new Error(`${part.outputPath} has invalid metadata for ${node.id}`);
    }
  }
  for (const edge of parsed.edges) {
    if (!partNodeIds.has(edge.source)) throw new Error(`${part.outputPath} has unowned edge source ${edge.source}`);
    if (partNodeIds.has(edge.target)) continue;
    if (edge.target.startsWith("file:")) {
      const targetPath = edge.target.slice(5);
      if (neighborFilePaths.has(targetPath) || importedFilePaths.has(targetPath)) continue;
    }
    if (neighborEntityIds.has(edge.target)) continue;
    throw new Error(`${part.outputPath} has invalid edge target ${edge.target}`);
  }
}

console.log(JSON.stringify({
  parts: parts.length,
  nodes: nodes.length,
  edges: dedupedEdges.length,
  imports: importActual,
  partDetails: parts.map((part) => ({file: path.basename(part.outputPath), nodes: part.nodes, edges: part.edges, files: part.files.length}))
}, null, 2));
