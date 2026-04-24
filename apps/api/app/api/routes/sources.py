from uuid import UUID

from app.core.database import get_session
from app.repositories.source_repository import SourceRepository
from app.schemas.source import SourceCreate, SourceRead, SourceUpdate
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("", response_model=list[SourceRead])
async def list_sources(
    active: bool | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[SourceRead]:
    repo = SourceRepository(session)
    items = await repo.list(active=active)
    return [SourceRead.model_validate(i) for i in items]


@router.post("", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate,
    session: AsyncSession = Depends(get_session),
) -> SourceRead:
    repo = SourceRepository(session)
    created = await repo.create(payload)
    await session.commit()
    await session.refresh(created)
    return SourceRead.model_validate(created)


@router.get("/{source_id}", response_model=SourceRead)
async def get_source(
    source_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> SourceRead:
    repo = SourceRepository(session)
    item = await repo.get(source_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return SourceRead.model_validate(item)


@router.patch("/{source_id}", response_model=SourceRead)
async def update_source(
    source_id: UUID,
    payload: SourceUpdate,
    session: AsyncSession = Depends(get_session),
) -> SourceRead:
    repo = SourceRepository(session)
    updated = await repo.update(source_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Source not found")
    await session.commit()
    await session.refresh(updated)
    return SourceRead.model_validate(updated)
