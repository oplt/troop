from __future__ import annotations

import hashlib
import json
import re
from html import unescape
from typing import Any

from backend.modules.rag.schemas import RagDocument, SourceType

PDF_UNSUPPORTED_DETAIL = (
    "PDF upload is not supported yet. Convert the document to plain text or Markdown "
    "before uploading, or paste the text via the document API."
)


def content_checksum(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def detect_source_type(content_type: str | None, filename: str | None) -> SourceType:
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    if name.endswith(".md") or "markdown" in ctype:
        return "markdown"
    if name.endswith(".json") or "json" in ctype:
        return "json"
    if name.endswith(".csv") or "csv" in ctype:
        return "csv"
    if name.endswith((".html", ".htm")) or "html" in ctype:
        return "html"
    if name.endswith((".py", ".ts", ".tsx", ".js", ".go", ".rs", ".java")):
        return "code"
    if name.endswith(".pdf") or "pdf" in ctype:
        return "pdf"
    return "text"


class DocumentParser:
    """Normalize supported source formats into plain text for indexing."""

    def parse(
        self,
        *,
        content: str | bytes,
        source_type: SourceType,
        title: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        meta = dict(metadata or {})
        text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content

        if source_type == "json":
            text, meta = self._parse_json(text, meta)
        elif source_type == "html":
            text = self._parse_html(text)
        elif source_type == "csv":
            text = self._parse_csv(text)
        elif source_type == "pdf":
            raise ValueError(PDF_UNSUPPORTED_DETAIL)
        elif source_type == "markdown":
            meta.setdefault("format", "markdown")

        return text.strip(), meta

    def normalize_document(
        self,
        *,
        document_id: str,
        source_id: str,
        source_type: SourceType,
        title: str,
        content: str | bytes,
        owner_user_id: str,
        project_id: str,
        workspace_id: str | None = None,
        visibility: str = "project",
        metadata: dict[str, Any] | None = None,
    ) -> RagDocument:
        parsed, meta = self.parse(
            content=content,
            source_type=source_type,
            title=title,
            metadata=metadata,
        )
        return RagDocument(
            document_id=document_id,
            source_id=source_id,
            source_type=source_type,
            title=title,
            content=parsed,
            owner_user_id=owner_user_id,
            project_id=project_id,
            workspace_id=workspace_id,
            visibility=visibility,
            metadata=meta,
            checksum=content_checksum(parsed),
        )

    def _parse_json(self, text: str, meta: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text, meta
        meta["json_root_type"] = type(payload).__name__
        return json.dumps(payload, indent=2, ensure_ascii=False), meta

    def _parse_html(self, text: str) -> str:
        without_scripts = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
        without_tags = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
        return unescape(re.sub(r"\s+", " ", without_tags)).strip()

    def _parse_csv(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
