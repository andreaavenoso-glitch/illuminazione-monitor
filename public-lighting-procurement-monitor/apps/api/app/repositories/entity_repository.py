from uuid import UUID

from app.models.entity import Entity
from app.schemas.entity import EntityCreate, EntityUpdate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class EntityRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, *, region: str | None = None) -> list[Entity]:
        stmt = select(Entity).order_by(Entity.name)
        if region:
            stmt = stmt.where(Entity.region == region)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, entity_id: UUID) -> Entity | None:
        return await self.session.get(Entity, entity_id)

    async def get_by_name_region(self, name: str, region: str | None) -> Entity | None:
        stmt = select(Entity).where(Entity.name == name, Entity.region == region)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, payload: EntityCreate) -> Entity:
        entity = Entity(**payload.model_dump())
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity_id: UUID, payload: EntityUpdate) -> Entity | None:
        entity = await self.get(entity_id)
        if entity is None:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(entity, field, value)
        await self.session.flush()
        return entity
