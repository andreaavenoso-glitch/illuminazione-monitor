"""Scan Albo Pretorio / Amministrazione Trasparente pages for entities on the
watchlist.

``WatchlistItem`` carries per-entity monitoring URLs (url_gare, url_esiti,
url_albo, url_trasparenza, url_determine) that were never actually read by
any collector -- this task closes that gap for ``url_albo`` and
``url_trasparenza``, the two sources where manifestazioni di interesse /
avvisi di preinformazione / indagini di mercato are published, well before a
formal bando appears on the usual e-procurement portals. ``url_trasparenza``
(the "Amministrazione Trasparente" section every Italian PA is legally
required to publish per D.Lgs. 33/2013, including a "Bandi di gara e
contratti" sub-section) is often a more reliable source than a guessed Albo
Pretorio URL, since it can be sourced directly from IPA (Indice delle
Pubbliche Amministrazioni) rather than discovered by hand.

Each active watchlist item gets the same 3-tier adaptive fetch as
SmartLLMCollector for every non-null URL it has (one page fetch per URL,
independently). For url_trasparenza, the landing page is usually just a
navigation menu, so this goes looking for where the actual content is
instead of stopping at the mandated "Bandi di gara e contratti" label:
sitemap.xml when the site has one (§ collectors/sitemap.py), otherwise the
label match plus an AI pass over every link on the page (§
select_relevant_links), up to MAX_EXTRA_PAGES pages. A dedicated Claude
prompt (tuned for heterogeneous municipal notice-board content, not tender
listings) then extracts only the pre-tender lighting-perimeter signals from
each page visited.

A third hop follows each already-relevant record's own link (when it has
one) to its detail page and enriches ente/scadenza/body from there --
listing pages rarely carry more than a title and a one-line snippet. This
only fires for the handful of candidates a listing page actually surfaces
(usually zero or one), not for every item on the page.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from urllib.parse import urljoin

from app.celery_app import celery_app
from app.collectors.adaptive_fetch import adaptive_fetch
from app.collectors.albo_pretorio_llm import (
    build_raw_record_kwargs,
    extract_albo_records,
    extract_bando_detail,
    find_bandi_link,
    merge_detail_into_record,
    select_relevant_links,
)
from app.collectors.sitemap import discover_sitemap_urls
from app.config import WorkerSettings, get_worker_settings
from app.db import SessionLocal
from shared_models import JobRun, RawRecord, WatchlistItem
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# Bounds how many extra pages a single url_trasparenza scan can follow, to
# keep the (real, Claude-metered) cost of going deeper predictable: each
# extra page is one more page fetch and one more extraction call, on top of
# whatever detail-page hops the records it finds trigger.
MAX_EXTRA_PAGES = 8


async def _fetch_page(url: str, *, settings: WorkerSettings, label: str) -> str:
    return await adaptive_fetch(
        url,
        timeout=60.0,
        max_html_chars=settings.smart_collector_max_html_chars,
        playwright_min_chars=settings.smart_collector_playwright_min_chars,
        playwright_wait_ms=settings.smart_collector_playwright_wait_ms,
        label=label,
    )


async def _process_page(
    session: AsyncSession,
    item: WatchlistItem,
    job: JobRun,
    *,
    target_url: str,
    target_html: str,
    label: str,
    settings: WorkerSettings,
    now: datetime,
    seen: set[str],
) -> None:
    """Extract records from one already-fetched page and persist the new
    ones. Shared by every page a watchlist item's scan touches, whether
    that's the single url_albo page or one of several url_trasparenza pages
    followed via sitemap/link-selection below.
    """
    records = await extract_albo_records(target_html, url=target_url, settings=settings, label=label)
    job.records_found += len(records)

    for record in records:
        # The extraction prompt asks for absolute URLs only, but Claude
        # doesn't always comply -- resolve defensively against the page
        # it was found on rather than handing a relative path straight
        # to httpx/Playwright (which reject it outright) or storing it
        # as-is in raw_url, where it would be unusable to a reader.
        detail_url = record.get("url")
        if detail_url:
            detail_url = urljoin(target_url, detail_url)
            record = {**record, "url": detail_url}
        if detail_url and detail_url != target_url:
            detail_html = await _fetch_page(detail_url, settings=settings, label=f"{label}:detail")
            if detail_html:
                details = await extract_bando_detail(
                    detail_html, url=detail_url, settings=settings, label=f"{label}:detail"
                )
                if details:
                    record = merge_detail_into_record(record, details)

        kwargs = build_raw_record_kwargs(
            url_albo=target_url,
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


async def _trasparenza_pages(cleaned: str, url: str, *, settings: WorkerSettings, label: str) -> list[str]:
    """Pages beyond the Amministrazione Trasparente landing page worth
    extracting from. Pre-gara signals are often filed under sections other
    than "Bandi di gara e contratti" (Provvedimenti, Avvisi, Novità...) or
    several clicks deep, so a single label match isn't enough. Sitemap.xml,
    when the site has one, is the cheapest and most complete way to find
    them; otherwise fall back to the deterministic label match plus an AI
    pass over every link on the landing page.
    """
    sitemap_pages = await discover_sitemap_urls(url)
    if sitemap_pages:
        return sitemap_pages[:MAX_EXTRA_PAGES]

    bandi_url = find_bandi_link(cleaned, base_url=url)
    selected = await select_relevant_links(cleaned, base_url=url, settings=settings, label=label)
    pages = [u for u in dict.fromkeys([bandi_url, *selected]) if u and u != url]
    return pages[:MAX_EXTRA_PAGES]


async def _scan_item(session: AsyncSession, item: WatchlistItem, job: JobRun) -> None:
    settings = get_worker_settings()
    if not settings.anthropic_api_key:
        log.warning("collect_watchlist.no_api_key")
        return

    urls = [
        (kind, url)
        for kind, url in (("albo", item.url_albo), ("trasparenza", item.url_trasparenza))
        if url
    ]
    now = datetime.now(tz=UTC)
    seen: set[str] = set()

    for kind, url in urls:
        label = f"{kind}:{item.id}"
        cleaned = await _fetch_page(url, settings=settings, label=label)
        if not cleaned:
            continue

        if kind != "trasparenza":
            await _process_page(
                session, item, job,
                target_url=url, target_html=cleaned, label=label,
                settings=settings, now=now, seen=seen,
            )
            continue

        extra_pages = await _trasparenza_pages(cleaned, url, settings=settings, label=label)
        if not extra_pages:
            # Nothing more specific found: extract from the landing page
            # itself, same as before this went looking further.
            await _process_page(
                session, item, job,
                target_url=url, target_html=cleaned, label=label,
                settings=settings, now=now, seen=seen,
            )
            continue

        log.info(
            "collect_watchlist.extra_pages",
            extra={"item": str(item.id), "count": len(extra_pages)},
        )
        for page_url in extra_pages:
            page_label = f"{label}:{page_url}"
            page_html = await _fetch_page(page_url, settings=settings, label=page_label)
            if not page_html:
                continue
            await _process_page(
                session, item, job,
                target_url=page_url, target_html=page_html, label=page_label,
                settings=settings, now=now, seen=seen,
            )

    item.last_scan_at = now


async def _run_watchlist_scan() -> dict[str, int]:
    totals = {"items_scanned": 0, "records_found": 0, "records_valid": 0, "errors": 0}
    async with SessionLocal() as session:
        job = JobRun(job_name="collect_watchlist_albo", status="running")
        session.add(job)
        await session.flush()

        stmt = select(WatchlistItem).where(
            WatchlistItem.active.is_(True),
            or_(WatchlistItem.url_albo.is_not(None), WatchlistItem.url_trasparenza.is_not(None)),
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
