# Memory architecture — Phase 0 (specification & inventory)

This document fulfills **Phase 0** from `memory_tasks.txt`: the layered memory model, promotion rules, and an audit of **this repository’s** persistence mapped to those layers. It intentionally **does not define new SQL tables**; schema changes remain the owner of `alembic upgrade head`.

Primary design input: `memory.txt` (root).

---

## 1. Purpose

Troop orchestration needs **multiple memory concerns** separated so that:

- **Execution truth** (what run is doing, approvals, blockers) stays **relational and queryable**, never “best effort” from a vector index.
- **Agent context** stays **bounded** (context packet), with **scoped retrieval** before global search.
- **Durable facts** (policies, ADRs, conventions) are **typed and promotable**, not dumped raw into long-term store.
- **Raw history** remains available for **audit and “why did we decide this?”** without polluting the hot path.

---

## 2. Five memory layers (definitions)

| Layer | Question it answers | Typical content | Authority |
|-------|---------------------|-----------------|-----------|
| **1. Execution state** | What is happening *now* in the workflow? | Run status, retries, approvals pending, blockers, tool call lifecycle, handoffs, GitHub sync pending, in-run checkpoints | **Postgres + workflow runner** (Celery/Temporal per ADR 0004). Not recoverable from embeddings alone. |
| **2. Working memory** | What is this run/thread *currently* using? | Current objective, accepted plan snippet, latest findings, scratch notes, unresolved questions, artifact refs, short transcript summary | **Run-scoped / thread-scoped**, bounded TTL or truncation. LangGraph checkpoints align with this concept. |
| **3. Semantic memory** | What is *true* for the org/project/agent? | Policies, standards, ADRs, glossary, routing prefs, promoted decisions | **Typed records** + metadata; retrieval augments, does not define truth. |
| **4. Episodic memory** | What *happened*? | Brainstorm transcripts, failed runs, incident timelines, review threads, verbatim logs | **Append-heavy**; MemPalace-style raw retention is appropriate *here* for investigation. |
| **5. Procedural memory** | *How* do we operate here? | Agent system prompts, templates, checklists, escalation playbooks, “how we triage” docs | Often **versioned text**; overlaps with agent catalog but should be **selectable** into context packets by task type. |

**Hard boundary:** Layer 1 must never depend on vector similarity for correctness (e.g. “find the active run” = SQL, not ANN).

---

## 3. Promotion rules (summary)

Writes should default **low** in the stack; promotion moves facts **up** only when justified.

| Target | Promote when… |
|--------|----------------|
| **Task / working** | Work notes, hypotheses, partial outputs, failed attempts, drafts — always allowed at task/run scope. |
| **Project (semantic or episodic)** | Affects architecture, changes a decision, reusable fix, dependency/interface rule, recurring failure pattern. |
| **Company (semantic)** | Cross-project policy, standard, convention, or change to how agents should generally behave. |

Pipeline stages (target architecture, not all implemented today): **capture → classify → validate (dedupe/conflict) → approve (for sensitive) → store in typed semantic or archival episodic**.

---

## 4. Logical namespaces (no DDL)

Namespaces are **API and documentation contracts** until dedicated tables exist. Suggested prefixes:

- `company/{tenant_or_org_id}/semantic/*`, `.../procedural/*`, `.../episodic/*`
- `project/{project_id}/semantic/*`, `.../procedural/*`, `.../episodic/*`
- `task/{task_id}/working/*`, `.../episodic/*`, `.../artifacts/*`
- `agent/{agent_id}/procedural/*`, `.../preferences/*`

**Inheritance:** project defaults override nothing at company level for *policies*; task scope is *isolated*; promoted rows carry **provenance** (source task, run, agent, time, confidence) when the schema supports it.

---

## 5. Context packet (target vs current)

**Target:** Each run receives a **constructed packet**: company brief → project brief → task brief → agent instruction subset → working scratchpad → top scoped retrievals → recent discussion summary → open blockers and acceptance criteria — under a **strict token budget**.

**Current (approximate):** `OrchestrationService._build_task_prompt` assembles a single prompt string from project goals, RAG-style knowledge hits (`_build_project_knowledge_context`), recent task comments and artifacts, agent memory text (`_build_agent_memory_context`), scratchpad summary and “previous run” diff from `checkpoint_json`, replay payload, and full `input_payload_json` (truncated). This is a **monolithic prompt**, not yet a formal packet schema or ordered scoped-retrieval stages.

---

## 6. Current implementation inventory

Below: **existing** tables/JSON fields (as implemented in code), mapped to **target** memory layers. Paths refer to `backend/modules/orchestration/` unless noted.

### 6.1 Execution state (Layer 1)

| Artifact | Location | Role today |
|----------|----------|------------|
| Run lifecycle | `models.py` → `TaskRun` (`status`, `run_mode`, `attempt_number`, `retry_count`, `started_at`, `completed_at`, `cancelled_at`, `error_message`, agent IDs, `provider_config_id`) | Primary execution record |
| Run I/O | `TaskRun.input_payload_json`, `output_payload_json` | Inputs/outputs for the run |
| Durable checkpoint blob | `TaskRun.checkpoint_json` | Includes `scratchpad_summary` (see working memory) |
| Event stream | `RunEvent` (`event_type`, `message`, `payload_json`, tokens/cost) | Append-only execution log |
| Task state | `OrchestratorTask.status`, `metadata_json` (e.g. SLA flags, reopen history, `execution_memory` after completed runs) | Task-level execution + lightweight memory bridge |
| Human gates | `ApprovalRequest` (orchestration module) | Approval-aware execution |
| GitHub sync queue / audit | `GithubSyncEvent` | External sync state and webhook audit |

