import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared_models.base import Base


class ScanRun(Base):
    """One run of the comuni scan (a trial, a region, or the daily one): what
    the progress view reads. Written by the worker as it goes."""

    __tablename__ = "scan_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Updated at every comune start/end: a "running" run that stopped updating
    # was killed (restart, time limit) and is shown as interrupted.
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")  # running|done|failed
    sample_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # unused (no call yet) | ok | down (the API refuses every call)
    claude_status: Mapped[str] = mapped_column(String, nullable=False, default="unused")
    claude_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set by the user ("Ferma raccolta"): the scan skips the comuni not yet started and later slow steps are skipped.
    stop_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScanItem(Base):
    """One comune inside a run."""

    __tablename__ = "scan_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scan_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watchlist_items.id", ondelete="SET NULL"), nullable=True
    )
    ente: Mapped[str] = mapped_column(String, nullable=False)
    # queued | running | done | error | skipped
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pages_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Pages sent to Claude (one call each) and how many of those calls failed.
    claude_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claude_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deepest: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stopped_by: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
