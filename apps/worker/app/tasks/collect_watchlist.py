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
import contextlib
import logging
import random
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

from app import claude_state
from app.celery_app import celery_app
from app.collectors.adaptive_fetch import FetchResult, adaptive_fetch, adaptive_fetch_result
from app.collectors.albo_pretorio_llm import (
    ClaudeUnavailable,
    build_raw_record_kwargs,
    extract_albo_records,
    extract_bando_detail,
    find_bandi_link,
    merge_detail_into_record,
    select_relevant_links,
)
from app.collectors.crawler import crawl
from app.collectors.page_gate import (
    GateResult,
    discovered_platforms,
    gate_page,
    pick_section_links,
    rank_links,
    safe_join,
    same_site,
)
from app.collectors.rules_extract import extract_records_by_rules
from app.collectors.sitemap import discover_sitemap_urls
from app.collectors.source_health import apply_scan_outcome
from app.config import WorkerSettings, get_worker_settings
from app.db import SessionLocal
from app.stop import run_stopped
from app.usage import current_run_id, current_scan_item_id
from shared_models import (
    Entity,
    JobRun,
    RawRecord,
    RegionSettings,
    ScanItem,
    ScanRun,
    Source,
    WatchlistItem,
)
from shared_models.categories import is_noise
from shared_models.regions import normalize_region
from shared_models.relevance import is_expired_record, mentions_date, only_old_dates, today_utc
from shared_models.services import configure as configure_services
from shared_models.services import parse_enabled
from sqlalchemy import or_, select, update
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


