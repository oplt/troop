"""Enterprise SSO identity providers and audit workspace scoping (ENT-001).

Revision ID: s4t5u6v7w8x9
Revises: r3s4t5u6v7w8
Create Date: 2026-08-14 22:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "s4t5u6v7w8x9"
down_revision: str | Sequence[str] | None = "r3s4t5u6v7w8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("workspace_id", sa.String(), nullable=True))
    op.create_index("ix_audit_logs_workspace_id", "audit_logs", ["workspace_id"], unique=False)

    op.add_column("users", sa.Column("auth_provider", sa.String(length=32), server_default="local"))
    op.add_column("users", sa.Column("external_auth_only", sa.Boolean(), server_default=sa.false()))
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=True)

    op.create_table(
        "identity_providers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("secrets_ref", sa.String(length=255), nullable=True),
        sa.Column("scopes_json", sa.JSON(), nullable=False),
        sa.Column("domain_allowlist_json", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("enforce_sso", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_identity_providers_slug"),
    )
    op.create_index("ix_identity_providers_enabled", "identity_providers", ["enabled"], unique=False)

    op.create_table(
        "external_identities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("provider_id", sa.String(), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["identity_providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "subject", name="uq_external_identities_provider_subject"),
    )
    op.create_index("ix_external_identities_user_id", "external_identities", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_external_identities_user_id", table_name="external_identities")
    op.drop_table("external_identities")
    op.drop_index("ix_identity_providers_enabled", table_name="identity_providers")
    op.drop_table("identity_providers")
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=False)
    op.drop_column("users", "external_auth_only")
    op.drop_column("users", "auth_provider")
    op.drop_index("ix_audit_logs_workspace_id", table_name="audit_logs")
    op.drop_column("audit_logs", "workspace_id")
