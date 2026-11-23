"""Live state of Claude (credit / limit), so the pages warn only while it holds."""
from datetime import UTC, datetime, timedelta

from app.auth import current_user
from app.core.database import get_session
from fastapi import APIRouter, Depends
from shared_models import ScanRun, ServiceStatus, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
RECHECK_AFTER = timedelta(seconds=90)


def should_probe(ok: bool | None, checked_at: datetime | None, now: datetime) -> bool:
    """Probe (a one-token call) only while Claude is believed down, at most every 90 seconds:
    when it is up, or unknown, nothing is spent."""
    return ok is False and (checked_at is None or now - checked_at >= RECHECK_AFTER)


def _probe() -> None:
    from app.services.admin_service import _celery_app

    _celery_app().send_task("app.tasks.claude_health.check_claude")


@router.get("")
async def claude_status(
    _: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> dict:
    now = datetime.now(tz=UTC)
    row = await session.get(ServiceStatus, "claude")
    if row is None:
        # Nothing recorded yet (before this feature): a last scan that was refused or fell back
        # to the rules means Claude may be down -> one probe will create the row.
        last = (
            await session.execute(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1))
        ).scalar_one_or_none()
        if last is not None and last.claude_status in ("down", "rules"):
            _probe()
        return {"ok": None, "error": None, "checked_at": None}
    if should_probe(row.ok, row.checked_at, now):
        row.checked_at = now  # throttle: the probe will set the real time
        await session.commit()
        _probe()
    return {"ok": row.ok, "error": row.error, "checked_at": row.checked_at}
