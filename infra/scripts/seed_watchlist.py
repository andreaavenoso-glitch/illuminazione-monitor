"""Seed watchlist_items, entities and sources with the baseline Italian public
lighting procurement targets. Idempotent: re-running preserves existing rows.

Usage (inside the api container):
    python -m infra.scripts.seed_watchlist
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import UUID

from app.core.database import SessionLocal
from app.models.entity import Entity
from app.models.source import Source
from app.models.watchlist_item import WatchlistItem
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Ported 1:1 from scripts/watchlist.json (38 entries).
# Layout: (ente, url, regione, entity_type).
WATCHLIST_ENTITIES: list[tuple[str, str, str, str]] = [
    ("Comune di Roma", "https://www.comune.roma.it/albo", "Lazio", "comune"),
    ("Comune di Milano", "https://www.comune.milano.it/albo", "Lombardia", "comune"),
    ("Comune di Napoli", "https://www.comune.napoli.it/albo", "Campania", "comune"),
    ("Comune di Torino", "https://www.comune.torino.it/appalti", "Piemonte", "comune"),
    ("Comune di Bologna", "https://www.comune.bologna.it/albo", "Emilia-Romagna", "comune"),
    ("Comune di Firenze", "https://www.comune.fi.it/albo", "Toscana", "comune"),
    ("Comune di Venezia", "https://www.comune.venezia.it/albo", "Veneto", "comune"),
    ("Comune di Palermo", "https://www.comune.palermo.it/albo", "Sicilia", "comune"),
    ("Comune di Genova", "https://www.comune.genova.it/albo", "Liguria", "comune"),
    ("Comune di Bari", "https://www.comune.bari.it/albo", "Puglia", "comune"),
    ("Comune di Catania", "https://www.comune.catania.it/albo", "Sicilia", "comune"),
    ("Comune di Verona", "https://www.comune.verona.it/albo", "Veneto", "comune"),
    ("Comune di Messina", "https://www.comune.messina.it/albo", "Sicilia", "comune"),
    ("Comune di Padova", "https://www.comune.padova.it/albo", "Veneto", "comune"),
    ("Comune di Trieste", "https://www.comune.trieste.it/albo", "Friuli-VG", "comune"),
    ("Comune di Brescia", "https://www.comune.brescia.it/albo", "Lombardia", "comune"),
    ("Comune di Taranto", "https://www.comune.taranto.it/albo", "Puglia", "comune"),
    ("Comune di Prato", "https://www.comune.prato.it/albo", "Toscana", "comune"),
    ("Comune di Reggio Calabria", "https://www.reggiocalabria.gov.it/albo", "Calabria", "comune"),
    ("Comune di Modena", "https://www.comune.modena.it/albo", "Emilia-Romagna", "comune"),
    ("Comune di Cagliari", "https://www.comune.cagliari.it/albo", "Sardegna", "comune"),
    ("Comune di Bergamo", "https://www.comune.bergamo.it/albo", "Lombardia", "comune"),
    ("Comune di Perugia", "https://www.comune.perugia.it/albo", "Umbria", "comune"),
    ("Comune di Ancona", "https://www.comune.ancona.it/albo", "Marche", "comune"),
    ("Provincia di Milano", "https://www.cittametropolitana.mi.it/albo", "Lombardia", "provincia"),
    ("Provincia di Roma", "https://www.cittametropolitana.roma.it/albo", "Lazio", "provincia"),
    ("Provincia di Napoli", "https://www.cittametropolitana.na.it/albo", "Campania", "provincia"),
    ("Provincia di Brescia", "https://www.provincia.brescia.it/albo", "Lombardia", "provincia"),
    ("Provincia di Torino", "https://www.cittametropolitana.torino.it/albo", "Piemonte", "provincia"),
    ("Regione Lombardia", "https://www.regione.lombardia.it/albo", "Lombardia", "regione"),
    ("Regione Lazio", "https://www.regione.lazio.it/albo", "Lazio", "regione"),
    ("Regione Siciliana", "https://www.regione.sicilia.it/albo", "Sicilia", "regione"),
    ("Regione Campania", "https://www.regione.campania.it/albo", "Campania", "regione"),
    ("ACEA SpA", "https://www.acea.it/appalti", "Lazio", "utility"),
    ("A2A SpA", "https://www.a2a.eu/appalti", "Lombardia", "utility"),
    ("Iren SpA", "https://www.gruppoiren.it/appalti", "Piemonte", "utility"),
    ("Hera SpA", "https://www.gruppohera.it/appalti", "Emilia-Romagna", "utility"),
]

# Spec §11 — sources across 3 tiers. source_priority_rank follows §9.2.
SOURCES: list[dict] = [
    # Tier official
    {"name": "ANAC Pubblicità Legale", "source_type": "official", "platform_type": "anac",
     "base_url": "https://dati.anticorruzione.it", "priority": "A",
     "source_priority_rank": 5, "reliability_score": 0.95, "publication_model": "rest_api"},
    {"name": "BDNCP", "source_type": "official", "platform_type": "bdncp",
     "base_url": "https://dati.anticorruzione.it/opendata", "priority": "A",
     "source_priority_rank": 5, "reliability_score": 0.95, "publication_model": "open_data"},
    {"name": "TED EU", "source_type": "official", "platform_type": "ted",
     "base_url": "https://ted.europa.eu/api/v3.0", "priority": "A",
     "source_priority_rank": 4, "reliability_score": 0.98, "publication_model": "rest_api"},
    {"name": "Gazzetta Ufficiale (GURI)", "source_type": "official", "platform_type": "guri",
     "base_url": "https://www.gazzettaufficiale.it", "priority": "A",
     "source_priority_rank": 4, "reliability_score": 0.95, "publication_model": "rss"},
    # Tier A e-procurement
    {"name": "ASMECOMM", "source_type": "eproc_portal", "platform_type": "asmecomm",
     "base_url": "https://piattaforma.asmecomm.it", "priority": "A",
     "source_priority_rank": 2, "reliability_score": 0.85, "publication_model": "html_scraping"},
    {"name": "Traspare", "source_type": "eproc_portal", "platform_type": "traspare",
     "base_url": "https://traspare.it", "priority": "A",
     "source_priority_rank": 2, "reliability_score": 0.85, "publication_model": "html_scraping"},
    {"name": "Tuttogare", "source_type": "eproc_portal", "platform_type": "tuttogare",
     "base_url": "https://www.tuttogare.it", "priority": "A",
     "source_priority_rank": 2, "reliability_score": 0.85, "publication_model": "html_scraping"},
    {"name": "SATER / Intercent-ER", "source_type": "eproc_portal", "platform_type": "sater",
     "base_url": "https://piattaformaintercenter.regione.emilia-romagna.it", "priority": "A",
     "source_priority_rank": 2, "reliability_score": 0.88, "publication_model": "html_scraping"},
    {"name": "START Toscana", "source_type": "eproc_portal", "platform_type": "start_toscana",
     "base_url": "https://start.toscana.it", "priority": "A",
     "source_priority_rank": 2, "reliability_score": 0.85, "publication_model": "html_scraping"},
    # Tier B e-procurement
    {"name": "DigitalPA", "source_type": "eproc_portal", "platform_type": "digitalpa",
     "base_url": "https://www.digitalpa.it", "priority": "B",
     "source_priority_rank": 2, "reliability_score": 0.75, "publication_model": "html_scraping"},
    {"name": "Portale Appalti", "source_type": "eproc_portal", "platform_type": "portale_appalti",
     "base_url": "https://portaleappalti.dsitalia.com", "priority": "B",
     "source_priority_rank": 2, "reliability_score": 0.75, "publication_model": "html_scraping"},
    {"name": "Sintel (ARIA Lombardia)", "source_type": "eproc_portal", "platform_type": "sintel",
     "base_url": "https://www.ariaspa.it/wps/portal/site/aria/acquistipervoi/Sintel", "priority": "B",
     "source_priority_rank": 2, "reliability_score": 0.85, "publication_model": "html_scraping"},
    {"name": "Net4market", "source_type": "eproc_portal", "platform_type": "net4market",
     "base_url": "https://app.albofornitori.it", "priority": "B",
     "source_priority_rank": 2, "reliability_score": 0.75, "publication_model": "html_scraping"},
    {"name": "Acquisti in Rete / Consip", "source_type": "eproc_portal", "platform_type": "consip",
     "base_url": "https://www.acquistinretepa.it", "priority": "B",
     "source_priority_rank": 2, "reliability_score": 0.90, "publication_model": "rest_api"},
    {"name": "SardegnaCAT", "source_type": "eproc_portal", "platform_type": "sardegnacat",
     "base_url": "https://www.sardegnacat.it", "priority": "B",
     "source_priority_rank": 2, "reliability_score": 0.75, "publication_model": "html_scraping"},
]


async def seed_sources(session: AsyncSession) -> dict[str, UUID]:
    out: dict[str, UUID] = {}
    for payload in SOURCES:
        stmt = select(Source).where(Source.name == payload["name"])
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            out[payload["name"]] = existing.id
            continue
        src = Source(
            name=payload["name"],
            source_type=payload["source_type"],
            platform_type=payload.get("platform_type"),
            base_url=payload["base_url"],
            sector_scope="illuminazione_pubblica",
            priority=payload.get("priority", "B"),
            source_priority_rank=payload.get("source_priority_rank", 999),
            reliability_score=Decimal(str(payload.get("reliability_score", 0))),
            publication_model=payload.get("publication_model"),
            active=True,
        )
        session.add(src)
        await session.flush()
        out[payload["name"]] = src.id
    return out


async def seed_entities_and_watchlist(
    session: AsyncSession, source_ids: dict[str, UUID]
) -> tuple[int, int]:
    # Pick one "albo pretorio"-ish default source; fallback to None if not seeded.
    default_source = source_ids.get("ANAC Pubblicità Legale")

    created_entities = 0
    created_watchlist = 0
    for name, url, region, entity_type in WATCHLIST_ENTITIES:
        stmt = select(Entity).where(Entity.name == name, Entity.region == region)
        entity = (await session.execute(stmt)).scalar_one_or_none()
        if entity is None:
            entity = Entity(name=name, region=region, entity_type=entity_type)
            session.add(entity)
            await session.flush()
            created_entities += 1

        wl_stmt = select(WatchlistItem).where(
            WatchlistItem.entity_id == entity.id,
            WatchlistItem.url_albo == url,
        )
        existing = (await session.execute(wl_stmt)).scalar_one_or_none()
        if existing:
            continue

        item = WatchlistItem(
            entity_id=entity.id,
            source_id=default_source,
            url_albo=url,
            frequency="daily",
            priority="B",
            reliability_score=Decimal("0.70"),
            publication_model="html_scraping",
            active=True,
        )
        session.add(item)
        created_watchlist += 1
    await session.flush()
    return created_entities, created_watchlist


async def main() -> None:
    async with SessionLocal() as session:
        source_ids = await seed_sources(session)
        created_entities, created_watchlist = await seed_entities_and_watchlist(
            session, source_ids
        )
        await session.commit()
        print(
            f"seed complete — sources={len(source_ids)} "
            f"new_entities={created_entities} new_watchlist={created_watchlist}"
        )


if __name__ == "__main__":
    asyncio.run(main())
