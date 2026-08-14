"""Slack identity bindings for approval actor mapping."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "o0p1q2r3s4t5"
down_revision = "n9o0p1q2r3s4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_identity_bindings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=True),
        sa.Column("connector_installation_id", sa.String(), nullable=False),
        sa.Column("slack_team_id", sa.String(length=64), nullable=True),
        sa.Column("slack_user_id", sa.String(length=64), nullable=True),
        sa.Column("slack_channel_id", sa.String(length=64), nullable=True),
        sa.Column("slack_username", sa.String(length=255), nullable=True),
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
            "slack_user_id",
            name="uq_slack_bindings_installation_user",
        ),
        sa.UniqueConstraint("link_token_hash", name="uq_slack_bindings_link_token_hash"),
    )
    op.create_index(
        op.f("ix_slack_identity_bindings_connector_installation_id"),
        "slack_identity_bindings",
        ["connector_installation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_slack_identity_bindings_owner_id"),
        "slack_identity_bindings",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_slack_identity_bindings_slack_user_id"),
        "slack_identity_bindings",
        ["slack_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_slack_bindings_owner_status",
        "slack_identity_bindings",
        ["owner_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_slack_bindings_expiry",
        "slack_identity_bindings",
        ["token_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_slack_bindings_expiry", table_name="slack_identity_bindings")
    op.drop_index("ix_slack_bindings_owner_status", table_name="slack_identity_bindings")
    op.drop_index(
        op.f("ix_slack_identity_bindings_slack_user_id"),
        table_name="slack_identity_bindings",
    )
    op.drop_index(
        op.f("ix_slack_identity_bindings_owner_id"),
        table_name="slack_identity_bindings",
    )
    op.drop_index(
        op.f("ix_slack_identity_bindings_connector_installation_id"),
        table_name="slack_identity_bindings",
    )
    op.drop_table("slack_identity_bindings")
