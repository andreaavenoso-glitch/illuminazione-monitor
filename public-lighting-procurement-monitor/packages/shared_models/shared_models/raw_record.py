import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared_models.base import Base


class RawRecord(Base):
    __tablename__ = "raw_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    raw_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_url: Mapped[str] = mapped_column(String, nullable=False)
    raw_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extracted_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
