from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOG_ROOT = Path(__file__).resolve().parents[2] / "logs" / "agent_runs"


def log_agent_event(event_type: str, **payload: Any) -> None:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    line = {
        "timestamp": now.isoformat(),
        "event_type": event_type,
        **{key: value for key, value in payload.items() if value is not None},
    }
    path = LOG_ROOT / f"{now.date().isoformat()}.log"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, sort_keys=True, default=str) + "\n")
