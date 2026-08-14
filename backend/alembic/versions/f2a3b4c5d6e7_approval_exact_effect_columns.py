"""Add canonical exact-effect columns to approval_requests.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-14 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "approval_requests",
        sa.Column("effect_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "approval_requests",
        sa.Column("effect_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "approval_requests",
        sa.Column("precondition_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "approval_requests",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "approval_requests",
        sa.Column("proposed_effect_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_approval_requests_effect_hash",
        "approval_requests",
        ["effect_hash"],
        unique=False,
    )
    op.create_index(
        "ix_approval_requests_expires_at",
        "approval_requests",
        ["expires_at"],
        unique=False,
    )

    bind = op.get_bind()
    bind.execute(
        text(
            """
            UPDATE approval_requests
            SET effect_hash = COALESCE(
                    NULLIF(payload_json->>'effect_hash', ''),
                    NULLIF(payload_json->>'arguments_hash', '')
                ),
                effect_version = COALESCE(
                    NULLIF(payload_json->>'effect_version', '')::integer,
                    1
                ),
                precondition_fingerprint = NULLIF(payload_json->>'precondition_fingerprint', ''),
                expires_at = CASE
                    WHEN payload_json ? 'expires_at'
                         AND NULLIF(payload_json->>'expires_at', '') IS NOT NULL
                    THEN (payload_json->>'expires_at')::timestamptz
                    ELSE NULL
                END,
                proposed_effect_json = COALESCE(
                    payload_json->'proposed_effect',
                    payload_json->'draft_arguments'
                )
            WHERE payload_json IS NOT NULL
              AND (
                    payload_json ? 'arguments_hash'
                 OR payload_json ? 'effect_hash'
                 OR payload_json ? 'draft_arguments'
                 OR payload_json ? 'proposed_effect'
              )
            """
        )
    )

    op.alter_column("approval_requests", "effect_version", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_approval_requests_expires_at", table_name="approval_requests")
    op.drop_index("ix_approval_requests_effect_hash", table_name="approval_requests")
    op.drop_column("approval_requests", "proposed_effect_json")
    op.drop_column("approval_requests", "expires_at")
    op.drop_column("approval_requests", "precondition_fingerprint")
    op.drop_column("approval_requests", "effect_version")
    op.drop_column("approval_requests", "effect_hash")
