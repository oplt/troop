"""Bounded Phase 7 load probe for a running Troop API.

This tool intentionally performs read-only HTTP requests. Dependency outages,
pool exhaustion, duplicate delivery, and slow SSE scenarios are exercised by
the pytest failure-injection suite, never through a production backdoor.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass

import httpx


@dataclass(frozen=True, slots=True)
class LoadSummary:
    url: str
    requests: int
    concurrency: int
    completed: int
    failures: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction)))
    return round(ordered[index], 2)


async def run_http_load(
    url: str,
    *,
    requests: int = 20,
    concurrency: int = 4,
    timeout_seconds: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LoadSummary:
    if requests < 1:
        raise ValueError("requests must be >= 1")
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    concurrency = min(concurrency, requests)
    semaphore = asyncio.Semaphore(concurrency)
    durations: list[float] = []
    failures = 0
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        limits=limits,
        transport=transport,
    ) as client:

        async def request_once() -> None:
            nonlocal failures
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get(url)
                    if response.status_code >= 500:
                        failures += 1
                except httpx.HTTPError:
                    failures += 1
                finally:
                    durations.append((time.perf_counter() - started) * 1000.0)

        await asyncio.gather(*(request_once() for _ in range(requests)))

    return LoadSummary(
        url=url,
        requests=requests,
        concurrency=concurrency,
        completed=len(durations),
        failures=failures,
        p50_ms=percentile(durations, 0.50),
        p95_ms=percentile(durations, 0.95),
        p99_ms=percentile(durations, 0.99),
        max_ms=round(max(durations, default=0.0), 2),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/health/live")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    summary = asyncio.run(
        run_http_load(
            args.url,
            requests=args.requests,
            concurrency=args.concurrency,
            timeout_seconds=args.timeout,
        )
    )
    print(json.dumps(asdict(summary), sort_keys=True))


if __name__ == "__main__":
    main()


__all__ = ["LoadSummary", "percentile", "run_http_load"]
