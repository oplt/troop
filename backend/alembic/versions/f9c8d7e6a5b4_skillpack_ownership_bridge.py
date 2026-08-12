"""Corrective migration for SkillPack ownership after e8a1c2d3f4b5 rewrite.

Revision ID: f9c8d7e6a5b4
Revises: e8a1c2d3f4b5
Create Date: 2026-08-12 20:40:00.000000

Freeze e8a1c2d3f4b5 as-applied. This revision:
- adds an ownership bridge for packs whose owner was invented (modal owner)
- tolerates skills_json already decoded as list/dict by the DB driver
"""

from __future__ import annotations

from collections.abc import Sequence
import json
import uuid

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "f9c8d7e6a5b4"
down_revision: str | Sequence[str] | None = "e8a1c2d3f4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.keys())
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return []
        return _as_list(parsed)
    return []


def upgrade() -> None:
    op.create_table(
        "skill_pack_ownership_bridge",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("skill_pack_id", sa.String(), nullable=True),
        sa.Column("skill_pack_slug", sa.String(length=255), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=True),
        sa.Column("inferred_owner_id", sa.String(), nullable=True),
        sa.Column("ownership_status", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_skill_pack_ownership_bridge_slug",
        "skill_pack_ownership_bridge",
        ["skill_pack_slug"],
    )

    connection = op.get_bind()
    # Skip if skill_packs table is gone
    has_packs = connection.execute(
        text("SELECT to_regclass('skill_packs') IS NOT NULL")
    ).scalar()
    if not has_packs:
        return

    agents = connection.execute(
        text("SELECT owner_id, skills_json FROM agent_profiles")
    ).fetchall()
    slug_to_owners: dict[str, set[str]] = {}
    for owner_id, skills_json in agents:
        for item in _as_list(skills_json):
            slug = str(item).strip()
            if not slug:
                continue
            slug_to_owners.setdefault(slug, set()).add(str(owner_id))

    packs = connection.execute(
        text("SELECT id, slug, name FROM skill_packs")
    ).fetchall()
    for pack_id, slug, name in packs:
        owners = slug_to_owners.get(str(slug), set())
        skill_row = connection.execute(
            text(
                "SELECT id, owner_id FROM skills WHERE legacy_skill_pack_id = :pid LIMIT 1"
            ),
            {"pid": pack_id},
        ).fetchone()
        skill_id = skill_row[0] if skill_row else None
        current_owner = skill_row[1] if skill_row else None

        if owners:
            status = "referenced"
            reason = "At least one agent skills_json references this pack slug"
            inferred = sorted(owners)[0]
            evidence = {"referencing_owners": sorted(owners)}
            # If current owner is not among referencers, flag uncertain
            if current_owner and current_owner not in owners:
                status = "ownership_uncertain"
                reason = (
                    "Skill owner does not match any agent that references the pack; "
                    "kept as-is and recorded for manual reconciliation"
                )
                inferred = current_owner
        else:
            status = "unreferenced_system"
            reason = (
                "No agent references this pack; ownership was previously invented. "
                "Recorded for system/organization reconciliation — not reassigned automatically."
            )
            inferred = current_owner
            evidence = {"pack_name": name}

        connection.execute(
            text(
                """
                INSERT INTO skill_pack_ownership_bridge
                (id, skill_pack_id, skill_pack_slug, skill_id, inferred_owner_id, ownership_status, reason, evidence_json)
                VALUES (:id, :pack_id, :slug, :skill_id, :owner, :status, :reason, CAST(:evidence AS json))
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pack_id": pack_id,
                "slug": slug,
                "skill_id": skill_id,
                "owner": inferred,
                "status": status,
                "reason": reason,
                "evidence": json.dumps(evidence if owners else {"pack_name": name}),
            },
        )


def downgrade() -> None:
    op.drop_index("ix_skill_pack_ownership_bridge_slug", table_name="skill_pack_ownership_bridge")
    op.drop_table("skill_pack_ownership_bridge")
