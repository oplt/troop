"""External knowledge sources for drive RAG sync."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "q2r3s4t5u6v7"
down_revision = "p1q2r3s4t5u6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_knowledge_sources",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=True),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("connector_installation_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("root_config_json", sa.JSON(), nullable=False),
        sa.Column("sync_cursor", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connector_installation_id"], ["connector_installations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "connector_installation_id",
            "provider",
            name="uq_external_knowledge_sources_project_installation",
        ),
    )
    op.create_index(
        op.f("ix_external_knowledge_sources_owner_id"),
        "external_knowledge_sources",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_knowledge_sources_project_id"),
        "external_knowledge_sources",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_knowledge_sources_connector_installation_id"),
        "external_knowledge_sources",
        ["connector_installation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_knowledge_sources_provider"),
        "external_knowledge_sources",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_knowledge_sources_status"),
        "external_knowledge_sources",
        ["status"],
        unique=False,
    )

    op.create_table(
        "external_document_sync_states",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("external_file_id", sa.String(length=512), nullable=False),
        sa.Column("external_path", sa.String(length=1024), nullable=False),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("project_document_id", sa.String(), nullable=True),
        sa.Column("acl_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("sync_status", sa.String(length=32), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_document_id"], ["project_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["external_knowledge_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_file_id", name="uq_external_document_sync_source_file"),
    )
    op.create_index(
        op.f("ix_external_document_sync_states_source_id"),
        "external_document_sync_states",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_document_sync_states_project_document_id"),
        "external_document_sync_states",
        ["project_document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_document_sync_states_sync_status"),
        "external_document_sync_states",
        ["sync_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_external_document_sync_states_sync_status"),
        table_name="external_document_sync_states",
    )
    op.drop_index(
        op.f("ix_external_document_sync_states_project_document_id"),
        table_name="external_document_sync_states",
    )
    op.drop_index(
        op.f("ix_external_document_sync_states_source_id"),
        table_name="external_document_sync_states",
    )
    op.drop_table("external_document_sync_states")
    op.drop_index(op.f("ix_external_knowledge_sources_status"), table_name="external_knowledge_sources")
    op.drop_index(op.f("ix_external_knowledge_sources_provider"), table_name="external_knowledge_sources")
    op.drop_index(
        op.f("ix_external_knowledge_sources_connector_installation_id"),
        table_name="external_knowledge_sources",
    )
    op.drop_index(op.f("ix_external_knowledge_sources_project_id"), table_name="external_knowledge_sources")
    op.drop_index(op.f("ix_external_knowledge_sources_owner_id"), table_name="external_knowledge_sources")
    op.drop_table("external_knowledge_sources")
