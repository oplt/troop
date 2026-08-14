"""Composite indexes for approvals, tasks, and runs hot filters.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-14 02:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_approval_requests_project_status",
        "approval_requests",
        ["project_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_task_runs_project_status",
        "task_runs",
        ["project_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_orchestrator_tasks_project_status",
        "orchestrator_tasks",
        ["project_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_brainstorms_project_status",
        "brainstorms",
        ["project_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_brainstorms_project_status", table_name="brainstorms")
    op.drop_index("ix_orchestrator_tasks_project_status", table_name="orchestrator_tasks")
    op.drop_index("ix_task_runs_project_status", table_name="task_runs")
    op.drop_index("ix_approval_requests_project_status", table_name="approval_requests")
