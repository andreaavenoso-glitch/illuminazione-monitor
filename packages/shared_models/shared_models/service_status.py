from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from shared_models.base import Base


class ServiceStatus(Base):
    """Last known state of an external service the app depends on (key "claude"): written by the
    worker when a call is refused (no credit, limit) or succeeds, and by the periodic probe. The
    page shows a warning only while ``ok`` is False, so it disappears by itself on recovery."""

    __tablename__ = "service_status"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
