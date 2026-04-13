"""Add token fields to run_events and eval_records table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Down_revision: a1b2c3d4e5f6
Branch_labels: None
Depends_on: None
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("run_events", sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("run_events", sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("run_events", sa.Column("cost_usd_micros", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "eval_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("run_a_id", sa.String(), nullable=True),
        sa.Column("run_b_id", sa.String(), nullable=True),
        sa.Column("agent_a_id", sa.String(), nullable=True),
        sa.Column("agent_b_id", sa.String(), nullable=True),
        sa.Column("model_a", sa.String(255), nullable=True),
        sa.Column("model_b", sa.String(255), nullable=True),
        sa.Column("winner", sa.String(8), nullable=True),
        sa.Column("score_a", sa.Float(), nullable=True),
        sa.Column("score_b", sa.Float(), nullable=True),
        sa.Column("criteria_met_a", sa.Boolean(), nullable=True),
        sa.Column("criteria_met_b", sa.Boolean(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_a_id"], ["task_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_b_id"], ["task_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agent_a_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agent_b_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eval_records_project_id", "eval_records", ["project_id"])
    op.create_index("ix_eval_records_task_id", "eval_records", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_eval_records_task_id", "eval_records")
    op.drop_index("ix_eval_records_project_id", "eval_records")
    op.drop_table("eval_records")
    op.drop_column("run_events", "cost_usd_micros")
    op.drop_column("run_events", "output_tokens")
    op.drop_column("run_events", "input_tokens")
