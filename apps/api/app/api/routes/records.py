from datetime import datetime
from uuid import UUID

from app.core.database import get_session
from app.repositories.procurement_repository import ProcurementRepository
from app.schemas.procurement import ProcurementRecordRead, RecordFilters
from app.services import exports_service
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _build_filters(
    regione: str | None,
    provincia: str | None,
    ente: str | None,
    stato_procedurale: str | None,
    tipo_novita: str | None,
    flag_ppp_doppio_oggetto: str | None,
    flag_om: str | None,
    flag_pre_gara: str | None,
    min_importo: float | None,
    max_importo: float | None,
    q: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    priorita: str | None,
    only_masters: bool,
) -> RecordFilters:
    return RecordFilters(
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


EXPORT_FORMATS = {
    "xlsx": (
        exports_service.render_xlsx,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    "csv": (exports_service.render_csv, "text/csv; charset=utf-8"),
    "json": (exports_service.render_json, "application/json"),
}


@router.get("/export/{fmt}")
async def export_records(
    fmt: str,
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
    only_masters: bool = True,
    limit: int = Query(default=10_000, ge=1, le=50_000),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(
            status_code=404, detail=f"Unsupported format: {fmt}. Use xlsx | csv | json."
        )
    renderer, media_type = EXPORT_FORMATS[fmt]
    filters = _build_filters(
        regione,
        provincia,
        ente,
        stato_procedurale,
        tipo_novita,
        flag_ppp_doppio_oggetto,
        flag_om,
        flag_pre_gara,
        min_importo,
        max_importo,
        q,
        date_from,
        date_to,
        priorita,
        only_masters,
    )
    repo = ProcurementRepository(session)
    items = await repo.list(filters=filters, limit=limit, offset=0)
    body = renderer(items)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    filename = f"illuminazione-{today}.{fmt}"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
