from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = BACKEND_ROOT / "modules"
LEGACY_MEMORY_HTTP_FILES = {
    "memory/entry_types.py",
    "memory/episodic_jobs.py",
    "memory/namespaces.py",
    "memory/service.py",
}


def _module_name(path: Path) -> str:
    return ".".join(path.with_suffix("").relative_to(BACKEND_ROOT.parent).parts)


def _top_level_imports(tree: ast.Module) -> Iterable[str]:
    pending = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module
        elif isinstance(node, (ast.If, ast.Try)):
            pending.extend(node.body)
            pending.extend(node.orelse)
            if isinstance(node, ast.Try):
                pending.extend(node.finalbody)
                pending.extend(item for handler in node.handlers for item in handler.body)


def _module_graph() -> dict[str, set[str]]:
    files = [path for path in MODULE_ROOT.rglob("*.py") if path.name != "__init__.py"]
    known = {_module_name(path) for path in files}
    graph: dict[str, set[str]] = {}
    for path in files:
        name = _module_name(path)
        imports = set(_top_level_imports(ast.parse(path.read_text())))
        graph[name] = imports & known
    return graph


def _find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    trail: list[str] = []

    def visit(module: str) -> list[str] | None:
        if module in visiting:
            start = trail.index(module)
            return trail[start:] + [module]
        if module in visited:
            return None
        visiting.add(module)
        trail.append(module)
        for dependency in graph[module]:
            cycle = visit(dependency)
            if cycle:
                return cycle
        trail.pop()
        visiting.remove(module)
        visited.add(module)
        return None

    for module in graph:
        cycle = visit(module)
        if cycle:
            return cycle
    return None


def test_domain_import_boundaries() -> None:
    violations: list[str] = []
    memory_http_files: set[str] = set()
    for path in MODULE_ROOT.rglob("*.py"):
        relative = path.relative_to(MODULE_ROOT).as_posix()
        imports = set(_top_level_imports(ast.parse(path.read_text())))
        is_repository = "repository" in path.parts or path.name == "repository.py"
        for imported in imports:
            if is_repository and ".router" in imported:
                violations.append(f"{relative}: repository imports HTTP router {imported}")
            if relative.startswith("rag/") and ".router" in imported:
                violations.append(f"{relative}: RAG imports route module {imported}")
            if relative.startswith("memory/") and (
                imported == "fastapi" or imported.startswith("backend.api") or ".router" in imported
            ):
                memory_http_files.add(relative)
            if relative.startswith("projects/") and (
                imported.startswith("frontend") or "workforce.ui" in imported
            ):
                violations.append(f"{relative}: project domain imports UI concept {imported}")
    assert not violations, "\n".join(violations)
    assert memory_http_files <= LEGACY_MEMORY_HTTP_FILES, (
        "New memory code may not depend on the HTTP layer; legacy adapters are frozen: "
        f"{sorted(memory_http_files - LEGACY_MEMORY_HTTP_FILES)}"
    )


def test_backend_modules_have_no_top_level_import_cycles() -> None:
    cycle = _find_cycle(_module_graph())
    assert cycle is None, " -> ".join(cycle or [])


def test_remaining_facade_mixins_document_host_contracts() -> None:
    targets = {
        "ai/documents/service.py": "AiDocumentsMixin",
        "ai/evaluations/service.py": "AiEvaluationsMixin",
        "ai/retrieval/service.py": "AiRetrievalMixin",
        "ai/reviews/service.py": "AiReviewsMixin",
        "ai/runs/service.py": "AiRunsMixin",
        "memory/service.py": "OrchestrationMemoryServiceMixin",
        "orchestration/execution/execution_service.py": "OrchestrationExecutionServiceMixin",
        "projects/service.py": "OrchestrationProjectsServiceMixin",
        "projects/tasks_service.py": "OrchestrationTasksServiceMixin",
    }
    for relative, class_name in targets.items():
        tree = ast.parse((MODULE_ROOT / relative).read_text())
        class_node = next(
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        doc = (ast.get_docstring(class_node) or "").lower()
        assert "require" in doc, f"{class_name} must document its host dependencies"
