from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import TaskRun

WORKSPACE_ROOT = Path(__file__).resolve().parents[2] / "workspaces"
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
ALLOWED_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".geojson", ".log"}
DENIED_NAMES = {".env", "id_rsa", "id_dsa", "credentials", "secrets.json"}


def _safe_filename(filename: str) -> str:
    raw = filename.strip().replace("\\", "/")
    if not raw or raw.endswith("/"):
        raise HTTPException(status_code=400, detail="Filename is required.")
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise HTTPException(status_code=400, detail="Workspace path escapes are not allowed.")
    if any(part in DENIED_NAMES for part in path.parts):
        raise HTTPException(status_code=400, detail="Secret-like filenames are not allowed.")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File extension is not allowed.")
    return path.as_posix()


def _resolve_inside(root: Path, relative_path: str) -> Path:
    safe_name = _safe_filename(relative_path)
    root_resolved = root.resolve()
    target = (root_resolved / safe_name).resolve()
    if root_resolved != target and root_resolved not in target.parents:
        raise HTTPException(status_code=400, detail="Workspace path escapes are not allowed.")
    return target


async def run_workspace_root(db: AsyncSession, run_id: str) -> Path:
    run = await db.get(TaskRun, run_id)
    if run is None or run.task_id is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return WORKSPACE_ROOT / "projects" / run.project_id / "tasks" / run.task_id / "runs" / run.id


async def create_workspace_for_run(db: AsyncSession, run_id: str) -> Path:
    root = await run_workspace_root(db, run_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


async def list_run_workspace_files(db: AsyncSession, run_id: str) -> list[dict[str, str | int]]:
    root = await create_workspace_for_run(db, run_id)
    files: list[dict[str, str | int]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "name": path.name,
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                }
            )
    return files


async def write_artifact(
    db: AsyncSession,
    run_id: str,
    filename: str,
    content: str,
) -> Path:
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_ARTIFACT_BYTES:
        raise HTTPException(status_code=400, detail="Artifact exceeds max file size.")
    root = await create_workspace_for_run(db, run_id)
    target = _resolve_inside(root, filename)
    if target.exists():
        target = target.with_name(f"{target.stem}-{uuid4().hex[:8]}{target.suffix}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    return target
