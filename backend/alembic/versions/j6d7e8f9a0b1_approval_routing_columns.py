"""Add role-based approval routing columns (HITL-002A).

Revision ID: j6d7e8f9a0b1
Revises: i5c6d7e8f9a0
Create Date: 2026-08-14 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "j6d7e8f9a0b1"
down_revision: str | Sequence[str] | None = "i5c6d7e8f9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("approval_requests", sa.Column("workspace_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_approval_requests_workspace_id_workspaces",
        "approval_requests",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_approval_requests_workspace_id",
        "approval_requests",
        ["workspace_id"],
        unique=False,
    )
    op.add_column(
        "approval_requests",
        sa.Column(
            "eligible_approvers_json",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "approval_requests",
        sa.Column(
            "routing_snapshot_json",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "approval_requests",
        sa.Column("decided_eligibility_reason", sa.Text(), nullable=True),
    )

    bind = op.get_bind()
    bind.execute(
        text(
            """
            UPDATE approval_requests AS ar
            SET workspace_id = w.id
            FROM orchestrator_projects AS p
            JOIN workspaces AS w ON w.owner_user_id = p.owner_id AND w.is_default IS TRUE
            WHERE ar.project_id = p.id
              AND ar.workspace_id IS NULL
            """
        )
    )
    bind.execute(
        text(
            """
            UPDATE approval_requests AS ar
            SET workspace_id = w.id
            FROM workspaces AS w
            WHERE ar.project_id IS NULL
              AND ar.requested_by_user_id = w.owner_user_id
              AND w.is_default IS TRUE
              AND ar.workspace_id IS NULL
            """
        )
    )

    op.alter_column("approval_requests", "eligible_approvers_json", server_default=None)
    op.alter_column("approval_requests", "routing_snapshot_json", server_default=None)


def downgrade() -> None:
    op.drop_column("approval_requests", "decided_eligibility_reason")
    op.drop_column("approval_requests", "routing_snapshot_json")
    op.drop_column("approval_requests", "eligible_approvers_json")
    op.drop_index("ix_approval_requests_workspace_id", table_name="approval_requests")
    op.drop_constraint(
        "fk_approval_requests_workspace_id_workspaces",
        "approval_requests",
        type_="foreignkey",
    )
    op.drop_column("approval_requests", "workspace_id")
