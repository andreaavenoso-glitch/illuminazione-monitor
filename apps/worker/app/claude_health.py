"""Persist whether Claude is usable (see shared_models.ServiceStatus), without ever failing a job."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.db import SessionLocal
from shared_models import ServiceStatus

log = logging.getLogger(__name__)
_known: bool | None = None  # last value written by this process: success calls write only on a change


async def set_status(ok: bool, error: str | None = None) -> None:
    global _known
    try:
        async with SessionLocal() as s:
            row = await s.get(ServiceStatus, "claude")
            if row is None:
                s.add(ServiceStatus(key="claude", ok=ok, error=error, checked_at=datetime.now(tz=UTC)))
            else:
                row.ok, row.error, row.checked_at = ok, error, datetime.now(tz=UTC)
            await s.commit()
        _known = ok
    except Exception:  # noqa: BLE001
        log.exception("claude_health.write_failed")


async def note_success() -> None:
    """A call went through: Claude works. Written once per change, not on every call."""
    if _known is not True:
        await set_status(True)
