"""Task assignment, agent work sessions, and routing explainability."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from backend.modules.identity_access.models import User
from backend.modules.orchestration.local_repo import normalize_workspace
from backend.modules.projects.orchestration_models import OrchestratorTask


class TaskAssignmentMixin:
    async def _ensure_project_agent_member(
        self,
        user: User,
        project_id: str,
        agent_id: str,
        relationship: str,
    ) -> None:
        await self.get_agent(user, agent_id)
        membership = await self.repo.get_project_membership(project_id, agent_id)
        if membership is None:
            raise HTTPException(
                status_code=422,
                detail=f"{relationship} agent must be assigned to this project before it can own the task.",
            )

    async def start_agent_work_session(
        self,
        user: User,
        project_id: str,
        task_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        task = await self.get_task(user, project_id, task_id)
        if payload.get("agent_id"):
            await self.get_agent(user, str(payload["agent_id"]))
        repo_workspace = normalize_workspace((project.settings_json or {}).get("local_repo"))
        risk_level = str(payload.get("risk_level") or "medium")
        if risk_level not in {"low", "medium", "high"}:
            risk_level = "medium"
        required_tests = [
            str(item).strip() for item in payload.get("required_tests") or [] if str(item).strip()
        ]
        session = {
            "status": "queued",
            "agent_id": payload.get("agent_id") or task.assigned_agent_id,
            "repository_link_id": payload.get("repository_link_id"),
            "local_repo": {
                "enabled": repo_workspace["enabled"],
                "repo_path": repo_workspace["repo_path"],
                "dirty_worktree_policy": repo_workspace["dirty_worktree_policy"],
            },
            "acceptance_criteria": payload.get("acceptance_criteria") or task.acceptance_criteria,
            "risk_level": risk_level,
            "required_tests": required_tests,
            "planning_gate_required": risk_level in {"medium", "high"},
            "plan_status": "required" if risk_level in {"medium", "high"} else "optional",
            "quality_score": None,
            "artifacts": [],
            "created_by_user_id": user.id,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        metadata = dict(task.metadata_json or {})
        metadata["local_repo_session"] = session
        task.metadata_json = metadata
        if task.status == "backlog":
            await self._transition_task_status(task, "queued", reason="agent work session queued")
        await self.db.commit()
        await self.db.refresh(task)
        return session

    async def update_agent_work_session(
        self,
        user: User,
        project_id: str,
        task_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        task = await self.get_task(user, project_id, task_id)
        allowed_statuses = {
            "queued",
            "preparing_workspace",
            "analyzing",
            "planning",
            "editing",
            "testing",
            "review-ready",
            "blocked",
            "failed",
            "done",
        }
        metadata = dict(task.metadata_json or {})
        session = dict(metadata.get("local_repo_session") or {})
        status = str(payload.get("status") or session.get("status") or "queued")
        if status not in allowed_statuses:
            raise HTTPException(status_code=422, detail="Invalid agent work session status.")
        if payload.get("plan"):
            session["plan"] = str(payload["plan"])
            session["plan_status"] = str(payload.get("plan_status") or "pending_approval")
        if payload.get("blocker"):
            session["blocker"] = str(payload["blocker"])
        if payload.get("summary"):
            session["summary"] = str(payload["summary"])
        if isinstance(payload.get("artifacts"), list):
            session["artifacts"] = payload["artifacts"]
        session["status"] = status
        session["updated_by_user_id"] = user.id
        session["updated_at"] = datetime.now(UTC).isoformat()
        metadata["local_repo_session"] = session
        task.metadata_json = metadata
        if status == "review-ready":
            await self._transition_task_status(
                task, "needs_review", reason="agent session review ready"
            )
        elif status == "blocked":
            await self._transition_task_status(
                task, "blocked", reason=session.get("blocker") or "agent session blocked"
            )
        elif status == "failed":
            await self._transition_task_status(
                task, "failed", reason=session.get("summary") or "agent session failed"
            )
        elif status == "done":
            await self._transition_task_status(task, "completed", reason="agent session done")
        await self.db.commit()
        await self.db.refresh(task)
        return session

    async def score_agent_work_session(
        self, user: User, project_id: str, task_id: str
    ) -> dict[str, Any]:
        task = await self.get_task(user, project_id, task_id)
        metadata = dict(task.metadata_json or {})
        session = dict(metadata.get("local_repo_session") or {})
        required_tests = list(session.get("required_tests") or [])
        artifacts = list(session.get("artifacts") or [])
        test_artifacts = [
            item
            for item in artifacts
            if isinstance(item, dict) and item.get("kind") == "test_output"
        ]
        diff_size = int(session.get("diff_bytes") or 0)
        security_risk = (
            25
            if session.get("risk_level") == "high"
            else 10
            if session.get("risk_level") == "medium"
            else 5
        )
        coverage = (
            100
            if required_tests and test_artifacts
            else 60
            if test_artifacts
            else 25
            if required_tests
            else 50
        )
        blast_radius = max(0, 100 - min(80, diff_size // 2500))
        correctness = 80 if session.get("status") in {"review-ready", "done"} else 45
        confidence = round((correctness + coverage + blast_radius + (100 - security_risk)) / 4)
        score = {
            "correctness": correctness,
            "test_coverage": coverage,
            "diff_size": diff_size,
            "blast_radius": blast_radius,
            "confidence": confidence,
            "security_risk": security_risk,
            "ux_impact": 25 if "frontend" in " ".join(task.labels_json or []) else 0,
        }
        session["quality_score"] = score
        session["updated_at"] = datetime.now(UTC).isoformat()
        metadata["local_repo_session"] = session
        task.metadata_json = metadata
        await self.db.commit()
        return score

    def _routing_explainability_from_payload(
        self, payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        raw = (
            (payload or {}).get("orchestration_meta") if isinstance(payload, dict) else None
        ) or {}
        if not isinstance(raw, dict):
            return {}
        return {
            "agent_selection_reason": str(
                raw.get("agent_selection_reason") or raw.get("worker_agent_rationale") or ""
            ),
            "model_selection_reason": str(
                raw.get("model_selection_reason") or raw.get("model_rationale") or ""
            ),
            "routing_inputs": raw.get("routing_inputs")
            if isinstance(raw.get("routing_inputs"), dict)
            else {},
            "routing_policy_snapshot": raw.get("routing_policy_snapshot")
            if isinstance(raw.get("routing_policy_snapshot"), dict)
            else {},
            "agent_source": raw.get("worker_agent_id_source"),
            "model_source": raw.get("model_source"),
        }

    def _routing_explainability_from_task_metadata(
        self, task: OrchestratorTask | Any
    ) -> dict[str, Any]:
        meta = dict(getattr(task, "metadata_json", None) or {})
        raw = meta.get("routing_explainability")
        return raw if isinstance(raw, dict) else {}
