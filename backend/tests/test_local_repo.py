from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backend.modules.orchestration.local_repo import (
    LocalRepoError,
    branch_name_for_task,
    command_allowed,
    inspect_workspace,
    read_repo_file,
    run_safe_command,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    (root / "README.md").write_text("hello\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "init")
    return root


def test_inspect_workspace_blocks_dirty_repo(repo: Path) -> None:
    (repo / "README.md").write_text("changed\n")

    status = inspect_workspace({"repo_path": str(repo), "dirty_worktree_policy": "block"})

    assert status["valid"] is False
    assert status["dirty"] is True
    assert any("dirty policy is block" in reason for reason in status["blocked_reasons"])


def test_command_allowlist_supports_subcommands_without_broad_git(repo: Path) -> None:
    assert command_allowed("git status --short", ["git status"])
    assert not command_allowed("git reset --hard", ["git status", "git diff"])

    result = run_safe_command({"repo_path": str(repo), "command_allowlist": ["git status"]}, command="git status --short")

    assert result.exit_code == 0


def test_read_repo_file_honors_denylist(repo: Path) -> None:
    (repo / ".env").write_text("SECRET=value\n")

    with pytest.raises(LocalRepoError):
        read_repo_file({"repo_path": str(repo), "file_denylist": [".env"]}, ".env")


def test_branch_name_for_task_is_deterministic() -> None:
    assert branch_name_for_task("1234567890abcdef", "Fix Login!") == "agent/12345678-fix-login"
