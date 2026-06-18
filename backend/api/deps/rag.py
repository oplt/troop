"""FastAPI dependencies for RAG services."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_db
from backend.modules.rag.service import RagService


def get_rag_service(db: AsyncSession = Depends(get_db)) -> RagService:
    return RagService(db)
