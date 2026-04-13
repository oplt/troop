# ADR 0003: Product Vision (product_idea.txt) vs Orchestration Runtime

## Status
Accepted (living document — implementation catches up incrementally)

## Context
`product_idea.txt` describes an AI project operations platform: LangGraph-style agent graphs, Temporal-style durable workflows, split services (GitHub, model gateway, observability), deep GitHub semantics, rich hierarchy UX, and strict agent permission tiers.

Troop today ships a **modular monolith** with **FastAPI + SQLAlchemy + Celery + Redis**, a first orchestration module (agents, tasks, runs, brainstorms, GitHub App webhooks, providers, knowledge, approvals), and an SPA.

## Decision
1. **Keep Celery + async Python as the primary execution plane** for the medium term. Temporal remains an optional future extraction if workflow durability requirements exceed what replay + idempotent workers provide.
2. **LangGraph is optional** behind `ORCHESTRATION_USE_LANGGRAPH` (see ADR 0004). When enabled, run modes are dispatched through an in-process `StateGraph`; Celery remains the durable queue. A hard LangGraph-only rewrite is still deferred.
3. **GitHub integration stays in-process** beside orchestration; extract only if webhook volume or compliance isolation demands it.
4. **Product gaps** (permissions, offline mode, portfolio analytics, decision recall in search, etc.) are closed with **incremental features** behind settings and `metadata_json` conventions rather than big-bang rewrites.
5. **External references** from the product memo map to canonical docs:
   - [LangChain multi-agent guidance](https://python.langchain.com/docs/concepts/multi_agent/)
   - [GitHub webhooks — issues & comments](https://docs.github.com/en/webhooks/webhook-events-and-payloads)
   - [Ollama OpenAI compatibility](https://github.com/ollama/ollama/blob/main/docs/openai.md)
   - [LangGraph overview](https://langchain-ai.github.io/langgraph/)
   - [Temporal workflows](https://docs.temporal.io/workflows)

## Consequences
- Faster shipping; fewer moving parts in dev/staging.
- Some product bullets remain **policy/UI** features (portfolio, hierarchy builder) rather than new processes.
- Revisit this ADR when run volume, compliance, or team size forces service boundaries.