**Gap vs ideal:** No Temporal workflow history yet (see `docs/adr/0004-langgraph-and-temporal-execution-plane.md`); Celery + DB remain execution truth.

### 6.2 Working memory (Layer 2)

| Artifact | Location | Role today |
|----------|----------|------------|
| Run scratchpad summary | `TaskRun.checkpoint_json["scratchpad_summary"]` updated in `_refresh_run_scratchpad` from last N `RunEvent`s | Run-scoped short summary |
| “What changed since last run” | `_build_run_scratchpad_context` — textual diff block vs previous `TaskRun` | Working / handoff hint |
| Replay carry-forward | `run.input_payload_json["orchestration_replay"]` | Thread-like continuation |

**Gap:** Not a full structured working object (objective, plan, open questions); no per-agent private scratchpad namespace; truncation policy is ad hoc (event count / char limits).

### 6.3 Semantic memory (Layer 3)

| Artifact | Location | Role today |
|----------|----------|------------|
| Project goals / summary | `OrchestratorProject.goals_markdown`, `knowledge_summary` | Always-ish project brief |
| RAG chunks | `ProjectDocument`, `ProjectDocumentChunk` (+ embeddings on chunk when present) | Semantic retrieval over uploaded docs |
| Decisions | `ProjectDecision` | Explicit decision records (ADR-like) |
| Brainstorm summaries | `Brainstorm.summary`, `final_recommendation`, `decision_log_json` | Structured discussion outcomes |
| Agent memory KV | `AgentMemoryEntry` (`key`, `value_text`, `scope`, `status`, TTL, `source_run_id`) | Durable snippets; `long-term` scope uses approvals |

**Gap:** No separate **typed** semantic entity table (policy vs glossary vs convention); chunks and agent memory are the main “fact” stores; **company-level** semantic scope is not first-class in orchestration models reviewed here.

### 6.4 Episodic memory (Layer 4)

| Artifact | Location | Role today |
|----------|----------|------------|
| Brainstorm turns | `BrainstormMessage` | Verbatim-ish multi-agent dialogue |
| Task comments | `TaskComment` | Human/agent thread on task |
| Run events | `RunEvent` | Fine-grained episodic log |
| Artifacts | `TaskArtifact` | Named blobs tied to task/run |
| Documents | `ProjectDocument.source_text` / `object_key` | Raw source or object storage pointer |
| GitHub mirrored comments | Task comments prefixed with GitHub markers (service layer) | Cross-system episodic thread |

**Gap:** No unified **episodic archive** API or compaction job; no mandatory provenance block on all episodic rows; blob store usage depends on document upload path.

### 6.5 Procedural memory (Layer 5)

| Artifact | Location | Role today |
|----------|----------|------------|
| Agent instructions | `AgentProfile` (`system_prompt`, markdown fields, `rules_markdown`, `output_contract_markdown`, `mission_markdown`) | Primary procedural surface |
| Templates / catalog | `AgentTemplateCatalog`, templates in `templates.py` | Reusable agent definitions |
| Skill packs | `SkillPack` | Packaged procedural bundles |
| Project execution / gates | `OrchestratorProject.settings_json` (execution, github, hitl, etc.) + gate config endpoints | Policy-like configuration |
| Escalation / routing rules | JSON under `settings_json.execution` | Operational playbooks in config form |

**Gap:** Procedural snippets are not **selected by task type** into a minimal packet; whole agent text often flows into prompts via inheritance resolution elsewhere.

---

## 7. Gap analysis (prioritized for later phases)

These are **engineering backlog items**, not Phase 0 schema work.

1. **Formal context packet** — Replace/augment monolithic `_build_task_prompt` with a versioned packet structure + telemetry (sizes per section).
2. **Scoped retrieval order** — Enforce task → project → company → deep search in `_search_project_knowledge` and related callers.
3. **Typed semantic store** — New models **via Alembic** when you are ready: entity types, provenance, conflict flags.
4. **Promotion service** — Classifier + validator + approval hooks; avoid auto-promoting every run output to semantic.
5. **Per-agent private scratchpad** — Namespace or JSON keyed by agent under run; enforce “no cross-agent leak” in prompts.
6. **Compaction / TTL** — Systematic archival for `RunEvent` / task metadata noise; keep pointers for audit.
7. **Execution vs working split** — Move scratchpad fields to clearer JSON schema; keep `checkpoint_json` replay-safe if LangGraph grows.
8. **Company scope** — First-class tenant/org semantic store if multi-tenant product memory is required beyond per-project.

---

## 8. Related documents

- `memory.txt` — Full rationale (MemPalace, LangGraph, Temporal references).
- `memory_tasks.txt` — Phased implementation checklist.
- `docs/memory-architecture-phase1-execution-state.md` — Layer 1 contract, Celery/Postgres truth, snapshot APIs.
- `docs/memory-architecture-phases-2-12.md` — Phases 2–12 implementation map (working → semantic → episodic, packet, gaps).
- `docs/adr/0004-langgraph-and-temporal-execution-plane.md` — Execution plane direction.
- `docs/adr/0003-product-vision-alignment-orchestration.md` — Product alignment.

---

## 9. Maintenance

When you add tables or rename JSON keys via Alembic, update **§6** and **§7** in this file so Phase 0 inventory stays truthful. No migration was added as part of Phase 0.
