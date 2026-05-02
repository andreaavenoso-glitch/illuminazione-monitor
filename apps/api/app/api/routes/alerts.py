from uuid import UUID

from app.auth import current_user, require_role
from app.core.database import get_session
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import AlertRead
from fastapi import APIRouter, Depends, HTTPException
from shared_models import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    is_open: bool | None = True,
    severity: str | None = None,
    limit: int = 200,
    _: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AlertRead]:
    repo = AlertRepository(session)
    items = await repo.list(is_open=is_open, severity=severity, limit=limit)
    return [AlertRead.model_validate(i) for i in items]


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(
    alert_id: UUID,
    _: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> AlertRead:
    repo = AlertRepository(session)
    alert = await repo.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertRead.model_validate(alert)


@router.patch("/{alert_id}/close", response_model=AlertRead)
async def close_alert(
    alert_id: UUID,
    _: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
) -> AlertRead:
    repo = AlertRepository(session)
    alert = await repo.close(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    await session.commit()
    await session.refresh(alert)
    return AlertRead.model_validate(alert)
