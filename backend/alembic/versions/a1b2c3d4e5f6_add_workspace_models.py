"""add workspace models

Revision ID: a1b2c3d4e5f6
Revises: 7b66139f1c4a
Create Date: 2026-04-12 20:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "7b66139f1c4a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orchestrator_tasks", sa.Column("parent_task_id", sa.String(), nullable=True))
    op.create_index("ix_orchestrator_tasks_parent_task_id", "orchestrator_tasks", ["parent_task_id"])
    op.create_foreign_key(
        "fk_task_parent",
        "orchestrator_tasks",
        "orchestrator_tasks",
        ["parent_task_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_table(
        "project_milestones",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_milestones_project_id", "project_milestones", ["project_id"])

    op.create_table(
        "project_decisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.String(),
            sa.ForeignKey("orchestrator_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "brainstorm_id",
            sa.String(),
            sa.ForeignKey("brainstorms.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("author_label", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_decisions_project_id", "project_decisions", ["project_id"])
    op.create_index("ix_project_decisions_task_id", "project_decisions", ["task_id"])
    op.create_index("ix_project_decisions_brainstorm_id", "project_decisions", ["brainstorm_id"])


def downgrade() -> None:
    op.drop_table("project_decisions")
    op.drop_table("project_milestones")
    op.drop_constraint("fk_task_parent", "orchestrator_tasks", type_="foreignkey")
    op.drop_index("ix_orchestrator_tasks_parent_task_id", table_name="orchestrator_tasks")
    op.drop_column("orchestrator_tasks", "parent_task_id")
