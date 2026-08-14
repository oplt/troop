"""Split workflow draft/published pointers and add graph hash (WF-001A).

Revision ID: l8f9a0b1c2d3
Revises: k7e8f9a0b1c2
Create Date: 2026-08-14 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "l8f9a0b1c2d3"
down_revision: str | Sequence[str] | None = "k7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_definitions",
        sa.Column("draft_version_id", sa.String(), nullable=True),
    )
    op.add_column(
        "workflow_definitions",
        sa.Column("published_version_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_workflow_definitions_draft_version_id",
        "workflow_definitions",
        ["draft_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_definitions_published_version_id",
        "workflow_definitions",
        ["published_version_id"],
        unique=False,
    )
    op.add_column(
        "workflow_versions",
        sa.Column("graph_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_workflow_versions_graph_hash",
        "workflow_versions",
        ["graph_hash"],
        unique=False,
    )

    bind = op.get_bind()
    bind.execute(
        text(
            """
            UPDATE workflow_definitions AS wd
            SET draft_version_id = wv.id
            FROM workflow_versions AS wv
            WHERE wd.current_version_id = wv.id
              AND COALESCE(wv.is_published, FALSE) IS FALSE
            """
        )
    )
    bind.execute(
        text(
            """
            UPDATE workflow_definitions AS wd
            SET published_version_id = wv.id
            FROM workflow_versions AS wv
            WHERE wd.current_version_id = wv.id
              AND COALESCE(wv.is_published, FALSE) IS TRUE
            """
        )
    )
    bind.execute(
        text(
            """
            UPDATE workflow_definitions AS wd
            SET published_version_id = latest.id
            FROM (
                SELECT DISTINCT ON (workflow_id)
                    workflow_id,
                    id
                FROM workflow_versions
                WHERE COALESCE(is_published, FALSE) IS TRUE
                ORDER BY workflow_id, version_number DESC, created_at DESC
            ) AS latest
            WHERE wd.published_version_id IS NULL
              AND wd.id = latest.workflow_id
            """
        )
    )
    bind.execute(
        text(
            """
            UPDATE workflow_definitions AS wd
            SET draft_version_id = draft.id
            FROM (
                SELECT DISTINCT ON (workflow_id)
                    workflow_id,
                    id
                FROM workflow_versions
                WHERE COALESCE(is_published, FALSE) IS FALSE
                ORDER BY workflow_id, created_at DESC
            ) AS draft
            WHERE wd.draft_version_id IS NULL
              AND wd.id = draft.workflow_id
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_versions_graph_hash", table_name="workflow_versions")
    op.drop_column("workflow_versions", "graph_hash")
    op.drop_index(
        "ix_workflow_definitions_published_version_id",
        table_name="workflow_definitions",
    )
    op.drop_index(
        "ix_workflow_definitions_draft_version_id",
        table_name="workflow_definitions",
    )
    op.drop_column("workflow_definitions", "published_version_id")
    op.drop_column("workflow_definitions", "draft_version_id")
