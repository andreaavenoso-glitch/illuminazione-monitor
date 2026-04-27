"""Historical backfill: re-run all active collectors with an extended
``since`` window (7 / 14 / 30 days). Useful after onboarding new sources
or to recover missed runs after a downtime.

Triggered via ``POST /admin/run-backfill?days=14``. Writes a JobRun row
per source and a summary JobRun ``backfill_orchestrator``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.celery_app import celery_app
from app.collectors import COLLECTOR_REGISTRY
from app.db import SessionLocal
from shared_models import JobRun, Source
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

ALLOWED_WINDOWS = {7, 14, 30}


async def _run_source(session: AsyncSession, source: Source, *, since: datetime) -> bool:
    collector_cls = COLLECTOR_REGISTRY.get(source.platform_type or "")
    if collector_cls is None:
        return False

    collector = collector_cls(source.id, source.base_url)
    job = JobRun(
        job_name=f"backfill_{collector.name}",
        source_id=source.id,
        status="running",
    )
    session.add(job)
    await session.flush()

    result = await collector.run(session, since=since)
    job.ended_at = datetime.now(tz=UTC)
    job.records_found = result.found
    job.records_valid = result.valid
    job.duplicates_removed = result.duplicates_removed
    job.error_message = result.error
    job.status = "failed" if result.error else "success"
    if not result.error:
        source.last_checked_at = job.ended_at
    return not result.error


async def _run(days: int) -> dict[str, int]:
    if days not in ALLOWED_WINDOWS:
        raise ValueError(f"days must be one of {sorted(ALLOWED_WINDOWS)}, got {days}")

    since = datetime.now(tz=UTC) - timedelta(days=days)
    async with SessionLocal() as session:
        orchestrator = JobRun(
            job_name=f"backfill_orchestrator_{days}d",
            status="running",
        )
        session.add(orchestrator)
        await session.flush()

        stmt = select(Source).where(Source.active.is_(True))
        sources = list((await session.execute(stmt)).scalars().all())

        ran = 0
        failed = 0
        for source in sources:
            try:
                ok = await _run_source(session, source, since=since)
                ran += 1
                if not ok:
                    failed += 1
            except Exception as exc:  # noqa: BLE001
                log.exception(
                    "backfill.crashed",
                    extra={"source": source.name, "err": str(exc)},
                )
                failed += 1

        orchestrator.records_found = ran
        orchestrator.records_valid = ran - failed
        orchestrator.status = "partial" if failed else "success"
        orchestrator.ended_at = datetime.now(tz=UTC)
        await session.commit()

        return {
            "window_days": days,
            "sources_total": len(sources),
            "sources_ran": ran,
            "sources_failed": failed,
        }


@celery_app.task(name="app.tasks.backfill.run_backfill")
def run_backfill(days: int = 7) -> dict[str, int]:
    return asyncio.run(_run(days))
