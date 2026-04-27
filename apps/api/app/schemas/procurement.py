from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProcurementRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_id: str | None = None
    source_priority_rank: int
    numero_gara_id: str | None = None
    data_pubblicazione: datetime | None = None
    tipo_appalto: str | None = None
    descrizione: str | None = None
    ente: str
    importo: Decimal | None = None
    provincia: str | None = None
    regione: str | None = None
    comune: str | None = None
    tipologia_gara_procedura: str | None = None
    scadenza: datetime | None = None
    criterio: str | None = None
    cig: str | None = None
    classifiche: str | None = None
    link_bando: str
    macrosettore: str
    stato_procedurale: str
    tipo_novita: str
    flag_concessione_ambito: str
    flag_ppp_doppio_oggetto: str
    flag_in_house_ambito: str
    flag_om: str
    flag_pre_gara: str
    tag_tecnico: str | None = None
    validation_level: str | None = None
    reliability_index: str | None = None
    is_weak_evidence: bool
    score_commerciale: int | None = None
    priorita_commerciale: str | None = None
    dedup_key: str | None = None
    master_record_id: UUID | None = None
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass
class RecordFilters:
    regione: str | None = None
    provincia: str | None = None
    ente: str | None = None
    stato_procedurale: str | None = None
    tipo_novita: str | None = None
    flag_ppp_doppio_oggetto: str | None = None
    flag_om: str | None = None
    flag_pre_gara: str | None = None
    min_importo: float | None = None
    max_importo: float | None = None
    q: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    priorita: str | None = None
    only_masters: bool = False
