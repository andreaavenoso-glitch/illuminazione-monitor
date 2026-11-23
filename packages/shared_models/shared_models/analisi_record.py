import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared_models.base import Base


class AnalisiRecord(Base):
    """Preliminary analysis of the documentation of one notice: the documents read (page + attachments)
    and the fields extracted from them, each with its source. ``campi`` is open on purpose: the data
    to extract for the presentation will grow without a migration."""

    __tablename__ = "analisi_record"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    procurement_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procurement_records.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    documenti: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # [{url, nome, caratteri, tipo}]
    campi: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {campo: {valore, fonte, contesto}}
    metodo: Mapped[str] = mapped_column(String, nullable=False, default="regole")
    # "base" (the page and its documents) or "approfondita" (the documents of the documents, more levels)
    profondita: Mapped[str] = mapped_column(String, nullable=False, default="base", server_default="base")
    eseguita_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
