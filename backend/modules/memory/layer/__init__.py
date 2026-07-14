"""Unified AI memory layer (mem0-inspired facade over semantic memory storage)."""

from backend.modules.memory.layer.config import MemoryConfig, resolve_memory_config
from backend.modules.memory.layer.port import MemoryStore
from backend.modules.memory.layer.schemas import (
    MemoryAccessContext,
    MemoryFilters,
    MemoryRecord,
    MemoryScope,
)
from backend.modules.memory.layer.service import MemoryService

__all__ = [
    "MemoryConfig",
    "MemoryAccessContext",
    "MemoryFilters",
    "MemoryRecord",
    "MemoryScope",
    "MemoryService",
    "MemoryStore",
    "resolve_memory_config",
]
