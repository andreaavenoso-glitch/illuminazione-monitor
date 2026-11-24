"""Seed the regional structure: region_settings for the 20 regions and the
regional sites (e-procurement, SUA/CUC, regional bando pages) of the catalog.

Idempotent and non-destructive: an existing region keeps its enabled flag and
recipients (edited in the UI); existing sources keep their active flag.

Env:
    ENABLED_REGIONS            regions switched on when first created
                               (default "Lombardia,Puglia" -- the two test regions)
    REGION_DEFAULT_RECIPIENTS  comma-separated emails for newly created regions

Usage (inside the api container):
    python -m infra.scripts.seed_regions
"""
from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path

CATALOG = Path(__file__).parent / "data" / "siti_regionali.json"
DEFAULT_ENABLED = "Lombardia,Puglia"
# Test referent for every region until real regional referents are entered in the UI.
DEFAULT_RECIPIENTS = "andrea.avenoso@outlook.com"


def parse_list(value: str | None) -> list[str]:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


async def main() -> None:
    from app.core.database import SessionLocal
    from shared_models import RegionSettings, Source
    from shared_models.regions import REGIONS, normalize_region
    from sqlalchemy import select

    enabled = {normalize_region(r) for r in parse_list(os.environ.get("ENABLED_REGIONS", DEFAULT_ENABLED))}
    recipients = ",".join(parse_list(os.environ.get("REGION_DEFAULT_RECIPIENTS") or DEFAULT_RECIPIENTS)) or None

    new_regions = new_sources = 0
    async with SessionLocal() as session:
        for region in REGIONS:
            if await session.get(RegionSettings, region) is None:
                session.add(RegionSettings(region=region, enabled=region in enabled, recipients=recipients))
                new_regions += 1

        entries = json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.exists() else []
        for e in entries:
            region = normalize_region(e["regione"])
            if region is None:
                continue
            name = f"{region} - {e['nome']}"
            if (await session.execute(select(Source).where(Source.name == name))).scalar_one_or_none():
                continue
            session.add(Source(
                name=name,
                source_type="regional_site",
                platform_type="generic_html",
                base_url=e["url"],
                regione=region,
                ruolo=e["ruolo"],
                sector_scope="illuminazione_pubblica",
                priority="B",
                source_priority_rank=2,
                reliability_score=Decimal("0.70"),
                publication_model="html_scraping",
                active=True,
            ))
            new_sources += 1
        await session.commit()
    print(f"seed_regions: new_regions={new_regions} new_regional_sites={new_sources} enabled={sorted(enabled)}")


if __name__ == "__main__":
    asyncio.run(main())
