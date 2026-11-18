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
import random
from collections import Counter
from datetime import UTC, datetime
from urllib.parse import urljoin

from app.celery_app import celery_app
from app.collectors.adaptive_fetch import FetchResult, adaptive_fetch, adaptive_fetch_result
from app.collectors.albo_pretorio_llm import (
    build_raw_record_kwargs,
    extract_albo_records,
    extract_bando_detail,
    find_bandi_link,
    merge_detail_into_record,
    select_relevant_links,
)
from app.collectors.page_gate import gate_page, pick_section_links
from app.collectors.sitemap import discover_sitemap_urls
from app.collectors.source_health import apply_scan_outcome
from app.config import WorkerSettings, get_worker_settings
from app.db import SessionLocal
from shared_models import Entity, JobRun, RawRecord, RegionSettings, WatchlistItem
from shared_models.regions import normalize_region
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


async def _fetch_page_result(url: str, *, settings: WorkerSettings, label: str) -> FetchResult:
    """Like _fetch_page but keeps why a fetch failed, for source health."""
    return await adaptive_fetch_result(
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
    stats: Counter,
) -> None:
    """Extract records from one already-fetched page and persist the new
    ones. Shared by every page a watchlist item's scan touches, whether
    that's the single url_albo page or one of several url_trasparenza pages
    followed via sitemap/link-selection below.

    A fixed pre-filter (app.collectors.page_gate) runs first: pages with no
    lighting/PPP wording never reach Claude, matching entries go as a compact
    list, and a page unchanged since its last successful analysis is skipped.
    """
    stats["pages_read"] += 1
    gated = gate_page(target_html, base_url=target_url)
    stats[f"template_{gated.template}"] += 1
    if gated.action == "skip":
        stats["pages_skipped_no_keywords"] += 1
        return
    hashes = dict(item.content_hashes or {})
    if hashes.get(target_url) == gated.digest:
        stats["pages_unchanged"] += 1
        return
    stats[f"pages_to_claude_{gated.action}"] += 1

    status = {"ok": True}
    records = await extract_albo_records(
        gated.html, url=target_url, settings=settings, label=label, status=status
    )
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

    if status["ok"]:
        # Only after a successful analysis: a failed call must be retried.
        hashes[target_url] = gated.digest
        item.content_hashes = hashes


async def _trasparenza_pages(
    cleaned: str, url: str, *, settings: WorkerSettings, label: str, stats: Counter
) -> list[str]:
    """Pages beyond the Amministrazione Trasparente landing page worth
    extracting from. Pre-gara signals are often filed under sections other
    than "Bandi di gara e contratti" (Provvedimenti, Avvisi, Novita...) or
    several clicks deep, so a single label match isn't enough. In order of
    cost: sitemap.xml (free, complete when present), the legal section names
    matched on the page's links (free), and only if neither finds anything,
    an AI pass over every link of the landing page.
    """
    sitemap_pages = await discover_sitemap_urls(url)
    if sitemap_pages:
        stats["links_from_sitemap"] += 1
        return sitemap_pages[:MAX_EXTRA_PAGES]

    bandi_url = find_bandi_link(cleaned, base_url=url)
    labelled = pick_section_links(cleaned, base_url=url, limit=MAX_EXTRA_PAGES)
    pages = [u for u in dict.fromkeys([bandi_url, *labelled]) if u and u != url]
    if pages:
        stats["links_from_labels"] += 1
        return pages[:MAX_EXTRA_PAGES]

    stats["links_from_claude"] += 1
    selected = await select_relevant_links(cleaned, base_url=url, settings=settings, label=label)
    return [u for u in dict.fromkeys(selected) if u and u != url][:MAX_EXTRA_PAGES]


async def _scan_item(session: AsyncSession, item: WatchlistItem, job: JobRun, stats: Counter) -> None:
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
    # Source health: the item is healthy if at least one of its primary URLs
    # returned content (finding nothing relevant there still counts).
    primary_ok = False
    first_error: str | None = None

    for kind, url in urls:
        label = f"{kind}:{item.id}"
        fetched = await _fetch_page_result(url, settings=settings, label=label)
        cleaned = fetched.text
        if not cleaned:
            first_error = first_error or fetched.error
            continue
        primary_ok = True
        if fetched.url and fetched.url != url:
            # A variant (www on/off, http) answered: resolve links against it
            # and remember it, so the next scan goes straight there.
            log.info("collect_watchlist.url_repaired", extra={"item": str(item.id), "old": url, "new": fetched.url})
            setattr(item, "url_albo" if kind == "albo" else "url_trasparenza", fetched.url)
            url = fetched.url

        if kind != "trasparenza":
            await _process_page(
                session, item, job,
                target_url=url, target_html=cleaned, label=label,
                settings=settings, now=now, seen=seen, stats=stats,
            )
            continue

        extra_pages = await _trasparenza_pages(cleaned, url, settings=settings, label=label, stats=stats)
        if not extra_pages:
            # Nothing more specific found: extract from the landing page
            # itself, same as before this went looking further.
            await _process_page(
                session, item, job,
                target_url=url, target_html=cleaned, label=label,
                settings=settings, now=now, seen=seen, stats=stats,
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
                settings=settings, now=now, seen=seen, stats=stats,
            )

    item.last_scan_at = now
    apply_scan_outcome(item, now=now, ok=primary_ok, error=first_error)


