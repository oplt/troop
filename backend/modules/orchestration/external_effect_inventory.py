"""External-effect and idempotency contracts for mutating tool actions.

REL-001A inventory: every mutating native/GitHub/Gmail/Telegram/MCP/A2A action
must declare side-effect class, approval rule, idempotency strategy, ownership
check, and retry behavior. Actions without durable idempotency are blocked from
*new autonomous* use (approval-gated execution remains allowed).
"""

# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from backend.modules.workforce.action_metadata import IdempotencyStrategy, SideEffect


@dataclass(frozen=True, slots=True)
class ExternalEffectContract:
    action_key: str
    provider: str
    risk_level: str
    side_effect: SideEffect
    approval_rule: str
    idempotency_strategy: IdempotencyStrategy
    idempotency_detail: str
    ownership_check: str
    retry_behavior: str
    notes: str = ""

    @property
    def blocks_autonomous_use(self) -> bool:
        if self.side_effect == SideEffect.READ:
            return False
        return self.idempotency_strategy != IdempotencyStrategy.DURABLE_CLAIM


# Canonical inventory keyed by exact tool slug. Pattern families below extend this.
_EXTERNAL_EFFECT_CONTRACTS: dict[str, ExternalEffectContract] = {
    "invoke_specialist": ExternalEffectContract(
        action_key="invoke_specialist",
        provider="troop",
        risk_level="medium",
        side_effect=SideEffect.INTERNAL_MUTATING,
        approval_rule="Execution policy; limited to an active parent run and one nesting level",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Creates and executes a child run; parent invocation count bounds fan-out",
        ownership_check="Parent run ownership is inherited and rechecked by ExecutionService",
        retry_behavior="Do not retry automatically because a replay may create another child run",
    ),
    # --- Gmail ---
    "gmail.search_messages": ExternalEffectContract(
        action_key="gmail.search_messages",
        provider="gmail",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only; HTTP GET safe to retry",
        ownership_check="ConnectorInstallation.owner_id + active status",
        retry_behavior="Gmail adapter surfaces retryable GmailAPIError; no write retry",
    ),
    "gmail.get_message": ExternalEffectContract(
        action_key="gmail.get_message",
        provider="gmail",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only",
        ownership_check="ConnectorInstallation.owner_id + active status",
        retry_behavior="Safe GET retry via external_http policy",
    ),
    "gmail.get_thread": ExternalEffectContract(
        action_key="gmail.get_thread",
        provider="gmail",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only",
        ownership_check="ConnectorInstallation.owner_id + active status",
        retry_behavior="Safe GET retry via external_http policy",
    ),
    "gmail.create_draft": ExternalEffectContract(
        action_key="gmail.create_draft",
        provider="gmail",
        risk_level="medium",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="ActionPolicy default autonomous; catalog requires_approval=False",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Each call creates a new provider draft; DraftExecutionMetadata is post-hoc fingerprint only",
        ownership_check="ConnectorInstallation.owner_id + company scope",
        retry_behavior="No durable claim; Celery/workflow replay may create duplicate drafts",
        notes="BLOCKED from new autonomous use until REL-001B receipt/claim exists.",
    ),
    "gmail.update_draft": ExternalEffectContract(
        action_key="gmail.update_draft",
        provider="gmail",
        risk_level="medium",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Provider draft replace; content_hash updated after success only",
        ownership_check="ConnectorInstallation.owner_id + DraftExecutionMetadata row",
        retry_behavior="No durable claim; ambiguous replay may overwrite draft twice",
        notes="BLOCKED from new autonomous use.",
    ),
    "gmail.send_draft": ExternalEffectContract(
        action_key="gmail.send_draft",
        provider="gmail",
        risk_level="high",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="approval_required; consumed canonical ApprovalRequest + arguments_hash",
        idempotency_strategy=IdempotencyStrategy.DURABLE_CLAIM,
        idempotency_detail="ExternalActionExecution.idempotency_key UNIQUE (workflow_run:approval:draft:action) claimed before Gmail send",
        ownership_check="ConnectorInstallation.owner_id; approval owner match; DraftExecutionMetadata fingerprint + stale thread check",
        retry_behavior="IntegrityError → concurrent duplicate blocked; succeeded row returns cached result; ambiguous failure → outcome_unknown",
    ),
    "gmail.add_label": ExternalEffectContract(
        action_key="gmail.add_label",
        provider="gmail",
        risk_level="medium",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Gmail modify labels API; no Troop receipt",
        ownership_check="ConnectorInstallation.owner_id",
        retry_behavior="POST without idempotency key → single attempt per external_http policy",
        notes="BLOCKED from new autonomous use.",
    ),
    # --- Outlook Mail ---
    "outlook.search_messages": ExternalEffectContract(
        action_key="outlook.search_messages",
        provider="outlook",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only; Graph GET safe to retry",
        ownership_check="ConnectorInstallation.owner_id + active status",
        retry_behavior="Outlook adapter surfaces retryable OutlookAPIError; no write retry",
    ),
    "outlook.get_message": ExternalEffectContract(
        action_key="outlook.get_message",
        provider="outlook",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only",
        ownership_check="ConnectorInstallation.owner_id + active status",
        retry_behavior="Safe GET retry via external_http policy",
    ),
    "outlook.get_thread": ExternalEffectContract(
        action_key="outlook.get_thread",
        provider="outlook",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only",
        ownership_check="ConnectorInstallation.owner_id + active status",
        retry_behavior="Safe GET retry via external_http policy",
    ),
    "outlook.create_draft": ExternalEffectContract(
        action_key="outlook.create_draft",
        provider="outlook",
        risk_level="medium",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="ActionPolicy default autonomous; catalog requires_approval=False",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Each call creates a new provider draft; DraftExecutionMetadata is post-hoc fingerprint only",
        ownership_check="ConnectorInstallation.owner_id + company scope",
        retry_behavior="No durable claim; Celery/workflow replay may create duplicate drafts",
        notes="BLOCKED from new autonomous use until durable receipt exists.",
    ),
    "outlook.update_draft": ExternalEffectContract(
        action_key="outlook.update_draft",
        provider="outlook",
        risk_level="medium",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Provider draft replace; content_hash updated after success only",
        ownership_check="ConnectorInstallation.owner_id + DraftExecutionMetadata row",
        retry_behavior="No durable claim; ambiguous replay may overwrite draft twice",
        notes="BLOCKED from new autonomous use.",
    ),
    "outlook.send_draft": ExternalEffectContract(
        action_key="outlook.send_draft",
        provider="outlook",
        risk_level="high",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="approval_required; consumed canonical ApprovalRequest + arguments_hash",
        idempotency_strategy=IdempotencyStrategy.DURABLE_CLAIM,
        idempotency_detail="ExternalActionExecution.idempotency_key UNIQUE (workflow_run:approval:draft:action) claimed before Outlook send",
        ownership_check="ConnectorInstallation.owner_id; approval owner match; DraftExecutionMetadata fingerprint + stale thread check",
        retry_behavior="IntegrityError → concurrent duplicate blocked; succeeded row returns cached result; ambiguous failure → outcome_unknown",
    ),
    "outlook.add_label": ExternalEffectContract(
        action_key="outlook.add_label",
        provider="outlook",
        risk_level="medium",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Graph categories PATCH; no Troop receipt",
        ownership_check="ConnectorInstallation.owner_id",
        retry_behavior="PATCH without idempotency key → single attempt per external_http policy",
        notes="BLOCKED from new autonomous use.",
    ),
    # --- Google Calendar ---
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="google_calendar",
            risk_level="low",
            side_effect=SideEffect.READ,
            approval_rule="ActionPolicy default autonomous",
            idempotency_strategy=IdempotencyStrategy.NONE,
            idempotency_detail="Read-only calendar query",
            ownership_check="ConnectorInstallation.owner_id + active status",
            retry_behavior="Safe GET/POST read retry",
        )
        for slug in (
            "google_calendar.list_events",
            "google_calendar.get_event",
            "google_calendar.get_availability",
        )
    },
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="google_calendar",
            risk_level="medium" if "create" in slug or "update" in slug else "high",
            side_effect=SideEffect.EXTERNAL_MUTATING,
            approval_rule="approval_required",
            idempotency_strategy=IdempotencyStrategy.NONE,
            idempotency_detail="Calendar mutation without durable Troop receipt",
            ownership_check="ConnectorInstallation.owner_id",
            retry_behavior="Approval-gated single attempt per workflow step",
            notes="BLOCKED from new autonomous use.",
        )
        for slug in (
            "google_calendar.create_event",
            "google_calendar.update_event",
            "google_calendar.cancel_event",
        )
    },
    # --- Microsoft Calendar ---
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="microsoft_calendar",
            risk_level="low",
            side_effect=SideEffect.READ,
            approval_rule="ActionPolicy default autonomous",
            idempotency_strategy=IdempotencyStrategy.NONE,
            idempotency_detail="Read-only calendar query",
            ownership_check="ConnectorInstallation.owner_id + active status",
            retry_behavior="Safe GET/POST read retry",
        )
        for slug in (
            "microsoft_calendar.list_events",
            "microsoft_calendar.get_event",
            "microsoft_calendar.get_availability",
        )
    },
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="microsoft_calendar",
            risk_level="medium" if "create" in slug or "update" in slug else "high",
            side_effect=SideEffect.EXTERNAL_MUTATING,
            approval_rule="approval_required",
            idempotency_strategy=IdempotencyStrategy.NONE,
            idempotency_detail="Calendar mutation without durable Troop receipt",
            ownership_check="ConnectorInstallation.owner_id",
            retry_behavior="Approval-gated single attempt per workflow step",
            notes="BLOCKED from new autonomous use.",
        )
        for slug in (
            "microsoft_calendar.create_event",
            "microsoft_calendar.update_event",
            "microsoft_calendar.cancel_event",
        )
    },
    # --- Google Drive ---
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="google_drive",
            risk_level="low",
            side_effect=SideEffect.READ,
            approval_rule="ActionPolicy default autonomous",
            idempotency_strategy=IdempotencyStrategy.NONE,
            idempotency_detail="Read-only Drive query",
            ownership_check="ConnectorInstallation.owner_id + active status",
            retry_behavior="Safe GET retry",
        )
        for slug in (
            "google_drive.search_files",
            "google_drive.get_file_metadata",
            "google_drive.get_file_content",
        )
    },
    # --- Microsoft Drive ---
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="microsoft_drive",
            risk_level="low",
            side_effect=SideEffect.READ,
            approval_rule="ActionPolicy default autonomous",
            idempotency_strategy=IdempotencyStrategy.NONE,
            idempotency_detail="Read-only Graph drive query",
            ownership_check="ConnectorInstallation.owner_id + active status",
            retry_behavior="Safe GET retry",
        )
        for slug in (
            "microsoft_drive.search_files",
            "microsoft_drive.get_file_metadata",
            "microsoft_drive.get_file_content",
        )
    },
    # --- Jira ---
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="jira",
            risk_level="low",
            side_effect=SideEffect.READ,
            approval_rule="ActionPolicy default autonomous",
            idempotency_strategy=IdempotencyStrategy.NONE,
            idempotency_detail="Read-only Jira query",
            ownership_check="ConnectorInstallation.owner_id + active status",
            retry_behavior="Safe GET retry",
        )
        for slug in (
            "jira.search_issues",
            "jira.get_issue",
            "jira.get_issue_comments",
        )
    },
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="jira",
            risk_level="medium",
            side_effect=SideEffect.EXTERNAL_MUTATING,
            approval_rule="approval_required; consumed canonical ApprovalRequest + arguments_hash",
            idempotency_strategy=IdempotencyStrategy.DURABLE_CLAIM,
            idempotency_detail="ExternalActionExecution.idempotency_key UNIQUE per workflow approval",
            ownership_check="ConnectorInstallation.owner_id; approval owner match",
            retry_behavior="IntegrityError → concurrent duplicate blocked; succeeded row returns cached result",
        )
        for slug in ("jira.create_issue", "jira.update_issue", "jira.add_comment")
    },
    # --- Linear ---
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="linear",
            risk_level="low",
            side_effect=SideEffect.READ,
            approval_rule="ActionPolicy default autonomous",
            idempotency_strategy=IdempotencyStrategy.NONE,
            idempotency_detail="Read-only Linear GraphQL query",
            ownership_check="ConnectorInstallation.owner_id + active status",
            retry_behavior="Safe GraphQL read retry",
        )
        for slug in (
            "linear.search_issues",
            "linear.get_issue",
            "linear.get_issue_comments",
        )
    },
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="linear",
            risk_level="medium",
            side_effect=SideEffect.EXTERNAL_MUTATING,
            approval_rule="approval_required; consumed canonical ApprovalRequest + arguments_hash",
            idempotency_strategy=IdempotencyStrategy.DURABLE_CLAIM,
            idempotency_detail="ExternalActionExecution.idempotency_key UNIQUE per workflow approval",
            ownership_check="ConnectorInstallation.owner_id; approval owner match",
            retry_behavior="IntegrityError → concurrent duplicate blocked; succeeded row returns cached result",
        )
        for slug in ("linear.create_issue", "linear.update_issue", "linear.add_comment")
    },
    # --- HubSpot ---
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="hubspot",
            risk_level="low",
            side_effect=SideEffect.READ,
            approval_rule="ActionPolicy default autonomous",
            idempotency_strategy=IdempotencyStrategy.NONE,
            idempotency_detail="Read-only HubSpot CRM query",
            ownership_check="ConnectorInstallation.owner_id + active status",
            retry_behavior="Safe GET/POST search retry",
        )
        for slug in (
            "hubspot.search_contacts",
            "hubspot.get_contact",
            "hubspot.search_companies",
            "hubspot.get_company",
        )
    },
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="hubspot",
            risk_level="high" if slug == "hubspot.send_email" else "medium",
            side_effect=SideEffect.EXTERNAL_MUTATING,
            approval_rule="approval_required; consumed canonical ApprovalRequest + arguments_hash",
            idempotency_strategy=IdempotencyStrategy.DURABLE_CLAIM,
            idempotency_detail="ExternalActionExecution.idempotency_key UNIQUE per workflow approval",
            ownership_check="ConnectorInstallation.owner_id; allowlisted contact fields only for updates",
            retry_behavior="IntegrityError → concurrent duplicate blocked; succeeded row returns cached result",
        )
        for slug in ("hubspot.update_contact", "hubspot.create_note", "hubspot.send_email")
    },
    # --- Salesforce ---
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="salesforce",
            risk_level="low",
            side_effect=SideEffect.READ,
            approval_rule="ActionPolicy default autonomous",
            idempotency_strategy=IdempotencyStrategy.NONE,
            idempotency_detail="Read-only Salesforce SOQL/query",
            ownership_check="ConnectorInstallation.owner_id + active status",
            retry_behavior="Safe GET query retry",
        )
        for slug in (
            "salesforce.search_contacts",
            "salesforce.get_contact",
            "salesforce.search_accounts",
            "salesforce.get_account",
        )
    },
    **{
        slug: ExternalEffectContract(
            action_key=slug,
            provider="salesforce",
            risk_level="high" if slug == "salesforce.send_email" else "medium",
            side_effect=SideEffect.EXTERNAL_MUTATING,
            approval_rule="approval_required; consumed canonical ApprovalRequest + arguments_hash",
            idempotency_strategy=IdempotencyStrategy.DURABLE_CLAIM,
            idempotency_detail="ExternalActionExecution.idempotency_key UNIQUE per workflow approval",
            ownership_check="ConnectorInstallation.owner_id; allowlisted contact fields only for updates",
            retry_behavior="IntegrityError → concurrent duplicate blocked; succeeded row returns cached result",
        )
        for slug in ("salesforce.update_contact", "salesforce.create_task", "salesforce.send_email")
    },
    # --- Telegram ---
    "telegram.send_message": ExternalEffectContract(
        action_key="telegram.send_message",
        provider="telegram",
        risk_level="medium",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="ActionPolicy default autonomous; catalog requires_approval=False",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="sendMessage has no Troop durable key",
        ownership_check="ConnectorInstallation.owner_id + bot token from installation config",
        retry_behavior="Celery at-least-once may duplicate messages",
        notes="BLOCKED from new autonomous use.",
    ),
    "telegram.edit_message": ExternalEffectContract(
        action_key="telegram.edit_message",
        provider="telegram",
        risk_level="medium",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="editMessageText; no Troop receipt",
        ownership_check="ConnectorInstallation.owner_id",
        retry_behavior="Retry may re-apply same edit; still no durable claim",
        notes="BLOCKED from new autonomous use.",
    ),
    "telegram.answer_callback": ExternalEffectContract(
        action_key="telegram.answer_callback",
        provider="telegram",
        risk_level="low",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="answerCallbackQuery; Telegram rejects duplicate callback_id but Troop has no durable receipt",
        ownership_check="ConnectorInstallation.owner_id",
        retry_behavior="Provider may return error on duplicate; not durable at Troop boundary",
        notes="BLOCKED from new autonomous use.",
    ),
    # --- Slack ---
    "slack.search_messages": ExternalEffectContract(
        action_key="slack.search_messages",
        provider="slack",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only search/history scan",
        ownership_check="ConnectorInstallation.owner_id + active status",
        retry_behavior="Safe GET/search retry via external_http policy",
    ),
    "slack.get_thread": ExternalEffectContract(
        action_key="slack.get_thread",
        provider="slack",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only thread replies",
        ownership_check="ConnectorInstallation.owner_id + active status",
        retry_behavior="Safe GET retry",
    ),
    "slack.get_message": ExternalEffectContract(
        action_key="slack.get_message",
        provider="slack",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only message fetch",
        ownership_check="ConnectorInstallation.owner_id + active status",
        retry_behavior="Safe GET retry",
    ),
    "slack.post_message": ExternalEffectContract(
        action_key="slack.post_message",
        provider="slack",
        risk_level="high",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="approval_required; consumed canonical ApprovalRequest + arguments_hash",
        idempotency_strategy=IdempotencyStrategy.DURABLE_CLAIM,
        idempotency_detail="ExternalActionExecution.idempotency_key UNIQUE (workflow_run:approval:channel:thread:action)",
        ownership_check="ConnectorInstallation.owner_id; approval owner match; SlackIdentityBinding for channel approvals",
        retry_behavior="IntegrityError → concurrent duplicate blocked; succeeded row returns cached result",
    ),
    "slack.update_message": ExternalEffectContract(
        action_key="slack.update_message",
        provider="slack",
        risk_level="medium",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="ActionPolicy default autonomous; approval-channel feedback only",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="chat.update for approval UX; no Troop durable receipt",
        ownership_check="ConnectorInstallation.owner_id",
        retry_behavior="Retry may re-apply same edit",
        notes="BLOCKED from new autonomous use.",
    ),
    # --- Microsoft Teams ---
    "teams.search_messages": ExternalEffectContract(
        action_key="teams.search_messages",
        provider="teams",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only Graph search",
        ownership_check="ConnectorInstallation.owner_id + tenant match",
        retry_behavior="Safe search retry",
    ),
    "teams.get_thread": ExternalEffectContract(
        action_key="teams.get_thread",
        provider="teams",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only thread replies",
        ownership_check="ConnectorInstallation.owner_id + tenant match",
        retry_behavior="Safe GET retry",
    ),
    "teams.get_message": ExternalEffectContract(
        action_key="teams.get_message",
        provider="teams",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="ActionPolicy default autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only message fetch",
        ownership_check="ConnectorInstallation.owner_id + tenant match",
        retry_behavior="Safe GET retry",
    ),
    "teams.post_message": ExternalEffectContract(
        action_key="teams.post_message",
        provider="teams",
        risk_level="high",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="approval_required; consumed canonical ApprovalRequest + arguments_hash",
        idempotency_strategy=IdempotencyStrategy.DURABLE_CLAIM,
        idempotency_detail="ExternalActionExecution.idempotency_key UNIQUE (workflow_run:approval:conversation:reply:action)",
        ownership_check="ConnectorInstallation.owner_id; TeamsIdentityBinding tenant/user match",
        retry_behavior="IntegrityError → concurrent duplicate blocked; succeeded row returns cached result",
    ),
    "teams.update_message": ExternalEffectContract(
        action_key="teams.update_message",
        provider="teams",
        risk_level="medium",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="ActionPolicy default autonomous; approval-channel feedback only",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Graph message update for approval UX",
        ownership_check="ConnectorInstallation.owner_id",
        retry_behavior="Retry may re-apply same edit",
        notes="BLOCKED from new autonomous use.",
    ),
    # --- GitHub toolbox + API paths ---
    "github_comment": ExternalEffectContract(
        action_key="github_comment",
        provider="github",
        risk_level="medium",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="catalog requires_approval=True; HITL dangerous_tool_call grant OR github_comment approval API",
        idempotency_strategy=IdempotencyStrategy.APPROVAL_DEDUP_ONLY,
        idempotency_detail="github_outbound_dedup dedupes approval creation; API post uses posted_comment_id payload guard only",
        ownership_check="resolve_authorized_repository + issue_link; GithubConnection.owner_id (SEC-001)",
        retry_behavior="Toolbox POST: no retry; approval API: skip if posted_comment_id set",
        notes="BLOCKED from new autonomous use; provider replay not durable.",
    ),
    "github_label_issue": ExternalEffectContract(
        action_key="github_label_issue",
        provider="github",
        risk_level="medium",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="requires_approval=True; dangerous_tools HITL gate",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Direct GitHub labels API; no Troop receipt",
        ownership_check="resolve_authorized_repository + issue_link (SEC-001)",
        retry_behavior="POST without idempotency key",
        notes="BLOCKED from new autonomous use.",
    ),
    "github_create_pr": ExternalEffectContract(
        action_key="github_create_pr",
        provider="github",
        risk_level="high",
        side_effect=SideEffect.EXTERNAL_MUTATING,
        approval_rule="requires_approval=True; dangerous_tools HITL gate",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="GitHub create pull request; no Troop durable key",
        ownership_check="resolve_authorized_repository (SEC-001)",
        retry_behavior="POST without idempotency key",
        notes="BLOCKED from new autonomous use.",
    ),
    # --- Native workspace tools ---
    "fs_write": ExternalEffectContract(
        action_key="fs_write",
        provider="native",
        risk_level="high",
        side_effect=SideEffect.INTERNAL_MUTATING,
        approval_rule="requires_approval=True; dangerous_tools HITL when run_tool gate enabled",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Project-scoped path overwrite; no content-addressed receipt",
        ownership_check="OrchestratorProject-scoped _resolve_scoped_path",
        retry_behavior="Replay overwrites same path again",
        notes="BLOCKED from new autonomous use.",
    ),
    "code_execute": ExternalEffectContract(
        action_key="code_execute",
        provider="native",
        risk_level="high",
        side_effect=SideEffect.INTERNAL_MUTATING,
        approval_rule="requires_approval=True; dangerous_tools HITL",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Sandbox subprocess; side effects not keyed",
        ownership_check="Project/run scoped cpu_executor job",
        retry_behavior="No automatic retry; caller may re-run entire job",
        notes="BLOCKED from new autonomous use.",
    ),
    "db_query": ExternalEffectContract(
        action_key="db_query",
        provider="native",
        risk_level="critical",
        side_effect=SideEffect.READ,
        approval_rule="requires_approval=True (catalog); current implementation is SELECT-only",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only entities (tasks/runs/documents/artifacts) despite catalog wording",
        ownership_check="OrchestratorProject.id filter on all entities",
        retry_behavior="Safe read retry",
        notes="Not mutating today; any future write path must add durable idempotency before autonomous use.",
    ),
    # --- Read-only native (listed for completeness) ---
    "web_fetch": ExternalEffectContract(
        action_key="web_fetch",
        provider="native",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="GET-only via safe_outbound_request",
        ownership_check="Outbound URL allowlist (outbound_url service)",
        retry_behavior="Safe GET retry",
    ),
    "web_search": ExternalEffectContract(
        action_key="web_search",
        provider="native",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Read-only search",
        ownership_check="Provider API key scoped to deployment",
        retry_behavior="Provider-dependent",
    ),
    "knowledge_search": ExternalEffectContract(
        action_key="knowledge_search",
        provider="native",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Project document chunk retrieval",
        ownership_check="ProjectDocument.project_id == current project",
        retry_behavior="Safe read retry",
    ),
    "repo_search": ExternalEffectContract(
        action_key="repo_search",
        provider="native",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Linked repository search",
        ownership_check="Project-scoped repository linkage",
        retry_behavior="Safe read retry",
    ),
    "fs_read": ExternalEffectContract(
        action_key="fs_read",
        provider="native",
        risk_level="low",
        side_effect=SideEffect.READ,
        approval_rule="autonomous",
        idempotency_strategy=IdempotencyStrategy.NONE,
        idempotency_detail="Project-scoped filesystem read",
        ownership_check="OrchestratorProject-scoped _resolve_scoped_path",
        retry_behavior="Safe read retry",
    ),
}

