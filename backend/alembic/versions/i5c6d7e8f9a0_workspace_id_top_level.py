"""Add workspace_id to top-level tenant tables (RBAC-001C).

Revision ID: i5c6d7e8f9a0
Revises: h4b5c6d7e8f0
Create Date: 2026-08-14 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from backend.modules.identity_access.workspace_fk_migration import (
    WORKSPACE_COMPOSITE_INDEXES,
    direct_backfill_sql,
    null_workspace_count_sql,
    workspace_fk_targets,
)
from sqlalchemy import text

from alembic import op

revision: str = "i5c6d7e8f9a0"
down_revision: str | Sequence[str] | None = "h4b5c6d7e8f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_workspace_id(table_name: str) -> None:
    op.add_column(table_name, sa.Column("workspace_id", sa.String(), nullable=True))
    op.create_foreign_key(
        f"fk_{table_name}_workspace_id_workspaces",
        table_name,
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(f"ix_{table_name}_workspace_id", table_name, ["workspace_id"], unique=False)


def _drop_workspace_id(table_name: str) -> None:
    op.drop_index(f"ix_{table_name}_workspace_id", table_name=table_name)
    op.drop_constraint(f"fk_{table_name}_workspace_id_workspaces", table_name, type_="foreignkey")
    op.drop_column(table_name, "workspace_id")


def _assert_zero_null_workspace_ids(bind, table_name: str) -> None:
    null_count = bind.execute(text(null_workspace_count_sql(table_name))).scalar_one()
    if null_count:
        raise RuntimeError(
            f"RBAC-001C backfill incomplete for {table_name}: "
            f"{null_count} row(s) still have NULL workspace_id"
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    targets = workspace_fk_targets()

    for target in targets:
        columns = {col["name"] for col in inspector.get_columns(target.table_name)}
        if target.owner_column not in columns:
            raise RuntimeError(
                f"RBAC-001C cannot backfill {target.table_name}: "
                f"owner column {target.owner_column!r} does not exist"
            )
        if "workspace_id" not in columns:
            _add_workspace_id(target.table_name)

    for target in targets:
        bind.execute(text(direct_backfill_sql(table_name=target.table_name, owner_column=target.owner_column)))

    for target in targets:
        _assert_zero_null_workspace_ids(bind, target.table_name)
        op.alter_column(target.table_name, "workspace_id", existing_type=sa.String(), nullable=False)

    for index_name, table_name, columns, postgresql_ops in WORKSPACE_COMPOSITE_INDEXES:
        op.create_index(
            index_name,
            table_name,
            list(columns),
            unique=False,
            postgresql_ops=postgresql_ops,
        )


def downgrade() -> None:
    for index_name, table_name, _columns, _ops in reversed(WORKSPACE_COMPOSITE_INDEXES):
        op.drop_index(index_name, table_name=table_name)

    for target in reversed(workspace_fk_targets()):
        _drop_workspace_id(target.table_name)
