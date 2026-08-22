from __future__ import annotations

from collections import Counter
from pathlib import Path

from backend.modules.orchestration.router import router
from fastapi.routing import APIRoute


def test_extracted_domain_routes_keep_public_contracts_without_duplicates() -> None:
    operations = [
        (route.path, method)
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    ]
    counts = Counter(operations)
    assert not [operation for operation, count in counts.items() if count > 1]

    expected = {
        ("/portfolio", "GET"),
        ("/portfolio/control-plane", "GET"),
        ("/analytics/cost", "GET"),
        ("/providers", "GET"),
        ("/providers/{provider_id}/runtime/start", "POST"),
        ("/tasks/my", "GET"),
    }
    assert expected <= set(operations)


def test_monolithic_router_is_frozen_below_pre_extraction_route_count() -> None:
    source = Path(__file__).resolve().parents[1] / "modules/orchestration/router.py"
    direct_routes = sum(
        1 for line in source.read_text().splitlines() if line.startswith("@router.")
    )
    assert direct_routes <= 190
