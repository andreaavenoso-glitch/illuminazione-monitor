"""Pipeline stage 3: score + dedupe procurement_records.

Steps for each batch:
1. recompute ``dedup_key`` for every record (covers backfills)
2. group records by ``dedup_key`` and pick a master per §9.2
3. assign ``master_record_id`` on duplicates so the dashboard can hide them
4. compute ``score_commerciale`` + ``priorita_commerciale`` via the scoring
   engine (port of pipeline.js:222-240)

A single ``JobRun`` row records counters (records_found = examined,
records_valid = scored, duplicates_removed = members marked as duplicate).
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime
from uuid import UUID

from app.celery_app import celery_app
from app.db import SessionLocal
from app.domain.deduplication import compute_dedup_key, deduplicate_group
from scoring_engine import ScoringInput, score_record
from shared_models import JobRun, ProcurementRecord
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

BATCH_SIZE = 1000


def _is_yes(value: str | None) -> bool:
    return (value or "").strip().lower() == "yes"


def _tag_list(record: ProcurementRecord) -> tuple[str, ...]:
    raw = (record.tag_tecnico or "").strip()
    if not raw:
        return ()
    return tuple(t.strip() for t in raw.split(",") if t.strip())


def _pre_gara_strength(record: ProcurementRecord) -> str | None:
    if record.stato_procedurale != "PRE-GARA":
        return None
    # Heuristic: when a strong pre-gara marker (delibera/determina/
    # avviso preinformazione) is in the description, treat as forte.
    text = (record.descrizione or "").lower()
    if any(kw in text for kw in ("delibera", "determina", "avviso preinformazione")):
        return "forte"
    return "debole"


async def _process(session: AsyncSession, job: JobRun, *, now: datetime) -> None:
    stmt = select(ProcurementRecord).order_by(ProcurementRecord.first_seen_at.asc()).limit(BATCH_SIZE)
    records = list((await session.execute(stmt)).scalars().all())
    job.records_found = len(records)

    # 1. Recompute dedup keys
    by_key: dict[str, list[ProcurementRecord]] = defaultdict(list)
    for r in records:
        key = compute_dedup_key(
            cig=r.cig, ente=r.ente, oggetto=r.descrizione, importo=r.importo
        )
        r.dedup_key = key
        by_key[key].append(r)

    # 2. Group + assign master/duplicates
    duplicates_marked = 0
    for group in by_key.values():
        if len(group) < 2:
            # Master is itself.
            for r in group:
                r.master_record_id = None
            continue
        result = deduplicate_group(group)
        master_uuid = UUID(result.master_id) if result.master_id else None
        for r in group:
            if str(r.id) == result.master_id:
                r.master_record_id = None
            else:
                r.master_record_id = master_uuid
                duplicates_marked += 1
    job.duplicates_removed = duplicates_marked

    # 3. Score everything (also duplicates: useful for downstream comparison)
    scored = 0
    for r in records:
        try:
            output = score_record(
                ScoringInput(
                    importo=r.importo,
                    stato_procedurale=r.stato_procedurale,
                    scadenza=r.scadenza,
                    flag_ppp=_is_yes(r.flag_ppp_doppio_oggetto),
                    flag_pnrr="PNRR" in _tag_list(r),
                    flag_sopra_soglia_ue="sopra soglia UE" in _tag_list(r),
                    pre_gara_forza=_pre_gara_strength(r),
                    tag_tecnico=_tag_list(r),
                ),
                now=now,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("score.crashed", extra={"record_id": str(r.id), "err": str(exc)})
            job.error_message = f"{type(exc).__name__}: {exc}"
            continue

        r.score_commerciale = output.score
        r.priorita_commerciale = output.priority
        scored += 1
    job.records_valid = scored


async def _run() -> dict[str, int]:
    async with SessionLocal() as session:
        job = JobRun(job_name="score_and_dedupe", status="running")
        session.add(job)
        await session.flush()

        now = datetime.now(tz=UTC)
        await _process(session, job, now=now)

        job.ended_at = datetime.now(tz=UTC)
        job.status = "failed" if job.error_message else "success"
        await session.commit()
        return {
            "records_found": job.records_found,
            "records_valid": job.records_valid,
            "duplicates_removed": job.duplicates_removed,
        }


@celery_app.task(name="app.tasks.score_and_dedupe.score_and_dedupe")
def score_and_dedupe() -> dict[str, int]:
    return asyncio.run(_run())
