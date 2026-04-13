from datetime import date as date_type, datetime, time
from typing import Literal

from pydantic import BaseModel, Field

from backend.core.schemas import RequestModel
from backend.modules.projects.schemas import TaskPriority

CalendarEntryType = Literal["event", "appointment"]
CalendarItemType = Literal["event", "appointment", "task"]
CalendarItemSource = Literal["planner", "task", "orchestration"]


class CalendarItemUpdate(RequestModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    date: date_type | None = None
    start_time: time | None = None
    end_time: time | None = None


class CalendarItemCreate(RequestModel):
    type: CalendarItemType
    title: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    date: date_type
    start_time: time | None = None
    end_time: time | None = None
    project_id: str | None = None
    priority: TaskPriority | None = "medium"
    assignee_id: str | None = None


class CalendarItemResponse(BaseModel):
    id: str
    source: CalendarItemSource
    type: CalendarItemType
    title: str
    description: str | None
    date: date_type
    start_time: time | None = None
    end_time: time | None = None
    project_id: str | None = None
    project_name: str | None = None
    priority: TaskPriority | None = None
    status: str | None = None
    created_at: datetime
