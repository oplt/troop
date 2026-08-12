"""Add workflow_child_executions for indexed parent/child wakes.

Revision ID: a1b2c3d4e5f6
Revises: f9c8d7e6a5b4
Create Date: 2026-08-12 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f9c8d7e6a5b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_child_executions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workflow_run_id", sa.String(), nullable=False),
        sa.Column("workflow_node_id", sa.String(length=255), nullable=False),
        sa.Column("child_type", sa.String(length=32), nullable=False),
        sa.Column("child_run_id", sa.String(), nullable=True),
        sa.Column("branch_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_run_id",
            "workflow_node_id",
            "child_run_id",
            name="uq_workflow_child_exec_run_node_child",
        ),
        sa.UniqueConstraint(
            "workflow_run_id",
            "workflow_node_id",
            "branch_key",
            name="uq_workflow_child_exec_run_node_branch",
        ),
    )
    op.create_index(
        "ix_workflow_child_executions_workflow_run_id",
        "workflow_child_executions",
        ["workflow_run_id"],
    )
    op.create_index(
        "ix_workflow_child_executions_child_run_id",
        "workflow_child_executions",
        ["child_run_id"],
    )
    op.create_index(
        "ix_workflow_child_executions_status",
        "workflow_child_executions",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_child_executions_status", table_name="workflow_child_executions")
    op.drop_index(
        "ix_workflow_child_executions_child_run_id", table_name="workflow_child_executions"
    )
    op.drop_index(
        "ix_workflow_child_executions_workflow_run_id", table_name="workflow_child_executions"
    )
    op.drop_table("workflow_child_executions")
