"""Episodic memory search, archive, and index embedding workers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from fastapi import HTTPException
from sqlalchemy import select

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.storage import StorageAssetClass, StorageNotConfiguredError, object_storage
from backend.modules.identity_access.models import User
from backend.modules.memory.episodic import build_episodic_archive_jsonl_gz, episodic_object_key
from backend.modules.memory.metrics import increment_memory_metric
from backend.modules.memory.models import normalize_embedding_for_vector
from backend.modules.memory.settings import merge_memory_settings
from backend.modules.orchestration.models import RunEvent, TaskRun
from backend.modules.projects.orchestration_models import OrchestratorProject

logger = get_logger(__name__)


class _EmbeddingProvider(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


def episodic_embedding_batch_size() -> int:
    return max(1, int(getattr(settings, "RAG_INDEXING_BATCH_SIZE", 64)))


async def embed_episodic_index_rows_batched(
    ai_providers: _EmbeddingProvider,
    rows: list[Any],
    texts: list[str],
    *,
    batch_size: int | None = None,
) -> int:
    """Embed episodic index rows in provider-sized batches with per-row fallback."""
    if not rows or not texts or len(rows) != len(texts):
        return 0

    size = max(1, int(batch_size or episodic_embedding_batch_size()))
    embedded = 0
    for start in range(0, len(rows), size):
        batch_rows = rows[start : start + size]
        batch_texts = texts[start : start + size]
        try:
            vectors = await ai_providers.embed_texts(batch_texts)
            if len(vectors) != len(batch_rows):
                raise ValueError(
                    f"embedding provider returned {len(vectors)} vectors for {len(batch_rows)} rows"
                )
            for row, vec in zip(batch_rows, vectors, strict=True):
                try:
                    row.embedding_vector = normalize_embedding_for_vector(vec)
                    embedded += 1
                except Exception as exc:
                    logger.warning(
                        "episodic_index_embed_failed source_id=%s error=%s",
                        getattr(row, "source_id", None),
                        exc,
                    )
        except Exception as exc:
            logger.warning(
                "episodic_index_embed_batch_failed batch_size=%s error=%s",
                len(batch_rows),
                exc,
            )
            for row, text in zip(batch_rows, batch_texts, strict=True):
                try:
                    vec = (await ai_providers.embed_texts([text]))[0]
                    row.embedding_vector = normalize_embedding_for_vector(vec)
                    embedded += 1
                except Exception as row_exc:
                    logger.warning(
                        "episodic_index_embed_failed source_id=%s error=%s",
                        getattr(row, "source_id", None),
                        row_exc,
                    )
    return embedded


class EpisodicJobsMixin:
    async def search_episodic_memory(
        self,
        user: User,
        project_id: str,
        *,
        q: str | None = None,
        vec_q: str | None = None,
        limit: int = 45,
        since: datetime | None = None,
        until: datetime | None = None,
        task_id: str | None = None,
        kinds: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        project = await self.get_project(user, project_id)
        ms = merge_memory_settings(project.settings_json)
        base = await self.repo.search_episodic_for_project(
            project_id,
            query=q,
            limit=limit,
            since=since,
            until=until,
            task_id=task_id,
            kinds=kinds,
        )
        if vec_q and str(vec_q).strip() and ms.get("enable_episodic_vector_search", True):
            try:
                qv = (await self.ai_providers.embed_texts([str(vec_q).strip()[:8000]]))[0]
                idx_rows = await self.repo.search_episodic_index_by_vector(
                    project.owner_id, project_id, qv, limit=min(limit, 40)
                )
                vec_hits: list[dict[str, Any]] = []
                for row in idx_rows:
                    vec_hits.append(
                        {
                            "kind": f"indexed_{row.source_kind}",
                            "id": row.source_id,
                            "snippet": (row.text_content or "")[:500],
                            "created_at": row.created_at.isoformat(),
                            "index_id": row.id,
                        }
                    )
                seen: set[str] = set()
                merged: list[dict[str, Any]] = []
                for hit in vec_hits + base:
                    key = f"{hit.get('kind')}:{hit.get('id')}"
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(hit)
                increment_memory_metric("episodic_vector_queries")
                return merged[:limit]
            except Exception as exc:
                logger.warning("episodic vector search failed: %s", exc)
        return base

    async def list_episodic_archive_manifests_for_project(
        self, user: User, project_id: str
    ) -> list[Any]:
        project = await self.get_project(user, project_id)
        return await self.repo.list_episodic_archive_manifests(project.owner_id, project_id)

    async def get_episodic_archive_download_url(
        self, user: User, project_id: str, archive_id: str
    ) -> str:
        project = await self.get_project(user, project_id)
        manifest = await self.repo.get_episodic_archive_manifest(
            project.owner_id, project_id, archive_id
        )
        if manifest is None:
            raise HTTPException(status_code=404, detail="Episodic archive not found")
        if not object_storage.is_configured:
            raise HTTPException(status_code=503, detail="Object storage is not configured")
        try:
            return await object_storage.presigned_get_url(
                manifest.object_key,
                bucket=object_storage.private_bucket(),
            )
        except StorageNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail="Failed to prepare archive download"
            ) from exc

    async def run_episodic_retention_and_archive_job(self) -> dict[str, Any]:
        """Archive old episodic sources to cold storage; trim search index (never deletes run_events)."""
        result = await self.db.execute(select(OrchestratorProject))
        projects = list(result.scalars().all())
        archived_projects = 0
        archived_bytes = 0
        index_rows_dropped = 0
        for project in projects:
            ms = merge_memory_settings(project.settings_json)
            if not ms.get("episodic_archive_enabled", True):
                continue
            days = int(ms.get("episodic_retention_days") or 90)
            cutoff = datetime.now(UTC) - timedelta(days=days)
            events = await self.repo.list_run_events_for_project_before(
                project.id, cutoff, limit=5000
            )
            if not events:
                continue
            records = [
                {
                    "kind": "run_event",
                    "id": ev.id,
                    "run_id": ev.run_id,
                    "task_id": ev.task_id,
                    "event_type": ev.event_type,
                    "message": ev.message,
                    "created_at": ev.created_at,
                }
                for ev in events
            ]
            try:
                body = build_episodic_archive_jsonl_gz(records)
            except Exception:
                continue
            tag = f"{cutoff.date().isoformat()}_{project.id[:8]}"
            key = episodic_object_key(project.owner_id, project.id, tag)
            try:
                await object_storage.upload_bytes(
                    object_key=key,
                    body=body,
                    content_type="application/gzip",
                    asset_class=StorageAssetClass.PRIVATE,
                )
            except StorageNotConfiguredError:
                logger.warning("episodic archive skipped: storage not configured")
                continue
            except Exception as exc:
                logger.warning("episodic archive upload failed: %s", exc)
                continue
            await self.repo.create_episodic_archive_manifest(
                owner_id=project.owner_id,
                project_id=project.id,
                object_key=key,
                period_start=events[0].created_at,
                period_end=events[-1].created_at,
                record_count=len(records),
                byte_size=len(body),
                stats_json={"kinds": {"run_event": len(records)}},
            )
            if ms.get("episodic_delete_index_after_archive", True):
                dropped = await self.repo.delete_episodic_index_rows_before(project.id, cutoff)
                index_rows_dropped += dropped
            await self.db.commit()
            archived_projects += 1
            archived_bytes += len(body)
        increment_memory_metric("episodic_retention_runs")
        return {
            "projects_touched": archived_projects,
            "archived_bytes": archived_bytes,
            "index_rows_dropped": index_rows_dropped,
        }

    async def backfill_episodic_search_index(
        self, user: User, project_id: str, *, limit: int = 200
    ) -> int:
        """Index recent run events into episodic_search_index (snippets for vector search)."""
        project = await self.get_project(user, project_id)
        res = await self.db.execute(
            select(RunEvent)
            .join(TaskRun, RunEvent.run_id == TaskRun.id)
            .where(TaskRun.project_id == project_id)
            .order_by(RunEvent.created_at.desc())
            .limit(max(1, min(limit, 2000)))
        )
        events = list(res.scalars().all())
        if not events:
            return 0
        existing_rows = await self.repo.list_episodic_index_rows_for_sources(
            project_id, "run_event", [ev.id for ev in events]
        )
        existing_ids = {row.source_id for row in existing_rows}
        pending_texts: list[str] = []
        pending_rows = []
        for ev in events:
            if ev.id in existing_ids:
                continue
            text = (ev.message or "")[:4000]
            if not text.strip():
                continue
            row = await self.repo.create_episodic_search_index_row(
                owner_id=project.owner_id,
                project_id=project_id,
                source_kind="run_event",
                source_id=ev.id,
                text_content=text,
                created_at=ev.created_at,
            )
            pending_rows.append(row)
            pending_texts.append(text[:8000])
        await self.db.commit()
        if pending_rows:
            await embed_episodic_index_rows_batched(
                self.ai_providers,
                pending_rows,
                pending_texts,
            )
            await self.db.commit()
        increment_memory_metric("episodic_index_backfills")
        return len(pending_rows)

    async def process_episodic_index_embedding_batch(self, *, limit: int = 30) -> int:
        """Embed episodic index rows missing vectors (global, for Celery)."""
        res = await self.db.execute(select(OrchestratorProject.id))
        pids = [row[0] for row in res.all()]
        done = 0
        for pid in pids:
            rows = await self.repo.list_episodic_index_missing_embedding(pid, limit=limit)
            if not rows:
                continue
            texts = [(row.text_content or "")[:8000] for row in rows]
            embedded = await embed_episodic_index_rows_batched(
                self.ai_providers,
                rows,
                texts,
            )
            if embedded:
                await self.db.commit()
            done += embedded
        return done
