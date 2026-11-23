"""Pick a SAMPLE of comuni for the free tests, spread over size and quantity.

IPA has no population, so size comes from a CSV you provide (any file with the comune name and the resident
population, e.g. the ISTAT "popolazione residente" download): columns are recognised by name
(comune|denominazione and popolazione|pop|residenti). Without it the sample is spread over the provinces.

    docker compose exec -T api python -m infra.scripts.campione --region Lombardia --n 60 \
        --popolazione /workspace/infra/popolazione.csv --out /workspace/infra/prove/campione_lombardia.csv

Size classes: XS < 2.000, S 2.000-5.000, M 5.000-15.000, L 15.000-50.000, XL > 50.000 inhabitants.
The output (name;url;regione;provincia;fascia) feeds ``prova_siti --campione``.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import random
import re
from collections import defaultdict

FASCE = (("XS", 2_000), ("S", 5_000), ("M", 15_000), ("L", 50_000), ("XL", float("inf")))


def fascia_di(pop: int | None) -> str:
    if pop is None:
        return "n/d"
    for name, limit in FASCE:
        if pop < limit:
            return name
    return "XL"


def _key(name: str) -> str:
    n = re.sub(r"^(comune|citta)( metropolitana)? di\s+", "", name.strip().lower())
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def load_population(path: str) -> dict[str, int]:
    """{normalised comune name: population} from a CSV/TSV with recognisable columns."""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    first = text.split("\n", 1)[0]
    delim = ";" if first.count(";") >= max(first.count(","), first.count("\t")) else ("\t" if first.count("\t") > first.count(",") else ",")
    rows = csv.DictReader(text.splitlines(), delimiter=delim)
    out: dict[str, int] = {}
    for r in rows:
        low = {k.strip().lower(): v for k, v in r.items() if k}
        name = next((low[k] for k in ("comune", "denominazione", "denominazione comune", "nome") if k in low), None)
        pop = next((low[k] for k in ("popolazione", "pop", "residenti", "popolazione residente", "totale") if k in low), None)
        try:
            if name and pop:
                out[_key(name)] = int(re.sub(r"[^\d]", "", pop))
        except ValueError:
            continue
    return out


def stratified(items: list[dict], n: int, seed: int = 7) -> list[dict]:
    """About ``n`` items spread over the size classes (each class gets its share, at least 1 when present),
    and inside a class over the provinces. Repeatable: the same seed gives the same sample."""
    rng = random.Random(seed)
    by_f: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_f[it["fascia"]].append(it)
    total = len(items) or 1
    picked: list[dict] = []
    for _f, group in sorted(by_f.items()):
        share = max(1, round(n * len(group) / total))
        by_p: dict[str, list[dict]] = defaultdict(list)
        for g in group:
            by_p[g.get("provincia") or "-"].append(g)
        for lst in by_p.values():
            rng.shuffle(lst)
        chosen: list[dict] = []
        while len(chosen) < min(share, len(group)):
            for p in sorted(by_p):
                if by_p[p] and len(chosen) < min(share, len(group)):
                    chosen.append(by_p[p].pop())
        picked += chosen
    return picked[: max(n, len(by_f))]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--popolazione")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    from app.db import SessionLocal
    from shared_models import Entity, WatchlistItem
    from shared_models.regions import normalize_region
    from sqlalchemy import select

    pop = load_population(a.popolazione) if a.popolazione else {}
    async with SessionLocal() as s:
        rows = (await s.execute(select(WatchlistItem, Entity).join(Entity, WatchlistItem.entity_id == Entity.id)
                                .where(WatchlistItem.active.is_(True)))).all()
    items = []
    for it, e in rows:
        url = it.url_trasparenza or it.url_albo
        if url and normalize_region(e.region) == normalize_region(a.region):
            items.append({"nome": e.name, "url": url, "regione": e.region, "provincia": e.province,
                          "fascia": fascia_di(pop.get(_key(e.name)))})
    if not items:
        print("Nessun comune in watchlist per questa regione.")
        return
    sample = stratified(items, a.n)
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["nome", "url", "regione", "provincia", "fascia"], delimiter=";")
        w.writeheader()
        w.writerows(sample)
    from collections import Counter

    print(f"{len(sample)} comuni su {len(items)}; per fascia: {dict(Counter(x['fascia'] for x in sample))} -> {a.out}")
    if not pop:
        print("Nota: senza --popolazione la fascia e' n/d e il campione e' spalmato sulle province.")


if __name__ == "__main__":
    asyncio.run(main())
