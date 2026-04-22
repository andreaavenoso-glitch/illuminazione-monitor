from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.watchlist_item import WatchlistItem
from app.schemas.watchlist import WatchlistItemCreate, WatchlistItemUpdate


class WatchlistRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, *, active: bool | None = None) -> list[WatchlistItem]:
        stmt = select(WatchlistItem).order_by(WatchlistItem.priority, WatchlistItem.created_at)
        if active is not None:
            stmt = stmt.where(WatchlistItem.active == active)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, item_id: UUID) -> WatchlistItem | None:
        return await self.session.get(WatchlistItem, item_id)

    async def create(self, payload: WatchlistItemCreate) -> WatchlistItem:
        item = WatchlistItem(**payload.model_dump())
        self.session.add(item)
        await self.session.flush()
        return item

    async def update(self, item_id: UUID, payload: WatchlistItemUpdate) -> WatchlistItem | None:
        item = await self.get(item_id)
        if item is None:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        await self.session.flush()
        return item

    async def delete(self, item_id: UUID) -> bool:
        item = await self.get(item_id)
        if item is None:
            return False
        await self.session.delete(item)
        await self.session.flush()
        return True
