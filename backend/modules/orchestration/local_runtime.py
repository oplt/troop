from __future__ import annotations

import asyncio
import logging
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import ProviderConfig

logger = logging.getLogger(__name__)

_PROCESSES: dict[str, subprocess.Popen[bytes]] = {}


def _runtime_config(provider: ProviderConfig) -> dict[str, Any]:
    value = (provider.metadata_json or {}).get("local_runtime")
    return value if isinstance(value, dict) else {}


def _default_health_url(provider: ProviderConfig) -> str | None:
    base_url = (provider.base_url or "").rstrip("/")
    if provider.provider_type == "ollama":
        return f"{base_url or 'http://localhost:11434'}/api/tags"
    if provider.provider_type == "openai_compatible" and base_url:
        return f"{base_url}/models"
    return None


async def _health_ok(url: str | None) -> bool:
    if not url:
        return False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
        return 200 <= response.status_code < 300
    except Exception:
        return False


def _command_for(provider: ProviderConfig, config: dict[str, Any]) -> list[str] | None:
    raw_command = str(config.get("command") or "").replace("\\\n", " ").strip()
    if not raw_command and provider.provider_type == "ollama":
        raw_command = "ollama serve"
    if not raw_command:
        return None
    return shlex.split(raw_command)


def _working_dir(config: dict[str, Any]) -> str | None:
    raw_path = str(config.get("working_dir") or "").strip()
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if not path.is_dir():
        raise FileNotFoundError(f"Local runtime working directory not found: {path}")
    return str(path)


def _runtime_log_path(provider: ProviderConfig) -> Path:
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"local-runtime-{provider.id}.log"


def _tail_log(path: Path, limit: int = 2000) -> str:
    try:
        data = path.read_text(errors="replace")
    except Exception:
        return ""
    return data[-limit:].strip()


async def _mark_runtime_status(
    db: AsyncSession,
    provider: ProviderConfig,
    *,
    status: str,
    detail: str | None = None,
    pid: int | None = None,
) -> None:
    metadata = dict(provider.metadata_json or {})
    runtime = dict(metadata.get("local_runtime") or {})
    runtime["status"] = status
    if detail:
        runtime["last_error"] = detail
    elif "last_error" in runtime:
        runtime.pop("last_error", None)
    if pid is not None:
        runtime["pid"] = pid
    elif "pid" in runtime and status not in {"running", "starting"}:
        runtime.pop("pid", None)
    metadata["local_runtime"] = runtime
    provider.metadata_json = metadata
    await db.flush()


async def start_local_runtime(db: AsyncSession, provider: ProviderConfig) -> dict[str, Any]:
    config = _runtime_config(provider)
    is_local_runtime = provider.provider_type == "ollama" or config.get("mode") == "managed"
    if not is_local_runtime:
        await _mark_runtime_status(db, provider, status="not_supported", detail="Provider is not a local server runtime")
        return {"status": "not_supported"}

    process = _PROCESSES.get(provider.id)
    if process is not None and process.poll() is None:
        await _mark_runtime_status(db, provider, status="running", pid=process.pid)
        return {"status": "running", "pid": process.pid}

    health_url = str(config.get("health_url") or "").strip() or _default_health_url(provider)
    if await _health_ok(health_url):
        await _mark_runtime_status(db, provider, status="already_running")
        logger.info("local_runtime already_running provider_id=%s name=%s", provider.id, provider.name)
        return {"status": "already_running"}

    command = _command_for(provider, config)
    if not command:
        await _mark_runtime_status(db, provider, status="not_configured", detail="Missing local runtime command")
        return {"status": "not_configured"}

    log_path = _runtime_log_path(provider)
    try:
        log_file = log_path.open("ab")
        process = subprocess.Popen(
            command,
            cwd=_working_dir(config),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as exc:
        await _mark_runtime_status(db, provider, status="failed", detail=str(exc))
        logger.warning("local_runtime start_failed provider_id=%s name=%s error=%s", provider.id, provider.name, exc)
        return {"status": "failed", "detail": str(exc)}

    _PROCESSES[provider.id] = process
    await _mark_runtime_status(db, provider, status="starting", detail=f"Starting; log: {log_path}", pid=process.pid)
    logger.info("local_runtime starting provider_id=%s name=%s pid=%s", provider.id, provider.name, process.pid)
    startup_timeout_seconds = float(config.get("startup_timeout_seconds") or 30)
    deadline = time.monotonic() + startup_timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            detail = _tail_log(log_path) or f"Process exited with code {process.returncode}; log: {log_path}"
            await _mark_runtime_status(db, provider, status="exited", detail=detail)
            return {"status": "exited", "detail": detail}
        if await _health_ok(health_url):
            await _mark_runtime_status(db, provider, status="running", pid=process.pid)
            return {"status": "running", "pid": process.pid}
        await asyncio.sleep(1.0)
    if process.poll() is None:
        detail = f"Process started but health URL is not ready: {health_url}; log: {log_path}"
        await _mark_runtime_status(db, provider, status="starting", detail=detail, pid=process.pid)
        return {"status": "starting", "pid": process.pid, "detail": detail}
    detail = _tail_log(log_path) or f"Process exited with code {process.returncode}; log: {log_path}"
    await _mark_runtime_status(db, provider, status="exited", detail=detail)
    return {"status": "exited", "detail": detail}


async def stop_managed_local_runtimes() -> None:
    for provider_id, process in list(_PROCESSES.items()):
        if process.poll() is not None:
            _PROCESSES.pop(provider_id, None)
            continue
        process.terminate()
        try:
            await asyncio.to_thread(process.wait, 10)
        except subprocess.TimeoutExpired:
            process.kill()
            await asyncio.to_thread(process.wait)
        logger.info("managed_local_runtime stopped provider_id=%s pid=%s", provider_id, process.pid)
        _PROCESSES.pop(provider_id, None)
