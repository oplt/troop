"""Compatibility facade composing task service mixins."""

from __future__ import annotations

from sqlalchemy.orm import attributes as orm_attributes

from backend.modules.projects.tasks.acceptance import TaskAcceptanceMixin
from backend.modules.projects.tasks.artifacts import TaskArtifactsMixin
from backend.modules.projects.tasks.assignment import TaskAssignmentMixin
from backend.modules.projects.tasks.crud import TaskCrudMixin
from backend.modules.projects.tasks.dependencies import TaskDependenciesMixin
from backend.modules.projects.tasks.evidence import TaskEvidenceMixin
from backend.modules.projects.tasks.github import TaskGithubMixin
from backend.modules.projects.tasks.lifecycle import TaskLifecycleMixin
from backend.modules.projects.tasks.metadata import TaskMetadataMixin

__all__ = ["OrchestrationTasksServiceMixin", "orm_attributes"]


class OrchestrationTasksServiceMixin(
    TaskMetadataMixin,
    TaskCrudMixin,
    TaskDependenciesMixin,
    TaskAcceptanceMixin,
    TaskEvidenceMixin,
    TaskAssignmentMixin,
    TaskLifecycleMixin,
    TaskGithubMixin,
    TaskArtifactsMixin,
):
    """Task, acceptance, and subtask methods extracted from orchestration.

    The host service is expected to provide ``self.db`` and ``self.repo``, plus
    execution/github/memory helpers used by task lifecycle transitions.

    Requires ``self.db``, ``self.repo``, and the host's audit/provider
    dependencies. Calls execution, GitHub, and memory helpers during lifecycle
    transitions.
    """
