"""Add response_sla_hours to orchestrator_tasks.

Revision ID: f5a6b7c8d9e0
Revises: e1f2a3b4c5d6
Create Date: 2026-04-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orchestrator_tasks",
        sa.Column("response_sla_hours", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orchestrator_tasks", "response_sla_hours")
