"""Preliminary analysis of the documentation of one notice: read the page and its attached documents,
store them (Document rows with their text) and extract the fields by rules. Free; Claude can be added later
for the fields rules cannot read."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

from app.celery_app import celery_app
from app.collectors.doc_collect import LIVELLI, collect_docs
from app.collectors.doc_fields import extract_fields
from app.db import SessionLocal
from app.tasks.verify_records import _fetch_plain
from shared_models import AnalisiRecord, Document, ProcurementRecord
from shared_models.pregara import pregara_tipi
from sqlalchemy import select

log = logging.getLogger(__name__)


async def analyze(record_id: UUID, profondita: str = "base") -> dict:
    livello = LIVELLI.get(profondita, LIVELLI["base"])
    profondita = profondita if profondita in LIVELLI else "base"
    async with SessionLocal() as s:
        rec = await s.get(ProcurementRecord, record_id)
        if rec is None:
            return {"error": "record non trovato"}
        link, ente, descrizione = rec.link_bando, rec.ente, rec.descrizione or ""
    collected, why = await collect_docs(link, _fetch_plain, livello)
    readable = [d for d in collected if d.text]
    today = datetime.now(tz=UTC).date()
    fields = extract_fields([(d.name, d.text) for d in readable], today)
    # the kind of pre-gara signal, from the title and from what the documents say
    tipi = pregara_tipi(descrizione + " " + " ".join(d.text[:4000] for d in readable))
    if tipi:
        fields["pregara_tipi"] = {"valore": tipi, "fonte": "titolo e documenti", "contesto": ""}
    documenti = [
        {"url": d.url, "nome": d.name, "caratteri": len(d.text), "letto": bool(d.text), "livello": d.depth}
        for d in collected
    ]
    async with SessionLocal() as s:
        for d in readable:
            checksum = hashlib.sha256(d.text.encode("utf-8")).hexdigest()
            exists = (
                await s.execute(
                    select(Document).where(Document.procurement_record_id == record_id, Document.checksum == checksum)
                )
            ).scalar_one_or_none()
            if exists is None:
                s.add(Document(
                    procurement_record_id=record_id, filename=d.name, storage_url=d.url, text_content=d.text,
                    checksum=checksum,
                    mime_type="application/pdf" if d.url.lower().split("?")[0].endswith(".pdf") else "text/html",
                ))
        row = (
            await s.execute(select(AnalisiRecord).where(AnalisiRecord.procurement_record_id == record_id))
        ).scalar_one_or_none()
        if row is None:
            row = AnalisiRecord(procurement_record_id=record_id)
            s.add(row)
        # a deep analysis is never replaced by a later base one
        if not (row.profondita == "approfondita" and profondita == "base"):
            row.documenti, row.campi, row.profondita = documenti, fields, profondita
            row.metodo, row.eseguita_il = "regole", datetime.now(tz=UTC)
        await s.commit()
    log.info("analyze_record ente=%s livello=%s documenti=%d letti=%d campi=%d stop=%s",
             ente, profondita, len(collected), len(readable), len(fields), why)
    return {"ente": ente, "profondita": profondita, "documenti": len(collected), "letti": len(readable),
            "campi": len(fields), "stop": why}


@celery_app.task(name="app.tasks.analyze_record.analyze_record", soft_time_limit=900, time_limit=960)
def analyze_record(record_id: str, profondita: str = "base") -> dict:
    return asyncio.run(analyze(UUID(record_id), profondita))