async def _fetch_page_result(
    url: str,
    *,
    settings: WorkerSettings,
    label: str,
    timeout: float = 60.0,
    try_variants: bool = True,
) -> FetchResult:
    """Like _fetch_page but keeps why a fetch failed, for source health. Pages
    are kept far longer than what Claude may receive: the gate reads them whole
    (entries often sit past the first 80 000 characters) and cuts what it sends."""
    return await adaptive_fetch_result(
        url,
        timeout=timeout,
        max_html_chars=settings.crawl_max_html_chars,
        playwright_min_chars=settings.smart_collector_playwright_min_chars,
        playwright_wait_ms=settings.smart_collector_playwright_wait_ms,
        label=label,
        try_variants=try_variants,
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
    digests: set[str] | None = None,
) -> GateResult:
    """Extract records from one already-fetched page and persist the new
    ones. Shared by every page a watchlist item's scan touches, whether
    that's the single url_albo page or one of several url_trasparenza pages
    followed via sitemap/link-selection below.

    A fixed pre-filter (app.collectors.page_gate) runs first: pages with no
    lighting/PPP wording never reach Claude, matching entries go as a compact
    list, and a page unchanged since its last successful analysis is skipped.
    """
    stats["pages_read"] += 1
    gated = gate_page(
        target_html, base_url=target_url, full_limit=settings.smart_collector_max_html_chars
    )
    stats[f"template_{gated.template}"] += 1
    if gated.action == "skip":
        stats["pages_skipped_no_keywords"] += 1
        return gated
    if digests is not None:
        # The same content under another address (/utilita/... and
        # /amministrazione/... on one site) is analysed once per comune.
        if gated.digest in digests:
            stats["pages_duplicate_content"] += 1
            return gated
        digests.add(gated.digest)
    hashes = dict(item.content_hashes or {})
    if hashes.get(target_url) == gated.digest:
        stats["pages_unchanged"] += 1
        return gated
    stats[f"pages_to_claude_{gated.action}"] += 1

    status = {"ok": True}
    by_rules = not claude_state.use_claude(settings)
    records: list[dict] = []
    if not by_rules:
        records = await extract_albo_records(
            gated.html, url=target_url, settings=settings, label=label, status=status
        )
        if not status["ok"] and status.get("fatal") and claude_state.can_fall_back(settings):
            # No credit / limit reached: go on with the free rules, try Claude again later.
            claude_state.mark_down(status.get("error", "errore sconosciuto"))
            log.warning("collect_watchlist.claude_down_using_rules %s", status.get("error"))
            stats["claude_down_fallback"] += 1
            status = {"ok": True}
            by_rules = True
    if by_rules:
        stats["pages_by_rules"] += 1
        entity = await session.get(Entity, item.entity_id) if item.entity_id else None
        records = extract_records_by_rules(
            gated.candidates, ente=entity.name if entity else None, today=today_utc()
        )
        if not gated.candidates:
            stats["pages_unparsed_by_rules"] += 1  # no list structure: needs Claude
    job.records_found += len(records)
    stats["records_found"] += len(records)

    # Claude is told never to use the current date, but it sometimes does when a
    # page shows none: 39 of 128 records of a real run were "published today".
    # A date equal to today is kept only if today's date is really in the text it read.
    today = today_utc()
    for rec in records:
        if rec.get("date") == today.isoformat() and not mentions_date(gated.html, today):
            rec["date"] = None

    for record in records:
        # The extraction prompt asks for absolute URLs only, but Claude
        # doesn't always comply -- resolve defensively against the page
        # it was found on rather than handing a relative path straight
        # to httpx/Playwright (which reject it outright) or storing it
        # as-is in raw_url, where it would be unusable to a reader.
        detail_url = record.get("url")
        if detail_url:
            detail_url = safe_join(target_url, detail_url)
            record = {**record, "url": detail_url}
        # Not an opportunity (a payment, an award, a generic page, a non-procuring body):
        # dropped here, before any detail page is fetched.
        if is_noise(f"{record.get('title') or ''} {record.get('body') or ''}", record.get("ente")):
            stats["records_noise_dropped"] += 1
            continue
        # A deadline already known and past: over, skip it without paying for the
        # detail page. (A deadline learnt only from the detail page is checked below.)
        if is_expired_record(record):
            stats["records_expired_dropped"] += 1
            continue
        if detail_url and detail_url != target_url:
            detail_html = await _fetch_page(detail_url, settings=settings, label=f"{label}:detail")
            if detail_html:
                # Without Claude the deadline comes from the verification step (free).
                details = (
                    None
                    if by_rules or not claude_state.use_claude(settings)
                    else await extract_bando_detail(
                        detail_html, url=detail_url, settings=settings, label=f"{label}:detail"
                    )
                )
                if details:
                    record = merge_detail_into_record(record, details)
                # A detail page whose every date is old (attachments from 2023,
                # an award notice) is a closed procedure, whatever the list said.
                if not record.get("scadenza") and only_old_dates(detail_html, today):
                    stats["records_expired_dropped"] += 1
                    continue

        if is_expired_record(record):
            stats["records_expired_dropped"] += 1
            continue

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

    if not status["ok"]:
        stats["claude_errors"] += 1
        if status.get("fatal"):
            raise ClaudeUnavailable(status.get("error", "errore sconosciuto"))
    if status["ok"] and (not by_rules or claude_state.mode(settings) == "rules"):
        # Only after a successful analysis: a failed call must be retried, and a page read
        # by the free rules in "auto" is read by Claude when it is available again.
        hashes[target_url] = gated.digest
        item.content_hashes = hashes
    return gated


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

    if rank_links(cleaned, base_url=url, limit=1):
        # No section named as such, but the crawl can score the page's links.
        stats["links_from_ranking"] += 1
        return []
    if not claude_state.use_claude(settings):
        stats["links_by_rules_none"] += 1
        return []
    stats["links_from_claude"] += 1
    selected = await select_relevant_links(cleaned, base_url=url, settings=settings, label=label)
    return [u for u in dict.fromkeys(selected) if u and u != url][:MAX_EXTRA_PAGES]


MAX_COMUNI_LISTED = 50


async def _save_discovered_sites(
    session: AsyncSession,
    item: WatchlistItem,
    urls: list[str],
    *,
    start_url: str,
    stats: Counter,
    lock: asyncio.Lock | None = None,
) -> None:
    """Procurement platforms the crawl was led to (provincial / regional /
    vendor portals) are saved as regional sites of the comune's region, off
    until someone approves them: each active site is read on every run, so
    that is a decision, not a side effect."""
    found = discovered_platforms(urls, start_url)
    if not found or not item.entity_id:
        return
    entity = await session.get(Entity, item.entity_id)
    region = normalize_region(entity.region) if entity else None
    if not region or entity is None:
        return
    # Several comuni are scanned at once and may find the same portal: the
    # lookup, the insert and the commit happen under one lock, or two sessions
    # would both insert it (names are unique).
    async with lock or contextlib.nullcontext():
        await _upsert_discovered(session, entity, region, found, stats)
        await session.commit()


