from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from app.celery_app import celery_app
from app.collectors import COLLECTOR_REGISTRY, CollectorResult
from app.collectors.base import BaseCollector
from app.db import SessionLocal
from shared_models import JobRun, Source
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


async def _run_single(session: AsyncSession, source: Source) -> CollectorResult:
    collector_cls = COLLECTOR_REGISTRY.get(source.platform_type or "")
    if collector_cls is None:
        return CollectorResult(error=f"no collector registered for platform_type={source.platform_type!r}")

    collector: BaseCollector = collector_cls(source.id, source.base_url)

    job = JobRun(
        job_name=f"collect_{collector.name}",
        source_id=source.id,
        status="running",
    )
    session.add(job)
    await session.flush()

    result = await collector.run(session)
    job.ended_at = datetime.now(tz=UTC)
    job.records_found = result.found
    job.records_valid = result.valid
    job.records_weak = result.weak
    job.duplicates_removed = result.duplicates_removed
    job.error_message = result.error
    job.status = "failed" if result.error else ("partial" if result.valid == 0 else "success")

    if not result.error:
        source.last_checked_at = job.ended_at

    return result


async def _collect_by_type(source_type: str) -> dict[str, int]:
    totals = {"sources_run": 0, "records_valid": 0, "errors": 0}
    async with SessionLocal() as session:
        stmt = (
            select(Source)
            .where(Source.active.is_(True), Source.source_type == source_type)
            .order_by(Source.source_priority_rank, Source.name)
        )
        sources = (await session.execute(stmt)).scalars().all()

        for source in sources:
            try:
                result = await _run_single(session, source)
                totals["sources_run"] += 1
                totals["records_valid"] += result.valid
                if result.error:
                    totals["errors"] += 1
                    log.warning("collector.error", extra={"source": source.name, "err": result.error})
            except Exception as exc:  # noqa: BLE001
                totals["errors"] += 1
                log.exception("collector.crashed", extra={"source": source.name, "err": str(exc)})
        await session.commit()
    return totals


async def _collect_one(source_id: UUID) -> dict[str, int]:
    async with SessionLocal() as session:
        source = await session.get(Source, source_id)
        if source is None or not source.active:
            return {"sources_run": 0, "records_valid": 0, "errors": 0, "missing": 1}
        result = await _run_single(session, source)
        await session.commit()
        return {
            "sources_run": 1,
            "records_valid": result.valid,
            "errors": 1 if result.error else 0,
        }


@celery_app.task(name="app.tasks.collect_sources.collect_official_sources")
def collect_official_sources() -> dict[str, int]:
    return asyncio.run(_collect_by_type("official"))


@celery_app.task(name="app.tasks.collect_sources.collect_eproc_portals")
def collect_eproc_portals() -> dict[str, int]:
    return asyncio.run(_collect_by_type("eproc_portal"))


@celery_app.task(name="app.tasks.collect_sources.collect_single_source")
def collect_single_source(source_id: str) -> dict[str, int]:
    return asyncio.run(_collect_one(UUID(source_id)))
