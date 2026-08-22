"""Generate and validate Troop's backend/frontend capability contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT_JSON = ROOT / "docs/audits/api-ui-parity.json"
AUDIT_MARKDOWN = ROOT / "docs/audits/API_UI_PARITY.md"
OPENAPI_JSON = ROOT / "docs/audits/openapi.json"
GENERATED_TYPES = ROOT / "frontend/src/api/generated/openapi.ts"
FRONTEND_ROOT = ROOT / "frontend/src"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}

CLIENT_CALL = re.compile(
    r"(?:apiFetch|useSseStream)\s*(?:<[^;]{0,500}?>)?\s*\(\s*(?P<quote>[`\"'])(?P<path>.*?)(?P=quote)",
    re.DOTALL,
)
DIRECT_FETCH = re.compile(
    r"fetch\s*\(\s*`\$\{API_BASE\}(?P<path>.*?)`",
    re.DOTALL,
)
ROUTE_LITERAL = re.compile(r"<Route\s+path=\"(?P<path>[^\"]+)\"")
PARAMETER = re.compile(r"\{[^/{}]+\}")
INTERPOLATION = re.compile(r"\$\{[^}]+\}")


@dataclass(frozen=True)
class ClientReference:
    path: str
    source: str


def _load_openapi() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    from backend.api.main import app

    return app.openapi()


def _normalize_client_path(raw_path: str) -> str | None:
    path = raw_path.strip()
    if not path.startswith("/"):
        return None
    # Optional query suffixes often contain a nested template literal. The path before
    # the interpolation is the stable API contract in those cases.
    path = re.sub(r"\$\{(?:query|qs|suffix)\b.*$", "", path, flags=re.DOTALL)
    path = INTERPOLATION.sub("{param}", path)
    path = path.split("?", 1)[0].rstrip("/") or "/"
    if not path.startswith("/api/") and not path.startswith(
        ("/health", "/metrics", "/webhooks")
    ):
        path = f"/api/v1{path}"
    return path


def _shape(path: str) -> str:
    return PARAMETER.sub("{}", path.rstrip("/") or "/")


def _path_matches(client_path: str, backend_path: str) -> bool:
    client_shape = _shape(client_path)
    backend_shape = _shape(backend_path)
    if client_shape == backend_shape:
        return True
    if "{}" not in client_shape:
        return False
    pattern = re.escape(client_shape).replace(re.escape("{}"), r"[^/]+")
    return re.fullmatch(pattern, backend_shape) is not None


def _scan_frontend() -> list[ClientReference]:
    references: set[ClientReference] = set()
    for path in sorted(FRONTEND_ROOT.rglob("*")):
        if path.suffix not in {".ts", ".tsx"} or ".test." in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        for pattern in (CLIENT_CALL, DIRECT_FETCH):
            for match in pattern.finditer(text):
                normalized = _normalize_client_path(match.group("path"))
                if normalized:
                    references.add(ClientReference(path=normalized, source=relative))
    return sorted(references, key=lambda item: (item.path, item.source))


def _frontend_routes() -> set[str]:
    source = (FRONTEND_ROOT / "app/router.tsx").read_text(encoding="utf-8")
    return {match.group("path") for match in ROUTE_LITERAL.finditer(source)}


def _route_for(path: str) -> tuple[str | None, str]:
    rules = (
        (r"^/api/v1/auth/", "/", "authentication"),
        (r"^/api/v1/ai/", "/ai", "ai-studio"),
        (r"^/api/v1/rag/projects/", "/projects/:projectId", "knowledge"),
        (r"^/api/v1/calendar/", "/calendar", "calendar"),
        (
            r"^/api/v1/companies/[^/]+/semantic-memory",
            "/companies/:companyId/memory",
            "knowledge",
        ),
        (r"^/api/v1/companies", "/companies", "organization"),
        (r"^/api/v1/(users(?:/|$)|profile(?:/|$))", "/profile", "profile"),
        (r"^/api/v1/notifications", "/notifications", "notifications"),
        (r"^/api/v1/orchestration/approvals", "/approvals", "approvals"),
        (r"^/api/v1/orchestration/hitl", "/activity", "audit"),
        (r"^/api/v1/orchestration/agents", "/agents", "agents"),
        (r"^/api/v1/orchestration/teams", "/hierarchy", "hierarchy"),
        (r"^/api/v1/orchestration/brainstorms", "/brainstorms", "brainstorms"),
        (r"^/api/v1/orchestration/github", "/admin/settings", "integrations"),
        (r"^/api/v1/orchestration/analytics/cost", "/analytics/cost", "cost"),
        (r"^/api/v1/orchestration/analytics", "/analytics/execution", "observability"),
        (r"^/api/v1/orchestration/portfolio", "/portfolio", "portfolio"),
        (
            r"^/api/v1/orchestration/projects/[^/]+/evals",
            "/projects/:projectId/benchmark",
            "evaluation",
        ),
        (
            r"^/api/v1/orchestration/projects/[^/]+/semantic-memory",
            "/projects/:projectId",
            "knowledge",
        ),
        (r"^/api/v1/orchestration/projects", "/projects/:projectId", "project"),
        (r"^/api/v1/orchestration/(runs|tasks)", "/runs/:runId", "runs"),
        (r"^/api/v1/orchestration", "/dashboard", "operations"),
        (r"^/api/v1/platform", "/admin/settings", "platform-admin"),
        (r"^/api/v1/admin", "/admin/settings", "administration"),
        (r"^/api/v1/settings", "/admin/settings", "settings"),
        (r"^/api/v1/workforce/workflows", "/workforce-workflows", "workflows"),
        (r"^/api/v1/workforce/marketplace", "/marketplace", "marketplace"),
        (r"^/api/v1/workforce/connectors", "/integrations", "integrations"),
        (r"^/api/v1/workforce/departments", "/departments", "departments"),
        (r"^/api/v1/workforce/skills", "/skills", "skills"),
        (r"^/api/v1/workforce", "/my-tasks", "workforce"),
        (r"^/api/v1/(agents|tools|tasks|runs|memory)", "/dashboard", "compatibility"),
        (r"^/api/v1/graphql$", "/hierarchy", "hierarchy"),
    )
    for pattern, route, surface in rules:
        if re.search(pattern, path):
            return route, surface
    return None, "api"


def _classification(path: str, sources: list[str], deprecated: bool) -> str:
    if deprecated:
        return "deprecated"
    if sources:
        return "ui-required"
    if path.startswith(("/health/", "/metrics", "/webhooks/")) or any(
        marker in path for marker in ("/callback", "/webhooks/", "/stream")
    ):
        return "internal"
    if path == "/api/v1/graphql" or any(
        marker in path for marker in ("/export", "/seed", "/recovery-benchmark")
    ):
        return "api-only"
    return "ui-advanced"


def _capability(tags: list[str], operation_id: str) -> str:
    function_name = operation_id.split("_api_v1_", 1)[0].removesuffix("_metrics")
    namespace = (tags[0] if tags else "platform").replace("-", ".")
    return f"{namespace}.{function_name}"


def _build_inventory(
    schema: dict[str, Any], references: list[ClientReference]
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path, path_item in sorted(schema["paths"].items()):
        matching_sources = sorted(
            {ref.source for ref in references if _path_matches(ref.path, path)}
        )
        for method, operation in sorted(path_item.items()):
            if method not in HTTP_METHODS:
                continue
            deprecated = path.startswith(
                (
                    "/api/v1/agents",
                    "/api/v1/tools",
                    "/api/v1/tasks",
                    "/api/v1/runs",
                    "/api/v1/memory",
                )
            )
            route, surface = _route_for(path)
            classification = _classification(path, matching_sources, deprecated)
            entries.append(
                {
                    "capability": _capability(
                        list(operation.get("tags") or []),
                        str(operation.get("operationId") or "unknown"),
                    ),
                    "method": method.upper(),
                    "endpoint": path,
                    "classification": classification,
                    "route": route if classification == "ui-required" else None,
                    "surface": surface,
                    "frontend_implementations": matching_sources,
                    "operation_id": operation.get("operationId"),
                    "tags": operation.get("tags") or [],
                }
            )
    counts = Counter(entry["classification"] for entry in entries)
    return {
        "schema_version": 1,
        "source": "FastAPI OpenAPI + frontend API call scan",
        "endpoint_count": len(entries),
        "classification_counts": dict(sorted(counts.items())),
        "endpoints": entries,
    }


def _markdown(inventory: dict[str, Any]) -> str:
    counts = inventory["classification_counts"]
    summary = ", ".join(f"{key}: {value}" for key, value in counts.items())
    lines = [
        "# API and UI parity inventory",
        "",
        "This generated inventory classifies every FastAPI operation and records its intentional UI exposure. Regenerate it with `python scripts/api_ui_parity.py --write`.",
        "",
        f"Total operations: **{inventory['endpoint_count']}**. {summary}.",
        "",
        "| Method | Endpoint | Classification | UI route | Surface | Frontend implementation |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for entry in inventory["endpoints"]:
        sources = (
            "<br>".join(entry["frontend_implementations"])
            or "Intentional backend surface"
        )
        values = (
            entry["method"],
            f"`{entry['endpoint']}`",
            entry["classification"],
            f"`{entry['route']}`" if entry["route"] else "n/a",
            entry["surface"],
            sources,
        )
        lines.append(
            "| " + " | ".join(str(value).replace("|", "\\|") for value in values) + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _typescript(schema: dict[str, Any]) -> str:
    paths = sorted(schema["paths"])
    serialized = " | ".join(json.dumps(path) for path in paths)
    return (
        "// Generated by scripts/api_ui_parity.py. Do not edit by hand.\n"
        f"export type OpenApiPath = {serialized};\n\n"
        'export type OpenApiMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "OPTIONS" | "HEAD";\n'
        "export interface OpenApiOperationRef { method: OpenApiMethod; path: OpenApiPath }\n"
    )


def _outputs(schema: dict[str, Any], inventory: dict[str, Any]) -> dict[Path, str]:
    return {
        AUDIT_JSON: json.dumps(inventory, indent=2, sort_keys=False) + "\n",
        AUDIT_MARKDOWN: _markdown(inventory),
        OPENAPI_JSON: json.dumps(schema, indent=2, sort_keys=True) + "\n",
        GENERATED_TYPES: _typescript(schema),
    }


def _validation_errors(
    schema: dict[str, Any], inventory: dict[str, Any], references: list[ClientReference]
) -> list[str]:
    errors: list[str] = []
    backend_paths = set(schema["paths"])
    for ref in references:
        if not any(_path_matches(ref.path, path) for path in backend_paths):
            errors.append(
                f"Frontend call has no OpenAPI path: {ref.path} ({ref.source})"
            )
    frontend_routes = _frontend_routes()
    route_shapes = {_shape(route) for route in frontend_routes}
    for entry in inventory["endpoints"]:
        if entry["classification"] != "ui-required":
            continue
        if not entry["frontend_implementations"]:
            errors.append(
                f"ui-required endpoint has no client: {entry['method']} {entry['endpoint']}"
            )
        route = entry["route"]
        if not route or _shape(route.split("?", 1)[0]) not in route_shapes:
            errors.append(
                f"ui-required endpoint has orphaned route {route!r}: {entry['endpoint']}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--write", action="store_true", help="regenerate checked-in artifacts"
    )
    mode.add_argument(
        "--check", action="store_true", help="validate artifacts and API clients"
    )
    args = parser.parse_args()

    schema = _load_openapi()
    references = _scan_frontend()
    inventory = _build_inventory(schema, references)
    outputs = _outputs(schema, inventory)
    errors = _validation_errors(schema, inventory, references)

    if args.write:
        for path, content in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    else:
        for path, expected in outputs.items():
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                errors.append(f"Generated artifact is stale: {path.relative_to(ROOT)}")

    if errors:
        print("API/UI parity validation failed:", file=sys.stderr)
        for error in sorted(set(errors)):
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"API/UI parity valid: {inventory['endpoint_count']} operations, "
        f"{len(references)} frontend references"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