async def _upsert_discovered(session: AsyncSession, entity: Entity, region: str, found: dict[str, str], stats: Counter) -> None:
    for host, first_url in found.items():
        name = f"{region} - {host}"
        src = (await session.execute(select(Source).where(Source.name == name))).scalar_one_or_none()
        if src is None:
            src = Source(
                name=name, source_type="regional_site", platform_type="generic_html",
                base_url=first_url, regione=region, ruolo="scoperto",
                sector_scope="illuminazione_pubblica", priority="B", source_priority_rank=2,
                reliability_score=Decimal("0.60"), publication_model="html_scraping",
                active=False, discovered_from={"comuni": [], "count": 0},
            )
            session.add(src)
            stats["sites_discovered_new"] += 1
        info = dict(src.discovered_from or {"comuni": [], "count": 0})
        comuni = list(info.get("comuni", []))
        if entity.name not in comuni and len(comuni) < MAX_COMUNI_LISTED:
            comuni.append(entity.name)
        info.update(comuni=comuni, count=max(info.get("count", 0), len(comuni)))
        src.discovered_from = info
        log.info("collect_watchlist.site_discovered region=%s host=%s comune=%s", region, host, entity.name)


async def _scan_item(
    session: AsyncSession,
    item: WatchlistItem,
    job: JobRun,
    stats: Counter,
    site_lock: asyncio.Lock | None = None,
) -> None:
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
    digests: set[str] = set()
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
            log.info("collect_watchlist.url_repaired item=%s old=%s new=%s", item.id, url, fetched.url)
            setattr(item, "url_albo" if kind == "albo" else "url_trasparenza", fetched.url)
            url = fetched.url

        seeds: list[str] = []
        if kind == "trasparenza":
            seeds = await _trasparenza_pages(cleaned, url, settings=settings, label=label, stats=stats)

        async def on_page(page_url: str, page_html: str, depth: int, _label=label) -> GateResult:
            return await _process_page(
                session, item, job,
                target_url=page_url, target_html=page_html,
                label=_label if depth == 0 else f"{_label}:{page_url}",
                settings=settings, now=now, seen=seen, stats=stats, digests=digests,
            )

        async def fetch(page_url: str, _label=label, _start=url) -> FetchResult:
            # Inner pages of a site that already answered: no www/http variants.
            # Other hosts (provincial portals, vendors) get a shorter timeout.
            own = same_site(page_url, _start)
            return await _fetch_page_result(
                page_url, settings=settings, label=f"{_label}:{page_url}",
                timeout=60.0 if own else settings.crawl_external_timeout_s, try_variants=False,
            )

        result = await crawl(
            start_url=url, start_html=cleaned, seeds=seeds, fetch=fetch, on_page=on_page,
            max_pages=settings.crawl_max_pages, max_depth=settings.crawl_max_depth,
            time_budget_s=settings.crawl_time_budget_s, delay_s=settings.crawl_delay_s,
        )
        await _save_discovered_sites(
            session, item, [v.url for v in result.visits], start_url=url, stats=stats, lock=site_lock
        )
        stats[f"crawl_stopped_by_{result.stopped_by}"] += 1
        stats["pages_followed_deeper"] += sum(1 for v in result.visits if v.depth >= 2)
        stats["max_depth_reached"] = max(stats["max_depth_reached"], max(v.depth for v in result.visits))
        log.info(
            "collect_watchlist.crawl item=%s pages=%d deepest=%d stopped_by=%s",
            item.id, len(result.visits), max(v.depth for v in result.visits), result.stopped_by,
        )

    item.last_scan_at = now
    apply_scan_outcome(item, now=now, ok=primary_ok, error=first_error)


async def run_limited(items: list, worker, limit: int) -> None:
    """Run ``worker(item)`` for every item, at most ``limit`` at a time. A
    worker that raises does not stop the others (it is the worker's job to
    record its own failure)."""
    sem = asyncio.Semaphore(max(1, limit))

    async def guarded(item) -> None:
        async with sem:
            try:
                await worker(item)
            except Exception:  # noqa: BLE001
                log.exception("collect_watchlist.worker_failed")

    await asyncio.gather(*(guarded(i) for i in items))


