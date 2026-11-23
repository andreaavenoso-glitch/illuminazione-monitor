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
    looks_like_name,
    merge_people,
    rank_people_links,
    site_root,
    verify_person,
)
from app.collectors.referenti_agent import research
from app.collectors.referenti_script import search_referenti
from app.collectors.rules_extract import extract_people_by_rules
from app.config import get_worker_settings
from app.db import SessionLocal
from app.tasks.verify_records import fetch_document_text, html_to_text
from shared_models import Entity, ProcurementRecord, Referente, RicercaReferenti, WatchlistItem
from shared_models.referenti_logic import election_date, freshness, has_decree, page_date
from sqlalchemy import select

log = logging.getLogger(__name__)

MAX_PAGES = 6


def _apply_freshness(person: dict, text: str, elezione, today) -> dict:
    """Downgrade a verified name whose page is too old for its role (see referenti_logic)."""
    pos = text.lower().find(person["nome"].lower().split()[-1])
    window = text[max(0, pos - 300): pos + 300] if pos >= 0 else ""
    data_fonte = page_date(text, today)
    ok, motivo = freshness(person["ruolo"], data_fonte, elezione, has_decree(window), today)
    out = {**person, "data_fonte": data_fonte, "elezione_data": elezione, "motivo": None}
    if person["stato"] != "verificato":
        out["motivo"] = "ruolo non scritto accanto al nome"
    elif not ok:
        out["stato"] = "da_confermare"
        out["motivo"] = motivo
    return out


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


async def _save(ente: str, regione: str | None, people: list[dict]) -> None:
    """Upsert the people of an ente; names saved by an older version that are page furniture
    ("Condividi Facebook Twitter") are removed (the PEC row, ruolo "ente", is kept)."""
    now = datetime.now(tz=UTC)
    async with SessionLocal() as session:
        for old in (
            await session.execute(select(Referente).where(Referente.ente == ente, Referente.regione == regione))
        ).scalars().all():
            if old.ruolo != "ente" and not looks_like_name(old.nome):
                await session.delete(old)
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


async def _gather_pages(link: str, roots: list[str], settings) -> tuple[list[tuple[str, str]], list[str]]:
    """The record's own document, the comune's home page and the menu pages that lead to the people
    (all read here with plain HTTP / browser, not by the web tool, which only opens URLs it has
    been shown). Returns the pages (url, text) and the candidate menu links."""
    pages: list[tuple[str, str]] = []  # (url, text)
    menu_links: list[str] = []
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
        ranked = rank_people_links(home.text, base_url=base, limit=15)
        menu_links.extend(u for u in ranked if u not in menu_links)
        for u in ranked[:MAX_PAGES]:
            if u in seen or len(pages) >= MAX_PAGES + 1:
                continue
            seen.add(u)
            text = await fetch_document_text(u, settings)
            if text:
                pages.append((u, text))
    return pages, menu_links


async def _script_fetch(url: str, settings) -> tuple[str, str | None]:
    """(text, raw html) of a page of the comune: plain HTTP (PDF too), then the browser for JS sites."""
    from app.tasks.verify_records import _fetch_plain

    text, raw = await _fetch_plain(url)
    if text:
        return text, raw
    res = await adaptive_fetch_result(
        url, timeout=30, max_html_chars=settings.crawl_max_html_chars,
        playwright_min_chars=settings.smart_collector_playwright_min_chars,
        playwright_wait_ms=settings.smart_collector_playwright_wait_ms, label="referenti", try_variants=True,
    )
    return (html_to_text(res.text), res.text) if res.text else ("", None)


async def _fetch_press(url: str) -> str:
    import httpx

    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as c:
        r = await c.get(url, headers={"User-Agent": "Mozilla/5.0"})
    return r.text if r.status_code < 400 else ""


