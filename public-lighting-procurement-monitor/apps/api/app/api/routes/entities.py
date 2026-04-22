from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.repositories.entity_repository import EntityRepository
from app.schemas.entity import EntityCreate, EntityRead, EntityUpdate

router = APIRouter()


@router.get("", response_model=list[EntityRead])
async def list_entities(
    region: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[EntityRead]:
    repo = EntityRepository(session)
    items = await repo.list(region=region)
    return [EntityRead.model_validate(i) for i in items]


@router.post("", response_model=EntityRead, status_code=status.HTTP_201_CREATED)
async def create_entity(
    payload: EntityCreate,
    session: AsyncSession = Depends(get_session),
) -> EntityRead:
    repo = EntityRepository(session)
    created = await repo.create(payload)
    await session.commit()
    await session.refresh(created)
    return EntityRead.model_validate(created)


@router.get("/{entity_id}", response_model=EntityRead)
async def get_entity(
    entity_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> EntityRead:
    repo = EntityRepository(session)
    item = await repo.get(entity_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return EntityRead.model_validate(item)


@router.patch("/{entity_id}", response_model=EntityRead)
async def update_entity(
    entity_id: UUID,
    payload: EntityUpdate,
    session: AsyncSession = Depends(get_session),
) -> EntityRead:
    repo = EntityRepository(session)
    updated = await repo.update(entity_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    await session.commit()
    await session.refresh(updated)
    return EntityRead.model_validate(updated)
