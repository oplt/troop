from datetime import date

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.calendar.models import CalendarEntry
from backend.modules.calendar.repository import CalendarRepository
from backend.modules.calendar.schemas import (
    CalendarItemCreate,
    CalendarItemResponse,
    CalendarItemUpdate,
)
from backend.modules.identity_access.models import User
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask, ProjectMilestone


class CalendarService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = CalendarRepository(db)

    async def list_items(
        self,
        user: User,
        start_date: date,
        end_date: date,
    ) -> list[CalendarItemResponse]:
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="Start date must be before end date")

        entries = await self.repo.list_entries_by_user_and_range(user.id, start_date, end_date)
        orch_tasks = await self.repo.list_orchestrator_tasks_due_for_owner(user.id, start_date, end_date)
        milestones = await self.repo.list_project_milestones_due_for_owner(user.id, start_date, end_date)

        items = [self._entry_to_response(entry) for entry in entries]
        items.extend(self._orchestrator_task_to_response(t, p) for t, p in orch_tasks)
        items.extend(self._milestone_to_response(m, p) for m, p in milestones)
        items.sort(
            key=lambda item: (
                item.date.isoformat(),
                item.start_time.isoformat() if item.start_time else "99:99:99",
                item.created_at.isoformat(),
            )
        )
        return items

    async def create_item(self, user: User, payload: CalendarItemCreate) -> CalendarItemResponse:
        if payload.type == "task":
            raise HTTPException(
                status_code=400,
                detail="Create tasks from agent projects; calendar task items are read-only.",
            )
        return await self._create_entry_item(user, payload)

    async def _create_entry_item(
        self,
        user: User,
        payload: CalendarItemCreate,
    ) -> CalendarItemResponse:
        if payload.project_id:
            raise HTTPException(status_code=400, detail="Project can only be set for task items")
        if payload.assignee_id:
            raise HTTPException(status_code=400, detail="Assignee can only be set for task items")
        if payload.priority not in {None, "medium"}:
            raise HTTPException(status_code=400, detail="Priority can only be set for task items")
        if payload.end_time and not payload.start_time:
            raise HTTPException(
                status_code=400,
                detail="Start time is required when end time is set",
            )
        if payload.start_time and payload.end_time and payload.end_time <= payload.start_time:
            raise HTTPException(status_code=400, detail="End time must be after start time")

        entry = await self.repo.create_entry(
            user_id=user.id,
            entry_type=payload.type,
            title=payload.title.strip(),
            description=payload.description.strip() if payload.description else None,
            scheduled_for=payload.date,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )
        await self.db.commit()
        await self.db.refresh(entry)
        return self._entry_to_response(entry)

    @staticmethod
    def _entry_to_response(entry: CalendarEntry) -> CalendarItemResponse:
        return CalendarItemResponse(
            id=entry.id,
            source="planner",
            type=entry.type,
            title=entry.title,
            description=entry.description,
            date=entry.scheduled_for,
            start_time=entry.start_time,
            end_time=entry.end_time,
            created_at=entry.created_at,
        )

    @staticmethod
    def _orchestrator_task_to_response(task: OrchestratorTask, project: OrchestratorProject) -> CalendarItemResponse:
        if not task.due_date:
            raise HTTPException(status_code=500, detail="Orchestrator task is missing a due date")
        return CalendarItemResponse(
            id=task.id,
            source="orchestration",
            type="task",
            title=task.title,
            description=task.description,
            date=task.due_date.date(),
            project_id=project.id,
            project_name=project.name,
            priority=task.priority if task.priority in {"low", "medium", "high", "urgent"} else "medium",
            status=task.status,
            created_at=task.created_at,
        )

    @staticmethod
    def _milestone_to_response(milestone: ProjectMilestone, project: OrchestratorProject) -> CalendarItemResponse:
        if not milestone.due_date:
            raise HTTPException(status_code=500, detail="Project milestone is missing a due date")
        return CalendarItemResponse(
            id=milestone.id,
            source="orchestration",
            type="event",
            title=f"Milestone: {milestone.title}",
            description=milestone.description,
            date=milestone.due_date.date(),
            project_id=project.id,
            project_name=project.name,
            status=milestone.status,
            created_at=milestone.updated_at,
        )

    async def get_planner_item(self, user: User, entry_id: str) -> CalendarItemResponse:
        entry = await self.repo.get_entry(user.id, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Calendar entry not found")
        return self._entry_to_response(entry)

    async def update_planner_item(self, user: User, entry_id: str, payload: CalendarItemUpdate) -> CalendarItemResponse:
        entry = await self.repo.get_entry(user.id, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Calendar entry not found")
        data = payload.model_dump(exclude_unset=True)
        if "title" in data and data["title"] is not None:
            entry.title = data["title"].strip()
        if "description" in data:
            entry.description = data["description"].strip() if data["description"] else None
        if "date" in data and data["date"] is not None:
            entry.scheduled_for = data["date"]
        if "start_time" in data:
            entry.start_time = data["start_time"]
        if "end_time" in data:
            entry.end_time = data["end_time"]
        if entry.end_time and not entry.start_time:
            raise HTTPException(status_code=400, detail="Start time is required when end time is set")
        if entry.start_time and entry.end_time and entry.end_time <= entry.start_time:
            raise HTTPException(status_code=400, detail="End time must be after start time")
        await self.db.commit()
        await self.db.refresh(entry)
        return self._entry_to_response(entry)

    async def delete_planner_item(self, user: User, entry_id: str) -> None:
        entry = await self.repo.get_entry(user.id, entry_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Calendar entry not found")
        await self.repo.delete_entry(entry)
        await self.db.commit()
