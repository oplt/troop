"""Revision ID: t5u6v7w8x9y0
Revises: s4t5u6v7w8x9
Create Date: 2026-08-14 23:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "t5u6v7w8x9y0"
down_revision: str | Sequence[str] | None = "s4t5u6v7w8x9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_packages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("visibility", sa.String(length=32), nullable=False, server_default="private"),
        sa.Column("source_marketplace_slug", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_workspace_packages_workspace_slug"),
    )
    op.create_index("ix_workspace_packages_workspace_id", "workspace_packages", ["workspace_id"])
    op.create_index("ix_workspace_packages_owner_user_id", "workspace_packages", ["owner_user_id"])
    op.create_index("ix_workspace_packages_visibility", "workspace_packages", ["visibility"])

    op.create_table(
        "workspace_package_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("package_id", sa.String(), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("permission_manifest_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("trust_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("changelog", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["package_id"], ["workspace_packages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "package_id",
            "version_number",
            name="uq_workspace_package_versions_package_version",
        ),
    )
    op.create_index(
        "ix_workspace_package_versions_package_id",
        "workspace_package_versions",
        ["package_id"],
    )

    op.create_table(
        "workspace_package_installations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("package_id", sa.String(), nullable=False),
        sa.Column("installed_version_id", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("installed_by", sa.String(), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["installed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["installed_version_id"], ["workspace_package_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["package_id"], ["workspace_packages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "package_id",
            name="uq_workspace_package_installations_workspace_package",
        ),
    )
    op.create_index(
        "ix_workspace_package_installations_workspace_id",
        "workspace_package_installations",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_package_installations_workspace_id", "workspace_package_installations")
    op.drop_table("workspace_package_installations")
    op.drop_index("ix_workspace_package_versions_package_id", "workspace_package_versions")
    op.drop_table("workspace_package_versions")
    op.drop_index("ix_workspace_packages_visibility", "workspace_packages")
    op.drop_index("ix_workspace_packages_owner_user_id", "workspace_packages")
    op.drop_index("ix_workspace_packages_workspace_id", "workspace_packages")
    op.drop_table("workspace_packages")
