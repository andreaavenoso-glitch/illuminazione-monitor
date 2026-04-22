from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement_record import ProcurementRecord
from app.schemas.procurement import RecordFilters


class ProcurementRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, record_id: UUID) -> ProcurementRecord | None:
        return await self.session.get(ProcurementRecord, record_id)

    async def list(
        self,
        *,
        filters: RecordFilters,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProcurementRecord]:
        stmt = select(ProcurementRecord).order_by(
            ProcurementRecord.data_pubblicazione.desc().nullslast(),
            ProcurementRecord.first_seen_at.desc(),
        )

        conditions = []
        if filters.regione:
            conditions.append(ProcurementRecord.regione == filters.regione)
        if filters.provincia:
            conditions.append(ProcurementRecord.provincia == filters.provincia)
        if filters.ente:
            conditions.append(ProcurementRecord.ente.ilike(f"%{filters.ente}%"))
        if filters.stato_procedurale:
            conditions.append(ProcurementRecord.stato_procedurale == filters.stato_procedurale)
        if filters.tipo_novita:
            conditions.append(ProcurementRecord.tipo_novita == filters.tipo_novita)
        if filters.flag_ppp_doppio_oggetto:
            conditions.append(
                ProcurementRecord.flag_ppp_doppio_oggetto == filters.flag_ppp_doppio_oggetto
            )
        if filters.flag_om:
            conditions.append(ProcurementRecord.flag_om == filters.flag_om)
        if filters.flag_pre_gara:
            conditions.append(ProcurementRecord.flag_pre_gara == filters.flag_pre_gara)
        if filters.min_importo is not None:
            conditions.append(ProcurementRecord.importo >= filters.min_importo)
        if filters.max_importo is not None:
            conditions.append(ProcurementRecord.importo <= filters.max_importo)
        if filters.date_from is not None:
            conditions.append(ProcurementRecord.data_pubblicazione >= filters.date_from)
        if filters.date_to is not None:
            conditions.append(ProcurementRecord.data_pubblicazione <= filters.date_to)
        if filters.q:
            like = f"%{filters.q}%"
            conditions.append(
                or_(
                    ProcurementRecord.ente.ilike(like),
                    ProcurementRecord.descrizione.ilike(like),
                    ProcurementRecord.cig.ilike(like),
                )
            )

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
