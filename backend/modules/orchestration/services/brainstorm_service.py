from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from backend.modules.identity_access.models import User
from backend.modules.orchestration.models import Brainstorm, TaskRun
from backend.modules.projects.orchestration_models import OrchestratorTask
from backend.modules.team.models import AgentProfile


class OrchestrationBrainstormServiceMixin:
    async def brainstorm_discourse_insights(self, user: User, brainstorm_id: str) -> dict[str, Any]:
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        messages = await self.repo.list_brainstorm_messages(brainstorm_id)
        if not messages:
            return {
                "message_count": 0,
                "same_agent_streak_ratio": 0.0,
                "top_repeated_terms": [],
                "rounds_with_messages": 0,
                "last_round_repetition_score": None,
                "last_round_pairwise_min_similarity": None,
                "consensus_kind": None,
                "conflict_signal": None,
            }
        prev: str | None = None
        pairs = 0
        same = 0
        for m in messages:
            cur = m.agent_id or "unknown"
            if prev is not None:
                pairs += 1
                if cur == prev:
                    same += 1
            prev = cur
        ratio = same / pairs if pairs else 0.0
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "this",
            "that",
            "from",
            "have",
            "has",
            "are",
            "was",
            "were",
            "but",
            "not",
            "you",
            "your",
            "our",
            "their",
        }
        wc: Counter[str] = Counter()
        for m in messages:
            for w in re.findall(r"[a-zA-Z]{4,}", (m.content or "").lower()):
                if w not in stopwords:
                    wc[w] += 1
        top_terms = [w for w, _ in wc.most_common(12)]
        rounds = {m.round_number for m in messages}
        last_round = max((m.round_number for m in messages), default=0)
        last_contents = [m.content or "" for m in messages if m.round_number == last_round]
        stop_conditions = dict(brainstorm.stop_conditions_json or {})
        soft_thr = float(stop_conditions.get("soft_consensus_min_similarity", 0.72))
        conflict_thr = float(stop_conditions.get("conflict_pairwise_max_similarity", 0.38))
        metrics = self._brainstorm_consensus_metrics_from_contents(last_contents, soft_thr, conflict_thr)
        latest_log = None
        for entry in reversed(brainstorm.decision_log_json or []):
            if entry.get("type") == "round_summary":
                latest_log = entry
                break
        return {
            "message_count": len(messages),
            "same_agent_streak_ratio": round(float(ratio), 4),
            "top_repeated_terms": top_terms,
            "rounds_with_messages": len(rounds),
            "last_round_repetition_score": float(latest_log["repetition_score"])
            if latest_log and latest_log.get("repetition_score") is not None
            else metrics.get("repetition_score"),
            "last_round_pairwise_min_similarity": metrics.get("pairwise_min_similarity"),
            "consensus_kind": (latest_log or {}).get("consensus_kind") or metrics.get("consensus_kind"),
            "conflict_signal": (latest_log or {}).get("conflict_signal")
            if latest_log and "conflict_signal" in latest_log
            else metrics.get("conflict_signal"),
        }

    async def create_brainstorm(self, user: User, payload: dict[str, Any]):
        project = await self.get_project(user, payload["project_id"])
        if payload.get("task_id"):
            await self.get_task(user, project.id, payload["task_id"])
        stop_conditions = self._normalize_brainstorm_stop_conditions(payload)
        participant_ids: list[str] = []
        seen_participants: set[str] = set()
        for raw_id in payload.get("participant_agent_ids", []):
            agent_id = str(raw_id).strip()
            if not agent_id or agent_id in seen_participants:
                continue
            seen_participants.add(agent_id)
            participant_ids.append(agent_id)
        if len(participant_ids) < 2:
            raise HTTPException(
                status_code=400,
                detail="A brainstorm requires at least two unique participant agents.",
            )
        moderator_agent_id = payload.get("moderator_agent_id")
        if moderator_agent_id:
            await self._ensure_brainstorm_agent_member(user, project.id, moderator_agent_id, "Moderator")
        else:
            manager = await self._project_default_manager(project.id, project=project)
            moderator_agent_id = manager.id if manager else participant_ids[0]
        await self._ensure_brainstorm_agent_member(user, project.id, moderator_agent_id, "Moderator")
        for agent_id in participant_ids:
            await self._ensure_brainstorm_agent_member(user, project.id, agent_id, "Participant")
        item = await self.repo.create_brainstorm(
            project_id=project.id,
            task_id=payload.get("task_id"),
            initiator_user_id=user.id,
            moderator_agent_id=moderator_agent_id,
            topic=payload["topic"],
            max_rounds=payload.get("max_rounds", 3),
            stop_conditions_json=stop_conditions,
            decision_log_json=[],
        )
        profiles: list[AgentProfile] = []
        for agent_id in participant_ids:
            profiles.append(await self.get_agent(user, agent_id))
        for i, left in enumerate(profiles):
            for right in profiles[i + 1 :]:
                if not self._brainstorm_pair_allowed(left, right, project=project):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Brainstorm collaboration rules disallow pairing '{left.slug}' "
                            f"with '{right.slug}' (allowed_brainstorm_with)."
                        ),
                    )
        for index, agent_id in enumerate(participant_ids):
            await self.repo.create_brainstorm_participant(
                brainstorm_id=item.id,
                agent_id=agent_id,
                order_index=index,
                stance=None,
            )
        await self.db.commit()
        await self.db.refresh(item)
        await self._decorate_brainstorms([item])
        return item

    async def list_brainstorms(self, user: User, project_id: str | None = None):
        items = await self.repo.list_brainstorms(user.id, project_id)
        await self._decorate_brainstorms(items)
        return items

    async def get_brainstorm(self, user: User, brainstorm_id: str):
        item = await self.repo.get_brainstorm(user.id, brainstorm_id)
        if not item:
            raise HTTPException(status_code=404, detail="Brainstorm not found")
        await self._decorate_brainstorms([item])
        return item

    async def list_brainstorm_participants(self, user: User, brainstorm_id: str):
        await self.get_brainstorm(user, brainstorm_id)
        return await self.repo.list_brainstorm_participants(brainstorm_id)

    async def add_brainstorm_participant(
        self,
        user: User,
        brainstorm_id: str,
        agent_id: str,
        stance: str | None = None,
    ):
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        if brainstorm.status in {"running", "completed"}:
            raise HTTPException(status_code=409, detail="Participants can only change before or between runs.")
        await self._ensure_brainstorm_agent_member(user, brainstorm.project_id, agent_id, "Participant")
        participants = await self.repo.list_brainstorm_participants(brainstorm.id)
        if any(item.agent_id == agent_id for item in participants):
            raise HTTPException(status_code=409, detail="Agent is already a brainstorm participant.")
        profiles = [await self.get_agent(user, item.agent_id) for item in participants]
        candidate = await self.get_agent(user, agent_id)
        project = await self.get_project(user, brainstorm.project_id)
        if any(not self._brainstorm_pair_allowed(existing, candidate, project=project) for existing in profiles):
            raise HTTPException(status_code=400, detail="Brainstorm collaboration rules disallow this participant.")
        item = await self.repo.create_brainstorm_participant(
            brainstorm_id=brainstorm.id,
            agent_id=agent_id,
            order_index=max((item.order_index for item in participants), default=-1) + 1,
            stance=stance,
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def update_brainstorm_participant(
        self,
        user: User,
        brainstorm_id: str,
        participant_id: str,
        updates: dict[str, Any],
    ):
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        if brainstorm.status in {"running", "completed"}:
            raise HTTPException(status_code=409, detail="Participants can only change before or between runs.")
        participants = await self.repo.list_brainstorm_participants(brainstorm.id)
        item = next((row for row in participants if row.id == participant_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail="Brainstorm participant not found")
        if "stance" in updates:
            item.stance = updates["stance"]
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def remove_brainstorm_participant(self, user: User, brainstorm_id: str, participant_id: str) -> None:
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        if brainstorm.status in {"running", "completed"}:
            raise HTTPException(status_code=409, detail="Participants can only change before or between runs.")
        participants = await self.repo.list_brainstorm_participants(brainstorm.id)
        item = next((row for row in participants if row.id == participant_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail="Brainstorm participant not found")
        if len(participants) <= 2:
            raise HTTPException(status_code=409, detail="A brainstorm requires at least two participants.")
        await self.db.delete(item)
        await self.db.commit()

    async def list_brainstorm_messages(self, user: User, brainstorm_id: str):
        await self.get_brainstorm(user, brainstorm_id)
        return await self.repo.list_brainstorm_messages(brainstorm_id)

    async def start_brainstorm(self, user: User, brainstorm_id: str):
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        if brainstorm.status == "completed":
            raise HTTPException(status_code=409, detail="Brainstorm is already completed")
        active_runs = await self.repo.list_brainstorm_runs(brainstorm.id)
        if any(item.status in {"queued", "in_progress", "blocked"} for item in active_runs):
            raise HTTPException(status_code=409, detail="A brainstorm round is already active")
        current_round = self._brainstorm_current_round(brainstorm)
        if current_round >= brainstorm.max_rounds:
            raise HTTPException(status_code=409, detail="Brainstorm already reached the round limit")
        run = await self.repo.create_run(
            project_id=brainstorm.project_id,
            task_id=brainstorm.task_id,
            triggered_by_user_id=user.id,
            orchestrator_agent_id=brainstorm.moderator_agent_id,
            brainstorm_id=brainstorm.id,
            run_mode="brainstorm",
            status="queued",
            input_payload_json={"topic": brainstorm.topic, "target_round": current_round + 1},
        )
        brainstorm.status = "running"
        await self._emit_run_event(
            run,
            event_type="brainstorm_queued",
            message=f"Brainstorm round {current_round + 1} queued.",
        )
        from backend.modules.orchestration.execution.durable_execution import (
            submit_orchestration_run,
        )

        submit_orchestration_run(run.id)
        return run

    async def promote_brainstorm_to_tasks(self, user: User, brainstorm_id: str):
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        final_output = self._brainstorm_final_output(brainstorm)
        if not final_output:
            raise HTTPException(status_code=409, detail="Brainstorm has no finalized output to promote")
        tasks: list[OrchestratorTask] = []
        for line in final_output.splitlines():
            cleaned = line.strip(" -0123456789.")
            if len(cleaned) < 6:
                continue
            tasks.append(
                await self.repo.create_task(
                    project_id=brainstorm.project_id,
                    created_by_user_id=user.id,
                    assigned_agent_id=None,
                    reviewer_agent_id=None,
                    title=cleaned[:255],
                    description=f"Generated from brainstorm {brainstorm.topic}",
                    source="brainstorm",
                    task_type="generated",
                    priority="normal",
                    status="backlog",
                    acceptance_criteria=None,
                    due_date=None,
                    labels_json=["brainstorm"],
                    result_payload_json={"brainstorm_output_type": self._brainstorm_output_type(brainstorm)},
                    metadata_json={"brainstorm_id": brainstorm.id, "promoted_from": "brainstorm"},
                    position=await self.repo.get_next_task_position(brainstorm.project_id),
                )
            )
        await self.db.commit()
        return tasks

    async def force_brainstorm_summary(self, user: User, brainstorm_id: str):
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        if brainstorm.status == "completed":
            return brainstorm
        await self._finalize_brainstorm_output(brainstorm, reason="forced_summary")
        await self.db.commit()
        await self._decorate_brainstorms([brainstorm])
        return brainstorm

    async def promote_brainstorm_to_adr(self, user: User, brainstorm_id: str):
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        final_output = self._brainstorm_final_output(brainstorm)
        if not final_output:
            raise HTTPException(status_code=409, detail="Brainstorm has no finalized output to promote")
        decision = await self.repo.create_project_decision(
            project_id=brainstorm.project_id,
            task_id=brainstorm.task_id,
            brainstorm_id=brainstorm.id,
            title=f"ADR: {brainstorm.topic[:240]}",
            decision=final_output,
            rationale=brainstorm.summary,
            author_label="Brainstorm",
        )
        await self.db.commit()
        await self.db.refresh(decision)
        return decision

    async def promote_brainstorm_to_document(self, user: User, brainstorm_id: str):
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        final_output = self._brainstorm_final_output(brainstorm)
        if not final_output:
            raise HTTPException(status_code=409, detail="Brainstorm has no finalized output to promote")
        item = await self.repo.create_document(
            project_id=brainstorm.project_id,
            task_id=brainstorm.task_id,
            uploaded_by_user_id=user.id,
            filename=f"{self._slugify(brainstorm.topic)}-{self._brainstorm_output_type(brainstorm)}.md"[:255],
            content_type="text/markdown",
            source_text=final_output,
            object_key=None,
            size_bytes=len(final_output.encode("utf-8")),
            summary_text=(brainstorm.summary or final_output[:500])[:2000],
            ingestion_status="pending",
            chunk_count=0,
            ttl_days=None,
            expires_at=None,
            metadata_json={
                "brainstorm_id": brainstorm.id,
                "source": "brainstorm",
                "source_kind": "brainstorm",
                "output_type": self._brainstorm_output_type(brainstorm),
            },
        )
        await self._index_project_document(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def export_brainstorm_artifact(self, user: User, brainstorm_id: str) -> dict[str, Any]:
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        final_output = self._brainstorm_final_output(brainstorm)
        if not final_output:
            raise HTTPException(status_code=409, detail="Brainstorm has no finalized output to export")
        output_type = self._brainstorm_output_type(brainstorm)
        title = f"{brainstorm.topic[:220]} — {output_type.replace('_', ' ').title()}"
        for entry in reversed(brainstorm.decision_log_json or []):
            if entry.get("type") == "artifact_export" and entry.get("output_type") == output_type:
                return {
                    "artifact_kind": entry.get("artifact_kind", "project_document"),
                    "artifact_id": str(entry.get("artifact_id")),
                    "output_type": output_type,
                    "title": title,
                    "content": final_output,
                    "created_at": entry.get("created_at") or datetime.now(UTC),
                }
        metadata = {
            "brainstorm_id": brainstorm.id,
            "output_type": output_type,
            "source": "brainstorm",
        }
        if output_type == "adr":
            item = await self.repo.create_project_decision(
                project_id=brainstorm.project_id,
                task_id=brainstorm.task_id,
                brainstorm_id=brainstorm.id,
                title=f"ADR: {brainstorm.topic[:240]}",
                decision=final_output,
                rationale=brainstorm.summary,
                author_label="Brainstorm",
            )
            artifact_kind = "project_decision"
        elif brainstorm.task_id:
            item = await self.repo.create_task_artifact(
                task_id=brainstorm.task_id,
                run_id=None,
                kind=output_type,
                title=title[:255],
                content=final_output,
                metadata_json=metadata,
            )
            artifact_kind = "task_artifact"
        else:
            item = await self.repo.create_document(
                project_id=brainstorm.project_id,
                task_id=None,
                uploaded_by_user_id=user.id,
                filename=f"{self._slugify(brainstorm.topic)}-{output_type}.md"[:255],
                content_type="text/markdown",
                source_text=final_output,
                object_key=None,
                size_bytes=len(final_output.encode("utf-8")),
                summary_text=(brainstorm.summary or final_output[:500])[:2000],
                ingestion_status="pending",
                chunk_count=0,
                ttl_days=None,
                expires_at=None,
                metadata_json=metadata,
            )
            await self._index_project_document(item)
            artifact_kind = "project_document"
        decision_log = list(brainstorm.decision_log_json or [])
        decision_log.append(
            {
                "type": "artifact_export",
                "artifact_kind": artifact_kind,
                "output_type": output_type,
                "artifact_id": item.id,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        brainstorm.decision_log_json = decision_log
        await self.db.commit()
        await self.db.refresh(item)
        return {
            "artifact_kind": artifact_kind,
            "artifact_id": item.id,
            "output_type": output_type,
            "title": title,
            "content": final_output,
            "created_at": item.created_at,
        }

    async def _decorate_brainstorms(self, items: list[Brainstorm]) -> None:
        counts = await self.repo.count_brainstorm_participants([item.id for item in items])
        for item in items:
            stop_conditions = item.stop_conditions_json or {}
            latest_round_summary = None
            for decision in reversed(item.decision_log_json or []):
                if decision.get("type") == "round_summary":
                    latest_round_summary = decision.get("summary")
                    break
            item.__orchestration_view__ = {
                "mode": stop_conditions.get("mode", "exploration"),
                "output_type": stop_conditions.get("output_type", "implementation_plan"),
                "participant_count": counts.get(item.id, 0),
                "current_round": self._brainstorm_current_round(item),
                "consensus_status": stop_conditions.get("consensus_status", "open"),
                "latest_round_summary": latest_round_summary,
            }

    def _normalize_brainstorm_stop_conditions(self, payload: dict[str, Any]) -> dict[str, Any]:
        stop_conditions = dict(payload.get("stop_conditions") or {})
        mode = self._normalize_brainstorm_mode(
            payload.get("mode") or stop_conditions.get("mode") or "exploration"
        )
        output_type = self._normalize_brainstorm_output_type(
            payload.get("output_type") or stop_conditions.get("output_type") or self._brainstorm_default_output_type(mode)
        )
        stop_conditions["mode"] = mode
        stop_conditions["output_type"] = output_type
        stop_conditions["max_cost_usd"] = self._guardrail_float(
            payload.get("max_cost_usd") or stop_conditions.get("max_cost_usd") or 10,
            "max_cost_usd",
            0.1,
            1000,
        )
        stop_conditions["max_repetition_score"] = self._guardrail_float(
            payload.get("max_repetition_score") or stop_conditions.get("max_repetition_score") or 0.92,
            "max_repetition_score",
            0.1,
            1,
        )
        stop_conditions["stop_on_consensus"] = self._guardrail_bool(stop_conditions.get("stop_on_consensus", True))
        stop_conditions["escalate_on_no_consensus"] = self._guardrail_bool(
            stop_conditions.get("escalate_on_no_consensus", True)
        )
        stop_conditions.setdefault("consensus_status", "open")
        stop_conditions["soft_consensus_min_similarity"] = self._guardrail_float(
            stop_conditions.get("soft_consensus_min_similarity", 0.72),
            "soft_consensus_min_similarity",
            0,
            1,
        )
        stop_conditions["accept_soft_consensus"] = self._guardrail_bool(
            stop_conditions.get("accept_soft_consensus", True)
        )
        stop_conditions["conflict_pairwise_max_similarity"] = self._guardrail_float(
            stop_conditions.get("conflict_pairwise_max_similarity", 0.38),
            "conflict_pairwise_max_similarity",
            0,
            1,
        )
        stop_conditions["conflict_requires_moderation"] = self._guardrail_bool(
            stop_conditions.get("conflict_requires_moderation", True)
        )
        return stop_conditions

    def _guardrail_float(self, value: Any, name: str, minimum: float, maximum: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"{name} must be a number.") from exc
        if not minimum <= parsed <= maximum:
            raise HTTPException(
                status_code=422,
                detail=f"{name} must be between {minimum} and {maximum}.",
            )
        return parsed

    def _guardrail_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in {"0", "false", "no", "off", ""}

    def _normalize_brainstorm_mode(self, value: Any) -> str:
        raw = re.sub(r"[^a-z0-9]+", "_", str(value or "exploration").strip().lower()).strip("_")
        aliases = {
            "exploration": "exploration",
            "solution_design": "solution_design",
            "code_review": "code_review",
            "code_review_debate": "code_review",
            "incident_triage": "incident_triage",
            "root_cause": "root_cause",
            "root_cause_analysis": "root_cause",
            "architecture_proposal": "architecture_proposal",
        }
        return aliases.get(raw, "exploration")

    def _normalize_brainstorm_output_type(self, value: Any) -> str:
        raw = re.sub(r"[^a-z0-9]+", "_", str(value or "implementation_plan").strip().lower()).strip("_")
        aliases = {
            "adr": "adr",
            "architecture_decision_record": "adr",
            "implementation_plan": "implementation_plan",
            "delivery_plan": "implementation_plan",
            "test_plan": "test_plan",
            "verification_plan": "test_plan",
            "issue_reply": "issue_reply_draft",
            "issue_reply_draft": "issue_reply_draft",
            "risk_register": "risk_register",
        }
        return aliases.get(raw, "implementation_plan")

    def _brainstorm_default_output_type(self, mode: str) -> str:
        defaults = {
            "exploration": "implementation_plan",
            "solution_design": "implementation_plan",
            "code_review": "test_plan",
            "incident_triage": "risk_register",
            "root_cause": "risk_register",
            "architecture_proposal": "adr",
        }
        return defaults.get(mode, "implementation_plan")

    def _brainstorm_mode(self, brainstorm: Brainstorm) -> str:
        return str((brainstorm.stop_conditions_json or {}).get("mode") or "exploration")

    def _brainstorm_output_type(self, brainstorm: Brainstorm) -> str:
        return str((brainstorm.stop_conditions_json or {}).get("output_type") or "implementation_plan")

    def _brainstorm_current_round(self, brainstorm: Brainstorm) -> int:
        summaries = [int(item.get("round", 0)) for item in (brainstorm.decision_log_json or []) if item.get("type") == "round_summary"]
        return max(summaries, default=0)

    def _brainstorm_final_output(self, brainstorm: Brainstorm) -> str | None:
        final_entry = next(
            (item for item in reversed(brainstorm.decision_log_json or []) if item.get("type") == "final_output"),
            None,
        )
        if final_entry and final_entry.get("content"):
            return str(final_entry["content"])
        return brainstorm.final_recommendation or brainstorm.summary

    def _brainstorm_mode_instruction(self, mode: str) -> str:
        prompts = {
            "exploration": "Surface broad options, assumptions, open questions, and promising directions.",
            "solution_design": "Converge on an implementation design with architecture, interfaces, and tradeoffs.",
            "code_review": "Critique proposed changes, find risks, and recommend fixes and tests.",
            "incident_triage": "Prioritize likely causes, blast radius, mitigations, and immediate next actions.",
            "root_cause": "Reason from symptoms to root causes, evidence gaps, and validation steps.",
            "architecture_proposal": "Produce a structured architecture recommendation with constraints and alternatives.",
        }
        return prompts.get(mode, prompts["exploration"])

    def _brainstorm_output_instruction(self, output_type: str) -> str:
        prompts = {
            "adr": "Return an ADR-style document with Context, Decision, Consequences, and Follow-ups.",
            "implementation_plan": "Return an implementation plan with phases, owners, dependencies, and risks.",
            "test_plan": "Return a test plan with scenarios, acceptance checks, fixtures, and failure modes.",
            "issue_reply_draft": "Return a concise issue reply draft with status, evidence, next steps, and explicit asks.",
            "risk_register": "Return a risk register with severity, impact, mitigation, and contingency.",
        }
        return prompts.get(output_type, prompts["implementation_plan"])

    async def _ensure_brainstorm_agent_member(
        self,
        user: User,
        project_id: str,
        agent_id: str,
        relationship: str,
    ) -> AgentProfile:
        agent = await self.get_agent(user, agent_id)
        membership = await self.repo.get_project_membership(project_id, agent_id)
        if membership is None:
            raise HTTPException(
                status_code=422,
                detail=f"{relationship} agent must be assigned to this project before joining the brainstorm.",
            )
        if not agent.is_active:
            raise HTTPException(status_code=422, detail=f"{relationship} agent is inactive.")
        return agent

    def _message_similarity(self, left: str, right: str) -> float:
        left_tokens = {token for token in re.findall(r"[a-z0-9_]+", left.lower()) if len(token) > 2}
        right_tokens = {token for token in re.findall(r"[a-z0-9_]+", right.lower()) if len(token) > 2}
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = len(left_tokens.intersection(right_tokens))
        union = len(left_tokens.union(right_tokens))
        return intersection / union if union else 0.0

    def _brainstorm_first_line(self, text: str) -> str:
        for line in (text or "").splitlines():
            stripped = line.strip()
            if stripped:
                return stripped.lower()[:160]
        return (text or "").strip().lower()[:160]

    def _brainstorm_consensus_metrics_from_contents(
        self, contents: list[str], soft_thr: float, conflict_thr: float
    ) -> dict[str, Any]:
        n = len(contents)
        if n < 2:
            return {
                "pairwise_min_similarity": None,
                "pairwise_max_similarity": None,
                "repetition_score": 0.0,
                "conflict_signal": False,
                "consensus_kind": "none",
                "soft_consensus_match": False,
            }
        pairwise: list[float] = []
        for i in range(n):
            for j in range(i + 1, n):
                pairwise.append(self._message_similarity(contents[i], contents[j]))
        min_s = min(pairwise)
        max_s = max(pairwise)
        adj_scores = [
            self._message_similarity(contents[i - 1], contents[i]) for i in range(1, n)
        ]
        rep = max(adj_scores, default=0.0)
        normalized = {c.strip().lower()[:120] for c in contents if c.strip()}
        hard = len(normalized) == 1
        soft_match = min_s >= soft_thr
        distinct_lines = {self._brainstorm_first_line(c) for c in contents}
        conflict = max_s <= conflict_thr and len(distinct_lines) >= min(3, n)
        consensus_kind = "hard" if hard else "soft" if soft_match else "none"
        return {
            "pairwise_min_similarity": round(float(min_s), 4),
            "pairwise_max_similarity": round(float(max_s), 4),
            "repetition_score": round(float(rep), 4),
            "conflict_signal": bool(conflict),
            "consensus_kind": consensus_kind,
            "soft_consensus_match": bool(soft_match),
        }

    def _structured_output_response_format(self, agent: AgentProfile | None) -> str:
        policy = (agent.model_policy_json if agent else {}) or {}
        if policy.get("structured_output") is True or policy.get("structured_output_enabled") is True:
            return "json"
        schema = (agent.output_schema_json or {}) if agent else {}
        if str(schema.get("format") or "").strip().lower() == "json":
            return "json"
        return "text"

    def _tool_calling_allowed(self, agent: AgentProfile | None) -> bool:
        if agent is None:
            return True
        policy = agent.model_policy_json or {}
        if "tool_calling" in policy:
            return bool(policy.get("tool_calling"))
        if "tool_calling_enabled" in policy:
            return bool(policy.get("tool_calling_enabled"))
        return True

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "brainstorm-output"

    async def _generate_brainstorm_round_summary(
        self,
        run: TaskRun,
        provider: ProviderConfig | None,
        moderator: AgentProfile | None,
        mode: str,
        round_number: int,
        round_messages: list[dict[str, Any]],
    ) -> str:
        run.input_payload_json = {**(run.input_payload_json or {}), "fallback_model": provider.default_model if provider else None}
        _, result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=moderator,
            system_prompt=(moderator.system_prompt if moderator else "You summarize multi-agent discussion rounds."),
            user_prompt=(
                f"Summarize brainstorm mode '{mode}' after round {round_number}. "
                "Be concise. Capture consensus, unresolved disagreements, and the best next move.\n\n"
                f"{json.dumps(round_messages, indent=2)}"
            ),
            purpose="brainstorm round summary",
        )
        return result.output_text[:2000]

    async def _finalize_brainstorm_output(
        self,
        brainstorm: Brainstorm,
        *,
        run: TaskRun | None = None,
        provider: ProviderConfig | None = None,
        moderator: AgentProfile | None = None,
        reason: str,
    ) -> None:
        messages = await self.repo.list_brainstorm_messages(brainstorm.id)
        transcript = [
            {
                "round": item.round_number,
                "agent_id": item.agent_id,
                "message_type": item.message_type,
                "content": item.content,
            }
            for item in messages
        ]
        if provider is None and run is not None:
            moderator = moderator or await self._load_agent_for_run(brainstorm.moderator_agent_id)
            provider = await self._resolve_provider_for_run(run, moderator)
        elif provider is None:
            moderator = moderator or await self._load_agent_for_run(brainstorm.moderator_agent_id)
            if moderator and moderator.provider_config_id:
                provider = await self.db.get(ProviderConfig, moderator.provider_config_id)
            if provider is None:
                project = await self.db.get(OrchestratorProject, brainstorm.project_id)
                providers = await self.repo.list_providers(brainstorm.initiator_user_id, project.id if project else None)
                provider = next((item for item in providers if item.is_default), None) or (providers[0] if providers else None)
        output_type = self._brainstorm_output_type(brainstorm)
        _, result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=moderator,
            system_prompt=(moderator.system_prompt if moderator else "You are a structured discussion moderator."),
            user_prompt=(
                f"Finalize brainstorm '{brainstorm.topic}'. Reason: {reason}. "
                f"Output target: {output_type}. {self._brainstorm_output_instruction(output_type)}\n\n"
                f"Transcript:\n{json.dumps(transcript, indent=2)}"
            ),
            append_metrics=run is not None,
            purpose="brainstorm finalization",
        )
        brainstorm.summary = (brainstorm.summary or result.output_text[:2000])[:4000]
        brainstorm.final_recommendation = result.output_text[:4000]
        brainstorm.status = "completed"
        brainstorm.updated_at = datetime.now(UTC)
        stop_conditions = dict(brainstorm.stop_conditions_json or {})
        stop_conditions["consensus_status"] = stop_conditions.get("consensus_status", "open")
        brainstorm.stop_conditions_json = stop_conditions
        decision_log = list(brainstorm.decision_log_json or [])
        decision_log.append(
            {
                "type": "final_output",
                "reason": reason,
                "output_type": output_type,
                "content": result.output_text[:12000],
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        brainstorm.decision_log_json = decision_log

    async def _execute_brainstorm_run(self, run: TaskRun) -> None:
        brainstorm = await self.db.get(Brainstorm, run.brainstorm_id) if run.brainstorm_id else None
        if brainstorm is None:
            raise RuntimeError("Brainstorm run missing brainstorm context.")
        participants = await self.repo.list_brainstorm_participants(brainstorm.id)
        if not participants:
            raise RuntimeError("Brainstorm has no participants.")
        moderator = await self._load_agent_for_run(brainstorm.moderator_agent_id)
        provider = await self._resolve_provider_for_run(run, moderator)
        stop_conditions = dict(brainstorm.stop_conditions_json or {})
        mode = self._brainstorm_mode(brainstorm)
        current_round = self._brainstorm_current_round(brainstorm)
        target_round = int(run.input_payload_json.get("target_round") or current_round + 1)
        prior_messages = await self.repo.list_brainstorm_messages(brainstorm.id)
        conversation = [
            {
                "round": item.round_number,
                "agent_id": item.agent_id,
                "message_type": item.message_type,
                "content": item.content,
            }
            for item in prior_messages
        ]
        round_messages: list[dict[str, Any]] = []
        mode_instruction = self._brainstorm_mode_instruction(mode)
        for participant in participants:
            agent = await self._load_agent_for_run(participant.agent_id)
            context = "\n\n".join(
                f"Round {item['round']} {item.get('agent_id')}: {item['content']}"
                for item in conversation[-6:]
            )
            _, result = await self._execute_with_routing(
                run,
                provider=provider,
                agent=agent,
                system_prompt=(agent.system_prompt if agent else "You are a brainstorming participant."),
                user_prompt=(
                    f"Brainstorm topic: {brainstorm.topic}\n"
                    f"Mode: {mode}\n"
                    f"Round: {target_round}\n"
                    f"Instruction: {mode_instruction}\n"
                    f"Prior discussion:\n{context or 'No prior discussion.'}\n\n"
                    "State your position, supporting evidence, major tradeoffs, and your recommended next move."
                ),
                purpose="brainstorm round",
            )
            text = result.output_text.strip()
            round_messages.append(
                {
                    "agent_id": participant.agent_id,
                    "agent_name": agent.name if agent else participant.agent_id,
                    "content": text,
                }
            )
            await self.repo.create_brainstorm_message(
                brainstorm_id=brainstorm.id,
                agent_id=participant.agent_id,
                round_number=target_round,
                message_type="argument",
                content=text,
                metadata_json={"mode": mode},
            )
            await self._emit_run_event(
                run,
                event_type="brainstorm_round",
                message=f"Round {target_round} response from {agent.name if agent else participant.agent_id}.",
                payload={"round": target_round, "agent_id": participant.agent_id},
            )
        repetition_score = 0.0
        if len(round_messages) >= 2:
            message_scores = []
            for index in range(1, len(round_messages)):
                message_scores.append(
                    self._message_similarity(
                        round_messages[index - 1]["content"],
                        round_messages[index]["content"],
                    )
                )
            repetition_score = max(message_scores, default=0.0)
        consensus_metrics = self._brainstorm_consensus_metrics_from_contents(
            [item["content"] for item in round_messages],
            float(stop_conditions.get("soft_consensus_min_similarity", 0.72)),
            float(stop_conditions.get("conflict_pairwise_max_similarity", 0.38)),
        )
        if len(round_messages) >= 2:
            consensus_metrics["repetition_score"] = round(float(repetition_score), 4)
        consensus_reached = False
        normalized_positions = {item["content"].strip().lower()[:120] for item in round_messages}
        hard_consensus = len(round_messages) >= 2 and len(normalized_positions) == 1
        soft_match = bool(consensus_metrics.get("soft_consensus_match"))
        if stop_conditions.get("stop_on_consensus", True) and len(round_messages) >= 2:
            consensus_reached = hard_consensus or (
                soft_match and bool(stop_conditions.get("accept_soft_consensus", True))
            )
        if consensus_reached:
            stop_conditions["consensus_status"] = "consensus" if hard_consensus else "soft_consensus"
        elif bool(consensus_metrics.get("conflict_signal")):
            stop_conditions["consensus_status"] = "conflict"
        elif repetition_score >= float(stop_conditions.get("max_repetition_score", 0.92)):
            stop_conditions["consensus_status"] = "loop_detected"
        else:
            stop_conditions["consensus_status"] = "open"
        round_summary = await self._generate_brainstorm_round_summary(
            run,
            provider,
            moderator,
            mode,
            target_round,
            round_messages,
        )
        decision_log = list(brainstorm.decision_log_json or [])
        decision_log.append(
            {
                "type": "round_summary",
                "round": target_round,
                "summary": round_summary,
                "repetition_score": repetition_score,
                "consensus_reached": consensus_reached,
                "consensus_kind": "hard" if hard_consensus else "soft" if soft_match else "open",
                "conflict_signal": bool(consensus_metrics.get("conflict_signal")),
                "pairwise_min_similarity": consensus_metrics.get("pairwise_min_similarity"),
                "pairwise_max_similarity": consensus_metrics.get("pairwise_max_similarity"),
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        brainstorm.decision_log_json = decision_log
        brainstorm.summary = round_summary
        brainstorm.updated_at = datetime.now(UTC)
        cost_usd = run.estimated_cost_micros / 1_000_000
        total_cost_usd = sum(
            item.estimated_cost_micros for item in await self.repo.list_brainstorm_runs(brainstorm.id)
        ) / 1_000_000
        force_finalize = False
        force_reason = ""
        if consensus_reached:
            force_finalize = True
            force_reason = "consensus"
        elif target_round >= brainstorm.max_rounds:
            force_finalize = True
            force_reason = "max_rounds"
        elif total_cost_usd >= float(stop_conditions.get("max_cost_usd", 10)):
            force_finalize = True
            force_reason = "max_cost"
        elif bool(consensus_metrics.get("conflict_signal")) and stop_conditions.get("conflict_requires_moderation", True):
            force_finalize = True
            force_reason = "conflict_requires_moderation"
        elif repetition_score >= float(stop_conditions.get("max_repetition_score", 0.92)):
            force_finalize = True
            force_reason = "loop_detected"

        brainstorm.stop_conditions_json = stop_conditions
        run.output_payload_json = {
            "summary": round_summary,
            "round_messages": round_messages,
            "consensus_reached": consensus_reached,
            "rounds_completed": target_round,
            "mode": mode,
            "output_type": self._brainstorm_output_type(brainstorm),
            "repetition_score": repetition_score,
            "cost_usd": cost_usd,
            "total_cost_usd": total_cost_usd,
            "consensus_metrics": consensus_metrics,
            "hard_consensus": hard_consensus,
            "soft_consensus_match": soft_match,
        }
        await self._emit_run_event(
            run,
            event_type="brainstorm_round_summary",
            message=f"Round {target_round} summary generated.",
            payload={"round": target_round, "repetition_score": repetition_score, "consensus_reached": consensus_reached},
        )
        if force_finalize:
            await self._finalize_brainstorm_output(
                brainstorm,
                run=run,
                provider=provider,
                moderator=moderator,
                reason=force_reason,
            )
            await self._emit_run_event(
                run,
                event_type="brainstorm_finalized",
                message=f"Brainstorm finalized after round {target_round}.",
                payload={"reason": force_reason},
            )
        else:
            brainstorm.status = "running"
        if (
            not consensus_reached
            and target_round >= brainstorm.max_rounds
            and stop_conditions.get("escalate_on_no_consensus", True)
        ):
            task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
            await self._escalate_blocker(
                run,
                task=task,
                reason="Brainstorm ended without consensus after configured limit.",
                metadata={"brainstorm_id": brainstorm.id, "round": target_round},
            )
        project = await self.db.get(OrchestratorProject, run.project_id)
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        if project and task:
            await self._apply_project_escalation_rules(
                project,
                run=run,
                task=task,
                trigger="brainstorm_finished",
                rounds_completed=target_round,
                consensus_reached=consensus_reached,
            )

    async def _execute_debate_run(self, run: TaskRun) -> None:
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise RuntimeError("Run project not found")
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        moderator = await self._load_agent_for_run(run.orchestrator_agent_id)
        participants = await self._debate_participants(
            project.id,
            preferred_ids=[run.worker_agent_id, run.reviewer_agent_id],
            task=task,
        )
        if len(participants) < 2:
            raise RuntimeError("Debate mode requires at least two agents")
        provider = await self._resolve_provider_for_run(run, moderator or participants[0])
        prompt = await self._build_task_prompt(run, moderator, prefix="Moderate a structured two-sided debate.")
        statements: list[dict[str, Any]] = []
        prior = ""
        for round_number in range(1, 3):
            for side, agent in enumerate(participants[:2], start=1):
                _, result = await self._execute_with_routing(
                    run,
                    provider=provider,
                    agent=agent,
                    system_prompt=agent.system_prompt or "You are a specialist debating a task approach.",
                    user_prompt=(
                        f"{prompt}\n\nDebate round {round_number}. You are side {side}. "
                        f"Respond to the prior position and defend your recommendation.\n\nPrior:\n{prior or 'No prior argument.'}"
                    ),
                    purpose="debate argument",
                )
                prior = result.output_text
                statements.append({"round": round_number, "agent_id": agent.id, "text": result.output_text})
                await self._emit_run_event(
                    run,
                    event_type="debate_argument",
                    message=f"Round {round_number} argument from {agent.name}.",
                    payload={"agent_id": agent.id},
                )
        _, moderator_result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=moderator,
            system_prompt=(moderator.system_prompt if moderator else "You are a moderator."),
            user_prompt=(
                "Resolve this debate and provide the final recommendation.\n\n"
                f"{json.dumps(statements, indent=2)}"
            ),
            purpose="debate moderation",
            response_format=self._structured_output_response_format(moderator),
        )
        run.output_payload_json = {
            "summary": moderator_result.output_text[:1200],
            "final_output": moderator_result.output_text,
            "debate_messages": statements,
        }
        await self._write_artifact(
            run,
            kind="debate_transcript",
            title="Debate transcript",
            content=json.dumps(statements, indent=2),
            metadata={"participant_count": 2},
        )
