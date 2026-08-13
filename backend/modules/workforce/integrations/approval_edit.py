"""Provider-neutral orchestration for replacing an approved-action draft."""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.modules.audit.repository import AuditRepository
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.orchestration.tool_execution_context import arguments_hash
from backend.modules.workforce.integrations.approval_delivery import ApprovalDeliveryService
from backend.modules.workforce.integrations.email import email_action_arguments_hash
from backend.modules.workforce.integrations.gmail import GmailAdapter
from backend.modules.workforce.models import (
    ApprovalDelivery,
    DraftExecutionMetadata,
    WorkflowRun,
)


async def replace_email_approval_draft(
    db: AsyncSession,
    *,
    owner_id: str,
    approval_id: str,
    changes: dict[str, Any],
) -> ApprovalRequest:
    result = await db.execute(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.requested_by_user_id == owner_id,
        )
        .with_for_update()
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise ValueError("Approval request not found")
    if approval.status != "pending":
        raise ValueError("Only a pending approval can be edited")

    payload = dict(approval.payload_json or {})
    draft_arguments = dict(payload.get("draft_arguments") or {})
    installation_id = str(draft_arguments.get("connector_installation_id") or "")
    draft_id = str(draft_arguments.get("gmail_draft_id") or "")
    if not installation_id or not draft_id:
        raise ValueError("Approval is not bound to a Gmail draft")

    for key in ("subject", "to", "cc", "bcc"):
        if key in changes:
            draft_arguments[key] = changes[key]
    if "body_text" in changes:
        draft_arguments["body"] = str(changes["body_text"])
        draft_arguments["body_text"] = str(changes["body_text"])
    elif "body" in changes:
        draft_arguments["body"] = str(changes["body"])
        draft_arguments["body_text"] = str(changes["body"])

    gmail = await GmailAdapter.for_owner(
        db,
        owner_id=owner_id,
        installation_id=installation_id,
    )
    await gmail.execute("gmail.update_draft", draft_arguments)

    metadata_result = await db.execute(
        select(DraftExecutionMetadata).where(
            DraftExecutionMetadata.owner_id == owner_id,
            DraftExecutionMetadata.connector_installation_id == installation_id,
            DraftExecutionMetadata.provider_draft_id == draft_id,
        )
    )
    metadata = metadata_result.scalar_one_or_none()
    if metadata is None:
        raise ValueError("Draft execution metadata missing")
    metadata.content_hash = email_action_arguments_hash(draft_arguments)
    metadata.draft_version += 1
    metadata.status = "current"

    now = datetime.now(UTC)
    approval.status = "invalidated"
    approval.reason = "Draft edited; replacement approval created"
    approval.resolved_at = now
    payload["invalidated_by_edit"] = True
    approval.payload_json = payload
    flag_modified(approval, "payload_json")

    replacement_payload = {
        **payload,
        "arguments_hash": arguments_hash(draft_arguments),
        "draft_arguments": draft_arguments,
        "replaces_approval_request_id": approval.id,
    }
    replacement = ApprovalRequest(
        id=str(uuid4()),
        project_id=approval.project_id,
        task_id=approval.task_id,
        run_id=approval.run_id,
        requested_by_user_id=owner_id,
        approval_type=approval.approval_type,
        status="pending",
        reason="Approve the revised Gmail draft",
        payload_json=replacement_payload,
    )
    db.add(replacement)
    await db.flush()

    deliveries_result = await db.execute(
        select(ApprovalDelivery).where(ApprovalDelivery.approval_request_id == approval.id)
    )
    telegram_installation_ids: set[str] = set()
    for delivery in deliveries_result.scalars().all():
        delivery.status = "invalidated"
        delivery.responded_at = now
        if delivery.channel == "telegram":
            telegram_installation_ids.add(delivery.connector_installation_id)

    workflow_run_id = str(replacement_payload.get("workflow_run_id") or "")
    if workflow_run_id:
        workflow = await db.get(WorkflowRun, workflow_run_id)
        if workflow is None or str(workflow.created_by or "") != owner_id:
            raise ValueError("Approval workflow ownership mismatch")
        context = dict(workflow.context_json or {})
        variables = dict(context.get("vars") or {})
        variables["pending_approval_request_id"] = replacement.id
        pending_tool = dict(variables.get("pending_tool") or {})
        pending_tool["approval_request_id"] = replacement.id
        pending_tool["params"] = draft_arguments
        variables["pending_tool"] = pending_tool
        context["vars"] = variables
        workflow.context_json = context
        flag_modified(workflow, "context_json")

    await AuditRepository(db).log(
        "orchestration.approval.edited",
        user_id=owner_id,
        resource_type="approval_request",
        resource_id=replacement.id,
        metadata={
            "replaces_approval_request_id": approval.id,
            "connector_installation_id": installation_id,
            "draft_version": metadata.draft_version,
        },
    )
    await db.commit()
    await db.refresh(replacement)

    for telegram_installation_id in telegram_installation_ids:
        with suppress(Exception):
            await ApprovalDeliveryService(db).deliver_telegram(
                approval_request_id=replacement.id,
                connector_installation_id=telegram_installation_id,
            )
    return replacement
