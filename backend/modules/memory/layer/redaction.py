from __future__ import annotations

import re
from typing import Literal

RedactionReason = Literal["blocked_pattern", "empty_after_redaction"]

# Patterns for secrets and sensitive material — never persist these as long-term memory.
_SENSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("api_key", re.compile(
        r"\b(sk-[A-Za-z0-9]{10,}|AKIA[0-9A-Z]{16}|api[_-]?key\s*[:=]\s*\S+)", re.I
    )),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*\b", re.I)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("password", re.compile(r"\b(password|passwd|pwd)\s*[:=]\s*\S+", re.I)),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("connection_string", re.compile(
        r"\b(postgres(?:ql)?|mysql|mongodb(\+srv)?|redis)://\S+", re.I
    )),
    ("env_var", re.compile(r"(?m)^(?:export\s+)?[A-Z][A-Z0-9_]{2,}\s*=\s*\S+")),
    ("github_token", re.compile(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]+\b")),
    ("aws_secret", re.compile(r"\b(?:AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16})\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
]

_REDACTION_REPLACEMENT = "[REDACTED]"


def contains_sensitive_content(text: str) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for _, pattern in _SENSITIVE_PATTERNS)


def redact_sensitive_content(text: str) -> tuple[str, list[str]]:
    """Return redacted text and list of matched sensitive categories."""
    if not text:
        return "", []
    redacted = text
    matched: list[str] = []
    for label, pattern in _SENSITIVE_PATTERNS:
        if pattern.search(redacted):
            matched.append(label)
            redacted = pattern.sub(_REDACTION_REPLACEMENT, redacted)
    return redacted.strip(), matched


def is_safe_to_store(text: str) -> tuple[bool, RedactionReason | None]:
    """Block storage when content is mostly sensitive or empty after redaction."""
    if not text or not text.strip():
        return False, "empty_after_redaction"

    if contains_sensitive_content(text):
        redacted, _ = redact_sensitive_content(text)
        # If almost everything was redacted, don't store at all.
        if not redacted or redacted.replace(_REDACTION_REPLACEMENT, "").strip() == "":
            return False, "blocked_pattern"
        # Partial redaction is OK if meaningful text remains.
        if len(redacted.replace(_REDACTION_REPLACEMENT, "").strip()) < 20:
            return False, "blocked_pattern"

    return True, None


def sanitize_for_storage(text: str) -> tuple[str | None, list[str]]:
    """Redact secrets; return None if nothing safe remains."""
    if not text or not text.strip():
        return None, []

    redacted, matched = redact_sensitive_content(text)
    if matched:
        meaningful = redacted.replace(_REDACTION_REPLACEMENT, "").strip()
        if len(meaningful) < 20:
            return None, matched

    safe, _reason = is_safe_to_store(redacted)
    if not safe:
        return None, matched
    return redacted, matched
