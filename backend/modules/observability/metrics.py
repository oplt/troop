"""Dependency-free, bounded Prometheus-compatible application metrics."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Literal

MetricType = Literal["counter", "gauge", "histogram"]
DEFAULT_HISTOGRAM_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)
_PATH_ID = re.compile(r"/[0-9a-f]{8,}(?=/|$)|/\d+(?=/|$)", re.IGNORECASE)


def bounded_route(path: str) -> str:
    """Normalize fallback paths so metrics cannot grow per resource ID."""
    normalized = _PATH_ID.sub("/{id}", path or "/")
    return normalized[:120] or "/"


def bounded_label(value: object, *, fallback: str = "unknown", limit: int = 64) -> str:
    text = str(value or fallback).strip()
    text = re.sub(r"[^A-Za-z0-9_./:{}-]+", "_", text)
    return text[:limit] or fallback


@dataclass(slots=True)
class _Metric:
    name: str
    metric_type: MetricType
    help_text: str
    label_names: tuple[str, ...]
    buckets: tuple[float, ...] = DEFAULT_HISTOGRAM_BUCKETS
    values: dict[tuple[str, ...], float] = field(default_factory=dict)
    histogram_counts: dict[tuple[str, ...], list[int]] = field(default_factory=dict)
    histogram_sums: dict[tuple[str, ...], float] = field(default_factory=dict)


class MetricsRegistry:
    """Thread-safe registry with explicit metric shapes and bounded labels."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._metrics: dict[str, _Metric] = {}

    def _metric(
        self,
        name: str,
        metric_type: MetricType,
        help_text: str,
        label_names: tuple[str, ...],
        buckets: tuple[float, ...] = DEFAULT_HISTOGRAM_BUCKETS,
    ) -> _Metric:
        with self._lock:
            metric = self._metrics.get(name)
            if metric is None:
                metric = _Metric(name, metric_type, help_text, label_names, buckets)
                self._metrics[name] = metric
            elif (metric.metric_type, metric.label_names) != (metric_type, label_names):
                raise ValueError(f"Metric {name} was registered with an incompatible shape")
            return metric

    @staticmethod
    def _labels(metric: _Metric, labels: dict[str, object] | None) -> tuple[str, ...]:
        provided = labels or {}
        unknown = set(provided) - set(metric.label_names)
        missing = set(metric.label_names) - set(provided)
        if unknown or missing:
            raise ValueError(f"Metric labels mismatch unknown={unknown} missing={missing}")
        return tuple(bounded_label(provided[name]) for name in metric.label_names)

    def increment(
        self,
        name: str,
        *,
        help_text: str,
        labels: dict[str, object] | None = None,
        delta: float = 1,
    ) -> None:
        metric = self._metric(name, "counter", help_text, tuple(sorted(labels or {})))
        key = self._labels(metric, labels)
        with self._lock:
            metric.values[key] = metric.values.get(key, 0) + delta

    def set_gauge(
        self,
        name: str,
        value: float,
        *,
        help_text: str,
        labels: dict[str, object] | None = None,
    ) -> None:
        metric = self._metric(name, "gauge", help_text, tuple(sorted(labels or {})))
        key = self._labels(metric, labels)
        with self._lock:
            metric.values[key] = value

    def increment_gauge(
        self,
        name: str,
        *,
        help_text: str,
        labels: dict[str, object] | None = None,
        delta: float = 1,
    ) -> None:
        metric = self._metric(name, "gauge", help_text, tuple(sorted(labels or {})))
        key = self._labels(metric, labels)
        with self._lock:
            metric.values[key] = max(0, metric.values.get(key, 0) + delta)

    def observe(
        self,
        name: str,
        value: float,
        *,
        help_text: str,
        labels: dict[str, object] | None = None,
        buckets: tuple[float, ...] = DEFAULT_HISTOGRAM_BUCKETS,
    ) -> None:
        metric = self._metric(
            name,
            "histogram",
            help_text,
            tuple(sorted(labels or {})),
            buckets,
        )
        key = self._labels(metric, labels)
        with self._lock:
            counts = metric.histogram_counts.setdefault(key, [0] * (len(metric.buckets) + 1))
            for index, bucket in enumerate(metric.buckets):
                if value <= bucket:
                    counts[index] += 1
            counts[-1] += 1
            metric.histogram_sums[key] = metric.histogram_sums.get(key, 0.0) + value

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                name: {
                    "type": metric.metric_type,
                    "help": metric.help_text,
                    "labels": metric.label_names,
                    "values": dict(metric.values),
                    "histograms": {
                        key: {
                            "buckets": list(counts),
                            "sum": metric.histogram_sums.get(key, 0.0),
                        }
                        for key, counts in metric.histogram_counts.items()
                    },
                }
                for name, metric in self._metrics.items()
            }

    def reset(self) -> None:
        with self._lock:
            self._metrics.clear()

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for metric in sorted(self._metrics.values(), key=lambda item: item.name):
                lines.extend(
                    (
                        f"# HELP {metric.name} {metric.help_text}",
                        f"# TYPE {metric.name} {metric.metric_type}",
                    )
                )
                if metric.metric_type == "histogram":
                    for labels, counts in metric.histogram_counts.items():
                        for index, bucket in enumerate(metric.buckets):
                            lines.append(
                                _sample(
                                    metric.name + "_bucket",
                                    labels,
                                    metric.label_names,
                                    counts[index],
                                    {"le": str(bucket)},
                                )
                            )
                        lines.append(
                            _sample(
                                metric.name + "_bucket",
                                labels,
                                metric.label_names,
                                counts[-1],
                                {"le": "+Inf"},
                            )
                        )
                        lines.append(
                            _sample(
                                metric.name + "_sum",
                                labels,
                                metric.label_names,
                                metric.histogram_sums.get(labels, 0.0),
                            )
                        )
                        lines.append(
                            _sample(metric.name + "_count", labels, metric.label_names, counts[-1])
                        )
                else:
                    for labels, value in metric.values.items():
                        lines.append(_sample(metric.name, labels, metric.label_names, value))
        return "\n".join(lines) + ("\n" if lines else "")


