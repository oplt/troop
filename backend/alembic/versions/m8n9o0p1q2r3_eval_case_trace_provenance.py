"""Evaluation case trace provenance columns (EVAL-001A).

Revision ID: m8n9o0p1q2r3
Revises: l8f9a0b1c2d3
Create Date: 2026-08-14 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "m8n9o0p1q2r3"
down_revision: str | Sequence[str] | None = "l8f9a0b1c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("source_run_id", sa.String(), nullable=True),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("source_trace_span_id", sa.String(), nullable=True),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("provenance_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("input_snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("expected_assertions_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "ai_evaluation_cases",
        sa.Column("correction_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_ai_evaluation_cases_source_run_id",
        "ai_evaluation_cases",
        ["source_run_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_ai_evaluation_cases_source_run_id",
        "ai_evaluation_cases",
        "task_runs",
        ["source_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_ai_evaluation_cases_source_run_id",
        "ai_evaluation_cases",
        type_="foreignkey",
    )
    op.drop_index("ix_ai_evaluation_cases_source_run_id", table_name="ai_evaluation_cases")
    op.drop_column("ai_evaluation_cases", "correction_json")
    op.drop_column("ai_evaluation_cases", "expected_assertions_json")
    op.drop_column("ai_evaluation_cases", "input_snapshot_json")
    op.drop_column("ai_evaluation_cases", "provenance_json")
    op.drop_column("ai_evaluation_cases", "source_trace_span_id")
    op.drop_column("ai_evaluation_cases", "source_run_id")
