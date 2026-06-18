from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from backend.modules.memory.layer.config import MemoryConfig
from backend.modules.memory.layer.context import build_memory_context
from backend.modules.memory.layer.dedup import content_hash, is_duplicate
from backend.modules.memory.layer.extractor import extract_with_rules, parse_llm_extraction
from backend.modules.memory.layer.redaction import (
    contains_sensitive_content,
    is_safe_to_store,
    redact_sensitive_content,
    sanitize_for_storage,
)
from backend.modules.memory.layer.schemas import MemoryFilters, MemoryRecord
from backend.modules.memory.layer.service import MemoryService


def test_redaction_blocks_api_keys_and_passwords():
    raw = "User password: hunter2 and api_key=sk-abcdefghijklmnopqrstuvwxyz1234567890"
    assert contains_sensitive_content(raw)
    redacted, hits = redact_sensitive_content(raw)
    assert "[REDACTED]" in redacted
    assert hits
    safe, reason = is_safe_to_store(redacted)
    assert safe or reason == "blocked_pattern"


def test_sanitize_for_storage_rejects_mostly_secret_content():
    secret_only = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"
    assert sanitize_for_storage(secret_only)[0] is None


def test_sanitize_for_storage_allows_clean_facts():
    fact = "The team decided to use PostgreSQL with pgvector for semantic memory search."
    safe, hits = sanitize_for_storage(fact)
    assert safe == fact
    assert hits == []


def test_content_hash_dedup():
    a = "Prefer TypeScript strict mode for all frontend packages."
    b = "prefer   typescript strict mode for all frontend packages."
    assert content_hash(a) == content_hash(b)
    seen = {content_hash(a)}
    assert is_duplicate(seen, b)


def test_build_memory_context_formatting():
    records = [
        MemoryRecord(
            id="1",
            content="Always run migrations before deploying.",
            user_id="u1",
            memory_type="policy",
            title="Deploy checklist",
        ),
        MemoryRecord(
            id="2",
            content="Default search limit is five memories.",
            user_id="u1",
            memory_type="preference",
        ),
    ]
    block = build_memory_context(records)
    assert block.startswith("Relevant memory context:")
    assert "Deploy checklist" in block
    assert "Default search limit" in block


def test_rule_extractor_finds_preferences():
    messages = [
        {
            "role": "user",
            "content": "We prefer to always use strict typing and avoid any in new modules.",
        }
    ]
    extracted = extract_with_rules(messages, min_confidence=0.4)
    assert extracted
    assert extracted[0].memory_type in {"preference", "convention", "note", "policy"}


def test_parse_llm_extraction_json():
    raw = '{"memories":[{"text":"Project uses FastAPI with async SQLAlchemy.","memory_type":"fact","confidence":0.8}]}'
    items = parse_llm_extraction(raw)
    assert len(items) == 1
    assert "FastAPI" in items[0].text


@dataclass
class _FakeProvider:
    stored: dict[str, MemoryRecord] = field(default_factory=dict)

    async def add(self, *, owner_id: str, content: str, scope: str, project_id: str | None, metadata: dict[str, Any]) -> MemoryRecord:
        rid = f"m-{len(self.stored)+1}"
        record = MemoryRecord(
            id=rid,
            content=content,
            user_id=owner_id,
            project_id=project_id,
            metadata=metadata,
            memory_type=str(metadata.get("memory_type") or "note"),
        )
        self.stored[rid] = record
        return record

    async def get(self, owner_id: str, memory_id: str) -> MemoryRecord | None:
        row = self.stored.get(memory_id)
        return row if row and row.user_id == owner_id else None

    async def search(self, owner_id: str, query: str, *, query_vec, filters: MemoryFilters, limit: int) -> list[MemoryRecord]:
        return [r for r in self.stored.values() if r.user_id == owner_id][:limit]

    async def update(self, owner_id: str, memory_id: str, *, content: str | None, metadata: dict[str, Any] | None) -> MemoryRecord | None:
        row = await self.get(owner_id, memory_id)
        if row is None:
            return None
        if content is not None:
            row.content = content
        if metadata:
            row.metadata.update(metadata)
        return row

    async def delete(self, owner_id: str, memory_id: str) -> bool:
        row = await self.get(owner_id, memory_id)
        if row is None:
            return False
        del self.stored[memory_id]
        return True

    async def delete_for_user(self, owner_id: str) -> int:
        ids = [mid for mid, row in self.stored.items() if row.user_id == owner_id]
        for mid in ids:
            del self.stored[mid]
        return len(ids)

    async def find_duplicate(self, owner_id: str, content_hash: str, filters: MemoryFilters) -> MemoryRecord | None:
        for row in self.stored.values():
            if row.user_id == owner_id and row.metadata.get("content_hash") == content_hash:
                return row
        return None


class _FakeSession:
    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_memory_service_disabled_is_noop():
    provider = _FakeProvider()
    service = MemoryService(
        _FakeSession(),  # type: ignore[arg-type]
        config=MemoryConfig(enabled=False),
        provider=provider,
    )
    assert await service.add_memory("u1", "Some durable fact about the project.") is None
    assert await service.search_memories("u1", "fact") == []
    assert await service.build_memory_context("u1", "fact") == ""


@pytest.mark.asyncio
async def test_memory_service_add_search_update_delete():
    provider = _FakeProvider()
    service = MemoryService(
        _FakeSession(),  # type: ignore[arg-type]
        config=MemoryConfig(enabled=True, dedup_enabled=True),
        provider=provider,
    )
    created = await service.add_memory(
        "u1",
        "The staging environment uses Redis for Celery broker.",
        {"project_id": "p1", "memory_type": "fact"},
        project_id="p1",
    )
    assert created is not None
    assert created.id in provider.stored

    blocked = await service.add_memory("u1", "password: super-secret-value-that-should-never-be-stored")
    assert blocked is None

    results = await service.search_memories(
        "u1",
        "Redis Celery",
        filters=MemoryFilters(user_id="u1", project_id="p1"),
    )
    assert results

    updated = await service.update_memory(
        created.id,
        user_id="u1",
        content="The staging environment uses Redis Cluster for Celery broker.",
    )
    assert updated is not None
    assert "Cluster" in updated.content

    deleted = await service.delete_memory(created.id, user_id="u1")
    assert deleted is True


@pytest.mark.asyncio
async def test_memory_service_dedup_skips_duplicate():
    provider = _FakeProvider()
    service = MemoryService(
        _FakeSession(),  # type: ignore[arg-type]
        config=MemoryConfig(enabled=True, dedup_enabled=True),
        provider=provider,
    )
    first = await service.add_memory("u1", "Always pin dependency versions in production.", project_id="p1")
    second = await service.add_memory("u1", "always pin dependency versions in production.", project_id="p1")
    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert len(provider.stored) == 1