def _sample(
    name: str,
    values: tuple[str, ...],
    label_names: tuple[str, ...],
    value: float,
    extra: dict[str, str] | None = None,
) -> str:
    labels = dict(zip(label_names, values, strict=True))
    labels.update(extra or {})
    rendered = ",".join(
        f'{key}="{str(item).replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
        for key, item in sorted(labels.items())
    )
    return f"{name}{{{rendered}}} {value}" if rendered else f"{name} {value}"


metrics_registry = MetricsRegistry()

HTTP_REQUESTS = "troop_http_requests_total"
HTTP_DURATION = "troop_http_request_duration_seconds"
HTTP_ERRORS = "troop_http_errors_total"
HTTP_ACTIVE = "troop_http_active_requests"
WORKER_TASKS = "troop_worker_tasks_total"
WORKER_DURATION = "troop_worker_task_duration_seconds"
WORKER_ACTIVE = "troop_worker_active_tasks"
PROVIDER_REQUESTS = "troop_provider_requests_total"
PROVIDER_DURATION = "troop_provider_request_duration_seconds"
DB_QUERIES = "troop_db_queries_total"
DB_DURATION = "troop_db_query_duration_seconds"
DB_ERRORS = "troop_db_errors_total"
CACHE_OPERATIONS = "troop_cache_operations_total"
CACHE_DURATION = "troop_cache_operation_duration_seconds"
SSE_CONNECTIONS = "troop_sse_connections"
SSE_EVENTS = "troop_sse_events_total"
QUEUE_DEPTH = "troop_queue_depth"
QUEUE_AGE = "troop_queue_oldest_age_seconds"
RUNS = "troop_orchestration_runs_total"
MEMORY_RETRIEVALS = "troop_memory_retrievals_total"
MEMORY_RETRIEVAL_DURATION = "troop_memory_retrieval_duration_seconds"
DISTRIBUTED_LOCKS = "troop_distributed_lock_attempts_total"


def record_http_request(method: str, route: str, status_code: int, duration_seconds: float) -> None:
    normalized_route = bounded_route(route)
    metrics_registry.increment(
        HTTP_REQUESTS,
        help_text="Completed HTTP requests.",
        labels={"method": method, "route": normalized_route, "status": str(status_code)},
    )
    metrics_registry.observe(
        HTTP_DURATION,
        duration_seconds,
        help_text="HTTP request duration in seconds.",
        labels={"method": method, "route": normalized_route},
    )
    if status_code >= 500:
        metrics_registry.increment(
            HTTP_ERRORS,
            help_text="HTTP 5xx responses.",
            labels={"method": method, "route": normalized_route},
        )


def record_worker_task(task: str, outcome: str, duration_seconds: float) -> None:
    normalized_task = bounded_label(task)
    labels = {"task": normalized_task, "outcome": bounded_label(outcome)}
    metrics_registry.increment(WORKER_TASKS, help_text="Completed Celery tasks.", labels=labels)
    metrics_registry.observe(
        WORKER_DURATION,
        duration_seconds,
        help_text="Celery task duration in seconds.",
        labels={"task": normalized_task},
    )


def record_provider_call(
    provider: str,
    operation: str,
    outcome: str,
    duration_seconds: float,
) -> None:
    normalized_provider = bounded_label(provider)
    normalized_operation = bounded_label(operation)
    metrics_registry.increment(
        PROVIDER_REQUESTS,
        help_text="Provider calls.",
        labels={
            "provider": normalized_provider,
            "operation": normalized_operation,
            "outcome": bounded_label(outcome),
        },
    )
    metrics_registry.observe(
        PROVIDER_DURATION,
        duration_seconds,
        help_text="Provider call duration in seconds.",
        labels={"provider": normalized_provider, "operation": normalized_operation},
    )


