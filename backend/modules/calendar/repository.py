from datetime import date, time

from sqlalchemy import Date, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.calendar.models import CalendarEntry
from backend.modules.orchestration.models import OrchestratorProject, OrchestratorTask


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
            select(CalendarEntry).where(CalendarEntry.id == entry_id, CalendarEntry.user_id == user_id)
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
    ) -> list[tuple[OrchestratorTask, OrchestratorProject]]:
        stmt = (
            select(OrchestratorTask, OrchestratorProject)
            .join(OrchestratorProject, OrchestratorTask.project_id == OrchestratorProject.id)
            .where(
                OrchestratorProject.owner_id == owner_user_id,
                OrchestratorTask.due_date.isnot(None),
                cast(OrchestratorTask.due_date, Date) >= start_date,
                cast(OrchestratorTask.due_date, Date) <= end_date,
            )
            .order_by(OrchestratorTask.due_date.asc(), OrchestratorTask.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.all())

