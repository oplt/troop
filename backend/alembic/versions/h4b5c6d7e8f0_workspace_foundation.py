"""Add workspaces + workspace_memberships and backfill default tenant per user.

Revision ID: h4b5c6d7e8f0
Revises: g3a4b5c6d7e8
Create Date: 2026-08-14 17:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "h4b5c6d7e8f0"
down_revision: str | Sequence[str] | None = "g3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "workspaces" not in existing_tables:
        op.create_table(
            "workspaces",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("owner_user_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("slug", sa.String(length=64), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("settings_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("owner_user_id", "slug", name="uq_workspaces_owner_slug"),
        )
        op.create_index("ix_workspaces_owner_user_id", "workspaces", ["owner_user_id"])
        op.create_index("ix_workspaces_slug", "workspaces", ["slug"])
        op.create_index("ix_workspaces_is_default", "workspaces", ["is_default"])

    workspace_indexes = {idx["name"] for idx in inspector.get_indexes("workspaces")}
    if "uq_workspaces_one_default_per_owner" not in workspace_indexes:
        op.create_index(
            "uq_workspaces_one_default_per_owner",
            "workspaces",
            ["owner_user_id"],
            unique=True,
            postgresql_where=sa.text("is_default = true"),
        )

    if "workspace_memberships" not in existing_tables:
        op.create_table(
            "workspace_memberships",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("workspace_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("role", sa.String(length=32), nullable=False, server_default="owner"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("invited_by_user_id", sa.String(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "workspace_id", "user_id", name="uq_workspace_memberships_workspace_user"
            ),
        )
        op.create_index("ix_workspace_memberships_workspace_id", "workspace_memberships", ["workspace_id"])
        op.create_index("ix_workspace_memberships_user_id", "workspace_memberships", ["user_id"])
        op.create_index("ix_workspace_memberships_role", "workspace_memberships", ["role"])
        op.create_index("ix_workspace_memberships_status", "workspace_memberships", ["status"])
        op.create_index(
            "ix_workspace_memberships_invited_by_user_id",
            "workspace_memberships",
            ["invited_by_user_id"],
        )

    from backend.modules.identity_access.workspace_backfill import (
        default_workspace_name,
        default_workspace_slug,
    )

    bind = op.get_bind()
    now = datetime.now(UTC)
    users = bind.execute(text("SELECT id, email, full_name FROM users")).mappings().all()
    for row in users:
        user_id = str(row["id"])
        existing = bind.execute(
            text(
                """
                SELECT id FROM workspaces
                WHERE owner_user_id = :owner_user_id AND is_default = true
                LIMIT 1
                """
            ),
            {"owner_user_id": user_id},
        ).first()
        if existing is not None:
            continue
        workspace_id = str(uuid4())
        membership_id = str(uuid4())
        name = default_workspace_name(email=str(row["email"] or ""), full_name=row["full_name"])
        slug = default_workspace_slug()
        bind.execute(
            text(
                """
                INSERT INTO workspaces (
                    id, owner_user_id, name, slug, is_default, settings_json, created_at, updated_at
                ) VALUES (
                    :id, :owner_user_id, :name, :slug, true, '{}'::json, :now, :now
                )
                """
            ),
            {
                "id": workspace_id,
                "owner_user_id": user_id,
                "name": name,
                "slug": slug,
                "now": now,
            },
        )
        bind.execute(
            text(
                """
                INSERT INTO workspace_memberships (
                    id, workspace_id, user_id, role, status, metadata_json, created_at, updated_at
                ) VALUES (
                    :id, :workspace_id, :user_id, 'owner', 'active', '{}'::json, :now, :now
                )
                """
            ),
            {
                "id": membership_id,
                "workspace_id": workspace_id,
                "user_id": user_id,
                "now": now,
            },
        )

    op.alter_column("workspaces", "is_default", server_default=None)
    op.alter_column("workspace_memberships", "role", server_default=None)
    op.alter_column("workspace_memberships", "status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_workspace_memberships_invited_by_user_id", table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_status", table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_role", table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_user_id", table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_workspace_id", table_name="workspace_memberships")
    op.drop_table("workspace_memberships")
    op.drop_index("uq_workspaces_one_default_per_owner", table_name="workspaces")
    op.drop_index("ix_workspaces_is_default", table_name="workspaces")
    op.drop_index("ix_workspaces_slug", table_name="workspaces")
    op.drop_index("ix_workspaces_owner_user_id", table_name="workspaces")
    op.drop_table("workspaces")
