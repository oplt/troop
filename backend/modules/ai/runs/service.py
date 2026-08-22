"""AI Studio prompt execution runs."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from fastapi import HTTPException

from backend.modules.ai.models import AiPromptTemplate, AiPromptVersion
from backend.modules.ai.prompts.renderer import render_template
from backend.modules.ai.providers import ProviderGenerateRequest
from backend.modules.identity_access.models import User


class AiRunsMixin:
    """Run lifecycle behavior.

    Requires ``self.db``, ``self.repo``, and ``self.providers``. Calls
    ``self.retrieve_chunks`` from the retrieval domain until that domain is
    migrated to explicit composition.
    """

    async def _resolve_prompt_version(
        self,
        user: User,
        *,
        prompt_template_key: str | None,
        prompt_version_id: str | None,
    ) -> tuple[AiPromptTemplate | None, AiPromptVersion]:
        if prompt_version_id:
            version = await self.repo.get_prompt_version(prompt_version_id)
            if not version:
                raise HTTPException(status_code=404, detail="Prompt version not found")
            template = await self.repo.get_prompt_template_for_user(
                user.id, version.prompt_template_id
            )
            if not template:
                raise HTTPException(status_code=404, detail="Prompt template not found")
            return template, version
        if not prompt_template_key:
            raise HTTPException(
                status_code=422,
                detail="prompt_template_key or prompt_version_id is required",
            )
        template = await self.repo.get_prompt_template_by_key_for_user(user.id, prompt_template_key)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        versions = await self.repo.list_prompt_versions(template.id)
        version = None
        if template.active_version_id:
            version = next(
                (item for item in versions if item.id == template.active_version_id), None
            )
        if version is None:
            version = next((item for item in versions if item.is_published), None)
        if version is None and versions:
            version = versions[0]
        if version is None:
            raise HTTPException(status_code=422, detail="This prompt template has no versions yet")
        return template, version

    async def run_prompt(
        self,
        user: User,
        *,
        prompt_template_key: str | None,
        prompt_version_id: str | None,
        variables: dict[str, Any],
        retrieval_query: str | None,
        document_ids: list[str],
        top_k: int,
        review_required: bool,
        evaluation_dataset_id: str | None = None,
        evaluation_case_id: str | None = None,
        queue_async: bool = False,
        model_name: str | None = None,
    ):
        template, version = await self._resolve_prompt_version(
            user,
            prompt_template_key=prompt_template_key,
            prompt_version_id=prompt_version_id,
        )
        provider = self.providers.get(version.provider_key)
        matches: list[dict[str, Any]] = []
        if retrieval_query:
            matches = await self.retrieve_chunks(
                user,
                query=retrieval_query,
                document_ids=document_ids,
                top_k=top_k,
            )
            variables = {
                **variables,
                "retrieval_context": "\n\n".join(
                    f"[{item['document_title']} #{item['chunk_index']}]\n{item['content']}"
                    for item in matches
                ),
            }

        rendered_system_prompt = render_template(version.system_prompt, variables)
        rendered_user_prompt = render_template(version.user_prompt_template, variables)
        run = await self.repo.create_run(
            user_id=user.id,
            prompt_template_id=template.id if template else None,
            prompt_version_id=version.id,
            evaluation_dataset_id=evaluation_dataset_id,
            evaluation_case_id=evaluation_case_id,
            provider_key=version.provider_key,
            model_name=model_name or version.model_name,
            status="queued" if queue_async else "running",
            response_format=version.response_format,
            variables_json=variables,
            retrieval_query=retrieval_query,
            retrieved_chunk_ids_json=[item["chunk_id"] for item in matches],
            input_messages_json=[
                {"role": "system", "content": rendered_system_prompt},
                {"role": "user", "content": rendered_user_prompt},
            ],
            review_status="pending" if review_required else "not_requested",
        )
        await self.db.flush()

        if queue_async:
            await self.db.commit()
            await self.db.refresh(run)
            from backend.workers.orchestration import queue_ai_studio_run

            queue_ai_studio_run(run.id)
            return run

        return await self._complete_ai_run(
            run,
            user=user,
            provider=provider,
            version=version,
            rendered_system_prompt=rendered_system_prompt,
            rendered_user_prompt=rendered_user_prompt,
            review_required=review_required,
            model_name=model_name,
        )

    async def execute_queued_ai_run(self, run_id: str):
        run = await self.repo.get_run_by_id(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="AI run not found")
        if run.status not in {"queued", "running"}:
            return run
        version = (
            await self.repo.get_prompt_version(run.prompt_version_id)
            if run.prompt_version_id
            else None
        )
        if version is None:
            run.status = "failed"
            run.error_message = "Prompt version missing for queued AI run."
            run.completed_at = datetime.now(UTC)
            await self.db.commit()
            return run
        provider = self.providers.get(run.provider_key)
        messages = list(run.input_messages_json or [])
        system_prompt = next((m.get("content") for m in messages if m.get("role") == "system"), "")
        user_prompt = next((m.get("content") for m in messages if m.get("role") == "user"), "")
        run.status = "running"
        await self.db.commit()
        user = await self.db.get(User, run.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="AI run owner not found")
        return await self._complete_ai_run(
            run,
            user=user,
            provider=provider,
            version=version,
            rendered_system_prompt=str(system_prompt or ""),
            rendered_user_prompt=str(user_prompt or ""),
            review_required=run.review_status == "pending",
            model_name=run.model_name,
        )

    async def _complete_ai_run(
        self,
        run,
        *,
        user: User,
        provider,
        version,
        rendered_system_prompt: str,
        rendered_user_prompt: str,
        review_required: bool,
        model_name: str | None = None,
    ):
        started = perf_counter()
        effective_model = model_name or version.model_name
        try:
            result = await provider.generate(
                ProviderGenerateRequest(
                    model=effective_model,
                    system_prompt=rendered_system_prompt,
                    user_prompt=rendered_user_prompt,
                    response_format=version.response_format,
                    temperature=version.temperature,
                )
            )
            latency_ms = int((perf_counter() - started) * 1000)
            run.status = "completed"
            run.output_text = result.output_text
            run.output_json = result.output_json
            run.latency_ms = latency_ms
            run.input_tokens = result.input_tokens
            run.output_tokens = result.output_tokens
            run.total_tokens = result.total_tokens
            run.estimated_cost_micros = (result.input_tokens * version.input_cost_per_million) + (
                result.output_tokens * version.output_cost_per_million
            )
            run.completed_at = datetime.now(UTC)
        except HTTPException as exc:
            run.status = "failed"
            run.error_message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            run.completed_at = datetime.now(UTC)
            await self.db.commit()
            raise
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.now(UTC)
            await self.db.commit()
            raise HTTPException(status_code=502, detail="AI provider execution failed") from exc

        if review_required:
            await self.repo.create_review(
                run_id=run.id,
                requested_by_user_id=user.id,
                status="pending",
            )

        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def get_run(self, user: User, run_id: str):
        run = await self.repo.get_run_for_user(user.id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="AI run not found")
        return run

    async def list_runs(self, user: User, **page):
        return await self.repo.list_runs_for_user(user.id, **page)
