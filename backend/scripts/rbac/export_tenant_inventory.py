"""Export tenant table inventory for RBAC migration planning."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.identity_access.tenant_inventory import (  # noqa: E402
    TENANT_TABLE_INVENTORY,
    inventory_by_phase,
)


def main() -> None:
    payload = {
        "top_level": [entry.__dict__ for entry in inventory_by_phase("top_level")],
        "child": [entry.__dict__ for entry in inventory_by_phase("child")],
        "user_scoped": [entry.__dict__ for entry in inventory_by_phase("user_scoped")],
        "platform": [entry.__dict__ for entry in inventory_by_phase("platform")],
        "audit": [entry.__dict__ for entry in inventory_by_phase("audit")],
        "total_entries": len(TENANT_TABLE_INVENTORY),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
