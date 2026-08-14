"""Portfolio-wide execution policy persistence."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from backend.modules.identity_access.models import User
from backend.modules.projects.orchestration_models import PortfolioExecutionPolicy


class PortfolioPolicyMixin:
    async def get_portfolio_execution_policy(self, user: User) -> dict[str, Any]:
        stmt = select(PortfolioExecutionPolicy).where(PortfolioExecutionPolicy.owner_id == user.id)
        record = (await self.db.execute(stmt)).scalar_one_or_none()
        return self._normalize_portfolio_execution_policy(record.settings_json if record else None)

    async def update_portfolio_execution_policy(
        self, user: User, payload: dict[str, Any]
    ) -> dict[str, Any]:
        normalized = self._normalize_portfolio_execution_policy(payload)
        stmt = select(PortfolioExecutionPolicy).where(PortfolioExecutionPolicy.owner_id == user.id)
        record = (await self.db.execute(stmt)).scalar_one_or_none()
        if record is None:
            record = PortfolioExecutionPolicy(owner_id=user.id, settings_json=normalized)
            self.db.add(record)
        else:
            record.settings_json = normalized

        projects = await self.repo.list_projects(user.id)
        for project in projects:
            project.settings_json = self._normalize_project_settings(
                self._apply_portfolio_defaults_to_project_settings(
                    project.settings_json or {},
                    normalized,
                )
            )

        await self.db.commit()
        return normalized
