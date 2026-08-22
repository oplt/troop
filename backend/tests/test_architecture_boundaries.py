from __future__ import annotations

import ast
from pathlib import Path

from backend.api.compat.memory import _scope_filters, _scope_metadata
from backend.api.router import api_router

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def test_removed_app_namespace_has_no_production_imports() -> None:
    assert not (BACKEND_ROOT / "app").exists()
    production_roots = [BACKEND_ROOT / name for name in ("api", "core", "db", "modules", "workers")]
    stale: list[str] = []
    for root in production_roots:
        for path in root.rglob("*.py"):
            imports = _imports(path)
            if any(name == "backend.app" or name.startswith("backend.app.") for name in imports):
                stale.append(str(path.relative_to(BACKEND_ROOT)))
    assert stale == []


def test_non_transport_modules_do_not_import_api_layer() -> None:
    violations: list[str] = []
    for path in (BACKEND_ROOT / "modules").rglob("*.py"):
        if path.name in {"router.py", "graphql_router.py"} or "routers" in path.parts:
            continue
        if any(name == "backend.api" or name.startswith("backend.api.") for name in _imports(path)):
            violations.append(str(path.relative_to(BACKEND_ROOT)))
    assert violations == []


def test_compatibility_routes_keep_public_paths() -> None:
    paths = {route.path for route in api_router.routes}
    assert {
        "/api/v1/agents",
        "/api/v1/tools",
        "/api/v1/tasks",
        "/api/v1/tasks/{task_id}/runs",
        "/api/v1/runs/{run_id}",
        "/api/v1/runs/{run_id}/approve-plan",
        "/api/v1/memory",
    }.issubset(paths)


def test_memory_scope_mapping_is_explicit() -> None:
    project_id, metadata = _scope_metadata("task", "task-1", {"project_id": "project-1"})
    assert project_id == "project-1"
    assert metadata["task_id"] == "task-1"

    company_filters = _scope_filters("company", "company-1", "user-1")
    task_filters = _scope_filters("task", "task-1", "user-1")
    assert company_filters.company_id == "company-1"
    assert task_filters.task_id == "task-1"
