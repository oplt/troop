"""Task evidence bundle validation and artifact change summaries."""

from __future__ import annotations

from typing import Any

from backend.modules.projects.orchestration_models import OrchestratorTask


class TaskEvidenceMixin:
    async def _changed_artifacts_payload(
        self,
        task_id: str,
        *,
        run_id: str | None = None,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        list_task_artifacts = getattr(self.repo, "list_task_artifacts", None)
        if not callable(list_task_artifacts):
            return []
        rows = await list_task_artifacts(task_id)
        filtered = [row for row in rows if run_id is None or getattr(row, "run_id", None) == run_id]
        return [
            {
                "id": row.id,
                "run_id": row.run_id,
                "kind": row.kind,
                "title": row.title,
                "created_at": row.created_at,
            }
            for row in filtered[:limit]
        ]

    async def _check_task_evidence_bundle_payload(
        self,
        task: OrchestratorTask | Any,
        *,
        target_status: str,
    ) -> dict[str, Any]:
        metadata = dict(getattr(task, "metadata_json", None) or {})
        links = self._normalized_external_links(metadata.get("external_links"))
        bundle = metadata.get("evidence_bundle")
        if not isinstance(bundle, dict):
            bundle = {}
        accepted_artifact_ids = {
            str(item).strip()
            for item in (bundle.get("accepted_artifact_ids") or [])
            if str(item).strip()
        }
        accepted_external_link_ids = {
            str(item).strip()
            for item in (bundle.get("accepted_external_link_ids") or [])
            if str(item).strip()
        }
        reviewer_decision = (
            dict(bundle.get("reviewer_decision"))
            if isinstance(bundle.get("reviewer_decision"), dict)
            else {}
        )
        sync_summary = str(bundle.get("sync_summary") or "").strip()
        artifacts = await self.repo.list_task_artifacts(task.id)
        artifact_ids = {
            str(getattr(item, "id", "")).strip()
            for item in artifacts
            if str(getattr(item, "id", "")).strip()
        }
        link_ids = {
            str(item.get("id") or "").strip() for item in links if str(item.get("id") or "").strip()
        }
        checks = [
            {
                "name": "accepted_artifacts",
                "passed": bool(accepted_artifact_ids & artifact_ids),
                "detail": "Accepted artifacts selected."
                if accepted_artifact_ids & artifact_ids
                else "Select at least one accepted artifact for final evidence.",
            },
            {
                "name": "accepted_external_links",
                "passed": bool(accepted_external_link_ids & link_ids),
                "detail": "Accepted external links selected."
                if accepted_external_link_ids & link_ids
                else "Select at least one accepted external link for final evidence.",
            },
            {
                "name": "reviewer_decision",
                "passed": bool(str(reviewer_decision.get("status") or "").strip()),
                "detail": "Reviewer decision recorded."
                if str(reviewer_decision.get("status") or "").strip()
                else "Record reviewer decision before final sync/archive.",
            },
        ]
        if target_status == "synced_to_github":
            checks.append(
                {
                    "name": "sync_summary",
                    "passed": bool(sync_summary),
                    "detail": "Sync summary recorded."
                    if sync_summary
                    else "Add sync summary before moving to synced_to_github.",
                }
            )
        if target_status == "archived":
            checks.append(
                {
                    "name": "archive_summary",
                    "passed": bool(sync_summary)
                    or getattr(task, "status", "") == "synced_to_github",
                    "detail": "Archive summary or prior GitHub sync recorded."
                    if bool(sync_summary) or getattr(task, "status", "") == "synced_to_github"
                    else "Archive needs sync summary or prior synced_to_github state.",
                }
            )
        return {
            "task_id": task.id,
            "passed": all(item["passed"] for item in checks),
            "checks": checks,
        }