def filter_stale(items: list, hours: float | None, now: datetime | None = None) -> list:
    """Comuni not read in the last ``hours`` hours (never read counts as stale).
    ``None`` keeps everything. This is what "resume" uses after an interrupted run:
    the comuni it had finished carry a recent ``last_scan_at`` and are skipped."""
    if hours is None:
        return items
    from datetime import timedelta

    limit = (now or datetime.now(tz=UTC)) - timedelta(hours=hours)
    return [i for i in items if i.last_scan_at is None or i.last_scan_at < limit]


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


# Stats keys that are a maximum, not a count, when per-comune counters are merged.
_MAX_STAT_KEYS = frozenset({"max_depth_reached"})


class Checkpointer:
    """Runs ``action`` every ``every`` finished comuni, never two at once and
    never failing the scan. Used to normalize the records found so far while a
    long scan is still going: before this, they appeared only at the very end, so
    a run cut short (Codespace stopped, worker restart) showed none of them."""

    def __init__(self, every: int, action) -> None:
        self.every = max(1, every)
        self.action = action
        self.finished = 0
        self.lock = asyncio.Lock()

    async def tick(self) -> None:
        self.finished += 1
        if self.finished % self.every or self.lock.locked():
            return
        async with self.lock:
            try:
                await self.action()
            except Exception:  # noqa: BLE001
                log.exception("collect_watchlist.checkpoint_failed")


# Records of the comuni read so far are normalized every this many comuni.
CHECKPOINT_EVERY = 20


def merge_stats(total: Counter, local: Counter) -> None:
    """Add one comune's counters to the run's: counts are summed, maxima kept."""
    for key, value in local.items():
        if key in _MAX_STAT_KEYS:
            total[key] = max(total[key], value)
        else:
            total[key] += value


def item_progress(local: Counter) -> dict:
    """What the progress view shows for one finished comune (pure)."""
    stopped = next(
        (k.removeprefix("crawl_stopped_by_") for k, v in local.items() if k.startswith("crawl_stopped_by_") and v),
        None,
    )
    return {
        "pages_read": local["pages_read"],
        "pages_skipped": local["pages_skipped_no_keywords"] + local["pages_unchanged"] + local["pages_duplicate_content"],
        "claude_calls": local["pages_to_claude_compact"] + local["pages_to_claude_full"],
        "claude_errors": local["claude_errors"],
        "records_found": local["records_found"],
        "deepest": local["max_depth_reached"],
        "stopped_by": stopped,
    }


async def _update_scan_item(run_id, scan_item_id, **values) -> None:
    """Short session of its own: progress must be visible at once and must not
    depend on the state of the comune's working session."""
    try:
        async with SessionLocal() as s:
            await s.execute(update(ScanItem).where(ScanItem.id == scan_item_id).values(**values))
            await s.execute(update(ScanRun).where(ScanRun.id == run_id).values(heartbeat_at=datetime.now(tz=UTC)))
            await s.commit()
    except Exception:  # noqa: BLE001  the progress view must never break the scan
        log.exception("collect_watchlist.progress_update_failed")


async def _set_run_claude(run_id, status: str, error: str | None, *, only_if_unused: bool = False) -> None:
    try:
        async with SessionLocal() as s:
            stmt = update(ScanRun).where(ScanRun.id == run_id)
            if only_if_unused:
                stmt = stmt.where(ScanRun.claude_status == "unused")
            await s.execute(stmt.values(claude_status=status, claude_error=error))
            await s.commit()
    except Exception:  # noqa: BLE001
        log.exception("collect_watchlist.progress_update_failed")


def _run_config(settings, limit, skip_hours, item_ids) -> dict:
    """What this run used, kept with it so runs can be compared later (see the Storico tab)."""
    tipo = "mirata" if item_ids else "prova" if limit else "ripresa" if skip_hours else "completa"
    return {
        "tipo": tipo,
        "crawl_max_pages": settings.crawl_max_pages,
        "crawl_max_depth": settings.crawl_max_depth,
        "crawl_time_budget_s": settings.crawl_time_budget_s,
        "scan_item_timeout_s": settings.scan_item_timeout_s,
        "extraction_mode": settings.extraction_mode,
        "servizi": settings.enabled_services or "tutti",
    }


