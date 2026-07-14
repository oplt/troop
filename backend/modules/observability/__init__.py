"""Application observability ports and optional instrumentation."""

from backend.modules.observability.metrics import metrics_registry

__all__ = ["metrics_registry"]
