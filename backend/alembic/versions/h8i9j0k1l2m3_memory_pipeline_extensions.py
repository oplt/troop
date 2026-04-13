"""Semantic embedding column, procedural playbooks, memory ingest jobs.

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-04-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        op.execute(
            sa.text(
                "ALTER TABLE semantic_memory_entries "
                "ADD COLUMN IF NOT EXISTS embedding_vector vector(1536)"
            )
        )

    op.create_table(
        "procedural_playbooks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tags_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("namespace", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "slug", name="uq_procedural_playbooks_project_slug"),
    )
    op.create_index("ix_procedural_playbooks_owner_id", "procedural_playbooks", ["owner_id"])
    op.create_index("ix_procedural_playbooks_project_id", "procedural_playbooks", ["project_id"])

    op.create_table(
        "memory_ingest_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="'pending'"),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_ingest_jobs_owner_id", "memory_ingest_jobs", ["owner_id"])
    op.create_index("ix_memory_ingest_jobs_project_id", "memory_ingest_jobs", ["project_id"])
    op.create_index("ix_memory_ingest_jobs_status", "memory_ingest_jobs", ["status"])
    op.create_index("ix_memory_ingest_jobs_job_type", "memory_ingest_jobs", ["job_type"])


def downgrade() -> None:
    op.drop_table("memory_ingest_jobs")
    op.drop_table("procedural_playbooks")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE semantic_memory_entries DROP COLUMN IF EXISTS embedding_vector"))
