"""Add team_templates table.

Revision ID: j1k2l3m4n5o6
Revises: f5a6b7c8d9e0
Create Date: 2026-04-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j1k2l3m4n5o6"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_templates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(length=255), nullable=False),
        sa.Column("roles_json", sa.JSON(), nullable=False),
        sa.Column("tools_json", sa.JSON(), nullable=False),
        sa.Column("autonomy", sa.String(length=64), nullable=False),
        sa.Column("visibility", sa.String(length=64), nullable=False),
        sa.Column("agent_template_slugs_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_team_templates_slug"), "team_templates", ["slug"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_team_templates_slug"), table_name="team_templates")
    op.drop_table("team_templates")