async def _save_ricerca(ente: str, regione: str | None, metodo: str, res: dict) -> None:
    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(RicercaReferenti).where(RicercaReferenti.ente == ente, RicercaReferenti.regione == regione)
            )
        ).scalar_one_or_none()
        if row is None:
            row = RicercaReferenti(ente=ente, regione=regione)
            session.add(row)
        row.metodo = metodo
        row.checklist = {"passi": res.get("checklist") or [], "urls": res.get("urls") or [], "stampa_articoli": res.get("press") or []}
        row.lacune = res.get("lacune") or []
        row.stampa = res.get("stampa")
        row.elezione_data = res.get("elezione")
        row.mandato_scadenza = res.get("mandato_scadenza")
        row.eseguita_il = datetime.now(tz=UTC)
        await session.commit()


async def find_for_record(record_id: UUID) -> dict:
    async with SessionLocal() as session:
        rec = await session.get(ProcurementRecord, record_id)
        if rec is None:
            return {"error": "record non trovato"}
        ente, regione, link = rec.ente, rec.regione, rec.link_bando
    return await find_for_ente(ente, regione, link)


async def find_for_ente(ente: str, regione: str | None, link: str | None = None) -> dict:
    """Referenti of one ente. ``link`` (the notice's own page) is optional: without it the search starts
    from the comune's site on the watchlist."""
    settings = get_worker_settings()
    async with SessionLocal() as session:
        roots = await _site_urls(session, ente, regione, link or "")
    if not roots and not link:
        return {"ente": ente, "error": "nessun sito del comune in watchlist: impossibile cercare", "trovati": 0}
    link = link or roots[0]

    claude_state.reset()  # a topped-up account is picked up again
    mode = (settings.referenti_mode or "script").lower()
    if mode in ("script", "auto"):
        async with SessionLocal() as session:
            ent = (
                await session.execute(select(Entity).where(Entity.name == ente, Entity.region == regione))
            ).scalar_one_or_none()
            pec = ent.pec if ent else None
        async def fetch(u: str):
            return await _script_fetch(u, settings)
        # the record's own document first (the RUP is often named there), then the comune's site
        res = await search_referenti(
            ente, [*roots, link] if link not in roots else roots, fetch, _fetch_press, pec=pec, today=datetime.now(tz=UTC).date()
        )
        people = list(res["people"])
        if pec:
            people.append({
                "nome": "PEC dell'ente", "ruolo": "ente", "qualifica": "PEC (IPA)", "email": pec, "telefono": None,
                "citazione": None, "fonte_url": "https://indicepa.gov.it", "data_fonte": None,
                "elezione_data": res["elezione"], "stato": "verificato", "motivo": None,
            })
        has_mayor = any(p["ruolo"] == "sindaco" for p in res["people"])
        if mode == "script" or has_mayor or not claude_state.use_claude(settings):
            await _save(ente, regione, people)
            await _save_ricerca(ente, regione, "script", res)
            ok = sum(1 for c in res["checklist"] if c["ok"])
            log.info("find_referenti script ente=%s people=%d checklist=%d/12", ente, len(res["people"]), ok)
            return {
                "ente": ente, "trovati": len(res["people"]), "metodo": "script (gratuito)", "pagine": len(res["urls"]),
                "proposte": len(res["people"]), "url": res["urls"][:20], "lacune": res["lacune"], "stampa": res["stampa"],
                "checklist_ok": ok, "mandato_scadenza": str(res["mandato_scadenza"] or ""),
            }
        # auto: the script found no sindaco -> let the agent try, below
    pages, menu_links = await _gather_pages(link, roots, settings)
    if mode in ("auto", "agent") and claude_state.use_claude(settings):
        status: dict = {"ok": True}
        res = await research(
            ente, regione, [link, *roots], settings, status, pages=pages, menu_links=menu_links
        )
        if res is not None:
            people = list(res["people"])
            if res["pec"]:
                pec, fonte = res["pec"]
                people.append({
                    "nome": "PEC dell'ente", "ruolo": "ente", "qualifica": "PEC", "email": pec, "telefono": None,
                    "citazione": None, "fonte_url": fonte or "https://indicepa.gov.it", "data_fonte": None,
                    "elezione_data": res["elezione"], "stato": "verificato", "motivo": None,
                })
            await _save(ente, regione, people)
            await _save_ricerca(ente, regione, "agente", {"lacune": res["lacune"], "stampa": res["stampa"], "elezione": res["elezione"], "mandato_scadenza": res["mandato_scadenza"], "urls": res["urls"], "checklist": []})
            log.info("find_referenti agent ente=%s people=%d lacune=%s", ente, len(res["people"]), res["lacune"])
            return {
                "ente": ente, "trovati": len(res["people"]), "metodo": "agente", "pagine": len(res["urls"]),
                "proposte": len(res["people"]), "url": res["urls"][:20], "lacune": res["lacune"],
                "stampa": res["stampa"], "mandato_scadenza": str(res["mandato_scadenza"] or ""),
            }
        if status.get("fatal") and claude_state.can_fall_back(settings):
            claude_state.mark_down(status.get("error", "errore"))
        # otherwise (or on a fatal refusal): read the comune's own pages, as before

    today = datetime.now(tz=UTC).date()
    # last election written on any page of the ente
    elezione = max((e for _, t in pages if (e := election_date(t, today))), default=None)
    found: list[tuple[dict, str]] = []
    claude_calls = 0
    proposed = 0
    by_rules = False
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
        proposed += len(proposals)
        for person in proposals:
            checked = verify_person(person, text)
            if checked:
                found.append((_apply_freshness(checked, text, elezione, today), url))
    people = merge_people(found)
    await _save(ente, regione, people)
    log.info(
        "find_referenti ente=%s pages=%s claude_calls=%d proposed=%d people=%d",
        ente, [(u[:80], len(t)) for u, t in pages], claude_calls, proposed, len(people),
    )
    return {
        "ente": ente, "pagine": len(pages), "trovati": len(people), "proposte": proposed,
        "metodo": "regole" if by_rules else "claude", "url": [u for u, _ in pages],
    }


