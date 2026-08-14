"""P5.8 — Settings defaults, aliases, and boot without optional flags."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_MINIMAL_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://app:app@localhost:5432/app_db",
    "REDIS_URL": "redis://localhost:6379/0",
    "JWT_SECRET": "integration-test-secret-with-enough-entropy",
    "JWT_ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "15",
    "REFRESH_TOKEN_EXPIRE_DAYS": "7",
    "APP_ENV": "dev",
    # Override repo `.env` files so we assert documented defaults, not local dev overrides.
    "CELERY_TASK_ALWAYS_EAGER": "false",
    "RAG_PYTHON_FALLBACK_ENABLED": "false",
    "VECTOR_FALLBACK_JSON": "false",
    "VECTOR_WRITE_EMBEDDING_JSON": "false",
    "AI_RETRIEVE_PYTHON_FALLBACK_ENABLED": "false",
    "MEMORY_LLM_EXTRACTION_ENABLED": "false",
    "METRICS_QUEUE_REFRESH_ENABLED": "false",
}


def test_settings_construct_with_minimal_required_env(monkeypatch):
    for key, value in _MINIMAL_ENV.items():
        monkeypatch.setenv(key, value)
    from backend.core.config import Settings

    cfg = Settings()
    assert cfg.DATABASE_URL.startswith("postgresql+asyncpg://")
    assert cfg.REDIS_URL.startswith("redis://")
    assert cfg.APP_ENV == "dev"


def test_optional_feature_flags_default_safe(monkeypatch):
    for key, value in _MINIMAL_ENV.items():
        monkeypatch.setenv(key, value)
    from backend.core.config import Settings

    cfg = Settings()
    assert cfg.RAG_PYTHON_FALLBACK_ENABLED is False
    assert cfg.VECTOR_FALLBACK_JSON is False
    assert cfg.vector_python_fallback_enabled is False
    assert cfg.VECTOR_WRITE_EMBEDDING_JSON is False
    assert cfg.AI_RETRIEVE_PYTHON_FALLBACK_ENABLED is False
    assert cfg.MEMORY_LLM_EXTRACTION_ENABLED is False
    assert cfg.ORCHESTRATION_DURABLE_QUEUE_BACKEND == "celery"
    assert cfg.CELERY_TASK_ALWAYS_EAGER is False
    assert cfg.METRICS_QUEUE_REFRESH_ENABLED is False


def test_vector_fallback_alias_or_semantics(monkeypatch):
    for key, value in _MINIMAL_ENV.items():
        monkeypatch.setenv(key, value)
    from backend.core.config import Settings

    monkeypatch.setenv("VECTOR_FALLBACK_JSON", "true")
    cfg = Settings()
    assert cfg.RAG_PYTHON_FALLBACK_ENABLED is False
    assert cfg.vector_python_fallback_enabled is True

    monkeypatch.delenv("VECTOR_FALLBACK_JSON", raising=False)
    monkeypatch.setenv("RAG_PYTHON_FALLBACK_ENABLED", "true")
    cfg = Settings()
    assert cfg.vector_python_fallback_enabled is True


def test_celery_urls_fallback_to_redis(monkeypatch):
    for key, value in _MINIMAL_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
    from backend.core.config import Settings

    cfg = Settings()
    assert cfg.celery_broker_url == cfg.REDIS_URL
    assert cfg.celery_result_backend == cfg.REDIS_URL


def test_database_pool_role_defaults(monkeypatch):
    for key, value in _MINIMAL_ENV.items():
        monkeypatch.setenv(key, value)
    from backend.core.config import Settings

    cfg = Settings()
    assert cfg.DATABASE_POOL_SIZE == 10
    assert cfg.DATABASE_POOL_SIZE_WORKER == 5
    assert cfg.REDIS_MAX_CONNECTIONS == 50
    assert cfg.effective_database_pool_size == 10


def test_production_security_validation(monkeypatch):
    for key, value in _MINIMAL_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com")
    from backend.core.config import Settings

    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings()


def test_langgraph_not_a_dependency():
    lock = Path(__file__).resolve().parents[1] / "uv.lock"
    requires_dist = lock.read_text(encoding="utf-8").split("requires-dist = [", 1)[-1].split("]", 1)[0]
    assert "langgraph" not in requires_dist


def test_fresh_process_boot_without_optional_flags():
    """Import Settings + FastAPI app in a clean process with only required env."""
    repo_root = Path(__file__).resolve().parents[2]
    code = (
        "from backend.core.config import Settings; "
        "s = Settings(); "
        "assert s.ORCHESTRATION_DURABLE_QUEUE_BACKEND == 'celery'; "
        "assert not s.vector_python_fallback_enabled; "
        "from backend.api.main import app; "
        "assert app.title"
    )
    env = {**os.environ, **{k: str(v) for k, v in _MINIMAL_ENV.items()}}
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_langgraph_shim_still_removed():
    assert not Path("backend/modules/orchestration/execution/langgraph_runner.py").exists()
