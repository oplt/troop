"""Unified AI memory layer (mem0-inspired facade over semantic memory storage)."""

from backend.modules.memory.layer.config import MemoryConfig, resolve_memory_config
from backend.modules.memory.layer.schemas import MemoryFilters, MemoryRecord, MemoryScope
from backend.modules.memory.layer.service import MemoryService

__all__ = [
    "MemoryConfig",
    "MemoryFilters",
    "MemoryRecord",
    "MemoryScope",
    "MemoryService",
    "resolve_memory_config",
]
