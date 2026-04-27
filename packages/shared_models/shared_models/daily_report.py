import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared_models.base import Base


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    total_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_updates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_pregara: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_new_sources: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
