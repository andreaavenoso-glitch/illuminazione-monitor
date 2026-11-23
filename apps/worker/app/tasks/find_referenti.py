"""Find the referenti (sindaco, assessore LL.PP./illuminazione, responsabile tecnico, RUP)
of the ente behind one record, from the pages of its own site. On request, one ente at
a time; the result is stored with the page it was read from."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from app import claude_state
from app.celery_app import celery_app
from app.collectors.adaptive_fetch import adaptive_fetch_result
from app.collectors.referenti import (
    extract_people,
    has_role_words,
    merge_people,
    rank_people_links,
    site_root,
    verify_person,
)
from app.collectors.rules_extract import extract_people_by_rules
from app.config import get_worker_settings
from app.db import SessionLocal
from app.tasks.verify_records import fetch_document_text, html_to_text
from shared_models import Entity, ProcurementRecord, Referente, WatchlistItem
from sqlalchemy import select

log = logging.getLogger(__name__)

MAX_PAGES = 6


async def _site_urls(session, ente: str, regione: str | None, record_link: str) -> list[str]:
    """Roots to start from: the site of the comune on the watchlist, else the record's."""
    q = select(WatchlistItem).join(Entity, WatchlistItem.entity_id == Entity.id).where(Entity.name == ente)
    if regione:
        q = q.where(Entity.region == regione)
    roots: list[str] = []
    for item in (await session.execute(q)).scalars().all():
        for u in (item.url_trasparenza, item.url_albo, item.url_gare):
            r = site_root(u) if u else None
            if r and r not in roots:
                roots.append(r)
    own = site_root(record_link)
    if own and own not in roots:
        roots.append(own)
    return roots[:2]


async def find_for_record(record_id: UUID) -> dict:
    settings = get_worker_settings()
    async with SessionLocal() as session:
        rec = await session.get(ProcurementRecord, record_id)
        if rec is None:
            return {"error": "record non trovato"}
        ente, regione, link = rec.ente, rec.regione, rec.link_bando
        roots = await _site_urls(session, ente, regione, link)

    pages: list[tuple[str, str]] = []  # (url, text)
    # 1) the record's own document: the RUP is often named there
    doc = await fetch_document_text(link, settings)
    if doc:
        pages.append((link, doc))
    # 2) the comune's site: home page, then the menu entries that lead to the people
    seen = {link}
    for root in roots:
        home = await adaptive_fetch_result(
            root, timeout=30, max_html_chars=settings.crawl_max_html_chars,
            playwright_min_chars=settings.smart_collector_playwright_min_chars,
            playwright_wait_ms=settings.smart_collector_playwright_wait_ms,
            label="referenti", try_variants=True,
        )
        if not home.text:
            continue
        base = home.url or root
        pages.append((base, html_to_text(home.text)))
        seen.add(base)
        for u in rank_people_links(home.text, base_url=base, limit=MAX_PAGES):
            if u in seen or len(pages) >= MAX_PAGES + 1:
                continue
            seen.add(u)
            text = await fetch_document_text(u, settings)
            if text:
                pages.append((u, text))
    found: list[tuple[dict, str]] = []
    claude_calls = 0
    by_rules = False
    claude_state.reset()  # a topped-up account is picked up again
    for url, text in pages:
        if not has_role_words(text):
            continue
        proposals: list[dict] | None = None
        if claude_state.use_claude(settings):
            status: dict = {"ok": True}
            claude_calls += 1
            proposals = await extract_people(text, url=url, ente=ente, settings=settings, status=status)
            if not status["ok"] and status.get("fatal") and claude_state.can_fall_back(settings):
                claude_state.mark_down(status.get("error", "errore"))
                proposals = None
        if proposals is None:
            by_rules = True
            proposals = extract_people_by_rules(text)
        for person in proposals:
            checked = verify_person(person, text)
            if checked:
                found.append((checked, url))
    people = merge_people(found)
    now = datetime.now(tz=UTC)
    async with SessionLocal() as session:
        for p in people:
            existing = (
                await session.execute(
                    select(Referente).where(
                        Referente.ente == ente, Referente.regione == regione,
                        Referente.ruolo == p["ruolo"], Referente.nome == p["nome"],
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(Referente(ente=ente, regione=regione, verified_at=now, **p))
            else:
                for k, v in p.items():
                    setattr(existing, k, v)
                existing.verified_at = now
        await session.commit()
    log.info("find_referenti ente=%s pages=%d claude_calls=%d people=%d", ente, len(pages), claude_calls, len(people))
    return {"ente": ente, "pagine": len(pages), "trovati": len(people), "metodo": "regole" if by_rules else "claude"}


@celery_app.task(name="app.tasks.find_referenti.find_referenti", soft_time_limit=600, time_limit=660)
def find_referenti(record_id: str) -> dict:
    return asyncio.run(find_for_record(UUID(record_id)))
