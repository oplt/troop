"""enforce unique slug for agent templates

Revision ID: 9f2d1b8c4e77
Revises: f4bdbfb299ae
Create Date: 2026-04-20 13:20:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f2d1b8c4e77"
down_revision: str | Sequence[str] | None = "f4bdbfb299ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY slug
                    ORDER BY created_at DESC, id DESC
                ) AS row_num
            FROM agent_templates
        )
        DELETE FROM agent_templates AS t
        USING ranked AS r
        WHERE t.id = r.id
          AND r.row_num > 1
        """
    )
    op.drop_index("ix_agent_templates_slug", table_name="agent_templates")
    op.create_index("ix_agent_templates_slug", "agent_templates", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_agent_templates_slug", table_name="agent_templates")
    op.create_index("ix_agent_templates_slug", "agent_templates", ["slug"], unique=False)
