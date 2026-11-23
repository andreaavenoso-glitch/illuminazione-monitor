"""Preliminary analysis of the documentation of one notice: read the page and its attached documents,
store them (Document rows with their text) and extract the fields by rules. Free; Claude can be added later
for the fields rules cannot read."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

from app.celery_app import celery_app
from app.collectors.doc_fields import extract_fields
from app.db import SessionLocal
from app.tasks.verify_records import _fetch_plain, attachment_links
from shared_models import AnalisiRecord, Document, ProcurementRecord
from sqlalchemy import select

log = logging.getLogger(__name__)
MAX_ATTACHMENTS = 8


def _name(url: str) -> str:
    return urlsplit(url).path.rsplit("/", 1)[-1] or urlsplit(url).netloc


async def analyze(record_id: UUID) -> dict:
    async with SessionLocal() as s:
        rec = await s.get(ProcurementRecord, record_id)
        if rec is None:
            return {"error": "record non trovato"}
        link, ente = rec.link_bando, rec.ente
    text, raw = await _fetch_plain(link)
    docs: list[tuple[str, str, str]] = []  # (url, name, text)
    if text:
        docs.append((link, "pagina dell'avviso", text))
    if raw:
        for u in attachment_links(raw, base_url=link, limit=MAX_ATTACHMENTS):
            t, _ = await _fetch_plain(u)
            docs.append((u, _name(u), t))
    readable = [d for d in docs if d[2]]
    fields = extract_fields([(n, t) for _, n, t in readable], datetime.now(tz=UTC).date())
    documenti = [
        {"url": u, "nome": n, "caratteri": len(t), "letto": bool(t)} for u, n, t in docs
    ]
    async with SessionLocal() as s:
        for u, n, t in readable:
            checksum = hashlib.sha256(t.encode("utf-8")).hexdigest()
            exists = (
                await s.execute(
                    select(Document).where(Document.procurement_record_id == record_id, Document.checksum == checksum)
                )
            ).scalar_one_or_none()
            if exists is None:
                s.add(Document(
                    procurement_record_id=record_id, filename=n, storage_url=u, text_content=t, checksum=checksum,
                    mime_type="application/pdf" if u.lower().split("?")[0].endswith(".pdf") else "text/html",
                ))
        row = (
            await s.execute(select(AnalisiRecord).where(AnalisiRecord.procurement_record_id == record_id))
        ).scalar_one_or_none()
        if row is None:
            row = AnalisiRecord(procurement_record_id=record_id)
            s.add(row)
        row.documenti, row.campi, row.metodo, row.eseguita_il = documenti, fields, "regole", datetime.now(tz=UTC)
        await s.commit()
    log.info("analyze_record ente=%s documenti=%d campi=%d", ente, len(readable), len(fields))
    return {"ente": ente, "documenti": len(docs), "letti": len(readable), "campi": len(fields)}


@celery_app.task(name="app.tasks.analyze_record.analyze_record", soft_time_limit=600, time_limit=660)
def analyze_record(record_id: str) -> dict:
    return asyncio.run(analyze(UUID(record_id)))
