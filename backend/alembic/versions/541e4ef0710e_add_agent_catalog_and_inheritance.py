"""add agent catalog and inheritance

Revision ID: 541e4ef0710e
Revises: 7b66139f1c4a
Create Date: 2026-04-12 22:15:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "541e4ef0710e"
down_revision: str | Sequence[str] | None = "7b66139f1c4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_profiles", sa.Column("parent_template_slug", sa.String(length=255), nullable=True))
    op.add_column("agent_profiles", sa.Column("skills_json", sa.JSON(), nullable=False, server_default="[]"))
    op.create_index(op.f("ix_agent_profiles_parent_template_slug"), "agent_profiles", ["parent_template_slug"], unique=False)

    op.create_table(
        "skill_packs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("allowed_tools_json", sa.JSON(), nullable=False),
        sa.Column("rules_markdown", sa.Text(), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_skill_packs_slug"), "skill_packs", ["slug"], unique=False)

    op.create_table(
        "agent_templates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_template_slug", sa.String(length=255), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("mission_markdown", sa.Text(), nullable=False),
        sa.Column("rules_markdown", sa.Text(), nullable=False),
        sa.Column("output_contract_markdown", sa.Text(), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("allowed_tools_json", sa.JSON(), nullable=False),
        sa.Column("skills_json", sa.JSON(), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("model_policy_json", sa.JSON(), nullable=False),
        sa.Column("budget_json", sa.JSON(), nullable=False),
        sa.Column("memory_policy_json", sa.JSON(), nullable=False),
        sa.Column("output_schema_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_templates_slug"), "agent_templates", ["slug"], unique=False)
    op.create_index(op.f("ix_agent_templates_parent_template_slug"), "agent_templates", ["parent_template_slug"], unique=False)

    op.alter_column("agent_profiles", "skills_json", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_templates_parent_template_slug"), table_name="agent_templates")
    op.drop_index(op.f("ix_agent_templates_slug"), table_name="agent_templates")
    op.drop_table("agent_templates")

    op.drop_index(op.f("ix_skill_packs_slug"), table_name="skill_packs")
    op.drop_table("skill_packs")

    op.drop_index(op.f("ix_agent_profiles_parent_template_slug"), table_name="agent_profiles")
    op.drop_column("agent_profiles", "skills_json")
    op.drop_column("agent_profiles", "parent_template_slug")
