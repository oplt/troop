"""Permission-aware external drive sync into project RAG documents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import User
from backend.modules.memory.models import ProjectDocument
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.rag.retrieval import DocumentIngestionService
from backend.modules.workforce.integrations.drive_acl import actor_can_read_acl
from backend.modules.workforce.integrations.google_drive import (
    GoogleDriveAdapter,
    GoogleDriveAPIError,
)
from backend.modules.workforce.integrations.microsoft_drive import (
    MicrosoftDriveAdapter,
)
from backend.modules.workforce.models import ExternalDocumentSyncState, ExternalKnowledgeSource

_TEXT_MIMES = {
    "text/",
    "application/json",
    "application/xml",
    "application/javascript",
}


def _is_text_mime(mime: str) -> bool:
    return any(mime.startswith(prefix) for prefix in _TEXT_MIMES) or mime in {
        "application/vnd.google-apps.document",
        "application/vnd.google-apps.spreadsheet",
        "application/vnd.google-apps.presentation",
    }


class DriveSyncService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = OrchestrationRepository(db)

    async def sync_source(self, source_id: str, *, actor_user_id: str) -> dict[str, Any]:
        source = await self.db.get(ExternalKnowledgeSource, source_id)
        if source is None or source.owner_id != actor_user_id:
            raise ValueError("Knowledge source not found")
        if source.provider == "google_drive":
            return await self._sync_google(source, actor_user_id=actor_user_id)
        if source.provider == "microsoft_drive":
            return await self._sync_microsoft(source, actor_user_id=actor_user_id)
        raise ValueError(f"Unsupported drive provider: {source.provider}")

    async def _sync_google(
        self, source: ExternalKnowledgeSource, *, actor_user_id: str
    ) -> dict[str, Any]:
        adapter = await GoogleDriveAdapter.for_owner(
            self.db,
            owner_id=source.owner_id,
            installation_id=source.connector_installation_id,
        )
        page_token = source.sync_cursor
        if not page_token:
            start = await adapter.execute("google_drive.get_start_page_token", {})
            page_token = str(start.get("startPageToken") or "")
        if not page_token:
            raise GoogleDriveAPIError("Unable to initialize Google Drive change cursor")
        indexed = deleted = 0
        while page_token:
            changes = await adapter.execute("google_drive.list_changes", {"page_token": page_token})
            for change in changes.get("changes") or []:
                if change.get("removed") or (change.get("file") or {}).get("trashed"):
                    if await self._tombstone(source, str(change.get("fileId") or "")):
                        deleted += 1
                    continue
                file_body = dict(change.get("file") or {})
                file_id = str(file_body.get("id") or change.get("fileId") or "")
                if not file_id or not _is_text_mime(str(file_body.get("mimeType") or "")):
                    continue
                if await self._index_google_file(
                    source, adapter, file_id=file_id, actor_user_id=actor_user_id
                ):
                    indexed += 1
            page_token = changes.get("nextPageToken")
            if not page_token:
                source.sync_cursor = str(
                    changes.get("newStartPageToken") or source.sync_cursor or ""
                )
        source.last_synced_at = datetime.now(UTC)
        source.status = "active"
        await self.db.commit()
        return {"indexed": indexed, "deleted": deleted, "cursor": source.sync_cursor}

    async def _sync_microsoft(
        self, source: ExternalKnowledgeSource, *, actor_user_id: str
    ) -> dict[str, Any]:
        adapter = await MicrosoftDriveAdapter.for_owner(
            self.db,
            owner_id=source.owner_id,
            installation_id=source.connector_installation_id,
        )
        root_config = dict(source.root_config_json or {})
        arguments = {
            "drive_id": root_config.get("drive_id"),
            "site_id": root_config.get("site_id"),
            "delta_link": source.sync_cursor or None,
        }
        indexed = deleted = 0
        delta_link = source.sync_cursor
        while True:
            body = await adapter.execute("microsoft_drive.list_delta", arguments)
            for item in body.get("value") or []:
                if item.get("@microsoft.graph.deleted") or item.get("deleted"):
                    if await self._tombstone(source, str(item.get("id") or "")):
                        deleted += 1
                    continue
                file_id = str(item.get("id") or "")
                if not file_id or item.get("folder"):
                    continue
                if not _is_text_mime(
                    str(item.get("file", {}).get("mimeType") or item.get("mimeType") or "")
                ):
                    continue
                if await self._index_microsoft_file(
                    source,
                    adapter,
                    file_id=file_id,
                    actor_user_id=actor_user_id,
                    root_config=root_config,
                ):
                    indexed += 1
            delta_link = str(body.get("@odata.deltaLink") or body.get("@odata.nextLink") or "")
            if body.get("@odata.nextLink"):
                arguments["delta_link"] = delta_link
                continue
            source.sync_cursor = delta_link or source.sync_cursor
            break
        source.last_synced_at = datetime.now(UTC)
        source.status = "active"
        await self.db.commit()
        return {"indexed": indexed, "deleted": deleted, "cursor": source.sync_cursor}

    async def _tombstone(self, source: ExternalKnowledgeSource, external_file_id: str) -> bool:
        result = await self.db.execute(
            select(ExternalDocumentSyncState).where(
                ExternalDocumentSyncState.source_id == source.id,
                ExternalDocumentSyncState.external_file_id == external_file_id,
            )
        )
        state = result.scalar_one_or_none()
        if state is None:
            return False
        state.sync_status = "deleted"
        state.deleted_at = datetime.now(UTC)
        if state.project_document_id:
            document = await self.db.get(ProjectDocument, state.project_document_id)
            if document is not None:
                document.deleted_at = datetime.now(UTC)
                await self.repo.replace_document_chunks(document, [])
        return True

    async def _index_google_file(
        self,
        source: ExternalKnowledgeSource,
        adapter: GoogleDriveAdapter,
        *,
        file_id: str,
        actor_user_id: str,
    ) -> bool:
        payload = await adapter.execute("google_drive.get_file_content", {"file_id": file_id})
        meta = dict(payload.get("metadata") or {})
        acl_snapshot = dict(meta.get("acl_snapshot") or {})
        user = await self.db.get(User, actor_user_id)
        if user and not actor_can_read_acl(acl_snapshot, actor_email=user.email):
            return False
        return await self._upsert_document(
            source,
            external_file_id=file_id,
            external_path=str(meta.get("name") or file_id),
            etag=str(meta.get("modifiedTime") or ""),
            acl_snapshot=acl_snapshot,
            content=str(payload.get("content") or ""),
            actor_user_id=actor_user_id,
            mime_type=str(meta.get("mimeType") or "text/plain"),
        )

    async def _index_microsoft_file(
        self,
        source: ExternalKnowledgeSource,
        adapter: MicrosoftDriveAdapter,
        *,
        file_id: str,
        actor_user_id: str,
        root_config: dict[str, Any],
    ) -> bool:
        payload = await adapter.execute(
            "microsoft_drive.get_file_content",
            {"file_id": file_id, **root_config},
        )
        meta = dict(payload.get("metadata") or {})
        acl_snapshot = dict(meta.get("acl_snapshot") or {})
        user = await self.db.get(User, actor_user_id)
        if user and not actor_can_read_acl(acl_snapshot, actor_email=user.email):
            return False
        return await self._upsert_document(
            source,
            external_file_id=file_id,
            external_path=str(meta.get("name") or file_id),
            etag=str(meta.get("lastModifiedDateTime") or ""),
            acl_snapshot=acl_snapshot,
            content=str(payload.get("content") or ""),
            actor_user_id=actor_user_id,
            mime_type=str(
                meta.get("file", {}).get("mimeType") or meta.get("mimeType") or "text/plain"
            ),
        )

    async def _upsert_document(
        self,
        source: ExternalKnowledgeSource,
        *,
        external_file_id: str,
        external_path: str,
        etag: str,
        acl_snapshot: dict[str, Any],
        content: str,
        actor_user_id: str,
        mime_type: str,
    ) -> bool:
        if not content.strip():
            return False
        result = await self.db.execute(
            select(ExternalDocumentSyncState).where(
                ExternalDocumentSyncState.source_id == source.id,
                ExternalDocumentSyncState.external_file_id == external_file_id,
            )
        )
        state = result.scalar_one_or_none()
        if state and state.etag == etag and state.project_document_id:
            return False
        document: ProjectDocument | None = None
        if state and state.project_document_id:
            document = await self.db.get(ProjectDocument, state.project_document_id)
        if document is None:
            document = await self.repo.create_document(
                project_id=source.project_id,
                task_id=None,
                uploaded_by_user_id=actor_user_id,
                filename=external_path,
                content_type=mime_type,
                source_text=content,
                object_key=None,
                size_bytes=len(content.encode()),
                summary_text=content[:500],
                ingestion_status="pending",
                metadata_json={},
            )
        else:
            document.filename = external_path
            document.source_text = content
            document.size_bytes = len(content.encode())
            document.summary_text = content[:500]
            document.deleted_at = None
            document.ingestion_status = "pending"
        document.metadata_json = {
            **dict(document.metadata_json or {}),
            "source_kind": source.provider,
            "external_file_id": external_file_id,
            "external_path": external_path,
            "etag": etag,
            "connector_installation_id": source.connector_installation_id,
            "acl_snapshot": acl_snapshot,
        }
        if state is None:
            state = ExternalDocumentSyncState(
                source_id=source.id,
                external_file_id=external_file_id,
                external_path=external_path,
                project_document_id=document.id,
            )
            self.db.add(state)
        state.external_path = external_path
        state.etag = etag
        state.acl_snapshot_json = acl_snapshot
        state.sync_status = "indexed"
        state.deleted_at = None
        state.project_document_id = document.id
        await self.db.flush()
        await DocumentIngestionService(self.db).index_project_document(document)
        return True
