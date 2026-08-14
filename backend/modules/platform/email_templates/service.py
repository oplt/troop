"""Transactional email template CRUD and rendering."""

from __future__ import annotations

import re

from fastapi import HTTPException

from backend.modules.platform.models import EmailTemplate

PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


class PlatformEmailTemplatesMixin:
    async def list_email_templates(self) -> list[EmailTemplate]:
        return await self.repo.list_email_templates()

    async def create_email_template(self, payload: dict) -> EmailTemplate:
        if await self.repo.get_email_template_by_key(payload["key"]) is not None:
            raise HTTPException(
                status_code=409, detail="An email template with this key already exists"
            )
        template = await self.repo.create_email_template(**payload)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def update_email_template(self, template_id: str, payload: dict) -> EmailTemplate:
        template = await self.repo.get_email_template_by_id(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Email template not found")
        for field, value in payload.items():
            setattr(template, field, value)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def render_email_template(
        self,
        *,
        key: str,
        context: dict[str, str],
        fallback_subject: str,
        fallback_html: str,
        fallback_text: str | None = None,
    ) -> tuple[str, str, str | None]:
        template = await self.repo.get_email_template_by_key(key)
        if not template or not template.is_active:
            return fallback_subject, fallback_html, fallback_text
        return (
            self._render_template_string(template.subject_template, context),
            self._render_template_string(template.html_template, context),
            (
                self._render_template_string(template.text_template, context)
                if template.text_template
                else None
            ),
        )
    @staticmethod
    def _render_template_string(template: str, context: dict[str, str]) -> str:
        def _replace(match: re.Match[str]) -> str:
            key = match.group(1)
            return str(context.get(key, ""))

        return PLACEHOLDER_PATTERN.sub(_replace, template)
