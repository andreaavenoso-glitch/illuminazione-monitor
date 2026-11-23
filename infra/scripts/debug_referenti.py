"""Show, step by step, why the search for referenti of one record finds (or not) anybody.

    docker compose exec -T worker python -m infra.scripts.debug_referenti "Scanzano Jonico"

Prints: is the PDF reader installed, the pages read (size, role words), the attachments found
and read, what Claude and the free rules propose on each page, and what survives the check.
"""
from __future__ import annotations

import asyncio
import sys


async def main(needle: str) -> None:
    from app.collectors.referenti import (
        extract_people,
        has_role_words,
        rank_people_links,
        site_root,
        verify_person,
    )
    from app.collectors.rules_extract import extract_people_by_rules
    from app.config import get_worker_settings
    from app.db import SessionLocal
    from app.tasks.verify_records import _fetch_plain, attachment_links, fetch_document_text, html_to_text
    from shared_models import ProcurementRecord
    from sqlalchemy import select

    settings = get_worker_settings()
    try:
        import pypdf  # noqa: F401

        print("lettore PDF (pypdf): installato")
    except ImportError:
        print("lettore PDF (pypdf): MANCANTE -> ricostruire l'immagine del worker (bash aggiorna.sh)")
    async with SessionLocal() as s:
        recs = (
            await s.execute(select(ProcurementRecord).where(ProcurementRecord.ente.ilike(f"%{needle}%")).limit(3))
        ).scalars().all()
    if not recs:
        print(f"nessun record per '{needle}'")
        return
    rec = recs[0]
    print(f"\nRecord: {rec.ente} | {rec.link_bando}")
    text, raw = await _fetch_plain(rec.link_bando)
    print(f"pagina del record: {len(text)} caratteri (HTML grezzo: {'si' if raw else 'no'})")
    if raw:
        links = attachment_links(raw, base_url=rec.link_bando)
        print(f"allegati riconosciuti: {links or 'nessuno'}")
        for u in links:
            t, _ = await _fetch_plain(u)
            print(f"  - {u[:90]}: {len(t)} caratteri letti")
    pages = [(rec.link_bando, await fetch_document_text(rec.link_bando, settings))]
    root = site_root(rec.link_bando)
    if root:
        home, hraw = await _fetch_plain(root)
        print(f"\nhome {root}: {len(home)} caratteri")
        if hraw:
            ranked = rank_people_links(hraw, base_url=root, limit=6)
            print(f"voci di menu verso giunta/uffici trovate: {ranked or 'nessuna'}")
            pages.append((root, html_to_text(hraw)))
            for u in ranked[:3]:
                pages.append((u, await fetch_document_text(u, settings)))
    for url, t in pages:
        print(f"\n== {url[:100]}  ({len(t)} caratteri, parole di ruolo: {has_role_words(t)})")
        if not t:
            continue
        rules = extract_people_by_rules(t)
        print(f"   regole: {[(p['ruolo'], p['nome']) for p in rules] or 'nessuno'}")
        if settings.anthropic_api_key and has_role_words(t):
            st: dict = {"ok": True}
            props = await extract_people(t, url=url, ente=rec.ente, settings=settings, status=st)
            print(f"   Claude: {[(p.get('ruolo'), p.get('nome')) for p in props] or 'nessuno'}  stato={st}")
            for p in props:
                print(f"     controllo sul testo di {p.get('nome')}: {'ok' if verify_person(p, t) else 'SCARTATO'}")


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "Scanzano"))
