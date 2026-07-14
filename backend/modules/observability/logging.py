"""Stable logging interface that delegates to the existing core setup."""

from __future__ import annotations

import logging
from typing import Any

from backend.core.logging import get_logger, setup_logging
from backend.modules.observability.context import current_context


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit a bounded event while automatically adding current context IDs."""
    context_fields = current_context().as_log_fields()
    merged = {**context_fields, **fields}
    rendered_fields = " ".join(
        f"{key}={value}" for key, value in sorted(merged.items()) if value is not None
    )
    logger.log(level, "%s%s", event, f" {rendered_fields}" if rendered_fields else "")


__all__ = ["get_logger", "log_event", "setup_logging"]
