from uuid import UUID

from app.core.database import get_session
from app.repositories.watchlist_repository import WatchlistRepository
from app.schemas.watchlist import WatchlistItemCreate, WatchlistItemRead, WatchlistItemUpdate
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("", response_model=list[WatchlistItemRead])
async def list_watchlist(
    active: bool | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[WatchlistItemRead]:
    repo = WatchlistRepository(session)
    items = await repo.list(active=active)
    return [WatchlistItemRead.model_validate(i) for i in items]


@router.post("", response_model=WatchlistItemRead, status_code=status.HTTP_201_CREATED)
async def create_watchlist_item(
    payload: WatchlistItemCreate,
    session: AsyncSession = Depends(get_session),
) -> WatchlistItemRead:
    repo = WatchlistRepository(session)
    created = await repo.create(payload)
    await session.commit()
    await session.refresh(created)
    return WatchlistItemRead.model_validate(created)


@router.patch("/{item_id}", response_model=WatchlistItemRead)
async def update_watchlist_item(
    item_id: UUID,
    payload: WatchlistItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> WatchlistItemRead:
    repo = WatchlistRepository(session)
    updated = await repo.update(item_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    await session.commit()
    await session.refresh(updated)
    return WatchlistItemRead.model_validate(updated)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist_item(
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    repo = WatchlistRepository(session)
    ok = await repo.delete(item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
