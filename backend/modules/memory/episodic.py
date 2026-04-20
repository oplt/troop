"""Episodic cold-archive JSONL helpers (Layer 4)."""

from __future__ import annotations

import gzip
import json
from datetime import datetime
from typing import Any


def build_episodic_archive_jsonl_gz(records: list[dict[str, Any]]) -> bytes:
    lines = "\n".join(json.dumps(r, default=_json_default) for r in records) + ("\n" if records else "")
    return gzip.compress(lines.encode("utf-8"), compresslevel=6)


def _json_default(obj: Any) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def episodic_object_key(owner_id: str, project_id: str, period_tag: str) -> str:
    return f"episodic-archives/{owner_id}/{project_id}/{period_tag}.jsonl.gz"
