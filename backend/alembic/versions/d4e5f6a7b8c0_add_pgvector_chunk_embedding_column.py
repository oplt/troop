"""Add pgvector extension and embedding_vector on document chunks.

Revision ID: d4e5f6a7b8c0
Revises: c3d4e5f60718
Create Date: 2026-04-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c0"
# Merge branches: run_events/evals (b2c3…) and memory/knowledge (c3d4…).
down_revision: Union[str, tuple[str, str], None] = ("b2c3d4e5f6a7", "c3d4e5f60718")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    op.execute(
        sa.text("ALTER TABLE project_document_chunks ADD COLUMN IF NOT EXISTS embedding_vector vector(1536)")
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(sa.text("ALTER TABLE project_document_chunks DROP COLUMN IF EXISTS embedding_vector"))
