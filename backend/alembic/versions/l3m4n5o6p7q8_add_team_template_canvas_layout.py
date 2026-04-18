"""Add canvas layout JSON to team_templates.

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-04-18

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l3m4n5o6p7q8"
down_revision: Union[str, None] = "k2l3m4n5o6p7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "team_templates",
        sa.Column("canvas_layout_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.alter_column("team_templates", "canvas_layout_json", server_default=None)


def downgrade() -> None:
    op.drop_column("team_templates", "canvas_layout_json")
