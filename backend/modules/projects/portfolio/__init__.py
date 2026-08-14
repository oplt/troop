"""Portfolio service composition."""

from __future__ import annotations

from backend.modules.projects.portfolio.budget import PortfolioBudgetMixin
from backend.modules.projects.portfolio.control_plane import PortfolioControlPlaneMixin
from backend.modules.projects.portfolio.insights import PortfolioInsightsMixin
from backend.modules.projects.portfolio.overview import PortfolioOverviewMixin
from backend.modules.projects.portfolio.policy import PortfolioPolicyMixin

__all__ = ["ProjectPortfolioMixin"]


class ProjectPortfolioMixin(
    PortfolioOverviewMixin,
    PortfolioPolicyMixin,
    PortfolioControlPlaneMixin,
    PortfolioInsightsMixin,
    PortfolioBudgetMixin,
):
    """Portfolio policy, summaries, control plane, and execution insights."""
