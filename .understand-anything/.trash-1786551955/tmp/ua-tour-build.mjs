import fs from "node:fs";

const [resultsPath, outputPath] = process.argv.slice(2);
if (!resultsPath || !outputPath) {
  console.error("Usage: node ua-tour-build.mjs <results.json> <tour.json>");
  process.exit(1);
}

const tour = [
  {
    order: 1,
    title: "Why Troop Exists",
    description: "Start with Troop's project guide to understand why agents are modeled as persistent, versioned system participants rather than isolated chats. It introduces the product's workflows, architecture, security boundaries, and technology stack, giving the rest of the tour a shared vocabulary.",
    nodeIds: ["document:README.md"],
  },
  {
    order: 2,
    title: "Backend Bootstrap",
    description: "With the product map established, follow the top-scored code entry point as it creates the FastAPI application, attaches the versioned router, and manages shared lifecycle resources. The centralized settings module is highly depended upon because it validates the runtime, security, orchestration, storage, AI, RAG, and observability configuration used by every subsystem.",
    nodeIds: ["file:backend/api/main.py", "file:backend/api/router.py", "file:backend/core/config.py"],
    languageLesson: "FastAPI composes an application from APIRouter modules and resolves declared dependencies per request; asynchronous lifespan handlers are the natural place to initialize and close shared clients.",
  },
  {
    order: 3,
    title: "Agent Operating Surface",
    description: "The bootstrap routes into an agent-facing API that manages profiles, tasks, runs, artifacts, tools, and memory. Its application service turns tasks into planned runs with snapshots and approval gates, while the registry assigns schemas and risk levels to tools and the workspace isolates execution artifacts.",
    nodeIds: ["file:backend/app/agents/router.py", "file:backend/app/agents/application.py", "file:backend/app/agents/tools/registry.py", "file:backend/app/agents/workspace.py"],
  },
  {
    order: 4,
    title: "Orchestration Control Plane",
    description: "Building on those agent primitives, the main orchestration transport exposes projects, tasks, runs, providers, memory, evaluation, and live events. The control plane and execution boundary coordinate manager-worker hierarchies, durable checkpoints, budgets, retries, tools, artifacts, and task transitions, while human-in-the-loop policy decides which actions require explicit consent.",
    nodeIds: ["file:backend/modules/orchestration/router.py", "file:backend/modules/orchestration/control_plane.py", "file:backend/modules/orchestration/services/execution_domain.py", "file:backend/modules/orchestration/execution/execution_service.py", "file:backend/modules/orchestration/hitl_policy.py"],
    languageLesson: "Python service composition keeps transport concerns in FastAPI routers while domain objects coordinate behavior; async functions allow long-running agent and provider operations without blocking the request loop.",
  },
  {
    order: 5,
    title: "Governance and GitHub",
    description: "The human-in-the-loop policy becomes concrete in approval handlers and services that authorize decisions, emit audit events, and resume gated runs. The GitHub domain applies the same governance to repository links, webhooks, issue synchronization, pull requests, and publishing run results, so external writes remain controlled rather than incidental side effects.",
    nodeIds: ["file:backend/modules/orchestration/routers/approvals.py", "file:backend/modules/orchestration/services/approvals_service.py", "file:backend/modules/orchestration/services/github_sync_domain.py", "file:backend/modules/github/service.py"],
  },
  {
    order: 6,
    title: "Persistent Execution State",
    description: "The orchestration lifecycle is durable because shared SQLAlchemy infrastructure provides asynchronous sessions over a common declarative model base. Orchestration models persist providers, runs, events, approvals, and evaluations, while Alembic loads the full metadata graph and evolves the relational schema through reversible migrations.",
    nodeIds: ["file:backend/db/base.py", "file:backend/db/session.py", "file:backend/modules/orchestration/models.py", "file:backend/alembic/env.py", "file:backend/alembic/versions/f4bdbfb299ae_generate_tables.py"],
    languageLesson: "SQLAlchemy's declarative base maps Python classes to relational tables, while Alembic migrations apply ordered, reversible schema changes so deployed databases evolve with the code.",
  },
  {
    order: 7,
    title: "Memory and Retrieval",
    description: "On top of persistence, Troop stores working, semantic, procedural, and episodic memory alongside documents, vector chunks, playbooks, and knowledge links. The memory service manages lifecycle and prompt context, while the RAG pipeline performs hybrid pgvector retrieval and citation-aware grounding; the two architecture guides explain privacy, retention, ingestion, and retrieval trade-offs.",
    nodeIds: ["file:backend/modules/memory/models.py", "file:backend/modules/memory/service.py", "file:backend/modules/rag/retrieval.py", "document:docs/MEMORY_LAYER.md", "document:docs/RAG_LAYER.md"],
    languageLesson: "Vector retrieval augments relational filtering with similarity search: embeddings narrow semantically relevant chunks, then reranking and citations keep generated answers grounded in traceable source material.",
  },
  {
    order: 8,
    title: "Queue-Driven Execution",
    description: "Long-running work leaves the request path through Celery queues configured with delivery guarantees, time limits, serialization rules, and telemetry. Worker tasks drive orchestration, GitHub synchronization, provider checks, memory maintenance, embeddings, and code execution, while durable-execution checks fail closed before work is submitted to an incapable backend.",
    nodeIds: ["file:backend/workers/celery_app.py", "file:backend/workers/orchestration.py", "file:backend/workers/tasks.py", "file:backend/modules/orchestration/execution/durable_execution.py"],
  },
  {
    order: 9,
    title: "Frontend Bootstrap",
    description: "The browser side starts by mounting React's global providers and lazy route tree, including authentication, query caching, theming, notifications, suspense, and error boundaries. A shared authenticated client handles CSRF, token refresh, session expiry, and normalized errors, and the orchestration API module turns the backend surface into a comprehensive typed contract.",
    nodeIds: ["file:frontend/src/main.tsx", "file:frontend/src/app/providers.tsx", "file:frontend/src/app/router.tsx", "file:frontend/src/api/client.ts", "file:frontend/src/api/orchestration.ts"],
    languageLesson: "React composes cross-cutting state through providers, while TypeScript types make the API boundary explicit; lazy routes and Suspense keep initial rendering separate from feature loading.",
  },
  {
    order: 10,
    title: "Operational Workspace",
    description: "Those frontend foundations converge in the project command center, which brings together hierarchy, tasks, kanban, runs, memory, approvals, repositories, decisions, and live state. The hierarchy builder edits and validates agent teams, while section-aware query hooks and live snapshots load only the data needed for the current operational view.",
    nodeIds: ["file:frontend/src/pages/projectDetail/OrchestrationProjectDetailView.tsx", "file:frontend/src/pages/HierarchyPage.tsx", "file:frontend/src/features/orchestration/project/queries.ts", "file:frontend/src/features/hierarchy/live/useHierarchyLiveState.ts"],
    languageLesson: "Custom React hooks encapsulate TanStack Query and live-stream state so large page components consume stable domain-oriented interfaces instead of duplicating synchronization logic.",
  },
  {
    order: 11,
    title: "Contracts and Journeys",
    description: "After seeing the full request-to-workspace path, inspect the tests that protect it at several scales. Integration smoke tests cover health, authentication, projects, RAG, Celery, and run lifecycles; focused suites enforce durable execution and memory safety, while Vitest and Playwright validate frontend cache behavior and browser journeys.",
    nodeIds: ["file:backend/tests/test_integration_baseline.py", "file:backend/tests/test_durable_execution_contract.py", "file:backend/tests/test_memory_layer.py", "file:frontend/src/features/orchestration/project/mutations.test.ts", "file:frontend/playwright.config.ts"],
  },
  {
    order: 12,
    title: "Delivery and Operations",
    description: "The local platform assembles PostgreSQL with pgvector, Redis, object storage, and an optional observability overlay, while repository automation provides consistent operating commands. GitHub Actions then runs backend policy checks, tests, RAG evaluation, and the frontend build chain; the deployment runbook connects those gates to Celery topology, monitoring, and rollback.",
    nodeIds: ["service:Makefile", "service:infra/docker-compose.yml", "service:infra/observability/docker-compose.observability.yml", "pipeline:.github/workflows/quality.yml", "document:docs/DEPLOYMENT_RUNBOOK.md"],
    languageLesson: "Compose YAML declares services, health checks, networks, and volumes, while GitHub Actions separates event triggers, parallel jobs, and sequential release checks.",
  },
];