async def _run_watchlist_scan(
    region: str | None = None,
    limit: int | None = None,
    skip_scanned_hours: float | None = None,
    item_ids: list[str] | None = None,
) -> dict[str, int]:
    configure_services(parse_enabled(get_worker_settings().enabled_services))
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
        stmt = stmt.add_columns(Entity.region, Entity.name).outerjoin(Entity, WatchlistItem.entity_id == Entity.id)
        rows = (await session.execute(stmt)).all()
        wanted = await _regions_to_scan(session, region)
        names = {item.id: (name or "comune") for item, _, name in rows}
        items = [
            item for item, item_region, _ in rows
            if wanted is None or normalize_region(item_region) in wanted
        ]
        if item_ids:  # targeted collection: exactly the comuni the user selected
            wanted_ids = {str(i) for i in item_ids}
            items = [i for i in items if str(i.id) in wanted_ids]
        items = filter_stale(items, skip_scanned_hours)
        items = select_sample(items, limit)
        log.info("collect_watchlist.scope region=%s items=%d limit=%s", region, len(items), limit)

        # The progress view: one run, and one row per comune, visible as
        # "queued" from the first second.
        run = ScanRun(
            region=normalize_region(region) if region else None,
            sample_limit=limit, total=len(items), status="running", heartbeat_at=datetime.now(tz=UTC),
            config=_run_config(get_worker_settings(), limit, skip_scanned_hours, item_ids),
        )
        session.add(run)
        await session.flush()
        scan_item_ids = {}
        for item in items:
            si = ScanItem(run_id=run.id, item_id=item.id, ente=names.get(item.id, "comune"))
            session.add(si)
            await session.flush()
            scan_item_ids[item.id] = si.id
        await session.commit()
        current_run_id.set(run.id)  # inherited by the per-comune tasks started below

        settings = get_worker_settings()
        site_lock = asyncio.Lock()
        checkpoint = Checkpointer(CHECKPOINT_EVERY, _normalize_now)
        claude_down = asyncio.Event()
        claude_state.reset()  # a topped-up account is tried again from the start of every run
        rules_noted = False
        if not claude_state.use_claude(settings):
            rules_noted = True
            await _set_run_claude(
                run.id, "rules",
                "Modalità regole (EXTRACTION_MODE=rules o chiave Claude assente): nessuna chiamata a Claude.",
            )
        item_ids = [item.id for item in items]

        async def scan_one(item_id) -> None:
            # Each comune has its own session (a session is not safe to share
            # between concurrent tasks) and commits as it goes: a task killed
            # by the Celery time limit or a restart loses at most what is in
            # flight. The shared JobRun is only touched by plain attribute
            # updates, which is safe on one event loop.
            sid = scan_item_ids[item_id]
            current_scan_item_id.set(sid)
            if await run_stopped(run.id):
                stats["items_skipped_stopped"] += 1
                await _update_scan_item(run.id, sid, status="skipped", ended_at=datetime.now(tz=UTC), error="raccolta fermata")
                return
            if claude_down.is_set():
                stats["items_skipped_claude_down"] += 1
                await _update_scan_item(run.id, sid, status="skipped", error="Claude non disponibile")
                return
            local: Counter = Counter()
            await _update_scan_item(run.id, sid, status="running", started_at=datetime.now(tz=UTC))
            outcome, error = "done", None
            async with SessionLocal() as item_session:
                item = await item_session.get(WatchlistItem, item_id)
                if item is None:
                    await _update_scan_item(run.id, sid, status="error", ended_at=datetime.now(tz=UTC), error="comune non trovato")
                    return
                try:
                    await asyncio.wait_for(
                        _scan_item(item_session, item, job, local, site_lock),
                        timeout=settings.scan_item_timeout_s,
                    )
                    totals["items_scanned"] += 1
                except TimeoutError:
                    outcome = "error"
                    error = f"tempo massimo superato ({int(settings.scan_item_timeout_s)} s): comune saltato"
                    totals["errors"] += 1
                    log.warning("collect_watchlist.item_timeout item=%s", item_id)
                    await item_session.rollback()
                except ClaudeUnavailable as exc:
                    # Every other comune would fail the same way: stop the run
                    # and say so, instead of crawling for an hour to report "0".
                    outcome, error = "error", f"Claude non disponibile: {exc}"
                    if not claude_down.is_set():
                        claude_down.set()
                        job.error_message = error
                        totals["claude_unavailable"] = 1
                        log.error("collect_watchlist.claude_unavailable %s", exc)
                        await _set_run_claude(run.id, "down", str(exc)[:500])
                    totals["errors"] += 1
                    await item_session.rollback()
                except Exception as exc:  # noqa: BLE001
                    outcome, error = "error", f"{type(exc).__name__}: {exc}"[:500]
                    totals["errors"] += 1
                    job.error_message = f"{type(exc).__name__}: {exc}"
                    log.exception("collect_watchlist.item_crashed", extra={"item": str(item_id), "err": str(exc)})
                    await item_session.rollback()
                try:
                    await item_session.commit()
                except Exception:  # noqa: BLE001
                    log.exception("collect_watchlist.commit_failed item=%s", item_id)
                    await item_session.rollback()
            merge_stats(stats, local)
            progress = item_progress(local)
            await _update_scan_item(
                run.id, sid, status=outcome, ended_at=datetime.now(tz=UTC), error=error, **progress
            )
            nonlocal rules_noted
            if not rules_noted and claude_state.is_down():
                rules_noted = True
                await _set_run_claude(
                    run.id, "rules",
                    f"Claude non disponibile, la raccolta prosegue con le regole: {claude_state.last_error() or ''}"[:500],
                )
            if progress["claude_calls"] and not progress["claude_errors"] and not claude_down.is_set():
                await _set_run_claude(run.id, "ok", None, only_if_unused=True)
            await checkpoint.tick()

        await run_limited(item_ids, scan_one, settings.scan_concurrency)
        await session.commit()

        job.ended_at = datetime.now(tz=UTC)
        job.status = "failed" if job.error_message else ("partial" if job.records_valid == 0 else "success")
        totals["records_found"] = job.records_found
        totals["records_valid"] = job.records_valid
        await session.commit()
        await _finish_run(run.id, job.error_message)
    log.info("collect_watchlist.stats %s", dict(sorted(stats.items())))
    # Pre-filter savings and platform mix, visible in the task result.
    totals.update(dict(stats))
    return totals


