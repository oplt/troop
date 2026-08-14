"""Pure task metadata normalization helpers."""

from __future__ import annotations

import uuid
from typing import Any

EXTERNAL_LINK_KINDS: frozenset[str] = frozenset(
    {"spec", "doc", "figma", "pr", "commit", "incident", "runbook", "issue", "other"}
)


def normalized_external_links(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        label = str(item.get("label") or "").strip()
        if not url or not label:
            continue
        kind = str(item.get("kind") or "other").strip().lower()
        if kind not in EXTERNAL_LINK_KINDS:
            kind = "other"
        row_id = str(item.get("id") or uuid.uuid4()).strip()
        rows.append(
            {
                "id": row_id,
                "kind": kind,
                "label": label[:255],
                "url": url[:2000],
                "notes": str(item.get("notes") or "").strip()[:500],
            }
        )
    return rows


def normalized_required_tools(raw: Any) -> list[str]:
    values = raw if isinstance(raw, (list, tuple, set)) else str(raw or "").split(",")
    result: list[str] = []
    for value in values:
        tool = str(value).strip()
        if tool and tool not in result:
            result.append(tool[:120])
    return result[:64]


def normalized_task_metadata(
    raw: Any,
    *,
    required_tools: Any = None,
    external_links: Any = None,
) -> dict[str, Any]:
    meta = dict(raw or {}) if isinstance(raw, dict) else {}
    if required_tools is not None:
        meta["required_tools"] = normalized_required_tools(required_tools)
    else:
        meta["required_tools"] = normalized_required_tools(meta.get("required_tools"))
    if external_links is not None:
        meta["external_links"] = normalized_external_links(external_links)
    else:
        meta["external_links"] = normalized_external_links(meta.get("external_links"))
    bundle_raw = meta.get("evidence_bundle")
    bundle = dict(bundle_raw) if isinstance(bundle_raw, dict) else {}
    bundle["accepted_artifact_ids"] = [
        str(item).strip()
        for item in (bundle.get("accepted_artifact_ids") or [])
        if str(item).strip()
    ]
    bundle["accepted_external_link_ids"] = [
        str(item).strip()
        for item in (bundle.get("accepted_external_link_ids") or [])
        if str(item).strip()
    ]
    reviewer_decision = bundle.get("reviewer_decision")
    bundle["reviewer_decision"] = (
        dict(reviewer_decision) if isinstance(reviewer_decision, dict) else {}
    )
    bundle["sync_summary"] = str(bundle.get("sync_summary") or "").strip()
    meta["evidence_bundle"] = bundle
    return meta
