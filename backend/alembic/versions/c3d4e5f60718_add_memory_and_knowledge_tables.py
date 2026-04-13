"""add memory and knowledge tables

Revision ID: c3d4e5f60718
Revises: 9f8d7c6b5a4e
Create Date: 2026-04-13 12:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d4e5f60718"
down_revision: str | Sequence[str] | None = "9f8d7c6b5a4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("project_documents", sa.Column("ingestion_status", sa.String(length=32), nullable=False, server_default="pending"))
    op.add_column("project_documents", sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("project_documents", sa.Column("ttl_days", sa.Integer(), nullable=True))
    op.add_column("project_documents", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("project_documents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("project_documents", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_index(op.f("ix_project_documents_expires_at"), "project_documents", ["expires_at"], unique=False)
    op.create_index(op.f("ix_project_documents_deleted_at"), "project_documents", ["deleted_at"], unique=False)

    op.create_table(
        "project_document_chunks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_document_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_document_id"], ["project_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_document_chunks_project_document_id"), "project_document_chunks", ["project_document_id"], unique=False)
    op.create_index(op.f("ix_project_document_chunks_project_id"), "project_document_chunks", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_document_chunks_task_id"), "project_document_chunks", ["task_id"], unique=False)
    op.create_index(op.f("ix_project_document_chunks_deleted_at"), "project_document_chunks", ["deleted_at"], unique=False)

    op.create_table(
        "agent_memory_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("source_run_id", sa.String(), nullable=True),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approved_by_user_id", sa.String(), nullable=True),
        sa.Column("ttl_days", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agent_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_run_id"], ["task_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_memory_entries_owner_id"), "agent_memory_entries", ["owner_id"], unique=False)
    op.create_index(op.f("ix_agent_memory_entries_agent_id"), "agent_memory_entries", ["agent_id"], unique=False)
    op.create_index(op.f("ix_agent_memory_entries_project_id"), "agent_memory_entries", ["project_id"], unique=False)
    op.create_index(op.f("ix_agent_memory_entries_source_run_id"), "agent_memory_entries", ["source_run_id"], unique=False)
    op.create_index(op.f("ix_agent_memory_entries_key"), "agent_memory_entries", ["key"], unique=False)
    op.create_index(op.f("ix_agent_memory_entries_status"), "agent_memory_entries", ["status"], unique=False)
    op.create_index(op.f("ix_agent_memory_entries_approved_by_user_id"), "agent_memory_entries", ["approved_by_user_id"], unique=False)
    op.create_index(op.f("ix_agent_memory_entries_expires_at"), "agent_memory_entries", ["expires_at"], unique=False)
    op.create_index(op.f("ix_agent_memory_entries_deleted_at"), "agent_memory_entries", ["deleted_at"], unique=False)

    op.alter_column("project_documents", "ingestion_status", server_default=None)
    op.alter_column("project_documents", "chunk_count", server_default=None)
    op.alter_column("project_documents", "updated_at", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_memory_entries_deleted_at"), table_name="agent_memory_entries")
    op.drop_index(op.f("ix_agent_memory_entries_expires_at"), table_name="agent_memory_entries")
    op.drop_index(op.f("ix_agent_memory_entries_approved_by_user_id"), table_name="agent_memory_entries")
    op.drop_index(op.f("ix_agent_memory_entries_status"), table_name="agent_memory_entries")
    op.drop_index(op.f("ix_agent_memory_entries_key"), table_name="agent_memory_entries")
    op.drop_index(op.f("ix_agent_memory_entries_source_run_id"), table_name="agent_memory_entries")
    op.drop_index(op.f("ix_agent_memory_entries_project_id"), table_name="agent_memory_entries")
    op.drop_index(op.f("ix_agent_memory_entries_agent_id"), table_name="agent_memory_entries")
    op.drop_index(op.f("ix_agent_memory_entries_owner_id"), table_name="agent_memory_entries")
    op.drop_table("agent_memory_entries")

    op.drop_index(op.f("ix_project_document_chunks_deleted_at"), table_name="project_document_chunks")
    op.drop_index(op.f("ix_project_document_chunks_task_id"), table_name="project_document_chunks")
    op.drop_index(op.f("ix_project_document_chunks_project_id"), table_name="project_document_chunks")
    op.drop_index(op.f("ix_project_document_chunks_project_document_id"), table_name="project_document_chunks")
    op.drop_table("project_document_chunks")

    op.drop_index(op.f("ix_project_documents_deleted_at"), table_name="project_documents")
    op.drop_index(op.f("ix_project_documents_expires_at"), table_name="project_documents")
    op.drop_column("project_documents", "updated_at")
    op.drop_column("project_documents", "deleted_at")
    op.drop_column("project_documents", "expires_at")
    op.drop_column("project_documents", "ttl_days")
    op.drop_column("project_documents", "chunk_count")
    op.drop_column("project_documents", "ingestion_status")
