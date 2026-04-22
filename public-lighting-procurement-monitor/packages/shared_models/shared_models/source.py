import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared_models.base import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    platform_type: Mapped[str | None] = mapped_column(String, nullable=True)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    sector_scope: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[str] = mapped_column(String, nullable=False, default="B")
    frequency: Mapped[str] = mapped_column(String, nullable=False, default="daily")
    reliability_score: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=0, nullable=False)
    productivity_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    publication_model: Mapped[str | None] = mapped_column(String, nullable=True)
    source_priority_rank: Mapped[int] = mapped_column(default=999, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
