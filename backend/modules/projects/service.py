"""Compatibility facade composing project service mixins."""

from __future__ import annotations

from backend.modules.projects.portfolio_service import ProjectPortfolioMixin
from backend.modules.projects.project_crud import ProjectCrudMixin
from backend.modules.projects.project_hierarchy import ProjectHierarchyMixin
from backend.modules.projects.project_memory import ProjectMemoryMixin
from backend.modules.projects.project_settings import DEFAULT_PORTFOLIO_EXECUTION_POLICY
from backend.modules.projects.project_settings_service import ProjectSettingsMixin
from backend.modules.projects.project_team_service import ProjectTeamMixin
from backend.modules.projects.project_workspace import ProjectWorkspaceMixin

__all__ = ["DEFAULT_PORTFOLIO_EXECUTION_POLICY", "OrchestrationProjectsServiceMixin"]


class OrchestrationProjectsServiceMixin(
    ProjectCrudMixin,
    ProjectPortfolioMixin,
    ProjectSettingsMixin,
    ProjectHierarchyMixin,
    ProjectTeamMixin,
    ProjectWorkspaceMixin,
    ProjectMemoryMixin,
):
    """Project, portfolio, and policy methods extracted from orchestration.

    The host service is expected to provide ``self.db``, ``self.repo``,
    ``self.audit_repo``, and the orchestration-only helpers used for repository
    indexing, task bootstrapping, and knowledge-graph side effects.

    Requires ``self.db``, ``self.repo``, and ``self.audit_repo``. Calls task,
    provider-routing, and memory helpers supplied by the compatibility host;
    new code should prefer explicit domain objects.
    """
