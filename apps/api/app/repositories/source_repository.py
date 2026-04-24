from uuid import UUID

from app.models.source import Source
from app.schemas.source import SourceCreate, SourceUpdate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class SourceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, *, active: bool | None = None) -> list[Source]:
        stmt = select(Source).order_by(Source.source_priority_rank, Source.name)
        if active is not None:
            stmt = stmt.where(Source.active == active)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, source_id: UUID) -> Source | None:
        return await self.session.get(Source, source_id)

    async def get_by_name(self, name: str) -> Source | None:
        stmt = select(Source).where(Source.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, payload: SourceCreate) -> Source:
        entity = Source(**payload.model_dump())
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, source_id: UUID, payload: SourceUpdate) -> Source | None:
        entity = await self.get(source_id)
        if entity is None:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(entity, field, value)
        await self.session.flush()
        return entity
