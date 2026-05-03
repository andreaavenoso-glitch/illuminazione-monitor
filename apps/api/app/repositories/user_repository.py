from datetime import UTC, datetime
from uuid import UUID

from shared_models import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list(self, *, active: bool | None = None) -> list[User]:
        stmt = select(User).order_by(User.created_at.desc())
        if active is not None:
            stmt = stmt.where(User.is_active == active)
        return list((await self.session.execute(stmt)).scalars().all())

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        role: str,
        full_name: str | None = None,
    ) -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hash,
            role=role,
            full_name=full_name,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update(self, user: User, **fields) -> User:
        for k, v in fields.items():
            setattr(user, k, v)
        await self.session.flush()
        return user

    async def touch_last_login(self, user: User) -> None:
        user.last_login_at = datetime.now(tz=UTC)
        await self.session.flush()

    async def delete(self, user_id: UUID) -> bool:
        user = await self.get(user_id)
        if user is None:
            return False
        await self.session.delete(user)
        await self.session.flush()
        return True
