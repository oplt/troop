"""Teams identity bindings for approval actor mapping."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p1q2r3s4t5u6"
down_revision = "o0p1q2r3s4t5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams_identity_bindings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=True),
        sa.Column("connector_installation_id", sa.String(), nullable=False),
        sa.Column("teams_tenant_id", sa.String(length=64), nullable=True),
        sa.Column("teams_user_id", sa.String(length=64), nullable=True),
        sa.Column("conversation_id", sa.String(length=255), nullable=True),
        sa.Column("teams_username", sa.String(length=255), nullable=True),
        sa.Column("link_token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connector_installation_id"], ["connector_installations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connector_installation_id",
            "teams_user_id",
            name="uq_teams_bindings_installation_user",
        ),
        sa.UniqueConstraint("link_token_hash", name="uq_teams_bindings_link_token_hash"),
    )
    op.create_index(
        op.f("ix_teams_identity_bindings_connector_installation_id"),
        "teams_identity_bindings",
        ["connector_installation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teams_identity_bindings_owner_id"),
        "teams_identity_bindings",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_teams_identity_bindings_teams_user_id"),
        "teams_identity_bindings",
        ["teams_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_teams_bindings_owner_status",
        "teams_identity_bindings",
        ["owner_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_teams_bindings_expiry",
        "teams_identity_bindings",
        ["token_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_teams_bindings_expiry", table_name="teams_identity_bindings")
    op.drop_index("ix_teams_bindings_owner_status", table_name="teams_identity_bindings")
    op.drop_index(
        op.f("ix_teams_identity_bindings_teams_user_id"),
        table_name="teams_identity_bindings",
    )
    op.drop_index(
        op.f("ix_teams_identity_bindings_owner_id"),
        table_name="teams_identity_bindings",
    )
    op.drop_index(
        op.f("ix_teams_identity_bindings_connector_installation_id"),
        table_name="teams_identity_bindings",
    )
    op.drop_table("teams_identity_bindings")