def select_sample(items: list, limit: int | None, rng: random.Random | None = None) -> list:
    """At most ``limit`` items for a trial run: never-scanned ones first, then
    the rest, random within each group, so repeating a trial covers new
    comuni instead of the same ones. ``None`` means no limit."""
    if limit is None or limit >= len(items):
        return items
    rng = rng or random.Random()
    fresh = [i for i in items if i.last_scan_at is None]
    seen = [i for i in items if i.last_scan_at is not None]
    rng.shuffle(fresh)
    rng.shuffle(seen)
    return (fresh + seen)[:limit]


async def _regions_to_scan(session: AsyncSession, region: str | None) -> set[str] | None:
    """Regions a scan should cover, or None for "everything" (no region
    configuration at all, i.e. before the regional setup was seeded)."""
    if region:
        r = normalize_region(region)
        return {r} if r else set()
    rows = (await session.execute(select(RegionSettings))).scalars().all()
    if not rows:
        return None
    return {r.region for r in rows if r.enabled}


async def _run_watchlist_scan(region: str | None = None, limit: int | None = None) -> dict[str, int]:
    totals = {"items_scanned": 0, "records_found": 0, "records_valid": 0, "errors": 0}
    stats: Counter = Counter()
    async with SessionLocal() as session:
        job = JobRun(job_name="collect_watchlist_albo", status="running")
        session.add(job)
        await session.flush()

        stmt = select(WatchlistItem).where(
            WatchlistItem.active.is_(True),
            or_(WatchlistItem.url_albo.is_not(None), WatchlistItem.url_trasparenza.is_not(None)),
        )
        stmt = stmt.add_columns(Entity.region).outerjoin(Entity, WatchlistItem.entity_id == Entity.id)
        rows = (await session.execute(stmt)).all()
        wanted = await _regions_to_scan(session, region)
        items = [
            item for item, item_region in rows
            if wanted is None or normalize_region(item_region) in wanted
        ]
        items = select_sample(items, limit)
        log.info("collect_watchlist.scope", extra={"region": region, "items": len(items), "limit": limit})

        for item in items:
            try:
                await _scan_item(session, item, job, stats)
                totals["items_scanned"] += 1
            except Exception as exc:  # noqa: BLE001
                totals["errors"] += 1
                job.error_message = f"{type(exc).__name__}: {exc}"
                log.exception("collect_watchlist.item_crashed", extra={"item": str(item.id), "err": str(exc)})
            # Persist as we go: a full scan of 100+ comuni takes ~20 minutes,
            # and committing only at the end meant a task killed by the
            # Celery time limit (or a worker restart) lost everything it had
            # already found. expire_on_commit=False (app.db) keeps the loaded
            # items usable across commits.
            await session.commit()

        job.ended_at = datetime.now(tz=UTC)
        job.status = "failed" if job.error_message else ("partial" if job.records_valid == 0 else "success")
        totals["records_found"] = job.records_found
        totals["records_valid"] = job.records_valid
        await session.commit()
    log.info("collect_watchlist.stats", extra={"stats": dict(stats)})
    # Pre-filter savings and platform mix, visible in the task result.
    totals.update(dict(stats))
    return totals


# A region can have hundreds of comuni (Puglia ~250 at ~11 s each), well past
# the global 25/30 minute limits, and the scan commits per item anyway.
@celery_app.task(
    name="app.tasks.collect_watchlist.collect_watchlist_albo",
    soft_time_limit=4 * 3600,
    time_limit=4 * 3600 + 300,
)
def collect_watchlist_albo(region: str | None = None, limit: int | None = None) -> dict[str, int]:
    """Scan the watchlist; ``region`` limits it to one region (any, enabled or
    not), otherwise only the enabled regions are scanned. ``limit`` caps the
    number of comuni (trial run)."""
    return asyncio.run(_run_watchlist_scan(region, limit))
