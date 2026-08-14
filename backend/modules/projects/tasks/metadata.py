"""Task metadata normalization wrappers."""

from __future__ import annotations

from typing import Any

from backend.modules.projects.task_metadata import (
    normalized_external_links,
    normalized_required_tools,
    normalized_task_metadata,
)


class TaskMetadataMixin:
    def _normalized_external_links(self, raw: Any) -> list[dict[str, str]]:
        return normalized_external_links(raw)

    def _normalized_required_tools(self, raw: Any) -> list[str]:
        return normalized_required_tools(raw)

    def _normalized_task_metadata(
        self,
        raw: Any,
        *,
        required_tools: Any = None,
        external_links: Any = None,
    ) -> dict[str, Any]:
        return normalized_task_metadata(
            raw,
            required_tools=required_tools,
            external_links=external_links,
        )
