from datetime import datetime
from uuid import UUID

from app.core.database import get_session
from app.repositories.procurement_repository import ProcurementRepository
from app.schemas.procurement import ProcurementRecordRead, RecordFilters
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("", response_model=list[ProcurementRecordRead])
async def list_records(
    regione: str | None = None,
    provincia: str | None = None,
    ente: str | None = None,
    stato_procedurale: str | None = None,
    tipo_novita: str | None = None,
    flag_ppp_doppio_oggetto: str | None = None,
    flag_om: str | None = None,
    flag_pre_gara: str | None = None,
    min_importo: float | None = None,
    max_importo: float | None = None,
    q: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    priorita: str | None = None,
    only_masters: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[ProcurementRecordRead]:
    filters = RecordFilters(
        regione=regione,
        provincia=provincia,
        ente=ente,
        stato_procedurale=stato_procedurale,
        tipo_novita=tipo_novita,
        flag_ppp_doppio_oggetto=flag_ppp_doppio_oggetto,
        flag_om=flag_om,
        flag_pre_gara=flag_pre_gara,
        min_importo=min_importo,
        max_importo=max_importo,
        q=q,
        date_from=date_from,
        date_to=date_to,
        priorita=priorita,
        only_masters=only_masters,
    )
    repo = ProcurementRepository(session)
    items = await repo.list(filters=filters, limit=limit, offset=offset)
    return [ProcurementRecordRead.model_validate(i) for i in items]


@router.get("/{record_id}", response_model=ProcurementRecordRead)
async def get_record(
    record_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> ProcurementRecordRead:
    repo = ProcurementRepository(session)
    item = await repo.get(record_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Record not found")
    return ProcurementRecordRead.model_validate(item)
