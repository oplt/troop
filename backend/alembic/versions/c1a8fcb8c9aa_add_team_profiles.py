"""add team profiles table

Revision ID: c1a8fcb8c9aa
Revises: 9f2d1b8c4e77
Create Date: 2026-04-20 15:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1a8fcb8c9aa"
down_revision: str | Sequence[str] | None = "9f2d1b8c4e77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "team_profiles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("source_team_template_slug", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(length=255), nullable=False),
        sa.Column("roles_json", sa.JSON(), nullable=False),
        sa.Column("tools_json", sa.JSON(), nullable=False),
        sa.Column("autonomy", sa.String(length=64), nullable=False),
        sa.Column("visibility", sa.String(length=64), nullable=False),
        sa.Column("agent_template_slugs_json", sa.JSON(), nullable=False),
        sa.Column("canvas_layout_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_team_profiles_owner_id"), "team_profiles", ["owner_id"], unique=False)
    op.create_index(op.f("ix_team_profiles_slug"), "team_profiles", ["slug"], unique=False)
    op.create_index(
        op.f("ix_team_profiles_source_team_template_slug"),
        "team_profiles",
        ["source_team_template_slug"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_team_profiles_source_team_template_slug"), table_name="team_profiles")
    op.drop_index(op.f("ix_team_profiles_slug"), table_name="team_profiles")
    op.drop_index(op.f("ix_team_profiles_owner_id"), table_name="team_profiles")
    op.drop_table("team_profiles")
