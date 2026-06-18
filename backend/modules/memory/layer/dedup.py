from __future__ import annotations

import hashlib


def content_hash(text: str) -> str:
    normalized = " ".join((text or "").strip().lower().split())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def is_duplicate(existing_hashes: set[str], candidate: str) -> bool:
    return content_hash(candidate) in existing_hashes
