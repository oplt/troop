"""Canonical governance metadata for native tools and action policies.

Risk level and approval decision remain on ToolDefinition (requires_approval,
risk_level) and ActionPolicy (decision, risk_level). This module holds the
extended governance dimensions shared across catalog, DB rows, and policy resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG


class SideEffect(StrEnum):
    READ = "read"
    INTERNAL_MUTATING = "internal_mutating"
    EXTERNAL_MUTATING = "external_mutating"


class IdempotencyStrategy(StrEnum):
    NONE = "none"
    APPROVAL_DEDUP_ONLY = "approval_dedup_only"
    APPROVAL_PAYLOAD_GUARD = "approval_payload_guard"
    DURABLE_CLAIM = "durable_claim"


class Reversibility(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"


class DataSensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class CommitCheckStrategy(StrEnum):
    NONE = "none"
    APPROVAL_PAYLOAD_HASH = "approval_payload_hash"
    RESOURCE_FINGERPRINT = "resource_fingerprint"
    DURABLE_CLAIM = "durable_claim"
    APPROVAL_AND_FINGERPRINT = "approval_and_fingerprint"


@dataclass(frozen=True, slots=True)
class ActionGovernanceMetadata:
    side_effect: SideEffect
    reversibility: Reversibility
    data_sensitivity: DataSensitivity
    parallel_safe: bool
    idempotency_strategy: IdempotencyStrategy
    commit_check_strategy: CommitCheckStrategy

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "side_effect": self.side_effect.value,
            "reversibility": self.reversibility.value,
            "data_sensitivity": self.data_sensitivity.value,
            "parallel_safe": self.parallel_safe,
            "idempotency_strategy": self.idempotency_strategy.value,
            "commit_check_strategy": self.commit_check_strategy.value,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> ActionGovernanceMetadata:
        return cls(
            side_effect=SideEffect(str(raw.get("side_effect") or SideEffect.READ)),
            reversibility=Reversibility(str(raw.get("reversibility") or Reversibility.NONE)),
            data_sensitivity=DataSensitivity(
                str(raw.get("data_sensitivity") or DataSensitivity.INTERNAL)
            ),
            parallel_safe=bool(raw.get("parallel_safe", False)),
            idempotency_strategy=IdempotencyStrategy(
                str(raw.get("idempotency_strategy") or IdempotencyStrategy.NONE)
            ),
            commit_check_strategy=CommitCheckStrategy(
                str(raw.get("commit_check_strategy") or CommitCheckStrategy.NONE)
            ),
        )


def _commit_check_for(
    slug: str,
    *,
    side_effect: SideEffect,
    idempotency: IdempotencyStrategy,
) -> CommitCheckStrategy:
    if idempotency == IdempotencyStrategy.DURABLE_CLAIM:
        if slug in {
            "gmail.send_draft",
            "outlook.send_draft",
            "google_calendar.create_event",
            "google_calendar.update_event",
            "google_calendar.cancel_event",
            "microsoft_calendar.create_event",
            "microsoft_calendar.update_event",
            "microsoft_calendar.cancel_event",
            "jira.create_issue",
            "jira.update_issue",
            "jira.add_comment",
            "linear.create_issue",
            "linear.update_issue",
            "linear.add_comment",
            "hubspot.update_contact",
            "hubspot.create_note",
            "hubspot.send_email",
            "salesforce.update_contact",
            "salesforce.create_task",
            "salesforce.send_email",
            "slack.post_message",
            "teams.post_message",
        }:
            return CommitCheckStrategy.APPROVAL_AND_FINGERPRINT
        return CommitCheckStrategy.DURABLE_CLAIM
    if idempotency == IdempotencyStrategy.APPROVAL_DEDUP_ONLY:
        return CommitCheckStrategy.APPROVAL_PAYLOAD_HASH
    if idempotency == IdempotencyStrategy.APPROVAL_PAYLOAD_GUARD:
        return CommitCheckStrategy.APPROVAL_PAYLOAD_HASH
    if side_effect == SideEffect.READ:
        return CommitCheckStrategy.NONE
    return CommitCheckStrategy.NONE


def _reversibility_for(slug: str, side_effect: SideEffect) -> Reversibility:
    if side_effect == SideEffect.READ:
        return Reversibility.FULL
    if slug in {"gmail.create_draft", "gmail.update_draft", "outlook.create_draft", "outlook.update_draft", "fs_write"}:
        return Reversibility.PARTIAL
    return Reversibility.NONE


def _data_sensitivity_for(slug: str) -> DataSensitivity:
    if slug.startswith(("gmail.", "outlook.", "google_calendar.", "microsoft_calendar.", "jira.", "linear.", "hubspot.", "salesforce.")):
        return DataSensitivity.CONFIDENTIAL
    if slug.startswith("telegram."):
        return DataSensitivity.CONFIDENTIAL
    if slug.startswith("slack."):
        return DataSensitivity.CONFIDENTIAL
    if slug.startswith("teams."):
        return DataSensitivity.CONFIDENTIAL
    if slug in {"db_query", "knowledge_search", "repo_search"}:
        return DataSensitivity.CONFIDENTIAL
    if slug in {"web_search", "web_fetch"}:
        return DataSensitivity.PUBLIC
    if slug.startswith("github_"):
        return DataSensitivity.INTERNAL
    if slug.startswith("fs_") or slug == "code_execute":
        return DataSensitivity.INTERNAL
    return DataSensitivity.INTERNAL


def _parallel_safe_for(slug: str, side_effect: SideEffect) -> bool:
    if side_effect == SideEffect.READ:
        return True
    return slug == "telegram.answer_callback"


def _governance_from_inventory(slug: str) -> ActionGovernanceMetadata | None:
    from backend.modules.orchestration.external_effect_inventory import (
        get_external_effect_contract,
    )

    contract = get_external_effect_contract(slug)
    if contract is None:
        return None
    side_effect = SideEffect(contract.side_effect)
    idempotency = IdempotencyStrategy(contract.idempotency_strategy)
    return ActionGovernanceMetadata(
        side_effect=side_effect,
        reversibility=_reversibility_for(slug, side_effect),
        data_sensitivity=_data_sensitivity_for(slug),
        parallel_safe=_parallel_safe_for(slug, side_effect),
        idempotency_strategy=idempotency,
        commit_check_strategy=_commit_check_for(
            slug,
            side_effect=side_effect,
            idempotency=idempotency,
        ),
    )


# Abstract action keys used in DEFAULT_ACTION_POLICIES without ToolDefinition rows.
_ABSTRACT_ACTION_GOVERNANCE: dict[str, ActionGovernanceMetadata] = {
    "knowledge_read": ActionGovernanceMetadata(
        side_effect=SideEffect.READ,
        reversibility=Reversibility.FULL,
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
        parallel_safe=True,
        idempotency_strategy=IdempotencyStrategy.NONE,
        commit_check_strategy=CommitCheckStrategy.NONE,
    ),
    "external_email_send": ActionGovernanceMetadata(
        side_effect=SideEffect.EXTERNAL_MUTATING,
        reversibility=Reversibility.NONE,
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
        parallel_safe=False,
        idempotency_strategy=IdempotencyStrategy.NONE,
        commit_check_strategy=CommitCheckStrategy.NONE,
    ),
    "social_publish": ActionGovernanceMetadata(
        side_effect=SideEffect.EXTERNAL_MUTATING,
        reversibility=Reversibility.NONE,
        data_sensitivity=DataSensitivity.PUBLIC,
        parallel_safe=False,
        idempotency_strategy=IdempotencyStrategy.NONE,
        commit_check_strategy=CommitCheckStrategy.NONE,
    ),
    "ad_budget_change": ActionGovernanceMetadata(
        side_effect=SideEffect.EXTERNAL_MUTATING,
        reversibility=Reversibility.PARTIAL,
        data_sensitivity=DataSensitivity.RESTRICTED,
        parallel_safe=False,
        idempotency_strategy=IdempotencyStrategy.NONE,
        commit_check_strategy=CommitCheckStrategy.NONE,
    ),
    "delete_record": ActionGovernanceMetadata(
        side_effect=SideEffect.INTERNAL_MUTATING,
        reversibility=Reversibility.NONE,
        data_sensitivity=DataSensitivity.CONFIDENTIAL,
        parallel_safe=False,
        idempotency_strategy=IdempotencyStrategy.NONE,
        commit_check_strategy=CommitCheckStrategy.NONE,
    ),
    "merge_pull_request": ActionGovernanceMetadata(
        side_effect=SideEffect.EXTERNAL_MUTATING,
        reversibility=Reversibility.NONE,
        data_sensitivity=DataSensitivity.INTERNAL,
        parallel_safe=False,
        idempotency_strategy=IdempotencyStrategy.NONE,
        commit_check_strategy=CommitCheckStrategy.NONE,
    ),
    "shell_destructive_action": ActionGovernanceMetadata(
        side_effect=SideEffect.INTERNAL_MUTATING,
        reversibility=Reversibility.NONE,
        data_sensitivity=DataSensitivity.RESTRICTED,
        parallel_safe=False,
        idempotency_strategy=IdempotencyStrategy.NONE,
        commit_check_strategy=CommitCheckStrategy.NONE,
    ),
    "invoke_specialist": ActionGovernanceMetadata(
        side_effect=SideEffect.INTERNAL_MUTATING,
        reversibility=Reversibility.NONE,
        data_sensitivity=DataSensitivity.INTERNAL,
        parallel_safe=False,
        idempotency_strategy=IdempotencyStrategy.NONE,
        commit_check_strategy=CommitCheckStrategy.NONE,
    ),
}


def governance_for_action_key(action_key: str) -> ActionGovernanceMetadata:
    """Resolve governance metadata for a catalog slug or abstract policy key."""
    key = str(action_key or "").strip()
    if not key:
        return ActionGovernanceMetadata(
            side_effect=SideEffect.EXTERNAL_MUTATING,
            reversibility=Reversibility.NONE,
            data_sensitivity=DataSensitivity.INTERNAL,
            parallel_safe=False,
            idempotency_strategy=IdempotencyStrategy.NONE,
            commit_check_strategy=CommitCheckStrategy.NONE,
        )
    if key in _ABSTRACT_ACTION_GOVERNANCE:
        return _ABSTRACT_ACTION_GOVERNANCE[key]
    from_inventory = _governance_from_inventory(key)
    if from_inventory is not None:
        return from_inventory
    if key.startswith("mcp."):
        return ActionGovernanceMetadata(
            side_effect=SideEffect.EXTERNAL_MUTATING,
            reversibility=Reversibility.NONE,
            data_sensitivity=DataSensitivity.CONFIDENTIAL,
            parallel_safe=False,
            idempotency_strategy=IdempotencyStrategy.NONE,
            commit_check_strategy=CommitCheckStrategy.NONE,
        )
    if key.startswith("a2a."):
        return ActionGovernanceMetadata(
            side_effect=SideEffect.EXTERNAL_MUTATING,
            reversibility=Reversibility.NONE,
            data_sensitivity=DataSensitivity.CONFIDENTIAL,
            parallel_safe=False,
            idempotency_strategy=IdempotencyStrategy.NONE,
            commit_check_strategy=CommitCheckStrategy.NONE,
        )
    return ActionGovernanceMetadata(
        side_effect=SideEffect.EXTERNAL_MUTATING,
        reversibility=Reversibility.NONE,
        data_sensitivity=DataSensitivity.INTERNAL,
        parallel_safe=False,
        idempotency_strategy=IdempotencyStrategy.NONE,
        commit_check_strategy=CommitCheckStrategy.APPROVAL_PAYLOAD_HASH,
    )


def native_tool_governance_rows() -> list[tuple[str, ActionGovernanceMetadata]]:
    rows: list[tuple[str, ActionGovernanceMetadata]] = []
    for item in NATIVE_TOOL_CATALOG:
        slug = str(item["slug"])
        rows.append((slug, governance_for_action_key(slug)))
    return rows


def governance_metadata_json(action_key: str) -> dict:
    """Snapshot for ActionPolicy.metadata_json['governance']."""
    return {"governance": governance_for_action_key(action_key).to_dict()}


def default_action_policies_with_governance() -> list[dict]:
    """DEFAULT_ACTION_POLICIES rows enriched with canonical governance metadata."""
    from backend.modules.workforce.constants import DEFAULT_ACTION_POLICIES

    return [
        {**row, **governance_metadata_json(str(row["action_key"]))}
        for row in DEFAULT_ACTION_POLICIES
    ]


def assert_native_catalog_has_governance() -> None:
    missing = [
        slug
        for slug, _ in native_tool_governance_rows()
        if _governance_from_inventory(slug) is None
    ]
    if missing:
        raise AssertionError(f"native tools missing external-effect inventory: {missing}")
