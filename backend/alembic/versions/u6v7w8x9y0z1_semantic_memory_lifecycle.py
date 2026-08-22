"""Add semantic memory canonical lifecycle columns.

Revision ID: u6v7w8x9y0z1
Revises: t5u6v7w8x9y0
Create Date: 2026-08-22 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "u6v7w8x9y0z1"
down_revision: str | Sequence[str] | None = "t5u6v7w8x9y0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "semantic_memory_entries",
        sa.Column("canonical_key", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "semantic_memory_entries",
        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "semantic_memory_entries",
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "semantic_memory_entries",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="current"),
    )
    op.add_column(
        "semantic_memory_entries",
        sa.Column(
            "supersedes_memory_id",
            sa.String(),
            sa.ForeignKey("semantic_memory_entries.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_semantic_memory_entries_canonical_key",
        "semantic_memory_entries",
        ["canonical_key"],
    )
    op.create_index(
        "ix_semantic_memory_entries_valid_from",
        "semantic_memory_entries",
        ["valid_from"],
    )
    op.create_index(
        "ix_semantic_memory_entries_valid_until",
        "semantic_memory_entries",
        ["valid_until"],
    )
    op.create_index(
        "ix_semantic_memory_entries_status",
        "semantic_memory_entries",
        ["status"],
    )
    op.create_index(
        "ix_semantic_memory_entries_supersedes_memory_id",
        "semantic_memory_entries",
        ["supersedes_memory_id"],
    )
    op.create_index(
        "uq_semantic_memory_current_canonical_key",
        "semantic_memory_entries",
        ["owner_id", "canonical_key"],
        unique=True,
        postgresql_where=sa.text(
            "canonical_key IS NOT NULL AND status = 'current' AND deleted_at IS NULL"
        ),
    )


def downgrade() -> None:
    for index in (
        "uq_semantic_memory_current_canonical_key",
        "ix_semantic_memory_entries_supersedes_memory_id",
        "ix_semantic_memory_entries_status",
        "ix_semantic_memory_entries_valid_until",
        "ix_semantic_memory_entries_valid_from",
        "ix_semantic_memory_entries_canonical_key",
    ):
        op.drop_index(index, table_name="semantic_memory_entries")
    for column in (
        "supersedes_memory_id",
        "status",
        "valid_until",
        "valid_from",
        "canonical_key",
    ):
        op.drop_column("semantic_memory_entries", column)
