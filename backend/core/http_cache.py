from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from fastapi import Request, Response

from backend.core.config import settings


def _document_row_fingerprint(row: Any) -> str:
    updated = getattr(row, "updated_at", None) or getattr(row, "created_at", None)
    updated_token = updated.isoformat() if isinstance(updated, datetime) else str(updated or "")
    chunk_count = getattr(row, "chunk_count", "")
    ingestion_status = getattr(row, "ingestion_status", "")
    return f"{row.id}:{updated_token}:{chunk_count}:{ingestion_status}"


def compute_documents_etag(rows: list[Any]) -> str:
    parts = sorted(_document_row_fingerprint(row) for row in rows)
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f'W/"{digest}"'


def apply_private_list_cache_headers(response: Response, etag: str) -> None:
    max_age = max(0, settings.CACHE_HTTP_DOCUMENT_LIST_MAX_AGE_SECONDS)
    response.headers["Cache-Control"] = f"private, max-age={max_age}, must-revalidate"
    response.headers["ETag"] = etag


def maybe_not_modified(request: Request, response: Response, etag: str) -> bool:
    apply_private_list_cache_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        response.status_code = 304
        return True
    return False
