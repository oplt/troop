from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.schemas import RequestModel
from backend.modules.github.schemas import GithubSyncEventResponse

from backend.modules.orchestration.schemas.agents import AgentResponse
from backend.modules.orchestration.schemas.approvals import ApprovalResponse
from backend.modules.orchestration.schemas.projects import ProjectResponse
from backend.modules.orchestration.schemas.runs import TaskRunResponse

class OverviewResponse(BaseModel):
    projects: list[ProjectResponse]
    agents: list[AgentResponse]
    active_runs: list[TaskRunResponse]
    pending_approvals: list[ApprovalResponse]
    github_events: list[GithubSyncEventResponse]
