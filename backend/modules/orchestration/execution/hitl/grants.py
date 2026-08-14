"""HITL grant consumption."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.modules.orchestration.models import TaskRun


class ExecutionHitlGrantsMixin:
    async def _consume_hitl_grant(
        self,
        run: TaskRun,
        approval_type: str,
        expected_payload: dict[str, Any] | None = None,
    ) -> bool:
        """Consume one approved action grant while resuming a blocked run.

        Approval decisions are durable records, not an in-memory bypass. A grant is
        matched to the exact run/action and marked consumed before the protected
        operation proceeds, preventing a later retry from reusing it accidentally.
        """
        expected = dict(expected_payload or {})
        approvals = await self.repo.list_approvals_for_run(run.id, status="approved")
        for approval in approvals:
            if approval.approval_type != approval_type:
                continue
            payload = dict(approval.payload_json or {})
            if payload.get("_consumed_at"):
                continue
            if any(payload.get(key) != value for key, value in expected.items()):
                continue
            payload["_consumed_at"] = datetime.now(UTC).isoformat()
            approval.payload_json = payload
            await self._emit_run_event(
                run,
                event_type="approval_grant_consumed",
                message=f"Consumed approved HITL action: {approval_type}.",
                payload={"approval_id": approval.id, "approval_type": approval_type},
            )
            return True
        return False
