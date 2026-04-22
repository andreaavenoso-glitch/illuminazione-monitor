"""Materialize procurement_records from unprocessed raw_records.

Pipeline stage 2: reads every raw_record that has not yet produced a matching
procurement_record (lookup by raw_url first, CIG second) and either inserts a
new row or updates the existing one.

Upsert strategy for Sprint 5 (stronger dedup lands in Sprint 6):
- primary key: raw_record.raw_url → procurement_records.link_bando
- secondary: cig match
- when matched: update ``last_seen_at`` and any fields that were previously None
- when not matched: insert with ``first_seen_at`` = now

A per-job ``JobRun`` row captures counts (records_found/valid/weak).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.celery_app import celery_app
from app.db import SessionLocal
from app.domain.classification import classify_stato_procedurale, classify_tipo_novita
from app.domain.normalization import NormalizerInput, normalize
from shared_models import JobRun, ProcurementRecord, RawRecord, Source
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

BATCH_SIZE = 200


async def _process_batch(session: AsyncSession, job: JobRun) -> None:
    stmt = (
        select(RawRecord, Source)
        .outerjoin(Source, RawRecord.source_id == Source.id)
        .order_by(RawRecord.fetched_at.asc())
        .limit(BATCH_SIZE)
    )
    rows = (await session.execute(stmt)).all()
    now = datetime.now(tz=UTC)

    for raw, source in rows:
        job.records_found += 1
        try:
            processed = await _upsert(session, raw, source, now=now)
        except Exception as exc:  # noqa: BLE001
            log.exception("normalize.crashed", extra={"raw_id": str(raw.id), "err": str(exc)})
            job.error_message = f"{type(exc).__name__}: {exc}"
            continue

        if processed is None:
            continue
        if processed.is_weak_evidence:
            job.records_weak += 1
        else:
            job.records_valid += 1


async def _upsert(
    session: AsyncSession,
    raw: RawRecord,
    source: Source | None,
    *,
    now: datetime,
) -> ProcurementRecord | None:
    source_rank = source.source_priority_rank if source else 999
    payload = NormalizerInput(
        raw_title=raw.raw_title,
        raw_body=raw.raw_body,
        raw_url=raw.raw_url,
        raw_date=raw.raw_date,
        extracted=raw.extracted_json or {},
        source_priority_rank=source_rank,
    )
    normalized = normalize(payload)
    if normalized is None:
        return None  # out of perimeter

    stato = classify_stato_procedurale(
        descrizione=normalized.descrizione,
        raw_body=raw.raw_body,
        cig=normalized.cig,
        link=normalized.link_bando,
        atto_tipo=(raw.extracted_json or {}).get("atto_tipo"),
    )

    # Existing record? match on link first, cig fallback.
    existing = await _find_existing(session, link=normalized.link_bando, cig=normalized.cig)
    is_existing = existing is not None
    first_seen = existing.first_seen_at if existing else now
    tipo = classify_tipo_novita(
        first_seen_at=first_seen,
        data_pubblicazione=normalized.data_pubblicazione,
        is_existing_record=is_existing,
        stato_procedurale=stato,
        now=now,
    )

    if existing:
        _merge_fields(existing, normalized, stato=stato, tipo=tipo, now=now)
        return existing

    record = ProcurementRecord(
        ente=normalized.ente,
        descrizione=normalized.descrizione,
        importo=normalized.importo,
        cig=normalized.cig,
        data_pubblicazione=normalized.data_pubblicazione,
        scadenza=normalized.scadenza,
        regione=normalized.regione,
        provincia=normalized.provincia,
        comune=normalized.comune,
        tipologia_gara_procedura=normalized.tipologia_gara_procedura,
        link_bando=normalized.link_bando,
        macrosettore=normalized.macrosettore,
        source_priority_rank=normalized.source_priority_rank,
        stato_procedurale=stato,
        tipo_novita=tipo,
        flag_concessione_ambito=normalized.flag_concessione_ambito,
        flag_ppp_doppio_oggetto=normalized.flag_ppp_doppio_oggetto,
        flag_in_house_ambito=normalized.flag_in_house_ambito,
        flag_om=normalized.flag_om,
        flag_pre_gara=normalized.flag_pre_gara,
        tag_tecnico=",".join(normalized.tag_tecnico) if normalized.tag_tecnico else None,
        validation_level=normalized.validation_level,
        reliability_index=normalized.reliability_index,
        is_weak_evidence=normalized.is_weak_evidence,
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(record)
    await session.flush()
    return record


async def _find_existing(
    session: AsyncSession, *, link: str, cig: str | None
) -> ProcurementRecord | None:
    stmt = select(ProcurementRecord).where(ProcurementRecord.link_bando == link)
    hit = (await session.execute(stmt)).scalar_one_or_none()
    if hit or not cig:
        return hit
    stmt = select(ProcurementRecord).where(ProcurementRecord.cig == cig)
    return (await session.execute(stmt)).scalar_one_or_none()


def _merge_fields(
    target: ProcurementRecord,
    incoming,
    *,
    stato: str,
    tipo: str,
    now: datetime,
) -> None:
    target.last_seen_at = now
    target.stato_procedurale = stato
    target.tipo_novita = tipo
    for attr in (
        "descrizione",
        "importo",
        "cig",
        "data_pubblicazione",
        "scadenza",
        "regione",
        "provincia",
        "comune",
        "tipologia_gara_procedura",
    ):
        new_value = getattr(incoming, attr)
        if new_value and getattr(target, attr) in (None, ""):
            setattr(target, attr, new_value)

    for flag in (
        "flag_concessione_ambito",
        "flag_ppp_doppio_oggetto",
        "flag_in_house_ambito",
        "flag_om",
        "flag_pre_gara",
    ):
        new_value = getattr(incoming, flag)
        if new_value == "Yes":
            setattr(target, flag, "Yes")

    if incoming.tag_tecnico:
        existing_tags = set((target.tag_tecnico or "").split(",")) - {""}
        existing_tags.update(incoming.tag_tecnico)
        target.tag_tecnico = ",".join(sorted(existing_tags))

    target.validation_level = max(
        target.validation_level or "L1",
        incoming.validation_level,
    )
    target.reliability_index = incoming.reliability_index


async def _run_normalize() -> dict[str, int]:
    async with SessionLocal() as session:
        job = JobRun(job_name="normalize_records", status="running")
        session.add(job)
        await session.flush()

        await _process_batch(session, job)

        job.ended_at = datetime.now(tz=UTC)
        job.status = "failed" if job.error_message else "success"
        await session.commit()
        return {
            "records_found": job.records_found,
            "records_valid": job.records_valid,
            "records_weak": job.records_weak,
        }


@celery_app.task(name="app.tasks.normalize_records.normalize_records")
def normalize_records() -> dict[str, int]:
    return asyncio.run(_run_normalize())
