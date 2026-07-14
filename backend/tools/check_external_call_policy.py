"""Static guard for accidental runtime HTTP-client bypasses."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOTS = (ROOT / "backend",)
ALLOWED_DIRECT_CLIENT_FILES = {
    ROOT / "backend" / "core" / "http_clients.py",
}


def _python_files() -> list[Path]:
    return [
        path
        for root in RUNTIME_ROOTS
        for path in root.rglob("*.py")
        if ".venv" not in path.parts
    ]


def find_policy_violations() -> list[str]:
    violations: list[str] = []
    for path in _python_files():
        if path in ALLOWED_DIRECT_CLIENT_FILES or "tests" in path.parts or "tools" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{path}:{exc.lineno}: syntax error: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "AsyncClient":
                continue
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "httpx":
                violations.append(
                    f"{path}:{node.lineno}: use the shared managed HTTP client "
                    "instead of direct httpx.AsyncClient"
                )
    return violations


def main() -> int:
    violations = find_policy_violations()
    if violations:
        print("External call policy violations:")
        print("\n".join(violations))
        return 1
    print("External call policy passed: runtime HTTP clients are centralized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
