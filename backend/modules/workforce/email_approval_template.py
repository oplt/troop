"""Flagship email approval marketplace template (PROD-001A)."""

from __future__ import annotations

from typing import Any, Final

EMAIL_APPROVAL_FLAGSHIP_SLUG: Final[str] = "email-reply-telegram-approval"

EMAIL_APPROVAL_TEMPLATE_PACK: dict[str, Any] = {
    "flagship": True,
    "title": "Email approval automation",
    "summary": (
        "Gmail new message → classify → retrieve context → draft → deterministic checks → "
        "create draft → human approval → stale verification → send → audit."
    ),
    "requirements": {
        "connectors": ["gmail"],
        "optional_connectors": ["telegram"],
        "skill_slugs": ["email-response-drafter"],
    },
    "steps": [
        {
            "id": "trigger",
            "label": "Gmail new message",
            "actor": "system",
            "description": "Webhook trigger normalizes the inbound message and dedupes delivery.",
        },
        {
            "id": "normalize",
            "label": "Fetch thread",
            "actor": "deterministic",
            "description": "Loads the full Gmail thread with stable identifiers for later stale checks.",
        },
        {
            "id": "context",
            "label": "Retrieve company context",
            "actor": "deterministic",
            "description": "Knowledge search pulls relevant project/company facts before drafting.",
        },
        {
            "id": "classify",
            "label": "Classify + draft response",
            "actor": "ai",
            "description": (
                "The Email Response Drafter skill decides should_reply, category, confidence, "
                "and proposes subject/body with provenance."
            ),
        },
        {
            "id": "policy",
            "label": "Reply required?",
            "actor": "deterministic",
            "description": "Structured gate skips draft/send when the model recommends no reply.",
        },
        {
            "id": "create_draft",
            "label": "Create Gmail draft",
            "actor": "system",
            "description": "Persists the proposed reply as a provider draft before any send.",
        },
        {
            "id": "approve",
            "label": "Human approval",
            "actor": "human",
            "description": "Exact-effect approval in Troop (optional Telegram delivery). Edit-and-approve creates a new effect version.",
        },
        {
            "id": "stale_check",
            "label": "Stale thread + hash verification",
            "actor": "deterministic",
            "description": "Commit-time checks re-verify thread fingerprint, credentials, and draft hash.",
        },
        {
            "id": "send",
            "label": "Send Gmail message",
            "actor": "system",
            "description": "Idempotent send executes only after approval and passes stale checks.",
        },
        {
            "id": "audit",
            "label": "Audit receipt",
            "actor": "deterministic",
            "description": "HITL audit log and run ledger record the decision and provider receipt.",
        },
    ],
}


def flagship_email_approval_workflow() -> dict[str, Any]:
    return {
        "slug": EMAIL_APPROVAL_FLAGSHIP_SLUG,
        "name": "Email approval (flagship)",
        "category": "customer_success",
        "description": EMAIL_APPROVAL_TEMPLATE_PACK["summary"],
        "flagship": True,
        "template_pack": EMAIL_APPROVAL_TEMPLATE_PACK,
        "nodes": [
            {
                "id": "gmail_trigger",
                "type": "trigger",
                "label": "Gmail: new message",
                "config": {
                    "trigger_type": "gmail_new_message",
                    "connector_installation_id": "",
                },
            },
            {
                "id": "get_thread",
                "type": "tool",
                "label": "Fetch Gmail thread",
                "config": {
                    "tool_slug": "gmail.get_thread",
                    "params": {
                        "connector_installation_id": "$.email.connector_installation_id",
                        "thread_id": "$.email.thread_id",
                    },
                },
            },
            {
                "id": "fetch_context",
                "type": "tool",
                "label": "Retrieve company context",
                "config": {
                    "tool_slug": "knowledge_search",
                    "params": {
                        "query": "$.email.subject",
                        "limit": 5,
                    },
                },
            },
            {
                "id": "draft_skill",
                "type": "skill",
                "label": "Email Response Drafter",
                "config": {"skill_slug": "email-response-drafter"},
            },
            {"id": "draft_agent", "type": "agent", "label": "Classify + draft", "config": {}},
            {
                "id": "should_reply",
                "type": "condition",
                "label": "Reply required?",
                "config": {
                    "field": "should_reply",
                    "operator": "equals",
                    "value": True,
                },
            },
            {
                "id": "create_draft",
                "type": "tool",
                "label": "Create Gmail draft",
                "config": {
                    "tool_slug": "gmail.create_draft",
                    "params": {
                        "connector_installation_id": "$.email.connector_installation_id",
                        "thread_id": "$.email.thread_id",
                        "in_reply_to": "$.email.headers.message-id",
                        "to": {"$path": "email.from", "wrap_list": True},
                        "subject": "$.subject",
                        "body": "$.body_text",
                    },
                },
            },
            {
                "id": "send_draft",
                "type": "tool",
                "label": "Approve and send",
                "config": {
                    "tool_slug": "gmail.send_draft",
                    "params": {
                        "connector_installation_id": "$.email.connector_installation_id",
                        "gmail_draft_id": "$.tool_result_create_draft.output.id",
                        "thread_id": "$.email.thread_id",
                        "in_reply_to": "$.email.headers.message-id",
                        "to": {"$path": "email.from", "wrap_list": True},
                        "subject": "$.subject",
                        "body": "$.body_text",
                    },
                    "approval_delivery_channel": "in_app",
                    "approval_connector_installation_id": "",
                },
            },
        ],
        "edges": [
            {"from": "gmail_trigger", "to": "get_thread"},
            {"from": "get_thread", "to": "fetch_context"},
            {"from": "fetch_context", "to": "draft_skill"},
            {"from": "draft_skill", "to": "draft_agent"},
            {"from": "draft_agent", "to": "should_reply"},
            {"from": "should_reply", "to": "create_draft", "when": True},
            {"from": "create_draft", "to": "send_draft"},
        ],
        "entry_node_id": "gmail_trigger",
    }
