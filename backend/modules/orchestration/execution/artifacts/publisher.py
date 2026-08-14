"""Final artifact bundle publication."""

from __future__ import annotations

import json
from typing import Any

from backend.modules.orchestration.models import TaskRun


class ExecutionArtifactsPublisherMixin:
    async def _publish_final_artifacts(
        self,
        run: TaskRun,
        *,
        branch_results: list[dict[str, Any]],
        review_state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        created: list[dict[str, Any]] = []
        final_output = str(
            run.output_payload_json.get("final_output")
            or run.output_payload_json.get("summary")
            or ""
        )
        review_text = json.dumps(review_state, indent=2, default=str)
        evidence_payload = {
            "branches": [
                {
                    "branch_id": item.get("branch_id"),
                    "title": item.get("title"),
                    "status": item.get("status"),
                    "changed_files": item.get("changed_files") or [],
                    "risks": item.get("risks") or [],
                    "evidence_refs": item.get("evidence_refs") or [],
                    "child_run_id": item.get("child_run_id"),
                }
                for item in branch_results
            ],
            "review": review_state,
        }
        for kind, title, content in [
            (
                "summary",
                "Manager summary",
                str(run.output_payload_json.get("summary") or final_output)[:5000],
            ),
            ("implementation", "Result bundle", final_output[:12000]),
            (
                "evidence",
                "Evidence bundle",
                json.dumps(evidence_payload, indent=2, default=str)[:12000],
            ),
            ("review", "Review verdict", review_text[:12000]),
        ]:
            await self._write_artifact(
                run,
                kind=kind,
                title=title,
                content=content,
                metadata={"parent_run_id": run.id},
            )
            created.append({"kind": kind, "title": title})
        return created