_MCP_CONTRACT = ExternalEffectContract(
    action_key="mcp.*",
    provider="mcp",
    risk_level="high",
    side_effect=SideEffect.EXTERNAL_MUTATING,
    approval_rule="ActionPolicy default approval_required for unknown; MCPToolProvider estimate_risk=high",
    idempotency_strategy=IdempotencyStrategy.NONE,
    idempotency_detail="Dynamic MCP tool call; no Troop durable idempotency key before provider effect",
    ownership_check="ConnectorInstallation.owner_id; installation selected from owner MCP connectors",
    retry_behavior="MCPToolProvider returns failed status; Celery/workflow replay may duplicate writes",
    notes="BLOCKED from new autonomous use for all MCP tools until connector manifest idempotency (CONN-001).",
)

_A2A_CONTRACT = ExternalEffectContract(
    action_key="a2a.*",
    provider="a2a",
    risk_level="high",
    side_effect=SideEffect.EXTERNAL_MUTATING,
    approval_rule="a2a.send_task requires_approval=True; dynamic a2a.{id} inherits high risk",
    idempotency_strategy=IdempotencyStrategy.NONE,
    idempotency_detail="External agent task dispatch; no Troop receipt",
    ownership_check="ConnectorInstallation.owner_id for A2A installations",
    retry_behavior="Failed status returned; replay may duplicate external task",
    notes="BLOCKED from new autonomous use.",
)

