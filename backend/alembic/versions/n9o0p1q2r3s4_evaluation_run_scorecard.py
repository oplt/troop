"""Evaluation run scorecard columns (EVAL-001B).

Revision ID: n9o0p1q2r3s4
Revises: m8n9o0p1q2r3
Create Date: 2026-08-14 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "n9o0p1q2r3s4"
down_revision: str | Sequence[str] | None = "m8n9o0p1q2r3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_evaluation_runs",
        sa.Column("baseline_run_id", sa.String(), nullable=True),
    )
    op.add_column(
        "ai_evaluation_runs",
        sa.Column("candidate_config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "ai_evaluation_runs",
        sa.Column("metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "ai_evaluation_runs",
        sa.Column("scorecard_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "ai_evaluation_runs",
        sa.Column("judge_version_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "ai_evaluation_run_items",
        sa.Column("metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_index(
        "ix_ai_evaluation_runs_baseline_run_id",
        "ai_evaluation_runs",
        ["baseline_run_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_ai_evaluation_runs_baseline_run_id",
        "ai_evaluation_runs",
        "ai_evaluation_runs",
        ["baseline_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_ai_evaluation_runs_baseline_run_id",
        "ai_evaluation_runs",
        type_="foreignkey",
    )
    op.drop_index("ix_ai_evaluation_runs_baseline_run_id", table_name="ai_evaluation_runs")
    op.drop_column("ai_evaluation_run_items", "metrics_json")
    op.drop_column("ai_evaluation_runs", "judge_version_id")
    op.drop_column("ai_evaluation_runs", "scorecard_json")
    op.drop_column("ai_evaluation_runs", "metrics_json")
    op.drop_column("ai_evaluation_runs", "candidate_config_json")
    op.drop_column("ai_evaluation_runs", "baseline_run_id")
