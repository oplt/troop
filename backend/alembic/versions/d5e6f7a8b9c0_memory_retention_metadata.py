"""Add semantic memory retention, tombstone, and embedding version metadata.

Revision ID: d5e6f7a8b9c0
Revises: b7c3d9e2a1f4
Create Date: 2026-07-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "b7c3d9e2a1f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("semantic_memory_entries", sa.Column("ttl_days", sa.Integer(), nullable=True))
    op.add_column(
        "semantic_memory_entries",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "semantic_memory_entries",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "semantic_memory_entries",
        sa.Column(
            "retention_policy", sa.String(length=64), nullable=False, server_default="default"
        ),
    )
    op.add_column(
        "semantic_memory_entries",
        sa.Column("memory_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "semantic_memory_entries",
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "semantic_memory_entries",
        sa.Column("embedding_version", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_semantic_memory_entries_expires_at",
        "semantic_memory_entries",
        ["expires_at"],
    )
    op.create_index(
        "ix_semantic_memory_entries_deleted_at",
        "semantic_memory_entries",
        ["deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_semantic_memory_entries_deleted_at", table_name="semantic_memory_entries")
    op.drop_index("ix_semantic_memory_entries_expires_at", table_name="semantic_memory_entries")
    for column in (
        "embedding_version",
        "embedding_model",
        "memory_version",
        "retention_policy",
        "deleted_at",
        "expires_at",
        "ttl_days",
    ):
        op.drop_column("semantic_memory_entries", column)
