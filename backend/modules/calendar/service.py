from datetime import date

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.calendar.models import CalendarEntry
from backend.modules.calendar.repository import CalendarRepository
from backend.modules.calendar.schemas import CalendarItemCreate, CalendarItemResponse, CalendarItemUpdate
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask
from backend.modules.identity_access.models import User
from backend.modules.projects.models import Project, ProjectTask
from backend.modules.projects.repository import ProjectsRepository
from backend.modules.projects.schemas import ProjectTaskCreate
from backend.modules.projects.service import ProjectsService


class CalendarService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = CalendarRepository(db)
        self.projects_repo = ProjectsRepository(db)
        self.projects_service = ProjectsService(db)

    async def list_items(
        self,
        user: User,
        start_date: date,
        end_date: date,
    ) -> list[CalendarItemResponse]:
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="Start date must be before end date")

        entries = await self.repo.list_entries_by_user_and_range(user.id, start_date, end_date)
        tasks = await self.projects_repo.list_tasks_due_for_user(user.id, start_date, end_date)
        orch_tasks = await self.repo.list_orchestrator_tasks_due_for_owner(user.id, start_date, end_date)

        items = [self._entry_to_response(entry) for entry in entries]
        items.extend(self._task_to_response(task, project) for task, project in tasks)
        items.extend(self._orchestrator_task_to_response(t, p) for t, p in orch_tasks)
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
            return await self._create_task_item(user, payload)
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

    async def _create_task_item(
        self,
        user: User,
        payload: CalendarItemCreate,
    ) -> CalendarItemResponse:
        if not payload.project_id:
            raise HTTPException(status_code=400, detail="Project is required when creating a task")

        task, _ = await self.projects_service.create_task(
            user.id,
            user,
            payload.project_id,
            ProjectTaskCreate(
                title=payload.title.strip(),
                description=payload.description.strip() if payload.description else None,
                status="todo",
                priority=payload.priority or "medium",
                due_date=payload.date,
                assignee_id=payload.assignee_id or user.id,
            ),
        )
        project = await self.projects_service.get_project(user.id, payload.project_id)
        return self._task_to_response(task, project)

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
    def _task_to_response(task: ProjectTask, project: Project) -> CalendarItemResponse:
        if not task.due_date:
            raise HTTPException(status_code=500, detail="Task is missing a due date")

        return CalendarItemResponse(
            id=task.id,
            source="task",
            type="task",
            title=task.title,
            description=task.description,
            date=task.due_date,
            project_id=project.id,
            project_name=project.name,
            priority=task.priority,
            status=str(task.status),
            created_at=task.created_at,
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
