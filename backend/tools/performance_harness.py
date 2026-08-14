"""In-process performance benchmarks for hottest backend paths.

Used by ``phase0_baseline.py --in-process`` and pytest smoke tests.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Iterator

from sqlalchemy import event, select

from backend.modules.memory.models import SemanticMemoryEntry, normalize_embedding_for_vector
from backend.modules.orchestration.execution.durable_execution import is_run_execution_claimable
from backend.modules.orchestration.models import TaskRun
from backend.tools.phase0_baseline import summarize_timings


@contextmanager
def count_sql_queries(engine: Any) -> Iterator[list[str]]:
    """Count SQL statements executed on the bound sync engine."""
    statements: list[str] = []

    def before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(str(statement).lstrip()[:120])

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)


def _timing_result(
    *,
    name: str,
    timings_ms: list[float],
    query_count: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "latency": summarize_timings(timings_ms),
        "query_count": query_count,
    }
    if extra:
        payload.update(extra)
    return payload


async def benchmark_portfolio_control_plane(
    repo: Any,
    owner_id: str,
    *,
    samples: int = 5,
    engine: Any | None = None,
) -> dict[str, Any]:
    """Time ``load_portfolio_control_plane_bundle`` for an owner's projects."""
    projects = await repo.list_projects(owner_id)
    project_ids = [p.id for p in projects]
    cost_since = datetime.now(UTC) - timedelta(days=30)
    stuck_before = datetime.now(UTC) - timedelta(minutes=45)
    timings: list[float] = []
    query_count: int | None = None

    for index in range(max(1, samples)):
        started = time.perf_counter()
        if engine is not None and index == 0:
            with count_sql_queries(engine) as queries:
                await repo.load_portfolio_control_plane_bundle(
                    owner_id,
                    project_ids,
                    cost_since=cost_since,
                    stuck_before=stuck_before,
                )
            query_count = len(queries)
        else:
            await repo.load_portfolio_control_plane_bundle(
                owner_id,
                project_ids,
                cost_since=cost_since,
                stuck_before=stuck_before,
            )
        timings.append((time.perf_counter() - started) * 1000)

    return _timing_result(
        name="portfolio_control_plane",
        timings_ms=timings,
        query_count=query_count,
        extra={"project_count": len(project_ids)},
    )


async def benchmark_semantic_vector_search(
    repo: Any,
    owner_id: str,
    *,
    samples: int = 5,
    engine: Any | None = None,
) -> dict[str, Any]:
    """Time project-scoped vector retrieval when embeddings exist."""
    probe = await repo.db.execute(
        select(SemanticMemoryEntry.project_id)
        .where(
            SemanticMemoryEntry.owner_id == owner_id,
            SemanticMemoryEntry.project_id.is_not(None),
            SemanticMemoryEntry.deleted_at.is_(None),
        )
        .limit(1)
    )
    project_id = probe.scalar_one_or_none()
    if not project_id:
        return {
            "name": "semantic_vector_search",
            "skipped": "no semantic memory rows with embeddings for owner",
        }

    dim_probe = await repo.db.execute(
        select(SemanticMemoryEntry.embedding_vector)
        .where(
            SemanticMemoryEntry.owner_id == owner_id,
            SemanticMemoryEntry.project_id == project_id,
            SemanticMemoryEntry.embedding_vector.is_not(None),
        )
        .limit(1)
    )
    sample_vec = dim_probe.scalar_one_or_none()
    if not sample_vec:
        return {
            "name": "semantic_vector_search",
            "skipped": "no embedding_vector rows available",
            "project_id": project_id,
        }

    query_vec = normalize_embedding_for_vector(list(sample_vec))
    timings: list[float] = []
    query_count: int | None = None

    for index in range(max(1, samples)):
        started = time.perf_counter()
        if engine is not None and index == 0:
            with count_sql_queries(engine) as queries:
                await repo.search_semantic_memory_by_vector(
                    owner_id,
                    project_id,
                    query_vec,
                    limit=12,
                )
            query_count = len(queries)
        else:
            await repo.search_semantic_memory_by_vector(
                owner_id,
                project_id,
                query_vec,
                limit=12,
            )
        timings.append((time.perf_counter() - started) * 1000)

    return _timing_result(
        name="semantic_vector_search",
        timings_ms=timings,
        query_count=query_count,
        extra={"project_id": project_id},
    )


