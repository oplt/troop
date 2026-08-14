"""Add approval SLA, delegation, and escalation columns (HITL-002B).

Revision ID: k7e8f9a0b1c2
Revises: j6d7e8f9a0b1
Create Date: 2026-08-14 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "k7e8f9a0b1c2"
down_revision: str | Sequence[str] | None = "j6d7e8f9a0b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "approval_requests",
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_approval_requests_due_at",
        "approval_requests",
        ["due_at"],
        unique=False,
    )
    op.add_column(
        "approval_requests",
        sa.Column(
            "sla_policy_json",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "approval_requests",
        sa.Column(
            "delegations_json",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "approval_requests",
        sa.Column(
            "escalation_state_json",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.alter_column("approval_requests", "sla_policy_json", server_default=None)
    op.alter_column("approval_requests", "delegations_json", server_default=None)
    op.alter_column("approval_requests", "escalation_state_json", server_default=None)


def downgrade() -> None:
    op.drop_column("approval_requests", "escalation_state_json")
    op.drop_column("approval_requests", "delegations_json")
    op.drop_column("approval_requests", "sla_policy_json")
    op.drop_index("ix_approval_requests_due_at", table_name="approval_requests")
    op.drop_column("approval_requests", "due_at")
