"""Document upload and project knowledge search API boundary."""

from __future__ import annotations

from typing import Any

from backend.modules.identity_access.models import User

_KNOWLEDGE_METHODS = frozenset(
    {
        "upload_document",
        "list_documents",
        "delete_document",
        "search_project_knowledge",
        "list_project_memory",
        "delete_memory_entry",
        "create_knowledge_graph_edge_for_project",
        "list_knowledge_graph_edges_for_project",
        "delete_knowledge_graph_edge_for_project",
    }
)


class KnowledgeService:
    """Thin facade over memory domain for document and knowledge-graph routes."""

    def __init__(self, memory_host: Any) -> None:
        self._memory = memory_host

    def __getattr__(self, name: str):
        if name in _KNOWLEDGE_METHODS and hasattr(self._memory, name):
            return getattr(self._memory, name)
        raise AttributeError(f"{type(self).__name__!r} has no attribute {name!r}")

    async def upload_document(self, user: User, project_id: str, **kwargs):
        return await self._memory.upload_document(user, project_id, **kwargs)

    async def list_documents(
        self,
        user: User,
        project_id: str,
        task_id: str | None = None,
        **page,
    ):
        return await self._memory.list_documents(user, project_id, task_id=task_id, **page)

    async def delete_document(self, user: User, project_id: str, document_id: str) -> None:
        return await self._memory.delete_document(user, project_id, document_id)

    async def search_project_knowledge(self, user: User, project_id: str, **kwargs):
        return await self._memory.search_project_knowledge(user, project_id, **kwargs)

    async def list_project_memory(self, user: User, project_id: str, **kwargs):
        return await self._memory.list_project_memory(user, project_id, **kwargs)

    async def delete_memory_entry(self, user: User, project_id: str, memory_id: str) -> None:
        return await self._memory.delete_memory_entry(user, project_id, memory_id)
