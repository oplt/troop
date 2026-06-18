"""Add ai_document_chunks.embedding_vector and pgvector HNSW indexes.

Revision ID: b7c3d9e2a1f4
Revises: e2b7c4d1a0f3
Create Date: 2026-06-18 12:00:00.000000
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa

from alembic import op

revision: str = "b7c3d9e2a1f4"
down_revision: str | Sequence[str] | None = "e2b7c4d1a0f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VECTOR_INDEXES: tuple[tuple[str, str], ...] = (
    (
        "ix_project_document_chunks_embedding_hnsw",
        """
        CREATE INDEX IF NOT EXISTS ix_project_document_chunks_embedding_hnsw
        ON project_document_chunks
        USING hnsw (embedding_vector vector_cosine_ops)
        WHERE embedding_vector IS NOT NULL
        """,
    ),
    (
        "ix_semantic_memory_entries_embedding_hnsw",
        """
        CREATE INDEX IF NOT EXISTS ix_semantic_memory_entries_embedding_hnsw
        ON semantic_memory_entries
        USING hnsw (embedding_vector vector_cosine_ops)
        WHERE embedding_vector IS NOT NULL
        """,
    ),
    (
        "ix_episodic_search_index_embedding_hnsw",
        """
        CREATE INDEX IF NOT EXISTS ix_episodic_search_index_embedding_hnsw
        ON episodic_search_index
        USING hnsw (embedding_vector vector_cosine_ops)
        WHERE embedding_vector IS NOT NULL
        """,
    ),
    (
        "ix_ai_document_chunks_embedding_hnsw",
        """
        CREATE INDEX IF NOT EXISTS ix_ai_document_chunks_embedding_hnsw
        ON ai_document_chunks
        USING hnsw (embedding_vector vector_cosine_ops)
        WHERE embedding_vector IS NOT NULL
        """,
    ),
)


def upgrade() -> None:
    op.add_column(
        "ai_document_chunks",
        sa.Column(
            "embedding_vector",
            pgvector.sqlalchemy.vector.VECTOR(dim=1536),
            nullable=True,
        ),
    )
    for _name, ddl in _VECTOR_INDEXES:
        op.execute(sa.text(ddl))


def downgrade() -> None:
    for name, _ddl in reversed(_VECTOR_INDEXES):
        op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))
    op.drop_column("ai_document_chunks", "embedding_vector")
