from __future__ import annotations

import asyncio
import shlex
import subprocess
from pathlib import Path
from typing import Any


def docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=3,
            check=False,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def execute_code_job(
    *,
    shell_cmd: str,
    cwd: str,
    timeout: int,
    use_shell_wrap: bool,
) -> dict[str, Any]:
    cwd_path = Path(cwd)
    if docker_available():
        return execute_code_job_docker(shell_cmd=shell_cmd, cwd=cwd_path, timeout=timeout)
    if use_shell_wrap:
        args = ["bash", "-lc", shell_cmd]
    else:
        args = shlex.split(shell_cmd)
    result = subprocess.run(
        args,
        cwd=str(cwd_path),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": args,
        "cwd": str(cwd_path),
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "sandbox": "host",
        "execution_backend": "cpu_worker_pool",
    }


def execute_code_job_docker(*, shell_cmd: str, cwd: Path, timeout: int) -> dict[str, Any]:
    docker_args = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--memory",
        "256m",
        "--cpus",
        "0.5",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,size=64m",
        "-v",
        f"{str(cwd)}:/workspace:ro",
        "-w",
        "/workspace",
        "python:3.12-slim",
        "bash",
        "-c",
        shell_cmd,
    ]
    result = subprocess.run(
        docker_args,
        capture_output=True,
        text=True,
        timeout=timeout + 10,
        check=False,
    )
    return {
        "command": shell_cmd,
        "cwd": "/workspace",
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "sandbox": "docker",
        "execution_backend": "cpu_worker_pool",
    }


async def execute_code_job_async(
    *,
    shell_cmd: str,
    cwd: str,
    timeout: int,
    use_shell_wrap: bool,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        execute_code_job,
        shell_cmd=shell_cmd,
        cwd=cwd,
        timeout=timeout,
        use_shell_wrap=use_shell_wrap,
    )
