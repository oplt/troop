from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

import asyncpg

from backend.core.config import settings
from backend.modules.orchestration.model_utils import EMBEDDING_VECTOR_DIMENSIONS


EXPECTED_INDEXES = {
    "project_document_chunks": "ix_project_document_chunks_embedding_hnsw",
    "semantic_memory_entries": "ix_semantic_memory_entries_embedding_hnsw",
    "episodic_search_index": "ix_episodic_search_index_embedding_hnsw",
}


def _vector_literal(dimensions: int) -> str:
    values = ["0.001"] * max(1, dimensions)
    return "[" + ",".join(values) + "]"


async def _fetch_plan(conn: asyncpg.Connection, sql: str, *args: Any) -> dict[str, Any]:
    row = await conn.fetchrow(sql, *args)
    if row is None:
        raise RuntimeError("EXPLAIN returned no plan")
    return row[0][0]


def _plan_text(node: Any) -> str:
    return json.dumps(node, sort_keys=True)


def _uses_expected_index(plan: dict[str, Any], index_name: str) -> bool:
    return index_name in _plan_text(plan)


async def run_plan_check(
    *,
    database_url: str,
    project_id: str,
    dimensions: int,
    limit: int,
    require_index: bool,
) -> int:
    conn = await asyncpg.connect(database_url)
    try:
        vector = _vector_literal(dimensions)
        table_rows = await conn.fetch(
            """
            SELECT tablename, indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = ANY($1::text[])
            ORDER BY tablename, indexname
            """,
            list(EXPECTED_INDEXES.values()),
        )
        indexes = {row["tablename"]: row["indexname"] for row in table_rows}

        project_plan = await _fetch_plan(
            conn,
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT c.id, 1 - (c.embedding_vector <=> CAST($1 AS vector)) AS score
            FROM project_document_chunks c
            INNER JOIN project_documents d ON d.id = c.project_document_id
            WHERE c.project_id = $2
              AND c.deleted_at IS NULL
              AND d.deleted_at IS NULL
              AND c.embedding_vector IS NOT NULL
            ORDER BY c.embedding_vector <=> CAST($1 AS vector)
            LIMIT $3
            """,
            vector,
            project_id,
            limit,
        )
        semantic_plan = await _fetch_plan(
            conn,
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT id, 1 - (embedding_vector <=> CAST($1 AS vector)) AS score
            FROM semantic_memory_entries
            WHERE project_id = $2
              AND deleted_at IS NULL
              AND embedding_vector IS NOT NULL
            ORDER BY embedding_vector <=> CAST($1 AS vector)
            LIMIT $3
            """,
            vector,
            project_id,
            limit,
        )
        episodic_plan = await _fetch_plan(
            conn,
            """
            EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
            SELECT id, 1 - (embedding_vector <=> CAST($1 AS vector)) AS score
            FROM episodic_search_index
            WHERE project_id = $2
              AND archived_at IS NULL
              AND embedding_vector IS NOT NULL
            ORDER BY embedding_vector <=> CAST($1 AS vector)
            LIMIT $3
            """,
            vector,
            project_id,
            limit,
        )

        checks = {
            "project_document_chunks": {
                "expected_index": EXPECTED_INDEXES["project_document_chunks"],
                "index_exists": indexes.get("project_document_chunks")
                == EXPECTED_INDEXES["project_document_chunks"],
                "plan_uses_index": _uses_expected_index(
                    project_plan,
                    EXPECTED_INDEXES["project_document_chunks"],
                ),
                "plan": project_plan,
            },
            "semantic_memory_entries": {
                "expected_index": EXPECTED_INDEXES["semantic_memory_entries"],
                "index_exists": indexes.get("semantic_memory_entries")
                == EXPECTED_INDEXES["semantic_memory_entries"],
                "plan_uses_index": _uses_expected_index(
                    semantic_plan,
                    EXPECTED_INDEXES["semantic_memory_entries"],
                ),
                "plan": semantic_plan,
            },
            "episodic_search_index": {
                "expected_index": EXPECTED_INDEXES["episodic_search_index"],
                "index_exists": indexes.get("episodic_search_index")
                == EXPECTED_INDEXES["episodic_search_index"],
                "plan_uses_index": _uses_expected_index(
                    episodic_plan,
                    EXPECTED_INDEXES["episodic_search_index"],
                ),
                "plan": episodic_plan,
            },
        }
        print(json.dumps({"project_id": project_id, "checks": checks}, indent=2, default=str))
        if require_index:
            failed = [
                name
                for name, check in checks.items()
                if not check["index_exists"] or not check["plan_uses_index"]
            ]
            if failed:
                print("pgvector plan check failed: " + ", ".join(failed))
                return 1
        return 0
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate pgvector index presence and query plans.")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--database-url", default=settings.DATABASE_URL)
    parser.add_argument("--dimensions", type=int, default=EMBEDDING_VECTOR_DIMENSIONS)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--require-index", action="store_true")
    args = parser.parse_args()
    return asyncio.run(
        run_plan_check(
            database_url=args.database_url,
            project_id=args.project_id,
            dimensions=args.dimensions,
            limit=max(1, args.limit),
            require_index=args.require_index,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
