"""Clean a region of the comuni that do NOT come from the IPA file (leftovers of earlier simulations:
seed lists with plain names such as "Arluno" next to the IPA's "Comune di Arluno").

Dry run by default: it only counts and lists. Nothing is deleted without --applica.

    docker compose exec -T api python -m infra.scripts.pulisci_regione --region Lombardia \
        --file /workspace/infra/amministrazioni.txt             # look
    docker compose exec -T api python -m infra.scripts.pulisci_regione --region Lombardia \
        --file /workspace/infra/amministrazioni.txt --applica   # clean

What counts as "wrong": an entity of type comune in the region whose name is not one of the IPA file's comuni.
Removed with it (unless --tieni-record): its watchlist item, the raw and processed records collected under that
name, its referenti and referenti searches. The IPA comuni, the regional sites and everything of other regions
are never touched.
"""
from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable


def split_valid_old(entities: Iterable[tuple[str, str, str | None]], valid_names: set[str]) -> tuple[list, list]:
    """(valid, old) from (id, name, entity_type): old = a comune whose name is not in the IPA list."""
    valid, old = [], []
    for ent in entities:
        _id, name, etype = ent
        if (etype or "comune") != "comune":
            continue  # other kinds of enti are not comuni: left alone
        (valid if name in valid_names else old).append(ent)
    return valid, old


async def run(region: str, file: str, apply: bool, keep_records: bool) -> None:
    from app.core.database import SessionLocal
    from shared_models import Entity, ProcurementRecord, RawRecord, Referente, RicercaReferenti, WatchlistItem
    from shared_models.regions import normalize_region
    from sqlalchemy import delete, func, select

    from infra.scripts.import_ipa import parse_ipa_rows, xlsx_to_text

    canonical = normalize_region(region)
    if file.lower().endswith((".xlsx", ".xlsm")):
        text = xlsx_to_text(file)
    else:
        with open(file, encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    ipa = parse_ipa_rows(text, region)
    if not ipa:
        print(f"Nessun comune di {canonical} nel file IPA: controlla il file. Non cancello nulla.")
        return
    valid_names = {r["name"] for r in ipa}
    async with SessionLocal() as s:
        ents = (await s.execute(select(Entity).where(Entity.region == canonical))).scalars().all()
        valid, old = split_valid_old([(str(e.id), e.name, e.entity_type) for e in ents], valid_names)
        old_ids = [e[0] for e in old]
        old_names = [e[1] for e in old]
        print(f"Regione {canonical}: {len(ipa)} comuni nel file IPA, {len(valid)} presenti, {len(old)} da eliminare.")
        if old_names:
            print("Esempi da eliminare:", ", ".join(sorted(old_names)[:15]) + (" …" if len(old_names) > 15 else ""))
        missing = valid_names - {v[1] for v in valid}
        print(f"Comuni IPA non ancora importati: {len(missing)} (si importano con import_ipa).")
        if not old:
            print("Niente da pulire.")
            return

        async def count(model, *where) -> int:
            return int(await s.scalar(select(func.count()).select_from(model).where(*where)) or 0)

        n_items = await count(WatchlistItem, WatchlistItem.entity_id.in_(old_ids))
        n_raw = await count(RawRecord, RawRecord.entity_id.in_(old_ids))
        n_rec = await count(ProcurementRecord, ProcurementRecord.regione == canonical, ProcurementRecord.ente.in_(old_names))
        n_ref = await count(Referente, Referente.regione == canonical, Referente.ente.in_(old_names))
        print(f"Da eliminare: {len(old)} enti, {n_items} voci di watchlist, {n_raw} record grezzi, "
              f"{n_rec} record elaborati{' (TENUTI: --tieni-record)' if keep_records else ''}, {n_ref} referenti.")
        if not apply:
            print("\nQuesta era una simulazione: aggiungi --applica per eliminare davvero.")
            return
        if not keep_records:
            await s.execute(delete(RawRecord).where(RawRecord.entity_id.in_(old_ids)))
            await s.execute(delete(ProcurementRecord).where(
                ProcurementRecord.regione == canonical, ProcurementRecord.ente.in_(old_names)))
        await s.execute(delete(Referente).where(Referente.regione == canonical, Referente.ente.in_(old_names)))
        await s.execute(delete(RicercaReferenti).where(
            RicercaReferenti.regione == canonical, RicercaReferenti.ente.in_(old_names)))
        await s.execute(delete(WatchlistItem).where(WatchlistItem.entity_id.in_(old_ids)))
        await s.execute(delete(Entity).where(Entity.id.in_(old_ids)))
        await s.commit()
        print("Fatto: regione ripulita. Ora puoi rilanciare import_ipa per i comuni mancanti.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True)
    ap.add_argument("--file", required=True, help="file IPA 'Amministrazioni' (txt, csv o xlsx)")
    ap.add_argument("--applica", action="store_true", help="elimina davvero (senza: solo simulazione)")
    ap.add_argument("--tieni-record", action="store_true", help="non cancellare i record raccolti")
    a = ap.parse_args()
    asyncio.run(run(a.region, a.file, a.applica, a.tieni_record))


if __name__ == "__main__":
    main()
