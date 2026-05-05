"""widen episodic_search_index.source_id for task:run composite

Revision ID: e2b7c4d1a0f3
Revises: c1a8fcb8c9aa
Create Date: 2026-04-20 19:30:00.000000

task_id + ':' + run_id can be 73 chars (two UUIDs); VARCHAR(64) caused flush errors.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e2b7c4d1a0f3"
down_revision: str | Sequence[str] | None = "c1a8fcb8c9aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "episodic_search_index",
        "source_id",
        existing_type=sa.String(length=64),
        type_=sa.String(length=128),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "episodic_search_index",
        "source_id",
        existing_type=sa.String(length=128),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
