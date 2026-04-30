from __future__ import annotations

import fnmatch
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_ALLOWED_BRANCHES = ["main", "master", "develop", "feature/*", "fix/*", "agent/*"]
DEFAULT_COMMAND_ALLOWLIST = ["pnpm", "uv", "pytest", "ruff", "mypy", "git status", "git diff", "rg"]
DEFAULT_FILE_DENYLIST = [".env", ".env.*", "**/.env", "**/.env.*", "**/node_modules/**", "**/.git/**"]
DEFAULT_MAX_DIFF_BYTES = 200_000


class LocalRepoError(ValueError):
    pass


@dataclass(frozen=True)
class CommandResult:
    command: str
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


def normalize_workspace(raw: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(raw or {})
    repo_path = str(data.get("repo_path") or data.get("path") or "").strip()
    allowlist = [str(item).strip() for item in data.get("command_allowlist") or [] if str(item).strip()]
    allowed_branches = [str(item).strip() for item in data.get("allowed_branches") or [] if str(item).strip()]
    file_allowlist = [str(item).strip() for item in data.get("file_allowlist") or [] if str(item).strip()]
    file_denylist = [str(item).strip() for item in data.get("file_denylist") or [] if str(item).strip()]
    dirty_policy = str(data.get("dirty_worktree_policy") or "block").strip()
    if dirty_policy not in {"block", "warn", "allow"}:
        dirty_policy = "block"
    return {
        "enabled": bool(data.get("enabled", bool(repo_path))),
        "repo_path": repo_path,
        "allowed_branches": allowed_branches or list(DEFAULT_ALLOWED_BRANCHES),
        "dirty_worktree_policy": dirty_policy,
        "file_allowlist": file_allowlist,
        "file_denylist": file_denylist or list(DEFAULT_FILE_DENYLIST),
        "max_diff_bytes": int(data.get("max_diff_bytes") or DEFAULT_MAX_DIFF_BYTES),
        "command_allowlist": allowlist or list(DEFAULT_COMMAND_ALLOWLIST),
        "worktree_root": str(data.get("worktree_root") or "").strip(),
    }


def _run(args: list[str], cwd: Path, timeout_seconds: int = 10) -> str:
    completed = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise LocalRepoError(detail or f"Command failed: {' '.join(args)}")
    return completed.stdout.strip()


def _repo_root(path: str) -> Path:
    if not path:
        raise LocalRepoError("Repository path is required.")
    repo_path = Path(path).expanduser().resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        raise LocalRepoError("Repository path does not exist.")
    root = _run(["git", "rev-parse", "--show-toplevel"], repo_path)
    return Path(root).resolve()


def _is_branch_allowed(branch: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(branch, pattern) for pattern in patterns)


def inspect_workspace(raw: dict[str, Any] | None) -> dict[str, Any]:
    workspace = normalize_workspace(raw)
    root = _repo_root(workspace["repo_path"])
    branch = _run(["git", "branch", "--show-current"], root) or "HEAD"
    status = _run(["git", "status", "--short"], root)
    remote = _run(["git", "remote", "-v"], root) if (root / ".git").exists() else ""
    last_commit = _run(["git", "log", "-1", "--pretty=format:%H%x09%an%x09%aI%x09%s"], root)
    diff_bytes = len(_run(["git", "diff", "--binary"], root, timeout_seconds=20).encode("utf-8"))
    branch_allowed = _is_branch_allowed(branch, workspace["allowed_branches"])
    dirty = bool(status.strip())
    policy = workspace["dirty_worktree_policy"]
    blocked_reasons: list[str] = []
    if not branch_allowed:
        blocked_reasons.append(f"Branch '{branch}' is not allowed.")
    if dirty and policy == "block":
        blocked_reasons.append("Worktree has uncommitted changes and dirty policy is block.")
    if diff_bytes > workspace["max_diff_bytes"]:
        blocked_reasons.append("Current diff exceeds max diff size.")
    return {
        "workspace": {**workspace, "repo_path": str(root)},
        "valid": not blocked_reasons,
        "blocked_reasons": blocked_reasons,
        "branch": branch,
        "dirty": dirty,
        "status": status,
        "remotes": remote,
        "last_commit": last_commit,
        "diff_bytes": diff_bytes,
        "inspected_at": datetime.now(UTC).isoformat(),
    }


def branch_name_for_task(task_id: str, title: str | None = None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "task").lower()).strip("-")[:48] or "task"
    return f"agent/{task_id[:8]}-{slug}"


