"""Episodic cold archives, vector index, semantic graph links.

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-04-14

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "episodic_archive_manifests",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stats_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_episodic_archive_manifests_owner_id", "episodic_archive_manifests", ["owner_id"])
    op.create_index("ix_episodic_archive_manifests_project_id", "episodic_archive_manifests", ["project_id"])

    if bind.dialect.name == "postgresql":
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        op.execute(
            sa.text(
                """
                CREATE TABLE episodic_search_index (
                    id VARCHAR NOT NULL PRIMARY KEY,
                    owner_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    project_id VARCHAR NOT NULL REFERENCES orchestrator_projects(id) ON DELETE CASCADE,
                    source_kind VARCHAR(32) NOT NULL,
                    source_id VARCHAR(64) NOT NULL,
                    text_content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    archived_at TIMESTAMPTZ,
                    embedding_vector vector(1536),
                    CONSTRAINT uq_episodic_index_project_source
                        UNIQUE (project_id, source_kind, source_id)
                )
                """
            )
        )
        op.create_index("ix_episodic_search_index_owner_id", "episodic_search_index", ["owner_id"])
        op.create_index("ix_episodic_search_index_project_id", "episodic_search_index", ["project_id"])
        op.create_index("ix_episodic_search_index_source_kind", "episodic_search_index", ["source_kind"])
        op.create_index("ix_episodic_search_index_created_at", "episodic_search_index", ["created_at"])
    else:
        op.create_table(
            "episodic_search_index",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("owner_id", sa.String(), nullable=False),
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("source_kind", sa.String(length=32), nullable=False),
            sa.Column("source_id", sa.String(length=64), nullable=False),
            sa.Column("text_content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("embedding_vector", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "source_kind", "source_id", name="uq_episodic_index_project_source"),
        )
        op.create_index("ix_episodic_search_index_owner_id", "episodic_search_index", ["owner_id"])
        op.create_index("ix_episodic_search_index_project_id", "episodic_search_index", ["project_id"])
        op.create_index("ix_episodic_search_index_source_kind", "episodic_search_index", ["source_kind"])
        op.create_index("ix_episodic_search_index_created_at", "episodic_search_index", ["created_at"])

    op.create_table(
        "semantic_memory_links",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("from_entry_id", sa.String(), nullable=False),
        sa.Column("to_entry_id", sa.String(), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_entry_id"], ["semantic_memory_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_entry_id"], ["semantic_memory_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("from_entry_id", "to_entry_id", "relation_type", name="uq_semantic_link_edge"),
    )
    op.create_index("ix_semantic_memory_links_project_id", "semantic_memory_links", ["project_id"])
    op.create_index("ix_semantic_memory_links_from_entry_id", "semantic_memory_links", ["from_entry_id"])
    op.create_index("ix_semantic_memory_links_to_entry_id", "semantic_memory_links", ["to_entry_id"])


def downgrade() -> None:
    op.drop_table("semantic_memory_links")
    op.drop_table("episodic_search_index")
    op.drop_table("episodic_archive_manifests")
