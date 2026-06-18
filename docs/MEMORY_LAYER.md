# AI Memory Layer

Troop ships a production-oriented AI memory layer inspired by [mem0](https://github.com/mem0ai/mem0) patterns. It **extends the existing semantic memory subsystem** (PostgreSQL + pgvector) rather than adding mem0 as a dependency or running a separate vector store.

## Architecture

```
User / agent interaction
        │
        ▼
MemoryService  ──►  MemoryProvider  ──►  SqlMemoryRepository  ──►  semantic_memory_entries (pgvector)
        │                    │
        ├─ redaction           └─ entry mapping + dedup metadata
        ├─ dedup (MD5 hash)
        ├─ rule/LLM extraction
        └─ build_memory_context()
                │
                ▼
ContextPacket.relevant_memory_context  ──►  LLM / agent prompt
```

### Key components

| Module | Role |
|--------|------|
| `MemoryService` | Public facade: add, search, update, delete, build context, extract-from-interaction |
| `MemoryProvider` | Storage backend protocol |
| `SemanticMemoryProvider` | Default provider over `SemanticMemoryEntry` |
| `MemoryRepository` / `SqlMemoryRepository` | Persistence adapter |
| `MemoryConfig` | Global + per-project settings |
| `redaction.py` | Blocks/redacts secrets before persistence |
| `extractor.py` | Rule-based (+ optional LLM) durable-fact extraction |
| `context.py` | Formats retrieved memories for prompts |

Location: `backend/modules/memory/layer/`

## Integration points

### Before LLM generation

During run prompt assembly (`OrchestrationMemoryServiceMixin._assemble_user_context_packet`), the layer searches for relevant memories and injects a **`relevant_memory_context`** section into the `ContextPacket` when enabled.

### After run completion

When a run completes (`execution_service.execute_run`), `_extract_memory_layer_from_run` scans recent run events and the final output, extracts durable facts (preferences, decisions, constraints), and stores them via `MemoryService`.

### Agent HTTP API

`/api/v1/memory/*` routes delegate to `SqlMemoryStore`, which wraps `MemoryService`:

- `POST /` — add memory
- `GET /` — list by scope
- `POST /search` — search
- `PATCH /{memory_id}` — update
- `DELETE /{memory_id}` — delete

## Configuration

### Environment variables (`backend/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_LAYER_ENABLED` | `true` | Master switch; when `false`, all layer operations no-op |
| `MEMORY_PROVIDER` | `semantic_pgvector` | Provider id (only pgvector semantic backend today) |
| `MEMORY_DEFAULT_SEARCH_LIMIT` | `5` | Default top-k for search/context |
| `MEMORY_EXTRACTION_ENABLED` | `true` | Post-run fact extraction |
| `MEMORY_LLM_EXTRACTION_ENABLED` | `false` | Optional LLM extraction (requires configured AI provider) |
| `MEMORY_DEDUP_ENABLED` | `true` | MD5 content-hash deduplication |
| `MEMORY_MIN_EXTRACTION_CONFIDENCE` | `0.45` | Minimum classifier confidence |
| `MEMORY_LOG_CONTENT_IN_DEV` | `false` | Log short content previews (never in production) |

### Per-project overrides

Under `orchestrator_projects.settings_json.memory.layer`:

```json
{
  "memory": {
    "layer": {
      "enabled": true,
      "default_search_limit": 5,
      "extraction_enabled": true,
      "llm_extraction_enabled": false,
      "dedup_enabled": true,
      "inject_context_before_llm": true
    }
  }
}
```

## Privacy and deletion

- Secrets (API keys, bearer tokens, JWTs, passwords, private keys, connection strings) are **redacted or blocked** before storage.
- Production logs record event types, IDs, counts, and latency — **not raw memory content** (unless `MEMORY_LOG_CONTENT_IN_DEV=true` in non-production).
- Delete a single memory: `DELETE /api/v1/memory/{memory_id}` or `MemoryService.delete_memory`.
- Delete all memories for a user: `MemoryService.delete_memories_for_user(user_id)` (admin/service use).

## Disabling memory

Set `MEMORY_LAYER_ENABLED=false` in the environment. The app continues to work; retrieval returns empty context and writes are skipped. Existing semantic memory tables and orchestration memory features are unaffected.

## Metadata fields

Stored on `semantic_memory_entries.metadata_json` / provenance:

- `user_id` (owner scope via `owner_id`)
- `project_id`, `agent_id`, `session_id` (run id)
- `source` — e.g. `memory_service`, `rule_extractor`, `llm_extractor`
- `memory_type` / `entry_type` — decision, preference, policy, note, …
- `confidence`
- `content_hash` — dedup key
- `created_at` / `updated_at` — row timestamps

## Tests

```bash
cd backend
uv run pytest tests/test_memory_layer.py -q
```

## Design decisions

1. **No mem0 package** — Troop already has pgvector, embeddings, semantic entries, staged retrieval, and Celery embedding jobs. The layer adapts mem0's retrieve → generate → store loop and ADD-only extraction model without a second vector database.
2. **Extend, don't duplicate** — Long-term storage reuses `SemanticMemoryEntry`; episodic/working memory paths are unchanged.
3. **Rule-first extraction** — LLM extraction is opt-in via `MEMORY_LLM_EXTRACTION_ENABLED` to avoid extra model cost in dev/test.