def create_isolated_worktree(raw: dict[str, Any] | None, *, task_id: str, title: str | None = None) -> dict[str, Any]:
    status = inspect_workspace(raw)
    if not status["valid"]:
        raise LocalRepoError("; ".join(status["blocked_reasons"]))
    workspace = status["workspace"]
    root = Path(workspace["repo_path"]).resolve()
    branch = branch_name_for_task(task_id, title)
    worktree_root = Path(workspace.get("worktree_root") or root.parent / f"{root.name}.worktrees").expanduser().resolve()
    worktree_root.mkdir(parents=True, exist_ok=True)
    target = worktree_root / branch.replace("/", "-")
    if target.exists():
        raise LocalRepoError(f"Worktree already exists: {target}")
    _run(["git", "worktree", "add", "-b", branch, str(target)], root, timeout_seconds=60)
    return {"branch": branch, "path": str(target), "base_repo_path": str(root), "created_at": datetime.now(UTC).isoformat()}


def command_allowed(command: str, allowlist: list[str]) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    normalized = " ".join(parts[:2]) if len(parts) > 1 else parts[0]
    return any(normalized == item or parts[0] == item for item in allowlist)


def run_safe_command(
    raw: dict[str, Any] | None,
    *,
    command: str,
    cwd: str | None = None,
    timeout_seconds: int = 60,
) -> CommandResult:
    workspace = normalize_workspace(raw)
    root = _repo_root(workspace["repo_path"])
    if not command_allowed(command, workspace["command_allowlist"]):
        raise LocalRepoError("Command is not in workspace allowlist.")
    workdir = (root / cwd).resolve() if cwd else root
    if not str(workdir).startswith(str(root)):
        raise LocalRepoError("Command working directory must stay inside repository.")
    start = datetime.now(UTC)
    try:
        completed = subprocess.run(
            shlex.split(command),
            cwd=str(workdir),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        completed = subprocess.CompletedProcess(
            args=command,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "Command timed out.",
        )
        timed_out = True
    duration_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)
    return CommandResult(
        command=command,
        cwd=str(workdir),
        exit_code=int(completed.returncode),
        stdout=(completed.stdout or "")[-8000:],
        stderr=(completed.stderr or "")[-8000:],
        duration_ms=duration_ms,
        timed_out=timed_out,
    )


def file_allowed(relative_path: str, workspace: dict[str, Any]) -> bool:
    rel = relative_path.strip().lstrip("/")
    deny = workspace["file_denylist"]
    allow = workspace["file_allowlist"]
    if any(fnmatch.fnmatch(rel, pattern) for pattern in deny):
        return False
    return not allow or any(fnmatch.fnmatch(rel, pattern) for pattern in allow)


def read_repo_file(raw: dict[str, Any] | None, relative_path: str, limit: int = 40_000) -> dict[str, Any]:
    workspace = normalize_workspace(raw)
    root = _repo_root(workspace["repo_path"])
    rel = relative_path.strip().lstrip("/")
    if not file_allowed(rel, workspace):
        raise LocalRepoError("File path is denied by workspace policy.")
    path = (root / rel).resolve()
    if not str(path).startswith(str(root)) or not path.is_file():
        raise LocalRepoError("File not found inside repository.")
    data = path.read_text(errors="replace")
    return {"path": rel, "content": data[:limit], "truncated": len(data) > limit}


def build_context_pack(raw: dict[str, Any] | None, *, issue_text: str, acceptance_criteria: str | None = None) -> dict[str, Any]:
    workspace = normalize_workspace(raw)
    root = _repo_root(workspace["repo_path"])
    tree = run_safe_command(workspace, command="rg --files", timeout_seconds=20).stdout.splitlines()[:600]
    agent_files = [name for name in ["AGENTS.md", "CLAUDE.md", "README.md", "package.json", "pyproject.toml"] if (root / name).exists()]
    file_payloads = [read_repo_file(workspace, name, limit=12_000) for name in agent_files]
    status = inspect_workspace(workspace)
    return {
        "repo": status,
        "issue_text": issue_text,
        "acceptance_criteria": acceptance_criteria,
        "tree": tree,
        "files": file_payloads,
        "constraints": {
            "command_allowlist": workspace["command_allowlist"],
            "file_allowlist": workspace["file_allowlist"],
            "file_denylist": workspace["file_denylist"],
            "max_diff_bytes": workspace["max_diff_bytes"],
            "dirty_worktree_policy": workspace["dirty_worktree_policy"],
        },
        "created_at": datetime.now(UTC).isoformat(),
    }
