"""Provider-neutral email normalization and approval fingerprints."""

from __future__ import annotations

import base64
import hashlib
import html
import re
from datetime import UTC, datetime
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from backend.modules.orchestration.tool_execution_context import arguments_hash

_DANGEROUS_HTML = re.compile(
    r"<\s*(script|style|iframe|object|embed|form|meta|link)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_EVENT_ATTRIBUTE = re.compile(r"\s+on[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)
_UNSAFE_URI = re.compile(r"(?i)(href|src)\s*=\s*([\"'])\s*(?:javascript|data):.*?\2")
_TAG = re.compile(r"<[^>]+>")


def _decode_b64url(value: str | None) -> str:
    if not value:
        return ""
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode("utf-8", errors="replace")
    except (ValueError, UnicodeError):
        return ""


def sanitize_email_html(value: str | None) -> str:
    """Conservative sanitizer for rendering untrusted email HTML."""
    cleaned = _DANGEROUS_HTML.sub("", str(value or ""))
    cleaned = _EVENT_ATTRIBUTE.sub("", cleaned)
    cleaned = _UNSAFE_URI.sub(r'\1="#"', cleaned)
    return cleaned


def html_to_text(value: str | None) -> str:
    without_tags = _TAG.sub(" ", sanitize_email_html(value))
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _addresses(headers: dict[str, str], name: str) -> list[dict[str, str]]:
    return [
        {"name": display, "email": address.lower()}
        for display, address in getaddresses([headers.get(name, "")])
        if address
    ]


def _walk_parts(part: dict[str, Any]) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[dict[str, Any]] = []
    mime = str(part.get("mimeType") or "")
    body = dict(part.get("body") or {})
    filename = str(part.get("filename") or "")
    if filename or body.get("attachmentId"):
        attachments.append(
            {
                "filename": filename,
                "mime_type": mime,
                "size": int(body.get("size") or 0),
                "attachment_id": body.get("attachmentId"),
            }
        )
    elif mime == "text/plain":
        text_parts.append(_decode_b64url(body.get("data")))
    elif mime == "text/html":
        html_parts.append(sanitize_email_html(_decode_b64url(body.get("data"))))
    for child in part.get("parts") or []:
        child_text, child_html, child_attachments = _walk_parts(dict(child))
        text_parts.extend(child_text)
        html_parts.extend(child_html)
        attachments.extend(child_attachments)
    return text_parts, html_parts, attachments


def normalize_gmail_message(
    message: dict[str, Any],
    *,
    connector_installation_id: str,
) -> dict[str, Any]:
    payload = dict(message.get("payload") or {})
    headers = {
        str(item.get("name") or "").lower(): str(item.get("value") or "")
        for item in payload.get("headers") or []
        if item.get("name")
    }
    text_parts, html_parts, attachments = _walk_parts(payload)
    html_body = "\n".join(part for part in html_parts if part)
    text_body = "\n".join(part for part in text_parts if part) or html_to_text(html_body)
    received_at: datetime | None = None
    if message.get("internalDate"):
        try:
            received_at = datetime.fromtimestamp(int(message["internalDate"]) / 1000, tz=UTC)
        except (TypeError, ValueError, OSError):
            received_at = None
    if received_at is None and headers.get("date"):
        try:
            received_at = parsedate_to_datetime(headers["date"])
        except (TypeError, ValueError):
            received_at = None
    sender = _addresses(headers, "from")
    return {
        "provider": "gmail",
        "connector_installation_id": connector_installation_id,
        "message_id": str(message.get("id") or ""),
        "thread_id": str(message.get("threadId") or ""),
        "from": sender[0] if sender else {"name": "", "email": ""},
        "to": _addresses(headers, "to"),
        "cc": _addresses(headers, "cc"),
        "subject": headers.get("subject", ""),
        "text_body": text_body,
        "html_body": html_body,
        "received_at": received_at.isoformat() if received_at else None,
        "headers": {
            key: headers.get(key)
            for key in ("message-id", "in-reply-to", "references")
            if headers.get(key)
        },
        "attachments": attachments,
    }


def canonical_email_action_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Keep only security-sensitive send fields in a deterministic shape."""

    def normalize_addresses(value: Any) -> list[str]:
        raw = value if isinstance(value, list) else ([value] if value else [])
        normalized: list[str] = []
        for item in raw:
            address = item.get("email") if isinstance(item, dict) else item
            if address:
                normalized.append(str(address).strip().lower())
        return sorted(normalized)

    attachments = []
    for item in arguments.get("attachments") or []:
        if not isinstance(item, dict):
            continue
        attachments.append(
            {
                "attachment_id": str(item.get("attachment_id") or item.get("id") or ""),
                "filename": str(item.get("filename") or ""),
                "size": int(item.get("size") or 0),
            }
        )
    attachments.sort(key=lambda item: (item["attachment_id"], item["filename"], item["size"]))
    return {
        "provider": "gmail",
        "connector_installation_id": str(arguments.get("connector_installation_id") or ""),
        "gmail_draft_id": str(arguments.get("gmail_draft_id") or arguments.get("draft_id") or ""),
        "thread_id": str(arguments.get("thread_id") or ""),
        "in_reply_to": str(arguments.get("in_reply_to") or ""),
        "from": str(arguments.get("from") or "").strip().lower(),
        "to": normalize_addresses(arguments.get("to")),
        "cc": normalize_addresses(arguments.get("cc")),
        "bcc": normalize_addresses(arguments.get("bcc")),
        "subject": str(arguments.get("subject") or ""),
        "body": str(arguments.get("body") or arguments.get("body_text") or ""),
        "attachments": attachments,
    }


def email_action_arguments_hash(arguments: dict[str, Any]) -> str:
    return arguments_hash(canonical_email_action_arguments(arguments))


def thread_fingerprint(thread: dict[str, Any]) -> str:
    messages = [
        {
            "id": str(item.get("id") or ""),
            "history_id": str(item.get("historyId") or ""),
            "internal_date": str(item.get("internalDate") or ""),
        }
        for item in thread.get("messages") or []
        if "DRAFT" not in set(item.get("labelIds") or [])
    ]
    return arguments_hash({"thread_id": str(thread.get("id") or ""), "messages": messages})


def event_dedupe_key(provider: str, *parts: object) -> str:
    raw = "\x1f".join([provider, *(str(part) for part in parts)])
    return hashlib.sha256(raw.encode()).hexdigest()


def normalize_outlook_message(
    message: dict[str, Any],
    *,
    connector_installation_id: str,
) -> dict[str, Any]:
    sender = dict((message.get("from") or {}).get("emailAddress") or {})
    to_recipients = [
        {
            "name": str((item.get("emailAddress") or {}).get("name") or ""),
            "email": str((item.get("emailAddress") or {}).get("address") or "").lower(),
        }
        for item in message.get("toRecipients") or []
        if (item.get("emailAddress") or {}).get("address")
    ]
    cc_recipients = [
        {
            "name": str((item.get("emailAddress") or {}).get("name") or ""),
            "email": str((item.get("emailAddress") or {}).get("address") or "").lower(),
        }
        for item in message.get("ccRecipients") or []
        if (item.get("emailAddress") or {}).get("address")
    ]
    body = dict(message.get("body") or {})
    html_body = ""
    text_body = ""
    if str(body.get("contentType") or "").lower() == "html":
        html_body = sanitize_email_html(str(body.get("content") or ""))
        text_body = html_to_text(html_body)
    else:
        text_body = str(body.get("content") or "")
    received_at = message.get("receivedDateTime")
    attachments = [
        {
            "filename": str(item.get("name") or ""),
            "mime_type": str(item.get("contentType") or ""),
            "size": int(item.get("size") or 0),
            "attachment_id": str(item.get("id") or ""),
        }
        for item in message.get("attachments") or []
    ]
    return {
        "provider": "outlook",
        "connector_installation_id": connector_installation_id,
        "message_id": str(message.get("id") or ""),
        "thread_id": str(message.get("conversationId") or ""),
        "from": {
            "name": str(sender.get("name") or ""),
            "email": str(sender.get("address") or "").lower(),
        },
        "to": to_recipients,
        "cc": cc_recipients,
        "subject": str(message.get("subject") or ""),
        "text_body": text_body,
        "html_body": html_body,
        "received_at": str(received_at) if received_at else None,
        "headers": {
            key: message.get(key)
            for key in ("internetMessageId", "inReplyTo")
            if message.get(key)
        },
        "attachments": attachments,
    }


def canonical_outlook_email_action_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    canonical = canonical_email_action_arguments(
        {
            **arguments,
            "provider": "outlook",
            "gmail_draft_id": arguments.get("outlook_draft_id") or arguments.get("draft_id"),
        }
    )
    return {
        **canonical,
        "provider": "outlook",
        "outlook_draft_id": str(
            arguments.get("outlook_draft_id") or arguments.get("draft_id") or ""
        ),
    }


def outlook_email_action_arguments_hash(arguments: dict[str, Any]) -> str:
    return arguments_hash(canonical_outlook_email_action_arguments(arguments))


def outlook_thread_fingerprint(thread: dict[str, Any]) -> str:
    messages = [
        {
            "id": str(item.get("id") or ""),
            "last_modified": str(item.get("lastModifiedDateTime") or ""),
            "received_at": str(item.get("receivedDateTime") or ""),
        }
        for item in thread.get("value") or []
        if not item.get("isDraft")
    ]
    return arguments_hash(
        {
            "conversation_id": str(thread.get("conversation_id") or ""),
            "messages": messages,
        }
    )