async def benchmark_run_claim_precheck(
    repo: Any,
    *,
    samples: int = 20,
    engine: Any | None = None,
) -> dict[str, Any]:
    """Time worker claim precheck: fetch run + ``is_run_execution_claimable``."""
    probe = await repo.db.execute(
        select(TaskRun.id).order_by(TaskRun.created_at.desc()).limit(1)
    )
    run_id = probe.scalar_one_or_none()
    if not run_id:
        return {"name": "run_claim_precheck", "skipped": "no task_runs rows"}

    timings: list[float] = []
    query_count: int | None = None
    last_status: str | None = None
    claimable = False

    for index in range(max(1, samples)):
        started = time.perf_counter()
        if engine is not None and index == 0:
            with count_sql_queries(engine) as queries:
                run = await repo.get_run_for_worker(run_id)
                claimable = is_run_execution_claimable(run.status if run else None)
            query_count = len(queries)
        else:
            run = await repo.get_run_for_worker(run_id)
            claimable = is_run_execution_claimable(run.status if run else None)
        timings.append((time.perf_counter() - started) * 1000)
        if run is not None:
            last_status = run.status

    return _timing_result(
        name="run_claim_precheck",
        timings_ms=timings,
        query_count=query_count,
        extra={"run_id": run_id, "status": last_status, "claimable": claimable},
    )


async def collect_in_process_benchmarks(
    *,
    owner_id: str,
    samples: int = 5,
) -> dict[str, Any]:
    """Run repository-level hot-path benchmarks against live PostgreSQL."""
    from backend.db.session import SessionLocal, engine
    from backend.modules.orchestration.repository import OrchestrationRepository

    async with SessionLocal() as db:
        repo = OrchestrationRepository(db)
        projects = await repo.list_projects(owner_id)
        if not projects:
            return {
                "skipped": f"owner_id {owner_id!r} has no orchestrator projects",
                "benchmarks": [],
            }

        benchmarks = [
            await benchmark_portfolio_control_plane(
                repo, owner_id, samples=samples, engine=engine
            ),
            await benchmark_semantic_vector_search(
                repo, owner_id, samples=samples, engine=engine
            ),
            await benchmark_run_claim_precheck(repo, samples=max(samples, 10), engine=engine),
        ]
        return {"owner_id": owner_id, "benchmarks": benchmarks}


def metric_path(result: dict[str, Any], field: str = "p95_ms") -> float | None:
    latency = result.get("latency") or {}
    value = latency.get(field)
    return float(value) if value is not None else None


def compare_benchmark_reports(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    threshold: float = 2.0,
    metric: str = "p95_ms",
) -> dict[str, Any]:
    """Return regressions where current p95 exceeds baseline * threshold."""
    baseline_by_name = {
        item["name"]: item
        for item in baseline.get("in_process", {}).get("benchmarks", [])
        if isinstance(item, dict) and item.get("name")
    }
    current_items = current.get("in_process", {}).get("benchmarks", [])
    regressions: list[dict[str, Any]] = []
    for item in current_items:
        if not isinstance(item, dict) or item.get("skipped"):
            continue
        name = item.get("name")
        if not name or name not in baseline_by_name:
            continue
        base_val = metric_path(baseline_by_name[name], metric)
        cur_val = metric_path(item, metric)
        if base_val is None or cur_val is None or base_val <= 0:
            continue
        ratio = cur_val / base_val
        if ratio > threshold:
            regressions.append(
                {
                    "name": name,
                    "metric": metric,
                    "baseline": base_val,
                    "current": cur_val,
                    "ratio": round(ratio, 3),
                    "threshold": threshold,
                }
            )
    return {
        "threshold": threshold,
        "metric": metric,
        "regression_count": len(regressions),
        "regressions": regressions,
        "passed": len(regressions) == 0,
    }


__all__ = [
    "benchmark_portfolio_control_plane",
    "benchmark_run_claim_precheck",
    "benchmark_semantic_vector_search",
    "collect_in_process_benchmarks",
    "compare_benchmark_reports",
    "count_sql_queries",
    "metric_path",
]
