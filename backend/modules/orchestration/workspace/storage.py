"""Storage port and local adapter for run workspace files."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

WORKSPACE_ROOT = Path(__file__).resolve().parents[3] / "workspaces"
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
ALLOWED_EXTENSIONS = frozenset({".txt", ".md", ".json", ".csv", ".geojson", ".log"})
DENIED_NAMES = frozenset({".env", "id_rsa", "id_dsa", "credentials", "secrets.json"})


class WorkspacePathError(ValueError):
    """A workspace key or filename violates the storage path policy."""


class WorkspaceSizeError(ValueError):
    """Workspace content exceeds the configured size limit."""


@dataclass(frozen=True, slots=True)
class StoredWorkspaceFile:
    name: str
    path: str
    size_bytes: int
    location: str


class WorkspaceStorage(Protocol):
    """Storage-neutral operations needed by orchestration run workspaces."""

    async def list_files(self, workspace_key: str) -> list[StoredWorkspaceFile]: ...

    async def write_text(
        self,
        workspace_key: str,
        filename: str,
        content: str,
    ) -> StoredWorkspaceFile: ...


def _safe_relative_path(value: str, *, require_extension: bool) -> str:
    raw = value.strip().replace("\\", "/")
    if not raw or raw.endswith("/"):
        raise WorkspacePathError("A relative workspace path is required.")
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise WorkspacePathError("Workspace path escapes are not allowed.")
    if any(part.lower() in DENIED_NAMES for part in path.parts):
        raise WorkspacePathError("Secret-like filenames are not allowed.")
    if require_extension and path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise WorkspacePathError("File extension is not allowed.")
    return path.as_posix()


def _resolve_inside(root: Path, relative_path: str, *, require_extension: bool = True) -> Path:
    safe_name = _safe_relative_path(relative_path, require_extension=require_extension)
    root_resolved = root.resolve()
    target = (root_resolved / safe_name).resolve()
    if root_resolved != target and root_resolved not in target.parents:
        raise WorkspacePathError("Workspace path escapes are not allowed.")
    return target


class LocalWorkspaceStorage:
    """Local filesystem adapter with bounded, off-event-loop operations."""

    def __init__(self, root: Path = WORKSPACE_ROOT) -> None:
        self.root = root

    def _workspace_root(self, workspace_key: str) -> Path:
        return _resolve_inside(self.root, workspace_key, require_extension=False)

    async def list_files(self, workspace_key: str) -> list[StoredWorkspaceFile]:
        root = self._workspace_root(workspace_key)
        return await asyncio.to_thread(self._list_files_sync, root)

    async def write_text(
        self,
        workspace_key: str,
        filename: str,
        content: str,
    ) -> StoredWorkspaceFile:
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_ARTIFACT_BYTES:
            raise WorkspaceSizeError("Artifact exceeds max file size.")
        root = self._workspace_root(workspace_key)
        return await asyncio.to_thread(self._write_bytes_sync, root, filename, encoded)

    @staticmethod
    def _list_files_sync(root: Path) -> list[StoredWorkspaceFile]:
        root.mkdir(parents=True, exist_ok=True)
        files: list[StoredWorkspaceFile] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            files.append(
                StoredWorkspaceFile(
                    name=path.name,
                    path=path.relative_to(root).as_posix(),
                    size_bytes=path.stat().st_size,
                    location=str(path),
                )
            )
        return files

    @staticmethod
    def _write_bytes_sync(
        root: Path,
        filename: str,
        content: bytes,
    ) -> StoredWorkspaceFile:
        root.mkdir(parents=True, exist_ok=True)
        target = _resolve_inside(root, filename)
        if target.exists():
            target = target.with_name(f"{target.stem}-{uuid4().hex[:8]}{target.suffix}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return StoredWorkspaceFile(
            name=target.name,
            path=target.relative_to(root).as_posix(),
            size_bytes=len(content),
            location=str(target),
        )


__all__ = [
    "ALLOWED_EXTENSIONS",
    "DENIED_NAMES",
    "MAX_ARTIFACT_BYTES",
    "LocalWorkspaceStorage",
    "StoredWorkspaceFile",
    "WorkspacePathError",
    "WorkspaceSizeError",
    "WorkspaceStorage",
]