async def _normalize_now() -> None:
    from app.tasks.normalize_records import _run_normalize

    result = await _run_normalize()
    log.info("collect_watchlist.checkpoint_normalized %s", result)


async def _finish_run(run_id, error: str | None) -> None:
    try:
        async with SessionLocal() as s:
            stopped = bool(await s.scalar(select(ScanRun.stop_requested).where(ScanRun.id == run_id)))
            await s.execute(
                update(ScanRun).where(ScanRun.id == run_id).values(
                    ended_at=datetime.now(tz=UTC), heartbeat_at=datetime.now(tz=UTC),
                    status="stopped" if stopped else ("failed" if error else "done"), error=error,
                )
            )
            await s.commit()
    except Exception:  # noqa: BLE001
        log.exception("collect_watchlist.progress_update_failed")


# A region can have hundreds of comuni (Puglia ~250 at ~11 s each), well past
# the global 25/30 minute limits, and the scan commits per item anyway.
@celery_app.task(
    name="app.tasks.collect_watchlist.collect_watchlist_albo",
    soft_time_limit=4 * 3600,
    time_limit=4 * 3600 + 300,
)
def collect_watchlist_albo(
    region: str | None = None,
    limit: int | None = None,
    skip_scanned_hours: float | None = None,
    item_ids: list[str] | None = None,
) -> dict[str, int]:
    """Scan the watchlist; ``region`` limits it to one region (any, enabled or
    not), otherwise only the enabled regions are scanned. ``limit`` caps the
    number of comuni (trial run); ``skip_scanned_hours`` skips the ones read more
    recently than that (resume an interrupted run)."""
    return asyncio.run(_run_watchlist_scan(region, limit, skip_scanned_hours, item_ids))
