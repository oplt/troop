"""Add semantic_memory_entries (Layer 3 typed semantic store).

Revision ID: g7h8i9j0k1l2
Revises: f5a6b7c8d9e0
Create Date: 2026-04-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "semantic_memory_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("entry_type", sa.String(length=64), nullable=False),
        sa.Column("namespace", sa.String(length=512), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("source_chunk_id", sa.String(), nullable=True),
        sa.Column("source_task_id", sa.String(), nullable=True),
        sa.Column("source_run_id", sa.String(), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_by_user_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["project_document_chunks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_run_id"], ["task_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_task_id"], ["orchestrator_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_semantic_memory_entries_owner_id", "semantic_memory_entries", ["owner_id"])
    op.create_index("ix_semantic_memory_entries_scope", "semantic_memory_entries", ["scope"])
    op.create_index("ix_semantic_memory_entries_project_id", "semantic_memory_entries", ["project_id"])
    op.create_index("ix_semantic_memory_entries_agent_id", "semantic_memory_entries", ["agent_id"])
    op.create_index("ix_semantic_memory_entries_entry_type", "semantic_memory_entries", ["entry_type"])
    op.create_index("ix_semantic_memory_entries_namespace", "semantic_memory_entries", ["namespace"])
    op.create_index(
        "ix_semantic_memory_entries_source_chunk_id", "semantic_memory_entries", ["source_chunk_id"]
    )
    op.create_index(
        "ix_semantic_memory_entries_source_task_id", "semantic_memory_entries", ["source_task_id"]
    )
    op.create_index(
        "ix_semantic_memory_entries_source_run_id", "semantic_memory_entries", ["source_run_id"]
    )
    op.create_index(
        "ix_semantic_memory_entries_created_by_user_id",
        "semantic_memory_entries",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_table("semantic_memory_entries")
