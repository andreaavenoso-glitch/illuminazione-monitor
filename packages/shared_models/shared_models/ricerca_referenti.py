import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared_models.base import Base


class RicercaReferenti(Base):
    """Outcome of the last search of an ente's referenti: the 12-step checklist with the URLs
    checked, what was not found, the press check. Lets anybody see WHY a name is missing."""

    __tablename__ = "ricerche_referenti"
    __table_args__ = (UniqueConstraint("ente", "regione", name="uq_ricerca_referenti"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ente: Mapped[str] = mapped_column(String, nullable=False, index=True)
    regione: Mapped[str | None] = mapped_column(String, nullable=True)
    metodo: Mapped[str] = mapped_column(String, nullable=False, default="script")  # script | agente | pagine
    checklist: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    lacune: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    stampa: Mapped[str | None] = mapped_column(Text, nullable=True)
    elezione_data: Mapped[date | None] = mapped_column(Date, nullable=True)
    mandato_scadenza: Mapped[date | None] = mapped_column(Date, nullable=True)
    eseguita_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