def record_db_query(operation: str, outcome: str, duration_seconds: float) -> None:
    normalized_operation = bounded_label(operation)
    normalized_outcome = bounded_label(outcome)
    metrics_registry.increment(
        DB_QUERIES,
        help_text="Database queries.",
        labels={"operation": normalized_operation, "outcome": normalized_outcome},
    )
    metrics_registry.observe(
        DB_DURATION,
        duration_seconds,
        help_text="Database query duration in seconds.",
        labels={"operation": normalized_operation},
    )
    if normalized_outcome != "success":
        metrics_registry.increment(
            DB_ERRORS,
            help_text="Database query errors.",
            labels={"operation": normalized_operation},
        )


def record_cache_operation(
    cache_name: str,
    operation: str,
    outcome: str,
    duration_seconds: float,
) -> None:
    """Record cache behavior with bounded, non-sensitive labels.

    Cache keys deliberately never become metric labels: session, user, project,
    and document identifiers would create an unbounded and privacy-sensitive
    metric series. ``cache_name`` is the stable policy name instead.
    """
    labels = {
        "cache": bounded_label(cache_name),
        "operation": bounded_label(operation),
        "outcome": bounded_label(outcome),
    }
    metrics_registry.increment(
        CACHE_OPERATIONS,
        help_text="Cache operations by stable cache policy and outcome.",
        labels=labels,
    )
    metrics_registry.observe(
        CACHE_DURATION,
        duration_seconds,
        help_text="Cache operation duration in seconds.",
        labels={"cache": bounded_label(cache_name), "operation": bounded_label(operation)},
    )


def record_sse_event(stream: str, event: str, *, delta_connections: int = 0) -> None:
    normalized_stream = bounded_label(stream)
    metrics_registry.increment(
        SSE_EVENTS,
        help_text="SSE stream lifecycle and delivery events.",
        labels={"stream": normalized_stream, "event": bounded_label(event)},
    )
    if delta_connections:
        metrics_registry.increment_gauge(
            SSE_CONNECTIONS,
            help_text="Active server-sent event connections.",
            labels={"stream": normalized_stream},
            delta=delta_connections,
        )


def record_queue_state(queue: str, *, depth: int, oldest_age_seconds: float | None = None) -> None:
    """Record bounded queue pressure without exposing task or tenant IDs."""
    labels = {"queue": bounded_label(queue)}
    metrics_registry.set_gauge(
        QUEUE_DEPTH,
        max(0, depth),
        help_text="Current durable queue depth.",
        labels=labels,
    )
    if oldest_age_seconds is not None:
        metrics_registry.set_gauge(
            QUEUE_AGE,
            max(0.0, oldest_age_seconds),
            help_text="Age in seconds of the oldest queued item.",
            labels=labels,
        )


def record_run_outcome(run_mode: str, outcome: str) -> None:
    metrics_registry.increment(
        RUNS,
        help_text="Durable orchestration run outcomes.",
        labels={"run_mode": bounded_label(run_mode), "outcome": bounded_label(outcome)},
    )


def record_memory_retrieval(
    memory_type: str,
    outcome: str,
    duration_seconds: float,
) -> None:
    labels = {"memory_type": bounded_label(memory_type), "outcome": bounded_label(outcome)}
    metrics_registry.increment(
        MEMORY_RETRIEVALS,
        help_text="Memory and RAG retrieval outcomes.",
        labels=labels,
    )
    metrics_registry.observe(
        MEMORY_RETRIEVAL_DURATION,
        duration_seconds,
        help_text="Memory and RAG retrieval duration in seconds.",
        labels={"memory_type": bounded_label(memory_type)},
    )


def record_distributed_lock(name: str, outcome: str) -> None:
    metrics_registry.increment(
        DISTRIBUTED_LOCKS,
        help_text="Distributed lease acquisition outcomes.",
        labels={"lock": bounded_label(name), "outcome": bounded_label(outcome)},
    )


__all__ = [
    "CACHE_DURATION",
    "CACHE_OPERATIONS",
    "DISTRIBUTED_LOCKS",
    "MEMORY_RETRIEVALS",
    "MEMORY_RETRIEVAL_DURATION",
    "QUEUE_AGE",
    "QUEUE_DEPTH",
    "RUNS",
    "SSE_CONNECTIONS",
    "SSE_EVENTS",
    "DB_DURATION",
    "DB_ERRORS",
    "DB_QUERIES",
    "HTTP_ACTIVE",
    "HTTP_DURATION",
    "HTTP_ERRORS",
    "HTTP_REQUESTS",
    "MetricsRegistry",
    "PROVIDER_DURATION",
    "PROVIDER_REQUESTS",
    "WORKER_ACTIVE",
    "WORKER_DURATION",
    "WORKER_TASKS",
    "bounded_label",
    "bounded_route",
    "metrics_registry",
    "record_db_query",
    "record_cache_operation",
    "record_distributed_lock",
    "record_sse_event",
    "record_http_request",
    "record_memory_retrieval",
    "record_queue_state",
    "record_run_outcome",
    "record_provider_call",
    "record_worker_task",
]
