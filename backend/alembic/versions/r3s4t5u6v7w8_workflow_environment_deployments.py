"""Workflow environment deployments and connector installation environment (ENV-001).

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
Create Date: 2026-08-14 22:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "r3s4t5u6v7w8"
down_revision: str | Sequence[str] | None = "q2r3s4t5u6v7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "connector_installations",
        sa.Column("environment", sa.String(length=32), nullable=False, server_default="dev"),
    )
    op.create_index(
        "ix_connector_installations_environment",
        "connector_installations",
        ["environment"],
        unique=False,
    )

    op.create_table(
        "workflow_environment_deployments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("workflow_version_id", sa.String(), nullable=False),
        sa.Column("connection_bindings_json", sa.JSON(), nullable=False),
        sa.Column("deployed_by", sa.String(), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["deployed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workflow_version_id"], ["workflow_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_id",
            "environment",
            name="uq_workflow_environment_deployments_workflow_env",
        ),
    )
    op.create_index(
        "ix_workflow_environment_deployments_workflow_id",
        "workflow_environment_deployments",
        ["workflow_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_environment_deployments_environment",
        "workflow_environment_deployments",
        ["environment"],
        unique=False,
    )

    op.create_table(
        "workflow_environment_deployment_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("workflow_version_id", sa.String(), nullable=False),
        sa.Column("connection_bindings_json", sa.JSON(), nullable=False),
        sa.Column("previous_version_id", sa.String(), nullable=True),
        sa.Column("previous_bindings_json", sa.JSON(), nullable=True),
        sa.Column("actor_user_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workflow_version_id"], ["workflow_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["previous_version_id"], ["workflow_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_environment_deployment_events_workflow_env",
        "workflow_environment_deployment_events",
        ["workflow_id", "environment"],
        unique=False,
    )

    bind = op.get_bind()
    bind.execute(
        text(
            """
            INSERT INTO workflow_environment_deployments (
                id,
                workflow_id,
                environment,
                workflow_version_id,
                connection_bindings_json,
                deployed_by,
                deployed_at,
                metadata_json
            )
            SELECT
                gen_random_uuid()::text,
                wd.id,
                'dev',
                wd.published_version_id,
                '{}'::json,
                NULL,
                NOW(),
                '{"source":"backfill"}'::json
            FROM workflow_definitions AS wd
            WHERE wd.published_version_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workflow_environment_deployment_events_workflow_env",
        table_name="workflow_environment_deployment_events",
    )
    op.drop_table("workflow_environment_deployment_events")
    op.drop_index(
        "ix_workflow_environment_deployments_environment",
        table_name="workflow_environment_deployments",
    )
    op.drop_index(
        "ix_workflow_environment_deployments_workflow_id",
        table_name="workflow_environment_deployments",
    )
    op.drop_table("workflow_environment_deployments")
    op.drop_index("ix_connector_installations_environment", table_name="connector_installations")
    op.drop_column("connector_installations", "environment")
