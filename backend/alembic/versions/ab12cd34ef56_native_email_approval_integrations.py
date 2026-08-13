"""native email and external approval integration primitives

Revision ID: ab12cd34ef56
Revises: a1b2c3d4e5f6
Create Date: 2026-08-12 23:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ab12cd34ef56"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "connector_operations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "connector_definition_id",
            sa.String(),
            sa.ForeignKey("connector_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("input_schema_json", sa.JSON(), nullable=False),
        sa.Column("output_schema_json", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("required_scopes_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "connector_definition_id",
            "slug",
            name="uq_connector_operations_definition_slug",
        ),
    )
    op.create_index(
        "ix_connector_operations_definition",
        "connector_operations",
        ["connector_definition_id"],
    )
    op.create_index("ix_connector_operations_slug", "connector_operations", ["slug"])
    op.create_index(
        "ix_connector_operations_type_active",
        "connector_operations",
        ["operation_type", "is_active"],
    )

    op.create_table(
        "connector_oauth_states",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.String(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("encrypted_code_verifier", sa.Text(), nullable=False),
        sa.Column("requested_scopes_json", sa.JSON(), nullable=False),
        sa.Column("redirect_after", sa.String(length=1000), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("state_hash", name="uq_connector_oauth_states_state_hash"),
    )
    op.create_index(
        "ix_connector_oauth_states_owner_provider",
        "connector_oauth_states",
        ["owner_id", "provider"],
    )
    op.create_index("ix_connector_oauth_states_company", "connector_oauth_states", ["company_id"])
    op.create_index("ix_connector_oauth_states_expiry", "connector_oauth_states", ["expires_at"])

    op.create_table(
        "trigger_subscriptions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.String(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "connector_installation_id",
            sa.String(),
            sa.ForeignKey("connector_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_id",
            sa.String(),
            sa.ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_version_id",
            sa.String(),
            sa.ForeignKey("workflow_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_id", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_subscription_id", sa.String(length=512), nullable=True),
        sa.Column("external_cursor", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "workflow_version_id",
            "node_id",
            "connector_installation_id",
            name="uq_trigger_subscriptions_version_node_installation",
        ),
    )
    for name in (
        "owner_id",
        "company_id",
        "connector_installation_id",
        "workflow_id",
        "workflow_version_id",
        "provider",
    ):
        op.create_index(f"ix_trigger_subscriptions_{name}", "trigger_subscriptions", [name])
    op.create_index(
        "ix_trigger_subscriptions_status_expiry",
        "trigger_subscriptions",
        ["status", "expires_at"],
    )

    op.create_table(
        "external_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.String(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column(
            "connector_installation_id",
            sa.String(),
            sa.ForeignKey("connector_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_event_id", sa.String(length=512), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "workflow_run_id",
            sa.String(),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint("provider", "dedupe_key", name="uq_external_events_provider_dedupe"),
    )
    for name in (
        "owner_id",
        "company_id",
        "provider",
        "connector_installation_id",
        "event_type",
        "workflow_run_id",
    ):
        op.create_index(f"ix_external_events_{name}", "external_events", [name])
    op.create_index(
        "ix_external_events_status_received", "external_events", ["status", "received_at"]
    )

    op.create_table(
        "approval_deliveries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.String(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "approval_request_id",
            sa.String(),
            sa.ForeignKey("approval_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column(
            "connector_installation_id",
            sa.String(),
            sa.ForeignKey("connector_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("destination_id", sa.String(length=255), nullable=False),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "approval_request_id",
            "channel",
            "connector_installation_id",
            "destination_id",
            name="uq_approval_deliveries_target",
        ),
    )
    for name in (
        "owner_id",
        "company_id",
        "approval_request_id",
        "channel",
        "connector_installation_id",
    ):
        op.create_index(f"ix_approval_deliveries_{name}", "approval_deliveries", [name])
    op.create_index(
        "ix_approval_deliveries_status_created",
        "approval_deliveries",
        ["status", "created_at"],
    )

    op.create_table(
        "telegram_identity_bindings",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.String(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "connector_installation_id",
            sa.String(),
            sa.ForeignKey("connector_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_user_id", sa.String(length=64), nullable=True),
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=True),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("link_token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint(
            "connector_installation_id",
            "telegram_user_id",
            name="uq_telegram_bindings_installation_user",
        ),
        sa.UniqueConstraint("link_token_hash", name="uq_telegram_bindings_link_token_hash"),
    )
    op.create_index(
        "ix_telegram_bindings_owner_status",
        "telegram_identity_bindings",
        ["owner_id", "status"],
    )
    op.create_index("ix_telegram_bindings_company", "telegram_identity_bindings", ["company_id"])
    op.create_index(
        "ix_telegram_bindings_installation",
        "telegram_identity_bindings",
        ["connector_installation_id"],
    )
    op.create_index("ix_telegram_bindings_user", "telegram_identity_bindings", ["telegram_user_id"])
    op.create_index(
        "ix_telegram_bindings_expiry", "telegram_identity_bindings", ["token_expires_at"]
    )

    op.create_table(
        "approval_interactions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "approval_request_id",
            sa.String(),
            sa.ForeignKey("approval_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "approval_delivery_id",
            sa.String(),
            sa.ForeignKey("approval_deliveries.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("telegram_user_id", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("expected_input", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "approval_request_id",
            "telegram_user_id",
            "mode",
            name="uq_approval_interactions_approval_user_mode",
        ),
    )
    for name in (
        "owner_id",
        "approval_request_id",
        "approval_delivery_id",
        "telegram_user_id",
    ):
        op.create_index(f"ix_approval_interactions_{name}", "approval_interactions", [name])
    op.create_index(
        "ix_approval_interactions_status_expiry",
        "approval_interactions",
        ["status", "expires_at"],
    )

    op.create_table(
        "draft_execution_metadata",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.String(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "connector_installation_id",
            sa.String(),
            sa.ForeignKey("connector_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_run_id",
            sa.String(),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("workflow_node_id", sa.String(length=255), nullable=True),
        sa.Column("provider_draft_id", sa.String(length=512), nullable=False),
        sa.Column("message_id", sa.String(length=512), nullable=True),
        sa.Column("thread_id", sa.String(length=512), nullable=True),
        sa.Column("thread_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("draft_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint(
            "connector_installation_id",
            "provider_draft_id",
            name="uq_draft_execution_installation_provider_draft",
        ),
    )
    for name in (
        "owner_id",
        "company_id",
        "connector_installation_id",
        "workflow_run_id",
        "content_hash",
    ):
        op.create_index(f"ix_draft_execution_{name}", "draft_execution_metadata", [name])
    op.create_index(
        "ix_draft_execution_status_updated",
        "draft_execution_metadata",
        ["status", "updated_at"],
    )

    op.create_table(
        "external_action_executions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connector_installation_id",
            sa.String(),
            sa.ForeignKey("connector_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_run_id",
            sa.String(),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approval_request_id",
            sa.String(),
            sa.ForeignKey("approval_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action_key", sa.String(length=255), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("external_result_id", sa.String(length=512), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("idempotency_key", name="uq_external_action_executions_key"),
    )
    for name in (
        "owner_id",
        "connector_installation_id",
        "workflow_run_id",
        "approval_request_id",
        "action_key",
    ):
        op.create_index(
            f"ix_external_action_executions_{name}", "external_action_executions", [name]
        )
    op.create_index(
        "ix_external_action_executions_status_created",
        "external_action_executions",
        ["status", "created_at"],
    )


def downgrade() -> None:
    for table in (
        "external_action_executions",
        "draft_execution_metadata",
        "approval_interactions",
        "telegram_identity_bindings",
        "approval_deliveries",
        "external_events",
        "trigger_subscriptions",
        "connector_oauth_states",
        "connector_operations",
    ):
        op.drop_table(table)
