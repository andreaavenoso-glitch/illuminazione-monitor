import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared_models.base import Base


class ProcurementRecord(Base):
    __tablename__ = "procurement_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    source_priority_rank: Mapped[int] = mapped_column(default=999, nullable=False)
    numero_gara_id: Mapped[str | None] = mapped_column(String, nullable=True)
    data_pubblicazione: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tipo_appalto: Mapped[str | None] = mapped_column(String, nullable=True)
    descrizione: Mapped[str | None] = mapped_column(Text, nullable=True)
    ente: Mapped[str] = mapped_column(String, nullable=False)
    importo: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    provincia: Mapped[str | None] = mapped_column(String, nullable=True)
    regione: Mapped[str | None] = mapped_column(String, nullable=True)
    comune: Mapped[str | None] = mapped_column(String, nullable=True)
    area_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipologia_gara_procedura: Mapped[str | None] = mapped_column(String, nullable=True)
    scadenza: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criterio: Mapped[str | None] = mapped_column(String, nullable=True)
    cig: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    classifiche: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_bando: Mapped[str] = mapped_column(String, nullable=False)
    macrosettore: Mapped[str] = mapped_column(
        String, nullable=False, default="Illuminazione pubblica"
    )
    stato_procedurale: Mapped[str] = mapped_column(String, nullable=False)
    tipo_novita: Mapped[str] = mapped_column(String, nullable=False)

    flag_concessione_ambito: Mapped[str] = mapped_column(String, nullable=False, default="No")
    flag_ppp_doppio_oggetto: Mapped[str] = mapped_column(String, nullable=False, default="No")
    flag_in_house_ambito: Mapped[str] = mapped_column(String, nullable=False, default="No")
    flag_om: Mapped[str] = mapped_column(String, nullable=False, default="No")
    flag_pre_gara: Mapped[str] = mapped_column(String, nullable=False, default="No")

    tag_tecnico: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_level: Mapped[str | None] = mapped_column(String, nullable=True)
    reliability_index: Mapped[str | None] = mapped_column(String, nullable=True)
    is_weak_evidence: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    master_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("procurement_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
