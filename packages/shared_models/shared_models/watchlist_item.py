import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared_models.base import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    url_gare: Mapped[str | None] = mapped_column(String, nullable=True)
    url_esiti: Mapped[str | None] = mapped_column(String, nullable=True)
    url_albo: Mapped[str | None] = mapped_column(String, nullable=True)
    url_trasparenza: Mapped[str | None] = mapped_column(String, nullable=True)
    url_determine: Mapped[str | None] = mapped_column(String, nullable=True)
    frequency: Mapped[str] = mapped_column(String, nullable=False, default="daily")
    priority: Mapped[str] = mapped_column(String, nullable=False, default="B")
    reliability_score: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=0, nullable=False)
    productivity_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    publication_model: Mapped[str | None] = mapped_column(String, nullable=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
