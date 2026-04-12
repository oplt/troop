from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import User


class UsersRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_profile(self, user: User, full_name: str | None) -> User:
        user.full_name = full_name
        await self.db.flush()
        return user

    async def list_active_users(self) -> list[User]:
        result = await self.db.execute(
            select(User)
            .where(User.is_active.is_(True))
            .order_by(
                User.full_name.is_(None),
                User.full_name.asc(),
                User.email.asc(),
            )
        )
        return list(result.scalars().all())

    async def get_active_user_by_id(self, user_id: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active.is_(True))
        )
        return result.scalar_one_or_none()
