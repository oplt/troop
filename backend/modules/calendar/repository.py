from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.calendar.models import CalendarEntry
from backend.modules.orchestration.models import OrchestratorProject, OrchestratorTask
from backend.modules.projects.orchestration_models import ProjectMilestone


@dataclass(frozen=True, slots=True)
class CalendarTaskRow:
    id: str
    title: str
    status: str
    priority: str
    due_date: datetime
    created_at: datetime
    project_id: str
    project_name: str


@dataclass(frozen=True, slots=True)
class CalendarMilestoneRow:
    id: str
    title: str
    description: str | None
    status: str
    due_date: datetime
    updated_at: datetime
    project_id: str
    project_name: str


def date_range_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    """Half-open UTC bounds so indexed timestamp columns remain sargable."""
    start_dt = datetime.combine(start_date, time.min, tzinfo=UTC)
    end_dt = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC)
    return start_dt, end_dt


class CalendarRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_entries_by_user_and_range(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[CalendarEntry]:
        result = await self.db.execute(
            select(CalendarEntry)
            .where(
                CalendarEntry.user_id == user_id,
                CalendarEntry.scheduled_for >= start_date,
                CalendarEntry.scheduled_for <= end_date,
            )
            .order_by(
                CalendarEntry.scheduled_for.asc(),
                CalendarEntry.start_time.asc().nullslast(),
                CalendarEntry.created_at.asc(),
            )
        )
        return list(result.scalars().all())

    async def create_entry(
        self,
        user_id: str,
        entry_type: str,
        title: str,
        description: str | None,
        scheduled_for: date,
        start_time: time | None,
        end_time: time | None,
    ) -> CalendarEntry:
        entry = CalendarEntry(
            user_id=user_id,
            type=entry_type,
            title=title,
            description=description,
            scheduled_for=scheduled_for,
            start_time=start_time,
            end_time=end_time,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def get_entry(self, user_id: str, entry_id: str) -> CalendarEntry | None:
        result = await self.db.execute(
            select(CalendarEntry).where(
                CalendarEntry.id == entry_id,
                CalendarEntry.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_entry(self, entry: CalendarEntry) -> None:
        await self.db.delete(entry)
        await self.db.flush()

    async def list_orchestrator_tasks_due_for_owner(
        self,
        owner_user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[CalendarTaskRow]:
        start_dt, end_dt = date_range_bounds(start_date, end_date)
        stmt = (
            select(
                OrchestratorTask.id,
                OrchestratorTask.title,
                OrchestratorTask.status,
                OrchestratorTask.priority,
                OrchestratorTask.due_date,
                OrchestratorTask.created_at,
                OrchestratorProject.id.label("project_id"),
                OrchestratorProject.name.label("project_name"),
            )
            .join(OrchestratorProject, OrchestratorTask.project_id == OrchestratorProject.id)
            .where(
                OrchestratorProject.owner_id == owner_user_id,
                OrchestratorTask.due_date.isnot(None),
                OrchestratorTask.due_date >= start_dt,
                OrchestratorTask.due_date < end_dt,
            )
            .order_by(OrchestratorTask.due_date.asc(), OrchestratorTask.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return [
            CalendarTaskRow(
                id=row.id,
                title=row.title,
                status=row.status,
                priority=row.priority,
                due_date=row.due_date,
                created_at=row.created_at,
                project_id=row.project_id,
                project_name=row.project_name,
            )
            for row in result.all()
        ]

    async def list_project_milestones_due_for_owner(
        self,
        owner_user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[CalendarMilestoneRow]:
        start_dt, end_dt = date_range_bounds(start_date, end_date)
        stmt = (
            select(
                ProjectMilestone.id,
                ProjectMilestone.title,
                ProjectMilestone.description,
                ProjectMilestone.status,
                ProjectMilestone.due_date,
                ProjectMilestone.updated_at,
                OrchestratorProject.id.label("project_id"),
                OrchestratorProject.name.label("project_name"),
            )
            .join(OrchestratorProject, ProjectMilestone.project_id == OrchestratorProject.id)
            .where(
                OrchestratorProject.owner_id == owner_user_id,
                ProjectMilestone.due_date.isnot(None),
                ProjectMilestone.due_date >= start_dt,
                ProjectMilestone.due_date < end_dt,
            )
            .order_by(ProjectMilestone.due_date.asc(), ProjectMilestone.updated_at.asc())
        )
        result = await self.db.execute(stmt)
        return [
            CalendarMilestoneRow(
                id=row.id,
                title=row.title,
                description=row.description,
                status=row.status,
                due_date=row.due_date,
                updated_at=row.updated_at,
                project_id=row.project_id,
                project_name=row.project_name,
            )
            for row in result.all()
        ]
