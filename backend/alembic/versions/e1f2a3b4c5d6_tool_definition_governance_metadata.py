"""Add governance metadata columns to tool_definitions and backfill native tools.

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-08-14 14:15:00.000000
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tool_definitions",
        sa.Column("side_effect", sa.String(length=32), nullable=False, server_default="read"),
    )
    op.add_column(
        "tool_definitions",
        sa.Column("reversibility", sa.String(length=32), nullable=False, server_default="none"),
    )
    op.add_column(
        "tool_definitions",
        sa.Column(
            "data_sensitivity",
            sa.String(length=32),
            nullable=False,
            server_default="internal",
        ),
    )
    op.add_column(
        "tool_definitions",
        sa.Column("parallel_safe", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "tool_definitions",
        sa.Column(
            "idempotency_strategy",
            sa.String(length=64),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        "tool_definitions",
        sa.Column(
            "commit_check_strategy",
            sa.String(length=64),
            nullable=False,
            server_default="none",
        ),
    )

    from backend.modules.workforce.action_metadata import native_tool_governance_rows

    bind = op.get_bind()
    for slug, governance in native_tool_governance_rows():
        gov = governance.to_dict()
        bind.execute(
            text(
                """
                UPDATE tool_definitions
                SET side_effect = :side_effect,
                    reversibility = :reversibility,
                    data_sensitivity = :data_sensitivity,
                    parallel_safe = :parallel_safe,
                    idempotency_strategy = :idempotency_strategy,
                    commit_check_strategy = :commit_check_strategy,
                    metadata_json = COALESCE(metadata_json, '{}'::json)::jsonb
                        || jsonb_build_object('governance', CAST(:governance_json AS jsonb))
                WHERE slug = :slug
                """
            ),
            {
                "slug": slug,
                "side_effect": gov["side_effect"],
                "reversibility": gov["reversibility"],
                "data_sensitivity": gov["data_sensitivity"],
                "parallel_safe": gov["parallel_safe"],
                "idempotency_strategy": gov["idempotency_strategy"],
                "commit_check_strategy": gov["commit_check_strategy"],
                "governance_json": json.dumps(gov),
            },
        )

    op.alter_column("tool_definitions", "side_effect", server_default=None)
    op.alter_column("tool_definitions", "reversibility", server_default=None)
    op.alter_column("tool_definitions", "data_sensitivity", server_default=None)
    op.alter_column("tool_definitions", "parallel_safe", server_default=None)
    op.alter_column("tool_definitions", "idempotency_strategy", server_default=None)
    op.alter_column("tool_definitions", "commit_check_strategy", server_default=None)


def downgrade() -> None:
    op.drop_column("tool_definitions", "commit_check_strategy")
    op.drop_column("tool_definitions", "idempotency_strategy")
    op.drop_column("tool_definitions", "parallel_safe")
    op.drop_column("tool_definitions", "data_sensitivity")
    op.drop_column("tool_definitions", "reversibility")
    op.drop_column("tool_definitions", "side_effect")
