# Phase 5 operations: unified memory lifecycle

Phase 5 makes semantic memory a canonical, provider-neutral path while keeping
the existing orchestration service as the compatibility facade for approvals,
conflict review, and route response shapes.

## Scope and tenant boundary

Every memory operation is owned by `owner_id`. When a project belongs to a
company, `company_id` is the tenant boundary and is carried through
`MemoryAccessContext`/`MemoryFilters`. Project, agent, task, user, and global
namespaces are validated by `backend/modules/memory/namespaces.py`; arbitrary
namespace strings are normalized before persistence. Retrieval applies owner,
scope, project, agent, task, namespace, deleted, and expiry filters before
vector ranking.

## Retention and deletion

Semantic entries now carry `ttl_days`, `expires_at`, `deleted_at`,
`retention_policy`, and `memory_version`. The scheduled retention sweep marks
expired semantic rows as tombstones and clears their vector embeddings. Normal
retrieval excludes expired/tombstoned rows. Explicit semantic deletion uses the
same canonical provider path and is therefore cache-invalidated and excluded
from future retrieval. The additive migration is
`d5e6f7a8b9c0_memory_retention_metadata.py`.

The existing document, agent-memory, and episodic retention jobs remain
independent because they have different archival semantics. Do not copy
semantic text into episodic cold storage during privacy expiry; archival and
deletion are separate policies.

## Provider boundary

Application code depends on `MemoryService`, `MemoryProvider`, or the minimal
`MemoryStore` protocol. PostgreSQL/pgvector remains the current adapter.
Provider-specific metadata includes embedding model/version and is not exposed
as a high-cardinality metric label. A future Redis/vector provider must preserve
owner and namespace filtering and the same tombstone/TTL behavior.

## Prompt safety

Memory context is ranked using retrieval score, query overlap, confidence, and
recency, then clipped to `context_max_tokens`. The project memory settings UI
controls the default semantic TTL and memory context budget. Logs and prompt
telemetry contain sizes, IDs, scores, and provenance—not raw memory content or
secrets.

## Migration and rollback

1. Deploy the additive migration before application code that writes new fields.
2. Deploy the application; legacy rows remain valid with no TTL and version 1.
3. Run the existing retention worker to backfill operational tombstones only
   for rows with explicit expiry.
4. Verify owner/project/agent isolation and retrieval counts on a golden set.

Rollback is application-compatible because the new columns are nullable or
have server defaults. If provider behavior must be reverted, route writes back
through the old orchestration persistence method while retaining the migration;
do not drop columns during rollback.
