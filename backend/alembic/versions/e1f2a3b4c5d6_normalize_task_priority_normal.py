"""Normalize task priority medium -> normal.

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c0
Create Date: 2026-04-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d4e5f6a7b8c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text("UPDATE orchestrator_tasks SET priority = 'normal' WHERE priority = 'medium'")
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE orchestrator_tasks SET priority = 'medium' WHERE priority = 'normal'")
    )
