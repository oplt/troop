"""Portfolio budget burn projections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.modules.identity_access.models import User


class PortfolioBudgetMixin:
    async def project_budget_projection(
        self, user: User, days: int = 30
    ) -> dict[str, float | int | bool]:
        safe_days = max(1, min(int(days or 30), 365))
        since = datetime.now(UTC) - timedelta(days=safe_days)
        raw = await self.repo.aggregate_run_costs(user.id, since=since)
        total = float(raw.get("total_cost_micros") or 0) / 1_000_000
        burn_daily = total / safe_days
        projected_month = burn_daily * 30.0
        return {
            "days": safe_days,
            "total_cost_usd": round(total, 6),
            "daily_burn_usd": round(burn_daily, 6),
            "projected_monthly_usd": round(projected_month, 6),
            "soft_cap_warning": projected_month > 1000,
            "hard_cap_exceeded": projected_month > 5000,
        }
