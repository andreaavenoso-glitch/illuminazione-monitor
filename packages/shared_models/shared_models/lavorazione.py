import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared_models.base import Base

STATI = ("selezionata", "scartata")


class Lavorazione(Base):
    """What the team decided to do with one notice: pursue it (``selezionata``) or leave it (``scartata``), the
    notes, and when the e-mail and the summary sheet were produced. A notice with no row is simply not looked at yet.
    The analysis and the referenti stay in their own tables: this is only the decision and its trail."""

    __tablename__ = "lavorazioni"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    procurement_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procurement_records.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    stato: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decisa_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    email_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sintesi_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
