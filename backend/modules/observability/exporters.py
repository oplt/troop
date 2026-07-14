"""Exporter compatibility functions."""

from backend.modules.observability.metrics import metrics_registry


def prometheus_payload() -> str:
    return metrics_registry.render_prometheus()


__all__ = ["prometheus_payload"]
