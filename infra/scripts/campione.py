"""Pick a SAMPLE of comuni for the free tests, spread over size and quantity.

IPA has no population, so size comes from a CSV you provide (any file with the comune name and the resident
population, e.g. the ISTAT "popolazione residente" download): columns are recognised by name
(comune|denominazione and popolazione|pop|residenti). Without it the sample is spread over the provinces.

    docker compose exec -T api python -m infra.scripts.campione --region Lombardia --n 60 \
        --ipa /workspace/infra/amministrazioni.txt --out /workspace/infra/prove/campione.csv

The comuni come from the IPA file (--ipa) or, without it, from the watchlist. For Lombardia the repository's old list
gives an estimated size class to 73 comuni; ``--popolazione`` (CSV comune;popolazione) gives it to all.

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


def default_fasce_path(region: str) -> str | None:
    """The old Lombardia list of the repository carries an estimated size class for 73 comuni: still useful as a
    size hint (the comuni themselves come from IPA)."""
    from pathlib import Path

    p = Path(__file__).parent / "data" / "comuni_lombardia_illuminazione.csv"
    return str(p) if region.strip().lower() == "lombardia" and p.exists() else None


def load_fasce(path: str | None) -> dict[str, str]:
    """{normalised comune name: size class} from a CSV with the columns comune and fascia_pop_stimata (or fascia)."""
    if not path:
        return {}
    out: dict[str, str] = {}
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            low = {k.strip().strip('"').lower(): v for k, v in r.items() if k}
            name = low.get("comune") or low.get("nome")
            f_ = (low.get("fascia_pop_stimata") or low.get("fascia") or "").strip().upper()
            if name and f_ in {x for x, _ in FASCE}:
                out[_key(name)] = f_
    return out


def stratified(items: list[dict], n: int, seed: int = 7) -> list[dict]:
    """About ``n`` items spread over the size classes (each class gets its share, at least 1 when present),
    and inside a class over the provinces. Repeatable: the same seed gives the same sample."""
    rng = random.Random(seed)
    by_f: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_f[it["fascia"]].append(it)
    # Unknown sizes ("n/d") must not drown the classes we do know: count them at most as many as the known ones.
    known = sum(len(g) for f, g in by_f.items() if f != "n/d")
    eff = {f: (min(len(g), max(known, 1)) if f == "n/d" and known else len(g)) for f, g in by_f.items()}
    total = sum(eff.values()) or 1
    picked: list[dict] = []
    for f_, group in sorted(by_f.items()):
        share = max(1, round(n * eff[f_] / total))
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
    ap.add_argument("--popolazione", help="CSV comune;popolazione (es. ISTAT) per le fasce di dimensione")
    ap.add_argument("--ipa", help="file IPA 'Amministrazioni': prende i comuni da li' invece che dal database")
    ap.add_argument("--fasce", help="CSV con colonne comune e fascia_pop_stimata (di default quello della Lombardia nel repository)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    from pathlib import Path

    from shared_models.regions import normalize_region

    pop = load_population(a.popolazione) if a.popolazione else {}
    fasce_note = load_fasce(a.fasce or default_fasce_path(a.region))
    items = []
    if a.ipa:  # the comuni straight from the IPA file: no database, no import needed
        from infra.scripts.import_ipa import parse_ipa_rows, xlsx_to_text

        text = xlsx_to_text(a.ipa) if a.ipa.lower().endswith((".xlsx", ".xlsm")) else Path(a.ipa).read_text(encoding="utf-8-sig", errors="replace")
        for r in parse_ipa_rows(text, a.region):
            url = r["trasparenza"] or r["sito"]
            if url:
                k = _key(r["name"])
                items.append({"nome": r["name"], "url": url, "regione": normalize_region(a.region), "provincia": r["provincia"],
                              "fascia": fascia_di(pop[k]) if k in pop else fasce_note.get(k, "n/d")})
    else:
        from app.db import SessionLocal
        from shared_models import Entity, WatchlistItem
        from sqlalchemy import select

        async with SessionLocal() as s:
            rows = (await s.execute(select(WatchlistItem, Entity).join(Entity, WatchlistItem.entity_id == Entity.id)
                                    .where(WatchlistItem.active.is_(True)))).all()
        for it, e in rows:
            url = it.url_trasparenza or it.url_albo
            if url and normalize_region(e.region) == normalize_region(a.region):
                k = _key(e.name)
                items.append({"nome": e.name, "url": url, "regione": e.region, "provincia": e.province,
                              "fascia": fascia_di(pop[k]) if k in pop else fasce_note.get(k, "n/d")})
    if not items:
        print("Nessun comune trovato" + (" nel file IPA." if a.ipa else " in watchlist: usa --ipa con il file IPA, oppure importa i comuni."))
        return
    sample = stratified(items, a.n)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)  # the folder "prove" does not exist the first time
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