_SMTP_EMAIL_CONTRACT = ExternalEffectContract(
    action_key="platform.smtp_send_email",
    provider="platform",
    risk_level="high",
    side_effect=SideEffect.EXTERNAL_MUTATING,
    approval_rule="Not exposed as agent tool; system transactional email only",
    idempotency_strategy=IdempotencyStrategy.NONE,
    idempotency_detail="workers.email.send_email; Celery queue is at-least-once without recipient+subject dedupe",
    ownership_check="N/A (system triggered)",
    retry_behavior="Celery redelivery may duplicate email",
    notes="Not in tool catalog; documented for REL-001B regression scope.",
)


def get_external_effect_contract(action_key: str) -> ExternalEffectContract | None:
    key = str(action_key or "").strip()
    if not key:
        return None
    if key in _EXTERNAL_EFFECT_CONTRACTS:
        return _EXTERNAL_EFFECT_CONTRACTS[key]
    if key.startswith("mcp."):
        return _MCP_CONTRACT
    if key.startswith("a2a."):
        return _A2A_CONTRACT
    return None


def list_external_effect_contracts() -> list[ExternalEffectContract]:
    return [
        *_EXTERNAL_EFFECT_CONTRACTS.values(),
        _MCP_CONTRACT,
        _A2A_CONTRACT,
        _SMTP_EMAIL_CONTRACT,
    ]


