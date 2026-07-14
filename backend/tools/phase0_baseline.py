"""Collect a repeatable Phase 0 performance baseline.

Examples from the repository root::

    python backend/tools/phase0_baseline.py \
        --url http://127.0.0.1:8000/health/live \
        --pid 12345 \
        --redis-url redis://127.0.0.1:6379/0 \
        --queue celery \
        --output artifacts/phase0-baseline.json

The tool deliberately reports failures in the JSON artifact instead of
silently replacing them with zeros.  This allows a baseline captured without
PostgreSQL, Redis, or a running API to remain useful and auditable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import resource
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


def percentile(values: list[float], fraction: float) -> float | None:
    """Return an interpolated percentile in milliseconds, or None if empty."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    weight = position - lower
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * weight
    return round(value, 3)


def summarize_timings(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "min_ms": round(min(values), 3) if values else None,
        "max_ms": round(max(values), 3) if values else None,
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
    }


def _safe_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


async def benchmark_url(
    client: httpx.AsyncClient,
    url: str,
    *,
    requests: int,
    concurrency: int,
) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    timings: list[float] = []
    statuses: Counter[str] = Counter()
    errors: list[str] = []

    async def one_request() -> None:
        async with semaphore:
            started = time.perf_counter()
            try:
                response = await client.get(url)
                elapsed_ms = (time.perf_counter() - started) * 1000
                timings.append(elapsed_ms)
                statuses[str(response.status_code)] += 1
            except Exception as exc:
                errors.append(_safe_error(exc))

    await asyncio.gather(*(one_request() for _ in range(max(0, requests))))
    return {
        "url": url,
        "requests": requests,
        "concurrency": max(1, concurrency),
        "successful_samples": len(timings),
        "status_counts": dict(statuses),
        "errors": errors[:20],
        "latency": summarize_timings(timings),
    }


async def benchmark_redis(redis_url: str, *, samples: int, timeout: float) -> dict[str, Any]:
    try:
        import redis.asyncio as redis

        client = redis.from_url(redis_url, socket_timeout=timeout)
        timings: list[float] = []
        try:
            for _ in range(max(1, samples)):
                started = time.perf_counter()
                await client.ping()
                timings.append((time.perf_counter() - started) * 1000)
        finally:
            await client.aclose()
        return {"url": _redact_url(redis_url), "latency": summarize_timings(timings)}
    except Exception as exc:
        return {"url": _redact_url(redis_url), "error": _safe_error(exc)}


async def benchmark_database(
    database_url: str,
    *,
    samples: int,
    timeout: float,
) -> dict[str, Any]:
    try:
        import asyncpg

        dsn = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
        connection = await asyncpg.connect(dsn=dsn, timeout=timeout)
        timings: list[float] = []
        try:
            for _ in range(max(1, samples)):
                started = time.perf_counter()
                await connection.fetchval("SELECT 1")
                timings.append((time.perf_counter() - started) * 1000)
        finally:
            await connection.close()
        return {"url": _redact_url(database_url), "latency": summarize_timings(timings)}
    except Exception as exc:
        return {"url": _redact_url(database_url), "error": _safe_error(exc)}


async def queue_depths(
    redis_url: str,
    queues: list[str],
    *,
    timeout: float,
) -> dict[str, Any]:
    if not queues:
        return {"queues": {}, "skipped": "no queue names supplied"}
    try:
        import redis.asyncio as redis

        client = redis.from_url(redis_url, socket_timeout=timeout)
        try:
            values: dict[str, int] = {}
            for queue in queues:
                values[queue] = int(await client.llen(queue))
            return {"queues": values}
        finally:
            await client.aclose()
    except Exception as exc:
        return {"queues": {}, "error": _safe_error(exc)}


def _proc_sample(pid: int) -> dict[str, int] | None:
    try:
        with (Path(f"/proc/{pid}/stat")).open(encoding="utf-8") as file:
            fields = file.read().rstrip().split(") ", 1)[1].split()
        clock_ticks = int(os.sysconf("SC_CLK_TCK"))
        cpu_seconds = (int(fields[11]) + int(fields[12])) / clock_ticks
        with Path(f"/proc/{pid}/statm").open(encoding="utf-8") as file:
            resident_pages = int(file.read().split()[1])
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        return {"cpu_seconds": cpu_seconds, "rss_bytes": resident_pages * page_size}
    except (FileNotFoundError, IndexError, OSError, ValueError):
        return None


def process_snapshot(pid: int | None) -> dict[str, Any]:
    target_pid = pid or os.getpid()
    proc = _proc_sample(target_pid)
    if proc is not None:
        scope = "target_process" if pid else "benchmark_process"
        return {"pid": target_pid, "scope": scope, **proc}
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "pid": target_pid,
        "scope": "benchmark_process",
        "cpu_seconds": usage.ru_utime + usage.ru_stime,
        "rss_bytes": usage.ru_maxrss * 1024,
    }


def _redact_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme, remainder = url.split("://", 1)
    _, host = remainder.rsplit("@", 1)
    return f"{scheme}://***@{host}"


def _git_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


async def collect(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    before = process_snapshot(args.pid)
    async with httpx.AsyncClient(timeout=args.timeout, follow_redirects=False) as client:
        endpoint_results = [
            await benchmark_url(
                client,
                url,
                requests=args.requests,
                concurrency=args.concurrency,
            )
            for url in args.url
        ]
    redis_url = args.redis_url or os.getenv("REDIS_URL")
    database_url = args.database_url or os.getenv("DATABASE_URL")
    redis_result = (
        await benchmark_redis(redis_url, samples=args.samples, timeout=args.timeout)
        if redis_url
        else {"skipped": "REDIS_URL not set"}
    )
    database_result = (
        await benchmark_database(database_url, samples=args.samples, timeout=args.timeout)
        if database_url
        else {"skipped": "DATABASE_URL not set"}
    )
    queues = (
        await queue_depths(redis_url, args.queue, timeout=args.timeout)
        if redis_url
        else {"skipped": "REDIS_URL not set"}
    )
    after = process_snapshot(args.pid)
    elapsed = max(time.perf_counter() - started, 0.001)
    cpu_delta = after["cpu_seconds"] - before["cpu_seconds"]
    return {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "git_revision": _git_revision(),
        "parameters": {
            "urls": args.url,
            "requests_per_url": args.requests,
            "concurrency": args.concurrency,
            "samples": args.samples,
            "timeout_seconds": args.timeout,
        },
        "endpoints": endpoint_results,
        "redis": redis_result,
        "database": database_result,
        "queue_depth": queues,
        "process": {
            "before": before,
            "after": after,
            "elapsed_seconds": round(elapsed, 3),
            "cpu_percent_of_one_core": round(max(0.0, cpu_delta / elapsed * 100), 3),
            "rss_delta_bytes": after["rss_bytes"] - before["rss_bytes"],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        action="append",
        default=None,
        help="HTTP endpoint to sample; repeat for multiple endpoints.",
    )
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--pid", type=int, help="Server PID to sample; defaults to this process.")
    parser.add_argument("--redis-url")
    parser.add_argument("--database-url")
    parser.add_argument("--queue", action="append", default=[], help="Redis/Celery queue name.")
    parser.add_argument("--output", type=Path, help="Write JSON artifact to this path.")
    args = parser.parse_args()
    if not args.url:
        args.url = ["http://127.0.0.1:8000/health/live"]
    return args


def main() -> None:
    args = parse_args()
    if args.requests < 0 or args.concurrency < 1 or args.samples < 1:
        raise SystemExit("requests must be >= 0; concurrency and samples must be >= 1")
    report = asyncio.run(collect(args))
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
