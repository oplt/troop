"""add provider health and model matrix

Revision ID: 9f8d7c6b5a4e
Revises: 541e4ef0710e
Create Date: 2026-04-13 10:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9f8d7c6b5a4e"
down_revision: str | Sequence[str] | None = "541e4ef0710e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_configs",
        sa.Column("last_healthcheck_latency_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "provider_configs",
        sa.Column("is_healthy", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "model_capabilities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("model_slug", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("supports_tools", sa.Boolean(), nullable=False),
        sa.Column("supports_vision", sa.Boolean(), nullable=False),
        sa.Column("max_context_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_per_1k_input", sa.Float(), nullable=False),
        sa.Column("cost_per_1k_output", sa.Float(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_model_capabilities_provider_type"),
        "model_capabilities",
        ["provider_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_capabilities_model_slug"),
        "model_capabilities",
        ["model_slug"],
        unique=False,
    )
    op.alter_column("provider_configs", "is_healthy", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_model_capabilities_model_slug"), table_name="model_capabilities")
    op.drop_index(op.f("ix_model_capabilities_provider_type"), table_name="model_capabilities")
    op.drop_table("model_capabilities")
    op.drop_column("provider_configs", "is_healthy")
    op.drop_column("provider_configs", "last_healthcheck_latency_ms")
