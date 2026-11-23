"""Start a region (or all of them) from a clean sheet after test runs, keeping the HISTORY.

What it does, in this order:
1. SNAPSHOT: before deleting anything it writes what is there (avvisi, referenti, ricerche, analisi counts) to
   infra/prove/storico/<data>_<regione>.json, so that old and new tests stay comparable.
2. CLEANS the results: avvisi (and their alerts / analyses / events), raw records, referenti, referenti searches.
3. RESETS the memory of the scan (the fingerprints of the pages already read): without this the next scan would
   skip every page that did not change and would find nothing again.

It NEVER touches: the regions, the comuni (IPA), the watchlist addresses, the history of the scans
(the "Storico" tab: runs, per-comune items, depth), Claude's usage counter and the users.

Dry run by default: it only counts. Nothing is deleted without --applica.

    docker compose exec -T api python -m infra.scripts.azzera_prove --region Lombardia            # look
    docker compose exec -T api python -m infra.scripts.azzera_prove --region Lombardia --applica  # clean
    docker compose exec -T api python -m infra.scripts.azzera_prove --region all --applica        # every region
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HISTORY_DIR = Path("/workspace/infra/prove/storico")
# Heavy or useless columns left out of the snapshot.
_SKIP_COLUMNS = {"raw_html", "raw_body", "checklist_raw"}


def row_to_dict(row: Any) -> dict[str, Any]:
    """A model instance as plain JSON-able values (dates, uuids and decimals as text)."""
    from sqlalchemy import inspect

    out: dict[str, Any] = {}
    for col in inspect(type(row)).columns:
        if col.key in _SKIP_COLUMNS:
            continue
        val = getattr(row, col.key)
        out[col.key] = val if isinstance(val, (str, int, float, bool, list, dict, type(None))) else str(val)
    return out


def summarize(records: list[dict], referenti: list[dict]) -> dict[str, Any]:
    """The numbers that make two test rounds comparable (pure, tested)."""
    by_cat = Counter((r.get("tipo_novita") or r.get("atto_tipo") or "n/d") for r in records)
    by_state = Counter((r.get("verifica_esito") or "non verificato") for r in records)
    by_role = Counter(p.get("ruolo") or "n/d" for p in referenti)
    enti = {r.get("ente") for r in records if r.get("ente")}
    return {
        "avvisi": len(records),
        "enti_con_avvisi": len(enti),
        "per_tipo": dict(by_cat),
        "per_verifica": dict(by_state),
        "referenti": len(referenti),
        "referenti_per_ruolo": dict(by_role),
        "enti_con_referenti": len({p.get("ente") for p in referenti if p.get("ente")}),
    }


def history_path(region: str, now: datetime, base: Path | None = None) -> Path:
    base = base or HISTORY_DIR  # read at call time, so it can be redirected
    safe = "".join(c if c.isalnum() else "-" for c in region).strip("-").lower() or "regione"
    return base / f"{now.strftime('%Y%m%d-%H%M')}_{safe}.json"


async def run(region: str, apply: bool) -> None:
    from app.core.database import SessionLocal
    from shared_models import (
        Entity,
        ProcurementRecord,
        RawRecord,
        Referente,
        RicercaReferenti,
        WatchlistItem,
    )
    from shared_models.regions import normalize_region
    from sqlalchemy import delete, func, or_, select, update

    async with SessionLocal() as s:
        if region.lower() == "all":
            regions = sorted({r for (r,) in (await s.execute(select(Entity.region).distinct())).all() if r})
        else:
            regions = [normalize_region(region)]
        now = datetime.now(UTC)
        for canonical in regions:
            ents = (await s.execute(select(Entity).where(Entity.region == canonical))).scalars().all()
            ent_ids = [e.id for e in ents]
            names = [e.name for e in ents]
            rec_where = or_(ProcurementRecord.regione == canonical, ProcurementRecord.ente.in_(names or ["-"]))
            records = (await s.execute(select(ProcurementRecord).where(rec_where))).scalars().all()
            referenti = (await s.execute(select(Referente).where(Referente.regione == canonical))).scalars().all()
            ricerche = (await s.execute(select(RicercaReferenti).where(RicercaReferenti.regione == canonical))).scalars().all()
            n_raw = int(await s.scalar(select(func.count()).select_from(RawRecord).where(
                RawRecord.entity_id.in_(ent_ids or [None]))) or 0)
            n_items = int(await s.scalar(select(func.count()).select_from(WatchlistItem).where(
                WatchlistItem.entity_id.in_(ent_ids or [None]))) or 0)
            rec_d = [row_to_dict(r) for r in records]
            ref_d = [row_to_dict(r) for r in referenti]
            summary = summarize(rec_d, ref_d)
            print(f"\n== {canonical}: {len(ents)} comuni, {summary['avvisi']} avvisi, {summary['referenti']} referenti, "
                  f"{len(ricerche)} ricerche, {n_raw} record grezzi; indirizzi da riportare a 'mai letti': {n_items}")
            if not apply:
                continue
            if not ents and not rec_d and not ref_d:
                print("   niente da salvare né da ripulire.")
                continue
            path = history_path(canonical, now)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({
                "regione": canonical, "creato_il": now.isoformat(), "riepilogo": summary,
                "avvisi": rec_d, "referenti": ref_d, "ricerche": [row_to_dict(r) for r in ricerche],
            }, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"   storico salvato: {path}")
            await s.execute(delete(ProcurementRecord).where(rec_where))
            await s.execute(delete(RawRecord).where(RawRecord.entity_id.in_(ent_ids or [None])))
            await s.execute(delete(Referente).where(Referente.regione == canonical))
            await s.execute(delete(RicercaReferenti).where(RicercaReferenti.regione == canonical))
            await s.execute(update(WatchlistItem).where(WatchlistItem.entity_id.in_(ent_ids or [None])).values(
                content_hashes=None, last_scan_at=None, last_success_at=None, consecutive_failures=0, last_error=None))
            await s.commit()
            print("   ripulita: avvisi, grezzi, referenti, ricerche; memoria delle pagine azzerata.")
        if not apply:
            print("\nQuesta era una simulazione: aggiungi --applica per ripulire davvero (lo storico si salva prima).")
        else:
            print(f"\nFatto. Storico delle scansioni (tab 'Storico') e comuni intatti. File in {HISTORY_DIR}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True, help="nome della regione oppure 'all'")
    ap.add_argument("--applica", action="store_true", help="ripulisce davvero (senza: solo conteggi)")
    a = ap.parse_args()
    asyncio.run(run(a.region, a.applica))


if __name__ == "__main__":
    main()