@celery_app.task(name="app.tasks.find_referenti.find_referenti", soft_time_limit=600, time_limit=660)
def find_referenti(record_id: str) -> dict:
    return asyncio.run(find_for_record(UUID(record_id)))


@celery_app.task(name="app.tasks.find_referenti.find_referenti_ente", soft_time_limit=600, time_limit=660)
def find_referenti_ente(ente: str, regione: str | None = None) -> dict:
    return asyncio.run(find_for_ente(ente, regione))


async def _region_entes(region: str) -> list[str]:
    """Enti of the region that have a notice worth acting on (any category, open or to verify)."""
    from datetime import timedelta

    from shared_models.categories import categorize_record

    since = datetime.now(tz=UTC) - timedelta(days=365)
    async with SessionLocal() as session:
        recs = (
            await session.execute(
                select(ProcurementRecord).where(
                    ProcurementRecord.regione == region,
                    ProcurementRecord.master_record_id.is_(None),
                    ProcurementRecord.first_seen_at >= since,
                )
            )
        ).scalars().all()
    return sorted({r.ente for r in recs if categorize_record(r) is not None})


async def find_for_region(region: str) -> dict:
    entes = await _region_entes(region)
    out = {"region": region, "enti": len(entes), "con_sindaco": 0, "senza_sito": 0, "errori": 0}
    for ente in entes:
        try:
            r = await asyncio.wait_for(find_for_ente(ente, region), timeout=300)
        except Exception:  # noqa: BLE001
            out["errori"] += 1
            log.exception("find_referenti.region_failed ente=%s", ente)
            continue
        if r.get("error"):
            out["senza_sito"] += 1
        elif r.get("trovati"):
            out["con_sindaco"] += 1
        await asyncio.sleep(1)
    return out


@celery_app.task(name="app.tasks.find_referenti.find_referenti_region", soft_time_limit=4 * 3600, time_limit=4 * 3600 + 300)
def find_referenti_region(region: str) -> dict:
    return asyncio.run(find_for_region(region))
