"""Add indexes for common list/calendar/connector query patterns.

Revision ID: c3d4e5f6a7b8
Revises: ab12cd34ef56
Create Date: 2026-08-13 00:20:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "ab12cd34ef56"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_orchestrator_projects_owner_updated",
        "orchestrator_projects",
        ["owner_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_orchestrator_tasks_project_due_date",
        "orchestrator_tasks",
        ["project_id", "due_date"],
        unique=False,
    )
    op.create_index(
        "ix_task_runs_project_created",
        "task_runs",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_connector_installations_owner_updated",
        "connector_installations",
        ["owner_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_connector_installations_owner_updated",
        table_name="connector_installations",
    )
    op.drop_index("ix_task_runs_project_created", table_name="task_runs")
    op.drop_index("ix_orchestrator_tasks_project_due_date", table_name="orchestrator_tasks")
    op.drop_index("ix_orchestrator_projects_owner_updated", table_name="orchestrator_projects")
