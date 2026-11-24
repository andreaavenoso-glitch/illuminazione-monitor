"""Correct the addresses an already-listed comune is read from (the initial seed never overwrites an existing comune).

    docker compose exec -T api python -m infra.scripts.imposta_siti --region Lombardia --comune Arluno \
        --albo https://dgegovpa.it/Arluno/albo/albo \
        --trasparenza https://dgegovpa.it/Arluno/amministrazionetrasparente/amministrazionetrasparente

Only the addresses given are changed; the counters of failed readings are reset, because they described the old address.
"""
from __future__ import annotations

import argparse
import asyncio


async def run(region: str, comune: str, albo: str | None, trasparenza: str | None) -> int:
    from app.core.database import SessionLocal
    from app.services.browser_import import pick_comune
    from shared_models import Entity, WatchlistItem
    from shared_models.regions import normalize_region
    from sqlalchemy import select

    async with SessionLocal() as s:
        rows = (await s.execute(select(WatchlistItem, Entity).join(Entity, WatchlistItem.entity_id == Entity.id))).all()
        item, others = pick_comune([(i, e.name) for i, e in rows if normalize_region(e.region) == normalize_region(region)], comune)
        if item is None:
            print(f"Più comuni corrispondono: {', '.join(others)}" if others else f"Comune «{comune}» non trovato in {region}.")
            return 1
        print(f"prima:  albo={item.url_albo}  trasparenza={item.url_trasparenza}")
        if albo:
            item.url_albo = albo
        if trasparenza:
            item.url_trasparenza = trasparenza
        item.consecutive_failures = 0
        item.last_error = None
        item.active = bool(item.url_albo or item.url_trasparenza)
        await s.commit()
        print(f"dopo:   albo={item.url_albo}  trasparenza={item.url_trasparenza}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", required=True)
    ap.add_argument("--comune", required=True)
    ap.add_argument("--albo")
    ap.add_argument("--trasparenza")
    a = ap.parse_args()
    if not (a.albo or a.trasparenza):
        ap.error("indica almeno --albo o --trasparenza")
    raise SystemExit(asyncio.run(run(a.region, a.comune, a.albo, a.trasparenza)))


if __name__ == "__main__":
    main()