def list_autonomous_blocked_action_keys() -> frozenset[str]:
    blocked = {
        contract.action_key
        for contract in _EXTERNAL_EFFECT_CONTRACTS.values()
        if contract.blocks_autonomous_use
    }
    blocked.update({"mcp.*", "a2a.*"})
    return frozenset(blocked)


def is_autonomous_blocked(action_key: str) -> bool:
    contract = get_external_effect_contract(action_key)
    if contract is None:
        return False
    return contract.blocks_autonomous_use


def mutating_catalog_slugs() -> frozenset[str]:
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    slugs: set[str] = set()
    for item in NATIVE_TOOL_CATALOG:
        slug = str(item["slug"])
        contract = get_external_effect_contract(slug)
        if contract and contract.side_effect != SideEffect.READ:
            slugs.add(slug)
    return frozenset(slugs)


def assert_inventory_covers_mutating_catalog() -> None:
    """Raise AssertionError when a catalog mutator lacks a contract entry."""
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    missing: list[str] = []
    for item in NATIVE_TOOL_CATALOG:
        slug = str(item["slug"])
        contract = get_external_effect_contract(slug)
        if contract is None:
            missing.append(slug)
            continue
        if contract.side_effect != SideEffect.READ and slug not in _EXTERNAL_EFFECT_CONTRACTS:
            missing.append(slug)
    if missing:
        raise AssertionError(f"Missing external-effect contracts for: {', '.join(sorted(missing))}")


def contracts_blocking_autonomous() -> Iterable[ExternalEffectContract]:
    for contract in list_external_effect_contracts():
        if contract.blocks_autonomous_use:
            yield contract
