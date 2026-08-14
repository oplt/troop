from __future__ import annotations

import threading
import time

import pytest
from backend.db.pool_metrics import register_db_pool_checkout_metrics
from backend.modules.observability.metrics import DB_POOL_CHECKOUT_WAIT, metrics_registry
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool


def _histogram_observations(metric_name: str, *, role: str) -> tuple[int, float]:
    snapshot = metrics_registry.snapshot()
    metric = snapshot.get(metric_name)
    if not metric:
        return 0, 0.0
    key = (role,)
    hist = metric["histograms"].get(key)
    if hist is None:
        return 0, 0.0
    counts = hist["buckets"]
    return int(counts[-1]), hist["sum"]


@pytest.fixture
def tiny_pool_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=10,
        connect_args={"check_same_thread": False},
    )
    metrics_registry.reset()
    register_db_pool_checkout_metrics(engine, role="test")
    try:
        yield engine
    finally:
        engine.dispose()
        metrics_registry.reset()


def test_session_construction_without_checkout_records_no_wait(tiny_pool_engine) -> None:
    from sqlalchemy.orm import Session

    Session(bind=tiny_pool_engine)
    count, total = _histogram_observations(DB_POOL_CHECKOUT_WAIT, role="test")
    assert count == 0
    assert total == 0.0


def test_pool_checkout_wait_histogram_records_contention(tiny_pool_engine) -> None:
    release = threading.Event()

    def hold_connection() -> None:
        with tiny_pool_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            release.wait(timeout=5)

    holder = threading.Thread(target=hold_connection)
    holder.start()
    time.sleep(0.05)

    started = time.perf_counter()
    with tiny_pool_engine.connect() as connection:
        waited = time.perf_counter() - started
        connection.execute(text("SELECT 1"))

    release.set()
    holder.join(timeout=5)

    count, total = _histogram_observations(DB_POOL_CHECKOUT_WAIT, role="test")
    assert count >= 2
    assert total >= 0.05
    assert waited >= 0.04


def test_register_is_idempotent(tiny_pool_engine) -> None:
    register_db_pool_checkout_metrics(tiny_pool_engine, role="test")
    with tiny_pool_engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    count, _ = _histogram_observations(DB_POOL_CHECKOUT_WAIT, role="test")
    assert count == 1


def test_checkout_wait_uses_role_label() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        connect_args={"check_same_thread": False},
    )
    metrics_registry.reset()
    register_db_pool_checkout_metrics(engine, role="worker")
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        worker_count, _ = _histogram_observations(DB_POOL_CHECKOUT_WAIT, role="worker")
        api_count, _ = _histogram_observations(DB_POOL_CHECKOUT_WAIT, role="api")
        assert worker_count == 1
        assert api_count == 0
    finally:
        engine.dispose()
        metrics_registry.reset()
