# Memory architecture — Phases 2–12 (implementation map)

This document ties **Phases 2–12** from `memory_tasks.txt` to **concrete code and APIs** in this repository. Phase 0–1 are in `docs/memory-architecture-phase0.md` and `docs/memory-architecture-phase1-execution-state.md`.

---

## Phase 2 — Working memory (Layer 2)

- **Storage:** `TaskRun.checkpoint_json["working_memory_v1"]` with bounded fields (`working_memory.py`).
- **Thread id for checkpoints:** `checkpoint_json["execution_thread_id"] = run.id` at execution start (`execute_run`).
- **API:** `GET/PATCH /orchestration/runs/{run_id}/working-memory` (auth = run owner via `get_run`).
- **Prompts:** Included in the context packet as section `working_memory` (`_assemble_user_context_packet`).
- **UI:** Run Inspector — editable when run status is `queued` | `in_progress` | `blocked`.

---

## Phase 3 — Semantic memory (Layer 3)

- **Storage:** Table `semantic_memory_entries` (Alembic `g7h8i9j0k1l2`), model `SemanticMemoryEntry`.
- **Types:** `policy`, `standard`, `adr`, `glossary`, `convention`, `preference`, `routing`, `note`.
- **Namespaces:** Default `project/{project_id}/semantic/{entry_type}/{slug-from-title}`; overridable on create.
- **API:** CRUD under `/orchestration/projects/{project_id}/semantic-memory` plus `POST .../promote-from-working-memory`.
- **Prompts:** Top keyword matches on task title injected as `semantic_memory` section (same packet builder).
- **UI:** `/agent-projects/:projectId/memory` (semantic list + create; episodic search on same page).

---

## Phase 4 — Episodic memory (Layer 4)

- **Search API:** `GET /orchestration/projects/{project_id}/episodic-memory/search?q=&limit=` — unions **run events**, **task comments**, **brainstorm messages** (keyword / recent tail).
- **Archive blobs / TTL / compaction:** Not fully automated; episodic raw data remains in existing tables (`RunEvent`, etc.). Extension point for object storage + jobs.

---

## Phase 5 — Procedural memory (Layer 5)

- **Code:** `procedural_context.py` — bounded excerpts from agent `mission_markdown`, `rules_markdown`, `output_contract_markdown` with light task-type/label heuristics.
- **Prompts:** Section `procedural_snippets` in the context packet (does **not** replace the full system prompt).

---

## Phase 6 — Context packet (Layer 6)

- **Code:** `context_packet.py` — `ContextPacket` with ordered sections and `combined_user_prompt(max_chars=12000)`.
- **Integration:** `_assemble_user_context_packet` + `_build_task_prompt`; **telemetry:** `logger.info("context_packet_built …")` with run id, total chars, section keys.

---

## Phase 7 — Promotion pipeline

- **Implemented path:** Working memory → typed semantic row via `promote-from-working-memory` (manual promotion with provenance).
- **Not implemented:** Global ingest queue, LLM classifier, auto-promote jobs (future workers).

---

## Phase 8 — Blackboard / private scratchpads

- **Status:** Contract documented here — **enforce** private-vs-shared in prompts requires per-agent namespaces in checkpoint or metadata and prompt-builder rules. Reserved for a focused follow-up (no separate ACL table yet).

---

## Phase 9 — Provenance

- **Semantic rows:** `provenance_json` + optional `source_task_id`, `source_run_id`, `source_chunk_id` on `SemanticMemoryEntry`.
- **Conflict resolver / compaction service:** Not built; provenance is stored for future tooling.

---

## Phases 10–11 — Modules & storage

- **Logical modules** map to: `working_memory.py`, `context_packet.py`, `procedural_context.py`, `execution_state.py`, orchestration `service`/`repository`/`router`, Celery `durable_execution`, optional `langgraph_runner`.
- **Postgres:** Authoritative for execution, working JSON, semantic entries, episodic sources.
- **pgvector:** Unchanged — RAG remains non-authoritative for execution (Phase 1).

---

## Phase 12 — Product & safety

- **Settings hook:** Use `OrchestratorProject.settings_json` for future keys, e.g. `memory.retrieval_depth`, `memory.auto_promote` (convention only until UI writes them).
- **Tenant isolation:** Semantic and episodic APIs scope by `get_project` / owner checks on `semantic_memory_entries.owner_id`.
- **Observability:** Context packet log lines; extend with metrics later.

---

## MemPalace / offline (backlog)

- **Deep recall:** Episodic search API is the lightweight stand-in; formal “hall/room” tagging can map to `namespace` + `metadata_json` on semantic rows.
- **Offline:** `ORCHESTRATION_OFFLINE_MODE` already affects providers; execution state remains SQL-backed.
