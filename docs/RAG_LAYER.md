# RAG Layer

Troop includes a production-oriented Retrieval-Augmented Generation (RAG) layer inspired by LangChain architecture patterns. It **extends the existing project document stack** (`ProjectDocument`, `ProjectDocumentChunk`, pgvector, Celery ingest jobs) rather than introducing a separate vector database or copying LangChain internals.

## Architecture

```
Upload / API ingest / repo index
        │
        ▼
DocumentIngestionService
  ├─ DocumentParser (normalize text/md/html/json/csv/code)
  ├─ ChunkingService (size + overlap + content hashes)
  ├─ EmbeddingService (batched, retry)
  └─ PgVectorStoreRepository (upsert chunks)
        │
        ▼
RetrieverService
  ├─ semantic vector search (pgvector)
  ├─ cosine fallback
  ├─ optional decision merge
  └─ optional RerankerService
        │
        ├─ RagPromptBuilder.build_context_block()  → agent ContextPacket.knowledge
        └─ RagAnswerService.answer()               → POST /rag/projects/{id}/answer
```

### Components

| Module | Role |
|--------|------|
| `RagService` | Facade: ingest, retrieve, build context, answer, delete, reindex |
| `DocumentIngestionService` | Parse → chunk → embed → upsert |
| `RetrieverService` | Vector search + filtering + context building |
| `RagAnswerService` | Grounded LLM answers with citations |
| `EmbeddingService` | Provider-agnostic embeddings with retry |
| `PgVectorStoreRepository` | pgvector-backed chunk storage |
| `SourceCitationService` | Citation formatting |

Location: `backend/modules/rag/`

## Relationship to memory

| Layer | Purpose |
|-------|---------|
| **Memory layer** | Durable user/project facts, preferences, decisions extracted from interactions |
| **RAG layer** | Retrieved knowledge from indexed documents and project sources |

Both can appear in agent prompts: memory via `relevant_memory_context`, RAG via `knowledge`.

## API endpoints

Base path: `/api/v1/rag`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/projects/{project_id}/documents` | Ingest text document |
| POST | `/projects/{project_id}/documents/bulk` | Bulk ingest (max 50) |
| POST | `/projects/{project_id}/documents/upload` | Upload UTF-8 file |
| GET | `/projects/{project_id}/documents` | List documents |
| GET | `/projects/{project_id}/documents/{document_id}` | Get document metadata |
| DELETE | `/projects/{project_id}/documents/{document_id}` | Delete document + vectors |
| POST | `/projects/{project_id}/search` | Retrieve chunks |
| POST | `/projects/{project_id}/answer` | Grounded answer + citations |
| POST | `/projects/{project_id}/documents/{document_id}/reindex` | Re-index document |

Existing orchestration endpoints remain available:
- `GET /api/v1/orchestration/projects/{id}/knowledge` — search (now delegates to RAG retriever when enabled)
- `POST /api/v1/orchestration/projects/{id}/documents` — upload (unchanged)

## Configuration

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_ENABLED` | `true` | Master switch |
| `RAG_PROVIDER` | `native` | Provider label (`native` = no LangChain runtime dependency) |
| `RAG_VECTOR_STORE` | `pgvector` | Vector backend |
| `RAG_EMBEDDING_PROVIDER` | *(empty → `AI_EMBEDDING_PROVIDER`)* | Embedding provider |
| `RAG_EMBEDDING_MODEL` | *(empty → `OPENAI_EMBEDDING_MODEL`)* | Embedding model |
| `RAG_CHUNK_SIZE` | `0` → `AI_DOCUMENT_CHUNK_SIZE` | Chunk size |
| `RAG_CHUNK_OVERLAP` | `0` → `AI_DOCUMENT_CHUNK_OVERLAP` | Overlap |
| `RAG_TOP_K` | `5` | Default retrieval limit |
| `RAG_SCORE_THRESHOLD` | `0.2` | Minimum similarity score |
| `RAG_RERANK_ENABLED` | `false` | Keyword-overlap reranking |
| `RAG_MAX_CONTEXT_TOKENS` | `4000` | Context budget hint |
| `RAG_INDEXING_BATCH_SIZE` | `64` | Embedding batch size |
| `RAG_LOG_CONTENT_IN_DEV` | `false` | Log content previews in non-prod |

## Agent / LLM integration

Before each agent run, `_build_project_knowledge_context` retrieves top chunks and formats them via `RagPromptBuilder`. The result is injected into `ContextPacket.sections["knowledge"]`.

Indexing uses existing Celery `document_ingest` jobs when `queue_async=true`.

## Security

- All endpoints require authenticated users and project ownership checks via `OrchestrationService.get_project`.
- Retrieval is scoped by `project_id` (and optional `task_id`).
- Production logs record IDs, counts, and latency — not full document bodies.
- Document deletion soft-deletes the row and removes chunk vectors.

## Disabling RAG

Set `RAG_ENABLED=false`. The app falls back to the legacy inline chunk/embed path. Agent runs continue without RAG-enriched context formatting.

## Tests

```bash
cd /home/polat/Desktop/Projects/troop
PYTHONPATH=. backend/.venv/bin/python -m pytest backend/tests/test_rag_layer.py -q
```

## Design decisions

1. **No LangChain dependency** — Troop already has chunking, embeddings, pgvector, and Celery jobs. The module mirrors LangChain’s loader → splitter → embed → store → retrieve → generate pipeline without coupling to LangChain classes.
2. **Single storage backend** — Project documents + pgvector; AI Studio documents remain a separate stack for now.
3. **Grounded answers** — `RagAnswerService` instructs the LLM to cite sources and refuse when context is insufficient.
4. **PDF/URL loaders** — Parser stubs exist; full PDF/URL ingestion can be added as plugins without changing the facade.
