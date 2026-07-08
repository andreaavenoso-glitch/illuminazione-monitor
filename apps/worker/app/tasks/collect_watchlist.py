"""Scan Albo Pretorio pages for entities on the watchlist.

``WatchlistItem`` carries per-entity monitoring URLs (url_gare, url_esiti,
url_albo, url_trasparenza, url_determine) that were never actually read by
any collector -- this task closes that gap for ``url_albo``, the source
where manifestazioni di interesse / avvisi di preinformazione / indagini di
mercato are published, well before a formal bando appears on the usual
e-procurement portals.

Each active watchlist item with a non-null ``url_albo`` gets the same 3-tier
adaptive fetch as SmartLLMCollector, then a dedicated Claude prompt
(tuned for heterogeneous municipal notice-board content, not tender
listings) extracts only the pre-tender lighting-perimeter signals.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.celery_app import celery_app
from app.collectors.adaptive_fetch import adaptive_fetch
from app.collectors.albo_pretorio_llm import build_raw_record_kwargs, extract_albo_records
from app.config import get_worker_settings
from app.db import SessionLocal
from shared_models import JobRun, RawRecord, WatchlistItem
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


async def _scan_item(session: AsyncSession, item: WatchlistItem, job: JobRun) -> None:
    settings = get_worker_settings()
    if not settings.anthropic_api_key:
        log.warning("collect_watchlist.no_api_key")
        return

    label = f"albo:{item.id}"
    cleaned = await adaptive_fetch(
        item.url_albo,
        timeout=60.0,
        max_html_chars=settings.smart_collector_max_html_chars,
        playwright_min_chars=settings.smart_collector_playwright_min_chars,
        playwright_wait_ms=settings.smart_collector_playwright_wait_ms,
        label=label,
    )
    if not cleaned:
        return

    records = await extract_albo_records(cleaned, url=item.url_albo, settings=settings, label=label)
    job.records_found += len(records)

    seen: set[str] = set()
    now = datetime.now(tz=UTC)
    for record in records:
        kwargs = build_raw_record_kwargs(
            url_albo=item.url_albo,
            source_id=item.source_id,
            entity_id=item.entity_id,
            record=record,
            now=now,
        )
        checksum = kwargs["checksum"]
        if checksum in seen:
            job.duplicates_removed += 1
            continue
        seen.add(checksum)

        session.add(RawRecord(**kwargs))
        job.records_valid += 1

    item.last_scan_at = now


async def _run_watchlist_scan() -> dict[str, int]:
    totals = {"items_scanned": 0, "records_found": 0, "records_valid": 0, "errors": 0}
    async with SessionLocal() as session:
        job = JobRun(job_name="collect_watchlist_albo", status="running")
        session.add(job)
        await session.flush()

        stmt = select(WatchlistItem).where(
            WatchlistItem.active.is_(True), WatchlistItem.url_albo.is_not(None)
        )
        items = (await session.execute(stmt)).scalars().all()

        for item in items:
            try:
                await _scan_item(session, item, job)
                totals["items_scanned"] += 1
            except Exception as exc:  # noqa: BLE001
                totals["errors"] += 1
                job.error_message = f"{type(exc).__name__}: {exc}"
                log.exception("collect_watchlist.item_crashed", extra={"item": str(item.id), "err": str(exc)})

        job.ended_at = datetime.now(tz=UTC)
        job.status = "failed" if job.error_message else ("partial" if job.records_valid == 0 else "success")
        totals["records_found"] = job.records_found
        totals["records_valid"] = job.records_valid
        await session.commit()
    return totals


@celery_app.task(name="app.tasks.collect_watchlist.collect_watchlist_albo")
def collect_watchlist_albo() -> dict[str, int]:
    return asyncio.run(_run_watchlist_scan())
