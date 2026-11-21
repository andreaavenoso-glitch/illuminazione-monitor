"""Diagnosi dei siti comunali non raggiungibili (consecutive_failures > 0).

Raggruppa i siti KO per causa e indica cosa fare; con --prova ritenta ogni
sito (varianti www/http, radice del dominio) senza modificare nulla; con
--applica salva gli indirizzi che ora rispondono.

    docker compose exec -T worker python -m infra.scripts.siti_ko [--regione Puglia] [--prova] [--applica]
"""
from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from urllib.parse import urlsplit, urlunsplit

AZIONE = {
    "dns": "indirizzo probabilmente sbagliato/dismesso: cercare il sito giusto (IPA, ricerca web)",
    "http_404": "pagina spostata: si riparte dalla home del dominio",
    "http_403": "il sito blocca i bot: non si risolve cambiando indirizzo; serve verifica manuale",
    "ssl": "certificato del server rotto: si prova http",
    "timeout": "lento o temporaneo: ritentare in un altro orario",
    "reset": "firewall/WAF: spesso solo www si o no; poi verifica manuale",
    "connect": "server che rifiuta la connessione: ritentare, poi verifica manuale",
    "empty": "pagina letta ma vuota (JS/blocco): verifica manuale",
}


def candidates(url: str, error: str | None) -> list[str]:
    from app.collectors.adaptive_fetch import url_variants

    parts = urlsplit(url)
    root = urlunsplit(parts._replace(path="/", query="", fragment=""))
    out = [url, *url_variants(url, error), root, *url_variants(root, error)]
    return list(dict.fromkeys(out))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regione")
    ap.add_argument("--prova", action="store_true")
    ap.add_argument("--applica", action="store_true")
    args = ap.parse_args()

    from app.collectors.adaptive_fetch import adaptive_fetch_result
    from app.config import get_worker_settings
    from app.db import SessionLocal
    from shared_models.entity import Entity
    from shared_models.watchlist_item import WatchlistItem
    from sqlalchemy import select

    st = get_worker_settings()
    async with SessionLocal() as s:
        q = (
            select(WatchlistItem, Entity)
            .join(Entity, Entity.id == WatchlistItem.entity_id)
            .where(WatchlistItem.consecutive_failures > 0, WatchlistItem.active.is_(True))
        )
        if args.regione:
            q = q.where(Entity.region.ilike(args.regione))
        rows = (await s.execute(q.order_by(Entity.name))).all()
        per: dict[str, list] = defaultdict(list)
        for item, ent in rows:
            per[item.last_error or "empty"].append((item, ent))
        print(f"Siti KO: {len(rows)}")
        for kind, lst in sorted(per.items(), key=lambda kv: -len(kv[1])):
            print(f"\n== {kind}: {len(lst)}  -> {AZIONE.get(kind, 'verifica manuale')}")
            for item, ent in lst:
                print(f"  {ent.name} ({ent.province or '-'})  {item.url_albo or item.url_gare or item.url_trasparenza}")
        if not args.prova:
            print("\nAggiungi --prova per ritentare con le varianti, --applica per salvarle.")
            return
        sana = 0
        for kind, lst in per.items():
            for item, ent in lst:
                base = item.url_albo or item.url_gare or item.url_trasparenza
                if not base:
                    continue
                for cand in candidates(base, kind):
                    r = await adaptive_fetch_result(
                        cand, timeout=15, max_html_chars=st.crawl_max_html_chars,
                        playwright_min_chars=st.smart_collector_playwright_min_chars,
                        playwright_wait_ms=st.smart_collector_playwright_wait_ms,
                        label="siti_ko", try_variants=False,
                    )
                    if r.text:
                        sana += 1
                        print(f"OK  {ent.name}: {cand}")
                        if args.applica:
                            for f in ("url_albo", "url_gare", "url_trasparenza"):
                                if getattr(item, f) == base:
                                    setattr(item, f, cand)
                            item.consecutive_failures = 0
                            item.last_error = None
                        break
                else:
                    print(f"KO  {ent.name}: nessuna variante risponde")
        if args.applica:
            await s.commit()
        print(f"\nRecuperabili: {sana}/{len(rows)}" + ("" if args.applica else " (non salvati: usa --applica)"))


if __name__ == "__main__":
    asyncio.run(main())
