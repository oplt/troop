"""AI Studio document listing and upload entrypoints."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, UploadFile

from backend.core.config import settings
from backend.modules.ai.documents.ingestion import AiDocumentIngestionMixin
from backend.modules.identity_access.models import User


class AiDocumentsMixin(AiDocumentIngestionMixin):
    async def list_documents(self, user: User):
        return await self.repo.list_documents_for_user(user.id)

    async def get_document(self, user: User, document_id: str):
        document = await self.repo.get_document_for_user(user.id, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return document

    async def create_document_from_upload(
        self,
        user: User,
        file: UploadFile,
        description: str | None,
        *,
        queue_async: bool | None = None,
    ) -> tuple[Any, str | None]:
        content_type = file.content_type or "text/plain"
        if not (
            content_type.startswith("text/")
            or content_type in {"application/json", "application/x-ndjson", "text/markdown"}
        ):
            raise HTTPException(
                status_code=400,
                detail="Document ingestion currently supports text, markdown, and json files only",
            )
        payload = await file.read()
        if not payload:
            raise HTTPException(status_code=400, detail="Uploaded document file is empty")
        if len(payload) > settings.AI_DOCUMENT_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Document exceeds the maximum size of"
                    f" {settings.AI_DOCUMENT_MAX_BYTES} bytes"
                ),
            )
        try:
            content = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400, detail="Uploaded document must be valid UTF-8 text"
            ) from exc
        title = file.filename or "Untitled document"
        return await self.create_document_from_text(
            user,
            title=title,
            description=description,
            content=content,
            content_type=content_type,
            filename=file.filename,
            queue_async=queue_async,
        )
