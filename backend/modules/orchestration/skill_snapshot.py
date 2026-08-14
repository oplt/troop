"""Freeze AgentSkillAssignment → SkillVersion IDs onto a TaskRun checkpoint."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.modules.orchestration.models import TaskRun
from backend.modules.orchestration.skill_runtime import load_assigned_skill_versions


async def freeze_skill_version_snapshot(
    db: AsyncSession,
    run: TaskRun,
    *,
    agent_id: str | None,
) -> dict[str, Any]:
    """Resolve and freeze exact SkillVersion IDs for the lifetime of this run."""
    if not agent_id:
        snapshot = {
            "agent_id": None,
            "skill_version_ids": [],
            "skills": [],
            "required_tools": [],
            "capabilities": [],
        }
    else:
        payloads = await load_assigned_skill_versions(db, agent_id)
        tools: list[str] = []
        caps: list[str] = []
        for item in payloads:
            for tool in item.get("required_tools") or []:
                if tool not in tools:
                    tools.append(str(tool))
            for cap in item.get("capabilities") or []:
                if cap not in caps:
                    caps.append(str(cap))
        snapshot = {
            "agent_id": agent_id,
            "skill_version_ids": [
                str(p["skill_version_id"]) for p in payloads if p.get("skill_version_id")
            ],
            "skills": [
                {
                    "skill_id": p.get("skill_id"),
                    "skill_version_id": p.get("skill_version_id"),
                    "slug": p.get("slug"),
                    "version_number": p.get("version_number"),
                    "required_tools": list(p.get("required_tools") or []),
                    "capabilities": list(p.get("capabilities") or []),
                    "evaluation_criteria": list(p.get("evaluation_criteria") or []),
                    "instructions_markdown": p.get("instructions_markdown") or "",
                }
                for p in payloads
            ],
            "required_tools": tools,
            "capabilities": caps,
        }

    checkpoint = dict(run.checkpoint_json or {})
    checkpoint["skill_version_snapshot"] = snapshot
    run.checkpoint_json = checkpoint
    flag_modified(run, "checkpoint_json")
    return snapshot


def get_frozen_skill_version_ids(run: TaskRun) -> list[str]:
    snapshot = (run.checkpoint_json or {}).get("skill_version_snapshot") or {}
    return [str(v) for v in (snapshot.get("skill_version_ids") or []) if v]


def get_frozen_skill_payloads(run: TaskRun) -> list[dict[str, Any]]:
    snapshot = (run.checkpoint_json or {}).get("skill_version_snapshot") or {}
    skills = snapshot.get("skills") or []
    return [s for s in skills if isinstance(s, dict)]