try {
  const results = JSON.parse(fs.readFileSync(resultsPath, "utf8"));
  if (!results.scriptCompleted) throw new Error("Topology analysis did not complete");
  if (tour.length < 5 || tour.length > 15) throw new Error(`Invalid step count ${tour.length}`);
  const nodeIds = new Set(Object.keys(results.nodeSummaryIndex));
  const badOrders = tour.filter((step, index) => step.order !== index + 1).map((step) => step.order);
  const emptySteps = tour.filter((step) => !Array.isArray(step.nodeIds) || step.nodeIds.length < 1 || step.nodeIds.length > 5).map((step) => step.order);
  const missingIds = tour.flatMap((step) => step.nodeIds).filter((id) => !nodeIds.has(id));
  if (badOrders.length || emptySteps.length || missingIds.length) {
    throw new Error(JSON.stringify({ badOrders, emptySteps, missingIds }));
  }
  if (tour[0].nodeIds[0] !== "document:README.md") throw new Error("Tour must start with README.md");
  fs.writeFileSync(outputPath, `${JSON.stringify(tour, null, 2)}\n`);
  console.log(JSON.stringify({ steps: tour.length, referencedNodes: tour.reduce((sum, step) => sum + step.nodeIds.length, 0), titles: tour.map((step) => step.title) }));
} catch (error) {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exit(1);
}
