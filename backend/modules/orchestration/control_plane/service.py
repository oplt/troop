"""Hierarchy control plane composition."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.control_plane.hierarchy_snapshot import ControlPlaneHierarchyMixin
from backend.modules.orchestration.control_plane.member_status import ControlPlaneMemberStatusMixin
from backend.modules.orchestration.control_plane.pubsub import (
    ControlPlaneEvent,
    ControlPlanePubSub,
    control_plane_pubsub,
)
from backend.modules.orchestration.control_plane.runtime_profiles import ControlPlaneRuntimeProfilesMixin
from backend.modules.orchestration.control_plane.serializers import ControlPlaneSerializersMixin
from backend.modules.orchestration.control_plane.task_commands import ControlPlaneTasksMixin
from backend.modules.orchestration.control_plane.team_commands import ControlPlaneTeamMixin
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.services.service import OrchestrationService

__all__ = [
    "ControlPlaneEvent",
    "ControlPlanePubSub",
    "HierarchyControlPlaneService",
    "control_plane_pubsub",
]


class HierarchyControlPlaneService(
    ControlPlaneSerializersMixin,
    ControlPlaneMemberStatusMixin,
    ControlPlaneHierarchyMixin,
    ControlPlaneRuntimeProfilesMixin,
    ControlPlaneTeamMixin,
    ControlPlaneTasksMixin,
):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrchestrationRepository(db)
        self.service = OrchestrationService(db)
